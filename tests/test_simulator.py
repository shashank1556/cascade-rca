"""Tests for backend/simulator.py in Cascade RCA."""

from datetime import datetime
import pytest

from backend.contracts import SimulationResponse, TelemetryEvent
from backend.simulator import (
    simulate_payment_failure,
    simulate_database_latency,
    simulate_notification_failure,
    reset_simulation,
    get_simulation_state,
)
from backend.telemetry import (
    generate_telemetry,
    get_recent_telemetry,
    store,
)


@pytest.fixture(autouse=True)
def clean_simulation():
    """Reset simulation before and after each test."""
    reset_simulation(reset_incident_id=True)
    yield
    reset_simulation(reset_incident_id=True)


def test_payment_failure_scenario():
    """Verify Scenario 1: Payment failure cascade.
    payment-service (root cause) -> order-service -> api-gateway.
    Database remains healthy.
    """
    res = simulate_payment_failure()
    assert isinstance(res, SimulationResponse)
    assert res.incident_id.startswith("INC-")
    assert res.status == "simulated"

    events = get_recent_telemetry(limit=100)
    assert len(events) > 0

    # Group by trace_id to inspect complete traces
    traces = {}
    for e in events:
        traces.setdefault(e.trace_id, []).append(e)

    # Find a checkout trace
    checkout_trace = None
    for trace_events in traces.values():
        services = {e.service for e in trace_events}
        if "payment-service" in services and "order-service" in services:
            checkout_trace = trace_events
            break

    assert checkout_trace is not None

    service_map = {e.service: e for e in checkout_trace}

    # 1. Root cause: payment-service
    pay_event = service_map["payment-service"]
    assert pay_event.status_code == 500
    assert pay_event.latency_ms >= 800

    # 2. Cascade: order-service
    ord_event = service_map["order-service"]
    assert ord_event.status_code == 500

    # 3. Cascade: api-gateway
    gw_event = service_map["api-gateway"]
    assert gw_event.status_code == 502

    # 4. Database is healthy
    db_event = service_map["database"]
    assert db_event.status_code == 200

    # 5. Temporal onset: payment fails first, then order, then gateway
    t_pay = datetime.fromisoformat(pay_event.timestamp.replace("Z", "+00:00"))
    t_ord = datetime.fromisoformat(ord_event.timestamp.replace("Z", "+00:00"))
    t_gw = datetime.fromisoformat(gw_event.timestamp.replace("Z", "+00:00"))
    assert t_pay < t_ord < t_gw


def test_database_latency_scenario():
    """Verify Scenario 2: Database latency cascade.
    database (origin) -> payment-service -> order-service -> api-gateway.
    """
    res = simulate_database_latency()
    assert isinstance(res, SimulationResponse)
    assert res.incident_id.startswith("INC-")

    events = get_recent_telemetry(limit=100)
    traces = {}
    for e in events:
        traces.setdefault(e.trace_id, []).append(e)

    checkout_trace = None
    for trace_events in traces.values():
        services = {e.service for e in trace_events}
        if "database" in services and "payment-service" in services:
            checkout_trace = trace_events
            break

    assert checkout_trace is not None
    service_map = {e.service: e for e in checkout_trace}

    # 1. Origin: database has severe latency
    db_event = service_map["database"]
    assert db_event.latency_ms >= 3000

    # 2. Payment-service times out
    pay_event = service_map["payment-service"]
    assert pay_event.status_code == 504
    assert pay_event.latency_ms >= 3000

    # 3. Order-service times out
    ord_event = service_map["order-service"]
    assert ord_event.status_code == 504

    # 4. API gateway times out
    gw_event = service_map["api-gateway"]
    assert gw_event.status_code == 504

    # 5. Temporal onset: database latency begins first
    t_db = datetime.fromisoformat(db_event.timestamp.replace("Z", "+00:00"))
    t_pay = datetime.fromisoformat(pay_event.timestamp.replace("Z", "+00:00"))
    t_ord = datetime.fromisoformat(ord_event.timestamp.replace("Z", "+00:00"))
    t_gw = datetime.fromisoformat(gw_event.timestamp.replace("Z", "+00:00"))
    assert t_db < t_pay < t_ord < t_gw


