from fastapi import APIRouter, Depends, HTTPException, Header, Request, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timezone
from app.database import get_db
from app.models import Repository, Scan, ScanStatus
from app.services.scanner import run_osv_scan

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    if x_github_event != "push":
        return {"message": f"Ignored event: {x_github_event}"}

    payload = await request.json()
    repo_url = payload.get("repository", {}).get("html_url")
    commit_hash = payload.get("after")

    if not repo_url or not commit_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid GitHub webhook payload"
        )

    result = await db.execute(select(Repository).where(Repository.url == repo_url))
    repo = result.scalars().first()

    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repo_url}' not configured in BuildShield"
        )

    new_scan = Scan(
        repository_id=repo.id,
        commit_hash=commit_hash,
        status=ScanStatus.PENDING.value,
        created_at=datetime.now(timezone.utc)
    )
    db.add(new_scan)
    await db.commit()
    await db.refresh(new_scan)

    # Launch the OSV scan in the background!
    background_tasks.add_task(run_osv_scan, new_scan.id)

    return {
        "id": new_scan.id,
        "repository_id": new_scan.repository_id,
        "commit_hash": new_scan.commit_hash,
        "status": new_scan.status,
        "message": "Scan triggered successfully"
    }
