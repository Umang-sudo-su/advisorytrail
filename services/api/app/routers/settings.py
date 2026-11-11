"""Settings page API: workspace defaults, personal preferences, team, tokens and webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import timedelta
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth import get_current_user
from app.config import settings as app_settings
from app.database import get_db
from app.models import (
    ApiToken,
    AuditLog,
    IntegrationCredential,
    Notification,
    Repository,
    User,
    WebhookEndpoint,
    WorkspaceMember,
)
from app.services.secret_box import seal
from app.services import github_auth, mailer
from app.services import notifications as notification_service
from app.services import preferences as prefs
from app.services import scheduler as scheduler_service

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

GITHUB_PERMISSIONS = [
    "Repository contents — read dependency manifests (package-lock.json, poetry.lock, requirements.txt)",
    "Pull requests — read head/base commits to diff findings",
    "Commit statuses — write the BuildShield check result on the scanned commit",
]


class MemberInvite(BaseModel):
    email: EmailStr
    role: str = Field(default="developer")


class MemberUpdate(BaseModel):
    role: str


class TokenCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)
    scopes: List[str] = Field(default_factory=lambda: ["read", "write"])


class GitHubConnect(BaseModel):
    token: str = Field(min_length=8, max_length=255)


class GitHubOAuthExchange(BaseModel):
    code: str = Field(min_length=4, max_length=255)


class WebhookCreate(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    url: str = Field(min_length=8, max_length=500)
    events: List[str] = Field(default_factory=list)


class WebhookUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=64)
    url: str | None = Field(default=None, min_length=8, max_length=500)
    events: List[str] | None = None
    enabled: bool | None = None


WEBHOOK_EVENT_TYPES = [
    {"id": "scan.completed", "label": "Scan completed"},
    {"id": "scan.failed", "label": "Scan failed or timed out"},
    {"id": "finding.new", "label": "New finding detected"},
    {"id": "repository.changed", "label": "Repository connection changed"},
]


def _actor(user: User) -> str:
    return user.email or user.username


def _iso(value) -> str | None:
    return value.isoformat() if value else None


async def _member_rows(db: AsyncSession) -> List[WorkspaceMember]:
    result = await db.execute(select(WorkspaceMember).order_by(WorkspaceMember.created_at, WorkspaceMember.id))
    return list(result.scalars().all())


async def _ensure_owner(db: AsyncSession, user: User) -> WorkspaceMember:
    """Bootstraps the signed-in account as the workspace Owner on first use."""
    result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.email == user.email))
    member = result.scalars().first()
    if member is not None:
        if member.user_id is None:
            member.user_id = user.id
            member.status = "active"
            await db.commit()
        return member

    member = WorkspaceMember(
        user_id=user.id,
        email=user.email,
        role="owner",
        status="active",
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


def _member_payload(member: WorkspaceMember) -> Dict[str, Any]:
    return {
        "id": member.id,
        "email": member.email,
        "role": member.role,
        "status": member.status,
        "invited_at": _iso(member.invited_at),
        "created_at": _iso(member.created_at),
        "is_registered": member.user_id is not None,
    }


def _token_payload(token: ApiToken) -> Dict[str, Any]:
    return {
        "id": token.id,
        "name": token.name,
        "prefix": token.prefix,
        "scopes": token.scopes or [],
        "created_at": _iso(token.created_at),
        "last_used_at": _iso(token.last_used_at),
        "expires_at": _iso(token.expires_at),
        "revoked": token.revoked_at is not None,
        "revoked_at": _iso(token.revoked_at),
    }


def _webhook_payload(endpoint: WebhookEndpoint) -> Dict[str, Any]:
    return {
        "id": endpoint.id,
        "name": endpoint.name,
        "url": endpoint.url,
        "events": endpoint.events or [],
        "enabled": bool(endpoint.enabled),
        "created_at": _iso(endpoint.created_at),
        "last_delivery_at": _iso(endpoint.last_delivery_at),
        "last_delivery_status": endpoint.last_delivery_status,
    }


def _github_account(repositories: List[Repository]) -> str | None:
    for repo in repositories:
        if not repo.url:
            continue
        parsed = urlparse(repo.url)
        if parsed.netloc.lower() in {"github.com", "www.github.com"}:
            parts = [part for part in parsed.path.strip("/").split("/") if part]
            if parts:
                return parts[0]
    return None


async def _integration_payload(db: AsyncSession) -> Dict[str, Any]:
    result = await db.execute(select(Repository).order_by(Repository.id))
    repositories = list(result.scalars().all())

    last_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.category == "GitHub Webhooks")
        .order_by(AuditLog.timestamp.desc())
        .limit(1)
    )
    last_event = last_result.scalars().first()

    connection = await github_auth.load_connection(db)
    client_id = os.getenv("GITHUB_CLIENT_ID", "").strip()
    callback = os.getenv("GITHUB_OAUTH_CALLBACK", "http://localhost:5173/")

    return {
        "github": {
            "connected": connection.connected,
            "account": connection.account or _github_account(repositories),
            "source": connection.source,
            "permissions": GITHUB_PERMISSIONS,
            "webhook_secret_configured": bool(app_settings.GITHUB_WEBHOOK_SECRET),
            "last_event_at": _iso(last_event.timestamp) if last_event else None,
            "last_event_action": last_event.action if last_event else None,
            "last_event_resource": last_event.resource_id if last_event else None,
            "oauth_configured": bool(client_id and os.getenv("GITHUB_CLIENT_SECRET")),
            "oauth_authorize_url": (
                "https://github.com/login/oauth/authorize"
                f"?client_id={client_id}&scope=repo&redirect_uri={callback}"
                if client_id
                else None
            ),
            "repositories": [
                {
                    "id": repo.id,
                    "name": repo.name,
                    "url": repo.url,
                }
                for repo in repositories
            ],
        },
        "webhook_events": WEBHOOK_EVENT_TYPES,
    }


def _workspace_payload(row) -> Dict[str, Any]:
    payload = prefs.workspace_payload(row)
    scheduled = payload["scan"].get("scheduled") or {}
    next_run = scheduler_service.compute_next_run(scheduled)
    scheduled["next_run"] = next_run.isoformat() if next_run else None
    payload["scan"]["scheduled"] = scheduled
    return payload


@router.get("/")
async def read_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = await prefs.get_workspace_row(db)
    user_row = await prefs.get_user_pref_row(db, current_user.id)
    member = await _ensure_owner(db, current_user)

    members = await _member_rows(db)

    tokens_result = await db.execute(
        select(ApiToken).where(ApiToken.user_id == current_user.id).order_by(ApiToken.created_at.desc())
    )
    tokens = list(tokens_result.scalars().all())

    webhooks_result = await db.execute(select(WebhookEndpoint).order_by(WebhookEndpoint.created_at.desc()))
    webhooks = list(webhooks_result.scalars().all())

    return {
        "workspace": _workspace_payload(workspace),
        "user": prefs.user_payload(user_row),
        "account": {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "role": member.role,
            "member_since": _iso(member.created_at),
        },
        "members": [_member_payload(item) for item in members],
        "tokens": [_token_payload(item) for item in tokens],
        "webhooks": [_webhook_payload(item) for item in webhooks],
        "notifications": [
            notification_service.notification_payload(item)
            for item in await notification_service.recent_notifications(db, current_user.id)
        ],
        "roles": prefs.role_matrix(),
        "integrations": await _integration_payload(db),
        "server": {
            "version": APP_VERSION,
            "api_version": "v1",
            "scanner": {
                "id": "osv-dev",
                "name": "OSV.dev advisory API",
                "description": "Queries api.osv.dev for advisories affecting pinned dependency versions.",
            },
            "email": mailer.transport_status(),
            "email_configured": mailer.transport_status()["configured"],
            "two_factor_available": True,
            "scheduled_scans_available": True,
            "scheduler_tick_seconds": scheduler_service.TICK_SECONDS,
            "api_base": "http://localhost:8000",
        },
    }


@router.put("/workspace")
async def update_workspace(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workspace = await prefs.get_workspace_row(db)
    try:
        cleaned = prefs.validate_workspace_payload(payload, workspace.name)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))

    changes: List[str] = []

    if "name" in cleaned and cleaned["name"] != workspace.name:
        changes.append(f"name {workspace.name} -> {cleaned['name']}")
        workspace.name = cleaned["name"]

    if "scan" in cleaned:
        current_scan = prefs.scan_config(workspace)
        updated_scan = json.loads(json.dumps(current_scan))
        for key, value in cleaned["scan"].items():
            if isinstance(value, dict):
                updated_scan.setdefault(key, {}).update(value)
            else:
                updated_scan[key] = value
        diff = _scan_diff(current_scan, updated_scan)
        if diff:
            changes.append(diff)
            workspace.settings = updated_scan

    if changes:
        prefs.add_audit(
            db,
            actor=_actor(current_user),
            action="WORKSPACE_SETTINGS_UPDATED",
            resource_id="workspace-settings",
            justification="; ".join(changes),
        )
        workspace.updated_at = prefs.utcnow()
        await db.commit()
        await db.refresh(workspace)

    return {"workspace": _workspace_payload(workspace)}


def _scan_diff(before: Dict[str, Any], after: Dict[str, Any]) -> str:
    parts: List[str] = []

    before_triggers = before.get("triggers", {})
    after_triggers = after.get("triggers", {})
    for key, value in after_triggers.items():
        if before_triggers.get(key) != value:
            parts.append(f"trigger {key} {'on' if value else 'off'}")

    for key in ("timeout_seconds", "concurrency", "scanners", "branches"):
        if before.get(key) != after.get(key):
            parts.append(f"{key} {before.get(key)} -> {after.get(key)}")

    if before.get("scheduled") != after.get("scheduled"):
        parts.append("scheduled scans changed")

    return "; ".join(parts)


@router.post("/github/connect")
async def connect_github(
    payload: GitHubConnect,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    token = payload.token.strip()
    try:
        account = await github_auth.verify_token(token)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach GitHub to validate the token: {type(error).__name__}",
        )

    result = await db.execute(
        select(IntegrationCredential).where(IntegrationCredential.provider == "github")
    )
    credential = result.scalars().first()
    sealed = seal(token)

    if credential is None:
        credential = IntegrationCredential(
            provider="github",
            sealed_token=sealed,
            account=account.get("login"),
        )
        db.add(credential)
    else:
        credential.sealed_token = sealed
        credential.account = account.get("login")
        credential.updated_at = prefs.utcnow()

    prefs.add_audit(
        db,
        actor=_actor(current_user),
        action="GITHUB_CONNECTED",
        resource_id=account.get("login") or "github",
        justification=f"Token validated; scopes {account.get('scopes') or 'unspecified'}",
    )
    await db.commit()

    return {
        "github": {
            "connected": True,
            "account": account.get("login"),
            "name": account.get("name"),
            "type": account.get("type"),
            "scopes": account.get("scopes"),
        },
        "integrations": await _integration_payload(db),
    }


@router.post("/github/disconnect")
async def disconnect_github(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Removes the stored credential. Repositories, scans and findings are kept."""
    result = await db.execute(
        select(IntegrationCredential).where(IntegrationCredential.provider == "github")
    )
    credential = result.scalars().first()
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GitHub is not connected from Settings.")

    account = credential.account or "github"
    await db.delete(credential)
    prefs.add_audit(
        db,
        actor=_actor(current_user),
        action="GITHUB_DISCONNECTED",
        resource_id=account,
        justification="Stored token removed; repository and scan history kept",
    )
    await db.commit()
    return None


