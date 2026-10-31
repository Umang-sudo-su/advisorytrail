import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

raw_db_url = os.getenv(
    "DATABASE_URL", 
    "postgresql://buildshield:buildshield_dev_pass@localhost:5432/buildshield_db"
)
DATABASE_URL = raw_db_url.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        yield session
