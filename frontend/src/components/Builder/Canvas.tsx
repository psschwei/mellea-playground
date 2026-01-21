import { useCallback, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  Node,
  Edge,
  BackgroundVariant,
  NodeTypes,
  EdgeTypes,
  ConnectionMode,
  SelectionMode,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Box } from '@chakra-ui/react';
import {
  reactFlowStyles,
  reactFlowContainerStyles,
  nodeColors,
  NodeCategory,
} from './theme';

// Props for the Canvas component
interface CanvasProps {
  initialNodes?: Node[];
  initialEdges?: Edge[];
  nodeTypes?: NodeTypes;
  edgeTypes?: EdgeTypes;
  onNodesChange?: (nodes: Node[]) => void;
  onEdgesChange?: (edges: Edge[]) => void;
  onNodeSelect?: (node: Node | null) => void;
  readOnly?: boolean;
}

// Default edge styling
const defaultEdgeOptions = {
  style: {
    stroke: reactFlowStyles.edge.default.stroke,
    strokeWidth: reactFlowStyles.edge.default.strokeWidth,
  },
  animated: false,
};

export function Canvas({
  initialNodes = [],
  initialEdges = [],
  nodeTypes,
  edgeTypes,
  onNodesChange: onNodesChangeCallback,
  onEdgesChange: onEdgesChangeCallback,
  onNodeSelect,
  readOnly = false,
}: CanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Handle new connections
  const onConnect = useCallback(
    (connection: Connection) => {
      if (readOnly) return;
      setEdges((eds) => addEdge(connection, eds));
    },
    [readOnly, setEdges]
  );

  // Notify parent of node changes
  const handleNodesChange = useCallback(
    (changes: Parameters<typeof onNodesChange>[0]) => {
      onNodesChange(changes);
      if (onNodesChangeCallback) {
        // Get updated nodes after changes are applied
        setNodes((currentNodes) => {
          onNodesChangeCallback(currentNodes);
          return currentNodes;
        });
      }
    },
    [onNodesChange, onNodesChangeCallback, setNodes]
  );

  // Notify parent of edge changes
  const handleEdgesChange = useCallback(
    (changes: Parameters<typeof onEdgesChange>[0]) => {
      onEdgesChange(changes);
      if (onEdgesChangeCallback) {
        setEdges((currentEdges) => {
          onEdgesChangeCallback(currentEdges);
          return currentEdges;
        });
      }
    },
    [onEdgesChange, onEdgesChangeCallback, setEdges]
  );

  // Handle node selection
  const onSelectionChange = useCallback(
    ({ nodes: selectedNodes }: { nodes: Node[]; edges: Edge[] }) => {
      if (onNodeSelect) {
        onNodeSelect(selectedNodes.length === 1 ? selectedNodes[0] : null);
      }
    },
    [onNodeSelect]
  );

  // Minimap node color function
  const minimapNodeColor = useCallback((node: Node) => {
    const category = node.data?.category as NodeCategory | undefined;
    return category ? nodeColors[category] : '#9CA3AF';
  }, []);

  // ProOptions to remove attribution (if licensed) or keep for free version
  const proOptions = useMemo(() => ({ hideAttribution: false }), []);

  return (
    <Box
      h="100%"
      w="100%"
      position="relative"
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
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        onSelectionChange={onSelectionChange}
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
