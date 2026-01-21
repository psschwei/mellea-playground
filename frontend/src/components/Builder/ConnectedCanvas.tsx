/**
 * ConnectedCanvas - Canvas automatically connected to CompositionContext
 *
 * This component wraps Canvas and connects it to the CompositionContext,
 * eliminating the need to manually pass state and handlers.
 * Also provides visual feedback for invalid connections.
 */
import { useCallback } from 'react';
import { Node, Edge, NodeTypes, EdgeTypes } from 'reactflow';
import { Box, Alert, AlertIcon, AlertDescription, CloseButton } from '@chakra-ui/react';
import { Canvas } from './Canvas';
import { useComposition, useCompositionValidation } from './CompositionContext';
import { ConnectionFeedbackProvider } from './ConnectionFeedback';

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
    selectAll,
    clearSelection,
  } = useComposition();

  const { lastValidationError, clearValidationError } = useCompositionValidation();

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
    <ConnectionFeedbackProvider>
      <Box position="relative" h="100%" w="100%">
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
          onSelectAll={selectAll}
          onClearSelection={clearSelection}
        />

        {/* Validation error toast */}
        {lastValidationError && !lastValidationError.valid && (
          <Alert
            status="error"
            position="absolute"
            bottom={4}
            left="50%"
            transform="translateX(-50%)"
            maxW="400px"
            borderRadius="md"
            boxShadow="lg"
            zIndex={1000}
          >
            <AlertIcon />
            <AlertDescription fontSize="sm">
              {lastValidationError.error}
            </AlertDescription>
            <CloseButton
              position="absolute"
              right={1}
              top={1}
              size="sm"
              onClick={clearValidationError}
            />
          </Alert>
        )}
      </Box>
    </ConnectionFeedbackProvider>
  );
}
