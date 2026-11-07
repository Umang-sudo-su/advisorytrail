import pytest
import hmac
import hashlib
import json

# This must match the GITHUB_WEBHOOK_SECRET environment variable in your docker-compose.yml
WEBHOOK_SECRET = "my_super_secure_local_testing_secret"

def generate_github_signature(payload: dict) -> str:
    """
    Helper function to generate the X-Hub-Signature-256 header.
    GitHub uses HMAC with SHA-256 to sign payloads.
    """
    # FastAPI reads the raw body bytes, so we must serialize the payload identically
    payload_bytes = json.dumps(payload).encode("utf-8")
    secret_bytes = WEBHOOK_SECRET.encode("utf-8")
    
    hash_object = hmac.new(secret_bytes, msg=payload_bytes, digestmod=hashlib.sha256)
    return f"sha256={hash_object.hexdigest()}"

@pytest.mark.asyncio
async def test_github_webhook_valid_signature(async_client):
    """
    Verifies that a valid, properly signed GitHub pull_request payload
    is accepted by the API and returns a 202 Accepted status.
    """
    # 1. Create a mock GitHub Pull Request payload
    payload = {
        "action": "opened",
        "pull_request": {
            "id": 987654321,
            "title": "Update authentication logic",
            "state": "open"
        },
        "repository": {
            "name": "buildshield-demo",
            "full_name": "Umang-sudo-su/buildshield-demo"
        }
    }
    
    # 2. Attach the required GitHub headers, including the HMAC signature
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": generate_github_signature(payload),
        "Content-Type": "application/json"
    }
    
    # 3. Fire the request at the isolated API test client
    # Note: Adjust the URL path below if your webhook router prefix is different
    response = await async_client.post("/api/v1/webhooks/github", json=payload, headers=headers)
    
    # 4. Assert the expected outcomes
    assert response.status_code == 202
    
    # Optional: Verify the JSON response body matches your expected output
    response_data = response.json()
    assert "status" in response_data