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
    return simulate_payment_failure()


@app.post("/simulate/database-latency", response_model=SimulationResponse)
def run_database_latency() -> SimulationResponse:
    """Inject database latency failure (propagates: database -> payment-service -> order-service -> api-gateway)."""
    return simulate_database_latency()


@app.post("/simulate/notification-failure", response_model=SimulationResponse)
def run_notification_failure() -> SimulationResponse:
    """Inject isolated notification service failure."""
    return simulate_notification_failure()


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
    return result


@app.post("/simulate/reset")
def reset_system() -> Dict[str, str]:
    """Reset system state, telemetry, and active incidents back to healthy."""
    reset_simulation()
    clear_telemetry()
    return {"status": "healthy", "message": "System state reset successfully"}


@app.get("/events")
async def sse_events():
    """Server-Sent Events endpoint streaming real-time graph and incident updates."""
    async def event_generator():
        while True:
            active = get_active_incident()
            inc_id = active.incident_id if active else "HEALTHY"
            graph = get_graph()
            
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "incident_id": inc_id,
                "has_active_incident": active is not None,
                "scenarios": active.scenarios if active else [],
                "graph": graph.model_dump(),
            }
            yield {"event": "telemetry_update", "data": json.dumps(payload)}
            await asyncio.sleep(1.0)

    return EventSourceResponse(event_generator())
