import {
  Box,
  Heading,
  HStack,
  VStack,
  Text,
  Button,
  useColorModeValue,
  Badge,
  Divider,
  IconButton,
  Tooltip,
} from '@chakra-ui/react';
import { FiPlus, FiSave, FiPlay, FiTrash2, FiCopy } from 'react-icons/fi';
import { ReactFlowProvider } from 'reactflow';
import {
  ConnectedCanvas,
  CompositionProvider,
  useCompositionSelection,
  useComposition,
  nodeColors,
  type MelleaNodeData,
} from '@/components/Builder';
import type { Node } from 'reactflow';

// Demo nodes to show the canvas is working
const initialNodes: Node<MelleaNodeData>[] = [
  {
    id: 'input-1',
    type: 'default',
    position: { x: 100, y: 100 },
    data: {
      label: 'Input',
      category: 'utility',
    },
    style: {
      background: '#ffffff',
      border: `2px solid ${nodeColors.utility}`,
      borderRadius: 8,
      padding: 10,
    },
  },
  {
    id: 'program-1',
    type: 'default',
    position: { x: 350, y: 100 },
    data: {
      label: 'Program Node',
      category: 'program',
    },
    style: {
      background: '#ffffff',
      border: `2px solid ${nodeColors.program}`,
      borderRadius: 8,
      padding: 10,
    },
  },
  {
    id: 'output-1',
    type: 'default',
    position: { x: 600, y: 100 },
    data: {
      label: 'Output',
      category: 'utility',
    },
    style: {
      background: '#ffffff',
      border: `2px solid ${nodeColors.utility}`,
      borderRadius: 8,
      padding: 10,
    },
  },
];

const initialEdges = [
  {
    id: 'e-input-program',
    source: 'input-1',
    target: 'program-1',
    style: { stroke: nodeColors.utility },
  },
  {
    id: 'e-program-output',
    source: 'program-1',
    target: 'output-1',
    style: { stroke: nodeColors.program },
  },
];

