import { useCallback, useMemo, useEffect, useRef } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  useReactFlow,
  Connection,
  Node,
  Edge,
  BackgroundVariant,
  NodeTypes,
  EdgeTypes,
  ConnectionMode,
  SelectionMode,
  OnNodesChange,
  OnEdgesChange,
  Viewport,
  OnConnectStartParams,
  ReactFlowProvider,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Box } from '@chakra-ui/react';
import {
  reactFlowStyles,
  reactFlowContainerStyles,
  nodeColors,
  NodeCategory,
} from './theme';
import { validateConnection } from './utils';
import { ValidationConnectionLine } from './edges';
import { useConnectionFeedback } from './ConnectionFeedback';
import type { MelleaNodeData } from './CompositionContext';
import { SIDEBAR_DRAG_TYPE } from './BuilderSidebar';

/** Data format for items dropped from sidebar */
export interface SidebarDropData {
  id: string;
  type: string;
  label: string;
  description: string;
  category: string;
  assetId?: string;
  defaultData?: Record<string, unknown>;
}

// Props for the Canvas component
interface CanvasProps {
  // Standalone mode props (when not using CompositionContext)
  initialNodes?: Node[];
  initialEdges?: Edge[];

  // Connected mode props (when using CompositionContext)
  nodes?: Node[];
  edges?: Edge[];
  onNodesChange?: OnNodesChange;
  onEdgesChange?: OnEdgesChange;
  onConnect?: (connection: Connection) => void;

  // Shared props
  nodeTypes?: NodeTypes;
  edgeTypes?: EdgeTypes;
  onNodeSelect?: (node: Node | null) => void;
  onSelectionChange?: (params: { nodes: Node[]; edges: Edge[] }) => void;
  onViewportChange?: (viewport: Viewport) => void;
  readOnly?: boolean;

  // Selection callbacks
  onSelectAll?: () => void;
  onClearSelection?: () => void;

  // Connection feedback (optional - uses ConnectionFeedback context if available)
  useConnectionFeedbackContext?: boolean;

  // Drag and drop from sidebar
  onDropFromSidebar?: (data: SidebarDropData, position: { x: number; y: number }) => void;
}

// Default edge styling
const defaultEdgeOptions = {
  style: {
    stroke: reactFlowStyles.edge.default.stroke,
    strokeWidth: reactFlowStyles.edge.default.strokeWidth,
  },
  animated: false,
};

/**
 * Inner canvas component that has access to ReactFlow context
 */
