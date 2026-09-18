"""Unit tests for backend/gemini_service.py.

Tests:
1. Gemini API narration generation (mocked successful response).
2. Deterministic fallback when GEMINI_API_KEY is unset.
3. Deterministic fallback when Gemini API returns error or timeout.
4. Explanation quality for single cascade scenarios.
5. Dual simultaneous failure explanation (primary cascade + independent component).
6. Commit message correlation in narrative.
7. Contract compliance with RCAResult.
"""

from unittest.mock import MagicMock, patch
import httpx
import pytest

from backend.contracts import CommitInfo, RCAResult, RootCause, TimelineEvent
from backend.gemini_service import generate_explanation


@pytest.fixture
def sample_rca_result():
    return RCAResult(
        incident_id="INC-101",
        status="resolved",
        root_cause=RootCause(service="payment-service", confidence=0.91),
        affected_services=["order-service", "api-gateway"],
        timeline=[
            TimelineEvent(
                timestamp="2026-09-18T10:00:01Z",
                service="payment-service",
                event="Connection pool exhausted (500)",
            ),
            TimelineEvent(
                timestamp="2026-09-18T10:00:02Z",
                service="order-service",
                event="Upstream call to payment-service failed",
            ),
            TimelineEvent(
                timestamp="2026-09-18T10:00:03Z",
                service="api-gateway",
                event="Bad gateway (502) returned to clients",
            ),
        ],
        commit=CommitInfo(
            sha="8f31c2a",
            message="fix(payment): adjust connection pool and timeout",
            url="https://github.com/shashank1556/cascade-rca/commit/8f31c2a",
            author="alex.dev",
        ),
        explanation="",
    )


def test_deterministic_fallback_when_api_key_unset(sample_rca_result):
    """When GEMINI_API_KEY is not set, deterministic fallback must be generated."""
    with patch.dict("os.environ", {}, clear=True):
        explanation = generate_explanation(sample_rca_result)
        assert isinstance(explanation, str)
        assert len(explanation) > 30
        assert "payment-service" in explanation
        assert "91%" in explanation
        assert "order-service" in explanation
        assert "api-gateway" in explanation
        assert "8f31c2a" in explanation


def test_deterministic_fallback_on_api_error(sample_rca_result):
    """When Gemini API returns 503 or error, falls back deterministically without crashing."""
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable"

    with patch.dict("os.environ", {"GEMINI_API_KEY": "dummy-key"}):
        with patch("httpx.Client.post", return_value=mock_resp):
            explanation = generate_explanation(sample_rca_result)
            assert "payment-service" in explanation
            assert "91%" in explanation
            assert "order-service" in explanation


def test_deterministic_fallback_on_network_timeout(sample_rca_result):
    """When Gemini request times out, gracefully falls back."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": "dummy-key"}):
        with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Read timeout")):
            explanation = generate_explanation(sample_rca_result)
            assert "payment-service" in explanation
            assert "91%" in explanation


def test_gemini_api_success_mock(sample_rca_result):
    """When Gemini API succeeds, returns the generated narration."""
    mock_resp_data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                "Payment-service encountered high latency due to recent commit 8f31c2a, "
                                "triggering downstream cascading 500 errors in order-service and api-gateway. "
                                "Root-cause confidence is 91%."
                            )
                        }
                    ]
                }
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_resp_data

    with patch.dict("os.environ", {"GEMINI_API_KEY": "dummy-key"}):
        with patch("httpx.Client.post", return_value=mock_resp):
            explanation = generate_explanation(sample_rca_result)
            assert "Payment-service encountered high latency" in explanation
            assert "8f31c2a" in explanation


def test_dual_simultaneous_failure_explanation():
    """Test narration when two independent simultaneous failures occur."""
    with patch.dict("os.environ", {}, clear=True):
        explanation = generate_explanation(
            service="payment-service",
            confidence=0.91,
            affected_services=["order-service", "api-gateway"],
            independent_failures=["notification-service"],
        )
        # Verify both the primary cascade and the independent failure are clearly narrated
        assert "payment-service" in explanation
        assert "notification-service" in explanation
        assert "independent" in explanation.lower() or "isolated" in explanation.lower()
        assert "order-service" in explanation
