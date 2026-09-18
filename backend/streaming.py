"""Server-Sent Events (SSE) streaming engine for Cascade RCA.

Streams real-time updates for:
- failure injection
- service state changes
- cascade propagation
- RCA results

Supports up to TWO simultaneous failure injections without overwriting
independent incident information. Maintains REST fallback compatibility.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class StreamingManager:
    """Manages SSE client subscriptions and event broadcasting."""

    def __init__(self) -> None:
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._active_failures: List[Dict[str, Any]] = []

    @property
    def active_failures(self) -> List[Dict[str, Any]]:
        return list(self._active_failures)

    def register_failure(self, incident_id: str, service: str, scenario: str) -> None:
        """Register a failure injection.

        Preserves up to 2 simultaneous active failure events without overwriting.
        """
        # Remove any existing failure for the same service if present
        self._active_failures = [f for f in self._active_failures if f.get("service") != service]
        
        # Keep maximum 2 simultaneous failures
        if len(self._active_failures) >= 2:
            self._active_failures.pop(0)

        self._active_failures.append({
            "incident_id": incident_id,
            "service": service,
            "scenario": scenario,
            "injected_at": datetime.now(timezone.utc).isoformat(),
        })

    def clear_failures(self) -> None:
        """Reset active failures."""
        self._active_failures.clear()

    async def subscribe(self) -> asyncio.Queue:
        """Register a new SSE client subscriber queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)
        logger.info("SSE client connected. Total subscribers: %d", len(self._subscribers))
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Unregister an SSE client subscriber queue."""
        async with self._lock:
            self._subscribers.discard(queue)
        logger.info("SSE client disconnected. Total subscribers: %d", len(self._subscribers))

    async def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcast an event to all connected SSE clients."""
        payload = {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_failures": self.active_failures,
            "data": data,
        }
        message = f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

        async with self._lock:
            subscribers_snapshot = list(self._subscribers)

        for queue in subscribers_snapshot:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full; dropping message")
            except Exception as e:
                logger.warning("Error putting message to subscriber: %s", e)

    def broadcast_sync(self, event_type: str, data: Dict[str, Any]) -> None:
        """Thread-safe synchronous helper to broadcast from synchronous handlers."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast(event_type, data))
        except RuntimeError:
            pass  # No running event loop

    # Specific event helpers
    async def emit_failure_injection(
        self, incident_id: str, service: str, scenario: str
    ) -> None:
        """Emit failure injection event."""
        self.register_failure(incident_id=incident_id, service=service, scenario=scenario)
        await self.broadcast(
            "failure_injection",
            {
                "incident_id": incident_id,
                "service": service,
                "scenario": scenario,
                "total_active_failures": len(self.active_failures),
                "active_failures": self.active_failures,
            },
        )

    async def emit_service_state(
        self,
        service: str,
        status: str,
        latency_ms: float = 20.0,
        status_code: int = 200,
        incident_id: Optional[str] = None,
    ) -> None:
        """Emit service state change event (e.g. healthy, degraded, failed)."""
        await self.broadcast(
            "service_state",
            {
                "service": service,
                "status": status,
                "latency_ms": latency_ms,
                "status_code": status_code,
                "incident_id": incident_id,
            },
        )

    async def emit_cascade_propagation(
        self,
        incident_id: str,
        from_service: str,
        to_service: str,
        hop: int,
        delay_ms: float = 250.0,
    ) -> None:
        """Emit cascade propagation step along the service graph."""
        await self.broadcast(
            "cascade_propagation",
            {
                "incident_id": incident_id,
                "from_service": from_service,
                "to_service": to_service,
                "hop": hop,
                "delay_ms": delay_ms,
            },
        )

    async def emit_rca_result(self, rca_result_dict: Dict[str, Any]) -> None:
        """Emit completed RCA result."""
        await self.broadcast("rca_result", rca_result_dict)


# Global singleton instance
streaming_manager = StreamingManager()


async def sse_event_generator(max_events: Optional[int] = None) -> AsyncGenerator[str, None]:
    """Async generator for FastAPI EventSourceResponse / StreamingResponse."""
    queue = await streaming_manager.subscribe()
    yielded_count = 0
    try:
        # Initial greeting and state synchronization event
        initial_payload = {
            "event": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_failures": streaming_manager.active_failures,
            "data": {
                "message": "Connected to Cascade RCA live event stream",
                "active_failures_count": len(streaming_manager.active_failures),
            },
        }
        yield f"event: connected\ndata: {json.dumps(initial_payload)}\n\n"
        yielded_count += 1
        if max_events is not None and yielded_count >= max_events:
            return

        while True:
            try:
                # Wait for next event or send heartbeat every 15 seconds
                message = await asyncio.wait_for(queue.get(), timeout=15.0)
                yield message
                yielded_count += 1
                if max_events is not None and yielded_count >= max_events:
                    return
            except asyncio.TimeoutError:
                heartbeat = {
                    "event": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "active_failures": streaming_manager.active_failures,
                }
                yield f": heartbeat\nevent: heartbeat\ndata: {json.dumps(heartbeat)}\n\n"
                yielded_count += 1
                if max_events is not None and yielded_count >= max_events:
                    return
    finally:
        await streaming_manager.unsubscribe(queue)


# FastAPI APIRouter for integration
try:
    from fastapi import APIRouter, Query
    from fastapi.responses import StreamingResponse

    streaming_router = APIRouter(tags=["Streaming"])

    @streaming_router.get("/events")
    async def sse_events(limit: Optional[int] = Query(None, description="Optional max events limit for testing")):
        """Server-Sent Events endpoint streaming real-time cascade and RCA updates."""
        return StreamingResponse(
            sse_event_generator(max_events=limit),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
except ImportError:
    streaming_router = None  # type: ignore
