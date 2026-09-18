"""GitHub REST API correlation service for Cascade RCA. LOCKED.

Locked public functions:
- get_recent_commits(...)
- get_commit_diff(...)

Correlates suspected root-cause microservices with recent repository commits
and diffs using the GitHub REST API. Gracefully degrades when GitHub is
unavailable, unconfigured, or rate-limited. Never exposes tokens to the frontend.
"""

import logging
import os
from typing import Dict, List, Optional
import httpx
from dotenv import load_dotenv

from backend.contracts import CommitInfo

load_dotenv()

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"

# Realistic curated mock commits for hackathon demo scenarios when
# GitHub API is unconfigured, unreachable, or rate-limited.
MOCK_COMMITS: Dict[str, List[CommitInfo]] = {
    "payment-service": [
        CommitInfo(
            sha="a8f3b1c",
            message="fix(payment): update Stripe gateway timeout threshold and retry policy",
            url="https://github.com/shashank1556/cascade-rca/commit/a8f3b1c",
            author="alex.dev@echelon.io",
        ),
        CommitInfo(
            sha="b4e2c90",
            message="refactor(payment): migrate payment authorization handlers to v2",
            url="https://github.com/shashank1556/cascade-rca/commit/b4e2c90",
            author="sarah.m@echelon.io",
        ),
    ],
    "database": [
        CommitInfo(
            sha="d7c1e54",
            message="perf(db): modify Postgres connection pool max_connections and idle timeouts",
            url="https://github.com/shashank1556/cascade-rca/commit/d7c1e54",
            author="dave.dba@echelon.io",
        ),
        CommitInfo(
            sha="e9a0f32",
            message="migration: add composite index on transactions(order_id, created_at)",
            url="https://github.com/shashank1556/cascade-rca/commit/e9a0f32",
            author="dave.dba@echelon.io",
        ),
    ],
    "notification-service": [
        CommitInfo(
            sha="f2b8a71",
            message="fix(notif): update Twilio SMS delivery retry backoff queue",
            url="https://github.com/shashank1556/cascade-rca/commit/f2b8a71",
            author="jordan.k@echelon.io",
        )
    ],
    "order-service": [
        CommitInfo(
            sha="c3d8e91",
            message="feat(order): add idempotency key check on checkout requests",
            url="https://github.com/shashank1556/cascade-rca/commit/c3d8e91",
            author="chris.t@echelon.io",
        )
    ],
    "api-gateway": [
        CommitInfo(
            sha="1e84c50",
            message="chore(gateway): update ratelimit middleware route mappings",
            url="https://github.com/shashank1556/cascade-rca/commit/1e84c50",
            author="platform-team@echelon.io",
        )
    ],
}

# Service keyword mapping for intelligent commit message matching
SERVICE_KEYWORDS: Dict[str, List[str]] = {
    "payment-service": ["payment", "payments", "stripe", "gateway", "transaction", "pay", "billing"],
    "database": ["database", "db", "postgres", "sql", "query", "pool", "vacuum", "migration"],
    "notification-service": ["notification", "notify", "email", "sms", "queue", "push", "alert"],
    "order-service": ["order", "orders", "checkout", "fulfillment"],
    "api-gateway": ["gateway", "proxy", "routing", "ingress", "ratelimit"],
    "user-service": ["user", "auth", "session", "profile"],
    "product-service": ["product", "catalog", "inventory", "item"],
}

FALLBACK_COMMITS = MOCK_COMMITS


def _get_headers(token: Optional[str] = None) -> Dict[str, str]:
    """Construct safe GitHub API headers without leaking tokens."""
    token = token or os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Cascade-RCA-Observability",
    }
    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers


