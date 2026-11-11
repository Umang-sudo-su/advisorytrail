"""Server-side session records backing revocable JWTs."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session, User


def new_jti() -> str:
    return secrets.token_urlsafe(24)


def _naive_utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def start_session(
    db: AsyncSession,
    user: User,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Session:
    session = Session(
        user_id=user.id,
        jti=new_jti(),
        user_agent=(user_agent or "")[:400] or None,
        ip_address=ip_address,
        created_at=_naive_utcnow(),
        last_seen_at=_naive_utcnow(),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


def session_payload(session: Session, current_jti: str | None = None) -> dict:
    return {
        "id": session.id,
        "jti": session.jti,
        "user_agent": session.user_agent,
        "ip_address": session.ip_address,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "last_seen_at": session.last_seen_at.isoformat() if session.last_seen_at else None,
        "revoked_at": session.revoked_at.isoformat() if session.revoked_at else None,
        "current": session.jti == current_jti,
    }
