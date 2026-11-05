from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import Optional, List

from app.database import get_db
from app.models import Scan, ScanStatus, Finding, Repository
from app.schemas import ScanCreate, ScanResponse, FindingResponse
from app.services.scanner import run_osv_scan

router = APIRouter(prefix="/api/v1/scans", tags=["Scans"])

@router.get("/", response_model=List[ScanResponse])
async def list_scans(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve a paginated list of all vulnerability scans."""
    result = await db.execute(
        select(Scan)
        .options(selectinload(Scan.findings), selectinload(Scan.repository))
        .offset(skip)
        .limit(limit)
    )
    scans = result.scalars().all()
    return scans

@router.post("/", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
async def trigger_manual_scan(
    payload: ScanCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Manually trigger an OSV vulnerability scan for a repository and commit hash."""
    repo_result = await db.execute(select(Repository).where(Repository.id == payload.repository_id))
    repo = repo_result.scalars().first()
    
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with id {payload.repository_id} not found"
        )

    new_scan = Scan(
        repository_id=payload.repository_id,
        commit_hash=payload.commit_hash,
        status=ScanStatus.PENDING.value
    )
    db.add(new_scan)
    await db.commit()
    await db.refresh(new_scan)

    # Dispatch background worker
    background_tasks.add_task(run_osv_scan, new_scan.id)

    # Reload scan with relationships for response
    result = await db.execute(
        select(Scan)
        .options(selectinload(Scan.findings), selectinload(Scan.repository))
        .where(Scan.id == new_scan.id)
    )
    return result.scalars().first()

@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan_detail(
    scan_id: int,
    severity: Optional[str] = Query(None, description="Filter findings by severity (e.g. HIGH, MODERATE, CRITICAL)"),
    limit: int = Query(50, ge=1, le=200, description="Number of findings to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination of findings"),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve detailed scan results with optional severity filtering and pagination."""
    scan_result = await db.execute(
        select(Scan)
        .options(selectinload(Scan.repository), selectinload(Scan.findings))
        .where(Scan.id == scan_id)
    )
    scan = scan_result.scalars().first()
    
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan with id {scan_id} not found"
        )

    # Filter and paginate findings in-memory
    filtered_findings = scan.findings
    if severity:
        filtered_findings = [f for f in filtered_findings if f.severity and f.severity.upper() == severity.upper()]
    
    scan.findings = filtered_findings[offset : offset + limit]
    return scan

@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(
    scan_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific vulnerability scan and its associated findings."""
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalars().first()
    
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan with id {scan_id} not found"
        )
        
    await db.delete(scan)
    await db.commit()
    return None