def get_recent_commits(
    service: Optional[str] = None,
    limit: int = 10,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    use_fallback: bool = True,
) -> List[CommitInfo]:
    """Retrieve recent commits from GitHub REST API, optionally filtered by service.

    Args:
        service: Optional service name to correlate with commit messages/paths.
        limit: Maximum number of commits to retrieve.
        owner: GitHub repository owner (defaults to GITHUB_OWNER env var).
        repo: GitHub repository name (defaults to GITHUB_REPO env var).
        token: Optional GitHub token (defaults to GITHUB_TOKEN env var).
        use_fallback: Whether to return curated mock commits if GitHub is unavailable.

    Returns:
        List[CommitInfo] objects matching the canonical contract.
    """
    owner = owner or os.getenv("GITHUB_OWNER")
    repo = repo or os.getenv("GITHUB_REPO")
    token = token or os.getenv("GITHUB_TOKEN")

    if owner and repo:
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits"
        headers = _get_headers(token)

        try:
            with httpx.Client(timeout=3.5) as client:
                response = client.get(url, headers=headers, params={"per_page": min(limit * 2, 30)})

                if response.status_code == 200:
                    commits_data = response.json()
                    if isinstance(commits_data, list):
                        results: List[CommitInfo] = []
                        keywords = SERVICE_KEYWORDS.get(service, [service]) if service else []

                        for item in commits_data:
                            sha = item.get("sha", "")[:7]
                            commit_obj = item.get("commit", {})
                            message = commit_obj.get("message", "").split("\n")[0]
                            html_url = item.get("html_url", f"https://github.com/{owner}/{repo}/commit/{sha}")
                            author_obj = commit_obj.get("author", {}) or item.get("author", {})
                            author = (
                                author_obj.get("name")
                                or (item.get("author") or {}).get("login")
                                or "unknown"
                            )

                            commit_info = CommitInfo(
                                sha=sha,
                                message=message,
                                url=html_url,
                                author=author,
                            )

                            if service and keywords:
                                message_lower = message.lower()
                                if any(kw in message_lower for kw in keywords):
                                    results.append(commit_info)
                            else:
                                results.append(commit_info)

                            if len(results) >= limit:
                                break

                        if results:
                            return results
                else:
                    logger.warning(
                        "GitHub API responded with status %d: %s",
                        response.status_code,
                        response.text[:100],
                    )
        except Exception as e:
            logger.warning("Error communicating with GitHub API: %s; using fallback if enabled", e)

    # Graceful fallback to mock commits for the suspected service
    if use_fallback:
        if service and service in MOCK_COMMITS:
            return MOCK_COMMITS[service][:limit]
        elif not service:
            all_commits = []
            for comm_list in MOCK_COMMITS.values():
                all_commits.extend(comm_list)
            return all_commits[:limit]

    return []


def get_commit_diff(
    sha: str,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[str]:
    """Retrieve commit diff text for a specific commit SHA.

    CONTRACT REQUIREMENT: Returns Optional[str], NOT a dictionary.

    Args:
        sha: The commit SHA or prefix.
        owner: GitHub repository owner.
        repo: GitHub repository name.
        token: Optional GitHub token.

    Returns:
        Unified diff string text, or None / simulated diff if unavailable.
    """
    owner = owner or os.getenv("GITHUB_OWNER")
    repo = repo or os.getenv("GITHUB_REPO")
    token = token or os.getenv("GITHUB_TOKEN")

    if owner and repo and sha:
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{sha}"
        headers = {
            "Accept": "application/vnd.github.v3.diff",
            "User-Agent": "Cascade-RCA-Observability",
        }
        if token and token.strip():
            headers["Authorization"] = f"Bearer {token.strip()}"

        try:
            with httpx.Client(timeout=3.5) as client:
                response = client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.text
                logger.warning("GitHub get_commit_diff failed with status %d", response.status_code)
        except Exception as e:
            logger.warning("Failed to fetch commit diff from GitHub: %s", e)

    # Fallback diff simulation for offline demo
    return (
        f"--- a/services/config.py\n"
        f"+++ b/services/config.py\n"
        f"@@ -15,5 +15,5 @@\n"
        f"- TIMEOUT_MS = 5000\n"
        f"+ TIMEOUT_MS = 500\n"
        f"- MAX_RETRIES = 3\n"
        f"+ MAX_RETRIES = 0\n"
    )


def correlate_root_cause_commit(service: str) -> Optional[CommitInfo]:
    """Helper to find the single most relevant commit for a suspected root-cause service.

    Guaranteed not to raise exceptions. Returns None if no commit is found or GitHub
    fails and fallback is disabled.
    """
    if not service:
        return None
    commits = get_recent_commits(service=service, limit=1)
    if commits:
        return commits[0]
    return None
