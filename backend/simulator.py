"""Failure simulation engine for Cascade RCA.

Locked public functions:
- simulate_payment_failure(...)
- simulate_database_latency(...)
- simulate_notification_failure(...)

Supports up to two simultaneous failure injections within an incident session.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import uuid

from backend.contracts import SimulationResponse, TelemetryEvent
from backend.models import IncidentRecord
from backend.telemetry import generate_telemetry


# In-memory store of incidents
_INCIDENTS: Dict[str, IncidentRecord] = {}
_ACTIVE_INCIDENT_ID: Optional[str] = None


def get_current_incident_id() -> str:
    """Get active incident ID or generate a new one."""
    global _ACTIVE_INCIDENT_ID
    if not _ACTIVE_INCIDENT_ID:
        _ACTIVE_INCIDENT_ID = f"INC-{uuid.uuid4().hex[:6].upper()}"
    return _ACTIVE_INCIDENT_ID


def get_incident(incident_id: str) -> Optional[IncidentRecord]:
    """Retrieve an incident record by ID."""
    return _INCIDENTS.get(incident_id)


def get_active_incident() -> Optional[IncidentRecord]:
    """Retrieve the currently active incident."""
    if _ACTIVE_INCIDENT_ID and _ACTIVE_INCIDENT_ID in _INCIDENTS:
        return _INCIDENTS[_ACTIVE_INCIDENT_ID]
    return None


def reset_simulation() -> None:
    """Reset all active simulations and incidents back to a healthy state."""
    global _ACTIVE_INCIDENT_ID, _INCIDENTS
    _ACTIVE_INCIDENT_ID = None
    _INCIDENTS.clear()


def _get_or_create_incident(incident_id: Optional[str] = None) -> IncidentRecord:
    global _ACTIVE_INCIDENT_ID
    inc_id = incident_id or get_current_incident_id()
    _ACTIVE_INCIDENT_ID = inc_id

    if inc_id not in _INCIDENTS:
        _INCIDENTS[inc_id] = IncidentRecord(
            incident_id=inc_id,
            status="active",
            scenarios=[],
            injected_services=[],
            created_at=datetime.now(timezone.utc).isoformat(),
            telemetry=[],
        )
    return _INCIDENTS[inc_id]


def simulate_payment_failure(incident_id: Optional[str] = None) -> SimulationResponse:
    """Simulate payment failure scenario.

    Propagation:
    payment-service (root) -> order-service -> api-gateway
    """
    incident = _get_or_create_incident(incident_id)
    if "payment_failure" not in incident.scenarios:
        incident.scenarios.append("payment_failure")
    if "payment-service" not in incident.injected_services:
        incident.injected_services.append("payment-service")

    base_time = datetime.now(timezone.utc)
    trace_base = f"trace-pay-{uuid.uuid4().hex[:6]}"

    # 1. Root: payment-service fails first at T+0s
    t0 = (base_time + timedelta(seconds=0)).isoformat()
    span_db = f"span-db-{uuid.uuid4().hex[:4]}"
    span_pay = f"span-pay-{uuid.uuid4().hex[:4]}"
    span_ord = f"span-ord-{uuid.uuid4().hex[:4]}"
    span_gw = f"span-gw-{uuid.uuid4().hex[:4]}"

    # Baseline healthy calls to database
    e_db = generate_telemetry(
        service="database",
        status_code=200,
        latency_ms=18.5,
        trace_id=trace_base,
        span_id=span_db,
        parent_span_id=span_pay,
        timestamp=t0,
    )
    incident.telemetry.append(e_db)

    # payment-service error (Root Cause)
    e_pay = generate_telemetry(
        service="payment-service",
        status_code=500,
        latency_ms=850.0,
        trace_id=trace_base,
        span_id=span_pay,
        parent_span_id=span_ord,
        timestamp=t0,
    )
    incident.telemetry.append(e_pay)

    # 2. Propagation: order-service fails shortly after at T+1.5s
    t1 = (base_time + timedelta(seconds=1.5)).isoformat()
    e_ord = generate_telemetry(
        service="order-service",
        status_code=500,
        latency_ms=920.0,
        trace_id=trace_base,
        span_id=span_ord,
        parent_span_id=span_gw,
        timestamp=t1,
    )
    incident.telemetry.append(e_ord)

    # 3. Propagation: api-gateway fails at T+3.0s
    t2 = (base_time + timedelta(seconds=3.0)).isoformat()
    e_gw = generate_telemetry(
        service="api-gateway",
        status_code=502,
        latency_ms=980.0,
        trace_id=trace_base,
        span_id=span_gw,
        parent_span_id=None,
        timestamp=t2,
    )
    incident.telemetry.append(e_gw)

    # Background healthy telemetry for unaffected services
    for svc in ["user-service", "product-service"]:
        incident.telemetry.append(
            generate_telemetry(service=svc, status_code=200, latency_ms=25.0, timestamp=t0)
        )

    return SimulationResponse(incident_id=incident.incident_id, status="active")


def simulate_database_latency(incident_id: Optional[str] = None) -> SimulationResponse:
    """Simulate database latency scenario.

    Propagation:
    database (root) -> payment-service -> order-service -> api-gateway
    """
    incident = _get_or_create_incident(incident_id)
    if "database_latency" not in incident.scenarios:
        incident.scenarios.append("database_latency")
    if "database" not in incident.injected_services:
        incident.injected_services.append("database")

    base_time = datetime.now(timezone.utc)
    trace_base = f"trace-db-{uuid.uuid4().hex[:6]}"

    span_db = f"span-db-{uuid.uuid4().hex[:4]}"
    span_pay = f"span-pay-{uuid.uuid4().hex[:4]}"
    span_ord = f"span-ord-{uuid.uuid4().hex[:4]}"
    span_gw = f"span-gw-{uuid.uuid4().hex[:4]}"

    # 1. Root: database latency spike at T+0s
    t0 = (base_time + timedelta(seconds=0)).isoformat()
    e_db = generate_telemetry(
        service="database",
        status_code=200,
        latency_ms=2850.0,  # Critical latency anomaly
        trace_id=trace_base,
        span_id=span_db,
        parent_span_id=span_pay,
        timestamp=t0,
    )
    incident.telemetry.append(e_db)

    # 2. Propagation: payment-service times out on database at T+1.2s
    t1 = (base_time + timedelta(seconds=1.2)).isoformat()
    e_pay = generate_telemetry(
        service="payment-service",
        status_code=504,
        latency_ms=2900.0,
        trace_id=trace_base,
        span_id=span_pay,
        parent_span_id=span_ord,
        timestamp=t1,
    )
    incident.telemetry.append(e_pay)

    # 3. Propagation: order-service times out at T+2.5s
    t2 = (base_time + timedelta(seconds=2.5)).isoformat()
    e_ord = generate_telemetry(
        service="order-service",
        status_code=504,
        latency_ms=2950.0,
        trace_id=trace_base,
        span_id=span_ord,
        parent_span_id=span_gw,
        timestamp=t2,
    )
    incident.telemetry.append(e_ord)

    # 4. Propagation: api-gateway times out at T+3.8s
    t3 = (base_time + timedelta(seconds=3.8)).isoformat()
    e_gw = generate_telemetry(
        service="api-gateway",
        status_code=504,
        latency_ms=3050.0,
        trace_id=trace_base,
        span_id=span_gw,
        parent_span_id=None,
        timestamp=t3,
    )
    incident.telemetry.append(e_gw)

    return SimulationResponse(incident_id=incident.incident_id, status="active")


def simulate_notification_failure(incident_id: Optional[str] = None) -> SimulationResponse:
    """Simulate notification failure scenario.

    Isolated failure on notification-service.
    Does NOT propagate to order-service or api-gateway.
    """
    incident = _get_or_create_incident(incident_id)
    if "notification_failure" not in incident.scenarios:
        incident.scenarios.append("notification_failure")
    if "notification-service" not in incident.injected_services:
        incident.injected_services.append("notification-service")

    base_time = datetime.now(timezone.utc)
    trace_base = f"trace-notif-{uuid.uuid4().hex[:6]}"

    t0 = (base_time + timedelta(seconds=0)).isoformat()
    span_notif = f"span-notif-{uuid.uuid4().hex[:4]}"
    span_ord = f"span-ord-{uuid.uuid4().hex[:4]}"

    # notification-service fails
    e_notif = generate_telemetry(
        service="notification-service",
        status_code=500,
        latency_ms=620.0,
        trace_id=trace_base,
        span_id=span_notif,
        parent_span_id=span_ord,
        timestamp=t0,
    )
    incident.telemetry.append(e_notif)

    # Unaffected services produce healthy telemetry
    for svc in ["api-gateway", "order-service", "payment-service", "database"]:
        incident.telemetry.append(
            generate_telemetry(service=svc, status_code=200, latency_ms=22.0, timestamp=t0)
        )

    return SimulationResponse(incident_id=incident.incident_id, status="active")
