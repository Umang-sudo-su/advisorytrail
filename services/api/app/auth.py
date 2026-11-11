import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.database import get_db
from app.models import ApiToken, Session, User

# JWT_SECRET is the historical env var name; SECRET_KEY is the pydantic setting.
SECRET_KEY = os.getenv("JWT_SECRET") or settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(
    data: dict,
    jti: Optional[str] = None,
    version: int = 0,
    expires_delta: timedelta | None = None,
):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "ver": version, "purpose": "access"})
    if jti:
        to_encode["jti"] = jti
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_challenge_token(username: str) -> str:
    """Short-lived token proving the password step passed, before the TOTP step."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    return jwt.encode({"sub": username, "purpose": "2fa", "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def _credentials_error(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def _user_from_api_token(token: str, request: Request, db: AsyncSession):
    """Resolves ``bs_...`` programmatic tokens and enforces their scopes."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    result = await db.execute(
        select(ApiToken).where(ApiToken.token_hash == token_hash, ApiToken.revoked_at.is_(None))
    )
    api_token = result.scalars().first()
    if api_token is None:
        return None

    expires_at = api_token.expires_at
    if expires_at is not None:
        # Postgres hands back an aware datetime; normalise before comparing.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            return None

    scopes = set(api_token.scopes or [])
    required = "read" if request.method in SAFE_METHODS else "write"
    if required not in scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This API token is read-only. Create a token with the read and write scope "
                "to make changes."
            ),
        )

    user = await db.get(User, api_token.user_id)
    if user is None or not user.is_active:
        return None

    # Track last use, but only once a minute: this is bookkeeping, and writing the row on
    # every API request costs a commit + WAL flush per call.
    now = datetime.now(timezone.utc)
    last_used = api_token.last_used_at
    if last_used is not None and last_used.tzinfo is None:
        last_used = last_used.replace(tzinfo=timezone.utc)
    if last_used is None or (now - last_used).total_seconds() >= 60:
        api_token.last_used_at = now.replace(tzinfo=None)
        await db.commit()
    return user


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    if token.startswith("bs_"):
        api_user = await _user_from_api_token(token, request, db)
        if api_user is None:
            raise _credentials_error()
        return api_user

    payload = decode_token(token)
    if payload.get("purpose") != "access":
        raise _credentials_error()

    username: str = payload.get("sub")
    if username is None:
        raise _credentials_error()

    query = select(User).where(User.username == username)
    result = await db.execute(query)
    user = result.scalars().first()
    if user is None or not user.is_active:
        raise _credentials_error()

    # A bumped token_version invalidates every token issued before it.
    if int(payload.get("ver", 0)) != int(user.token_version or 0):
        raise _credentials_error("Your session has been revoked. Sign in again.")

    jti = payload.get("jti")
    if not jti:
        raise _credentials_error("Your session has been revoked. Sign in again.")

    session_result = await db.execute(
        select(Session).where(
            Session.jti == jti,
            Session.user_id == user.id,
            Session.revoked_at.is_(None),
        )
    )
    session = session_result.scalars().first()
    if session is None:
        raise _credentials_error("This session has been signed out. Sign in again.")

    now = datetime.now(timezone.utc)
    last_seen = session.last_seen_at
    if last_seen is not None and last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    if last_seen is None or (now - last_seen).total_seconds() > 60:
        session.last_seen_at = now.replace(tzinfo=None)
        await db.commit()

    return user
