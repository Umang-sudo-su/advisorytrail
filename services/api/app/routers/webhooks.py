from fastapi import APIRouter, Request, Depends, Header, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import logging

from app.database import get_db
from app.models import Repository, Scan, ScanStatus

# Import our new background worker
from app.tasks import process_scan_background

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

# HOW IT WORKS: We add 'background_tasks: BackgroundTasks' to the function parameters.
# FastAPI magically provides this object so we can attach background jobs to the request.
@router.post("/github")
async def github_webhook(
    request: Request, 
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    if x_github_event != "pull_request":
        return {"status": "ignored"}

    payload = await request.json()
    action = payload.get("action")
    
    if action not in ["opened", "synchronize"]:
        return {"status": "ignored"}

    repo_data = payload.get("repository", {})
    pr_data = payload.get("pull_request", {})
    head_commit = pr_data.get("head", {}).get("sha", "unknown_hash")
    
    repo_query = await db.execute(select(Repository).filter_by(github_id=str(repo_data.get("id"))))
    repo = repo_query.scalars().first()

    if not repo:
        repo = Repository(
            github_id=str(repo_data.get("id")),
            name=repo_data.get("full_name"),
            url=repo_data.get("html_url")
        )
        db.add(repo)
        await db.flush()

    new_scan = Scan(repository_id=repo.id, commit_hash=head_commit, status=ScanStatus.PENDING)
    db.add(new_scan)
    await db.commit()

    # THE MAGIC HAPPENS HERE:
    # Instead of running the scanner, we hand the job to our background task.
    # FastAPI will immediately run the 'return' statement below to satisfy GitHub,
    # and THEN start executing process_scan_background silently behind the scenes.
    background_tasks.add_task(process_scan_background, scan_id=new_scan.id, clone_url=repo.url)

    return {"status": "success", "scan_queued_for_commit": head_commit}
