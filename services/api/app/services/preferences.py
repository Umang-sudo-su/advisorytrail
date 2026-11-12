"""Settings storage and validation shared by the Settings page endpoints.

Workspace-wide values (name, scan execution defaults) and personal preferences
live in separate tables so a personal change can never overwrite a workspace
default. Unknown keys are rejected instead of silently stored.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import AuditLog, UserPreference, WorkspaceSettings

DEFAULT_WORKSPACE_NAME = "AdvisoryTrail"

LANDING_PAGES = ["dashboard", "repositories", "scans", "findings"]
LANGUAGES = ["en"]
DATE_FORMATS = ["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY"]
TIME_FORMATS = ["24h", "12h"]
PAGE_SIZES = [10, 25, 50, 100]
REFRESH_INTERVALS = [15, 30, 60, 300]
DENSITIES = ["comfortable", "compact"]
DIGESTS = ["immediate", "daily", "weekly"]
ROLES = ["owner", "admin", "security_analyst", "developer", "viewer"]
TRIGGER_KEYS = ["pr_opened", "pr_synchronize", "pr_reopened", "push"]
SCHEDULE_FREQUENCIES = ["daily", "weekly"]
SCANNERS = ["osv-dev"]

DEFAULT_SCAN: Dict[str, Any] = {
    "triggers": {
        "pr_opened": True,
        "pr_synchronize": True,
        "pr_reopened": True,
        "push": False,
    },
    "scanners": ["osv-dev"],
    "timeout_seconds": 600,
    "concurrency": 2,
    "scheduled": {"enabled": False, "frequency": "daily", "time": "02:00"},
    "branches": ["main"],
}

NOTIFICATION_EVENTS = [
    "new_findings_critical",
    "new_findings_high",
    "new_findings_medium",
    "new_findings_low",
    "scan_completed",
    "scan_failed",
    "scan_partial",
    "scan_queued",
    "pr_scan_completed",
    "pr_result_changed",
    "check_run_updated",
    "github_attention",
    "webhook_unhealthy",
    "repo_access_changed",
    "invite_received",
    "member_changed",
    "account_security",
]

DEFAULT_NOTIFICATIONS: Dict[str, Any] = {
    "events": {
        "new_findings_critical": True,
        "new_findings_high": True,
        "new_findings_medium": False,
        "new_findings_low": False,
        "scan_completed": True,
        "scan_failed": True,
        "scan_partial": True,
        "scan_queued": False,
        "pr_scan_completed": True,
        "pr_result_changed": True,
        "check_run_updated": False,
        "github_attention": True,
        "webhook_unhealthy": True,
        "repo_access_changed": True,
        "invite_received": True,
        "member_changed": True,
        "account_security": True,
    },
    "channels": {"in_app": True, "email": False},
    "digest": "immediate",
    "quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00"},
}

DEFAULT_USER: Dict[str, Any] = {
    "display_name": "",
    "landing_page": "dashboard",
    "language": "en",
    "date_format": "YYYY-MM-DD",
    "time_format": "24h",
    "timezone": "UTC",
    "auto_refresh": True,
    "refresh_interval": 30,
    "page_size": 25,
    "density": "comfortable",
    "reduce_motion": False,
    "notifications": DEFAULT_NOTIFICATIONS,
}

_BRANCH_RE = re.compile(r"^[A-Za-z0-9._/*-]{1,120}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _deep_copy(value):
    import copy

    return copy.deepcopy(value)


async def get_workspace_row(db: AsyncSession) -> WorkspaceSettings:
    result = await db.execute(select(WorkspaceSettings).order_by(WorkspaceSettings.id))
    row = result.scalars().first()
    if row is None:
        row = WorkspaceSettings(name=DEFAULT_WORKSPACE_NAME, settings=_deep_copy(DEFAULT_SCAN))
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def get_user_pref_row(db: AsyncSession, user_id: int) -> UserPreference:
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    row = result.scalars().first()
    if row is None:
        row = UserPreference(user_id=user_id, settings=_deep_copy(DEFAULT_USER))
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def scan_config(row: WorkspaceSettings) -> Dict[str, Any]:
    stored = row.settings or {}
    config = _deep_copy(DEFAULT_SCAN)
    for key, value in stored.items():
        if key == "triggers" and isinstance(value, dict):
            config["triggers"].update({k: bool(v) for k, v in value.items() if k in TRIGGER_KEYS})
        elif key == "scheduled" and isinstance(value, dict):
            config["scheduled"].update({k: v for k, v in value.items() if k in ("enabled", "frequency", "time")})
        else:
            config[key] = value
    return config


def user_preferences(row: UserPreference) -> Dict[str, Any]:
    stored = row.settings or {}
    prefs = _deep_copy(DEFAULT_USER)
    for key, value in stored.items():
        if key == "notifications" and isinstance(value, dict):
            for section, section_value in value.items():
                if isinstance(section_value, dict) and isinstance(prefs["notifications"].get(section), dict):
                    prefs["notifications"][section].update(section_value)
                else:
                    prefs["notifications"][section] = section_value
        else:
            prefs[key] = value
    return prefs


def workspace_payload(row: WorkspaceSettings) -> Dict[str, Any]:
    return {
        "name": row.name,
        "scan": scan_config(row),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def user_payload(row: UserPreference) -> Dict[str, Any]:
    return user_preferences(row)


def validate_workspace_payload(payload: Dict[str, Any], current_name: str) -> Dict[str, Any]:
    """Returns ``{"name": ..., "scan": ...}`` with only the fields actually sent."""
    cleaned: Dict[str, Any] = {}

    if "name" in payload:
        name = payload["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Workspace name cannot be empty.")
        name = name.strip()
        if len(name) > 64:
            raise ValueError("Workspace name must be 64 characters or fewer.")
        cleaned["name"] = name

    if "scan" in payload:
        scan = payload["scan"]
        if not isinstance(scan, dict):
            raise ValueError("Scan configuration must be an object.")
        cleaned["scan"] = _validate_scan(scan)

    return cleaned


def _validate_scan(scan: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    if "triggers" in scan:
        triggers = scan["triggers"]
        if not isinstance(triggers, dict):
            raise ValueError("Scan triggers must be an object.")
        unknown = set(triggers) - set(TRIGGER_KEYS)
        if unknown:
            raise ValueError(f"Unknown scan trigger: {sorted(unknown)[0]}")
        out["triggers"] = {key: bool(value) for key, value in triggers.items()}

    if "scanners" in scan:
        scanners = scan["scanners"]
        if not isinstance(scanners, list) or not scanners:
            raise ValueError("At least one scanner must stay selected.")
        unknown = [item for item in scanners if item not in SCANNERS]
        if unknown:
            raise ValueError(f"Scanner '{unknown[0]}' is not available on this server.")
        out["scanners"] = scanners

    if "timeout_seconds" in scan:
        timeout = scan["timeout_seconds"]
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 30 <= timeout <= 3600:
            raise ValueError("Scan timeout must be between 30 and 3600 seconds.")
        out["timeout_seconds"] = timeout

    if "concurrency" in scan:
        concurrency = scan["concurrency"]
        if not isinstance(concurrency, int) or isinstance(concurrency, bool) or not 1 <= concurrency <= 10:
            raise ValueError("Scan concurrency must be between 1 and 10.")
        out["concurrency"] = concurrency

    if "scheduled" in scan:
        scheduled = scan["scheduled"]
        if not isinstance(scheduled, dict):
            raise ValueError("Scheduled scans must be an object.")
        cleaned: Dict[str, Any] = {}
        if "enabled" in scheduled:
            cleaned["enabled"] = bool(scheduled["enabled"])
        if "frequency" in scheduled:
            if scheduled["frequency"] not in SCHEDULE_FREQUENCIES:
                raise ValueError("Schedule frequency must be daily or weekly.")
            cleaned["frequency"] = scheduled["frequency"]
        if "time" in scheduled:
            if not isinstance(scheduled["time"], str) or not _TIME_RE.match(scheduled["time"]):
                raise ValueError("Schedule time must use HH:MM (24-hour).")
            cleaned["time"] = scheduled["time"]
        out["scheduled"] = cleaned

    if "branches" in scan:
        branches = scan["branches"]
        if isinstance(branches, str):
            branches = [part.strip() for part in branches.split(",") if part.strip()]
        if not isinstance(branches, list):
            raise ValueError("Branches must be a list of branch names.")
        if len(branches) > 10:
            raise ValueError("At most 10 branch patterns can be configured.")
        for branch in branches:
            if not isinstance(branch, str) or not _BRANCH_RE.match(branch.strip()):
                raise ValueError(f"'{branch}' is not a valid branch name or pattern.")
        out["branches"] = [branch.strip() for branch in branches]

    return out


def validate_user_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Preferences must be an object.")

    allowed = set(DEFAULT_USER) - {"notifications"}
    unknown = set(payload) - allowed - {"notifications"}
    if unknown:
        raise ValueError(f"Unknown preference: {sorted(unknown)[0]}")

    out: Dict[str, Any] = {}

    for key in ("display_name",):
        if key in payload:
            value = payload[key]
            if not isinstance(value, str) or len(value) > 64:
                raise ValueError("Display name must be 64 characters or fewer.")
            out[key] = value.strip()

    if "landing_page" in payload:
        if payload["landing_page"] not in LANDING_PAGES:
            raise ValueError("Choose a supported default landing page.")
        out["landing_page"] = payload["landing_page"]

    if "language" in payload:
        if payload["language"] not in LANGUAGES:
            raise ValueError("Only English is available right now.")
        out["language"] = payload["language"]

    if "date_format" in payload:
        if payload["date_format"] not in DATE_FORMATS:
            raise ValueError("Choose a supported date format.")
        out["date_format"] = payload["date_format"]

    if "time_format" in payload:
        if payload["time_format"] not in TIME_FORMATS:
            raise ValueError("Time format must be 24h or 12h.")
        out["time_format"] = payload["time_format"]

    if "timezone" in payload:
        timezone_name = payload["timezone"]
        if not isinstance(timezone_name, str):
            raise ValueError("Time zone must be a name such as UTC or Europe/London.")
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"'{timezone_name}' is not a known time zone.")
        out["timezone"] = timezone_name

    if "auto_refresh" in payload:
        out["auto_refresh"] = bool(payload["auto_refresh"])

    if "refresh_interval" in payload:
        if payload["refresh_interval"] not in REFRESH_INTERVALS:
            raise ValueError("Auto-refresh interval must be 15, 30, 60 or 300 seconds.")
        out["refresh_interval"] = payload["refresh_interval"]

    if "page_size" in payload:
        if payload["page_size"] not in PAGE_SIZES:
            raise ValueError("Page size must be 10, 25, 50 or 100.")
        out["page_size"] = payload["page_size"]

    if "density" in payload:
        if payload["density"] not in DENSITIES:
            raise ValueError("Density must be comfortable or compact.")
        out["density"] = payload["density"]

    if "reduce_motion" in payload:
        out["reduce_motion"] = bool(payload["reduce_motion"])

    if "notifications" in payload:
        notifications = payload["notifications"]
        if not isinstance(notifications, dict):
            raise ValueError("Notification preferences must be an object.")
        cleaned: Dict[str, Any] = {}

        if "events" in notifications:
            events = notifications["events"]
            if not isinstance(events, dict):
                raise ValueError("Notification events must be an object.")
            unknown = set(events) - set(NOTIFICATION_EVENTS)
            if unknown:
                raise ValueError(f"Unknown notification event: {sorted(unknown)[0]}")
            cleaned["events"] = {key: bool(value) for key, value in events.items()}

        if "channels" in notifications:
            channels = notifications["channels"]
            if not isinstance(channels, dict):
                raise ValueError("Notification channels must be an object.")
            unknown = set(channels) - {"in_app", "email"}
            if unknown:
                raise ValueError(f"Unknown notification channel: {sorted(unknown)[0]}")
            cleaned["channels"] = {key: bool(value) for key, value in channels.items()}

        if "digest" in notifications:
            if notifications["digest"] not in DIGESTS:
                raise ValueError("Digest frequency must be immediate, daily or weekly.")
            cleaned["digest"] = notifications["digest"]

        if "quiet_hours" in notifications:
            quiet = notifications["quiet_hours"]
            if not isinstance(quiet, dict):
                raise ValueError("Quiet hours must be an object.")
            quiet_clean: Dict[str, Any] = {}
            if "enabled" in quiet:
                quiet_clean["enabled"] = bool(quiet["enabled"])
            for bound in ("start", "end"):
                if bound in quiet:
                    if not isinstance(quiet[bound], str) or not _TIME_RE.match(quiet[bound]):
                        raise ValueError("Quiet hours must use HH:MM (24-hour).")
                    quiet_clean[bound] = quiet[bound]
            cleaned["quiet_hours"] = quiet_clean

        out["notifications"] = cleaned

    return out


def add_audit(
    db: AsyncSession,
    actor: str,
    action: str,
    resource_id: str,
    justification: str | None,
    category: str = "Settings",
) -> None:
    db.add(
        AuditLog(
            actor=actor,
            action=action,
            resource_id=resource_id,
            justification=justification,
            category=category,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def role_matrix() -> List[Dict[str, Any]]:
    """Explicit capabilities per role so the UI never relies on the role name alone."""
    return [
        {
            "role": "owner",
            "label": "Owner",
            "capabilities": [
                "Full workspace control",
                "Manage members, integrations and settings",
                "Transfer workspace ownership",
            ],
        },
        {
            "role": "admin",
            "label": "Admin",
            "capabilities": [
                "Manage members, integrations and settings",
                "Cannot transfer ownership",
            ],
        },
        {
            "role": "security_analyst",
            "label": "Security Analyst",
            "capabilities": [
                "Review scans and findings",
                "Dismiss findings and record risk decisions",
                "Cannot change workspace settings or integrations",
            ],
        },
        {
            "role": "developer",
            "label": "Developer",
            "capabilities": [
                "View repositories, scans and findings",
                "Cannot change workspace-wide settings",
            ],
        },
        {
            "role": "viewer",
            "label": "Viewer",
            "capabilities": ["Read-only access to permitted areas"],
        },
    ]
