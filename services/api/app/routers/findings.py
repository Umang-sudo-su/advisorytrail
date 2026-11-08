from typing import List
from fastapi import APIRouter, Depends, HTTPException
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
async def list_findings(db: AsyncSession = Depends(get_db)):
    query = select(Finding)
    result = await db.execute(query)
    findings = result.scalars().all()
    return findings