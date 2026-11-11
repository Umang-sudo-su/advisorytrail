from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.database import get_db
from app.models import Finding, AuditLog
from app.schemas import FindingResponse

router = APIRouter(prefix="/api/v1/findings", tags=["Findings"])

class FindingUpdate(BaseModel):
    status: str

@router.patch("/{finding_id}")
async def update_finding_status(finding_id: int, payload: FindingUpdate, db: AsyncSession = Depends(get_db)):
    valid_statuses = ["OPEN", "DISMISSED", "FALSE_POSITIVE"]
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {valid_statuses}")

    result = await db.execute(select(Finding).where(Finding.id == finding_id))
    finding = result.scalars().first()

    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    finding.status = payload.status
    
    # --- AUDIT LOG ENTRY ---
    db.add(AuditLog(
        actor="umang@buildshield.dev",
        action="FINDING_DISMISSED" if payload.status in ["DISMISSED", "FALSE_POSITIVE"] else "FINDING_STATUS_UPDATED",
        resource_id=f"vuln-{finding.osv_id}",
        justification=f"Status changed to {payload.status}",
        category="Finding Reviews & Dismissals"
    ))

    await db.commit()
    await db.refresh(finding)

    return {"message": "Finding status updated", "id": finding.id, "status": finding.status}

@router.get("/", response_model=List[FindingResponse])
async def list_findings(
    scan_id: Optional[int] = Query(None, description="Only findings from this scan"),
    severity: Optional[str] = Query(None, description="Filter by severity (e.g. HIGH, MODERATE)"),
    finding_status: Optional[str] = Query(None, alias="status", description="Filter by review status"),
    limit: Optional[int] = Query(None, ge=1, le=5000, description="Optional cap for large result sets"),
    offset: int = Query(0, ge=0, description="Rows to skip when paging"),
    db: AsyncSession = Depends(get_db)
):
    query = select(Finding).order_by(Finding.id)

    if scan_id is not None:
        query = query.where(Finding.scan_id == scan_id)
    if severity:
        query = query.where(Finding.severity == severity.upper())
    if finding_status:
        query = query.where(Finding.status == finding_status.upper())
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    result = await db.execute(query)
    return result.scalars().all()