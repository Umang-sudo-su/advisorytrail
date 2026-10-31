from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List

from app.database import get_db
from app.models import Repository
from app.schemas import RepositoryResponse

router = APIRouter(prefix="/api/v1/repositories", tags=["Repositories"])

@router.get("/", response_model=List[RepositoryResponse])
async def get_repositories(db: AsyncSession = Depends(get_db)):
    # Fetch repositories and eager load their associated scans
    result = await db.execute(
        select(Repository).options(selectinload(Repository.scans))
    )
    return result.scalars().all()
