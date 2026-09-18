import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Activity, AlertCircle } from 'lucide-react';

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
  getGraph,
  checkBackendHealth,
} from './api';

export const App: React.FC = () => {
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [rca, setRca] = useState<RCAResultType | null>(null);
  const [activeFailures, setActiveFailures] = useState<SSEActiveFailure[]>([]);
  const [propagationEdges, setPropagationEdges] = useState<
    Array<{ from: string; to: string }>
  >([]);
  const [, setConnectionStatus] = useState<
  'connected' | 'reconnecting' | 'offline'
   >('reconnecting');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedService, setSelectedService] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState('');

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* ---------------------------------------------------------
     UTC CLOCK
  --------------------------------------------------------- */
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTime(now.toUTCString().replace('GMT', 'UTC'));
    };

    updateTime();

    const timer = setInterval(updateTime, 1000);

    return () => clearInterval(timer);
  }, []);

  /* ---------------------------------------------------------
     INITIAL BACKEND STATE
  --------------------------------------------------------- */
  const syncInitialState = useCallback(async () => {
    try {
      const isHealthy = await checkBackendHealth();

      if (!isHealthy) {
        setConnectionStatus('offline');
        return;
      }

      const graphData = await getGraph();

      const failingEdges = graphData.edges
        .filter((edge) => edge.status === 'failing')
        .map((edge) => ({
          from: edge.source,
          to: edge.target,
        }));

      setPropagationEdges(failingEdges);
    } catch {
      setConnectionStatus('offline');
    }
  }, []);

  useEffect(() => {
    syncInitialState();
  }, [syncInitialState]);

  /* ---------------------------------------------------------
     SSE CONNECTION
     Technical connection status remains internal.
     It is intentionally NOT shown in the main header.
  --------------------------------------------------------- */
  useEffect(() => {
    let isSubscribed = true;

    const connectSSE = () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }

      setConnectionStatus('reconnecting');

      const eventSource = new EventSource(`${API_BASE}/events`);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        if (!isSubscribed) return;

        setConnectionStatus('connected');
        setErrorMessage(null);
      };

      /* Connected */
      eventSource.addEventListener(
        'connected',
        (event: MessageEvent) => {
          if (!isSubscribed) return;

          try {
            const envelope: SSEEventEnvelope<{ message: string }> =
              JSON.parse(event.data);

            if (envelope.active_failures) {
              setActiveFailures(envelope.active_failures);
            }
          } catch {
            // Ignore malformed SSE payload
          }
        }
      );

      /* Heartbeat */
      eventSource.addEventListener(
        'heartbeat',
        (event: MessageEvent) => {
          if (!isSubscribed) return;

          try {
            const envelope: SSEEventEnvelope = JSON.parse(event.data);

            if (envelope.active_failures) {
              setActiveFailures(envelope.active_failures);
            }
          } catch {
            // Ignore malformed heartbeat
          }
        }
      );

      /* Failure injection */
      eventSource.addEventListener(
        'failure_injection',
        (event: MessageEvent) => {
          if (!isSubscribed) return;

          try {
            const envelope: SSEEventEnvelope<{
              incident_id: string;
              service: string;
              scenario: string;
            }> = JSON.parse(event.data);

            if (envelope.active_failures) {
              setActiveFailures(envelope.active_failures);
            }

            if (envelope.data?.incident_id) {
              setIncidentId(envelope.data.incident_id);
            }
          } catch {
            // Ignore malformed event
          }
        }
      );

      /* Service state */
      eventSource.addEventListener(
        'service_state',
        (event: MessageEvent) => {
          if (!isSubscribed) return;

          try {
            const envelope: SSEEventEnvelope<{
              service?: string;
              status?: string;
              all_services?: boolean;
            }> = JSON.parse(event.data);

            if (
              envelope.data?.all_services &&
              envelope.data?.status === 'healthy'
            ) {
              setActiveFailures([]);
              setPropagationEdges([]);
              setRca(null);
              setIncidentId(null);
            }

            if (envelope.active_failures) {
              setActiveFailures(envelope.active_failures);
            }
          } catch {
            // Ignore malformed event
          }
        }
      );

      /* Cascade propagation */
      eventSource.addEventListener(
        'cascade_propagation',
        (event: MessageEvent) => {
          if (!isSubscribed) return;

          try {
            const envelope: SSEEventEnvelope<{
              from_service: string;
              to_service: string;
              hop: number;
            }> = JSON.parse(event.data);

            if (
              envelope.data?.from_service &&
              envelope.data?.to_service
            ) {
              setPropagationEdges((previous) => {
                const next = [
                  ...previous,
                  {
                    from: envelope.data!.from_service,
                    to: envelope.data!.to_service,
                  },
                ];

                return next.filter(
                  (edge, index, array) =>
                    array.findIndex(
                      (item) =>
                        item.from === edge.from &&
                        item.to === edge.to
                    ) === index
                );
              });
            }

            if (envelope.active_failures) {
              setActiveFailures(envelope.active_failures);
            }
          } catch {
            // Ignore malformed event
          }
        }
      );

      /* RCA result */
      eventSource.addEventListener(
        'rca_result',
        (event: MessageEvent) => {
          if (!isSubscribed) return;

          try {
            const envelope: SSEEventEnvelope<RCAResultType> =
              JSON.parse(event.data);

            const resultData: RCAResultType =
              envelope.data && 'root_cause' in envelope.data
                ? envelope.data
                : (envelope as unknown as RCAResultType);

            if (resultData?.root_cause) {
              setRca(resultData);

              if (resultData.incident_id) {
                setIncidentId(resultData.incident_id);
              }
            }

            if (envelope.active_failures) {
              setActiveFailures(envelope.active_failures);
            }
          } catch {
            // Ignore malformed event
          }
        }
      );

      /* Reconnect */
      eventSource.onerror = () => {
        if (!isSubscribed) return;

        setConnectionStatus('reconnecting');
        eventSource.close();

        reconnectTimeoutRef.current = setTimeout(() => {
          if (isSubscribed) {
            connectSSE();
          }
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

  /* ---------------------------------------------------------
     FAILURE SCENARIOS
  --------------------------------------------------------- */
  const handleInjectPayment = async () => {
    if (activeFailures.length >= 2) return;

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const response = await simulatePaymentFailure();
      setIncidentId(response.incident_id);
    } catch (error: unknown) {
      setErrorMessage(
        error instanceof Error ? error.message : 'Backend unavailable'
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleInjectDatabase = async () => {
    if (activeFailures.length >= 2) return;

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const response = await simulateDatabaseLatency();
      setIncidentId(response.incident_id);
    } catch (error: unknown) {
      setErrorMessage(
        error instanceof Error ? error.message : 'Backend unavailable'
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleInjectNotification = async () => {
    if (activeFailures.length >= 2) return;

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const response = await simulateNotificationFailure();
      setIncidentId(response.incident_id);
    } catch (error: unknown) {
      setErrorMessage(
        error instanceof Error ? error.message : 'Backend unavailable'
      );
    } finally {
      setIsLoading(false);
    }
  };

  /* ---------------------------------------------------------
     RESET
  --------------------------------------------------------- */
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
    } catch (error: unknown) {
      setErrorMessage(
        error instanceof Error ? error.message : 'Backend unavailable'
      );
    } finally {
      setIsLoading(false);
    }
  };

  /* ---------------------------------------------------------
     SYSTEM STATUS
  --------------------------------------------------------- */
  const getSystemStatus = () => {
    if (activeFailures.length === 0) {
      return {
        label: 'HEALTHY',
        class: 'status-healthy',
      };
    }

    if (activeFailures.length === 1) {
      return {
        label: 'ANOMALY DETECTED',
        class: 'status-degraded',
      };
    }

    return {
      label: 'DUAL INCIDENT ACTIVE',
      class: 'status-critical',
    };
  };

  const systemStatus = getSystemStatus();

  /* ---------------------------------------------------------
     INDEPENDENT FAILURE DETECTION
  --------------------------------------------------------- */
  const independentServices = activeFailures
    .map((failure) => failure.service)
    .filter(
      (service) =>
        service !== rca?.root_cause.service &&
        !rca?.affected_services.includes(service)
    );

  return (
    <div className="app-container">

      {/* =====================================================
          HEADER
      ===================================================== */}
      <header className="app-header">
        <div className="header-left">
          <div className="logo-badge">
            <Activity className="logo-icon" />
          </div>

          <div>
            <div className="app-title-row">
              <h1 className="app-title">CASCADE RCA</h1>
              <span className="version-tag">v1.0</span>
            </div>

            <p className="app-subtitle">
              Causal Root-Cause Analysis for Cascading Microservices
            </p>
          </div>
        </div>

        <div className="header-right">
          {/* Only meaningful user-facing status remains here */}
          <div className="header-status">
            <span className={`status-indicator ${systemStatus.class}`} />
            <div>
              <span className="stat-label">SYSTEM STATUS</span>
              <strong className={`status-text ${systemStatus.class}`}>
                {systemStatus.label}
              </strong>
            </div>
          </div>

          <div className="header-clock">
            <span className="stat-label">UTC</span>
            <span className="clock-value">
              {currentTime || 'SYNCING...'}
            </span>
          </div>
        </div>
      </header>

      {/* =====================================================
          ERROR
      ===================================================== */}
      {errorMessage && (
        <div className="api-error-banner">
          <div className="error-content">
            <AlertCircle className="error-icon" />
            <span>{errorMessage}</span>
          </div>

          <button
            onClick={() => setErrorMessage(null)}
            className="error-dismiss"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* =====================================================
          INCIDENT CONTROLS
      ===================================================== */}
      <section className="incident-section">
        <IncidentPanel
          activeFailures={activeFailures}
          isLoading={isLoading}
          onInjectPayment={handleInjectPayment}
          onInjectDatabase={handleInjectDatabase}
          onInjectNotification={handleInjectNotification}
          onReset={handleReset}
          incidentId={incidentId}
        />
      </section>

      {/* =====================================================
          MAIN DASHBOARD
      ===================================================== */}
      <main className="dashboard-grid">

        {/* SERVICE TOPOLOGY */}
        <section className="left-column">
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

        {/* RCA + AI + GITHUB */}
        <section className="right-column">

          <RCAResult
            rca={rca}
            isLoading={isLoading}
            independentServices={independentServices}
          />

          {/* =================================================
              AI EXPLANATION LAYER
          ================================================= */}
          <section className="ai-layer-card card">
            <div className="ai-layer-header">
              <div className="ai-layer-title-group">
                <div className="ai-layer-icon">
                  <span>✦</span>
                </div>

                <div>
                  <h3>AI Explanation Layer</h3>
                  <p>
                    Natural-language interpretation of the backend RCA result
                  </p>
                </div>
              </div>

              <span className="ai-layer-badge">
                AI NARRATION
              </span>
            </div>

            <div className="ai-layer-content">
              {!rca ? (
                <div className="ai-empty-state">
                  <p>
                    AI explanation will appear after an incident is analyzed.
                  </p>
                </div>
              ) : (
                <>
                  <div className="ai-explanation-label">
                    RCA ENGINE → AI EXPLANATION
                  </div>

                  <p className="ai-explanation-text">
                    {rca.explanation ||
                      'No natural-language explanation is currently available.'}
                  </p>

                  <div className="ai-layer-footer">
                    <span>
                      The RCA engine determines the causal result.
                    </span>
                    <span>
                      AI provides the human-readable explanation.
                    </span>
                  </div>
                </>
              )}
            </div>
          </section>

          <CommitCard
            commit={rca?.commit || null}
            rootCauseService={rca?.root_cause.service || null}
          />
        </section>
      </main>

      {/* =====================================================
          TIMELINE
      ===================================================== */}
      <section className="timeline-section">
        <Timeline
          timeline={rca?.timeline || []}
          rootCauseService={rca?.root_cause.service || null}
          independentServices={independentServices}
        />
      </section>

      {/* =====================================================
          FOOTER
      ===================================================== */}
      <footer className="app-footer">
        <span>
          Cascade RCA
        </span>

        <span>
          FastAPI · NetworkX · Causal Backpropagation · React
        </span>
      </footer>
    </div>
  );
};

export default App;