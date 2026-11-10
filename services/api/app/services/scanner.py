import asyncio
import httpx
import base64
import re
import json
from datetime import datetime, timezone
from urllib.parse import urlparse
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.models import Scan, ScanStatus, Finding, Policy
from app.database import engine
from app.config import settings

OSV_BATCH_QUERY_URL = "https://api.osv.dev/v1/querybatch"

SUPPORTED_MANIFESTS = ["package-lock.json", "poetry.lock", "requirements.txt"]


def repository_identifier(name: str, url: str) -> str:
    """Resolves the GitHub ``owner/repo`` slug a scan should read its manifest from.

    Repositories are stored with a display name like ``test-repo`` and the slug only
    lives in the URL, so the name alone is not enough to locate the manifest.
    """
    if url:
        parsed = urlparse(url)
        if parsed.netloc.lower() in {"github.com", "www.github.com"}:
            parts = [part for part in parsed.path.strip("/").split("/") if part]
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1].removesuffix('.git')}"
    if name and "/" in name:
        return name
    return None

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

def is_queryable_version(version) -> bool:
    """OSV rejects the whole batch when a version is missing or not a plain version."""
    return isinstance(version, str) and bool(re.match(r"^\d+(\.\d+)*([-+][0-9A-Za-z.\-]+)?$", version.strip()))


def parse_package_lock(content: str):
    packages = []
    try:
        data = json.loads(content)
        # Handle NPM v2/v3 lockfile format
        if "packages" in data:
            for pkg_path, details in data["packages"].items():
                if not pkg_path or not is_queryable_version(details.get("version")): continue
                name = pkg_path.split("node_modules/")[-1]
                if not name: continue
                packages.append((name, details["version"], "npm"))
        # Handle NPM v1 lockfile format
        elif "dependencies" in data:
            for name, details in data["dependencies"].items():
                if not is_queryable_version(details.get("version")): continue
                packages.append((name, details["version"], "npm"))
    except json.JSONDecodeError:
        pass
    return packages

