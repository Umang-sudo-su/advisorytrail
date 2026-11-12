from app.routers import scans, stats  # <-- Add stats here
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware
from app.routers import repositories, scans, webhooks, auth
from app.routers import findings
from app.routers import policies
from app.routers import audit_logs
from app.routers import events
from app.routers import settings as settings_router
from app.database import get_db, engine, Base
from app.migrations import ensure_schema
from app.services.scheduler import scheduler_loop
import app.models
import asyncio
from contextlib import suppress
from app.routers import repositories, scans, webhooks

# Surface scheduler and notification activity in container logs.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

# No API request needs a larger body; refusing them early keeps memory bounded.
MAX_BODY_BYTES = 2 * 1024 * 1024

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await ensure_schema(conn)

    # Background scheduler: automatic scans and due notification delivery.
    scheduler_task = asyncio.create_task(scheduler_loop())
    try:
        yield
    finally:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task

app = FastAPI(
    title="BuildShield API",
    description="GitHub-integrated security and reliability platform",
    version="1.0.0",
    lifespan=lifespan
)
# Large JSON lists (findings, scans) compress ~10x on the wire.
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # React / Vite dev server
        "http://127.0.0.1:5173",
        "http://localhost:3000",   # Docker dashboard (nginx)
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def harden_responses(request: Request, call_next):
    """Security headers, no-store for API data and a request body size cap."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Request body is too large."})

    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

    # Signed-in responses carry account and repository data; browsers and proxies
    # must never cache them.
    if request.url.path.startswith("/api/v1"):
        response.headers.setdefault("Cache-Control", "no-store")

    return response


app.include_router(repositories.router)
app.include_router(scans.router)
app.include_router(webhooks.router) # Newly added webhook router
app.include_router(auth.router)     # Add this line right here
app.include_router(stats.router)
app.include_router(findings.router)
app.include_router(policies.router)
app.include_router(audit_logs.router)  # Add this line to include the audit logs router
app.include_router(events.router)      # Live dashboard updates (SSE)
app.include_router(settings_router.router)  # Settings page (workspace, account, team, tokens, webhooks)

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception:
        # The exception text can contain the DSN or credentials, so it stays in the log.
        logger.exception("Health check could not reach the database")
        raise HTTPException(status_code=503, detail="Database connection failed")