@router.post("/github/oauth/exchange")
async def exchange_github_code(
    payload: GitHubOAuthExchange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    client_id = os.getenv("GITHUB_CLIENT_ID", "").strip()
    client_secret = os.getenv("GITHUB_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub OAuth is not configured on this server (set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET).",
        )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={"client_id": client_id, "client_secret": client_secret, "code": payload.code},
            timeout=10.0,
        )
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    token = data.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=data.get("error_description") or "GitHub did not return an access token.",
        )

    return await connect_github(GitHubConnect(token=token), db=db, current_user=current_user)


@router.post("/scan/schedule/run")
async def run_scheduled_scan_now(
    current_user: User = Depends(get_current_user),
):
    """Runs the same code path the scheduler uses, on demand."""
    result = await scheduler_service.run_scheduled_scans(reason=f"manual:{_actor(current_user)}")
    return result


@router.get("/notifications")
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = await notification_service.recent_notifications(db, current_user.id, limit=20)
    return [notification_service.notification_payload(item) for item in items]


@router.post("/notifications/test")
async def send_test_notification(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await prefs.get_user_pref_row(db, current_user.id)
    channels = prefs.user_preferences(row)["notifications"]["channels"]

    if not channels.get("in_app") and not channels.get("email"):
        return {"delivered": False, "detail": "Both delivery channels are turned off."}

    details = []
    delivered = False

    if channels.get("in_app"):
        db.add(
            Notification(
                user_id=current_user.id,
                event="account_security",
                subject="BuildShield test notification",
                body="This is a test notification from Settings.",
                digest="immediate",
                sent_at=prefs.utcnow(),
                status="in_app",
                detail="Shown in BuildShield",
            )
        )
        details.append("in-app")
        delivered = True

    if channels.get("email"):
        mail = await mailer.send_email(
            current_user.email,
            "BuildShield test notification",
            "This is a test notification from Settings → Notifications.",
        )
        details.append(f"email {mail['detail']}")
        delivered = delivered or mail["delivered"]

    prefs.add_audit(
        db,
        actor=_actor(current_user),
        action="NOTIFICATION_TEST",
        resource_id="notifications",
        justification="; ".join(details) or "no channels",
    )
    await db.commit()

    return {
        "delivered": delivered,
        "detail": "; ".join(details) or "Nothing was delivered.",
    }


@router.put("/user")
async def update_user_preferences(
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await prefs.get_user_pref_row(db, current_user.id)
    try:
        cleaned = prefs.validate_user_payload(payload)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error))

    stored = json.loads(json.dumps(row.settings or {}))

    for key, value in cleaned.items():
        if key == "notifications":
            current = stored.setdefault("notifications", {})
            for section, section_value in value.items():
                if isinstance(section_value, dict):
                    current.setdefault(section, {}).update(section_value)
                else:
                    current[section] = section_value
        else:
            stored[key] = value

    row.settings = stored
    row.updated_at = prefs.utcnow()
    await db.commit()
    await db.refresh(row)

    return {"user": prefs.user_payload(row)}


