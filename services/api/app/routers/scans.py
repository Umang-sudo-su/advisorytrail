from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value
from typing import Optional, List

from app.auth import get_current_user
from app.database import get_db
from app.models import Scan, ScanStatus, Finding, Repository, User
from app.schemas import ScanCreate, ScanResponse, FindingResponse
from app.services.scanner import run_scan_with_limits

router = APIRouter(prefix="/api/v1/scans", tags=["Scans"])

@router.get("/", response_model=List[ScanResponse])
async def list_scans(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a paginated list of all vulnerability scans."""
    # Count findings in SQL instead of loading them: a list entry only needs the number,
    # and embedding every finding made each response ~100x larger.
    finding_counts = (
        select(Finding.scan_id, func.count(Finding.id).label("finding_count"))
        .group_by(Finding.scan_id)
        .subquery()
    )
    result = await db.execute(
        select(Scan, func.coalesce(finding_counts.c.finding_count, 0))
        .outerjoin(finding_counts, finding_counts.c.scan_id == Scan.id)
        .order_by(Scan.created_at.asc(), Scan.id.asc())
        .offset(skip)
        .limit(limit)
    )
    scans = []
    for scan, finding_count in result.all():
        # Mark the collection as loaded-but-empty without triggering a lazy load.
        set_committed_value(scan, "findings", [])
        scan.findings_count = int(finding_count)
        scans.append(scan)
    return scans

@router.post("/", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
async def trigger_manual_scan(
    payload: ScanCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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

    # Dispatch background worker (honours the concurrency limit from Settings)
    background_tasks.add_task(run_scan_with_limits, new_scan.id)

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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
    scan.findings_count = len(filtered_findings)
    return scan

@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(
    scan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
