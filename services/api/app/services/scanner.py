import httpx
import base64
import re
import json
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

SUPPORTED_MANIFESTS = ["package-lock.json", "poetry.lock", "requirements.txt"]

def parse_requirements_txt(content: str):
    packages = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        match = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*==\s*([a-zA-Z0-9_\-\.]+)", line)
        if match: packages.append((match.group(1), match.group(2), "PyPI"))
    return packages

def parse_poetry_lock(content: str):
    packages = []
    current_pkg, current_ver = None, None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("[[package]]"):
            if current_pkg and current_ver:
                packages.append((current_pkg, current_ver, "PyPI"))
            current_pkg, current_ver = None, None
        elif line.startswith("name = "):
            current_pkg = line.split("=")[1].strip().strip('"').strip("'")
        elif line.startswith("version = "):
            current_ver = line.split("=")[1].strip().strip('"').strip("'")
    if current_pkg and current_ver:
        packages.append((current_pkg, current_ver, "PyPI"))
    return packages

def parse_package_lock(content: str):
    packages = []
    try:
        data = json.loads(content)
        # Handle NPM v2/v3 lockfile format
        if "packages" in data:
            for pkg_path, details in data["packages"].items():
                if not pkg_path or not details.get("version"): continue
                name = pkg_path.split("node_modules/")[-1]
                packages.append((name, details["version"], "npm"))
        # Handle NPM v1 lockfile format
        elif "dependencies" in data:
            for name, details in data["dependencies"].items():
                packages.append((name, details.get("version"), "npm"))
    except json.JSONDecodeError:
        pass
    return packages

async def fetch_manifest_from_github(owner_repo: str, commit_hash: str):
    if not settings.GITHUB_TOKEN:
        print("[GitHub API] GITHUB_TOKEN not set. Falling back to defaults.")
        return "requirements.txt", DEFAULT_TEST_REQUIREMENTS

    headers = {
        "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    try:
        async with httpx.AsyncClient() as client:
            for manifest_name in SUPPORTED_MANIFESTS:
                url = f"https://api.github.com/repos/{owner_repo}/contents/{manifest_name}"
                resp = await client.get(url, params={"ref": commit_hash}, headers=headers, timeout=10.0)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if "content" in data and data.get("encoding") == "base64":
                        decoded_bytes = base64.b64decode(data["content"])
                        print(f"[GitHub API] Fetched {manifest_name} from {owner_repo}@{commit_hash[:7]}")
                        return manifest_name, decoded_bytes.decode("utf-8")
                    
            print(f"[GitHub API] No supported manifests found. Falling back to defaults.")
    except Exception as e:
        print(f"[GitHub API] Error: {e}")

    return "requirements.txt", DEFAULT_TEST_REQUIREMENTS

async def update_github_commit_status(owner_repo: str, commit_hash: str, state: str, description: str, target_url: str = None):
    if not settings.GITHUB_TOKEN or not owner_repo or "/" not in owner_repo: return
    url = f"https://api.github.com/repos/{owner_repo}/statuses/{commit_hash}"
    headers = {"Authorization": f"Bearer {settings.GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    payload = {"state": state, "description": description[:140], "context": "security/buildshield"}
    if target_url: payload["target_url"] = target_url
    try:
        async with httpx.AsyncClient() as client: await client.post(url, headers=headers, json=payload, timeout=10.0)
    except Exception: pass

async def run_osv_scan(scan_id: int):
    async with AsyncSession(engine, expire_on_commit=False) as db:
        result = await db.execute(select(Scan).options(selectinload(Scan.repository)).where(Scan.id == scan_id))
        scan = result.scalars().first()
        if not scan: return

        scan.status = ScanStatus.IN_PROGRESS.value
        await db.commit()

        repo_identifier = scan.repository.name if scan.repository and "/" in scan.repository.name else None
        if repo_identifier: 
            await update_github_commit_status(repo_identifier, scan.commit_hash, "pending", "Scanning dependencies...", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")

        try:
            # 1. Fetch Manifest dynamically
            manifest_name, manifest_content = ("requirements.txt", DEFAULT_TEST_REQUIREMENTS)
            if repo_identifier:
                manifest_name, manifest_content = await fetch_manifest_from_github(repo_identifier, scan.commit_hash)
            
            # 2. Parse based on file type
            parsed_packages = []
            if manifest_name == "package-lock.json":
                parsed_packages = parse_package_lock(manifest_content)
            elif manifest_name == "poetry.lock":
                parsed_packages = parse_poetry_lock(manifest_content)
            else:
                parsed_packages = parse_requirements_txt(manifest_content)

            if not parsed_packages:
                scan.status = ScanStatus.COMPLETED.value
                await db.commit()
                if repo_identifier: 
                    await update_github_commit_status(repo_identifier, scan.commit_hash, "success", f"BuildShield: No dependencies found in {manifest_name}.", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")
                return

            # 3. Query OSV using the dynamically mapped ecosystem
            queries = [{"package": {"name": pkg, "ecosystem": eco}, "version": ver} for pkg, ver, eco in parsed_packages]
            
            async with httpx.AsyncClient() as client:
                response = await client.post(OSV_BATCH_QUERY_URL, json={"queries": queries}, timeout=15.0)
                response.raise_for_status()
                batch_data = response.json()

                results = batch_data.get("results", [])
                total_findings = 0

                for idx, res in enumerate(results):
                    pkg_name, pkg_version, pkg_eco = parsed_packages[idx]
                    for vuln in res.get("vulns", []):
                        severity_list = vuln.get("database_specific", {}).get("severity") or vuln.get("severity", [])
                        severity_str = severity_list.upper() if isinstance(severity_list, str) else "HIGH"

                        def extract_fixed(data):
                            for affected in data.get("affected", []):
                                if affected.get("package", {}).get("name") == pkg_name:
                                    for rng in affected.get("ranges", []):
                                        if rng.get("type") in ["ECOSYSTEM", "SEMVER"]:
                                            for event in rng.get("events", []):
                                                if "fixed" in event: return event["fixed"]
                            return None

                        fixed_version = extract_fixed(vuln)
                        if not fixed_version:
                            detail_resp = await client.get(f"https://api.osv.dev/v1/vulns/{vuln.get('id')}", timeout=10.0)
                            if detail_resp.status_code == 200: fixed_version = extract_fixed(detail_resp.json())

                        db.add(Finding(
                            scan_id=scan.id, 
                            osv_id=vuln.get("id", "UNKNOWN"), 
                            package_name=pkg_name, 
                            package_version=pkg_version, 
                            severity=severity_str, 
                            details={
                                "summary": vuln.get("summary", "No summary provided"), 
                                "ecosystem": pkg_eco, 
                                "fixed_version": fixed_version
                            }
                        ))
                        total_findings += 1

            scan.status = ScanStatus.COMPLETED.value
            await db.commit()

            final_state = "failure" if total_findings > 0 else "success"
            status_desc = f"BuildShield: {total_findings} vulnerabilities found in {manifest_name}." if total_findings > 0 else f"BuildShield: {manifest_name} passed!"

            if repo_identifier:
                await update_github_commit_status(repo_identifier, scan.commit_hash, final_state, status_desc, f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")

        except Exception as e:
            scan.status = ScanStatus.FAILED.value
            await db.commit()
            if repo_identifier:
                await update_github_commit_status(repo_identifier, scan.commit_hash, "error", f"BuildShield scan failed: {str(e)[:50]}", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")