async def fetch_manifest_from_github(owner_repo: str, commit_hash: str):
    """Returns ``(manifest_name, content)``, or ``(None, None)`` when nothing readable exists."""
    if not settings.GITHUB_TOKEN:
        print("[GitHub API] GITHUB_TOKEN not set. Cannot read repository manifests.")
        return None, None

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
                    
            print(f"[GitHub API] No supported manifests found in {owner_repo}@{commit_hash[:7]}.")
    except Exception as e:
        print(f"[GitHub API] Error: {e}")

    return None, None

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

        commit_hash = scan.commit_hash
        repository = scan.repository
        repo_identifier = repository_identifier(
            repository.name if repository else "",
            repository.url if repository else "",
        )
        if repo_identifier: 
            await update_github_commit_status(repo_identifier, scan.commit_hash, "pending", "Scanning dependencies...", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")

        try:
            # 1. Fetch Head and Base Manifests
            manifest_name, manifest_content = None, None
            base_parsed = []

            if repo_identifier:
                manifest_name, manifest_content = await fetch_manifest_from_github(repo_identifier, commit_hash)

                # Fetch Base to Diff
                if manifest_content and scan.base_commit_hash:
                    base_name, base_content = await fetch_manifest_from_github(repo_identifier, scan.base_commit_hash)
                    if base_content:
                        if base_name == "package-lock.json": base_parsed = parse_package_lock(base_content)
                        elif base_name == "poetry.lock": base_parsed = parse_poetry_lock(base_content)
                        else: base_parsed = parse_requirements_txt(base_content)

            # Never invent a manifest: a repository we cannot read is an incomplete scan,
            # not a scan of unrelated demo packages.
            if not manifest_content:
                scan.status = ScanStatus.FAILED.value
                scan.finished_at = datetime.now(timezone.utc)
                await db.commit()
                if repo_identifier:
                    await update_github_commit_status(repo_identifier, commit_hash, "error", "BuildShield: no readable dependency manifest.", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")
                return

            # 2. Parse Head Manifest
            parsed_packages = []
            if manifest_name == "package-lock.json": parsed_packages = parse_package_lock(manifest_content)
            elif manifest_name == "poetry.lock": parsed_packages = parse_poetry_lock(manifest_content)
            else: parsed_packages = parse_requirements_txt(manifest_content)
            
            base_pkg_versions = {(p[0], p[1]) for p in base_parsed}

            if not parsed_packages:
                scan.status = ScanStatus.COMPLETED.value
                scan.finished_at = datetime.now(timezone.utc)
                await db.commit()
                if repo_identifier: 
                    await update_github_commit_status(repo_identifier, commit_hash, "success", f"BuildShield: No dependencies found in {manifest_name}.", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")
                return

            # 3. Query OSV using the dynamically mapped ecosystem
            parsed_packages = [(p, v, e) for p, v, e in parsed_packages if is_queryable_version(v)]

            if not parsed_packages:
                scan.status = ScanStatus.COMPLETED.value
                scan.finished_at = datetime.now(timezone.utc)
                await db.commit()
                if repo_identifier:
                    await update_github_commit_status(repo_identifier, commit_hash, "success", f"BuildShield: no pinned dependency versions found in {manifest_name}.", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")
                return

            def extract_fixed(data, package: str):
                for affected in data.get("affected", []):
                    if affected.get("package", {}).get("name") == package:
                        for rng in affected.get("ranges", []):
                            if rng.get("type") in ["ECOSYSTEM", "SEMVER"]:
                                for event in rng.get("events", []):
                                    if "fixed" in event: return event["fixed"]
                return None

            async def resolve_fixed_version(client, vuln, package: str):
                fixed = extract_fixed(vuln, package)
                if fixed:
                    return fixed
                try:
                    detail_resp = await client.get(f"https://api.osv.dev/v1/vulns/{vuln.get('id')}", timeout=10.0)
                    if detail_resp.status_code == 200:
                        return extract_fixed(detail_resp.json(), package)
                except httpx.HTTPError:
                    pass
                return None

            total_findings = 0
            lookups = asyncio.Semaphore(8)

            async with httpx.AsyncClient() as client:
                # OSV caps batch size, so query in chunks and keep result order aligned.
                for start in range(0, len(parsed_packages), 250):
                    chunk = parsed_packages[start:start + 250]
                    queries = [{"package": {"name": pkg, "ecosystem": eco}, "version": ver} for pkg, ver, eco in chunk]

                    response = await client.post(OSV_BATCH_QUERY_URL, json={"queries": queries}, timeout=30.0)
                    if response.status_code == 400:
                        print(f"[OSV] Rejected query batch: {response.text[:200]}")
                        continue
                    response.raise_for_status()
                    batch_data = response.json()

                    results = batch_data.get("results", [])
                    matches = []

                    for idx, res in enumerate(results):
                        pkg_name, pkg_version, pkg_eco = chunk[idx]
                        for vuln in res.get("vulns", []):
                            severity_list = vuln.get("database_specific", {}).get("severity") or vuln.get("severity", [])
                            severity_str = severity_list.upper() if isinstance(severity_list, str) else "HIGH"
                            matches.append((vuln, pkg_name, pkg_version, pkg_eco, severity_str))

                    async def lookup(item):
                        async with lookups:
                            return await resolve_fixed_version(client, item[0], item[1])

                    # Advisory detail lookups are independent, so run them together.
                    fixed_versions = await asyncio.gather(*(lookup(item) for item in matches))

                    for (vuln, pkg_name, pkg_version, pkg_eco, severity_str), fixed_version in zip(matches, fixed_versions):
                        db.add(Finding(
                            scan_id=scan.id,
                            osv_id=vuln.get("id", "UNKNOWN"),
                            package_name=pkg_name,
                            package_version=pkg_version,
                            severity=severity_str,
                            details={
                                "summary": vuln.get("summary", "No summary provided"),
                                "ecosystem": pkg_eco,
                                "fixed_version": fixed_version,
                                "is_new": (pkg_name, pkg_version) not in base_pkg_versions
                            }
                        ))
                        total_findings += 1

            scan.status = ScanStatus.COMPLETED.value
            scan.finished_at = datetime.now(timezone.utc)
            
            # --- POLICY EVALUATION ENGINE ---
            policy_result = await db.execute(select(Policy).where(Policy.repository_id == scan.repository_id))
            policy_rules = [p.rule_type for p in policy_result.scalars().all()]
            
            critical_count = (
                await db.execute(
                    select(func.count(Finding.id)).where(
                        Finding.scan_id == scan.id, Finding.severity == "CRITICAL"
                    )
                )
            ).scalar() or 0
            
            final_state = "success"
            status_desc = f"BuildShield: {manifest_name} passed!"
            
            if total_findings > 0:
                if "WARN_ON_PR" in policy_rules:
                    final_state = "success"
                    status_desc = f"BuildShield: {total_findings} vulns found (Warning Mode)."
                elif "FAIL_ON_CRITICAL" in policy_rules:
                    if critical_count > 0:
                        final_state = "failure"
                        status_desc = f"BuildShield: {critical_count} CRITICAL vulns found!"
                    else:
                        final_state = "success"
                        status_desc = f"BuildShield: {total_findings} vulns found (None Critical)."
                else:
                    final_state = "failure"
                    status_desc = f"BuildShield: {total_findings} vulnerabilities found in {manifest_name}."
            
            await db.commit()

            if repo_identifier:
                await update_github_commit_status(repo_identifier, scan.commit_hash, final_state, status_desc, f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")

        except Exception as e:
            # Discard any partially collected findings, then mark the scan incomplete.
            await db.rollback()
            await db.execute(
                update(Scan).where(Scan.id == scan_id).values(
                    status=ScanStatus.FAILED.value,
                    finished_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            print(f"[Scan {scan_id}] failed: {e}")
            if repo_identifier:
                await update_github_commit_status(repo_identifier, commit_hash, "error", f"BuildShield scan failed: {str(e)[:50]}", f"http://127.0.0.1:8000/api/v1/scans/{scan_id}")
