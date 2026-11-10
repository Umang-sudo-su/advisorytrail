import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.auth import get_current_user
from app.database import SessionLocal
from app.models import AuditLog, Finding, Scan

router = APIRouter(prefix="/api/v1/events", tags=["Events"])

POLL_SECONDS = 1.0
PING_SECONDS = 15.0


async def current_state() -> str:
    """Cheap digest of everything the dashboard renders.

    Only changes in this string are pushed to clients, so a quiet system
    produces heartbeats instead of constant payloads.
    """
    async with SessionLocal() as db:
        scan_rows = (
            await db.execute(select(Scan.status, func.count(Scan.id)).group_by(Scan.status))
        ).all()
        findings = (await db.execute(select(func.count(Finding.id)))).scalar() or 0
        audit = (await db.execute(select(func.count(AuditLog.id)))).scalar() or 0

    return json.dumps(
        {
            "scans": {str(status): count for status, count in scan_rows},
            "findings": findings,
            "audit": audit,
        },
        sort_keys=True,
    )


@router.get("")
async def stream_events(_user=Depends(get_current_user)):
    """Server-sent events describing scan/finding/audit state changes."""

    async def event_stream():
        last = None
        idle_since = 0.0

        yield ": connected\n\n"

        try:
            while True:
                try:
                    state = await current_state()
                except Exception:
                    state = None

                if state is not None and state != last:
                    last = state
                    idle_since = 0.0
                    yield f"event: state\ndata: {state}\n\n"
                else:
                    idle_since += POLL_SECONDS
                    if idle_since >= PING_SECONDS:
                        idle_since = 0.0
                        yield ": ping\n\n"

                await asyncio.sleep(POLL_SECONDS)
        except asyncio.CancelledError:
            raise

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
