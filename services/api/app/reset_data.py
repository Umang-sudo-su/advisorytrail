"""Removes all working data so BuildShield can be tested against real repositories.

Configuration is kept: ``.env``, the schema and the stored GitHub connection (so
private-repository access still resolves). Every user, repository, scan, finding,
audit entry, notification, token, session and webhook is deleted, then the first
admin account is created again and its password printed once.

Run it inside the API container:

    docker compose exec -T api python -m app.reset_data --yes
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Dict

from sqlalchemy import text

# Child tables first: this order satisfies every foreign key.
DELETE_ORDER = (
    "findings",
    "scans",
    "policies",
    "repositories",
    "notifications",
    "api_tokens",
    "sessions",
    "user_preferences",
    "workspace_members",
    "users",
    "audit_logs",
    "webhook_endpoints",
    "workspace_settings",
    "policy_settings",
)


async def wipe_data() -> Dict[str, int]:
    from app.database import SessionLocal
    from app.setup_wizard import prepare_database

    await prepare_database()

    counts: Dict[str, int] = {}
    async with SessionLocal() as db:
        for table in DELETE_ORDER:
            # Table names are constants defined above, never user input.
            total = (await db.execute(text(f"SELECT count(*) FROM {table}"))).scalar() or 0
            counts[table] = int(total)
            await db.execute(text(f"DELETE FROM {table}"))
        await db.commit()

    return counts


async def run() -> int:
    from app.setup_wizard import ensure_admin

    counts = await wipe_data()
    removed = sum(counts.values())

    print("BuildShield data reset")
    print("=" * 60)
    for table, total in counts.items():
        if total:
            print(f"  removed {total:>5} row(s) from {table}")
    print(f"  total rows removed: {removed}")
    print("  kept: .env configuration, schema and the GitHub connection")

    username = os.getenv("BUILDSHIELD_ADMIN_USERNAME", "admin")
    email = os.getenv("BUILDSHIELD_ADMIN_EMAIL", "admin@buildshield.local")
    password = os.getenv("BUILDSHIELD_ADMIN_PASSWORD", "")

    print("\nCreating the first admin account")
    status = await ensure_admin(username, email, password)

    print("\n" + "=" * 60)
    if status == "created":
        print(f"  Sign in as {username} <{email}>")
        print("  The password was printed above and is shown only once.")
        print("  Change it from Settings as soon as you sign in.")
    else:
        print(f"  Admin account: {status}")
    print("  Next: connect a repository on the Repositories page.")
    print("=" * 60)
    return 0


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delete all BuildShield working data")
    parser.add_argument("--yes", action="store_true", help="confirm the deletion")
    args = parser.parse_args(argv)

    if not args.yes:
        print(
            "Refusing to delete data without --yes.\n"
            "This removes every user, repository, scan, finding, audit entry, token, "
            "session, notification and webhook."
        )
        return 2

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