function CanvasInner({
  // Standalone mode
  initialNodes = [],
  initialEdges = [],
  // Connected mode
  nodes: externalNodes,
  edges: externalEdges,
  onNodesChange: externalOnNodesChange,
  onEdgesChange: externalOnEdgesChange,
  onConnect: externalOnConnect,
  // Shared
  nodeTypes,
  edgeTypes,
  onNodeSelect,
  onSelectionChange: externalOnSelectionChange,
  onViewportChange,
  readOnly = false,
  // Selection callbacks
  onSelectAll,
  onClearSelection,
  // Connection feedback
  useConnectionFeedbackContext = true,
  // Drag and drop
  onDropFromSidebar,
}: CanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const reactFlowInstance = useReactFlow();
  // Determine if we're in connected mode (external state management)
  const isConnected = externalNodes !== undefined && externalEdges !== undefined;

  // Try to use connection feedback context (may not be available)
  let connectionFeedback: ReturnType<typeof useConnectionFeedback> | null = null;
  try {
    if (useConnectionFeedbackContext) {
      // eslint-disable-next-line react-hooks/rules-of-hooks
      connectionFeedback = useConnectionFeedback();
    }
  } catch {
    // Context not available, connection feedback disabled
  }

  // Internal state for standalone mode
  const [internalNodes, _setInternalNodes, internalOnNodesChange] =
    useNodesState(initialNodes);
  const [internalEdges, setInternalEdges, internalOnEdgesChange] =
    useEdgesState(initialEdges);

  // Use external or internal state
  const nodes = isConnected ? externalNodes : internalNodes;
  const edges = isConnected ? externalEdges : internalEdges;
  const onNodesChange = isConnected
    ? externalOnNodesChange!
    : internalOnNodesChange;
  const onEdgesChange = isConnected
    ? externalOnEdgesChange!
    : internalOnEdgesChange;

  // Handle new connections
  const onConnect = useCallback(
    (connection: Connection) => {
      if (readOnly) return;
      if (isConnected && externalOnConnect) {
        externalOnConnect(connection);
      } else {
        setInternalEdges((eds) => addEdge(connection, eds));
      }
    },
    [readOnly, isConnected, externalOnConnect, setInternalEdges]
  );

  // Handle selection changes
  const onSelectionChange = useCallback(
    ({ nodes: selectedNodes, edges: selectedEdges }: { nodes: Node[]; edges: Edge[] }) => {
      // Notify parent of full selection
      if (externalOnSelectionChange) {
        externalOnSelectionChange({ nodes: selectedNodes, edges: selectedEdges });
      }

      // Legacy single-node selection callback
      if (onNodeSelect) {
        onNodeSelect(selectedNodes.length === 1 ? selectedNodes[0] : null);
      }
    },
    [onNodeSelect, externalOnSelectionChange]
  );

  // Handle viewport changes
  const handleMoveEnd = useCallback(
    (_event: unknown, viewport: Viewport) => {
      if (onViewportChange) {
        onViewportChange(viewport);
      }
    },
    [onViewportChange]
  );

  // Handle connection start (for visual feedback)
  const handleConnectStart = useCallback(
    (_event: React.MouseEvent | React.TouchEvent, params: OnConnectStartParams) => {
      if (connectionFeedback) {
        connectionFeedback.startConnection(params, nodes as Node<MelleaNodeData>[], edges);
      }
    },
    [connectionFeedback, nodes, edges]
  );

  // Handle connection end (for visual feedback)
  const handleConnectEnd = useCallback(() => {
    if (connectionFeedback) {
      connectionFeedback.endConnection();
    }
  }, [connectionFeedback]);

  // Validate connection in real-time during drag
  const isValidConnection = useCallback(
    (connection: Connection) => {
      const result = validateConnection(
        connection,
        nodes as Node<MelleaNodeData>[],
        edges
      );

      // Update feedback context with validation result
      if (connectionFeedback) {
        connectionFeedback.updateHoverTarget(connection, nodes as Node<MelleaNodeData>[], edges);
      }

      return result.valid;
    },
    [nodes, edges, connectionFeedback]
  );

  // Minimap node color function
  const minimapNodeColor = useCallback((node: Node) => {
    const category = node.data?.category as NodeCategory | undefined;
    return category ? nodeColors[category] : '#9CA3AF';
  }, []);

  // ProOptions to remove attribution (if licensed) or keep for free version
  const proOptions = useMemo(() => ({ hideAttribution: false }), []);

  // Keyboard shortcuts for selection
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Don't handle shortcuts when typing in inputs
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement
      ) {
        return;
      }

      // Ctrl/Cmd+A: Select all
      if ((event.ctrlKey || event.metaKey) && event.key === 'a') {
        event.preventDefault();
        onSelectAll?.();
      }

      // Escape: Clear selection
      if (event.key === 'Escape') {
        event.preventDefault();
        onClearSelection?.();
      }
    };

    const container = containerRef.current;
    if (container) {
      container.addEventListener('keydown', handleKeyDown);
      return () => container.removeEventListener('keydown', handleKeyDown);
    }
  }, [onSelectAll, onClearSelection]);

  // Handle drag over to allow drop
  const handleDragOver = useCallback((event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  }, []);

  // Handle drop from sidebar
  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();

      if (readOnly || !onDropFromSidebar) return;

      const dataStr = event.dataTransfer.getData(SIDEBAR_DRAG_TYPE);
      if (!dataStr) return;

      try {
        const dropData: SidebarDropData = JSON.parse(dataStr);

        // Convert screen coordinates to flow coordinates
        const position = reactFlowInstance.screenToFlowPosition({
          x: event.clientX,
          y: event.clientY,
        });

        onDropFromSidebar(dropData, position);
      } catch (error) {
        console.error('Failed to parse drop data:', error);
      }
    },
    [readOnly, onDropFromSidebar, reactFlowInstance]
  );

  return (
    <Box
      ref={containerRef}
      h="100%"
      w="100%"
      position="relative"
      tabIndex={0}
      outline="none"
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      sx={{
        '& .react-flow': {
          fontFamily: 'Inter, system-ui, sans-serif',
        },
      }}
    >
      <style>{reactFlowContainerStyles}</style>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onConnectStart={handleConnectStart}
        onConnectEnd={handleConnectEnd}
        isValidConnection={isValidConnection}
        connectionLineComponent={ValidationConnectionLine}
        onSelectionChange={onSelectionChange}
        onMoveEnd={handleMoveEnd}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        connectionMode={ConnectionMode.Loose}
        selectionMode={SelectionMode.Partial}
        selectNodesOnDrag={!readOnly}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        elementsSelectable={!readOnly}
        panOnDrag={true}
        zoomOnScroll={true}
        zoomOnPinch={true}
        zoomOnDoubleClick={true}
        minZoom={0.1}
        maxZoom={2}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={proOptions}
        deleteKeyCode={readOnly ? null : ['Backspace', 'Delete']}
        className={connectionFeedback?.isConnecting ? 'connecting' : undefined}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={reactFlowStyles.background.gap}
          size={reactFlowStyles.background.size}
          color="#D1D5DB"
        />
        <Controls
          showZoom={true}
          showFitView={true}
          showInteractive={!readOnly}
          position="bottom-left"
        />
        <MiniMap
          nodeColor={minimapNodeColor}
          nodeStrokeWidth={reactFlowStyles.minimap.nodeStrokeWidth}
          maskColor={reactFlowStyles.minimap.maskColor}
          position="bottom-right"
          zoomable
          pannable
        />
      </ReactFlow>
    </Box>
  );
}

/**
 * Canvas component for the Visual Builder
 *
 * Can operate in two modes:
 * 1. Standalone mode: Pass initialNodes/initialEdges, manages its own state
 * 2. Connected mode: Pass nodes/edges/onNodesChange/onEdgesChange from CompositionContext
 *
 * Wraps CanvasInner with ReactFlowProvider to enable useReactFlow hook.
 */
export function Canvas(props: CanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}

/**
 * ConnectedCanvas - Canvas that automatically connects to CompositionContext
 * Use this when the Canvas should be managed by a CompositionProvider
 */
export { ConnectedCanvas } from './ConnectedCanvas';
