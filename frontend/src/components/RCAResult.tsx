import React from 'react';
import {
  BrainCircuit,
  CheckCircle2,
  TrendingUp,
  ArrowRight,
  Sparkles,
  Info,
} from 'lucide-react';
import type { RCAResult as RCAResultType } from '../api';

export interface RCAResultProps {
  rca: RCAResultType | null;
  isLoading: boolean;
  independentServices?: string[];
}

export const RCAResult: React.FC<RCAResultProps> = ({
  rca,
  isLoading,
  independentServices = [],
}) => {
  if (isLoading) {
    return (
      <div className="rca-card card loading-card">
        <div className="skeleton-pulse flex flex-col gap-4 p-4">
          <div className="h-6 bg-slate-800 rounded w-1/3"></div>
          <div className="h-20 bg-slate-800 rounded"></div>
          <div className="h-12 bg-slate-800 rounded"></div>
        </div>
      </div>
    );
  }

  if (!rca) {
    return (
      <div className="rca-card card empty-state">
        <div className="flex flex-col items-center justify-center p-8 text-center">
          <div className="icon-circle mb-3">
            <CheckCircle2 className="w-8 h-8 text-emerald-400" />
          </div>
          <h4 className="text-lg font-semibold text-slate-200">
            All Services Operating Normally
          </h4>
          <p className="text-sm text-slate-400 max-w-sm mt-1">
            No cascading anomalies detected. Inject a failure scenario using the controls above
            to observe real-time causal backpropagation.
          </p>
        </div>
      </div>
    );
  }

  const confidencePct = Math.round(rca.root_cause.confidence * 100);

  return (
    <div className="rca-card card">
      {/* Card Header */}
      <div className="card-header-bar">
        <div className="flex items-center gap-2">
          <BrainCircuit className="w-5 h-5 text-indigo-400" />
          <h3 className="text-base font-bold text-white">Root Cause Analysis (RCA)</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="status-badge status-resolved">
            {rca.status.toUpperCase()}
          </span>
          <span className="incident-id-tag font-mono text-xs text-slate-400">
            {rca.incident_id}
          </span>
        </div>
      </div>

      {/* Primary Root Cause Hero Box */}
      <div className="root-cause-hero">
        <div className="root-cause-info">
          <span className="hero-label">IDENTIFIED ROOT CAUSE</span>
          <div className="service-name-row">
            <h2 className="root-service-title">{rca.root_cause.service}</h2>
            <span className="causal-tag">RCA Engine Result</span>
          </div>
          <p className="hero-subtext">
            Determined by backend causal backpropagation and temporal onset analysis.
          </p>
        </div>

        {/* Confidence Meter */}
        <div className="confidence-meter-container">
          <div className="confidence-circle">
            <svg viewBox="0 0 36 36" className="circular-chart">
              <path
                className="circle-bg"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
              <path
                className="circle"
                strokeDasharray={`${confidencePct}, 100`}
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              />
            </svg>
            <div className="confidence-number">
              <span className="pct font-mono">{rca.root_cause.confidence.toFixed(2)}</span>
              <span className="label">SCORE</span>
            </div>
          </div>
          <div className="confidence-label-text">
            <TrendingUp className="w-3.5 h-3.5 text-emerald-400 inline mr-1" />
            <span>Causal Score ({confidencePct}%)</span>
          </div>
        </div>
      </div>

      {/* Independent Failure Callout (When backend reports concurrent independent faults) */}
      {independentServices.length > 0 && (
        <div className="independent-failure-callout">
          <div className="flex items-start gap-2.5">
            <Info className="w-5 h-5 text-purple-400 shrink-0 mt-0.5" />
            <div>
              <strong className="text-purple-300 font-semibold block text-sm">
                Concurrent Independent Fault: {independentServices.join(', ')}
              </strong>
              <p className="text-xs text-slate-300 mt-1 leading-relaxed">
                Backend state indicates independent failure activity occurring concurrently with the
                primary cascade. The causal analysis keeps these failure boundaries isolated.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Affected Downstream Services */}
      <div className="section-block">
        <h4 className="section-label">Cascaded Services Affected</h4>
        {rca.affected_services.length === 0 ? (
          <span className="text-xs text-slate-400 italic">
            None. Failure remained contained within isolated boundary.
          </span>
        ) : (
          <div className="affected-services-flow">
            <span className="service-pill root">{rca.root_cause.service}</span>
            {rca.affected_services.map((svc) => (
              <React.Fragment key={svc}>
                <ArrowRight className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                <span className="service-pill affected">{svc}</span>
              </React.Fragment>
            ))}
          </div>
        )}
      </div>

      {/* Gemini Narration Layer / Causal Explanation */}
      <div className="section-block explanation-box">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300 uppercase tracking-wider">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>Causal Explanation</span>
          </div>
          <span className="engine-source-pill">Gemini Narration</span>
        </div>
        <p className="explanation-text">
          {rca.explanation || 'Explanation unavailable.'}
        </p>
      </div>
    </div>
  );
};
