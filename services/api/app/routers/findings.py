from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from app.database import get_db
from app.models import Finding

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
    await db.commit()
    await db.refresh(finding)

    return {"message": "Finding status updated", "id": finding.id, "status": finding.status}
