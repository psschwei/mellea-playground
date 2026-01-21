/**
 * ConnectedCanvas - Canvas automatically connected to CompositionContext
 *
 * This component wraps Canvas and connects it to the CompositionContext,
 * eliminating the need to manually pass state and handlers.
 */
import { useCallback } from 'react';
import { Node, Edge, NodeTypes, EdgeTypes } from 'reactflow';
import { Canvas } from './Canvas';
import { useComposition } from './CompositionContext';

interface ConnectedCanvasProps {
  nodeTypes?: NodeTypes;
  edgeTypes?: EdgeTypes;
  readOnly?: boolean;
}

export function ConnectedCanvas({
  nodeTypes,
  edgeTypes,
  readOnly = false,
}: ConnectedCanvasProps) {
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    setSelection,
    setViewport,
  } = useComposition();

  // Handle selection changes and update context
  const handleSelectionChange = useCallback(
    ({ nodes: selectedNodes, edges: selectedEdges }: { nodes: Node[]; edges: Edge[] }) => {
      setSelection({
        nodes: selectedNodes.map((n) => n.id),
        edges: selectedEdges.map((e) => e.id),
      });
    },
    [setSelection]
  );

  return (
    <Canvas
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onConnect={onConnect}
      onSelectionChange={handleSelectionChange}
      onViewportChange={setViewport}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      readOnly={readOnly}
    />
  );
}
