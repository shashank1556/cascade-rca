/**
 * Cascade RCA Frontend API Client & Contracts.
 * Strictly complies with backend/contracts.py and ARCHITECTURE.md.
 * Authoritative source of truth is the backend FastAPI server.
 */

export const API_BASE =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export interface TelemetryEvent {
  timestamp: string;
  service: string;
  trace_id: string;
  span_id: string;
  parent_span_id?: string | null;
  latency_ms: float;
  status_code: number;
}

export type float = number;

export interface RootCause {
  service: string;
  confidence: number;
}

export interface TimelineEvent {
  timestamp: string;
  service: string;
  event: string;
}

export interface CommitInfo {
  sha: string;
  message: string;
  url: string;
  author: string;
}

export interface RCAResult {
  incident_id: string;
  status: string;
  root_cause: RootCause;
  affected_services: string[];
  timeline: TimelineEvent[];
  commit: CommitInfo | null;
  explanation: string;
}

export interface SimulationResponse {
  incident_id: string;
  status: string;
}

export interface GraphNode {
  id: string;
  label: string;
  service_type: string;
  status: 'healthy' | 'critical' | 'root_cause';
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  status: 'normal' | 'failing';
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface HealthStatus {
  status: string;
  version: string;
  services_count: number;
  dependencies_count: number;
}

export interface IncidentRecord {
  incident_id: string;
  created_at: string;
  status: string;
  scenarios: string[];
  injected_services: string[];
  telemetry: TelemetryEvent[];
  rca_result?: RCAResult | null;
}

export interface SSEActiveFailure {
  incident_id: string;
  service: string;
  scenario: string;
  injected_at: string;
}

export interface SSEEventEnvelope<T = unknown> {
  event: string;
  timestamp: string;
  active_failures: SSEActiveFailure[];
  data: T;
}

export const SERVICE_NAMES = [
  'api-gateway',
  'user-service',
  'order-service',
  'product-service',
  'payment-service',
  'notification-service',
  'database',
] as const;

export type ServiceName = (typeof SERVICE_NAMES)[number];

export const DEPENDENCIES: [ServiceName, ServiceName][] = [
  ['api-gateway', 'user-service'],
  ['api-gateway', 'order-service'],
  ['api-gateway', 'product-service'],
  ['order-service', 'payment-service'],
  ['order-service', 'notification-service'],
  ['payment-service', 'database'],
];

// Centralized API Client Functions
export async function simulatePaymentFailure(): Promise<SimulationResponse> {
  const res = await fetch(`${API_BASE}/simulate/payment-failure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    throw new Error(`Failed to simulate payment failure: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function simulateDatabaseLatency(): Promise<SimulationResponse> {
  const res = await fetch(`${API_BASE}/simulate/database-latency`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    throw new Error(`Failed to simulate database latency: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function simulateNotificationFailure(): Promise<SimulationResponse> {
  const res = await fetch(`${API_BASE}/simulate/notification-failure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    throw new Error(`Failed to simulate notification failure: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function resetSimulation(): Promise<{ status: string; message?: string }> {
  const res = await fetch(`${API_BASE}/simulate/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) {
    throw new Error(`Failed to reset simulation: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function getGraph(): Promise<GraphData> {
  const res = await fetch(`${API_BASE}/graph`);
  if (!res.ok) {
    throw new Error(`Failed to fetch service graph: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function getIncident(incidentId: string): Promise<IncidentRecord> {
  const res = await fetch(`${API_BASE}/incident/${encodeURIComponent(incidentId)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch incident ${incidentId}: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function getRCAResult(incidentId: string): Promise<RCAResult> {
  const res = await fetch(`${API_BASE}/rca/${encodeURIComponent(incidentId)}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch RCA result for ${incidentId}: HTTP ${res.status}`);
  }
  return await res.json();
}

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(2000) });
    return res.ok;
  } catch {
    return false;
  }
}

export function createEventSource(): EventSource {
  return new EventSource(`${API_BASE}/events`);
}
