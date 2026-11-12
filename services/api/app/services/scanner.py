import asyncio
import logging

import httpx
import base64
from contextvars import ContextVar
import re
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.models import Scan, ScanStatus, Finding
from app.database import engine
from app.config import settings
from app.services.policy import evaluate_check_run
from app.services.preferences import get_workspace_row, scan_config
from app.services.github_auth import load_connection as load_github_connection
from app.services.notifications import notify_scan_result

# Set per scan so status updates use the connected token without threading it through every call.
_GITHUB_TOKEN_VAR: ContextVar[str | None] = ContextVar("advisorytrail_github_token", default=None)

logger = logging.getLogger(__name__)

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

SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


def normalize_severity(value) -> str:
    """Maps OSV / GitHub Advisory severity text to one of the four UI levels."""
    if not isinstance(value, str):
        return "HIGH"
    text = value.strip().upper()
    if "CRITICAL" in text:
        return "CRITICAL"
    if "HIGH" in text:
        return "HIGH"
    if "MODERATE" in text or "MEDIUM" in text:
        return "MEDIUM"
    if "LOW" in text:
        return "LOW"
    return "HIGH"


def advisory_severity(*sources) -> str:
    """Picks the first usable severity: database_specific, affected entry, then CVSS."""
    for source in sources:
        if not source:
            continue
        database_specific = source.get("database_specific") or {}
        severity = database_specific.get("severity")
        if isinstance(severity, str) and severity.strip():
            return normalize_severity(severity)
        for affected in source.get("affected") or []:
            severity = (affected.get("database_specific") or {}).get("severity")
            if isinstance(severity, str) and severity.strip():
                return normalize_severity(severity)
        for entry in source.get("severity") or []:
            if isinstance(entry, str):
                return normalize_severity(entry)
    return "HIGH"


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

