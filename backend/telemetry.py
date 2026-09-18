"""Telemetry generator and store for Cascade RCA.

Locked public functions:
- generate_telemetry(...)
- get_recent_telemetry(...)
"""

from datetime import datetime, timezone
import uuid
from typing import List, Optional
from backend.contracts import TelemetryEvent, SERVICE_NAMES


# In-memory circular telemetry buffer
_TELEMETRY_BUFFER: List[TelemetryEvent] = []
_MAX_BUFFER_SIZE = 1000


def generate_telemetry(
    service: str,
    status_code: int = 200,
    latency_ms: float = 20.0,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> TelemetryEvent:
    """Generate and store an OTel-compatible TelemetryEvent."""
    if service not in SERVICE_NAMES:
        raise ValueError(f"Unknown service: {service}. Must be one of {SERVICE_NAMES}")

    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    if trace_id is None:
        trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    if span_id is None:
        span_id = f"span-{uuid.uuid4().hex[:8]}"

    event = TelemetryEvent(
        timestamp=timestamp,
        service=service,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        latency_ms=float(latency_ms),
        status_code=int(status_code),
    )

    _TELEMETRY_BUFFER.append(event)
    if len(_TELEMETRY_BUFFER) > _MAX_BUFFER_SIZE:
        _TELEMETRY_BUFFER.pop(0)

    return event


def get_recent_telemetry(
    service: Optional[str] = None,
    limit: int = 100,
) -> List[TelemetryEvent]:
    """Retrieve recent telemetry events, optionally filtered by service."""
    if service:
        filtered = [e for e in _TELEMETRY_BUFFER if e.service == service]
        return filtered[-limit:]
    return _TELEMETRY_BUFFER[-limit:]


def clear_telemetry() -> None:
    """Clear in-memory telemetry buffer."""
    global _TELEMETRY_BUFFER
    _TELEMETRY_BUFFER = []
