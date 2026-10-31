import hmac
import hashlib
import os
import logging
from fastapi import APIRouter, Request, Depends, Header, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models import Repository, Scan, ScanStatus
from app.tasks import process_scan_background
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

# Retrieve the secret from the environment variable
GITHUB_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

# Dependency to verify the GitHub signature
async def verify_github_signature(request: Request, x_hub_signature_256: str = Header(None)):
    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Missing signature header")
    
    # We must read the raw body exactly as it was sent by GitHub
    raw_body = await request.body()
    
    # Calculate our own HMAC-SHA256 hash using our secret and the raw body
    hash_object = hmac.new(
        key=GITHUB_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    )
    expected_signature = "sha256=" + hash_object.hexdigest()
    
    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(expected_signature, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid signature")

@router.post("/github", dependencies=[Depends(verify_github_signature)])
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

    background_tasks.add_task(process_scan_background, scan_id=new_scan.id, clone_url=repo.url)

    return {"status": "success", "scan_queued_for_commit": head_commit}
