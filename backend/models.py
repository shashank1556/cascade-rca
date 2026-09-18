"""Internal models for Cascade RCA backend.

Preserves and re-exports all canonical contracts from backend/contracts.py.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

# Re-export locked canonical contracts from contracts.py
from backend.contracts import (
    TelemetryEvent,
    RootCause,
    TimelineEvent,
    CommitInfo,
    RCAResult,
    SimulationResponse,
    SERVICE_NAMES,
    DEPENDENCIES,
)


class GraphNode(BaseModel):
    id: str
    label: str
    service_type: str = "service"
    status: str = "healthy"  # healthy, warning, critical, root_cause


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    status: str = "normal"  # normal, failing


class GraphData(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class IncidentRecord(BaseModel):
    incident_id: str
    status: str = "active"  # active, resolved
    scenarios: List[str] = Field(default_factory=list)  # e.g. ["payment_failure", "notification_failure"]
    injected_services: List[str] = Field(default_factory=list)
    created_at: str
    telemetry: List[TelemetryEvent] = Field(default_factory=list)
    rca_result: Optional[RCAResult] = None


class HealthStatus(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    services_count: int = len(SERVICE_NAMES)
    dependencies_count: int = len(DEPENDENCIES)
