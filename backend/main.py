"""Cascade RCA - FastAPI Integration and Main Entry Point.

Locked API endpoints:
- POST /simulate/payment-failure
- POST /simulate/database-latency
- POST /simulate/notification-failure
- GET /graph
- GET /incident/{incident_id}
- GET /rca/{incident_id}
- GET /health
"""

import asyncio
from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from backend.contracts import (
    DEPENDENCIES,
    RCAResult,
    SERVICE_NAMES,
    SimulationResponse,
)
from backend.models import (
    GraphData,
    GraphEdge,
    GraphNode,
    HealthStatus,
    IncidentRecord,
)
from backend.rca_engine import analyze_incident, build_service_graph, detect_cascade
from backend.simulator import (
    get_active_incident,
    get_incident,
    reset_simulation,
    simulate_database_latency,
    simulate_notification_failure,
    simulate_payment_failure,
)
from backend.telemetry import get_recent_telemetry, clear_telemetry

from fastapi.responses import StreamingResponse
from backend.streaming import sse_event_generator, streaming_manager

app = FastAPI(
    title="Cascade RCA API",
    description="Causal Root-Cause Analysis for Cascading Microservice Failures",
    version="1.0.0",
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthStatus)
def get_health() -> HealthStatus:
    """Health check endpoint."""
    return HealthStatus(
        status="ok",
        version="1.0.0",
        services_count=len(SERVICE_NAMES),
        dependencies_count=len(DEPENDENCIES),
    )


@app.get("/graph", response_model=GraphData)
def get_graph() -> GraphData:
    """Retrieve service topology graph with real-time operational status."""
    g = build_service_graph()
    telemetry = get_recent_telemetry(limit=100)
    cascade_info = detect_cascade(telemetry, g)
    failing = set(cascade_info.get("failing_services", []))
    propagation_edges = set(cascade_info.get("propagation_edges", []))

    # Check for root cause if failures exist
    root_service = None
    if failing:
        active_inc = get_active_incident()
        inc_id = active_inc.incident_id if active_inc else "CURRENT"
        rca_res = analyze_incident(inc_id, telemetry, g)
        root_service = rca_res.root_cause.service

    nodes: List[GraphNode] = []
    for s in SERVICE_NAMES:
        if s == root_service:
            status = "root_cause"
        elif s in failing:
            status = "critical"
        else:
            status = "healthy"

        nodes.append(GraphNode(id=s, label=s, service_type="service", status=status))

    edges: List[GraphEdge] = []
    for caller, callee in DEPENDENCIES:
        edge_id = f"{caller}->{callee}"
        # Edge status is failing if callee failed and propagated to caller
        edge_status = "failing" if (callee, caller) in propagation_edges or (caller in failing and callee in failing) else "normal"
        edges.append(GraphEdge(id=edge_id, source=caller, target=callee, status=edge_status))

    return GraphData(nodes=nodes, edges=edges)


@app.post("/simulate/payment-failure", response_model=SimulationResponse)
def run_payment_failure() -> SimulationResponse:
    """Inject payment service failure (propagates: payment-service -> order-service -> api-gateway)."""
    res = simulate_payment_failure()
    streaming_manager.register_failure(res.incident_id, "payment-service", "payment-failure")
    streaming_manager.broadcast_sync(
        "failure_injection",
        {"incident_id": res.incident_id, "service": "payment-service", "scenario": "payment-failure"},
    )
    streaming_manager.broadcast_sync(
        "service_state",
        {"service": "payment-service", "status": "root_cause", "incident_id": res.incident_id},
    )
    streaming_manager.broadcast_sync(
        "cascade_propagation",
        {"incident_id": res.incident_id, "from_service": "payment-service", "to_service": "order-service", "hop": 1},
    )
    streaming_manager.broadcast_sync(
        "cascade_propagation",
        {"incident_id": res.incident_id, "from_service": "order-service", "to_service": "api-gateway", "hop": 2},
    )
    return res


@app.post("/simulate/database-latency", response_model=SimulationResponse)
def run_database_latency() -> SimulationResponse:
    """Inject database latency failure (propagates: database -> payment-service -> order-service -> api-gateway)."""
    res = simulate_database_latency()
    streaming_manager.register_failure(res.incident_id, "database", "database-latency")
    streaming_manager.broadcast_sync(
        "failure_injection",
        {"incident_id": res.incident_id, "service": "database", "scenario": "database-latency"},
    )
    streaming_manager.broadcast_sync(
        "service_state",
        {"service": "database", "status": "root_cause", "incident_id": res.incident_id},
    )
    streaming_manager.broadcast_sync(
        "cascade_propagation",
        {"incident_id": res.incident_id, "from_service": "database", "to_service": "payment-service", "hop": 1},
    )
    streaming_manager.broadcast_sync(
        "cascade_propagation",
        {"incident_id": res.incident_id, "from_service": "payment-service", "to_service": "order-service", "hop": 2},
    )
    streaming_manager.broadcast_sync(
        "cascade_propagation",
        {"incident_id": res.incident_id, "from_service": "order-service", "to_service": "api-gateway", "hop": 3},
    )
    return res


@app.post("/simulate/notification-failure", response_model=SimulationResponse)
def run_notification_failure() -> SimulationResponse:
    """Inject isolated notification service failure."""
    res = simulate_notification_failure()
    streaming_manager.register_failure(res.incident_id, "notification-service", "notification-failure")
    streaming_manager.broadcast_sync(
        "failure_injection",
        {"incident_id": res.incident_id, "service": "notification-service", "scenario": "notification-failure"},
    )
    streaming_manager.broadcast_sync(
        "service_state",
        {"service": "notification-service", "status": "critical", "incident_id": res.incident_id},
    )
    return res


@app.get("/incident/{incident_id}", response_model=IncidentRecord)
def get_incident_by_id(incident_id: str) -> IncidentRecord:
    """Retrieve details and telemetry for a specific incident."""
    record = get_incident(incident_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return record


@app.get("/rca/{incident_id}", response_model=RCAResult)
def get_rca(incident_id: str) -> RCAResult:
    """Perform causal root cause analysis for an incident."""
    record = get_incident(incident_id)
    telemetry = record.telemetry if record and record.telemetry else get_recent_telemetry(limit=200)

    result = analyze_incident(incident_id, telemetry)
    if record:
        record.rca_result = result
    streaming_manager.broadcast_sync("rca_result", result.model_dump())
    return result


@app.post("/simulate/reset")
def reset_system() -> Dict[str, str]:
    """Reset system state, telemetry, and active incidents back to healthy."""
    reset_simulation()
    clear_telemetry()
    streaming_manager.clear_failures()
    streaming_manager.broadcast_sync("service_state", {"status": "healthy", "all_services": True})
    return {"status": "healthy", "message": "System state reset successfully"}


@app.get("/events")
async def sse_events(limit: Optional[int] = None):
    """Server-Sent Events endpoint streaming real-time graph, cascade, and RCA updates."""
    return StreamingResponse(
        sse_event_generator(max_events=limit),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
