from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List
from datetime import datetime, timezone

from app.database import get_db
from app.models import Scan, Repository, ScanStatus
from app.schemas import ScanCreate, ScanResponse
from app.routers.auth import get_current_user
from app.services.scanner import run_osv_scan

router = APIRouter(prefix="/api/v1/scans", tags=["Scans"])

@router.post("/", status_code=status.HTTP_201_CREATED)
async def trigger_scan(
    scan_data: ScanCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    result = await db.execute(select(Repository).where(Repository.id == scan_data.repository_id))
    repo = result.scalars().first()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID {scan_data.repository_id} not found"
        )

    new_scan = Scan(
        repository_id=scan_data.repository_id,
        commit_hash=scan_data.commit_hash,
        status=ScanStatus.PENDING.value,
        created_at=datetime.now(timezone.utc)
    )
    db.add(new_scan)
    await db.commit()
    await db.refresh(new_scan)

    background_tasks.add_task(run_osv_scan, new_scan.id)

    return {
        "id": new_scan.id,
        "repository_id": new_scan.repository_id,
        "commit_hash": new_scan.commit_hash,
        "status": new_scan.status,
        "created_at": new_scan.created_at,
        "findings": []
    }

@router.get("/", response_model=List[ScanResponse])
async def list_scans(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    result = await db.execute(select(Scan).options(selectinload(Scan.findings)))
    scans = result.scalars().all()
    return scans

@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(
    scan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    result = await db.execute(
        select(Scan)
        .options(selectinload(Scan.findings))
        .where(Scan.id == scan_id)
    )
    scan = result.scalars().first()
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan with ID {scan_id} not found"
        )
    return scan
