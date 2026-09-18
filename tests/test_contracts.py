"""Test contracts compliance for Cascade RCA."""

import pytest
from backend.contracts import (
    DEPENDENCIES,
    SERVICE_NAMES,
    CommitInfo,
    RCAResult,
    RootCause,
    SimulationResponse,
    TelemetryEvent,
    TimelineEvent,
)


def test_service_names():
    """Verify exact 7 service names exist."""
    expected = [
        "api-gateway",
        "user-service",
        "order-service",
        "product-service",
        "payment-service",
        "notification-service",
        "database",
    ]
    assert SERVICE_NAMES == expected


def test_dependencies():
    """Verify exact 6 dependencies exist in call direction."""
    expected = [
        ("api-gateway", "user-service"),
        ("api-gateway", "order-service"),
        ("api-gateway", "product-service"),
        ("order-service", "payment-service"),
        ("order-service", "notification-service"),
        ("payment-service", "database"),
    ]
    assert DEPENDENCIES == expected


def test_rca_result_serialization():
    """Verify RCAResult serializes with all required canonical fields."""
    result = RCAResult(
        incident_id="INC-001",
        status="resolved",
        root_cause=RootCause(service="payment-service", confidence=0.91),
        affected_services=["order-service", "api-gateway"],
        timeline=[
            TimelineEvent(
                timestamp="2026-09-18T10:00:01Z",
                service="payment-service",
                event="Failure injected",
            )
        ],
        commit=CommitInfo(
            sha="8f31c2a",
            message="fix(payment): timeout",
            url="https://github.com/...",
            author="alex",
        ),
        explanation="Payment failed and cascaded.",
    )

    data = result.model_dump()
    assert data["incident_id"] == "INC-001"
    assert data["status"] == "resolved"
    assert data["root_cause"]["service"] == "payment-service"
    assert data["root_cause"]["confidence"] == 0.91
    assert data["affected_services"] == ["order-service", "api-gateway"]
    assert len(data["timeline"]) == 1
    assert data["commit"]["sha"] == "8f31c2a"
    assert data["explanation"] != ""
