from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from app.database import get_db
from app.models import Policy

router = APIRouter(prefix="/api/v1/policies", tags=["Policies"])

class PolicyCreate(BaseModel):
    repository_id: int
    rule_type: str

@router.post("/")
async def create_policy(payload: PolicyCreate, db: AsyncSession = Depends(get_db)):
    new_policy = Policy(repository_id=payload.repository_id, rule_type=payload.rule_type)
    db.add(new_policy)
    await db.commit()
    await db.refresh(new_policy)
    return new_policy

@router.get("/{repository_id}")
async def get_policies(repository_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Policy).where(Policy.repository_id == repository_id))
    return result.scalars().all()