@router.post("/members", status_code=status.HTTP_201_CREATED)
async def invite_member(
    payload: MemberInvite,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _ensure_owner(db, current_user)

    if payload.role not in prefs.ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown role.")

    email = payload.email.strip().lower()
    existing = await db.execute(select(WorkspaceMember).where(WorkspaceMember.email == email))
    if existing.scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email is already a member or invited.")

    user_result = await db.execute(select(User).where(User.email == email))
    existing_user = user_result.scalars().first()

    member = WorkspaceMember(
        user_id=existing_user.id if existing_user else None,
        email=email,
        role=payload.role,
        status="active" if existing_user else "pending",
    )
    db.add(member)
    prefs.add_audit(
        db,
        actor=_actor(current_user),
        action="MEMBER_INVITED",
        resource_id=email,
        justification=f"role {payload.role}",
    )
    await db.commit()
    await db.refresh(member)

    return {
        "member": _member_payload(member),
        "email_sent": False,
        "note": "Invitation recorded. Email delivery is not configured on this server, so no message was sent.",
    }


@router.patch("/members/{member_id}")
async def update_member(
    member_id: int,
    payload: MemberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _ensure_owner(db, current_user)

    result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.id == member_id))
    member = result.scalars().first()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    if payload.role not in prefs.ROLES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown role.")

    if member.role == "owner" and payload.role != "owner":
        owners = [item for item in await _member_rows(db) if item.role == "owner" and item.status == "active"]
        if len(owners) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The workspace must keep at least one Owner.",
            )

    previous = member.role
    member.role = payload.role

    prefs.add_audit(
        db,
        actor=_actor(current_user),
        action="MEMBER_ROLE_CHANGED",
        resource_id=member.email,
        justification=f"{previous} -> {payload.role}",
    )
    await db.commit()
    await db.refresh(member)
    return {"member": _member_payload(member)}


