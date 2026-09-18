"""GitHub REST API integration for Cascade RCA. LOCKED.

Correlates suspected root-cause microservices with recent repository commits
and diffs using the GitHub REST API. Gracefully degrades when GitHub is
unavailable, unconfigured, or rate-limited.
"""

import logging
import os
from typing import Any, Dict, List, Optional
import httpx
from dotenv import load_dotenv

from backend.contracts import CommitInfo

load_dotenv()

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"

# Realistic curated mock commits for hackathon demo scenarios when
# GitHub API is unconfigured or unreachable.
FALLBACK_COMMITS: Dict[str, CommitInfo] = {
    "payment-service": CommitInfo(
        sha="8f31c2a",
        message="fix(payment): adjust connection pool and timeout parameters for stripe gateway",
        url="https://github.com/shashank1556/cascade-rca/commit/8f31c2a",
        author="alex.dev",
    ),
    "database": CommitInfo(
        sha="4c91d0e",
        message="perf(db): migration 0042 adding index on transactions table and vacuum settings",
        url="https://github.com/shashank1556/cascade-rca/commit/4c91d0e",
        author="data-infra",
    ),
    "notification-service": CommitInfo(
        sha="7b22e11",
        message="feat(notifications): switch email provider webhook retry policy to exponential backoff",
        url="https://github.com/shashank1556/cascade-rca/commit/7b22e11",
        author="sarah.m",
    ),
    "order-service": CommitInfo(
        sha="3a11b9f",
        message="refactor(order): streamline checkout fulfillment dispatch queue",
        url="https://github.com/shashank1556/cascade-rca/commit/3a11b9f",
        author="jordan.k",
    ),
    "api-gateway": CommitInfo(
        sha="1e84c50",
        message="chore(gateway): update ratelimit middleware route mappings",
        url="https://github.com/shashank1556/cascade-rca/commit/1e84c50",
        author="platform-team",
    ),
}

# Service keyword mapping for intelligent commit message matching
SERVICE_KEYWORDS: Dict[str, List[str]] = {
    "payment-service": ["payment", "stripe", "billing", "checkout", "transaction", "pay"],
    "database": ["db", "database", "postgres", "sql", "migration", "query", "pool"],
    "notification-service": ["notification", "notify", "email", "sms", "push", "alert"],
    "order-service": ["order", "orders", "checkout", "fulfillment"],
    "api-gateway": ["gateway", "proxy", "routing", "ingress", "ratelimit"],
    "user-service": ["user", "auth", "session", "profile"],
    "product-service": ["product", "catalog", "inventory", "item"],
}


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
        service: Optional service name to correlate with commit messages/files.
        limit: Maximum number of commits to retrieve.
        owner: GitHub repository owner (defaults to GITHUB_OWNER env var).
        repo: GitHub repository name (defaults to GITHUB_REPO env var).
        token: Optional GitHub token (defaults to GITHUB_TOKEN env var).
        use_fallback: Whether to return curated mock commits if GitHub is unavailable.

    Returns:
        List of CommitInfo objects matching the contract.
    """
    owner = owner or os.getenv("GITHUB_OWNER")
    repo = repo or os.getenv("GITHUB_REPO")
    token = token or os.getenv("GITHUB_TOKEN")

    if not owner or not repo:
        logger.info("GitHub owner/repo not configured. Utilizing fallback commits if enabled.")
        if use_fallback and service and service in FALLBACK_COMMITS:
            return [FALLBACK_COMMITS[service]]
        elif use_fallback and not service:
            return list(FALLBACK_COMMITS.values())[:limit]
        return []

    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits"
    headers = _get_headers(token)

    try:
        with httpx.Client(timeout=4.0) as client:
            response = client.get(url, headers=headers, params={"per_page": min(limit * 2, 30)})

            if response.status_code != 200:
                logger.warning(
                    "GitHub API responded with status %d: %s",
                    response.status_code,
                    response.text[:100],
                )
                if use_fallback and service and service in FALLBACK_COMMITS:
                    return [FALLBACK_COMMITS[service]]
                return []

            commits_data = response.json()
            if not isinstance(commits_data, list):
                return []

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

            if not results and service and use_fallback and service in FALLBACK_COMMITS:
                return [FALLBACK_COMMITS[service]]

            return results

    except Exception as e:
        logger.error("Error communicating with GitHub API: %s", e)
        if use_fallback and service and service in FALLBACK_COMMITS:
            return [FALLBACK_COMMITS[service]]
        return []


def get_commit_diff(
    sha: str,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Retrieve commit diff and metadata for a specific commit SHA.

    Args:
        sha: The commit SHA or prefix.
        owner: GitHub repository owner.
        repo: GitHub repository name.
        token: Optional GitHub token.

    Returns:
        Dictionary containing diff metadata and changed files, or None if unavailable.
    """
    owner = owner or os.getenv("GITHUB_OWNER")
    repo = repo or os.getenv("GITHUB_REPO")
    token = token or os.getenv("GITHUB_TOKEN")

    if not owner or not repo or not sha:
        # Fallback diff simulation for offline demo
        for s_name, fb_commit in FALLBACK_COMMITS.items():
            if fb_commit.sha.startswith(sha) or sha.startswith(fb_commit.sha):
                return {
                    "sha": fb_commit.sha,
                    "message": fb_commit.message,
                    "author": fb_commit.author,
                    "url": fb_commit.url,
                    "files": [
                        {
                            "filename": f"services/{s_name}/config.py",
                            "status": "modified",
                            "additions": 14,
                            "deletions": 5,
                            "patch": "@@ -12,5 +12,14 @@\n- TIMEOUT = 5.0\n+ TIMEOUT = 0.8\n+ POOL_SIZE = 10",
                        }
                    ],
                }
        return None

    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{sha}"
    headers = _get_headers(token)

    try:
        with httpx.Client(timeout=4.0) as client:
            response = client.get(url, headers=headers)
            if response.status_code != 200:
                logger.warning("GitHub get_commit_diff failed with status %d", response.status_code)
                return None

            data = response.json()
            return {
                "sha": data.get("sha", sha)[:7],
                "message": (data.get("commit", {}).get("message", "")).split("\n")[0],
                "author": (data.get("commit", {}).get("author", {}) or {}).get("name", "unknown"),
                "url": data.get("html_url", ""),
                "stats": data.get("stats", {}),
                "files": [
                    {
                        "filename": f.get("filename"),
                        "status": f.get("status"),
                        "additions": f.get("additions"),
                        "deletions": f.get("deletions"),
                        "patch": f.get("patch", "")[:400] if f.get("patch") else None,
                    }
                    for f in data.get("files", [])[:5]
                ],
            }
    except Exception as e:
        logger.error("Failed to fetch commit diff from GitHub: %s", e)
        return None


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
