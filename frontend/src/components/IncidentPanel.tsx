import React from 'react';
import {
  Flame,
  Clock,
  BellOff,
  RotateCcw,
  ShieldCheck,
  AlertOctagon,
  Layers,
} from 'lucide-react';

export interface IncidentPanelProps {
  activeFailures: Array<{
    incident_id: string;
    service: string;
    scenario: string;
  }>;
  isLoading: boolean;
  onInjectPayment: () => void;
  onInjectDatabase: () => void;
  onInjectNotification: () => void;
  onReset: () => void;
  incidentId: string | null;
}

export const IncidentPanel: React.FC<IncidentPanelProps> = ({
  activeFailures,
  isLoading,
  onInjectPayment,
  onInjectDatabase,
  onInjectNotification,
  onReset,
  incidentId,
}) => {
  const failureCount = activeFailures.length;
  const isMaxFailures = failureCount >= 2;
  const isHealthy = failureCount === 0;

  const hasPayment = activeFailures.some(
    (failure) =>
      failure.scenario.includes('payment') ||
      failure.service === 'payment-service'
  );

  const hasDb = activeFailures.some(
    (failure) =>
      failure.scenario.includes('database') ||
      failure.service === 'database'
  );

  const hasNotif = activeFailures.some(
    (failure) =>
      failure.scenario.includes('notification') ||
      failure.service === 'notification-service'
  );

  return (
    <div className="incident-panel card">

      {/* Header */}
      <div className="panel-header">
        <div className="panel-heading">
          <div className="panel-heading-icon">
            <Layers className="panel-heading-icon-svg" />
          </div>

          <div>
            <h3 className="panel-title">Failure Injection</h3>
            <p className="panel-subtitle">
              Simulate controlled microservice failure scenarios
            </p>
          </div>
        </div>

        <div className="incident-context">
          <div className="incident-context-item">
            <span className="context-label">INCIDENT</span>
            <span className="incident-id">
              {incidentId || '—'}
            </span>
          </div>

          <div className="context-divider" />

          <div className="incident-context-item">
            <span className="context-label">ACTIVE</span>
            <span
              className={`failure-count ${
                isMaxFailures ? 'failure-count-max' : ''
              }`}
            >
              {failureCount} / 2
            </span>
          </div>
        </div>
      </div>

      {/* Dual Failure Notice */}
      {failureCount === 2 && (
        <div className="dual-failure-banner">
          <AlertOctagon className="dual-failure-icon" />

          <div>
            <strong>Dual failure scenario active</strong>
            <span>
              Two concurrent failures are being analyzed independently by
              the RCA engine.
            </span>
          </div>
        </div>
      )}

      {/* Scenario Controls */}
      <div className="injection-buttons-grid">

        {/* Payment */}
        <button
          onClick={onInjectPayment}
          disabled={isLoading || (!hasPayment && isMaxFailures)}
          className={`btn-injection btn-payment ${
            hasPayment ? 'active' : ''
          }`}
          title="payment-service → order-service → api-gateway"
        >
          <div className="btn-icon-wrapper payment-icon">
            <Flame />
          </div>

          <div className="btn-content">
            <div className="btn-title-row">
              <span className="btn-title">
                Payment Failure
              </span>

              {hasPayment && (
                <span className="status-badge-active">
                  ACTIVE
                </span>
              )}
            </div>

            <span className="btn-subtitle">
              payment → order → API gateway
            </span>
          </div>
        </button>

        {/* Database */}
        <button
          onClick={onInjectDatabase}
          disabled={isLoading || (!hasDb && isMaxFailures)}
          className={`btn-injection btn-database ${
            hasDb ? 'active' : ''
          }`}
          title="database → payment-service → order-service → api-gateway"
        >
          <div className="btn-icon-wrapper database-icon">
            <Clock />
          </div>

          <div className="btn-content">
            <div className="btn-title-row">
              <span className="btn-title">
                Database Latency
              </span>

              {hasDb && (
                <span className="status-badge-active">
                  ACTIVE
                </span>
              )}
            </div>

            <span className="btn-subtitle">
              database → payment → order → API gateway
            </span>
          </div>
        </button>

        {/* Notification */}
        <button
          onClick={onInjectNotification}
          disabled={isLoading || (!hasNotif && isMaxFailures)}
          className={`btn-injection btn-notification ${
            hasNotif ? 'active' : ''
          }`}
          title="Isolated notification-service failure"
        >
          <div className="btn-icon-wrapper notification-icon">
            <BellOff />
          </div>

          <div className="btn-content">
            <div className="btn-title-row">
              <span className="btn-title">
                Notification Failure
              </span>

              {hasNotif && (
                <span className="status-badge-active">
                  ACTIVE
                </span>
              )}
            </div>

            <span className="btn-subtitle">
              isolated fault · no downstream cascade
            </span>
          </div>
        </button>
      </div>

      {/* Bottom Status / Reset */}
      <div className="panel-footer">

        <div
          className={`status-summary ${
            isHealthy ? 'healthy' : 'degraded'
          }`}
        >
          {isHealthy ? (
            <>
              <ShieldCheck className="status-summary-icon" />
              <span>System baseline healthy</span>
            </>
          ) : (
            <>
              <span className="status-summary-dot" />
              <span>
                Active:{' '}
                {activeFailures
                  .map((failure) => failure.service)
                  .join(', ')}
              </span>
            </>
          )}
        </div>

        <button
          onClick={onReset}
          disabled={isLoading}
          className="btn-reset"
          title="Restore all services to healthy state"
        >
          <RotateCcw />
          <span>Reset System</span>
        </button>
      </div>
    </div>
  );
};