def test_notification_failure_scenario():
    """Verify Scenario 3: Notification failure isolation.
    notification-service fails without propagating to unrelated services.
    """
    res = simulate_notification_failure()
    assert isinstance(res, SimulationResponse)

    events = get_recent_telemetry(limit=100)
    traces = {}
    for e in events:
        traces.setdefault(e.trace_id, []).append(e)

    notif_trace = None
    for trace_events in traces.values():
        services = {e.service for e in trace_events}
        if "notification-service" in services:
            notif_trace = trace_events
            break

    assert notif_trace is not None
    service_map = {e.service: e for e in notif_trace}

    # Notification service fails
    assert service_map["notification-service"].status_code == 500

    # Order and gateway handled notification failure gracefully (remain 200)
    assert service_map["order-service"].status_code == 200
    assert service_map["api-gateway"].status_code == 200


def test_payment_and_notification_simultaneous():
    """Verify simultaneous injection of payment failure and notification failure.
    Both failures remain active, incident ID is preserved, and telemetry preserves both.
    """
    res1 = simulate_payment_failure()
    incident_id_1 = res1.incident_id
    assert "payment_failure" in store.get_active_failures()

    res2 = simulate_notification_failure()
    incident_id_2 = res2.incident_id

    # The incident ID is preserved across both injections
    assert incident_id_1 == incident_id_2

    # BOTH failures are active at the same time
    active_failures = store.get_active_failures()
    assert len(active_failures) == 2
    assert "payment_failure" in active_failures
    assert "notification_failure" in active_failures

    # Both failure events are preserved in the telemetry buffer
    events = get_recent_telemetry(limit=200)
    payment_failures = [
        e for e in events if e.service == "payment-service" and e.status_code == 500
    ]
    notif_failures = [
        e for e in events if e.service == "notification-service" and e.status_code == 500
    ]
    assert len(payment_failures) > 0, "Payment failure events must be preserved"
    assert len(notif_failures) > 0, "Notification failure events must be preserved"

    # Further ongoing telemetry generation also reflects BOTH active failures
    new_events = generate_telemetry(count=3)
    new_services_failed = {e.service for e in new_events if e.status_code >= 500}
    assert "payment-service" in new_services_failed
    assert "notification-service" in new_services_failed


def test_payment_and_database_simultaneous():
    """Verify simultaneous injection of payment failure and database latency.
    Both failures are preserved, both traces are generated, and neither overwrites the other.
    """
    res1 = simulate_payment_failure()
    incident_id_1 = res1.incident_id

    res2 = simulate_database_latency()
    incident_id_2 = res2.incident_id

    # Same incident preserved
    assert incident_id_1 == incident_id_2

    # Both active simultaneously
    active_failures = store.get_active_failures()
    assert len(active_failures) == 2
    assert "payment_failure" in active_failures
    assert "database_latency" in active_failures

    # Telemetry contains traces for both failure modes
    events = get_recent_telemetry(limit=200)
    traces = {}
    for e in events:
        traces.setdefault(e.trace_id, []).append(e)

    has_payment_cascade = False
    has_db_latency_cascade = False

    for trace_events in traces.values():
        service_map = {e.service: e for e in trace_events}
        if "payment-service" in service_map and "database" in service_map:
            pay_e = service_map["payment-service"]
            db_e = service_map["database"]

            # In payment cascade: payment is 500, database is 200 (healthy)
            if pay_e.status_code == 500 and db_e.status_code == 200:
                has_payment_cascade = True

            # In db latency cascade: database has high latency and 504
            if db_e.status_code == 504 and db_e.latency_ms >= 3000:
                has_db_latency_cascade = True

    assert has_payment_cascade, "Payment failure cascade trace must be present"
    assert has_db_latency_cascade, "Database latency cascade trace must be present"

    # Subsequent generate_telemetry also produces both failure traces
    new_events = generate_telemetry(count=2)
    new_traces = {}
    for e in new_events:
        new_traces.setdefault(e.trace_id, []).append(e)

    new_has_payment = any(
        any(e.service == "payment-service" and e.status_code == 500 for e in t)
        and any(e.service == "database" and e.status_code == 200 for e in t)
        for t in new_traces.values()
    )
    new_has_db_latency = any(
        any(e.service == "database" and e.status_code == 504 for e in t)
        for t in new_traces.values()
    )
    assert new_has_payment, "Ongoing telemetry must generate payment cascade trace"
    assert new_has_db_latency, "Ongoing telemetry must generate database latency trace"


