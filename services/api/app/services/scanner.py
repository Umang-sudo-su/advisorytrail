import httpx
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models import Scan, ScanStatus, Finding
from app.database import engine

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

async def run_osv_scan(scan_id: int, manifest_content: str = None):
    """Parses requirements and queries OSV.dev batch endpoint for vulnerabilities."""
    async with AsyncSession(engine, expire_on_commit=False) as db:
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalars().first()
        
        if not scan:
            return

        scan.status = ScanStatus.IN_PROGRESS.value
        await db.commit()

        try:
            content_to_parse = manifest_content or DEFAULT_TEST_REQUIREMENTS
            parsed_packages = parse_requirements(content_to_parse)

            if not parsed_packages:
                scan.status = ScanStatus.COMPLETED.value
                await db.commit()
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

            for idx, res in enumerate(results):
                pkg_name, pkg_version = parsed_packages[idx]
                vulns = res.get("vulns", [])
                
                for vuln in vulns:
                    severity_list = vuln.get("database_specific", {}).get("severity") or vuln.get("severity", [])
                    severity_str = "HIGH"
                    if isinstance(severity_list, str):
                        severity_str = severity_list

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

            scan.status = ScanStatus.COMPLETED.value
            await db.commit()

        except Exception as e:
            scan.status = ScanStatus.FAILED.value
            await db.commit()
            print(f"Scan {scan_id} failed: {e}")
