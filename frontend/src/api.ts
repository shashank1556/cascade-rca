/**
 * Cascade RCA Frontend API Client & Contracts.
 * Strictly complies with backend/contracts.py and ARCHITECTURE.md.
 */

export interface TelemetryEvent {
  timestamp: string;
  service: string;
  trace_id: string;
  span_id: string;
  parent_span_id?: string | null;
  latency_ms: number;
  status_code: number;
}

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

export interface ServiceNodeMeta {
  id: string;
  name: string;
  tier: number;
  type: 'gateway' | 'service' | 'database';
  status: 'healthy' | 'root-cause' | 'affected' | 'independent-failure';
  latencyMs?: number;
  statusCode?: number;
  message?: string;
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

export type ServiceName = typeof SERVICE_NAMES[number];

export const DEPENDENCIES: [ServiceName, ServiceName][] = [
  ['api-gateway', 'user-service'],
  ['api-gateway', 'order-service'],
  ['api-gateway', 'product-service'],
  ['order-service', 'payment-service'],
  ['order-service', 'notification-service'],
  ['payment-service', 'database'],
];

const API_BASE = 'http://localhost:8000';

// Real-time backend API integration with automatic fallback to high-fidelity mock data
export async function simulatePaymentFailure(): Promise<SimulationResponse> {
  try {
    const res = await fetch(`${API_BASE}/simulate/payment-failure`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (res.ok) return await res.json();
  } catch {
    // Graceful offline demo fallback
  }
  return { incident_id: 'INC-001', status: 'simulated' };
}

export async function simulateDatabaseLatency(): Promise<SimulationResponse> {
  try {
    const res = await fetch(`${API_BASE}/simulate/database-latency`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (res.ok) return await res.json();
  } catch {
    // Graceful offline demo fallback
  }
  return { incident_id: 'INC-002', status: 'simulated' };
}

export async function simulateNotificationFailure(): Promise<SimulationResponse> {
  try {
    const res = await fetch(`${API_BASE}/simulate/notification-failure`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (res.ok) return await res.json();
  } catch {
    // Graceful offline demo fallback
  }
  return { incident_id: 'INC-003', status: 'simulated' };
}

export async function resetSimulation(): Promise<SimulationResponse> {
  try {
    const res = await fetch(`${API_BASE}/simulate/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (res.ok) return await res.json();
  } catch {
    // Graceful offline demo fallback
  }
  return { incident_id: 'INC-000', status: 'reset' };
}

export async function getRCAResult(incidentId: string): Promise<RCAResult> {
  try {
    const res = await fetch(`${API_BASE}/rca/${incidentId}`);
    if (res.ok) return await res.json();
  } catch {
    // Graceful offline demo fallback
  }
  return getMockRCAResult(incidentId);
}

export async function checkBackendHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(1500) });
    return res.ok;
  } catch {
    return false;
  }
}

/**
 * Deterministic mock generator strictly adhering to backend/contracts.py
 * for scenarios 1, 2, 3 and dual concurrent failures.
 */
export function getMockRCAResult(
  incidentId: string,
  activeFailures: string[] = ['payment_failure']
): RCAResult {
  const hasPayment = activeFailures.includes('payment_failure');
  const hasDb = activeFailures.includes('database_latency');
  const hasNotif = activeFailures.includes('notification_failure');

  const now = new Date();
  const formatTime = (offsetMs: number) =>
    new Date(now.getTime() - offsetMs).toISOString();

  // CASE B: Two independent failures occur simultaneously
  if (hasPayment && hasNotif) {
    return {
      incident_id: incidentId || 'INC-004',
      status: 'investigating',
      root_cause: {
        service: 'payment-service',
        confidence: 0.91,
      },
      affected_services: ['order-service', 'api-gateway', 'notification-service'],
      timeline: [
        {
          timestamp: formatTime(6200),
          service: 'payment-service',
          event: 'Primary Root Cause: 500 Internal Server Error (payment timeout). Initiates downstream cascade.',
        },
        {
          timestamp: formatTime(5800),
          service: 'notification-service',
          event: 'Independent Failure: 500 Internal Server Error (SMTP gateway unreachable). Isolated incident.',
        },
        {
          timestamp: formatTime(4900),
          service: 'order-service',
          event: 'Cascaded Failure: 500 Internal Server Error propagated from payment-service.',
        },
        {
          timestamp: formatTime(3500),
          service: 'api-gateway',
          event: 'Cascaded Failure: 502 Bad Gateway observed due to order-service checkout failure.',
        },
      ],
      commit: {
        sha: '8f31c2a',
        message: 'refactor(payment): update timeout and retry backoff thresholds',
        url: 'https://github.com/shashank1556/cascade-rca/commit/8f31c2a',
        author: 'payment-team-lead',
      },
      explanation:
        'Identified payment-service as the primary causal origin with 0.91 confidence, propagating failures downstream through order-service to api-gateway. Simultaneously, an independent isolated failure was detected on notification-service without topological linkage to the payment cascade.',
    };
  }

  // SCENARIO 2: Database latency cascade
  if (hasDb) {
    return {
      incident_id: incidentId || 'INC-002',
      status: 'resolved',
      root_cause: {
        service: 'database',
        confidence: 0.94,
      },
      affected_services: ['payment-service', 'order-service', 'api-gateway'],
      timeline: [
        {
          timestamp: formatTime(7500),
          service: 'database',
          event: 'Root Cause: Query latency elevated to 3200ms with connection pool exhaustion (504 Gateway Timeout).',
        },
        {
          timestamp: formatTime(6800),
          service: 'payment-service',
          event: 'Cascaded Failure: Database timeout propagated to payment processing (504 Gateway Timeout).',
        },
        {
          timestamp: formatTime(5500),
          service: 'order-service',
          event: 'Cascaded Failure: Order creation timeout (504 Gateway Timeout) waiting for payment confirmation.',
        },
        {
          timestamp: formatTime(4200),
          service: 'api-gateway',
          event: 'Cascaded Failure: Client facing 504 Gateway Timeout on checkout route.',
        },
      ],
      commit: {
        sha: '4d82b19',
        message: 'perf(database): alter index scan strategy on transactions table',
        url: 'https://github.com/shashank1556/cascade-rca/commit/4d82b19',
        author: 'dba-team',
      },
      explanation:
        'Causal analysis identifies database as the originating root cause (0.94 confidence). Unusually high database latency triggered upstream timeouts cascading through payment-service to order-service and the ingress api-gateway.',
    };
  }

  // SCENARIO 3: Notification failure (isolated)
  if (hasNotif) {
    return {
      incident_id: incidentId || 'INC-003',
      status: 'resolved',
      root_cause: {
        service: 'notification-service',
        confidence: 0.88,
      },
      affected_services: [],
      timeline: [
        {
          timestamp: formatTime(4500),
          service: 'notification-service',
          event: 'Isolated Root Cause: 500 Internal Server Error. Delivery queue connection refused.',
        },
      ],
      commit: {
        sha: 'c701ef3',
        message: 'fix(notification): update webhook signature verification logic',
        url: 'https://github.com/shashank1556/cascade-rca/commit/c701ef3',
        author: 'alerts-team',
      },
      explanation:
        'Identified notification-service as the isolated root cause (0.88 confidence). The failure occurred independently in the notification pipeline with no downstream propagation to order-service or api-gateway.',
    };
  }

  // SCENARIO 1: Payment failure (default)
  return {
    incident_id: incidentId || 'INC-001',
    status: 'resolved',
    root_cause: {
      service: 'payment-service',
      confidence: 0.91,
    },
    affected_services: ['order-service', 'api-gateway'],
    timeline: [
      {
        timestamp: formatTime(5500),
        service: 'payment-service',
        event: 'Root Cause: 500 Internal Server Error (Payment gateway connection dropped).',
      },
      {
        timestamp: formatTime(4200),
        service: 'order-service',
        event: 'Cascaded Failure: Order checkout failed with 500 Internal Server Error due to payment-service fault.',
      },
      {
        timestamp: formatTime(3100),
        service: 'api-gateway',
        event: 'Cascaded Failure: Ingress gateway received 502 Bad Gateway from order-service.',
      },
    ],
    commit: {
      sha: '8f31c2a',
      message: 'Update payment timeout handling',
      url: 'https://github.com/shashank1556/cascade-rca/commit/8f31c2a',
      author: 'payment-developer',
    },
    explanation:
      'Root-cause analysis confirms payment-service as the originating failure point (0.91 confidence). The failure cascaded downstream into order-service and surfaced to clients through api-gateway.',
  };
}
