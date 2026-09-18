import React, { useEffect, useMemo, useRef } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import type cytoscape from 'cytoscape';
import { Activity } from 'lucide-react';
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
  type: 'gateway' | 'service' | 'database';
}

const NODES: NodeLayout[] = [
  {
    id: 'api-gateway',
    name: 'api-gateway',
    role: 'API Ingress & Routing',
    x: 420,
    y: 60,
    type: 'gateway',
  },
  {
    id: 'user-service',
    name: 'user-service',
    role: 'User Auth & Profiles',
    x: 140,
    y: 190,
    type: 'service',
  },
  {
    id: 'order-service',
    name: 'order-service',
    role: 'Checkout & Order State',
    x: 420,
    y: 190,
    type: 'service',
  },
  {
    id: 'product-service',
    name: 'product-service',
    role: 'Catalog & Inventory',
    x: 700,
    y: 190,
    type: 'service',
  },
  {
    id: 'notification-service',
    name: 'notification-service',
    role: 'Push & Email Alerts',
    x: 230,
    y: 330,
    type: 'service',
  },
  {
    id: 'payment-service',
    name: 'payment-service',
    role: 'Payment Processing',
    x: 520,
    y: 330,
    type: 'service',
  },
  {
    id: 'database',
    name: 'database',
    role: 'Primary PostgreSQL Storage',
    x: 520,
    y: 470,
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

type NodeState =
  | 'healthy'
  | 'root-cause'
  | 'affected'
  | 'independent-failure';

const getNodeState = (
  serviceId: ServiceName,
  rootCauseService: string | null,
  affectedServices: string[],
  independentServices: string[],
): NodeState => {
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

const NODE_LABELS: Record<NodeState, string> = {
  healthy: '• 200 OK • Healthy',
  'root-cause': '▲ ROOT CAUSE',
  affected: '⚠ CASCADED ERROR',
  'independent-failure': '◆ INDEPENDENT FAULT',
};

export const ServiceGraph: React.FC<ServiceGraphProps> = ({
  rootCauseService,
  affectedServices,
  independentServices,
  propagationEdges,
  selectedService,
  onSelectService,
  activeFailuresCount,
}) => {
  const cyRef = useRef<cytoscape.Core | null>(null);

  /*
   * Node state comes exclusively from backend RCA state.
   * Frontend does not perform causal inference.
   */
  const nodeStates = useMemo(() => {
    const states: Record<string, NodeState> = {};

    for (const node of NODES) {
      states[node.id] = getNodeState(
        node.id,
        rootCauseService,
        affectedServices,
        independentServices,
      );
    }

    return states;
  }, [rootCauseService, affectedServices, independentServices]);

  /*
   * Build Cytoscape elements.
   *
   * Dependency edges = normal architecture.
   * Cascade edges = explicit backend propagation events.
   */
  const elements = useMemo(() => {
    const nodes = NODES.map((node) => {
      const state = nodeStates[node.id];

      return {
        data: {
          id: node.id,
          label: `${node.name}\n${node.role}\n${NODE_LABELS[state]}`,
          serviceName: node.name,
          role: node.role,
          state,
        },
        position: {
          x: node.x,
          y: node.y,
        },
      };
    });

    const dependencyEdges = EDGES.map((edge) => ({
      data: {
        id: `dependency-${edge.from}-${edge.to}`,
        source: edge.from,
        target: edge.to,
        edgeType: 'dependency',
      },
    }));

    const cascadeEdges = propagationEdges.map((edge, index) => ({
      data: {
        id: `cascade-${edge.from}-${edge.to}-${index}`,
        source: edge.from,
        target: edge.to,
        edgeType: 'cascade',
      },
    }));

    return [...nodes, ...dependencyEdges, ...cascadeEdges];
  }, [nodeStates, propagationEdges]);

  /*
   * Clean light-theme Cytoscape styling.
   */
  const stylesheet = useMemo<cytoscape.StylesheetStyle[]>(() => {
    return [
      {
        selector: 'node',
        style: {
          shape: 'roundrectangle',
          width: 190,
          height: 82,
          'background-color': '#ffffff',
          'border-width': 1.5,
          'border-color': '#cbd5e1',
          color: '#0f172a',
          label: 'data(label)',
          'font-family': 'Inter, sans-serif',
          'font-size': 11,
          'font-weight': 600,
          'text-wrap': 'wrap',
          'text-max-width': '175px',
          'text-valign': 'center',
          'text-halign': 'center',
          'line-height': 1.3,
          'overlay-opacity': 0,
        } as cytoscape.Css.Node,
      },

      {
        selector: 'node[state = "healthy"]',
        style: {
          'border-color': '#86efac',
          'border-width': 1.5,
          'background-color': '#ffffff',
        } as cytoscape.Css.Node,
      },

      {
        selector: 'node[state = "affected"]',
        style: {
          'border-color': '#f59e0b',
          'border-width': 2,
          'background-color': '#fffbeb',
        } as cytoscape.Css.Node,
      },

      {
        selector: 'node[state = "root-cause"]',
        style: {
          'border-color': '#ef4444',
          'border-width': 3,
          'background-color': '#fff1f2',
        } as cytoscape.Css.Node,
      },

      {
        selector: 'node[state = "independent-failure"]',
        style: {
          'border-color': '#8b5cf6',
          'border-width': 2,
          'background-color': '#f5f3ff',
        } as cytoscape.Css.Node,
      },

      {
        selector: 'node:selected',
        style: {
          'border-width': 3,
          'border-color': '#2563eb',
          'background-color': '#eff6ff',
        } as cytoscape.Css.Node,
      },

      {
        selector: 'edge[edgeType = "dependency"]',
        style: {
          width: 1.5,
          'line-color': '#94a3b8',
          'target-arrow-color': '#94a3b8',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          opacity: 0.8,
        } as cytoscape.Css.Edge,
      },

      {
        selector: 'edge[edgeType = "cascade"]',
        style: {
          width: 4,
          'line-color': '#ef4444',
          'target-arrow-color': '#ef4444',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          opacity: 1,
          'line-style': 'solid',
        } as cytoscape.Css.Edge,
      },
    ];
  }, []);

  /* Service selection */
  useEffect(() => {
    const cy = cyRef.current;

    if (!cy) {
      return;
    }

    const handleNodeTap = (event: cytoscape.EventObject) => {
      const nodeId = event.target.id();
      onSelectService(nodeId);
    };

    cy.on('tap', 'node', handleNodeTap);

    return () => {
      cy.removeListener('tap', 'node', handleNodeTap);
    };
  }, [onSelectService]);

  /* Synchronize external selection with Cytoscape */
  useEffect(() => {
    const cy = cyRef.current;

    if (!cy) {
      return;
    }

    cy.nodes().unselect();

    if (selectedService) {
      const node = cy.getElementById(selectedService);

      if (node.length > 0) {
        node.select();
      }
    }
  }, [selectedService, elements]);

  /*
   * Keep the topology fixed during the demo.
   * fit=false preserves user zoom/pan.
   */
  useEffect(() => {
    const cy = cyRef.current;

    if (!cy) {
      return;
    }

    cy.layout({
      name: 'preset',
      fit: false,
      padding: 40,
      animate: false,
    }).run();

    cy.resize();
  }, [elements]);

  return (
    <div className="service-graph-container">

      {/* Graph Header */}
      <div className="graph-header">
        <div className="graph-title-group">
          <div className="graph-title-icon">
            <Activity />
          </div>

          <div>
            <h3 className="graph-title">
              Microservice Dependency Topology
            </h3>

            <p className="graph-subtitle">
              Live service relationships and failure propagation
            </p>
          </div>
        </div>

        <div className="graph-legend">
          <div className="legend-item">
            <span className="legend-dot healthy" />
            <span>Healthy</span>
          </div>

          <div className="legend-item">
            <span className="legend-dot root-cause" />
            <span>Root Cause</span>
          </div>

          <div className="legend-item">
            <span className="legend-dot affected" />
            <span>Cascaded</span>
          </div>

          <div className="legend-item">
            <span className="legend-dot independent" />
            <span>Independent</span>
          </div>
        </div>
      </div>

      {/* Graph */}
      <div className="graph-canvas-wrapper">
        <CytoscapeComponent
          cy={(cy: cytoscape.Core) => {
            cyRef.current = cy;
          }}
          elements={elements}
          stylesheet={stylesheet}
          style={{
            width: '100%',
            height: '100%',
            display: 'block',
          }}
          minZoom={0.45}
          maxZoom={2}
          wheelSensitivity={0.2}
          boxSelectionEnabled={false}
          autounselectify={false}
          userZoomingEnabled
          userPanningEnabled
          zoomingEnabled
          panningEnabled
          autoungrabify
          layout={{
            name: 'preset',
            fit: false,
            padding: 40,
            animate: false,
          }}
        />
      </div>

      {/* Graph Information */}
      <div className="graph-footer-info">

        <div className="info-stat">
          <span className="info-stat-label">
            Services
          </span>
          <strong>
            7
          </strong>
        </div>

        <div className="info-stat">
          <span className="info-stat-label">
            Propagation
          </span>

          <strong>
            {rootCauseService
              ? `${rootCauseService} → Callers`
              : 'Normal Operations'}
          </strong>
        </div>

        <div className="info-stat">
          <span className="info-stat-label">
            Active Failures
          </span>

          <strong className="info-stat-accent">
            {activeFailuresCount === 0
              ? 'None'
              : activeFailuresCount === 1
                ? '1 Active'
                : '2 Simultaneous'}
          </strong>
        </div>

      </div>
    </div>
  );
};