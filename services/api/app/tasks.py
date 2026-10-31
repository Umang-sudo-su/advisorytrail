import logging
from app.database import SessionLocal
from app.models import Scan, ScanStatus, Finding
from app.scanners.osv import run_osv_scanner

logger = logging.getLogger(__name__)

# WHAT THIS IS: A standalone function that takes the ID of the scan we just created.
async def process_scan_background(scan_id: int, clone_url: str):
    
    # WHY WE OPEN A NEW SESSION: 
    # In FastAPI, the database connection attached to the web router closes the EXACT second 
    # we reply to GitHub. Since this background task runs AFTER we reply, if we try to use 
    # the old session, the app will crash with a "Session Closed" error. 
    # Opening 'SessionLocal()' here gives this background worker its own dedicated DB connection.
    async with SessionLocal() as db:
        
        # 1. Fetch the PENDING scan we just saved to the database
        scan = await db.get(Scan, scan_id)
        if not scan:
            return

        # 2. Update the UI state to "RUNNING"
        scan.status = ScanStatus.RUNNING
        await db.commit()
        logger.info(f"Scan {scan_id} marked as RUNNING.")

        # 3. RUN THE SCANNER
        # In a full production app, you would run 'git clone clone_url' here.
        # For this tutorial, we will point the scanner at our current backend directory (".").
        target_dir = "."
        scan_results = await run_osv_scanner(target_dir)

        # 4. PARSE THE FINDINGS
        # We loop through the JSON dictionary returned by our OSV-Scanner adapter
        # and translate the vulnerabilities into our database 'Finding' models.
        for result in scan_results.get("results", []):
            for pkg in result.get("packages", []):
                for vuln in pkg.get("vulnerabilities", []):
                    new_finding = Finding(
                        scan_id=scan.id,
                        osv_id=vuln.get("id", "UNKNOWN"),
                        package_name=pkg.get("package", {}).get("name", "unknown"),
                        package_version=pkg.get("package", {}).get("version", "unknown"),
                        severity="High", # We default to High for this example
                        details={"summary": vuln.get("summary", "No summary provided")}
                    )
                    db.add(new_finding) # Add to our database shopping cart

        # 5. COMPLETE THE SCAN
        scan.status = ScanStatus.COMPLETED
        await db.commit() # Checkout / permanently save the status update and the findings
        logger.info(f"Scan {scan_id} COMPLETED. Findings successfully saved.")
