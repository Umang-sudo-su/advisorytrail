import httpx
import base64
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.models import Scan, ScanStatus, Finding
from app.database import engine
from app.config import settings

OSV_BATCH_QUERY_URL = "https://api.osv.dev/v1/querybatch"

DEFAULT_TEST_REQUIREMENTS = """
urllib3==1.26.4
requests==2.25.0
jinja2==2.11.2
"""

def parse_requirements(content: str):
    packages = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*==\s*([a-zA-Z0-9_\-\.]+)", line)
        if match:
            packages.append((match.group(1), match.group(2)))
    return packages

async def fetch_manifest_from_github(owner_repo: str, commit_hash: str) -> str:
    if not settings.GITHUB_TOKEN:
        print("[GitHub API] GITHUB_TOKEN not set. Falling back to defaults.")
        return DEFAULT_TEST_REQUIREMENTS

    url = f"https://api.github.com/repos/{owner_repo}/contents/requirements.txt"
    params = {"ref": commit_hash}
    headers = {
        "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, headers=headers, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                if "content" in data and data.get("encoding") == "base64":
                    decoded_bytes = base64.b64decode(data["content"])
                    print(f"[GitHub API] Fetched requirements.txt from {owner_repo}@{commit_hash[:7]}")
                    return decoded_bytes.decode("utf-8")
            print(f"[GitHub API] API returned {resp.status_code}. Falling back to defaults.")
    except Exception as e:
        print(f"[GitHub API] Error: {e}")

    return DEFAULT_TEST_REQUIREMENTS

async def update_github_commit_status(owner_repo: str, commit_hash: str, state: str, description: str, target_url: str = None):
    if not settings.GITHUB_TOKEN or not owner_repo or "/" not in owner_repo:
        return

    url = f"https://api.github.com/repos/{owner_repo}/statuses/{commit_hash}"
    headers = {
        "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    payload = {
        "state": state,
        "description": description[:140],
        "context": "security/buildshield"
    }
    if target_url:
        payload["target_url"] = target_url

    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, headers=headers, json=payload, timeout=10.0)
    except Exception:
        pass

async def run_osv_scan(scan_id: int):
    async with AsyncSession(engine, expire_on_commit=False) as db:
        result = await db.execute(
            select(Scan).options(selectinload(Scan.repository)).where(Scan.id == scan_id)
        )
        scan = result.scalars().first()
        if not scan:
            return

        scan.status = ScanStatus.IN_PROGRESS.value
        await db.commit()

        repo_identifier = scan.repository.name if scan.repository and "/" in scan.repository.name else None

        if repo_identifier:
            await update_github_commit_status(
                repo_identifier, scan.commit_hash, "pending", 
                "BuildShield security scan in progress...", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}"
            )

        try:
            manifest_content = await fetch_manifest_from_github(repo_identifier, scan.commit_hash) if repo_identifier else DEFAULT_TEST_REQUIREMENTS
            parsed_packages = parse_requirements(manifest_content)

            if not parsed_packages:
                scan.status = ScanStatus.COMPLETED.value
                await db.commit()
                if repo_identifier:
                    await update_github_commit_status(
                        repo_identifier, scan.commit_hash, "success", 
                        "BuildShield: No dependencies found.", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}"
                    )
                return

            queries = [{"package": {"name": pkg, "ecosystem": "PyPI"}, "version": ver} for pkg, ver in parsed_packages]
            
            async with httpx.AsyncClient() as client:
                response = await client.post(OSV_BATCH_QUERY_URL, json={"queries": queries}, timeout=15.0)
                response.raise_for_status()
                batch_data = response.json()

                results = batch_data.get("results", [])
                total_findings = 0
                high_critical_count = 0

                for idx, res in enumerate(results):
                    pkg_name, pkg_version = parsed_packages[idx]
                    vulns = res.get("vulns", [])
                    
                    for vuln in vulns:
                        severity_list = vuln.get("database_specific", {}).get("severity") or vuln.get("severity", [])
                        severity_str = severity_list.upper() if isinstance(severity_list, str) else "HIGH"

                        if severity_str in ["HIGH", "CRITICAL"]:
                            high_critical_count += 1

                        # --- ROBUST FIXED VERSION EXTRACTION ---
                        def extract_fixed(data):
                            for affected in data.get("affected", []):
                                if affected.get("package", {}).get("name") == pkg_name:
                                    for rng in affected.get("ranges", []):
                                        # Ignore GIT commit hashes, grab standard semantic versions
                                        if rng.get("type") in ["ECOSYSTEM", "SEMVER"]:
                                            for event in rng.get("events", []):
                                                if "fixed" in event:
                                                    return event["fixed"]
                            return None

                        # 1. Try to extract from the batch response
                        fixed_version = extract_fixed(vuln)

                        # 2. If truncated, fetch the detailed vulnerability record directly
                        if not fixed_version:
                            detail_resp = await client.get(f"https://api.osv.dev/v1/vulns/{vuln.get('id')}", timeout=10.0)
                            if detail_resp.status_code == 200:
                                fixed_version = extract_fixed(detail_resp.json())

                        new_finding = Finding(
                            scan_id=scan.id,
                            osv_id=vuln.get("id", "UNKNOWN"),
                            package_name=pkg_name,
                            package_version=pkg_version,
                            severity=severity_str,
                            details={
                                "summary": vuln.get("summary", "No summary provided"),
                                "ecosystem": "PyPI",
                                "fixed_version": fixed_version
                            }
                        )
                        db.add(new_finding)
                        total_findings += 1

            scan.status = ScanStatus.COMPLETED.value
            await db.commit()

            final_state = "failure" if total_findings > 0 else "success"
            status_desc = f"BuildShield: {total_findings} vulnerabilities found." if total_findings > 0 else "BuildShield: Scan passed!"

            if repo_identifier:
                await update_github_commit_status(
                    repo_identifier, scan.commit_hash, final_state, status_desc, f"http://127.0.0.1:8000/api/v1/scans/{scan.id}"
                )

        except Exception as e:
            scan.status = ScanStatus.FAILED.value
            await db.commit()
            print(f"Scan {scan_id} failed: {e}")
            if repo_identifier:
                await update_github_commit_status(
                    repo_identifier, scan.commit_hash, "error", f"BuildShield scan failed: {str(e)[:50]}", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}"
                )