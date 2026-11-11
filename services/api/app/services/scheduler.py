"""Background scheduler: periodic scans plus due notification delivery.

Runs inside the API process on a short tick. Work is only claimed when the
schedule is enabled, and the last run is persisted so restarts do not re-run.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.models import Repository, Scan, ScanStatus
from app.services import notifications as notification_service
from app.services.preferences import get_workspace_row, scan_config
from app.services.scanner import run_scan_with_limits

logger = logging.getLogger(__name__)

TICK_SECONDS = float(os.getenv("SCHEDULER_TICK_SECONDS", "30"))


def _parse_time(value: str) -> time:
    try:
        hour, minute = (int(part) for part in (value or "02:00").split(":"))
        return time(hour=hour, minute=minute)
    except ValueError:
        return time(hour=2, minute=0)


def compute_next_run(scheduled: dict, now: Optional[datetime] = None) -> Optional[datetime]:
    """Next run in UTC for a daily/weekly schedule, or None when disabled."""
    if not scheduled or not scheduled.get("enabled"):
        return None

    now = now or datetime.now(timezone.utc)
    zone = ZoneInfo(scheduled.get("timezone") or "UTC")
    local_now = now.astimezone(zone)
    run_time = _parse_time(scheduled.get("time") or "02:00")

    candidate = local_now.replace(
        hour=run_time.hour, minute=run_time.minute, second=0, microsecond=0
    )
    if candidate <= local_now:
        candidate += timedelta(days=1)

    if scheduled.get("frequency") == "weekly":
        # Weekly scans run on Mondays.
        while candidate.weekday() != 0:
            candidate += timedelta(days=1)

    return candidate.astimezone(timezone.utc)


def _last_run(scheduled: dict) -> Optional[datetime]:
    value = scheduled.get("last_run")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


async def run_scheduled_scans(reason: str = "schedule") -> dict:
    """Queues a scan for each enabled branch of every repository."""
    async with SessionLocal() as db:
        workspace = await get_workspace_row(db)
        config = scan_config(workspace)
        scheduled = config.get("scheduled") or {}
        branches = config.get("branches") or ["main"]

        result = await db.execute(select(Repository).order_by(Repository.id))
        repositories = list(result.scalars().all())

        queued = []
        for repository in repositories:
            for branch in branches:
                scan = Scan(
                    repository_id=repository.id,
                    commit_hash=branch,
                    status=ScanStatus.PENDING.value,
                )
                db.add(scan)
                await db.commit()
                await db.refresh(scan)
                queued.append({"scan_id": scan.id, "repository": repository.name, "branch": branch})
                asyncio.create_task(run_scan_with_limits(scan.id))

        settings = dict(workspace.settings or {})
        scheduled_state = dict(settings.get("scheduled") or {})
        scheduled_state["last_run"] = datetime.now(timezone.utc).isoformat()
        scheduled_state["last_reason"] = reason
        settings["scheduled"] = scheduled_state
        workspace.settings = settings
        await db.commit()

        logger.info("Scheduled scan run (%s): %s scans queued", reason, len(queued))
        return {"queued": queued, "reason": reason}


async def _tick() -> None:
    async with SessionLocal() as db:
        workspace = await get_workspace_row(db)
        config = scan_config(workspace)
        scheduled = config.get("scheduled") or {}

        try:
            await notification_service.flush_due_notifications(db)
        except Exception as error:
            logger.warning("Notification flush failed: %s", error)

    if not scheduled.get("enabled"):
        return

    now = datetime.now(timezone.utc)
    last = _last_run(scheduled)
    next_run = compute_next_run(scheduled, last or now - timedelta(minutes=1))
    if next_run is None or now < next_run:
        return

    try:
        await run_scheduled_scans("schedule")
    except Exception as error:
        logger.exception("Scheduled scan run failed: %s", error)


async def scheduler_loop() -> None:
    logger.info("Scheduler started (tick %.1fs)", TICK_SECONDS)
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            logger.info("Scheduler stopped")
            raise
        except Exception as error:
            logger.exception("Scheduler tick failed: %s", error)
        await asyncio.sleep(TICK_SECONDS)
