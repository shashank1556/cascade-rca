"""Failure Simulator for Cascade RCA.

Complies with ARCHITECTURE.md and backend/contracts.py.
Developer 2: Backend Telemetry & Failure Simulation.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from backend.contracts import SimulationResponse
from backend.telemetry import (
    store,
    _generate_checkout_trace,
    _generate_notification_trace,
)


def simulate_payment_failure(incident_id: Optional[str] = None) -> SimulationResponse:
    """Simulate payment failure scenario:
    payment-service -> order-service -> api-gateway

    - Registers 'payment_failure' in active incident state (supporting up to 2 simultaneous failures).
    - Preserves any other active failure already injected without overwriting.
    - Injects deterministic cascading failure telemetry.
    """
    now = datetime.now(timezone.utc)
    inc_id = store.register_failure("payment_failure", incident_id=incident_id)

    # Influx of failure traces for the incident
    events = []
    for i in range(5):
        t = now + timedelta(milliseconds=i * 100)
        events.extend(_generate_checkout_trace(base_time=t, is_payment_failed=True))

    store.add_events(events)
    return SimulationResponse(incident_id=inc_id, status="simulated")


def simulate_database_latency(incident_id: Optional[str] = None) -> SimulationResponse:
    """Simulate database latency scenario:
    database -> payment-service -> order-service -> api-gateway

    - Registers 'database_latency' in active incident state (supporting up to 2 simultaneous failures).
    - Preserves any other active failure already injected without overwriting.
    - Injects deterministic cascading timeout telemetry.
    """
    now = datetime.now(timezone.utc)
    inc_id = store.register_failure("database_latency", incident_id=incident_id)

    events = []
    for i in range(5):
        t = now + timedelta(milliseconds=i * 100)
        events.extend(_generate_checkout_trace(base_time=t, is_db_latency=True))

    store.add_events(events)
    return SimulationResponse(incident_id=inc_id, status="simulated")


def simulate_notification_failure(incident_id: Optional[str] = None) -> SimulationResponse:
    """Simulate notification failure scenario:
    notification-service fails in isolation without cascading to unrelated services.

    - Registers 'notification_failure' in active incident state (supporting up to 2 simultaneous failures).
    - Preserves any other active failure already injected without overwriting.
    - Injects deterministic notification failure telemetry.
    """
    now = datetime.now(timezone.utc)
    inc_id = store.register_failure("notification_failure", incident_id=incident_id)

    events = []
    for i in range(5):
        t = now + timedelta(milliseconds=i * 100)
        events.extend(_generate_notification_trace(base_time=t, is_notification_failed=True))

    store.add_events(events)
    return SimulationResponse(incident_id=inc_id, status="simulated")


def reset_simulation(reset_incident_id: bool = True) -> SimulationResponse:
    """Reset all failure injections and clear telemetry back to healthy state."""
    active_id = store.get_active_incident_id() or "INC-000"
    store.reset(reset_incident=reset_incident_id)
    return SimulationResponse(incident_id=active_id, status="reset")


def get_simulation_state() -> Dict[str, object]:
    """Retrieve current simulation state for debugging or status reporting."""
    return {
        "incident_id": store.get_active_incident_id(),
        "active_failures": store.get_active_failures(),
        "total_events_buffered": len(store.get_recent_events(limit=10000)),
    }
