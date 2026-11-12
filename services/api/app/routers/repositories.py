from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth import get_current_user
from app.database import get_db
from app.models import Repository, User
from app.schemas import RepositoryCreate, RepositoryResponse
from app.services import github_repos
from app.services.github_auth import load_connection
from app.services.preferences import add_audit
from app.services.rate_limit import enforce

router = APIRouter(prefix="/api/v1/repositories", tags=["Repositories"])


def _payload(repo: Repository) -> Dict:
    return {
        "id": repo.id,
        "name": repo.name,
        "url": repo.url,
        "branch": repo.branch or "main",
        "private": bool(repo.is_private),
        "created_at": repo.created_at,
    }


@router.get("/", response_model=List[RepositoryResponse])
async def get_repositories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Repository).order_by(Repository.created_at.desc(), Repository.id.desc()))
    return [_payload(repo) for repo in result.scalars().all()]


@router.post("/", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def create_repository(
    repo: RepositoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Connects a repository only after GitHub confirms it and grants access.

    Every rejection carries a specific message so the dashboard can explain which
    stage failed: bad input, missing account, unknown repository, missing access,
    unknown branch or duplicate connection.
    """
    # A connection attempt costs a GitHub API call, so cap attempts per account.
    enforce(f"repo-connect:{current_user.id}", limit=10, window_seconds=300)

    try:
        full_name = github_repos.normalize_repository(repo.url or repo.name or "")
    except github_repos.RepositoryValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)

    existing = await db.execute(
        select(Repository).where(func.lower(Repository.name) == full_name.lower())
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{full_name} is already connected to AdvisoryTrail.",
        )

    connection = await load_connection(db)
    if not connection.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Connect a GitHub account first: Settings -> GitHub Integration, or add "
                "GITHUB_TOKEN to the server configuration. The account is what proves you "
                "can access private repositories."
            ),
        )

    try:
        info = await github_repos.lookup(full_name, connection.token, connection.account)

        branch = (repo.branch or "").strip() or info.default_branch
        if branch != info.default_branch:
            if not await github_repos.branch_exists(info.full_name, branch, connection.token):
                raise github_repos.RepositoryValidationError(
                    f"Branch '{branch}' does not exist in {info.full_name}. "
                    f"Use '{info.default_branch}' or another existing branch.",
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
    except github_repos.RepositoryValidationError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message)

    new_repo = Repository(
        name=info.full_name,
        url=info.html_url,
        branch=branch,
        is_private=info.private,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_repo)

    add_audit(
        db,
        actor=current_user.email or current_user.username,
        action="REPOSITORY_CONNECTED",
        resource_id=info.full_name,
        justification=(
            f"{'private' if info.private else 'public'} repository verified through GitHub; "
            f"branch {branch}; account {connection.account or connection.source}"
        ),
        category="Repository Access",
    )

    await db.commit()
    await db.refresh(new_repo)
    return _payload(new_repo)


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(
    repo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Repository).where(Repository.id == repo_id))
    repo = result.scalars().first()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    name = repo.name
    await db.delete(repo)
    add_audit(
        db,
        actor=current_user.email or current_user.username,
        action="REPOSITORY_DISCONNECTED",
        resource_id=name,
        justification="Repository disconnected; its scans and findings were deleted",
        category="Repository Access",
    )
    await db.commit()
    return None
