"""Unit tests for backend/streaming.py.

Tests:
1. Client subscription & unsubscription.
2. Broadcasting events to SSE subscribers.
3. Formatting of SSE messages.
4. Support for up to TWO simultaneous failure injections without overwriting.
5. Specific event emissions (failure_injection, service_state, cascade_propagation, rca_result).
6. SSE endpoint streaming via FastAPI TestClient.
"""

import asyncio
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.streaming import (
    StreamingManager,
    sse_event_generator,
    streaming_manager,
    streaming_router,
)


def test_streaming_subscription_and_broadcast():
    """Verify subscriber receives broadcast messages correctly formatted."""
    async def _run():
        mgr = StreamingManager()
        queue = await mgr.subscribe()

        await mgr.broadcast("test_event", {"key": "value"})

        # Check queue has received the event
        assert not queue.empty()
        msg = await queue.get()
        assert "event: test_event\n" in msg
        assert '"key": "value"' in msg
        assert "\n\n" in msg

        await mgr.unsubscribe(queue)

    asyncio.run(_run())


def test_dual_simultaneous_failure_tracking():
    """Verify system tracks up to 2 simultaneous failures without overwriting."""
    async def _run():
        mgr = StreamingManager()
        mgr.clear_failures()

        # First injection
        await mgr.emit_failure_injection(
            incident_id="INC-001",
            service="payment-service",
            scenario="payment-failure",
        )
        assert len(mgr.active_failures) == 1
        assert mgr.active_failures[0]["service"] == "payment-service"

        # Second injection (independent failure)
        await mgr.emit_failure_injection(
            incident_id="INC-002",
            service="notification-service",
            scenario="notification-failure",
        )
        assert len(mgr.active_failures) == 2
        services = [f["service"] for f in mgr.active_failures]
        assert "payment-service" in services
        assert "notification-service" in services

        # If a third failure occurs, oldest is rotated out to maintain maximum 2
        await mgr.emit_failure_injection(
            incident_id="INC-003",
            service="database",
            scenario="database-latency",
        )
        assert len(mgr.active_failures) == 2
        services_after = [f["service"] for f in mgr.active_failures]
        assert "payment-service" not in services_after
        assert "notification-service" in services_after
        assert "database" in services_after

    asyncio.run(_run())


def test_streaming_event_types():
    """Test emission of service state, cascade propagation, and RCA result."""
    async def _run():
        mgr = StreamingManager()
        queue = await mgr.subscribe()

        # Service state
        await mgr.emit_service_state(
            service="payment-service",
            status="failed",
            latency_ms=850.0,
            status_code=500,
            incident_id="INC-001",
        )
        msg1 = await queue.get()
        assert "event: service_state\n" in msg1
        assert '"status": "failed"' in msg1

        # Cascade propagation
        await mgr.emit_cascade_propagation(
            incident_id="INC-001",
            from_service="payment-service",
            to_service="order-service",
            hop=1,
        )
        msg2 = await queue.get()
        assert "event: cascade_propagation\n" in msg2
        assert '"from_service": "payment-service"' in msg2
        assert '"to_service": "order-service"' in msg2

        # RCA result
        await mgr.emit_rca_result({
            "incident_id": "INC-001",
            "root_cause": {"service": "payment-service", "confidence": 0.91},
        })
        msg3 = await queue.get()
        assert "event: rca_result\n" in msg3
        assert '"payment-service"' in msg3

        await mgr.unsubscribe(queue)

    asyncio.run(_run())


def test_sse_endpoint_fastapi():
    """Test GET /events SSE connection with FastAPI TestClient."""
    app = FastAPI()
    app.include_router(streaming_router)

    client = TestClient(app)
    response = client.get("/events?limit=1")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: connected" in response.text
    assert "active_failures" in response.text


def test_sse_event_payload_structure():
    """Test SSE event payload complies strictly with expected JSON schema:
    {
        "event": "...",
        "timestamp": "...",
        "active_failures": [...],
        "data": {...}
    }
    """
    async def _run():
        mgr = StreamingManager()
        queue = await mgr.subscribe()

        mgr.register_failure("INC-999", "payment-service", "payment-failure")
        await mgr.broadcast("custom_event", {"metric": 42, "flag": True})

        msg = await queue.get()
        assert msg.startswith("event: custom_event\ndata: ")
        
        # Extract JSON from 'data: <json>\n\n'
        data_line = [l for l in msg.split("\n") if l.startswith("data: ")][0]
        payload = json.loads(data_line[6:])

        assert payload["event"] == "custom_event"
        assert "timestamp" in payload
        assert isinstance(payload["active_failures"], list)
        assert len(payload["active_failures"]) == 1
        assert payload["active_failures"][0]["service"] == "payment-service"
        assert payload["data"] == {"metric": 42, "flag": True}

        await mgr.unsubscribe(queue)

    asyncio.run(_run())
