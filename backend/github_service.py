"""GitHub correlation service for Cascade RCA.

Locked public functions:
- get_recent_commits(...)
- get_commit_diff(...)

Resilient integration: Returns realistic mock commits or null if GitHub API is unavailable.
Never exposes tokens to the frontend.
"""

import os
from typing import List, Optional
import httpx
from backend.contracts import CommitInfo


# Realistic fallback commit catalog for the prototype demo
MOCK_COMMITS = {
    "payment-service": [
        CommitInfo(
            sha="a8f3b1c",
            message="fix(payment): update Stripe gateway timeout threshold and retry policy",
            url="https://github.com/echelon/cascade-rca/commit/a8f3b1c",
            author="alex.dev@echelon.io",
        ),
        CommitInfo(
            sha="b4e2c90",
            message="refactor(payment): migrate payment authorization handlers to v2",
            url="https://github.com/echelon/cascade-rca/commit/b4e2c90",
            author="sarah.m@echelon.io",
        ),
    ],
    "database": [
        CommitInfo(
            sha="d7c1e54",
            message="perf(db): modify Postgres connection pool max_connections and idle timeouts",
            url="https://github.com/echelon/cascade-rca/commit/d7c1e54",
            author="dave.dba@echelon.io",
        ),
        CommitInfo(
            sha="e9a0f32",
            message="migration: add composite index on transactions(order_id, created_at)",
            url="https://github.com/echelon/cascade-rca/commit/e9a0f32",
            author="dave.dba@echelon.io",
        ),
    ],
    "notification-service": [
        CommitInfo(
            sha="f2b8a71",
            message="fix(notif): update Twilio SMS delivery retry backoff queue",
            url="https://github.com/echelon/cascade-rca/commit/f2b8a71",
            author="jordan.k@echelon.io",
        )
    ],
    "order-service": [
        CommitInfo(
            sha="c3d8e91",
            message="feat(order): add idempotency key check on checkout requests",
            url="https://github.com/echelon/cascade-rca/commit/c3d8e91",
            author="chris.t@echelon.io",
        )
    ],
}


def get_recent_commits(service: Optional[str] = None) -> List[CommitInfo]:
    """Retrieve recent commits for the repository or targeted service."""
    github_token = os.getenv("GITHUB_TOKEN")
    owner = os.getenv("GITHUB_OWNER")
    repo = os.getenv("GITHUB_REPO")

    if github_token and owner and repo:
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/commits"
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "Cascade-RCA-Engine",
            }
            params = {}
            if service:
                params["path"] = f"services/{service}"

            with httpx.Client(timeout=3.0) as client:
                resp = client.get(url, headers=headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    commits = []
                    for item in data[:5]:
                        sha = item.get("sha", "")[:7]
                        commit_data = item.get("commit", {})
                        author_name = commit_data.get("author", {}).get("name", "dev")
                        msg = commit_data.get("message", "").split("\n")[0]
                        html_url = item.get("html_url", "")
                        commits.append(
                            CommitInfo(sha=sha, message=msg, url=html_url, author=author_name)
                        )
                    if commits:
                        return commits
        except Exception:
            # Fallback gracefully
            pass

    # Graceful fallback to mock commits for the suspected service
    if service and service in MOCK_COMMITS:
        return MOCK_COMMITS[service]

    default_list = []
    for s_commits in MOCK_COMMITS.values():
        default_list.extend(s_commits)
    return default_list[:5]


def get_commit_diff(sha: str) -> Optional[str]:
    """Retrieve commit diff text if available."""
    github_token = os.getenv("GITHUB_TOKEN")
    owner = os.getenv("GITHUB_OWNER")
    repo = os.getenv("GITHUB_REPO")

    if github_token and owner and repo:
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github.v3.diff",
                "User-Agent": "Cascade-RCA-Engine",
            }
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    return resp.text
        except Exception:
            pass

    return f"--- a/services/config.py\n+++ b/services/config.py\n@@ -15,3 +15,3 @@\n-TIMEOUT_MS = 5000\n+TIMEOUT_MS = 500\n"
