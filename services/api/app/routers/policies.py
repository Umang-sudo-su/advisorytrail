from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models import AuditLog, Policy
from app.services.policy import (
    RULE_DEFINITIONS,
    default_rule_state,
    get_policy_row,
    normalize_mode,
    rule_states,
    serialize,
)

router = APIRouter(prefix="/api/v1/policies", tags=["Policies"])

class PolicyCreate(BaseModel):
    repository_id: int
    rule_type: str

class PolicyRuleToggle(BaseModel):
    id: str
    enabled: bool

class PolicySettingsUpdate(BaseModel):
    mode: str
    rules: List[PolicyRuleToggle] = []

@router.get("")
@router.get("/")
async def read_policy_settings(db: AsyncSession = Depends(get_db)):
    """Returns the org-wide policy configuration used by the PR gate."""
    return serialize(await get_policy_row(db))

@router.put("")
@router.put("/")
async def update_policy_settings(payload: PolicySettingsUpdate, db: AsyncSession = Depends(get_db)):
    """Persists the Policies page configuration and records the change in the audit trail."""
    try:
        mode = normalize_mode(payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    known_rules = {rule["id"] for rule in RULE_DEFINITIONS}
    submitted = {}
    for item in payload.rules:
        if item.id not in known_rules:
            raise HTTPException(status_code=422, detail=f"Unknown policy rule: {item.id}")
        submitted[item.id] = item.enabled

    row = await get_policy_row(db)
    previous = serialize(row)

    states = default_rule_state()
    states.update(rule_states(row))
    states.update(submitted)
    for rule in RULE_DEFINITIONS:
        if rule["locked"]:
            states[rule["id"]] = True

    changes = []
    if previous["mode"] != mode:
        changes.append(f"mode {previous['mode']} -> {mode}")

    previous_states = {rule["id"]: rule["enabled"] for rule in previous["rules"]}
    for rule in RULE_DEFINITIONS:
        if previous_states.get(rule["id"]) != states[rule["id"]]:
            changes.append(f"{rule['id']} {'enabled' if states[rule['id']] else 'disabled'}")

    if not changes:
        return serialize(row)

    row.mode = mode
    row.rules = states
    row.updated_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            actor="umang@advisorytrail.dev",
            action="POLICY_UPDATED",
            resource_id="policy-settings",
            justification="; ".join(changes),
            category="Policy Changes",
        )
    )

    await db.commit()
    await db.refresh(row)
    return serialize(row)

@router.post("/")
async def create_policy(payload: PolicyCreate, db: AsyncSession = Depends(get_db)):
    new_policy = Policy(repository_id=payload.repository_id, rule_type=payload.rule_type)
    db.add(new_policy)
    await db.commit()
    await db.refresh(new_policy)
    return new_policy

@router.get("/{repository_id}")
async def list_repository_policies(repository_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Policy).where(Policy.repository_id == repository_id))
    return result.scalars().all()
