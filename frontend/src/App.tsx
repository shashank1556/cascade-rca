import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Activity, AlertCircle, Wifi, WifiOff } from 'lucide-react';
import { ServiceGraph } from './components/ServiceGraph';
import { IncidentPanel } from './components/IncidentPanel';
import { RCAResult } from './components/RCAResult';
import { Timeline } from './components/Timeline';
import { CommitCard } from './components/CommitCard';
import type {
  RCAResult as RCAResultType,
  SSEActiveFailure,
  SSEEventEnvelope,
} from './api';
import {
  API_BASE,
  simulatePaymentFailure,
  simulateDatabaseLatency,
  simulateNotificationFailure,
  resetSimulation,
  getRCAResult,
  getGraph,
  checkBackendHealth,
} from './api';

export const App: React.FC = () => {
  // State directly synchronized with backend
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [rca, setRca] = useState<RCAResultType | null>(null);
  const [activeFailures, setActiveFailures] = useState<SSEActiveFailure[]>([]);
  const [propagationEdges, setPropagationEdges] = useState<Array<{ from: string; to: string }>>([]);
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'reconnecting' | 'offline'>('reconnecting');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedService, setSelectedService] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState<string>('');

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Live UTC Clock
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTime(now.toUTCString().replace('GMT', 'UTC'));
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  // Sync initial graph & state on mount
  const syncInitialState = useCallback(async () => {
    try {
      const isHealthy = await checkBackendHealth();
      if (!isHealthy) {
        setConnectionStatus('offline');
        return;
      }
      const graphData = await getGraph();
      const failingEdges = graphData.edges
        .filter((e) => e.status === 'failing')
        .map((e) => ({ from: e.source, to: e.target }));
      setPropagationEdges(failingEdges);
    } catch {
      // Backend may be starting
    }
  }, []);

  useEffect(() => {
    syncInitialState();
  }, [syncInitialState]);

  // Real Server-Sent Events (SSE) integration
  useEffect(() => {
    let isSubscribed = true;

    const connectSSE = () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }

      setConnectionStatus('reconnecting');
      const es = new EventSource(`${API_BASE}/events`);
      eventSourceRef.current = es;

      es.onopen = () => {
        if (!isSubscribed) return;
        setConnectionStatus('connected');
        setErrorMessage(null);
      };

      // Handle custom SSE event types emitted by backend streaming_manager
      es.addEventListener('connected', (event: MessageEvent) => {
        if (!isSubscribed) return;
        try {
          const envelope: SSEEventEnvelope<{ message: string }> = JSON.parse(event.data);
          if (envelope.active_failures) {
            setActiveFailures(envelope.active_failures);
          }
        } catch {
          // Ignore JSON parse errors on ping
        }
      });

      es.addEventListener('heartbeat', (event: MessageEvent) => {
        if (!isSubscribed) return;
        try {
          const envelope: SSEEventEnvelope = JSON.parse(event.data);
          if (envelope.active_failures) {
            setActiveFailures(envelope.active_failures);
          }
        } catch {
          // Ignore heartbeat parse
        }
      });

      es.addEventListener('failure_injection', (event: MessageEvent) => {
        if (!isSubscribed) return;
        try {
          const envelope: SSEEventEnvelope<{ incident_id: string; service: string; scenario: string }> =
            JSON.parse(event.data);
          if (envelope.active_failures) {
            setActiveFailures(envelope.active_failures);
          }
          if (envelope.data?.incident_id) {
            setIncidentId(envelope.data.incident_id);
          }
        } catch {
          // Ignore malformed event
        }
      });

      es.addEventListener('service_state', (event: MessageEvent) => {
        if (!isSubscribed) return;
        try {
          const envelope: SSEEventEnvelope<{
            service?: string;
            status?: string;
            all_services?: boolean;
          }> = JSON.parse(event.data);

          if (envelope.data?.all_services && envelope.data?.status === 'healthy') {
            setActiveFailures([]);
            setPropagationEdges([]);
            setRca(null);
            setIncidentId(null);
          }
          if (envelope.active_failures) {
            setActiveFailures(envelope.active_failures);
          }
        } catch {
          // Ignore parse error
        }
      });

      es.addEventListener('cascade_propagation', (event: MessageEvent) => {
        if (!isSubscribed) return;
        try {
          const envelope: SSEEventEnvelope<{ from_service: string; to_service: string; hop: number }> =
            JSON.parse(event.data);
          if (envelope.data?.from_service && envelope.data?.to_service) {
            setPropagationEdges((prev) => {
              const next = [...prev, { from: envelope.data.from_service, to: envelope.data.to_service }];
              // Deduplicate
              return next.filter(
                (e, i, arr) =>
                  arr.findIndex((x) => x.from === e.from && x.to === e.to) === i
              );
            });
          }
          if (envelope.active_failures) {
            setActiveFailures(envelope.active_failures);
          }
        } catch {
          // Ignore parse error
        }
      });

      es.addEventListener('rca_result', (event: MessageEvent) => {
        if (!isSubscribed) return;
        try {
          const envelope: SSEEventEnvelope<RCAResultType> = JSON.parse(event.data);
          // Backend broadcasts either full envelope or raw RCAResult payload
          const resultData: RCAResultType =
            (envelope.data && 'root_cause' in envelope.data)
              ? envelope.data
              : (envelope as unknown as RCAResultType);

          if (resultData && resultData.root_cause) {
            setRca(resultData);
            if (resultData.incident_id) {
              setIncidentId(resultData.incident_id);
            }
          }
          if (envelope.active_failures) {
            setActiveFailures(envelope.active_failures);
          }
        } catch {
          // Ignore parse error
        }
      });

      es.onerror = () => {
        if (!isSubscribed) return;
        setConnectionStatus('reconnecting');
        es.close();
        // Exponential backoff / graceful reconnection
        reconnectTimeoutRef.current = setTimeout(() => {
          if (isSubscribed) connectSSE();
        }, 3000);
      };
    };

    connectSSE();

    return () => {
      isSubscribed = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, []);

  // Trigger RCA retrieval after simulation to ensure result renders promptly
  const fetchAuthoritativeRCA = async (incId: string) => {
    try {
      const result = await getRCAResult(incId);
      setRca(result);
      setErrorMessage(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unable to retrieve RCA result.';
      setErrorMessage(msg);
    }
  };

  // Scenario 1: Payment Failure
  const handleInjectPayment = async () => {
    if (activeFailures.length >= 2) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const resp = await simulatePaymentFailure();
      setIncidentId(resp.incident_id);
      // Backend automatically broadcasts SSE events; also fetch authoritative RCA
      await fetchAuthoritativeRCA(resp.incident_id);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Backend unavailable');
    } finally {
      setIsLoading(false);
    }
  };

  // Scenario 2: Database Latency
  const handleInjectDatabase = async () => {
    if (activeFailures.length >= 2) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const resp = await simulateDatabaseLatency();
      setIncidentId(resp.incident_id);
      await fetchAuthoritativeRCA(resp.incident_id);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Backend unavailable');
    } finally {
      setIsLoading(false);
    }
  };

  // Scenario 3: Notification Failure
  const handleInjectNotification = async () => {
    if (activeFailures.length >= 2) return;
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const resp = await simulateNotificationFailure();
      setIncidentId(resp.incident_id);
      await fetchAuthoritativeRCA(resp.incident_id);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Backend unavailable');
    } finally {
      setIsLoading(false);
    }
  };

  // Reset to clean healthy baseline
  const handleReset = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      await resetSimulation();
      setActiveFailures([]);
      setIncidentId(null);
      setRca(null);
      setPropagationEdges([]);
      setSelectedService(null);
    } catch (err: unknown) {
      setErrorMessage(err instanceof Error ? err.message : 'Backend unavailable');
    } finally {
      setIsLoading(false);
    }
  };

  // Compute overall system health status
  const getSystemStatus = () => {
    if (activeFailures.length === 0) return { label: 'HEALTHY', class: 'status-healthy' };
    if (activeFailures.length === 1) return { label: 'ANOMALY DETECTED', class: 'status-degraded' };
    return { label: 'DUAL INCIDENT ACTIVE', class: 'status-critical' };
  };

  const systemStatus = getSystemStatus();

  // Identify any active failure service that is NOT the primary root cause or in affected_services
  const independentServices = activeFailures
    .map((f) => f.service)
    .filter((svc) => svc !== rca?.root_cause.service && !rca?.affected_services.includes(svc));

  return (
    <div className="app-container">
      {/* Top Navigation Header */}
      <header className="app-header">
        <div className="header-left">
          <div className="logo-badge">
            <Activity className="w-6 h-6 text-indigo-400 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="app-title">CASCADE RCA</h1>
              <span className="version-tag font-mono">v1.0-LOCKED</span>
            </div>
            <p className="app-subtitle">
              System Observability & Resiliency — Causal Root-Cause Analysis for Cascading Microservices
            </p>
          </div>
        </div>

        <div className="header-right">
          {/* Real-time SSE Connection Status */}
          <div className="header-stat-box">
            <span className="stat-label">STREAM CONNECTION</span>
            <div className="flex items-center gap-1.5">
              {connectionStatus === 'connected' ? (
                <>
                  <Wifi className="w-3.5 h-3.5 text-emerald-400" />
                  <strong className="text-xs text-emerald-400">SSE Connected</strong>
                </>
              ) : connectionStatus === 'reconnecting' ? (
                <>
                  <Wifi className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
                  <strong className="text-xs text-amber-400">SSE Reconnecting</strong>
                </>
              ) : (
                <>
                  <WifiOff className="w-3.5 h-3.5 text-rose-400" />
                  <strong className="text-xs text-rose-400">Backend Offline</strong>
                </>
              )}
            </div>
          </div>

          <div className="header-stat-box">
            <span className="stat-label">SYSTEM HEALTH</span>
            <div className="flex items-center gap-1.5">
              <span className={`status-indicator ${systemStatus.class}`}></span>
              <strong className={`status-text ${systemStatus.class}`}>{systemStatus.label}</strong>
            </div>
          </div>

          <div className="header-stat-box">
            <span className="stat-label">INCIDENT TRACKER</span>
            <span className="font-mono text-sm text-slate-200">
              {incidentId || 'NONE (BASELINE)'}
            </span>
          </div>

          <div className="header-stat-box">
            <span className="stat-label">UTC CLOCK</span>
            <span className="font-mono text-xs text-slate-400">{currentTime || 'SYNCING...'}</span>
          </div>
        </div>
      </header>

      {/* Error notification banner if API fails */}
      {errorMessage && (
        <div className="api-error-banner flex items-center justify-between p-3 mb-4 rounded bg-rose-950/40 border border-rose-500/50 text-rose-200 text-sm">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button
            onClick={() => setErrorMessage(null)}
            className="text-xs text-rose-400 hover:text-white underline ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Dashboard Layout */}
      <main className="dashboard-grid">
        {/* Left Column: Topology & Failure Controls */}
        <section className="left-column">
          {/* Failure Injection Controls */}
          <IncidentPanel
            activeFailures={activeFailures}
            isLoading={isLoading}
            onInjectPayment={handleInjectPayment}
            onInjectDatabase={handleInjectDatabase}
            onInjectNotification={handleInjectNotification}
            onReset={handleReset}
            incidentId={incidentId}
          />

          {/* Microservice Dependency Topology */}
          <ServiceGraph
            rootCauseService={rca?.root_cause.service || null}
            affectedServices={rca?.affected_services || []}
            independentServices={independentServices}
            propagationEdges={propagationEdges}
            selectedService={selectedService}
            onSelectService={setSelectedService}
            activeFailuresCount={activeFailures.length}
          />
        </section>

        {/* Right Column: RCA Intelligence, Timeline, Commit Correlation */}
        <section className="right-column">
          {/* Canonical RCA Result Card */}
          <RCAResult
            rca={rca}
            isLoading={isLoading}
            independentServices={independentServices}
          />

          {/* GitHub Commit Correlation */}
          <CommitCard
            commit={rca?.commit || null}
            rootCauseService={rca?.root_cause.service || null}
          />

          {/* Propagation Timeline */}
          <Timeline
            timeline={rca?.timeline || []}
            rootCauseService={rca?.root_cause.service || null}
            independentServices={independentServices}
          />
        </section>
      </main>

      {/* Dashboard Footer */}
      <footer className="app-footer">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span>Cascade RCA Prototype</span>
          <span>•</span>
          <span>FastAPI + NetworkX Causal Backpropagation + React Vite</span>
          <span>•</span>
          <span>Complies with ARCHITECTURE.md & contracts.py</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500 font-mono">
          <span>Developer 3: Frontend Dashboard</span>
        </div>
      </footer>
    </div>
  );
};

export default App;
