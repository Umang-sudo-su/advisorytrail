from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List
from datetime import datetime, timezone

from app.database import get_db
from app.auth import get_current_user
from app.models import Scan, User
from app.schemas import ScanResponse, ScanCreate

router = APIRouter(prefix="/api/v1/scans", tags=["Scans"])

@router.get("/", response_model=List[ScanResponse])
async def get_all_scans(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = select(Scan).options(selectinload(Scan.findings))
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
async def trigger_scan(scan: ScanCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_scan = Scan(
        repository_id=scan.repository_id, 
        commit_hash=scan.commit_hash, 
        status="PENDING",
        created_at=datetime.now(timezone.utc)
    )
    db.add(new_scan)
    await db.commit()
    await db.refresh(new_scan)
    
    # Return a dict to prevent SQLAlchemy from lazy-loading relationships synchronously
    return {
        "id": new_scan.id,
        "repository_id": new_scan.repository_id,
        "commit_hash": new_scan.commit_hash,
        "status": new_scan.status,
        "created_at": new_scan.created_at,
        "findings": []
    }

@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = select(Scan).where(Scan.id == scan_id).options(selectinload(Scan.findings))
    result = await db.execute(query)
    scan = result.scalars().first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan

@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(scan_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = select(Scan).where(Scan.id == scan_id)
    result = await db.execute(query)
    scan = result.scalars().first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    await db.delete(scan)
    await db.commit()