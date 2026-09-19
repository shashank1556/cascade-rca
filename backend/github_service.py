"""GitHub REST API correlation service for Cascade RCA.

Provides:
- Recent commit retrieval from GitHub
- Service-aware commit relevance filtering
- Real commit diff retrieval
- Graceful fallback when GitHub is unavailable
- No GitHub token exposure to the frontend
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


# ---------------------------------------------------------------------------
# FALLBACK DATA
# ---------------------------------------------------------------------------
# Used ONLY when GitHub is unavailable, unconfigured, or rate-limited.
# These are not returned when the real GitHub API successfully responds
# but has no relevant commit.
MOCK_COMMITS: Dict[str, List[CommitInfo]] = {
    "payment-service": [
        CommitInfo(
            sha="a8f3b1c",
            message=(
                "fix(payment): update Stripe gateway timeout "
                "threshold and retry policy"
            ),
            url="https://github.com/shashank1556/cascade-rca/commit/a8f3b1c",
            author="alex.dev@echelon.io",
        ),
        CommitInfo(
            sha="b4e2c90",
            message=(
                "refactor(payment): migrate payment authorization "
                "handlers to v2"
            ),
            url="https://github.com/shashank1556/cascade-rca/commit/b4e2c90",
            author="sarah.m@echelon.io",
        ),
    ],
    "database": [
        CommitInfo(
            sha="d7c1e54",
            message=(
                "perf(db): modify Postgres connection pool "
                "max_connections and idle timeouts"
            ),
            url="https://github.com/shashank1556/cascade-rca/commit/d7c1e54",
            author="dave.dba@echelon.io",
        ),
        CommitInfo(
            sha="e9a0f32",
            message=(
                "migration: add composite index on "
                "transactions(order_id, created_at)"
            ),
            url="https://github.com/shashank1556/cascade-rca/commit/e9a0f32",
            author="dave.dba@echelon.io",
        ),
    ],
    "notification-service": [
        CommitInfo(
            sha="f2b8a71",
            message=(
                "fix(notif): update Twilio SMS delivery "
                "retry backoff queue"
            ),
            url="https://github.com/shashank1556/cascade-rca/commit/f2b8a71",
            author="jordan.k@echelon.io",
        )
    ],
    "order-service": [
        CommitInfo(
            sha="c3d8e91",
            message=(
                "feat(order): add idempotency key check "
                "on checkout requests"
            ),
            url="https://github.com/shashank1556/cascade-rca/commit/c3d8e91",
            author="chris.t@echelon.io",
        )
    ],
    "api-gateway": [
        CommitInfo(
            sha="1e84c50",
            message=(
                "chore(gateway): update ratelimit "
                "middleware route mappings"
            ),
            url="https://github.com/shashank1556/cascade-rca/commit/1e84c50",
            author="platform-team@echelon.io",
        )
    ],
}

# Preserve compatibility with existing code/tests.
FALLBACK_COMMITS = MOCK_COMMITS


# ---------------------------------------------------------------------------
# SERVICE KEYWORDS
# ---------------------------------------------------------------------------

SERVICE_KEYWORDS: Dict[str, List[str]] = {
    "payment-service": [
        "payment",
        "payments",
        "stripe",
        "gateway",
        "transaction",
        "pay",
        "billing",
    ],
    "database": [
        "database",
        "db",
        "postgres",
        "sql",
        "query",
        "pool",
        "vacuum",
        "migration",
    ],
    "notification-service": [
        "notification",
        "notify",
        "email",
        "sms",
        "queue",
        "push",
        "alert",
    ],
    "order-service": [
        "order",
        "orders",
        "checkout",
        "fulfillment",
    ],
    "api-gateway": [
        "gateway",
        "proxy",
        "routing",
        "ingress",
        "ratelimit",
    ],
    "user-service": [
        "user",
        "auth",
        "session",
        "profile",
    ],
    "product-service": [
        "product",
        "catalog",
        "inventory",
        "item",
    ],
}


# ---------------------------------------------------------------------------
# HEADERS
# ---------------------------------------------------------------------------

def _get_headers(token: Optional[str] = None) -> Dict[str, str]:
    """Construct safe GitHub API headers without exposing the token."""

    token = token or os.getenv("GITHUB_TOKEN")

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Cascade-RCA-Observability",
    }

    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"

    return headers


# ---------------------------------------------------------------------------
# RECENT COMMITS
# ---------------------------------------------------------------------------
def get_recent_commits(
    service: Optional[str] = None,
    limit: int = 10,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    use_fallback: bool = True,
) -> List[CommitInfo]:
    """Retrieve recent real GitHub commits and correlate them to a service.

    A commit is considered relevant when either:
    1. Its commit message contains a service keyword, OR
    2. One of its changed file paths contains a service-specific keyword.

    If GitHub successfully responds but no relevant commit exists, return [].
    Fallback data is used only when GitHub is unavailable/unconfigured/failed.
    """

    owner = owner or os.getenv("GITHUB_OWNER")
    repo = repo or os.getenv("GITHUB_REPO")
    token = token or os.getenv("GITHUB_TOKEN")

    if owner and repo:
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits"
        headers = _get_headers(token)

        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(
                    url,
                    headers=headers,
                    params={
                       "per_page": min(max(limit, 1) * 2, 30),
                       "sha": os.getenv("GITHUB_BRANCH", "shashank-rca"),
                    },
                )

                if response.status_code == 200:
                    commits_data = response.json()

                    if isinstance(commits_data, list):
                        commits: List[CommitInfo] = []

                        for item in commits_data:
                            sha_full = item.get("sha", "")
                            sha = sha_full[:7]

                            commit_obj = item.get("commit", {}) or {}

                            message = (
                                commit_obj.get("message", "")
                                .splitlines()[0]
                                .strip()
                            )

                            html_url = item.get(
                                "html_url",
                                f"https://github.com/{owner}/{repo}/commit/{sha_full}",
                            )

                            author_obj = (
                                commit_obj.get("author", {})
                                or item.get("author", {})
                                or {}
                            )

                            author = (
                                author_obj.get("name")
                                or (item.get("author") or {}).get("login")
                                or "unknown"
                            )

                            commits.append(
                                CommitInfo(
                                    sha=sha,
                                    message=message,
                                    url=html_url,
                                    author=author,
                                )
                            )

                        # --------------------------------------------------
                        # SERVICE-SPECIFIC RELEVANCE
                        # --------------------------------------------------

                        if service:
                            keywords = SERVICE_KEYWORDS.get(
                                service,
                                [service],
                            )

                            def message_relevance(commit: CommitInfo) -> int:
                                message_lower = commit.message.lower()

                                return sum(
                                    1
                                    for keyword in keywords
                                    if keyword.lower() in message_lower
                                )

                            # First filter by commit message.
                            message_matches = [
                                commit
                                for commit in commits
                                if message_relevance(commit) > 0
                            ]

                            # --------------------------------------------------
                            # FILE-PATH CORRELATION
                            # --------------------------------------------------
                            #
                            # A generic commit such as:
                            #     "Create contracts.py"
                            #
                            # must NOT be treated as a payment change merely
                            # because it is in backend/.
                            #
                            # We therefore inspect the actual files changed
                            # by each commit and look for service-specific
                            # path tokens.
                            #

                            path_matches: List[tuple[int, CommitInfo]] = []

                            for commit in commits:
                                try:
                                    detail_url = (
                                        f"{GITHUB_API_BASE}/repos/"
                                        f"{owner}/{repo}/commits/{commit.sha}"
                                    )

                                    detail_response = client.get(
                                        detail_url,
                                        headers=headers,
                                    )

                                    if detail_response.status_code != 200:
                                        continue

                                    detail_data = detail_response.json()
                                    changed_files = detail_data.get("files", [])

                                    path_score = 0

                                    for changed_file in changed_files:
                                        filename = str(
                                            changed_file.get("filename", "")
                                        ).lower()

                                        for keyword in keywords:
                                            keyword_lower = keyword.lower()

                                            # Normalize common service naming:
                                            # payment-service -> payment
                                            # notification-service -> notification
                                            # etc.
                                            service_token = keyword_lower.replace(
                                                "-service", ""
                                            )

                                            if service_token and service_token in filename:
                                                path_score += 1

                                    if path_score > 0:
                                        path_matches.append(
                                            (path_score, commit)
                                        )

                                except Exception as exc:
                                    logger.warning(
                                        "Failed to inspect GitHub commit %s: %s",
                                        commit.sha,
                                        exc,
                                    )

                            # --------------------------------------------------
                            # COMBINE MESSAGE + FILE-PATH EVIDENCE
                            # --------------------------------------------------

                            relevant: Dict[str, tuple[int, CommitInfo]] = {}

                            for commit in message_matches:
                                score = 10 + message_relevance(commit)
                                relevant[commit.sha] = (score, commit)

                            for path_score, commit in path_matches:
                                score = 20 + path_score

                                existing = relevant.get(commit.sha)

                                if existing:
                                    score = max(score, existing[0])

                                relevant[commit.sha] = (score, commit)

                            ranked = sorted(
                                relevant.values(),
                                key=lambda item: item[0],
                                reverse=True,
                            )

                            # IMPORTANT:
                            # If GitHub worked successfully but no genuinely
                            # relevant commit exists, return [].
                            return [
                                commit
                                for _, commit in ranked[:limit]
                            ]

                        # No service filter requested.
                        return commits[:limit]

                else:
                    logger.warning(
                        "GitHub API responded with status %d: %s",
                        response.status_code,
                        response.text[:300],
                    )

        except Exception as exc:
            logger.warning(
                "Error communicating with GitHub API: %s",
                exc,
            )

    # --------------------------------------------------
    # FALLBACK
    # --------------------------------------------------

    # Only use fallback when GitHub is unavailable,
    # unconfigured, or failed.
    if use_fallback:
        if service and service in MOCK_COMMITS:
            return MOCK_COMMITS[service][:limit]

        if not service:
            all_commits: List[CommitInfo] = []

            for commit_list in MOCK_COMMITS.values():
                all_commits.extend(commit_list)

            return all_commits[:limit]

    return []

# ---------------------------------------------------------------------------
# COMMIT DIFF
# ---------------------------------------------------------------------------

def get_commit_diff(
    sha: str,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[str]:
    """Retrieve the REAL unified diff for a GitHub commit.

    Returns:
        Real unified diff string if successful.
        None if GitHub is unavailable or the commit cannot be retrieved.

    IMPORTANT:
        This function never invents a fake diff.
    """

    owner = owner or os.getenv("GITHUB_OWNER")
    repo = repo or os.getenv("GITHUB_REPO")
    token = token or os.getenv("GITHUB_TOKEN")

    if not owner or not repo or not sha:
        return None

    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{sha}"

    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "User-Agent": "Cascade-RCA-Observability",
    }

    if token and token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                url,
                headers=headers,
            )

        if response.status_code == 200:
            return response.text

        logger.warning(
            "GitHub get_commit_diff failed with status %d",
            response.status_code,
        )

    except Exception as exc:
        logger.warning(
            "Failed to fetch commit diff from GitHub: %s",
            exc,
        )

    # NEVER return a simulated diff.
    return None


# ---------------------------------------------------------------------------
# ROOT-CAUSE COMMIT CORRELATION
# ---------------------------------------------------------------------------

def correlate_root_cause_commit(
    service: str,
) -> Optional[CommitInfo]:
    """Find the most relevant REAL commit for a suspected root cause.

    Returns None when:
    - service is empty
    - GitHub has no relevant commit
    - GitHub is unavailable and fallback data is unavailable
    """

    if not service:
        return None

    commits = get_recent_commits(
        service=service,
        limit=1,
    )

    if commits:
        return commits[0]

    return None