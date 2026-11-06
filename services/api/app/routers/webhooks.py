import hmac
import hashlib
from fastapi import APIRouter, Header, Request, HTTPException, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db
from app.config import settings
from app.models import Repository, Scan, ScanStatus
from app.services.scanner import run_osv_scan

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

async def verify_github_signature(request: Request, x_hub_signature_256: str = Header(None)):
    if not settings.GITHUB_WEBHOOK_SECRET:
        return
    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Missing signature")
    
    body = await request.body()
    mac = hmac.new(settings.GITHUB_WEBHOOK_SECRET.encode(), msg=body, digestmod=hashlib.sha256)
    expected_signature = "sha256=" + mac.hexdigest()
    
    if not hmac.compare_digest(expected_signature, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid signature")

@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(None),
    db: AsyncSession = Depends(get_db)
):
    await verify_github_signature(request, request.headers.get("X-Hub-Signature-256"))
    
    payload = await request.json()
    
    if x_github_event == "ping":
        return {"message": "pong"}

    commit_hash = None
    base_commit_hash = None
    repo_data = payload.get("repository", {})
    repo_name = repo_data.get("full_name") or repo_data.get("name")
    repo_url = repo_data.get("html_url")

    # 1. HANDLE PUSH EVENTS
    if x_github_event == "push":
        commit_hash = payload.get("after")
        if commit_hash == "0000000000000000000000000000000000000000":
            return {"message": "Branch deleted, skipping scan."}

    # 2. HANDLE PULL REQUEST EVENTS
    elif x_github_event == "pull_request":
        action = payload.get("action")
        # We only want to scan when a PR is newly opened or updated with new commits
        if action not in ["opened", "synchronize"]:
            return {"message": f"Ignoring pull_request action: {action}"}
        
        commit_hash = payload.get("pull_request", {}).get("head", {}).get("sha")
        base_commit_hash = payload.get("pull_request", {}).get("base", {}).get("sha")

    else:
        return {"message": f"Event {x_github_event} ignored."}

    if not commit_hash or not repo_name:
        raise HTTPException(status_code=400, detail="Invalid payload: missing commit hash or repository info")

    # Find or register the repository
    result = await db.execute(select(Repository).where(Repository.name == repo_name))
    repo = result.scalars().first()
    if not repo:
        repo = Repository(name=repo_name, url=repo_url)
        db.add(repo)
        await db.commit()
        await db.refresh(repo)

    # Create new scan execution record
    new_scan = Scan(
        repository_id=repo.id,
        commit_hash=commit_hash,
        status=ScanStatus.PENDING.value
    )
    db.add(new_scan)
    await db.commit()
    await db.refresh(new_scan)

    # Dispatch background worker
    background_tasks.add_task(run_osv_scan, new_scan.id)

    return {"message": "Scan triggered successfully", "scan_id": new_scan.id}