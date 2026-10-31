from fastapi import APIRouter, Request, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import logging

from app.database import get_db
from app.models import Repository, Scan, ScanStatus

# We set up a basic logger so we can see when GitHub pings us in the terminal
logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

# WHAT THIS DOES: We use @router.post because GitHub sends data via POST requests.
# We also use 'Header' to automatically grab the 'x-github-event' header GitHub sends.
@router.post("/github")
async def github_webhook(
    request: Request, 
    x_github_event: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Receives incoming webhook events from GitHub.
    """
    # 1. Verify this is actually an event we care about
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"Event '{x_github_event}' not tracked"}

    # 2. Extract the JSON payload GitHub sent us
    payload = await request.json()
    action = payload.get("action")
    
    # We only want to run scans when a PR is newly opened or updated (synchronized)
    if action not in ["opened", "synchronize"]:
        return {"status": "ignored", "reason": f"PR action '{action}' does not require a scan"}

    # 3. Parse out the specific data we need from the massive GitHub JSON
    repo_data = payload.get("repository", {})
    pr_data = payload.get("pull_request", {})
    head_commit = pr_data.get("head", {}).get("sha", "unknown_hash")
    
    logger.info(f"Received PR {action} event for {repo_data.get('full_name')} at commit {head_commit}")

    # 4. DATABASE LOGIC: Check if we already have this repository in our database
    repo_query = await db.execute(
        select(Repository).filter_by(github_id=str(repo_data.get("id")))
    )
    repo = repo_query.scalars().first()

    # If the repo doesn't exist, create it dynamically
    if not repo:
        repo = Repository(
            github_id=str(repo_data.get("id")),
            name=repo_data.get("full_name"),
            url=repo_data.get("html_url")
        )
        db.add(repo)
        await db.flush() # Flush to generate the repo.id

    # 5. Create a new "PENDING" scan in the database for this specific commit
    new_scan = Scan(
        repository_id=repo.id,
        commit_hash=head_commit,
        status=ScanStatus.PENDING
    )
    db.add(new_scan)
    
    # 6. Commit the changes to permanently save the Repo and Scan
    await db.commit()

    # Tell GitHub we successfully received and processed the webhook
    return {"status": "success", "scan_queued_for_commit": head_commit}
