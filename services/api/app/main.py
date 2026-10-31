from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.database import get_db, engine, Base
import app.models

# HOW IT WORKS: We import the two router files we created in the routers folder.
from app.routers import repositories, scans

@asynccontextmanager
async def lifespan(app: FastAPI):
    # This automatically creates our SQL tables when the server starts
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title="BuildShield API",
    description="GitHub-integrated security and reliability platform",
    version="1.0.0",
    lifespan=lifespan
)

# WHAT THIS DOES: This physically attaches the routes to the FastAPI app.
# If we skip this, FastAPI will ignore the files we just made.
app.include_router(repositories.router)
app.include_router(scans.router)

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")
