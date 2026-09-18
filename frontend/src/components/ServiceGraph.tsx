import React from 'react';
import {
  Server,
  Database,
  Globe,
  Bell,
  CreditCard,
  ShoppingCart,
  UserCheck,
  Activity,
} from 'lucide-react';
import type { ServiceName } from '../api';

export interface ServiceGraphProps {
  rootCauseService: string | null;
  affectedServices: string[];
  independentServices: string[];
  propagationEdges: Array<{ from: string; to: string }>;
  selectedService: string | null;
  onSelectService: (service: string) => void;
  activeFailuresCount: number;
}

interface NodeLayout {
  id: ServiceName;
  name: string;
  role: string;
  x: number;
  y: number;
  icon: React.ReactNode;
  type: 'gateway' | 'service' | 'database';
}

const NODES: NodeLayout[] = [
  // Tier 0: Ingress Gateway
  {
    id: 'api-gateway',
    name: 'api-gateway',
    role: 'API Ingress & Routing',
    x: 420,
    y: 60,
    icon: <Globe className="w-5 h-5 text-sky-400" />,
    type: 'gateway',
  },
  // Tier 1: Core Business Services
  {
    id: 'user-service',
    name: 'user-service',
    role: 'User Auth & Profiles',
    x: 140,
    y: 190,
    icon: <UserCheck className="w-5 h-5 text-indigo-400" />,
    type: 'service',
  },
  {
    id: 'order-service',
    name: 'order-service',
    role: 'Checkout & Order State',
    x: 420,
    y: 190,
    icon: <ShoppingCart className="w-5 h-5 text-amber-400" />,
    type: 'service',
  },
  {
    id: 'product-service',
    name: 'product-service',
    role: 'Catalog & Inventory',
    x: 700,
    y: 190,
    icon: <Server className="w-5 h-5 text-cyan-400" />,
    type: 'service',
  },
  // Tier 2: Downstream Services
  {
    id: 'notification-service',
    name: 'notification-service',
    role: 'Push & Email Alerts',
    x: 230,
    y: 330,
    icon: <Bell className="w-5 h-5 text-purple-400" />,
    type: 'service',
  },
  {
    id: 'payment-service',
    name: 'payment-service',
    role: 'Payment Processing',
    x: 520,
    y: 330,
    icon: <CreditCard className="w-5 h-5 text-rose-400" />,
    type: 'service',
  },
  // Tier 3: Persistence Layer
  {
    id: 'database',
    name: 'database',
    role: 'Primary PostgreSQL Storage',
    x: 520,
    y: 470,
    icon: <Database className="w-5 h-5 text-emerald-400" />,
    type: 'database',
  },
];

interface EdgeLayout {
  from: ServiceName;
  to: ServiceName;
}

const EDGES: EdgeLayout[] = [
  { from: 'api-gateway', to: 'user-service' },
  { from: 'api-gateway', to: 'order-service' },
  { from: 'api-gateway', to: 'product-service' },
  { from: 'order-service', to: 'notification-service' },
  { from: 'order-service', to: 'payment-service' },
  { from: 'payment-service', to: 'database' },
];