@router.delete("/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    member_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    owner = await _ensure_owner(db, current_user)

    result = await db.execute(select(WorkspaceMember).where(WorkspaceMember.id == member_id))
    member = result.scalars().first()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")

    if member.id == owner.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot remove your own membership.")

    if member.role == "owner":
        owners = [item for item in await _member_rows(db) if item.role == "owner" and item.status == "active"]
        if len(owners) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The workspace must keep at least one Owner.",
            )

    email = member.email
    await db.delete(member)
    prefs.add_audit(
        db,
        actor=_actor(current_user),
        action="MEMBER_REMOVED",
        resource_id=email,
        justification=f"role {member.role} revoked",
    )
    await db.commit()
    return None


@router.post("/tokens", status_code=status.HTTP_201_CREATED)
async def create_token(
    payload: TokenCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scopes = sorted(set(payload.scopes))
    unknown = [scope for scope in scopes if scope not in {"read", "write"}]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown token scope: {unknown[0]}",
        )
    if "read" not in scopes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A token must include the read scope.",
        )

    secret = "bs_" + secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    expires_at = prefs.utcnow() + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None

    token = ApiToken(
        user_id=current_user.id,
        name=payload.name.strip(),
        prefix=secret[:11],
        token_hash=token_hash,
        scopes=scopes,
        expires_at=expires_at,
    )
    db.add(token)
    prefs.add_audit(
        db,
        actor=_actor(current_user),
        action="API_TOKEN_CREATED",
        resource_id=payload.name.strip(),
        justification=f"scopes {'+'.join(scopes)}; "
        + (f"expires {expires_at.date().isoformat()}" if expires_at else "no expiry"),
    )
    await db.commit()
    await db.refresh(token)

    return {
        "token": _token_payload(token),
        "secret": secret,
        "note": "Copy this token now. It cannot be shown again.",
    }


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == current_user.id)
    )
    token = result.scalars().first()
    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found.")

    if token.revoked_at is None:
        token.revoked_at = prefs.utcnow()
        prefs.add_audit(
            db,
            actor=_actor(current_user),
            action="API_TOKEN_REVOKED",
            resource_id=token.name,
            justification=f"prefix {token.prefix}",
        )
        await db.commit()
    return None


