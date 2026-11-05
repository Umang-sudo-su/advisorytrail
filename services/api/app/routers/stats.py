from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from app.database import get_db
from app.models import Scan, Finding, ScanStatus

router = APIRouter(prefix="/api/v1/stats", tags=["Stats"])

@router.get("/")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    # Calculate Scan Totals
    active_scans = (await db.execute(select(func.count(Scan.id)).where(Scan.status == ScanStatus.IN_PROGRESS.value))).scalar() or 0
    failed_scans = (await db.execute(select(func.count(Scan.id)).where(Scan.status == ScanStatus.FAILED.value))).scalar() or 0
    success_scans = (await db.execute(select(func.count(Scan.id)).where(Scan.status == ScanStatus.COMPLETED.value))).scalar() or 0
    
    # Calculate Severity Breakdown
    severity_result = await db.execute(
        select(Finding.severity, func.count(Finding.id)).group_by(Finding.severity)
    )
    severity_counts = {row[0].upper(): row[1] for row in severity_result.all() if row[0]}
    
    breakdown = {
        "CRITICAL": severity_counts.get("CRITICAL", 0),
        "HIGH": severity_counts.get("HIGH", 0),
        "MEDIUM": severity_counts.get("MEDIUM", 0) + severity_counts.get("MODERATE", 0),
        "LOW": severity_counts.get("LOW", 0),
    }
    
    return {
        "active_pr_scans": active_scans,
        "failed_incomplete_scans": failed_scans,
        "clean_prs": success_scans,
        "new_pr_vulnerabilities": breakdown["CRITICAL"] + breakdown["HIGH"],
        "severity_breakdown": breakdown
    }
