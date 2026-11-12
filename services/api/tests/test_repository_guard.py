import pytest

from app.services.github_repos import (
    GitHubRepositoryInfo,
    RepositoryValidationError,
    ensure_access,
    normalize_repository,
)
from app.services.net_guard import validate_public_url


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://github.com/OWASP/NodeGoat", "OWASP/NodeGoat"),
        ("http://www.github.com/octocat/Hello-World.git", "octocat/Hello-World"),
        ("https://github.com/octocat/Hello-World/", "octocat/Hello-World"),
        ("https://github.com/octocat/Hello-World?tab=readme#top", "octocat/Hello-World"),
        ("git@github.com:owner/repo.git", "owner/repo"),
        ("github.com/owner/repo", "owner/repo"),
        ("owner/repo", "owner/repo"),
    ],
)
def test_normalize_repository_accepts_github_references(value, expected):
    assert normalize_repository(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "https://gitlab.com/owner/repo",
        "https://github.com/onlyowner",
        "https://github.com/owner/repo/extra",
        "ftp://github.com/owner/repo",
        "https://example.com/owner/repo",
        "owner/repo with spaces",
    ],
)
def test_normalize_repository_rejects_other_input(value):
    with pytest.raises(RepositoryValidationError):
        normalize_repository(value)


def _info(private: bool, pull: bool | None) -> GitHubRepositoryInfo:
    permissions = {} if pull is None else {"pull": pull}
    return GitHubRepositoryInfo(
        full_name="owner/repo",
        html_url="https://github.com/owner/repo",
        default_branch="main",
        private=private,
        permissions=permissions,
    )


def test_public_repository_needs_no_permissions():
    ensure_access(_info(private=False, pull=None), account="someone")


def test_private_repository_with_pull_is_allowed():
    ensure_access(_info(private=True, pull=True), account="owner")


def test_private_repository_without_access_is_refused():
    with pytest.raises(RepositoryValidationError) as error:
        ensure_access(_info(private=True, pull=False), account="stranger")

    assert error.value.status_code == 403
    assert "does not have access" in error.value.message


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000/hook",
        "http://127.0.0.1/hook",
        "http://10.0.0.5/hook",
        "http://192.168.1.10/hook",
        "http://169.254.169.254/latest/meta-data",
        "http://service.internal/hook",
        "http://printer.local/hook",
        "file:///etc/passwd",
        "not-a-url",
    ],
)
def test_webhook_guard_blocks_local_targets(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


def test_webhook_guard_allows_public_targets():
    assert validate_public_url("https://example.com/hook") == "https://example.com/hook"
