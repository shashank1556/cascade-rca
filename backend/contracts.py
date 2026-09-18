"""Shared contracts for Cascade RCA. LOCKED."""

from typing import List, Optional
from pydantic import BaseModel, Field


class TelemetryEvent(BaseModel):
    timestamp: str
    service: str
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    latency_ms: float
    status_code: int


class RootCause(BaseModel):
    service: str
    confidence: float = Field(ge=0.0, le=1.0)


class TimelineEvent(BaseModel):
    timestamp: str
    service: str
    event: str


class CommitInfo(BaseModel):
    sha: str
    message: str
    url: str
    author: str


class RCAResult(BaseModel):
    incident_id: str
    status: str
    root_cause: RootCause
    affected_services: List[str]
    timeline: List[TimelineEvent]
    commit: Optional[CommitInfo] = None
    explanation: str = ""


class SimulationResponse(BaseModel):
    incident_id: str
    status: str


SERVICE_NAMES = [
    "api-gateway",
    "user-service",
    "order-service",
    "product-service",
    "payment-service",
    "notification-service",
    "database",
]

DEPENDENCIES = [
    ("api-gateway", "user-service"),
    ("api-gateway", "order-service"),
    ("api-gateway", "product-service"),
    ("order-service", "payment-service"),
    ("order-service", "notification-service"),
    ("payment-service", "database"),
]
