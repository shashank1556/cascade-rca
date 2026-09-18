"""Tests for backend/telemetry.py in Cascade RCA."""

from datetime import datetime
import pytest

from backend.contracts import SERVICE_NAMES, TelemetryEvent
from backend.telemetry import (
    generate_telemetry,
    get_recent_telemetry,
    store,
)


@pytest.fixture(autouse=True)
def clean_store():
    """Reset the telemetry store before and after each test."""
    store.reset(reset_incident=True)
    yield
    store.reset(reset_incident=True)


def test_healthy_telemetry_generation():
    """Verify healthy telemetry generation conforms strictly to contracts."""
    events = generate_telemetry(count=2, is_healthy=True)
    assert len(events) > 0

    services_observed = set()
    for event in events:
        # Pydantic model validation
        assert isinstance(event, TelemetryEvent)
        assert event.service in SERVICE_NAMES
        assert event.status_code == 200
        assert event.latency_ms > 0
        assert event.trace_id.startswith("trace-")
        assert event.span_id.startswith("span-")
        services_observed.add(event.service)

        # ISO-8601 UTC timestamp format validation
        assert event.timestamp.endswith("Z")
        # Should parse with datetime.fromisoformat
        parsed = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
        assert parsed is not None

    # Check that root spans (api-gateway) have parent_span_id=None
    gw_events = [e for e in events if e.service == "api-gateway"]
    assert len(gw_events) > 0
    assert all(e.parent_span_id is None for e in gw_events)

    # Check child spans have a parent_span_id
    child_events = [e for e in events if e.service != "api-gateway"]
    assert len(child_events) > 0
    assert all(e.parent_span_id is not None for e in child_events)


def test_get_recent_telemetry_limit_and_filter():
    """Verify limit and service filtering on get_recent_telemetry."""
    generate_telemetry(count=5, is_healthy=True)

    all_recent = get_recent_telemetry(limit=10)
    assert len(all_recent) == 10

    user_events = get_recent_telemetry(limit=50, service="user-service")
    assert len(user_events) > 0
    assert all(e.service == "user-service" for e in user_events)


def test_single_service_telemetry_generation():
    """Verify generating telemetry specifically for a single service."""
    events = generate_telemetry(count=4, service="order-service", is_healthy=True)
    assert len(events) == 4
    assert all(e.service == "order-service" for e in events)
    assert all(e.status_code == 200 for e in events)


def test_invalid_service_name_raises():
    """Verify unknown service names are rejected."""
    with pytest.raises(ValueError):
        generate_telemetry(count=1, service="invalid-service-xyz")
