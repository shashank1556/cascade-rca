declare module 'react-cytoscapejs' {
  import type { ComponentType } from 'react';
  import type cytoscape from 'cytoscape';

  interface CytoscapeComponentProps {
    elements?: cytoscape.ElementDefinition[];
    stylesheet?: cytoscape.StylesheetStyle[];
    style?: React.CSSProperties;
    cy?: (cy: cytoscape.Core) => void;

    minZoom?: number;
    maxZoom?: number;
    wheelSensitivity?: number;
    boxSelectionEnabled?: boolean;
    autounselectify?: boolean;
    userZoomingEnabled?: boolean;
    userPanningEnabled?: boolean;
    zoomingEnabled?: boolean;
    panningEnabled?: boolean;
    autoungrabify?: boolean;

    layout?: cytoscape.LayoutOptions;
    className?: string;
  }

  const CytoscapeComponent: ComponentType<CytoscapeComponentProps>;

  export default CytoscapeComponent;
}