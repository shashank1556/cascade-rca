import React from 'react';
import {
  Flame,
  Clock,
  BellOff,
  RotateCcw,
  ShieldCheck,
  AlertOctagon,
  Layers,
  Sparkles,
} from 'lucide-react';

export interface IncidentPanelProps {
  activeFailures: Array<{ incident_id: string; service: string; scenario: string }>;
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
    (f) => f.scenario.includes('payment') || f.service === 'payment-service'
  );
  const hasDb = activeFailures.some(
    (f) => f.scenario.includes('database') || f.service === 'database'
  );
  const hasNotif = activeFailures.some(
    (f) => f.scenario.includes('notification') || f.service === 'notification-service'
  );

  return (
    <div className="incident-panel card">
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <Layers className="w-5 h-5 text-rose-400" />
          <h3 className="panel-title">Failure Injection Controls</h3>
        </div>
        <div className="incident-badge-wrapper">
          {incidentId && (
            <span className="incident-pill">
              <span className="dot pulse"></span>
              {incidentId}
            </span>
          )}
          <span className={`capacity-badge ${isMaxFailures ? 'max' : ''}`}>
            Active Failures: {failureCount}/2
          </span>
        </div>
      </div>

      <p className="panel-description">
        Inject real-world cascading failure scenarios into the microservice dependency topology.
        The backend engine supports up to <strong>two concurrent failure injections</strong> to evaluate
        multi-component causal isolation.
      </p>

      {/* Dual Failure Notice */}
      {failureCount === 2 && (
        <div className="dual-failure-banner">
          <AlertOctagon className="w-5 h-5 text-amber-400 shrink-0" />
          <div className="text-sm">
            <strong className="text-amber-300 block font-medium">
              Dual Failure Injection Active
            </strong>
            <span className="text-slate-300">
              Two concurrent failures are active. The backend RCA engine analyzes independent failure
              propagation paths without falsely conflating unrelated cascades.
            </span>
          </div>
        </div>
      )}

      {/* Button Grid */}
      <div className="injection-buttons-grid">
        {/* Scenario 1 */}
        <button
          onClick={onInjectPayment}
          disabled={isLoading || (!hasPayment && isMaxFailures)}
          className={`btn-injection btn-payment ${hasPayment ? 'active' : ''}`}
          title="Simulate Scenario 1: payment-service → order-service → api-gateway"
        >
          <div className="btn-icon-wrapper">
            <Flame className="w-5 h-5 text-rose-400" />
          </div>
          <div className="btn-content">
            <div className="btn-title-row">
              <span className="btn-title">Inject Payment Failure</span>
              {hasPayment && <span className="status-badge-active">ACTIVE</span>}
            </div>
            <span className="btn-subtitle">
              payment-service → order-service → api-gateway
            </span>
          </div>
        </button>

        {/* Scenario 2 */}
        <button
          onClick={onInjectDatabase}
          disabled={isLoading || (!hasDb && isMaxFailures)}
          className={`btn-injection btn-database ${hasDb ? 'active' : ''}`}
          title="Simulate Scenario 2: database latency → payment → order → api-gateway"
        >
          <div className="btn-icon-wrapper">
            <Clock className="w-5 h-5 text-amber-400" />
          </div>
          <div className="btn-content">
            <div className="btn-title-row">
              <span className="btn-title">Inject Database Latency</span>
              {hasDb && <span className="status-badge-active">ACTIVE</span>}
            </div>
            <span className="btn-subtitle">
              database (2850ms) → payment → order → api-gateway
            </span>
          </div>
        </button>

        {/* Scenario 3 */}
        <button
          onClick={onInjectNotification}
          disabled={isLoading || (!hasNotif && isMaxFailures)}
          className={`btn-injection btn-notification ${hasNotif ? 'active' : ''}`}
          title="Simulate Scenario 3: isolated notification-service failure"
        >
          <div className="btn-icon-wrapper">
            <BellOff className="w-5 h-5 text-purple-400" />
          </div>
          <div className="btn-content">
            <div className="btn-title-row">
              <span className="btn-title">Inject Notification Failure</span>
              {hasNotif && <span className="status-badge-active">ACTIVE</span>}
            </div>
            <span className="btn-subtitle">
              notification-service (Isolated fault, no downstream cascade)
            </span>
          </div>
        </button>
      </div>

      {/* Action Footer */}
      <div className="panel-footer">
        <div className="status-summary">
          {isHealthy ? (
            <div className="flex items-center gap-2 text-emerald-400 text-sm font-medium">
              <ShieldCheck className="w-4 h-4" />
              <span>System Baseline: 100% Healthy (No Active Anomalies)</span>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-rose-400 text-sm font-medium">
              <Sparkles className="w-4 h-4 text-amber-400 animate-pulse" />
              <span>
                Anomalies Injected: {activeFailures.map((f) => f.service).join(', ')}
              </span>
            </div>
          )}
        </div>

        <button
          onClick={onReset}
          disabled={isLoading && isHealthy}
          className="btn-reset"
          title="Reset telemetry and restore all services to healthy state"
        >
          <RotateCcw className="w-4 h-4" />
          <span>Reset System to Healthy</span>
        </button>
      </div>
    </div>
  );
};
