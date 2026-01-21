/**
 * ReactFlow theme configuration for the Visual Builder
 * Aligned with Chakra UI brand theme and builder spec (Section 6)
 */

// Node category colors (from spec 6.3.1)
export const nodeColors = {
  program: '#8B5CF6',   // Purple
  model: '#EC4899',     // Pink
  primitive: '#3B82F6', // Blue
  utility: '#10B981',   // Green
  error: '#EF4444',     // Red
} as const;

// Node execution state styles (from spec 6.10.1)
export const executionStateStyles = {
  idle: {
    borderColor: '#9CA3AF', // gray-400
    animation: null,
    icon: null,
    opacity: 1,
  },
  queued: {
    borderColor: '#FBBF24', // yellow-400
    animation: 'pulse',
    icon: 'clock',
    opacity: 1,
  },
  running: {
    borderColor: '#3B82F6', // blue-500
    animation: 'spin',
    icon: 'loader',
    opacity: 1,
  },
  succeeded: {
    borderColor: '#10B981', // green-500
    animation: null,
    icon: 'check',
    opacity: 1,
  },
  failed: {
    borderColor: '#EF4444', // red-500
    animation: null,
    icon: 'x',
    opacity: 1,
  },
  skipped: {
    borderColor: '#9CA3AF', // gray-400
    animation: null,
    icon: 'skip',
    opacity: 0.5,
  },
  cancelled: {
    borderColor: '#F97316', // orange-500
    animation: null,
    icon: 'stop',
    opacity: 1,
  },
} as const;

export type NodeCategory = keyof typeof nodeColors;
export type NodeExecutionState = keyof typeof executionStateStyles;

// ReactFlow default styles with custom theme
export const reactFlowStyles = {
  // Canvas background
  background: {
    color: '#F9FAFB',     // gray.50
    gap: 16,
    size: 1,
    variant: 'dots' as const,
  },

  // Default edge styles
  edge: {
    default: {
      stroke: '#9CA3AF',
      strokeWidth: 2,
      animated: false,
    },
    selected: {
      stroke: '#0073e6', // brand.500
      strokeWidth: 3,
    },
  },

  // Default node styles
  node: {
    width: 280,
    minHeight: 100,
    borderRadius: 8,
    borderWidth: 2,
    shadow: '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
    shadowSelected: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
  },

  // Handle styles
  handle: {
    size: 10,
    background: '#ffffff',
    border: '2px solid',
    borderRadius: '50%',
  },

  // Minimap styles
  minimap: {
    nodeColor: (node: { data?: { category?: NodeCategory } }) => {
      const category = node.data?.category;
      return category ? nodeColors[category] : '#9CA3AF';
    },
    nodeStrokeWidth: 2,
    maskColor: 'rgba(0, 0, 0, 0.1)',
  },

  // Controls styles
  controls: {
    buttonBgColor: '#ffffff',
    buttonBgColorHover: '#F3F4F6',
    buttonColor: '#374151',
    buttonBorderColor: '#E5E7EB',
  },
} as const;

// Edge color based on source node category (from spec 6.4.2)
export function getEdgeColor(sourceCategory?: NodeCategory): string {
  if (!sourceCategory) return reactFlowStyles.edge.default.stroke;
  return nodeColors[sourceCategory] || reactFlowStyles.edge.default.stroke;
}

// Default node styling based on category
export function getDefaultNodeStyle(category?: NodeCategory) {
  return {
    width: reactFlowStyles.node.width,
    borderRadius: reactFlowStyles.node.borderRadius,
    borderWidth: reactFlowStyles.node.borderWidth,
    borderStyle: 'solid' as const,
    borderColor: category ? nodeColors[category] : '#9CA3AF',
    boxShadow: reactFlowStyles.node.shadow,
    backgroundColor: '#ffffff',
  };
}

// CSS styles for ReactFlow container
export const reactFlowContainerStyles = `
  .react-flow__node {
    font-family: Inter, system-ui, sans-serif;
  }

  .react-flow__node.selected {
    box-shadow: ${reactFlowStyles.node.shadowSelected};
  }

  .react-flow__handle {
    width: ${reactFlowStyles.handle.size}px;
    height: ${reactFlowStyles.handle.size}px;
    background: ${reactFlowStyles.handle.background};
    border-radius: ${reactFlowStyles.handle.borderRadius};
  }

  .react-flow__edge-path {
    stroke-linecap: round;
  }

  .react-flow__edge.selected .react-flow__edge-path {
    stroke: ${reactFlowStyles.edge.selected.stroke};
    stroke-width: ${reactFlowStyles.edge.selected.strokeWidth};
  }

  .react-flow__background {
    background-color: ${reactFlowStyles.background.color};
  }

  .react-flow__controls {
    box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1);
    border-radius: 8px;
    overflow: hidden;
  }

  .react-flow__controls-button {
    background: ${reactFlowStyles.controls.buttonBgColor};
    border-color: ${reactFlowStyles.controls.buttonBorderColor};
    color: ${reactFlowStyles.controls.buttonColor};
  }

  .react-flow__controls-button:hover {
    background: ${reactFlowStyles.controls.buttonBgColorHover};
  }

  .react-flow__minimap {
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1);
  }

  /* Node execution state animations */
  @keyframes node-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
  }

  @keyframes node-spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .node-state-queued {
    animation: node-pulse 1.5s ease-in-out infinite;
  }

  .node-state-running .node-icon {
    animation: node-spin 1s linear infinite;
  }

  /* Connection feedback styles */
  .react-flow__handle.connecting {
    animation: handle-pulse 1s ease-in-out infinite;
  }

  .react-flow__handle.valid-target {
    box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.4);
    border-color: #10B981 !important;
  }

  .react-flow__handle.invalid-target {
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.4);
    border-color: #EF4444 !important;
    cursor: not-allowed;
  }

  @keyframes handle-pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.2); }
  }

  /* Dim non-valid handles during connection */
  .react-flow.connecting .react-flow__handle:not(.valid-target):not(.source-handle) {
    opacity: 0.4;
  }

  /* Highlight source handle */
  .react-flow__handle.source-handle {
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.4);
  }
`;
