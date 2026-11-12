"""GitHub repository validation for the Connect Repository flow.

Only github.com values are accepted, so a crafted URL can never make the API send
its GitHub token (or any request) to a different host.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import quote, urlparse

import httpx

GITHUB_API = "https://api.github.com"
GITHUB_HOSTS = {"github.com", "www.github.com"}

# GitHub's own rules: owners are alphanumeric with single hyphens, names allow . _ -
OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")

REQUEST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "BuildShield",
}


class RepositoryValidationError(Exception):
    """A user-facing reason the repository cannot be connected."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class GitHubRepositoryInfo:
    full_name: str
    html_url: str
    default_branch: str
    private: bool
    permissions: Dict[str, bool]

    @property
    def can_read(self) -> bool:
        return bool(self.permissions.get("pull"))


def normalize_repository(value: str) -> str:
    """Turns a URL or ``owner/name`` into a validated ``owner/name`` slug."""
    raw = (value or "").strip()
    if not raw:
        raise RepositoryValidationError("Enter a GitHub repository URL or owner/name.")

    if len(raw) > 300:
        raise RepositoryValidationError("That repository reference is too long.")

    raw = raw.split("#", 1)[0].split("?", 1)[0].rstrip("/")

    if raw.startswith("git@github.com:"):
        path = raw[len("git@github.com:"):]
    elif "://" in raw:
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            raise RepositoryValidationError("Only https://github.com repository URLs are supported.")
        if (parsed.hostname or "").lower() not in GITHUB_HOSTS:
            raise RepositoryValidationError(
                "Only github.com repositories can be connected. "
                "Paste a URL such as https://github.com/owner/repository."
            )
        path = parsed.path.strip("/")
    elif raw.lower().startswith(("github.com/", "www.github.com/")):
        path = raw.split("/", 1)[1]
    else:
        path = raw

    parts = [part for part in path.split("/") if part]
    if len(parts) != 2:
        raise RepositoryValidationError(
            "Use the form owner/repository, for example https://github.com/octocat/Hello-World."
        )

    owner, name = parts[0], parts[1]
    if name.lower().endswith(".git"):
        name = name[:-4]

    if name in {".", ".."} or not OWNER_RE.match(owner) or not REPO_RE.match(name):
        raise RepositoryValidationError(
            "That does not look like a valid GitHub repository name."
        )

    return f"{owner}/{name}"


def _headers(token: Optional[str]) -> Dict[str, str]:
    headers = dict(REQUEST_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _status_error(response: httpx.Response, full_name: str, account: Optional[str]) -> RepositoryValidationError:
    remaining = response.headers.get("x-ratelimit-remaining")
    if response.status_code == 403 and remaining == "0":
        return RepositoryValidationError(
            "The GitHub API rate limit has been reached. Wait a few minutes and try again.",
            429,
        )

    if response.status_code == 404:
        if account:
            return RepositoryValidationError(
                f"GitHub could not find {full_name}. Check the owner and name; if the "
                f"repository is private, the connected GitHub account ({account}) may not "
                "have access to it.",
                404,
            )
        return RepositoryValidationError(
            f"GitHub could not find {full_name}. Check the owner and name, and connect an "
            "account that can access it if it is private.",
            404,
        )

    if response.status_code == 401:
        return RepositoryValidationError(
            "GitHub rejected the stored token. Reconnect the GitHub account in Settings.",
            401,
        )

    if response.status_code == 403:
        return RepositoryValidationError(
            "GitHub refused access to this repository (HTTP 403). Check the token's permissions.",
            403,
        )

    return RepositoryValidationError(
        f"GitHub returned HTTP {response.status_code} while checking the repository. Try again.",
        502,
    )


async def lookup(full_name: str, token: Optional[str], account: Optional[str] = None) -> GitHubRepositoryInfo:
    """Confirms the repository exists and that the connected account can read it."""
    url = f"{GITHUB_API}/repos/{full_name}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0)) as client:
            response = await client.get(url, headers=_headers(token))
    except httpx.TimeoutException as error:
        raise RepositoryValidationError(
            "GitHub did not respond in time. Check your connection and try again.",
            504,
        ) from error
    except httpx.RequestError as error:
        raise RepositoryValidationError(
            "BuildShield could not reach GitHub. Check the server's internet connection.",
            502,
        ) from error

    if response.status_code != 200:
        raise _status_error(response, full_name, account)

    data = response.json()
    info = GitHubRepositoryInfo(
        full_name=data.get("full_name") or full_name,
        html_url=data.get("html_url") or f"https://github.com/{full_name}",
        default_branch=data.get("default_branch") or "main",
        private=bool(data.get("private")),
        permissions={key: bool(value) for key, value in (data.get("permissions") or {}).items()},
    )

    ensure_access(info, account)
    return info


def ensure_access(info: GitHubRepositoryInfo, account: Optional[str]) -> None:
    """Refuses a private repository the connected account cannot read."""
    if not info.private or info.can_read:
        return

    who = f"the connected GitHub account ({account})" if account else "the connected GitHub account"
    raise RepositoryValidationError(
        f"{info.full_name} is private and {who} does not have access to it. "
        "Ask a repository admin to grant access, then connect it again.",
        403,
    )


async def branch_exists(full_name: str, branch: str, token: Optional[str]) -> bool:
    """Confirms a branch name exists, so scans cannot be queued against a typo."""
    url = f"{GITHUB_API}/repos/{full_name}/branches/{quote(branch, safe='')}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(url, headers=_headers(token))
    except httpx.RequestError as error:
        raise RepositoryValidationError(
            "BuildShield could not reach GitHub to verify the branch.",
            502,
        ) from error

    if response.status_code == 200:
        return True
    if response.status_code == 404:
        return False
    if response.status_code in {401, 403}:
        raise _status_error(response, full_name, None)
    raise RepositoryValidationError(
        f"GitHub returned HTTP {response.status_code} while checking the branch.",
        502,
    )
