import React, { useState, useEffect } from 'react';
import { Activity } from 'lucide-react';
import { ServiceGraph } from './components/ServiceGraph';
import { IncidentPanel } from './components/IncidentPanel';
import { RCAResult } from './components/RCAResult';
import { Timeline } from './components/Timeline';
import { CommitCard } from './components/CommitCard';
import type { RCAResult as RCAResultType } from './api';
import {
  simulatePaymentFailure,
  simulateDatabaseLatency,
  simulateNotificationFailure,
  resetSimulation,
  getRCAResult,
  getMockRCAResult,
} from './api';

export const App: React.FC = () => {
  // Application starts in a HEALTHY state
  const [activeFailures, setActiveFailures] = useState<string[]>([]);
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [rca, setRca] = useState<RCAResultType | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [selectedService, setSelectedService] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState<string>('');

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

  // Update RCA result when activeFailures change
  const refreshRCA = async (failures: string[], incId: string | null) => {
    if (failures.length === 0) {
      setRca(null);
      return;
    }
    setIsLoading(true);
    try {
      const targetId = incId || 'INC-001';
      // Attempt backend API, with fallback to deterministic mock contract
      const result = await getRCAResult(targetId);
      // Ensure multi-failure state is accurately reflected
      if (failures.length > 0 && (!result || result.root_cause.confidence === 0)) {
        setRca(getMockRCAResult(targetId, failures));
      } else {
        // If backend returned single-failure RCA but we have dual failures, enrich with dual failure representation
        if (failures.length === 2 && failures.includes('notification_failure')) {
          setRca(getMockRCAResult(targetId, failures));
        } else {
          setRca(result);
        }
      }
    } catch {
      setRca(getMockRCAResult(incId || 'INC-001', failures));
    } finally {
      setIsLoading(false);
    }
  };

  // Scenario 1: Payment Failure
  const handleInjectPayment = async () => {
    if (activeFailures.includes('payment_failure')) return;
    if (activeFailures.length >= 2) return;

    setIsLoading(true);
    const newFailures = [...activeFailures, 'payment_failure'];
    setActiveFailures(newFailures);

    try {
      const resp = await simulatePaymentFailure();
      const currentIncId = resp.incident_id || incidentId || 'INC-001';
      setIncidentId(currentIncId);
      await refreshRCA(newFailures, currentIncId);
    } catch {
      const currentIncId = incidentId || 'INC-001';
      setIncidentId(currentIncId);
      setRca(getMockRCAResult(currentIncId, newFailures));
    } finally {
      setIsLoading(false);
    }
  };

  // Scenario 2: Database Latency
  const handleInjectDatabase = async () => {
    if (activeFailures.includes('database_latency')) return;
    if (activeFailures.length >= 2) return;

    setIsLoading(true);
    const newFailures = [...activeFailures, 'database_latency'];
    setActiveFailures(newFailures);

    try {
      const resp = await simulateDatabaseLatency();
      const currentIncId = resp.incident_id || incidentId || 'INC-002';
      setIncidentId(currentIncId);
      await refreshRCA(newFailures, currentIncId);
    } catch {
      const currentIncId = incidentId || 'INC-002';
      setIncidentId(currentIncId);
      setRca(getMockRCAResult(currentIncId, newFailures));
    } finally {
      setIsLoading(false);
    }
  };

  // Scenario 3: Notification Failure
  const handleInjectNotification = async () => {
    if (activeFailures.includes('notification_failure')) return;
    if (activeFailures.length >= 2) return;

    setIsLoading(true);
    const newFailures = [...activeFailures, 'notification_failure'];
    setActiveFailures(newFailures);

    try {
      const resp = await simulateNotificationFailure();
      const currentIncId = resp.incident_id || incidentId || 'INC-003';
      setIncidentId(currentIncId);
      await refreshRCA(newFailures, currentIncId);
    } catch {
      const currentIncId = incidentId || 'INC-003';
      setIncidentId(currentIncId);
      setRca(getMockRCAResult(currentIncId, newFailures));
    } finally {
      setIsLoading(false);
    }
  };

  // Reset to clean healthy baseline
  const handleReset = async () => {
    setIsLoading(true);
    try {
      await resetSimulation();
    } catch {
      // Offline fallback
    } finally {
      setActiveFailures([]);
      setIncidentId(null);
      setRca(null);
      setSelectedService(null);
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
            activeFailures={activeFailures}
            rootCauseService={rca?.root_cause.service || null}
            affectedServices={rca?.affected_services || []}
            selectedService={selectedService}
            onSelectService={setSelectedService}
          />
        </section>

        {/* Right Column: RCA Intelligence, Timeline, Commit Correlation */}
        <section className="right-column">
          {/* Canonical RCA Result Card */}
          <RCAResult
            rca={rca}
            isLoading={isLoading}
            activeFailures={activeFailures}
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
