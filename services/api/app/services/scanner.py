import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models import Scan, ScanStatus, Finding
from app.database import engine

OSV_QUERY_URL = "https://api.osv.dev/v1/query"

async def run_osv_scan(scan_id: int):
    """Runs in the background to query OSV.dev and update scan status and findings."""
    async with AsyncSession(engine, expire_on_commit=False) as db:
        # 1. Fetch scan record
        result = await db.execute(select(Scan).where(Scan.id == scan_id))
        scan = result.scalars().first()
        
        if not scan:
            return

        # 2. Update status to IN_PROGRESS
        scan.status = ScanStatus.IN_PROGRESS.value
        await db.commit()

        try:
            # 3. Query OSV.dev API by commit hash
            async with httpx.AsyncClient() as client:
                response = await client.post(OSV_QUERY_URL, json={"commit": scan.commit_hash})
                response.raise_for_status()
                data = response.json()

            vulns = data.get("vulns", [])
            
            # 4. Save findings to database
            for vuln in vulns:
                affected = vuln.get("affected", [{}])[0]
                package = affected.get("package", {})
                
                new_finding = Finding(
                    scan_id=scan.id,
                    osv_id=vuln.get("id", "UNKNOWN"),
                    package_name=package.get("name", "Unknown"),
                    package_version=scan.commit_hash[:8],
                    severity="HIGH",
                    details={
                        "summary": vuln.get("summary", "No summary provided"),
                        "ecosystem": package.get("ecosystem", "Unknown")
                    }
                )
                db.add(new_finding)

            # 5. Update status to COMPLETED
            scan.status = ScanStatus.COMPLETED.value
            await db.commit()

        except Exception as e:
            # 6. Fallback on failure
            scan.status = ScanStatus.FAILED.value
            await db.commit()
            print(f"Scan {scan_id} failed: {e}")