def _validate_webhook_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Webhook URL must be an absolute http(s) URL.",
        )
    return url


def _validate_events(events: List[str]) -> List[str]:
    known = {item["id"] for item in WEBHOOK_EVENT_TYPES}
    unknown = [item for item in events if item not in known]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown event type: {unknown[0]}",
        )
    return events


@router.post("/webhooks", status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: WebhookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    url = _validate_webhook_url(payload.url)
    events = _validate_events(payload.events) or [item["id"] for item in WEBHOOK_EVENT_TYPES]
    secret = "whsec_" + secrets.token_urlsafe(24)

    endpoint = WebhookEndpoint(
        name=payload.name.strip(),
        url=url,
        events=events,
        secret=secret,
        enabled=True,
    )
    db.add(endpoint)
    prefs.add_audit(
        db,
        actor=_actor(current_user),
        action="WEBHOOK_ENDPOINT_CREATED",
        resource_id=payload.name.strip(),
        justification=url,
    )
    await db.commit()
    await db.refresh(endpoint)

    return {
        "webhook": _webhook_payload(endpoint),
        "secret": secret,
        "note": "Copy this signing secret now. It cannot be shown again.",
    }


@router.patch("/webhooks/{webhook_id}")
async def update_webhook(
    webhook_id: int,
    payload: WebhookUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id))
    endpoint = result.scalars().first()
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")

    changes: List[str] = []

    if payload.name is not None and payload.name.strip() != endpoint.name:
        changes.append(f"name -> {payload.name.strip()}")
        endpoint.name = payload.name.strip()

    if payload.url is not None and payload.url != endpoint.url:
        endpoint.url = _validate_webhook_url(payload.url)
        changes.append(f"url -> {endpoint.url}")

    if payload.events is not None:
        endpoint.events = _validate_events(payload.events)
        changes.append("events updated")

    if payload.enabled is not None and payload.enabled != bool(endpoint.enabled):
        endpoint.enabled = payload.enabled
        changes.append("enabled" if payload.enabled else "disabled")

    if changes:
        prefs.add_audit(
            db,
            actor=_actor(current_user),
            action="WEBHOOK_ENDPOINT_UPDATED",
            resource_id=endpoint.name,
            justification="; ".join(changes),
        )
        await db.commit()
        await db.refresh(endpoint)

    return {"webhook": _webhook_payload(endpoint)}


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id))
    endpoint = result.scalars().first()
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")

    name = endpoint.name
    await db.delete(endpoint)
    prefs.add_audit(
        db,
        actor=_actor(current_user),
        action="WEBHOOK_ENDPOINT_DELETED",
        resource_id=name,
        justification="endpoint removed; audit history retained",
    )
    await db.commit()
    return None


@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(
    webhook_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.id == webhook_id))
    endpoint = result.scalars().first()
    if endpoint is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook endpoint not found.")

    body = json.dumps(
        {
            "event": "webhook.test",
            "delivered_at": prefs.utcnow().isoformat() + "Z",
            "workspace": (await prefs.get_workspace_row(db)).name,
        }
    ).encode("utf-8")
    signature = hmac.new(endpoint.secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256).hexdigest()

    delivered = False
    detail = ""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoint.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-BuildShield-Event": "webhook.test",
                    "X-BuildShield-Signature": f"sha256={signature}",
                },
                timeout=8.0,
            )
        delivered = 200 <= response.status_code < 300
        detail = f"HTTP {response.status_code}"
    except Exception as error:  # network failure is reported, never hidden
        detail = type(error).__name__

    endpoint.last_delivery_at = prefs.utcnow()
    endpoint.last_delivery_status = "delivered" if delivered else f"failed ({detail})"
    prefs.add_audit(
        db,
        actor=_actor(current_user),
        action="WEBHOOK_TEST_DELIVERY",
        resource_id=endpoint.name,
        justification=endpoint.last_delivery_status,
        category="GitHub Webhooks",
    )
    await db.commit()
    await db.refresh(endpoint)

    return {
        "delivered": delivered,
        "detail": detail,
        "webhook": _webhook_payload(endpoint),
    }
