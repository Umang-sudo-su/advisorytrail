"""GitHub credential resolution: connected token from Settings first, env second."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.models import IntegrationCredential
from app.services.secret_box import open_sealed

GITHUB_API = "https://api.github.com"


@dataclass
class GitHubConnection:
    token: Optional[str]
    account: Optional[str]
    source: str  # "settings" | "environment" | "none"

    @property
    def connected(self) -> bool:
        return bool(self.token)


async def load_connection(db: AsyncSession) -> GitHubConnection:
    result = await db.execute(
        select(IntegrationCredential).where(IntegrationCredential.provider == "github")
    )
    credential = result.scalars().first()
    if credential is not None:
        token = open_sealed(credential.sealed_token)
        if token:
            return GitHubConnection(token=token, account=credential.account, source="settings")

    if settings.GITHUB_TOKEN:
        return GitHubConnection(token=settings.GITHUB_TOKEN, account=None, source="environment")

    return GitHubConnection(token=None, account=None, source="none")


async def verify_token(token: str) -> dict:
    """Validates a token against GitHub and returns the account details."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{GITHUB_API}/user", headers=headers, timeout=10.0)

    if response.status_code == 401:
        raise ValueError("GitHub rejected that token. Check that it is valid and not expired.")
    if response.status_code != 200:
        raise ValueError(f"GitHub returned HTTP {response.status_code} while validating the token.")

    data = response.json()
    return {
        "login": data.get("login"),
        "name": data.get("name"),
        "type": data.get("type"),
        "scopes": response.headers.get("x-oauth-scopes", ""),
    }
