import httpx
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
    """Parses package==version pairs from a requirements.txt file string."""
    packages = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*==\s*([a-zA-Z0-9_\-\.]+)", line)
        if match:
            packages.append((match.group(1), match.group(2)))
    return packages

async def update_github_commit_status(owner_repo: str, commit_hash: str, state: str, description: str, target_url: str = None):
    """Posts commit status check back to GitHub Status API."""
    if not settings.GITHUB_TOKEN:
        print(f"[GitHub Status] Skipped: GITHUB_TOKEN env var not set.")
        return

    if not owner_repo or "/" not in owner_repo:
        print(f"[GitHub Status] Skipped: Invalid repo format '{owner_repo}'. Expected 'owner/repo'.")
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
            resp = await client.post(url, headers=headers, json=payload, timeout=10.0)
            if resp.status_code in (200, 201):
                print(f"[GitHub Status] Updated {owner_repo}@{commit_hash[:7]} -> state={state}")
            else:
                print(f"[GitHub Status] API returned {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[GitHub Status] Request failed: {e}")

async def run_osv_scan(scan_id: int, manifest_content: str = None):
    """Parses requirements, queries OSV batch API, and reports status to GitHub."""
    async with AsyncSession(engine, expire_on_commit=False) as db:
        result = await db.execute(
            select(Scan).options(selectinload(Scan.repository)).where(Scan.id == scan_id)
        )
        scan = result.scalars().first()
        
        if not scan:
            return

        scan.status = ScanStatus.IN_PROGRESS.value
        await db.commit()

        repo_identifier = None
        if scan.repository:
            if "/" in scan.repository.name:
                repo_identifier = scan.repository.name
            elif scan.repository.url and "github.com/" in scan.repository.url:
                repo_identifier = scan.repository.url.split("github.com/")[-1].rstrip(".git")

        if repo_identifier:
            await update_github_commit_status(
                owner_repo=repo_identifier,
                commit_hash=scan.commit_hash,
                state="pending",
                description="BuildShield security scan in progress...",
                target_url=f"http://127.0.0.1:8000/api/v1/scans/{scan.id}"
            )

        try:
            content_to_parse = manifest_content or DEFAULT_TEST_REQUIREMENTS
            parsed_packages = parse_requirements(content_to_parse)

            if not parsed_packages:
                scan.status = ScanStatus.COMPLETED.value
                await db.commit()
                if repo_identifier:
                    await update_github_commit_status(
                        owner_repo=repo_identifier,
                        commit_hash=scan.commit_hash,
                        state="success",
                        description="BuildShield: No dependencies found to scan.",
                        target_url=f"http://127.0.0.1:8000/api/v1/scans/{scan.id}"
                    )
                return

            queries = [
                {
                    "package": {"name": pkg, "ecosystem": "PyPI"},
                    "version": ver
                }
                for pkg, ver in parsed_packages
            ]
            
            payload = {"queries": queries}

            async with httpx.AsyncClient() as client:
                response = await client.post(OSV_BATCH_QUERY_URL, json=payload, timeout=15.0)
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
                    severity_str = "HIGH"
                    if isinstance(severity_list, str):
                        severity_str = severity_list.upper()

                    if severity_str in ["HIGH", "CRITICAL"]:
                        high_critical_count += 1

                    new_finding = Finding(
                        scan_id=scan.id,
                        osv_id=vuln.get("id", "UNKNOWN"),
                        package_name=pkg_name,
                        package_version=pkg_version,
                        severity=severity_str,
                        details={
                            "summary": vuln.get("summary", "No summary provided"),
                            "ecosystem": "PyPI"
                        }
                    )
                    db.add(new_finding)
                    total_findings += 1

            scan.status = ScanStatus.COMPLETED.value
            await db.commit()

            final_state = "failure" if total_findings > 0 else "success"
            status_desc = (
                f"BuildShield: {total_findings} vulnerabilities found ({high_critical_count} High/Critical)."
                if total_findings > 0
                else "BuildShield: Scan passed! No vulnerabilities detected."
            )

            if repo_identifier:
                await update_github_commit_status(
                    owner_repo=repo_identifier,
                    commit_hash=scan.commit_hash,
                    state=final_state,
                    description=status_desc,
                    target_url=f"http://127.0.0.1:8000/api/v1/scans/{scan.id}"
                )

        except Exception as e:
            scan.status = ScanStatus.FAILED.value
            await db.commit()
            print(f"Scan {scan_id} failed: {e}")
            if repo_identifier:
                await update_github_commit_status(
                    owner_repo=repo_identifier,
                    commit_hash=scan.commit_hash,
                    state="error",
                    description=f"BuildShield scan failed: {str(e)[:50]}",
                    target_url=f"http://127.0.0.1:8000/api/v1/scans/{scan.id}"
                )
