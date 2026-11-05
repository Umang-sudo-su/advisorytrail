import hmac
import hashlib
import os
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timezone

from app.database import get_db
from app.models import Repository, Scan, ScanStatus
from app.services.scanner import run_osv_scan

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "buildshield_secret_key")

def verify_github_signature(payload_bytes: bytes, signature_header: str):
    """Verifies the incoming payload against GitHub's X-Hub-Signature-256 header."""
    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header"
        )
    
    if not signature_header.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature format. Expected 'sha256=...'"
        )

    mac = hmac.new(GITHUB_WEBHOOK_SECRET.encode("utf-8"), msg=payload_bytes, digestmod=hashlib.sha256)
    expected_signature = f"sha256={mac.hexdigest()}"

    if not hmac.compare_digest(expected_signature, signature_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub webhook signature"
        )

@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(..., alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(None, alias="X-Hub-Signature-256"),
    db: AsyncSession = Depends(get_db)
):
    # 1. Read raw request payload bytes for signature calculation
    body_bytes = await request.body()

    # 2. Verify HMAC SHA-256 signature
    verify_github_signature(body_bytes, x_hub_signature_256)

    # 3. Process push event
    if x_github_event != "push":
        return {"message": f"Event '{x_github_event}' ignored"}

    payload = await request.json()
    repo_data = payload.get("repository", {})
    repo_name = repo_data.get("name")
    repo_url = repo_data.get("html_url")
    commit_hash = payload.get("after")

    if not repo_name or not commit_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload: missing repository name or commit hash"
        )

    # 4. Retrieve or register repository
    result = await db.execute(select(Repository).where(Repository.name == repo_name))
    repo = result.scalars().first()

    if not repo:
        repo = Repository(name=repo_name, url=repo_url)
        db.add(repo)
        await db.commit()
        await db.refresh(repo)

    # 5. Create new pending scan
    new_scan = Scan(
        repository_id=repo.id,
        commit_hash=commit_hash,
        status=ScanStatus.PENDING.value,
        created_at=datetime.now(timezone.utc)
    )
    db.add(new_scan)
    await db.commit()
    await db.refresh(new_scan)

    # 6. Trigger background OSV scanner task
    background_tasks.add_task(run_osv_scan, new_scan.id)

    return {
        "id": new_scan.id,
        "repository_id": new_scan.repository_id,
        "commit_hash": new_scan.commit_hash,
        "status": new_scan.status,
        "message": "Scan triggered successfully"
    }