// Node details sidebar - uses composition context
function NodeDetailsSidebar() {
  const {
    selection,
    selectedNode,
    removeSelectedNodes,
    duplicateSelectedNodes,
    clearSelection,
  } = useCompositionSelection();
  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

  const selectedCount = selection.nodes.length;
  const selectedEdgeCount = selection.edges.length;

  // No selection
  if (selectedCount === 0) {
    return null;
  }

  // Multi-selection view
  if (selectedCount > 1) {
    return (
      <VStack
        w="300px"
        p={4}
        borderLeft="1px"
        borderColor={borderColor}
        bg={bgColor}
        align="stretch"
        spacing={4}
      >
        <Heading size="sm">Multi-Selection</Heading>
        <Box>
          <Text fontSize="sm" fontWeight="medium" color="gray.500">
            Selected Items
          </Text>
          <Text fontSize="sm">
            {selectedCount} node{selectedCount !== 1 ? 's' : ''}
            {selectedEdgeCount > 0 && (
              <>, {selectedEdgeCount} edge{selectedEdgeCount !== 1 ? 's' : ''}</>
            )}
          </Text>
        </Box>
        <Divider />
        <Box>
          <Text fontSize="xs" fontWeight="medium" color="gray.500" mb={2}>
            Actions
          </Text>
          <HStack spacing={2}>
            <Tooltip label="Duplicate selected (Ctrl+D)">
              <IconButton
                aria-label="Duplicate selected"
                icon={<FiCopy />}
                size="sm"
                variant="outline"
                onClick={duplicateSelectedNodes}
              />
            </Tooltip>
            <Tooltip label="Delete selected (Delete)">
              <IconButton
                aria-label="Delete selected"
                icon={<FiTrash2 />}
                size="sm"
                variant="outline"
                colorScheme="red"
                onClick={removeSelectedNodes}
              />
            </Tooltip>
          </HStack>
        </Box>
        <Divider />
        <Button size="sm" variant="ghost" onClick={clearSelection}>
          Clear Selection
        </Button>
        <Text fontSize="xs" color="gray.400">
          Tip: Press Esc to clear selection
        </Text>
      </VStack>
    );
  }

  // Single selection view
  const category = selectedNode?.data?.category;

  return (
    <VStack
      w="300px"
      p={4}
      borderLeft="1px"
      borderColor={borderColor}
      bg={bgColor}
      align="stretch"
      spacing={4}
    >
      <HStack justify="space-between">
        <Heading size="sm">Node Details</Heading>
        <HStack spacing={1}>
          <Tooltip label="Duplicate">
            <IconButton
              aria-label="Duplicate node"
              icon={<FiCopy />}
              size="xs"
              variant="ghost"
              onClick={duplicateSelectedNodes}
            />
          </Tooltip>
          <Tooltip label="Delete">
            <IconButton
              aria-label="Delete node"
              icon={<FiTrash2 />}
              size="xs"
              variant="ghost"
              colorScheme="red"
              onClick={removeSelectedNodes}
            />
          </Tooltip>
        </HStack>
      </HStack>
      <Box>
        <Text fontSize="sm" fontWeight="medium" color="gray.500">
          ID
        </Text>
        <Text fontSize="sm">{selectedNode?.id}</Text>
      </Box>
      <Box>
        <Text fontSize="sm" fontWeight="medium" color="gray.500">
          Label
        </Text>
        <Text fontSize="sm">{selectedNode?.data?.label || 'Unnamed'}</Text>
      </Box>
      <Box>
        <Text fontSize="sm" fontWeight="medium" color="gray.500">
          Category
        </Text>
        {category && (
          <Badge
            colorScheme={
              category === 'program'
                ? 'purple'
                : category === 'model'
                  ? 'pink'
                  : category === 'primitive'
                    ? 'blue'
                    : 'green'
            }
          >
            {category}
          </Badge>
        )}
      </Box>
      <Box>
        <Text fontSize="sm" fontWeight="medium" color="gray.500">
          Position
        </Text>
        <Text fontSize="sm">
          x: {Math.round(selectedNode?.position.x ?? 0)}, y:{' '}
          {Math.round(selectedNode?.position.y ?? 0)}
        </Text>
      </Box>
    </VStack>
  );
}

// Header toolbar - uses composition context for dirty state
function BuilderHeader() {
  const { isDirty, getSerializableState, markClean } = useComposition();
  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

  const handleSave = () => {
    const state = getSerializableState();
    console.log('Saving composition:', state);
    // TODO: Actually save to backend
    markClean();
  };

  return (
    <HStack
      px={4}
      py={2}
      borderBottom="1px"
      borderColor={borderColor}
      bg={bgColor}
      justify="space-between"
    >
      <HStack spacing={4}>
        <Heading size="md">Visual Builder</Heading>
        <Text color="gray.500" fontSize="sm">
          Untitled Composition
          {isDirty && (
            <Text as="span" color="orange.500" ml={1}>
              (unsaved)
            </Text>
          )}
        </Text>
      </HStack>
      <HStack spacing={2}>
        <Button leftIcon={<FiPlus />} size="sm" variant="outline">
          Add Node
        </Button>
        <Button
          leftIcon={<FiSave />}
          size="sm"
          variant="outline"
          onClick={handleSave}
        >
          Save
        </Button>
        <Button leftIcon={<FiPlay />} size="sm" colorScheme="brand">
          Run
        </Button>
      </HStack>
    </HStack>
  );
}

// Main builder content
function BuilderContent() {
  return (
    <Box h="calc(100vh - 64px)" display="flex" flexDirection="column">
      <BuilderHeader />
      <Box flex="1" display="flex" overflow="hidden">
        <Box flex="1" bg="gray.50">
          <ConnectedCanvas />
        </Box>
        <NodeDetailsSidebar />
      </Box>
    </Box>
  );
}

export function BuilderPage() {
  return (
    <ReactFlowProvider>
      <CompositionProvider
        initialNodes={initialNodes}
        initialEdges={initialEdges}
      >
        <BuilderContent />
      </CompositionProvider>
    </ReactFlowProvider>
  );
}
