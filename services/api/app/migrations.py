"""Idempotent schema upgrades for databases created before a column existed."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

STATEMENTS = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_secret VARCHAR",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_enabled BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_recovery JSON",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS ip_address VARCHAR",
    "CREATE INDEX IF NOT EXISTS ix_sessions_jti ON sessions (jti)",
    "CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions (user_id)",

    # Hot-path indexes: list filters, joins and lookups that previously scanned whole tables.
    "CREATE INDEX IF NOT EXISTS ix_scans_repository_id ON scans (repository_id)",
    "CREATE INDEX IF NOT EXISTS ix_scans_status ON scans (status)",
    "CREATE INDEX IF NOT EXISTS ix_scans_created_at ON scans (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_findings_scan_id ON findings (scan_id)",
    "CREATE INDEX IF NOT EXISTS ix_findings_severity ON findings (severity)",
    "CREATE INDEX IF NOT EXISTS ix_findings_status ON findings (status)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_category ON audit_logs (category)",
    "CREATE INDEX IF NOT EXISTS ix_audit_logs_category_timestamp ON audit_logs (category, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_notifications_due ON notifications (status, scheduled_for)",
    "CREATE INDEX IF NOT EXISTS ix_sessions_user_active ON sessions (user_id, revoked_at)",
]


async def ensure_schema(conn: AsyncConnection) -> None:
    for statement in STATEMENTS:
        try:
            await conn.execute(text(statement))
        except Exception as error:  # a failed optional upgrade must not stop startup
            logger.warning("Schema upgrade skipped (%s): %s", statement, error)
