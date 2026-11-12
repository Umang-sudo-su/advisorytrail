"""Every review and scan endpoint must refuse anonymous callers."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_findings_list_requires_a_session():
    assert client.get("/api/v1/findings/").status_code == 401


def test_single_review_requires_a_session():
    response = client.patch("/api/v1/findings/1", json={"status": "DISMISSED"})
    assert response.status_code == 401


def test_bulk_review_requires_a_session():
    response = client.patch(
        "/api/v1/findings/bulk",
        json={"ids": [1, 2], "status": "DISMISSED"},
    )
    assert response.status_code == 401


def test_scans_require_a_session():
    assert client.get("/api/v1/scans/").status_code == 401
    assert client.post("/api/v1/scans/", json={"repository_id": 1, "commit_hash": "main"}).status_code == 401


def test_repository_connection_requires_a_session():
    response = client.post(
        "/api/v1/repositories/",
        json={"url": "https://github.com/octocat/Hello-World", "branch": "main"},
    )
    assert response.status_code == 401
