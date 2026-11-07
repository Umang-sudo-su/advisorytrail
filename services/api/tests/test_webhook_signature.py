import hashlib
import hmac
import os
import pytest
from fastapi.testclient import TestClient

from app.main import app as fastapi_app
from app.routers import webhooks

SECRET = "test-secret"
URL = "/api/v1/webhooks/github"
client = TestClient(fastapi_app)

# Update your SECRET variable to this:
SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "my_super_secure_local_testing_secret")



def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_missing_signature_is_rejected():
    assert client.post(URL, content=b"{}").status_code == 401


def test_wrong_signature_is_rejected():
    r = client.post(URL, content=b"{}", headers={"X-Hub-Signature-256": "sha256=" + "0" * 64})
    assert r.status_code == 403


def test_valid_signature_ping_event():
    body = b"{}"
    r = client.post(
        URL,
        content=body,
        headers={"X-Hub-Signature-256": sign(body), "X-GitHub-Event": "ping"},
    )
    assert r.status_code == 202
    assert r.json() == {"message": "pong"}