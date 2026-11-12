from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth import (
    create_access_token,
    create_challenge_token,
    decode_token,
    get_current_user,
    get_password_hash,
    oauth2_scheme,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models import Session, User
from app.schemas import UserCreate, UserResponse
from app.services import sessions as session_service
from app.services import totp
from app.services.preferences import add_audit
from app.services.rate_limit import enforce
from app.services.secret_box import open_sealed, seal

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TwoFactorVerify(BaseModel):
    challenge_token: str
    code: str = Field(min_length=6, max_length=20)


class TwoFactorEnable(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class TwoFactorDisable(BaseModel):
    password: str = Field(min_length=1, max_length=128)


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def _recovery_codes_remaining(user: User) -> int:
    return len(user.two_factor_recovery or [])


async def _session_token(db: AsyncSession, user: User, request: Request) -> str:
    session = await session_service.start_session(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=_client_ip(request),
    )
    return create_access_token(
        data={"sub": user.username},
        jti=session.jti,
        version=int(user.token_version or 0),
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    enforce(f"register:{_client_ip(request) or 'unknown'}", limit=5, window_seconds=3600)
    username_query = await db.execute(select(User.id).where(User.username == user.username))
    if username_query.scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username is already registered")

    email_query = await db.execute(select(User.id).where(User.email == user.email))
    if email_query.scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email is already registered")

    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=get_password_hash(user.password),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.post("/login")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    # The form field is called "username" but accepts either a username or an email.
    identifier = form_data.username.strip()
    # Slows down password guessing without locking a legitimate user out for long.
    enforce(
        f"login:{_client_ip(request) or 'unknown'}:{identifier.lower()}",
        limit=10,
        window_seconds=300,
        detail="Too many sign-in attempts. Wait a few minutes and try again.",
    )
    query = select(User).where(or_(User.username == identifier, User.email == identifier))
    result = await db.execute(query)
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username/email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is inactive")

    if user.two_factor_enabled:
        return {
            "requires_2fa": True,
            "challenge_token": create_challenge_token(user.username),
            "expires_in": 300,
        }

    access_token = await _session_token(db, user, request)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/2fa/verify")
async def verify_two_factor(
    payload: TwoFactorVerify,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        claims = decode_token(payload.challenge_token)
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="The sign-in challenge expired.")

    if claims.get("purpose") != "2fa":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This is not a 2FA challenge.")

    enforce(
        f"2fa:{_client_ip(request) or 'unknown'}:{claims.get('sub')}",
        limit=10,
        window_seconds=300,
        detail="Too many verification attempts. Wait a few minutes and try again.",
    )

    result = await db.execute(select(User).where(User.username == claims.get("sub")))
    user = result.scalars().first()
    if user is None or not user.two_factor_enabled or not user.two_factor_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Two-factor authentication is not enabled.")

    secret = open_sealed(user.two_factor_secret)
    if not secret:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stored 2FA secret is unreadable.")

    code = payload.code.strip()
    if totp.verify_code(secret, code):
        pass
    else:
        # Recovery codes are single use.
        hashed = totp.hash_recovery_code(code)
        remaining = [item for item in (user.two_factor_recovery or []) if item != hashed]
        if len(remaining) == len(user.two_factor_recovery or []):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="That code is not valid.")
        user.two_factor_recovery = remaining
        await db.commit()

    access_token = await _session_token(db, user, request)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/2fa/status")
async def two_factor_status(current_user: User = Depends(get_current_user)):
    return {
        "enabled": bool(current_user.two_factor_enabled),
        "recovery_codes_remaining": _recovery_codes_remaining(current_user),
    }


@router.post("/2fa/setup")
async def setup_two_factor(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.two_factor_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-factor authentication is already enabled.")

    secret = totp.generate_secret()
    current_user.two_factor_secret = seal(secret)
    await db.commit()

    return {
        "secret": secret,
        "otpauth_uri": totp.provisioning_uri(secret, current_user.email or current_user.username),
        "digits": totp.DIGITS,
        "period": totp.STEP_SECONDS,
    }


@router.post("/2fa/enable")
async def enable_two_factor(
    payload: TwoFactorEnable,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.two_factor_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Start the 2FA setup first.")

    secret = open_sealed(current_user.two_factor_secret)
    if not secret or not totp.verify_code(secret, payload.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="That code is not valid. Try the next one.")

    codes = totp.generate_recovery_codes()
    current_user.two_factor_enabled = True
    current_user.two_factor_recovery = totp.hash_recovery_codes(codes)
    add_audit(
        db,
        actor=current_user.email or current_user.username,
        action="TWO_FACTOR_ENABLED",
        resource_id=current_user.username,
        justification="Authenticator app enrolled; recovery codes generated",
    )
    await db.commit()

    return {"recovery_codes": codes}


@router.post("/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_two_factor(
    payload: TwoFactorDisable,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That password is not correct.")

    current_user.two_factor_enabled = False
    current_user.two_factor_secret = None
    current_user.two_factor_recovery = None
    add_audit(
        db,
        actor=current_user.email or current_user.username,
        action="TWO_FACTOR_DISABLED",
        resource_id=current_user.username,
        justification="Password re-authenticated",
    )
    await db.commit()
    return None


def _current_jti(token: str = Depends(oauth2_scheme)) -> Optional[str]:
    if token.startswith("bs_"):
        return None
    return decode_token(token).get("jti")


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    jti: Optional[str] = Depends(_current_jti),
):
    result = await db.execute(
        select(Session)
        .where(Session.user_id == current_user.id, Session.revoked_at.is_(None))
        .order_by(Session.last_seen_at.desc())
    )
    sessions = result.scalars().all()
    return [session_service.session_payload(session, jti) for session in sessions]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == current_user.id)
    )
    session = result.scalars().first()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    if session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        add_audit(
            db,
            actor=current_user.email or current_user.username,
            action="SESSION_REVOKED",
            resource_id=f"session-{session.id}",
            justification=session.user_agent or "unknown device",
        )
        await db.commit()
    return None


@router.post("/sessions/revoke-others")
async def revoke_other_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    jti: Optional[str] = Depends(_current_jti),
):
    result = await db.execute(
        select(Session).where(Session.user_id == current_user.id, Session.revoked_at.is_(None))
    )
    revoked = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for session in result.scalars().all():
        if session.jti == jti:
            continue
        session.revoked_at = now
        revoked += 1

    if revoked:
        add_audit(
            db,
            actor=current_user.email or current_user.username,
            action="SESSIONS_REVOKED",
            resource_id="all-other-sessions",
            justification=f"{revoked} other session(s) signed out",
        )
        await db.commit()
    return {"revoked": revoked}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    jti: Optional[str] = Depends(_current_jti),
):
    if not jti:
        return None
    result = await db.execute(select(Session).where(Session.jti == jti))
    session = result.scalars().first()
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()
    return None


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    """Used by the dashboard on load to confirm a stored session token is still valid."""
    return current_user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    jti: Optional[str] = Depends(_current_jti),
):
    """Re-authenticates with the current password before replacing it."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That current password is not correct.",
        )

    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Choose a new password that is different from the current one.",
        )

    current_user.hashed_password = get_password_hash(payload.new_password)

    # Sign out every other device, keeping this one signed in.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = await db.execute(
        select(Session).where(Session.user_id == current_user.id, Session.revoked_at.is_(None))
    )
    revoked = 0
    for session in result.scalars().all():
        if session.jti == jti:
            continue
        session.revoked_at = now
        revoked += 1

    add_audit(
        db,
        actor=current_user.email or current_user.username,
        action="PASSWORD_CHANGED",
        resource_id=current_user.username,
        justification=f"Password re-authenticated and replaced; {revoked} other session(s) signed out",
    )
    await db.commit()
    return None
