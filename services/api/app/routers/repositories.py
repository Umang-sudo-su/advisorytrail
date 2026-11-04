from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from datetime import datetime, timezone

from app.database import get_db
from app.auth import get_current_user
from app.models import Repository, User
from app.schemas import RepositoryCreate, RepositoryResponse

router = APIRouter(prefix="/api/v1/repositories", tags=["Repositories"])

@router.get("/", response_model=List[RepositoryResponse])
async def get_repositories(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = select(Repository)
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def create_repository(repo: RepositoryCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_repo = Repository(
        name=repo.name, 
        url=repo.url,
        created_at=datetime.now(timezone.utc)
    )
    db.add(new_repo)
    await db.commit()
    await db.refresh(new_repo)
    return new_repo

@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(repo_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = select(Repository).where(Repository.id == repo_id)
    result = await db.execute(query)
    repo = result.scalars().first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    await db.delete(repo)
    await db.commit()