"""Unit tests for backend/github_service.py.

Tests:
1. GitHub commit retrieval with mock REST API.
2. Commit diff retrieval with mock REST API.
3. Fallback behavior when GitHub is unavailable or unconfigured.
4. Compliance with locked CommitInfo contract.
5. Service-specific correlation.
"""

from unittest.mock import MagicMock, patch
import httpx
import pytest

from backend.contracts import CommitInfo
from backend.github_service import (
    FALLBACK_COMMITS,
    correlate_root_cause_commit,
    get_commit_diff,
    get_recent_commits,
)


def test_fallback_commits_contract():
    """Verify fallback commits strictly comply with CommitInfo contract."""
    for service, commit in FALLBACK_COMMITS.items():
        assert isinstance(commit, CommitInfo)
        assert commit.sha != ""
        assert commit.message != ""
        assert commit.url.startswith("http")
        assert commit.author != ""


def test_get_recent_commits_fallback_when_unconfigured():
    """When GITHUB_OWNER/REPO are unset, fallback commits are returned gracefully."""
    with patch.dict("os.environ", {}, clear=True):
        commits = get_recent_commits(service="payment-service", use_fallback=True)
        assert len(commits) == 1
        assert commits[0].sha == FALLBACK_COMMITS["payment-service"].sha
        assert "stripe" in commits[0].message.lower() or "payment" in commits[0].message.lower()


def test_get_recent_commits_without_fallback_when_unconfigured():
    """When fallback is disabled and GitHub unconfigured, returns empty list without error."""
    with patch.dict("os.environ", {}, clear=True):
        commits = get_recent_commits(service="payment-service", use_fallback=False)
        assert commits == []


def test_get_recent_commits_success_mock():
    """Test successful response parsing from GitHub REST API."""
    mock_response_data = [
        {
            "sha": "abc1234567890",
            "commit": {
                "message": "fix(payment): resolve connection leak in gateway client",
                "author": {"name": "Alice Engineer"},
            },
            "html_url": "https://github.com/example/repo/commit/abc1234",
        },
        {
            "sha": "def9876543210",
            "commit": {
                "message": "docs: update API documentation",
                "author": {"name": "Bob Writer"},
            },
            "html_url": "https://github.com/example/repo/commit/def9876",
        },
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response_data

    with patch("httpx.Client.get", return_value=mock_resp):
        commits = get_recent_commits(
            service="payment-service",
            owner="example",
            repo="repo",
            token="ghp_testtoken",
            use_fallback=False,
        )
        assert len(commits) == 1
        assert commits[0].sha == "abc1234"
        assert commits[0].author == "Alice Engineer"
        assert "payment" in commits[0].message.lower()


def test_get_recent_commits_network_failure_handling():
    """Verify system does not crash on network errors and falls back safely."""
    with patch("httpx.Client.get", side_effect=httpx.ConnectError("Network unreachable")):
        # With fallback enabled
        commits_fb = get_recent_commits(
            service="database",
            owner="example",
            repo="repo",
            use_fallback=True,
        )
        assert len(commits_fb) == 1
        assert commits_fb[0].sha == FALLBACK_COMMITS["database"].sha

        # With fallback disabled
        commits_no_fb = get_recent_commits(
            service="database",
            owner="example",
            repo="repo",
            use_fallback=False,
        )
        assert commits_no_fb == []


def test_get_commit_diff_success_mock():
    """Test retrieving diff from GitHub API."""
    mock_diff_data = {
        "sha": "abc1234",
        "commit": {
            "message": "fix: update timeout config",
            "author": {"name": "Alice"},
        },
        "html_url": "https://github.com/example/repo/commit/abc1234",
        "stats": {"total": 10, "additions": 8, "deletions": 2},
        "files": [
            {
                "filename": "services/payment/config.py",
                "status": "modified",
                "additions": 8,
                "deletions": 2,
                "patch": "@@ -1,2 +1,8 @@",
            }
        ],
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_diff_data

    with patch("httpx.Client.get", return_value=mock_resp):
        diff = get_commit_diff("abc1234", owner="example", repo="repo", token="ghp_test")
        assert diff is not None
        assert diff["sha"] == "abc1234"
        assert len(diff["files"]) == 1
        assert diff["files"][0]["filename"] == "services/payment/config.py"


def test_get_commit_diff_fallback_offline():
    """Test diff fallback for offline demo."""
    diff = get_commit_diff(FALLBACK_COMMITS["payment-service"].sha)
    assert diff is not None
    assert diff["sha"] == FALLBACK_COMMITS["payment-service"].sha
    assert len(diff["files"]) > 0


def test_correlate_root_cause_commit():
    """Test single commit correlation helper."""
    commit = correlate_root_cause_commit("payment-service")
    assert commit is not None
    assert isinstance(commit, CommitInfo)
    assert commit.sha != ""

    unknown = correlate_root_cause_commit("")
    assert unknown is None
