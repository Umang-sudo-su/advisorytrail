import subprocess
import tempfile
import json
import logging
import asyncio
from sqlalchemy.future import select
from app.database import AsyncSessionLocal
from app.models import Scan, Finding, Repository, ScanStatus

logger = logging.getLogger(__name__)

async def run_osv_scan(scan_id: int):
    """Background task wrapper that manages the DB session and executes the real OSV scanner."""
    async with AsyncSessionLocal() as db:
        try:
            # 1. Fetch scan and repository from database
            scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
            scan = scan_result.scalars().first()
            if not scan:
                logger.error(f"Scan {scan_id} not found for background execution.")
                return

            repo_result = await db.execute(select(Repository).where(Repository.id == scan.repository_id))
            repo = repo_result.scalars().first()
            if not repo:
                logger.error(f"Repository for scan {scan_id} not found.")
                scan.status = ScanStatus.FAILED.value
                await db.commit()
                return

            # Mark scan as running
            scan.status = "IN_PROGRESS"
            await db.commit()

            # 2. Run the blocking OSV scanner in a separate thread to keep FastAPI fast and responsive
            findings_data = await asyncio.to_thread(run_real_osv_scan, repo.url)

            # 3. Save real findings to the database
            for finding in findings_data:
                db_finding = Finding(
                    scan_id=scan.id,
                    osv_id=finding["osv_id"],
                    package_name=finding["package_name"],
                    package_version=finding["package_version"],
                    severity=finding["severity"],
                    details=finding["details"],
                    status=finding["status"]
                )
                db.add(db_finding)

            scan.status = ScanStatus.COMPLETED.value
            await db.commit()
            logger.info(f"Scan {scan_id} completed successfully with {len(findings_data)} findings.")

        except Exception as e:
            logger.error(f"Scan {scan_id} failed with error: {e}")
            if 'scan' in locals() and scan:
                scan.status = ScanStatus.FAILED.value
                await db.commit()

def run_real_osv_scan(repo_url: str):
    """Clones a repo, runs osv-scanner, and returns structured finding dictionaries."""
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # 1. Shallow clone for maximum speed
            subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, temp_dir],
                check=True,
                capture_output=True,
                text=True
            )
            
            # 2. Run OSV-Scanner and output JSON
            process = subprocess.run(
                ["osv-scanner", "-r", "--json", temp_dir],
                capture_output=True,
                text=True
            )
            
            if not process.stdout.strip():
                return [] 
                
            osv_results = json.loads(process.stdout)
            return parse_osv_json(osv_results)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Clone failed: {e.stderr}")
            raise Exception("Repository cloning failed. Check URL or permissions.")
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parse failed: {process.stderr}")
            raise Exception("Scanner output was not valid JSON.")

def parse_osv_json(osv_results: dict):
    findings = []
    for result in osv_results.get("results", []):
        for package_group in result.get("packages", []):
            pkg_info = package_group.get("package", {})
            for vuln in package_group.get("vulnerabilities", []):
                db_specific = vuln.get("database_specific", {})
                severity = db_specific.get("severity", "MEDIUM")
                
                findings.append({
                    "osv_id": vuln.get("id"),
                    "package_name": pkg_info.get("name"),
                    "package_version": pkg_info.get("version"),
                    "severity": severity.upper(),
                    "details": vuln,
                    "status": "OPEN"
                })
    return findings