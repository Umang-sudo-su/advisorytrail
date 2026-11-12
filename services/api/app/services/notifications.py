"""Notification fan-out: in-app records plus real SMTP delivery.

Preferences decide the events and channels; digests and quiet hours are honoured
by queueing a Notification row and letting the scheduler flush it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import Notification, User, WorkspaceMember
from app.services import mailer
from app.services.preferences import get_user_pref_row, user_preferences

logger = logging.getLogger(__name__)

# Events that must never be delayed by quiet hours or a digest.
URGENT_EVENTS = {"account_security", "new_findings_critical", "scan_failed"}


def _in_quiet_hours(prefs: dict, now_utc: datetime) -> bool:
    quiet = prefs.get("quiet_hours") or {}
    if not quiet.get("enabled"):
        return False

    try:
        zone = ZoneInfo(prefs.get("timezone") or "UTC")
    except Exception:
        zone = timezone.utc

    local = now_utc.astimezone(zone)
    start = quiet.get("start") or "22:00"
    end = quiet.get("end") or "07:00"

    try:
        start_h, start_m = (int(part) for part in start.split(":"))
        end_h, end_m = (int(part) for part in end.split(":"))
    except ValueError:
        return False

    minutes = local.hour * 60 + local.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    if start_minutes == end_minutes:
        return False
    if start_minutes < end_minutes:
        return start_minutes <= minutes < end_minutes
    return minutes >= start_minutes or minutes < end_minutes


def _quiet_hours_end(prefs: dict, now_utc: datetime) -> datetime:
    quiet = prefs.get("quiet_hours") or {}
    try:
        zone = ZoneInfo(prefs.get("timezone") or "UTC")
    except Exception:
        zone = timezone.utc

    local = now_utc.astimezone(zone)
    end = quiet.get("end") or "07:00"
    try:
        end_h, end_m = (int(part) for part in end.split(":"))
    except ValueError:
        end_h, end_m = 7, 0

    target = local.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    if target <= local:
        target = target + timedelta(days=1)
    return target.astimezone(timezone.utc)


def _next_digest_time(prefs: dict, now_utc: datetime) -> datetime:
    digest = prefs.get("digest") or "immediate"
    if digest == "weekly":
        days_ahead = (7 - now_utc.weekday()) % 7 or 7
        target = (now_utc + timedelta(days=days_ahead)).replace(hour=9, minute=0, second=0, microsecond=0)
        return target
    # daily (and any unknown value) goes out at 09:00 UTC tomorrow.
    target = (now_utc + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    return target


async def _notify_user(
    db: AsyncSession,
    user: User,
    event: str,
    subject: str,
    body: str,
    urgent: bool,
) -> None:
    prefs_row = await get_user_pref_row(db, user.id)
    prefs = user_preferences(prefs_row)
    notifications_prefs = prefs.get("notifications") or {}
    events = notifications_prefs.get("events") or {}
    channels = notifications_prefs.get("channels") or {}

    if not events.get(event, False):
        return

    now = datetime.now(timezone.utc)
    queued_until: Optional[datetime] = None

    if not urgent:
        if _in_quiet_hours(prefs, now):
            queued_until = _quiet_hours_end(prefs, now)
        elif (notifications_prefs.get("digest") or "immediate") != "immediate":
            queued_until = _next_digest_time(prefs, now)

    if channels.get("in_app", True):
        db.add(
            Notification(
                user_id=user.id,
                event=event,
                subject=subject,
                body=body,
                digest="immediate",
                scheduled_for=None,
                sent_at=now.replace(tzinfo=None),
                status="in_app",
                detail="Shown in AdvisoryTrail",
            )
        )

    if not channels.get("email"):
        await db.commit()
        return

    if queued_until is not None:
        db.add(
            Notification(
                user_id=user.id,
                event=event,
                subject=subject,
                body=body,
                digest=(notifications_prefs.get("digest") or "immediate"),
                scheduled_for=queued_until.replace(tzinfo=None),
                sent_at=None,
                status="queued",
                detail="Held for quiet hours" if _in_quiet_hours(prefs, now) else "Held for digest",
            )
        )
        await db.commit()
        return

    result = await mailer.send_email(user.email, subject, body)
    db.add(
        Notification(
            user_id=user.id,
            event=event,
            subject=subject,
            body=body,
            digest="immediate",
            sent_at=now.replace(tzinfo=None),
            status="sent" if result["delivered"] else "failed",
            detail=result["detail"],
        )
    )
    await db.commit()


async def notify_scan_result(
    db: AsyncSession,
    scan_id: int,
    repository_name: str,
    commit_hash: str,
    outcome: str,
    summary: str,
    critical_new: int = 0,
) -> int:
    """Notifies every workspace member whose preferences cover this scan outcome."""
    members_result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.user_id.is_not(None)))
    members = list(members_result.scalars().all())
    if not members:
        return 0

    user_ids = [member.user_id for member in members]
    users_result = await db.execute(select(User).where(User.id.in_(user_ids), User.is_active.is_(True)))
    users = list(users_result.scalars().all())

    event = "scan_failed" if outcome in {"failed", "timed_out"} else "scan_completed"
    subject = f"AdvisoryTrail: {repository_name} scan {outcome}"
    body = (
        f"Repository: {repository_name}\n"
        f"Commit: {commit_hash}\n"
        f"Outcome: {outcome}\n"
        f"{summary}\n"
    )

    sent = 0
    for user in users:
        try:
            await _notify_user(db, user, event, subject, body, urgent=(event == "scan_failed"))
            sent += 1
        except Exception as error:  # one bad recipient must not fail the scan
            logger.warning("Notification failed for user %s: %s", user.id, error)
    return sent


async def flush_due_notifications(db: AsyncSession, limit: int = 50) -> int:
    """Sends queued digest / quiet-hours notifications that are now due."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await db.execute(
        select(Notification)
        .where(Notification.status == "queued", Notification.scheduled_for <= now)
        .order_by(Notification.scheduled_for)
        .limit(limit)
    )
    queued = list(result.scalars().all())

    sent = 0
    for notification in queued:
        user = await db.get(User, notification.user_id)
        if user is None or not user.is_active:
            notification.status = "skipped"
            notification.detail = "Recipient no longer active"
            continue

        delivery = await mailer.send_email(user.email, notification.subject, notification.body)
        notification.sent_at = datetime.now(timezone.utc).replace(tzinfo=None)
        notification.status = "sent" if delivery["delivered"] else "failed"
        notification.detail = delivery["detail"]
        sent += 1

    if queued:
        await db.commit()
    return sent


async def recent_notifications(db: AsyncSession, user_id: int, limit: int = 10) -> Iterable[Notification]:
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


def notification_payload(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "event": notification.event,
        "subject": notification.subject,
        "status": notification.status,
        "detail": notification.detail,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
        "sent_at": notification.sent_at.isoformat() if notification.sent_at else None,
        "scheduled_for": notification.scheduled_for.isoformat() if notification.scheduled_for else None,
    }
