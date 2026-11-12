import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

raw_db_url = os.getenv(
    "DATABASE_URL", 
    "postgresql://advisorytrail:advisorytrail_dev_pass@localhost:5432/advisorytrail_db"
)
DATABASE_URL = raw_db_url.replace("postgresql://", "postgresql+asyncpg://")

# SQL echo is a debugging aid only: it writes every statement to the logs, so it stays off
# unless explicitly enabled.
SQL_ECHO = os.getenv("SQL_ECHO", "false").strip().lower() in {"1", "true", "yes", "on"}

engine = create_async_engine(
    DATABASE_URL,
    echo=SQL_ECHO,
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_db():
    async with SessionLocal() as session:
        yield session