export const ServiceGraph: React.FC<ServiceGraphProps> = ({
  rootCauseService,
  affectedServices,
  independentServices,
  propagationEdges,
  selectedService,
  onSelectService,
  activeFailuresCount,
}) => {
  // Purely derives node state from backend state props
  const getNodeState = (serviceId: ServiceName): 'healthy' | 'root-cause' | 'affected' | 'independent-failure' => {
    if (serviceId === rootCauseService) {
      return 'root-cause';
    }
    if (independentServices.includes(serviceId)) {
      return 'independent-failure';
    }
    if (affectedServices.includes(serviceId)) {
      return 'affected';
    }
    return 'healthy';
  };

  // Edge cascade state reflects backend propagation events or failing edge status
  const isEdgeInCascade = (from: ServiceName, to: ServiceName): boolean => {
    // 1. Check if backend emitted this edge in cascade_propagation or /graph
    const matchedBackendPropagation = propagationEdges.some(
      (e) => (e.from === from && e.to === to) || (e.from === to && e.to === from)
    );
    if (matchedBackendPropagation) {
      return true;
    }

    // 2. Check if both endpoints are active in the primary cascade chain
    const fromState = getNodeState(from);
    const toState = getNodeState(to);
    if (
      (fromState === 'root-cause' || fromState === 'affected') &&
      (toState === 'root-cause' || toState === 'affected')
    ) {
      // Notification-service is isolated; never connect it to payment cascade
      if (
        (from === 'order-service' && to === 'notification-service') ||
        (to === 'order-service' && from === 'notification-service')
      ) {
        return false;
      }
      return true;
    }

    return false;
  };

  const getNodePos = (id: ServiceName) => {
    const node = NODES.find((n) => n.id === id);
    return node ? { x: node.x, y: node.y } : { x: 0, y: 0 };
  };

  return (
    <div className="service-graph-container">
      <div className="graph-header">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-400" />
          <h3 className="text-lg font-semibold text-white tracking-wide">
            Microservice Dependency Topology
          </h3>
        </div>
        <div className="graph-legend">
          <div className="legend-item">
            <span className="legend-dot healthy"></span>
            <span>Healthy (200 OK)</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot root-cause"></span>
            <span>Identified Root Cause</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot affected"></span>
            <span>Cascaded Error</span>
          </div>
          <div className="legend-item">
            <span className="legend-dot independent"></span>
            <span>Independent Failure</span>
          </div>
        </div>
      </div>

      <div className="graph-canvas-wrapper">
        <svg
          viewBox="0 0 860 550"
          className="graph-svg"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            {/* Arrowhead markers */}
            <marker
              id="arrow-default"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#475569" />
            </marker>

            <marker
              id="arrow-cascade"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#f43f5e" />
            </marker>

            {/* Glowing filter effects */}
            <filter id="glow-root" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="8" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
            <filter id="glow-affected" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
            <filter id="glow-independent" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="7" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Dependency Connector Lines */}
          <g className="edges-layer">
            {EDGES.map((edge) => {
              const start = getNodePos(edge.from);
              const end = getNodePos(edge.to);
              const isCascade = isEdgeInCascade(edge.from, edge.to);

              const deltaY = end.y - start.y;
              const controlY = start.y + deltaY * 0.5;
              const pathD = `M ${start.x} ${start.y + 24} C ${start.x} ${controlY}, ${end.x} ${controlY}, ${end.x} ${end.y - 24}`;

              return (
                <g key={`${edge.from}->${edge.to}`} className="edge-group">
                  <path
                    d={pathD}
                    className={`edge-path ${isCascade ? 'edge-cascade' : 'edge-normal'}`}
                    markerEnd={isCascade ? 'url(#arrow-cascade)' : 'url(#arrow-default)'}
                  />
                  {isCascade && (
                    <circle r="4" className="edge-cascade-particle">
                      <animateMotion
                        path={pathD}
                        dur="1.8s"
                        repeatCount="indefinite"
                        keyPoints="1;0"
                        keyTimes="0;1"
                      />
                    </circle>
                  )}
                </g>
              );
            })}
          </g>

          {/* Service Nodes */}
          <g className="nodes-layer">
            {NODES.map((node) => {
              const state = getNodeState(node.id);
              const isSelected = selectedService === node.id;

              return (
                <g
                  key={node.id}
                  transform={`translate(${node.x - 85}, ${node.y - 32})`}
                  className={`node-group node-${state} ${isSelected ? 'node-selected' : ''}`}
                  onClick={() => onSelectService(node.id)}
                  style={{ cursor: 'pointer' }}
                >
                  {/* Outer pulse wave for root cause */}
                  {state === 'root-cause' && (
                    <rect
                      x="-6"
                      y="-6"
                      width="182"
                      height="76"
                      rx="16"
                      className="pulse-rect"
                    />
                  )}

                  {/* Main Node Box */}
                  <rect
                    x="0"
                    y="0"
                    width="170"
                    height="64"
                    rx="12"
                    className="node-box"
                  />

                  {/* Header background bar */}
                  <rect
                    x="0"
                    y="0"
                    width="170"
                    height="28"
                    rx="12"
                    className="node-header-bar"
                  />

                  {/* Status Indicator Pill */}
                  <g transform="translate(10, 8)">
                    {state === 'healthy' && (
                      <circle cx="4" cy="6" r="4" fill="#10b981" />
                    )}
                    {state === 'root-cause' && (
                      <circle cx="4" cy="6" r="4" fill="#f43f5e" />
                    )}
                    {state === 'affected' && (
                      <circle cx="4" cy="6" r="4" fill="#f59e0b" />
                    )}
                    {state === 'independent-failure' && (
                      <circle cx="4" cy="6" r="4" fill="#a855f7" />
                    )}
                  </g>

                  {/* Node Title */}
                  <text
                    x="26"
                    y="18"
                    className="node-title"
                  >
                    {node.name}
                  </text>

                  {/* Subtitle / Role */}
                  <text
                    x="12"
                    y="42"
                    className="node-role"
                  >
                    {node.role}
                  </text>

                  {/* State Badge with clean UTF-8 */}
                  <g transform="translate(10, 48)">
                    {state === 'healthy' && (
                      <text x="0" y="8" className="badge-text healthy">
                        • 200 OK • Healthy
                      </text>
                    )}
                    {state === 'root-cause' && (
                      <text x="0" y="8" className="badge-text root-cause">
                        ▲ ROOT CAUSE
                      </text>
                    )}
                    {state === 'affected' && (
                      <text x="0" y="8" className="badge-text affected">
                        ⚠ CASCADED ERROR
                      </text>
                    )}
                    {state === 'independent-failure' && (
                      <text x="0" y="8" className="badge-text independent">
                        ◆ INDEPENDENT FAULT
                      </text>
                    )}
                  </g>
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      <div className="graph-footer-info">
        <div className="info-stat">
          <span className="text-slate-400">Total Services:</span>
          <strong className="text-slate-200">7 Active</strong>
        </div>
        <div className="info-stat">
          <span className="text-slate-400">Propagation Direction:</span>
          <strong className="text-slate-200">
            {rootCauseService ? `${rootCauseService} → Callers` : 'Normal Operations'}
          </strong>
        </div>
        <div className="info-stat">
          <span className="text-slate-400">Active Failure Components:</span>
          <strong className="text-indigo-300">
            {activeFailuresCount === 0
              ? 'None (Healthy)'
              : activeFailuresCount === 1
              ? '1 Failure Active'
              : '2 Simultaneous Failures'}
          </strong>
        </div>
      </div>
    </div>
  );
};