async def fetch_manifest_from_github(owner_repo: str, commit_hash: str, token: str | None = None):
    """Returns ``(manifest_name, content)``, or ``(None, None)`` when nothing readable exists."""
    if not token:
        print("[GitHub API] No GitHub token available. Cannot read repository manifests.")
        return None, None

    headers = {
        "Authorization": f"Bearer {token}",
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

async def update_github_commit_status(owner_repo: str, commit_hash: str, state: str, description: str, target_url: str = None, token: str | None = None) -> tuple[bool, str]:
    """Posts a commit status and reports why it was not published.

    Returns ``(published, reason)`` so the caller can log a refusal such as a token
    without write access instead of dropping it silently.
    """
    token = token or _GITHUB_TOKEN_VAR.get()
    if not token:
        return False, "no GitHub token is connected"
    if not owner_repo or "/" not in owner_repo:
        return False, "repository is not a GitHub owner/name"

    url = f"https://api.github.com/repos/{owner_repo}/statuses/{commit_hash}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    payload = {"state": state, "description": description[:140], "context": "security/advisorytrail"}
    if target_url:
        payload["target_url"] = target_url
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
    except httpx.HTTPError as error:
        return False, f"request to GitHub failed ({type(error).__name__})"

    if response.status_code in {200, 201}:
        return True, "published"
    if response.status_code in {401, 403, 404}:
        return False, (
            f"GitHub refused it (HTTP {response.status_code}); the connected token needs "
            f"write access to {owner_repo}"
        )
    return False, f"GitHub returned HTTP {response.status_code}"


async def push_commit_status(scan_id: int, owner_repo: str, commit_hash: str, state: str, description: str, target_url: str) -> None:
    """Publishes a commit status, logging any refusal with its reason."""
    published, reason = await update_github_commit_status(owner_repo, commit_hash, state, description, target_url)
    if not published:
        logger.warning("[Scan %s] GitHub commit status not published: %s", scan_id, reason)

_SCAN_SEMAPHORE: asyncio.Semaphore | None = None
_SCAN_SEMAPHORE_SIZE = 0


def _semaphore_for(size: int) -> asyncio.Semaphore:
    """Shared concurrency gate; rebuilt whenever the configured limit changes."""
    global _SCAN_SEMAPHORE, _SCAN_SEMAPHORE_SIZE

    size = max(1, min(10, int(size)))
    if _SCAN_SEMAPHORE is None or _SCAN_SEMAPHORE_SIZE != size:
        _SCAN_SEMAPHORE = asyncio.Semaphore(size)
        _SCAN_SEMAPHORE_SIZE = size
    return _SCAN_SEMAPHORE


async def run_scan_with_limits(scan_id: int):
    """Runs a scan under the concurrency limit saved in Settings → Scan Configuration."""
    async with AsyncSession(engine, expire_on_commit=False) as db:
        config = scan_config(await get_workspace_row(db))

    semaphore = _semaphore_for(config.get("concurrency", 2))
    async with semaphore:
        await run_osv_scan(scan_id)


async def run_osv_scan(scan_id: int):
    async with AsyncSession(engine, expire_on_commit=False) as db:
        result = await db.execute(select(Scan).options(selectinload(Scan.repository)).where(Scan.id == scan_id))
        scan = result.scalars().first()
        if not scan: return

        config = scan_config(await get_workspace_row(db))
        timeout_seconds = int(config.get("timeout_seconds", 600))
        deadline = time.monotonic() + timeout_seconds

        connection = await load_github_connection(db)
        github_token = connection.token
        _GITHUB_TOKEN_VAR.set(github_token)

        scan.status = ScanStatus.IN_PROGRESS.value
        await db.commit()

        commit_hash = scan.commit_hash
        repository = scan.repository
        repo_identifier = repository_identifier(
            repository.name if repository else "",
            repository.url if repository else "",
        )
        if repo_identifier: 
            await push_commit_status(scan_id, repo_identifier, scan.commit_hash, "pending", "Scanning dependencies...", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")

        try:
            # 1. Fetch Head and Base Manifests
            manifest_name, manifest_content = None, None
            base_parsed = []

            base_name, base_content = None, None
            if repo_identifier:
                # Head and base are independent GitHub round trips, so fetch them together
                # instead of paying both latencies back to back.
                if scan.base_commit_hash:
                    (manifest_name, manifest_content), (base_name, base_content) = await asyncio.gather(
                        fetch_manifest_from_github(repo_identifier, commit_hash, github_token),
                        fetch_manifest_from_github(repo_identifier, scan.base_commit_hash, github_token),
                    )
                else:
                    manifest_name, manifest_content = await fetch_manifest_from_github(repo_identifier, commit_hash, github_token)

                # Parse Base to Diff
                if manifest_content and base_content:
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
                    await push_commit_status(scan_id, repo_identifier, commit_hash, "error", "AdvisoryTrail: no readable dependency manifest.", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")
                try:
                    await notify_scan_result(
                        db,
                        scan.id,
                        repository.name if repository else f"repository-{scan.repository_id}",
                        commit_hash,
                        "failed",
                        "No readable dependency manifest was found for that commit.",
                    )
                except Exception as notify_error:
                    print(f"[Scan {scan_id}] failure notification failed: {notify_error}")
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
                    await push_commit_status(scan_id, repo_identifier, commit_hash, "success", f"AdvisoryTrail: No dependencies found in {manifest_name}.", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")
                return

            # 3. Query OSV using the dynamically mapped ecosystem
            parsed_packages = [(p, v, e) for p, v, e in parsed_packages if is_queryable_version(v)]

            if not parsed_packages:
                scan.status = ScanStatus.COMPLETED.value
                scan.finished_at = datetime.now(timezone.utc)
                await db.commit()
                if repo_identifier:
                    await push_commit_status(scan_id, repo_identifier, commit_hash, "success", f"AdvisoryTrail: no pinned dependency versions found in {manifest_name}.", f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")
                return

            def extract_fixed(data, package: str):
                for affected in data.get("affected", []):
                    if affected.get("package", {}).get("name") == package:
                        for rng in affected.get("ranges", []):
                            if rng.get("type") in ["ECOSYSTEM", "SEMVER"]:
                                for event in rng.get("events", []):
                                    if "fixed" in event: return event["fixed"]
                return None

            total_findings = 0
            blocking_new = 0
            lookups = asyncio.Semaphore(8)
            seen: set[tuple[str, str, str]] = set()

            async with httpx.AsyncClient() as client:
                # OSV caps batch size, so query in chunks and keep result order aligned.
                for start in range(0, len(parsed_packages), 250):
                    # A scan that runs past the configured timeout must fail, never look clean.
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"scan exceeded the configured {timeout_seconds}s timeout")

                    chunk = parsed_packages[start:start + 250]
                    queries = [{"package": {"name": pkg, "ecosystem": eco}, "version": ver} for pkg, ver, eco in chunk]

                    response = await client.post(
                        OSV_BATCH_QUERY_URL,
                        json={"queries": queries},
                        timeout=max(5.0, min(30.0, deadline - time.monotonic())),
                    )
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
                            matches.append((vuln, pkg_name, pkg_version, pkg_eco))

                    # The batch endpoint only returns ids; fetch each advisory once so the
                    # finding carries its real severity, summary and fixed version.
                    async def load_advisory(item):
                        advisory_id = item[0].get("id")
                        if not advisory_id:
                            return {}
                        async with lookups:
                            try:
                                detail_response = await client.get(
                                    f"https://api.osv.dev/v1/vulns/{advisory_id}", timeout=10.0
                                )
                                if detail_response.status_code == 200:
                                    return detail_response.json()
                            except httpx.HTTPError:
                                pass
                        return {}

                    advisories = await asyncio.gather(*(load_advisory(item) for item in matches))

                    for (vuln, pkg_name, pkg_version, pkg_eco), advisory in zip(matches, advisories):
                        vuln_id = vuln.get("id", "UNKNOWN")
                        dedupe_key = (pkg_name, pkg_version, vuln_id)
                        if dedupe_key in seen:
                            continue
                        seen.add(dedupe_key)

                        detail = advisory or vuln
                        fixed_version = extract_fixed(detail, pkg_name) or extract_fixed(vuln, pkg_name)
                        severity_str = advisory_severity(detail, vuln)
                        is_new = (pkg_name, pkg_version) not in base_pkg_versions

                        db.add(Finding(
                            scan_id=scan.id,
                            osv_id=vuln_id,
                            package_name=pkg_name,
                            package_version=pkg_version,
                            severity=severity_str,
                            details={
                                "summary": detail.get("summary") or vuln.get("summary") or "No summary provided",
                                "ecosystem": pkg_eco,
                                "fixed_version": fixed_version,
                                "is_new": is_new,
                                "aliases": detail.get("aliases") or [],
                            }
                        ))
                        total_findings += 1
                        # Rule 1 looks at vulnerabilities this PR introduces that have a fix.
                        if is_new and fixed_version and severity_str in {"CRITICAL", "HIGH"}:
                            blocking_new += 1

            scan.status = ScanStatus.COMPLETED.value
            scan.finished_at = datetime.now(timezone.utc)
            
            # --- POLICY EVALUATION ENGINE ---
            # The mode and rule toggles come from the settings saved on the Policies page.
            final_state, status_desc = await evaluate_check_run(
                db,
                manifest_name=manifest_name,
                total_findings=total_findings,
                blocking_new=blocking_new,
            )
            
            await db.commit()

            if repo_identifier:
                await push_commit_status(scan_id, repo_identifier, scan.commit_hash, final_state, status_desc, f"http://127.0.0.1:8000/api/v1/scans/{scan.id}")

            try:
                await notify_scan_result(
                    db,
                    scan.id,
                    repository.name if repository else f"repository-{scan.repository_id}",
                    scan.commit_hash,
                    "completed",
                    status_desc,
                    blocking_new,
                )
            except Exception as notify_error:
                print(f"[Scan {scan_id}] notification failed: {notify_error}")

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
                await push_commit_status(scan_id, repo_identifier, commit_hash, "error", f"AdvisoryTrail scan failed: {str(e)[:50]}", f"http://127.0.0.1:8000/api/v1/scans/{scan_id}")

            try:
                await notify_scan_result(
                    db,
                    scan_id,
                    repository.name if repository else f"repository-{scan.repository_id}",
                    commit_hash,
                    "failed",
                    f"The scan did not complete: {type(e).__name__}",
                )
            except Exception as notify_error:
                print(f"[Scan {scan_id}] failure notification failed: {notify_error}")
