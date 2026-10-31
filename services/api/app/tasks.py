import logging
import asyncio
import tempfile
import os
from app.database import SessionLocal
from app.models import Scan, ScanStatus, Finding, Repository
from app.scanners.osv import run_osv_scanner
from app.github import update_github_check

logger = logging.getLogger(__name__)

async def process_scan_background(scan_id: int, clone_url: str):
    async with SessionLocal() as db:
        scan = await db.get(Scan, scan_id)
        if not scan:
            return

        # Fetch the repository details so we know where to send the API request
        repo = await db.get(Repository, scan.repository_id)

        scan.status = ScanStatus.RUNNING
        await db.commit()
        
        # 1. NOTIFY GITHUB: SCAN STARTED
        await update_github_check(repo.name, scan.commit_hash, "in_progress")
        logger.info(f"Scan {scan_id} marked as RUNNING. GitHub Check updated.")

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = os.path.join(tmpdir, "repo")
            
            clone_process = await asyncio.create_subprocess_exec(
                "git", "clone", clone_url, repo_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await clone_process.communicate()
            
            if clone_process.returncode == 0:
                checkout_process = await asyncio.create_subprocess_exec(
                    "git", "checkout", scan.commit_hash,
                    cwd=repo_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await checkout_process.communicate()

                scan_results = await run_osv_scanner(repo_dir)
                
                # Track how many vulnerabilities we find
                vuln_count = 0

                for result in scan_results.get("results", []):
                    for pkg in result.get("packages", []):
                        for vuln in pkg.get("vulnerabilities", []):
                            vuln_count += 1
                            new_finding = Finding(
                                scan_id=scan.id,
                                osv_id=vuln.get("id", "UNKNOWN"),
                                package_name=pkg.get("package", {}).get("name", "unknown"),
                                package_version=pkg.get("package", {}).get("version", "unknown"),
                                severity="High",
                                details={"summary": vuln.get("summary", "No summary provided")}
                            )
                            db.add(new_finding)

        scan.status = ScanStatus.COMPLETED
        await db.commit()
        
        # 2. NOTIFY GITHUB: SCAN FINISHED
        # If we found 1 or more vulnerabilities, the PR fails. Otherwise, it passes.
        conclusion = "failure" if vuln_count > 0 else "success"
        summary = f"BuildShield detected {vuln_count} high-severity vulnerabilities."
        
        await update_github_check(repo.name, scan.commit_hash, "completed", conclusion, summary)
        logger.info(f"Scan {scan_id} COMPLETED. GitHub Check set to {conclusion}.")
