import httpx
import hmac
import hashlib
import json

SECRET = b"buildshield_secret_key"

# The Pull Request Event Payload
payload = {
    "action": "opened",
    "pull_request": {"head": {"sha": "657e1d4"}},
    "repository": {
        "name": "Umang-sudo-su/BuildShield", 
        "html_url": "https://github.com/Umang-sudo-su/BuildShield"
    }
}

# Serialize exactly as it will be sent, then sign it
body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
signature = "sha256=" + hmac.new(SECRET, msg=body, digestmod=hashlib.sha256).hexdigest()

print(f"Triggering PR webhook...")
resp = httpx.post(
    "http://127.0.0.1:8000/api/v1/webhooks/github",
    content=body,
    headers={
        "Content-Type": "application/json", 
        "X-GitHub-Event": "pull_request", 
        "X-Hub-Signature-256": signature
    }
)
print(f"Server responded with {resp.status_code}: {resp.text}")
