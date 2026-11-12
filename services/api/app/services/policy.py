"""Org-wide policy settings for the deterministic pull request gate.

The Policies page edits a single configuration row. Rule wording and the locked
"incomplete" rule live here, on the server, so clients can only toggle the
booleans they are allowed to change.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PolicySettings

POLICY_MODES = ("report", "warn", "enforce")
DEFAULT_MODE = "enforce"

RULE_DEFINITIONS = (
    {
        "id": "block-new",
        "text": "Rule 1: New Critical/High Vulnerability with Fixed Version -> BLOCK PR Check Run",
        "default": True,
        "locked": False,
    },
    {
        "id": "warn-existing",
        "text": "Rule 2: Pre-existing Vulnerability in Baseline -> WARN ONLY",
        "default": True,
        "locked": False,
    },
    {
        "id": "incomplete",
        "text": "Rule 3: Failed or Timed-Out Scan -> INCOMPLETE CHECK (Never mark clean)",
        "default": True,
        "locked": True,
    },
)


def default_rule_state() -> dict[str, bool]:
    return {rule["id"]: rule["default"] for rule in RULE_DEFINITIONS}


async def get_policy_row(db: AsyncSession) -> PolicySettings:
    """Returns the stored configuration, creating the defaults on first use."""
    row = (await db.execute(select(PolicySettings).order_by(PolicySettings.id))).scalars().first()
    if row is None:
        row = PolicySettings(mode=DEFAULT_MODE, rules=default_rule_state())
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


def rule_states(row: PolicySettings) -> dict[str, bool]:
    stored = row.rules if isinstance(row.rules, dict) else {}
    states = default_rule_state()
    for rule in RULE_DEFINITIONS:
        if rule["id"] in stored:
            states[rule["id"]] = bool(stored[rule["id"]])
        if rule["locked"]:
            states[rule["id"]] = True
    return states


def normalize_mode(value: str) -> str:
    mode = (value or "").strip().lower()
    if mode not in POLICY_MODES:
        raise ValueError(f"Unknown policy mode. Allowed: {', '.join(POLICY_MODES)}")
    return mode


def serialize(row: PolicySettings) -> dict[str, Any]:
    states = rule_states(row)
    return {
        "mode": row.mode if row.mode in POLICY_MODES else DEFAULT_MODE,
        "rules": [
            {
                "id": rule["id"],
                "text": rule["text"],
                "locked": rule["locked"],
                "enabled": states[rule["id"]],
            }
            for rule in RULE_DEFINITIONS
        ],
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def evaluate_check_run(
    db: AsyncSession,
    *,
    manifest_name: str,
    total_findings: int,
    blocking_new: int,
) -> tuple[str, str]:
    """Applies the stored policy to a finished scan.

    Returns the GitHub commit state ("success" or "failure") and the check run
    description that explains the decision.
    """
    settings = serialize(await get_policy_row(db))
    mode = settings["mode"]
    states = {rule["id"]: rule["enabled"] for rule in settings["rules"]}

    if total_findings == 0:
        return "success", f"AdvisoryTrail: {manifest_name} passed!"

    if mode == "report":
        return "success", f"AdvisoryTrail: {total_findings} vulnerabilities found (report only)."

    if mode == "warn":
        return "success", f"AdvisoryTrail: {total_findings} vulns found (Warning Mode)."

    if not states.get("block-new", True):
        return "success", f"AdvisoryTrail: {total_findings} vulns found (Rule 1 is off, PR not blocked)."

    if blocking_new > 0:
        return "failure", (
            f"AdvisoryTrail: {blocking_new} new Critical/High vulns with fixes block this PR."
        )

    return "success", f"AdvisoryTrail: {total_findings} vulns found (no new Critical/High with fixes)."
