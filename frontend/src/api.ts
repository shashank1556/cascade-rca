/**
 * Cascade RCA Frontend API Client & Contracts.
 * Strictly complies with backend/contracts.py and ARCHITECTURE.md.
 * Authoritative source of truth is the backend FastAPI server.
 */

import axios from 'axios';

export const API_BASE =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Central Axios client.
 * No secrets are stored or sent from the frontend.
 */
const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

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
  try {
    const response = await api.post<SimulationResponse>(
      '/simulate/payment-failure'
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(
        `Failed to simulate payment failure: HTTP ${
          error.response?.status ?? 'network error'
        }`
      );
    }
    throw error;
  }
}

export async function simulateDatabaseLatency(): Promise<SimulationResponse> {
  try {
    const response = await api.post<SimulationResponse>(
      '/simulate/database-latency'
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(
        `Failed to simulate database latency: HTTP ${
          error.response?.status ?? 'network error'
        }`
      );
    }
    throw error;
  }
}

export async function simulateNotificationFailure(): Promise<SimulationResponse> {
  try {
    const response = await api.post<SimulationResponse>(
      '/simulate/notification-failure'
    );
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(
        `Failed to simulate notification failure: HTTP ${
          error.response?.status ?? 'network error'
        }`
      );
    }
    throw error;
  }
}

export async function resetSimulation(): Promise<{
  status: string;
  message?: string;
}> {
  try {
    const response = await api.post<{
      status: string;
      message?: string;
    }>('/simulate/reset');

    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(
        `Failed to reset simulation: HTTP ${
          error.response?.status ?? 'network error'
        }`
      );
    }
    throw error;
  }
}

export async function getGraph(): Promise<GraphData> {
  try {
    const response = await api.get<GraphData>('/graph');
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(
        `Failed to fetch service graph: HTTP ${
          error.response?.status ?? 'network error'
        }`
      );
    }
    throw error;
  }
}

export async function getIncident(
  incidentId: string
): Promise<IncidentRecord> {
  try {
    const response = await api.get<IncidentRecord>(
      `/incident/${encodeURIComponent(incidentId)}`
    );

    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(
        `Failed to fetch incident ${incidentId}: HTTP ${
          error.response?.status ?? 'network error'
        }`
      );
    }
    throw error;
  }
}

export async function getRCAResult(
  incidentId: string
): Promise<RCAResult> {
  try {
    const response = await api.get<RCAResult>(
      `/rca/${encodeURIComponent(incidentId)}`
    );

    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      throw new Error(
        `Failed to fetch RCA result for ${incidentId}: HTTP ${
          error.response?.status ?? 'network error'
        }`
      );
    }
    throw error;
  }
}

export async function checkBackendHealth(): Promise<boolean> {
  try {
    await api.get('/health', {
      timeout: 2000,
    });

    return true;
  } catch {
    return false;
  }
}

/**
 * SSE remains native EventSource because it is a browser streaming API.
 * Axios is used for REST/HTTP requests above.
 */
export function createEventSource(): EventSource {
  return new EventSource(`${API_BASE}/events`);
}