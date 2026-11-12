import httpx
import os
import logging

logger = logging.getLogger(__name__)

async def update_github_check(repo_full_name: str, commit_hash: str, status: str, conclusion: str = None, summary: str = ""):
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        logger.warning("No GITHUB_TOKEN set. Skipping status update.")
        return

    # URL updated to the Commit Statuses API
    url = f"https://api.github.com/repos/{repo_full_name}/statuses/{commit_hash}"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    # Map our internal statuses to GitHub's 'state' requirements (pending, success, failure)
    state = "pending"
    if conclusion == "success":
        state = "success"
    elif conclusion == "failure":
        state = "failure"

    payload = {
        "state": state,
        "description": summary[:140] if summary else "Scan in progress...",
        "context": "AdvisoryTrail Security Scan"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code not in [200, 201]:
            logger.error(f"Failed to update GitHub Status: {response.text}")