def test_database_and_notification_simultaneous():
    """Verify simultaneous injection of database latency and notification failure.
    Both are active, preserved, and reflected in recent and ongoing telemetry.
    """
    res1 = simulate_database_latency()
    res2 = simulate_notification_failure()
    assert res1.incident_id == res2.incident_id

    active = store.get_active_failures()
    assert len(active) == 2
    assert "database_latency" in active
    assert "notification_failure" in active

    events = get_recent_telemetry(limit=200)
    has_db_latency = any(e.service == "database" and e.status_code == 504 for e in events)
    has_notif_failure = any(e.service == "notification-service" and e.status_code == 500 for e in events)
    assert has_db_latency, "Database latency telemetry must be present"
    assert has_notif_failure, "Notification failure telemetry must be present"


def test_third_failure_rejected_and_first_two_remain_active():
    """Verify that when two failures are already active, a third failure injection
    is rejected with a clear error and the first two failures remain active.
    """
    simulate_payment_failure()
    simulate_notification_failure()
    assert store.get_active_failures() == ["payment_failure", "notification_failure"]

    # Attempting to inject a third failure must raise a clear RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        simulate_database_latency()

    assert "maximum of two simultaneous failures already active" in str(exc_info.value)

    # Verify that the first two failures REMAIN ACTIVE and untouched
    active = store.get_active_failures()
    assert len(active) == 2
    assert active == ["payment_failure", "notification_failure"]
    assert "database_latency" not in active


def test_reinjecting_existing_active_failure_allowed():
    """Verify that re-injecting a failure that is already among the active failures
    does not error and does not count as a third failure.
    """
    simulate_payment_failure()
    simulate_notification_failure()

    # Re-inject payment failure (already active)
    res = simulate_payment_failure()
    assert res.status == "simulated"
    assert store.get_active_failures() == ["payment_failure", "notification_failure"]


def test_reset_simulation():
    """Verify reset returns system to clean healthy state."""
    simulate_payment_failure()
    simulate_notification_failure()
    assert len(store.get_active_failures()) == 2

    res = reset_simulation()
    assert res.status == "reset"
    assert len(store.get_active_failures()) == 0
    assert len(get_recent_telemetry(limit=100)) == 0

    # New telemetry is completely healthy
    events = generate_telemetry(count=2)
    assert all(e.status_code == 200 for e in events)


def test_simultaneous_failures_distinguishable():
    """Verify that during simultaneous failure injections, individual traces
    clearly isolate the cascading path from the independent failure path.
    """
    simulate_payment_failure()
    simulate_notification_failure()

    events = get_recent_telemetry(limit=200)
    traces = {}
    for e in events:
        traces.setdefault(e.trace_id, []).append(e)

    payment_cascade_traces = []
    notification_failure_traces = []

    for trace_id, trace_events in traces.items():
        failed_services = {e.service for e in trace_events if e.status_code >= 500}

        # Payment cascade trace: payment failed, order failed, gateway failed
        if "payment-service" in failed_services and "order-service" in failed_services:
            # Notification-service must NOT be failed in this trace
            assert "notification-service" not in failed_services
            payment_cascade_traces.append(trace_events)

        # Notification failure trace: notification failed
        if "notification-service" in failed_services:
            # Payment-service must NOT be failed in this trace
            assert "payment-service" not in failed_services
            notification_failure_traces.append(trace_events)

    assert len(payment_cascade_traces) > 0, "Must have distinct payment cascade traces"
    assert len(notification_failure_traces) > 0, "Must have distinct notification failure traces"

