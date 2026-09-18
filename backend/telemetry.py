"""Backend Telemetry Generation and Storage for Cascade RCA.

Complies with ARCHITECTURE.md and backend/contracts.py.
Developer 2: Backend Telemetry & Failure Simulation.
"""

from collections import deque
from datetime import datetime, timezone
import itertools
import threading
from typing import Dict, List, Optional

from backend.contracts import (
    SERVICE_NAMES,
    DEPENDENCIES,
    TelemetryEvent,
)


def _format_timestamp(dt: datetime) -> str:
    """Format datetime as ISO-8601 UTC string with millisecond precision."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class TelemetryStore:
    """Thread-safe in-memory store for telemetry events and incident state."""

    def __init__(self, maxlen: int = 5000):
        self._lock = threading.Lock()
        self._events: deque[TelemetryEvent] = deque(maxlen=maxlen)
        self._active_incident_id: Optional[str] = None
        self._active_failures: List[str] = []
        self._failure_start_times: Dict[str, datetime] = {}
        self._incident_counter: int = 1
        self._trace_counter = itertools.count(1)
        self._span_counter = itertools.count(1)

    def next_trace_id(self) -> str:
        with self._lock:
            return f"trace-{next(self._trace_counter):05d}"

    def next_span_id(self, service: str) -> str:
        with self._lock:
            return f"span-{service}-{next(self._span_counter):06d}"

    def add_event(self, event: TelemetryEvent) -> None:
        with self._lock:
            self._events.append(event)

    def add_events(self, events: List[TelemetryEvent]) -> None:
        with self._lock:
            self._events.extend(events)

    def get_recent_events(
        self, limit: int = 100, service: Optional[str] = None
    ) -> List[TelemetryEvent]:
        with self._lock:
            if service:
                matched = [e for e in self._events if e.service == service]
            else:
                matched = list(self._events)
            # Return the most recent 'limit' events in chronological order
            return matched[-limit:] if limit > 0 else []

    def get_or_create_incident_id(self, requested_id: Optional[str] = None) -> str:
        with self._lock:
            if requested_id:
                self._active_incident_id = requested_id
                return requested_id
            if not self._active_incident_id:
                self._active_incident_id = f"INC-{self._incident_counter:03d}"
                self._incident_counter += 1
            return self._active_incident_id

    def get_active_incident_id(self) -> Optional[str]:
        with self._lock:
            return self._active_incident_id

    def register_failure(self, failure_type: str, incident_id: Optional[str] = None) -> str:
        """Register an active failure injection, supporting up to TWO simultaneous failures.
        
        Does NOT overwrite an existing failure when a second failure is added.
        """
        with self._lock:
            if incident_id:
                self._active_incident_id = incident_id
            elif not self._active_incident_id:
                self._active_incident_id = f"INC-{self._incident_counter:03d}"
                self._incident_counter += 1

            if failure_type not in self._active_failures:
                # Maintain at most two simultaneous active failures
                if len(self._active_failures) >= 2:
                    # Drop the oldest to retain up to two simultaneous failures
                    removed = self._active_failures.pop(0)
                    self._failure_start_times.pop(removed, None)
                self._active_failures.append(failure_type)
                self._failure_start_times[failure_type] = datetime.now(timezone.utc)

            return self._active_incident_id

    def get_active_failures(self) -> List[str]:
        with self._lock:
            return list(self._active_failures)

    def get_failure_start_time(self, failure_type: str) -> Optional[datetime]:
        with self._lock:
            return self._failure_start_times.get(failure_type)

    def clear_active_failures(self) -> None:
        with self._lock:
            self._active_failures.clear()
            self._failure_start_times.clear()

    def reset(self, reset_incident: bool = True) -> None:
        with self._lock:
            self._events.clear()
            self._active_failures.clear()
            self._failure_start_times.clear()
            if reset_incident:
                self._active_incident_id = None


# Singleton store instance for backend state
store = TelemetryStore()


def _generate_checkout_trace(
    base_time: datetime,
    is_payment_failed: bool = False,
    is_db_latency: bool = False,
) -> List[TelemetryEvent]:
    """Generate a distributed trace for the checkout flow:
    api-gateway -> order-service -> payment-service -> database
    """
    from datetime import timedelta

    trace_id = store.next_trace_id()
    events: List[TelemetryEvent] = []

    span_gw = store.next_span_id("api-gateway")
    span_ord = store.next_span_id("order-service")
    span_pay = store.next_span_id("payment-service")
    span_db = store.next_span_id("database")

    if is_payment_failed:
        # Scenario 1: payment-service fails at T0, order-service fails at T0+150ms, api-gateway fails at T0+300ms
        t_pay = base_time
        t_ord = base_time + timedelta(milliseconds=150)
        t_gw = base_time + timedelta(milliseconds=300)
        t_db = base_time - timedelta(milliseconds=50)

        # Database call succeeded before payment failure logic
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t_db),
                service="database",
                trace_id=trace_id,
                span_id=span_db,
                parent_span_id=span_pay,
                latency_ms=25.0,
                status_code=200,
            )
        )
        # Root cause: payment-service fails
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t_pay),
                service="payment-service",
                trace_id=trace_id,
                span_id=span_pay,
                parent_span_id=span_ord,
                latency_ms=850.0,
                status_code=500,
            )
        )
        # Cascade to order-service
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t_ord),
                service="order-service",
                trace_id=trace_id,
                span_id=span_ord,
                parent_span_id=span_gw,
                latency_ms=950.0,
                status_code=500,
            )
        )
        # Cascade to api-gateway
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t_gw),
                service="api-gateway",
                trace_id=trace_id,
                span_id=span_gw,
                parent_span_id=None,
                latency_ms=1100.0,
                status_code=502,
            )
        )

    elif is_db_latency:
        # Scenario 2: database latency spikes at T0, cascading timeouts to payment, order, api-gateway
        t_db = base_time
        t_pay = base_time + timedelta(milliseconds=100)
        t_ord = base_time + timedelta(milliseconds=200)
        t_gw = base_time + timedelta(milliseconds=300)

        # Origin: database latency
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t_db),
                service="database",
                trace_id=trace_id,
                span_id=span_db,
                parent_span_id=span_pay,
                latency_ms=3200.0,
                status_code=504,
            )
        )
        # Cascade to payment-service timeout
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t_pay),
                service="payment-service",
                trace_id=trace_id,
                span_id=span_pay,
                parent_span_id=span_ord,
                latency_ms=3400.0,
                status_code=504,
            )
        )
        # Cascade to order-service timeout
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t_ord),
                service="order-service",
                trace_id=trace_id,
                span_id=span_ord,
                parent_span_id=span_gw,
                latency_ms=3500.0,
                status_code=504,
            )
        )
        # Cascade to api-gateway timeout
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t_gw),
                service="api-gateway",
                trace_id=trace_id,
                span_id=span_gw,
                parent_span_id=None,
                latency_ms=3600.0,
                status_code=504,
            )
        )

    else:
        # Healthy checkout flow
        t0 = base_time
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t0 + timedelta(milliseconds=10)),
                service="database",
                trace_id=trace_id,
                span_id=span_db,
                parent_span_id=span_pay,
                latency_ms=12.0,
                status_code=200,
            )
        )
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t0 + timedelta(milliseconds=20)),
                service="payment-service",
                trace_id=trace_id,
                span_id=span_pay,
                parent_span_id=span_ord,
                latency_ms=25.0,
                status_code=200,
            )
        )
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t0 + timedelta(milliseconds=35)),
                service="order-service",
                trace_id=trace_id,
                span_id=span_ord,
                parent_span_id=span_gw,
                latency_ms=40.0,
                status_code=200,
            )
        )
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t0 + timedelta(milliseconds=50)),
                service="api-gateway",
                trace_id=trace_id,
                span_id=span_gw,
                parent_span_id=None,
                latency_ms=55.0,
                status_code=200,
            )
        )

    return events


def _generate_notification_trace(
    base_time: datetime,
    is_notification_failed: bool = False,
) -> List[TelemetryEvent]:
    """Generate a distributed trace for the notification flow:
    api-gateway -> order-service -> notification-service
    """
    from datetime import timedelta

    trace_id = store.next_trace_id()
    events: List[TelemetryEvent] = []

    span_gw = store.next_span_id("api-gateway")
    span_ord = store.next_span_id("order-service")
    span_notif = store.next_span_id("notification-service")

    if is_notification_failed:
        # Scenario 3: notification-service fails at T0, isolated failure without breaking order/gateway
        t_notif = base_time
        t_ord = base_time + timedelta(milliseconds=50)
        t_gw = base_time + timedelta(milliseconds=80)

        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t_notif),
                service="notification-service",
                trace_id=trace_id,
                span_id=span_notif,
                parent_span_id=span_ord,
                latency_ms=650.0,
                status_code=500,
            )
        )
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t_ord),
                service="order-service",
                trace_id=trace_id,
                span_id=span_ord,
                parent_span_id=span_gw,
                latency_ms=35.0,
                status_code=200,
            )
        )
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(t_gw),
                service="api-gateway",
                trace_id=trace_id,
                span_id=span_gw,
                parent_span_id=None,
                latency_ms=45.0,
                status_code=200,
            )
        )
    else:
        # Healthy notification flow
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(base_time + timedelta(milliseconds=10)),
                service="notification-service",
                trace_id=trace_id,
                span_id=span_notif,
                parent_span_id=span_ord,
                latency_ms=18.0,
                status_code=200,
            )
        )
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(base_time + timedelta(milliseconds=20)),
                service="order-service",
                trace_id=trace_id,
                span_id=span_ord,
                parent_span_id=span_gw,
                latency_ms=28.0,
                status_code=200,
            )
        )
        events.append(
            TelemetryEvent(
                timestamp=_format_timestamp(base_time + timedelta(milliseconds=35)),
                service="api-gateway",
                trace_id=trace_id,
                span_id=span_gw,
                parent_span_id=None,
                latency_ms=40.0,
                status_code=200,
            )
        )

    return events


def _generate_user_service_trace(base_time: datetime) -> List[TelemetryEvent]:
    """Generate a healthy user-service trace: api-gateway -> user-service."""
    from datetime import timedelta

    trace_id = store.next_trace_id()
    span_gw = store.next_span_id("api-gateway")
    span_user = store.next_span_id("user-service")

    return [
        TelemetryEvent(
            timestamp=_format_timestamp(base_time + timedelta(milliseconds=10)),
            service="user-service",
            trace_id=trace_id,
            span_id=span_user,
            parent_span_id=span_gw,
            latency_ms=15.0,
            status_code=200,
        ),
        TelemetryEvent(
            timestamp=_format_timestamp(base_time + timedelta(milliseconds=20)),
            service="api-gateway",
            trace_id=trace_id,
            span_id=span_gw,
            parent_span_id=None,
            latency_ms=25.0,
            status_code=200,
        ),
    ]


def _generate_product_service_trace(base_time: datetime) -> List[TelemetryEvent]:
    """Generate a healthy product-service trace: api-gateway -> product-service."""
    from datetime import timedelta

    trace_id = store.next_trace_id()
    span_gw = store.next_span_id("api-gateway")
    span_prod = store.next_span_id("product-service")

    return [
        TelemetryEvent(
            timestamp=_format_timestamp(base_time + timedelta(milliseconds=10)),
            service="product-service",
            trace_id=trace_id,
            span_id=span_prod,
            parent_span_id=span_gw,
            latency_ms=20.0,
            status_code=200,
        ),
        TelemetryEvent(
            timestamp=_format_timestamp(base_time + timedelta(milliseconds=22)),
            service="api-gateway",
            trace_id=trace_id,
            span_id=span_gw,
            parent_span_id=None,
            latency_ms=30.0,
            status_code=200,
        ),
    ]


# ---------------------------------------------------------------------------
# Locked Public Functions (ARCHITECTURE.md Section 5)
# ---------------------------------------------------------------------------


def generate_telemetry(
    count: int = 10,
    service: Optional[str] = None,
    is_healthy: Optional[bool] = None,
    include_active_failures: bool = True,
) -> List[TelemetryEvent]:
    """Generate synthetic telemetry events adhering to contracts.py.

    - When healthy: generates standard traces across all services with 200 status codes.
    - When active failures exist: generates traces reflecting active failures
      (e.g., payment cascade, database latency, notification failure).
    - Can generate specific service events if `service` is specified.
    - All generated events are appended to the in-memory telemetry store.

    Args:
        count: Number of traces/cycles to generate.
        service: Optional filter to generate events for a single specific service.
        is_healthy: Force healthy generation if True, ignoring active failures.
        include_active_failures: Reflect registered failures in the generated telemetry.

    Returns:
        List of TelemetryEvent objects generated in this cycle.
    """
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    active_failures = [] if is_healthy else (store.get_active_failures() if include_active_failures else [])

    has_payment_failure = "payment_failure" in active_failures
    has_db_latency = "database_latency" in active_failures
    has_notification_failure = "notification_failure" in active_failures

    new_events: List[TelemetryEvent] = []

    # If a specific single service is requested, generate standalone events for it
    if service:
        if service not in SERVICE_NAMES:
            raise ValueError(f"Unknown service '{service}'. Must be one of {SERVICE_NAMES}")

        is_failed = (
            (service == "payment-service" and has_payment_failure)
            or (service == "database" and has_db_latency)
            or (service == "notification-service" and has_notification_failure)
            or (service in ("order-service", "api-gateway") and (has_payment_failure or has_db_latency))
        )
        for i in range(max(1, count)):
            event_time = now + timedelta(milliseconds=i * 20)
            trace_id = store.next_trace_id()
            span_id = store.next_span_id(service)
            status_code = 500 if is_failed and service != "api-gateway" else (502 if is_failed else 200)
            if has_db_latency and service in ("database", "payment-service", "order-service", "api-gateway"):
                status_code = 504
                latency = 3200.0 + (i * 10)
            elif is_failed:
                latency = 850.0
            else:
                latency = 25.0

            new_events.append(
                TelemetryEvent(
                    timestamp=_format_timestamp(event_time),
                    service=service,
                    trace_id=trace_id,
                    span_id=span_id,
                    parent_span_id=None,
                    latency_ms=latency,
                    status_code=status_code,
                )
            )

        store.add_events(new_events)
        return new_events

    # Standard end-to-end trace generation
    for i in range(max(1, count)):
        cycle_time = now + timedelta(milliseconds=i * 100)

        # 1. Checkout trace (affected by payment failure or database latency)
        checkout_events = _generate_checkout_trace(
            base_time=cycle_time,
            is_payment_failed=has_payment_failure,
            is_db_latency=has_db_latency,
        )
        new_events.extend(checkout_events)

        # 2. Notification trace (affected by notification failure)
        notif_events = _generate_notification_trace(
            base_time=cycle_time + timedelta(milliseconds=20),
            is_notification_failed=has_notification_failure,
        )
        new_events.extend(notif_events)

        # 3. User profile trace (healthy baseline)
        user_events = _generate_user_service_trace(
            base_time=cycle_time + timedelta(milliseconds=40)
        )
        new_events.extend(user_events)

        # 4. Product catalog trace (healthy baseline)
        prod_events = _generate_product_service_trace(
            base_time=cycle_time + timedelta(milliseconds=60)
        )
        new_events.extend(prod_events)

    store.add_events(new_events)
    return new_events


def get_recent_telemetry(
    limit: int = 100,
    service: Optional[str] = None,
) -> List[TelemetryEvent]:
    """Retrieve recent telemetry events from the in-memory store.

    Args:
        limit: Maximum number of events to return.
        service: Optional filter by service name.

    Returns:
        List of TelemetryEvent objects matching the criteria.
    """
    return store.get_recent_events(limit=limit, service=service)
