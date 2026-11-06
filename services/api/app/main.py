from app.routers import scans, stats  # <-- Add stats here
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from app.routers import repositories, scans, webhooks, auth
from app.routers import findings
from app.routers import policies
from app.database import get_db, engine, Base
import app.models
from app.routers import repositories, scans, webhooks

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title="BuildShield API",
    description="GitHub-integrated security and reliability platform",
    version="1.0.0",
    lifespan=lifespan
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # React / Vite frontend
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repositories.router)
app.include_router(scans.router)
app.include_router(webhooks.router) # Newly added webhook router
app.include_router(auth.router)     # Add this line right here
app.include_router(stats.router)
app.include_router(findings.router)
app.include_router(policies.router)

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")
