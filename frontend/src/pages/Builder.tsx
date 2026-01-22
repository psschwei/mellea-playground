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
import { FiSave, FiPlay, FiTrash2, FiCopy, FiGrid } from 'react-icons/fi';
import { ReactFlowProvider, useReactFlow } from 'reactflow';
import { useCallback } from 'react';
import {
  ConnectedCanvas,
  CompositionProvider,
  useCompositionSelection,
  useComposition,
  melleaNodeTypes,
  melleaEdgeTypes,
  defaultEdgeType,
  BuilderSidebar,
  type MelleaNodeData,
  type CategoryEdgeData,
  type SidebarItem,
  type SidebarRecentlyUsedEntry,
} from '@/components/Builder';
import { useRecentlyUsedNodes } from '@/hooks/useRecentlyUsedNodes';
import type { Node } from 'reactflow';

// Demo nodes to show the canvas is working with custom node types
const initialNodes: Node<MelleaNodeData>[] = [
  {
    id: 'input-1',
    type: 'utility',
    position: { x: 50, y: 100 },
    data: {
      label: 'User Input',
      category: 'utility',
      utilityType: 'input',
      dataType: 'string',
    } as MelleaNodeData,
  },
  {
    id: 'model-1',
    type: 'model',
    position: { x: 350, y: 50 },
    data: {
      label: 'GPT-4',
      category: 'model',
      provider: 'OpenAI',
      modelName: 'gpt-4-turbo',
      temperature: 0.7,
      maxTokens: 2048,
    } as MelleaNodeData,
  },
  {
    id: 'program-1',
    type: 'program',
    position: { x: 350, y: 250 },
    data: {
      label: 'Text Processor',
      category: 'program',
      version: '1.2.0',
      slots: {
        inputs: [
          { id: 'text', label: 'Text' },
          { id: 'config', label: 'Config' },
        ],
        outputs: [
          { id: 'result', label: 'Result' },
          { id: 'metadata', label: 'Metadata' },
        ],
      },
    } as MelleaNodeData,
  },
  {
    id: 'merge-1',
    type: 'primitive',
    position: { x: 700, y: 150 },
    data: {
      label: 'Merge Results',
      category: 'primitive',
      primitiveType: 'merge',
    } as MelleaNodeData,
  },
  {
    id: 'output-1',
    type: 'utility',
    position: { x: 1000, y: 150 },
    data: {
      label: 'Final Output',
      category: 'utility',
      utilityType: 'output',
      dataType: 'object',
    } as MelleaNodeData,
  },
  {
    id: 'note-1',
    type: 'utility',
    position: { x: 50, y: 300 },
    data: {
      label: 'Note',
      category: 'utility',
      utilityType: 'note',
      noteText: 'This composition demonstrates the custom node types:\n- Utility nodes for I/O\n- Model nodes for AI\n- Program nodes for logic\n- Primitive nodes for control flow',
    } as MelleaNodeData,
  },
];

const initialEdges = [
  {
    id: 'e-input-model',
    source: 'input-1',
    sourceHandle: 'value',
    target: 'model-1',
    targetHandle: 'input',
    type: defaultEdgeType,
    data: { sourceCategory: 'utility' } as CategoryEdgeData,
  },
  {
    id: 'e-input-program',
    source: 'input-1',
    sourceHandle: 'value',
    target: 'program-1',
    targetHandle: 'text',
    type: defaultEdgeType,
    data: { sourceCategory: 'utility' } as CategoryEdgeData,
  },
  {
    id: 'e-model-merge',
    source: 'model-1',
    sourceHandle: 'output',
    target: 'merge-1',
    targetHandle: 'input1',
    type: defaultEdgeType,
    data: { sourceCategory: 'model' } as CategoryEdgeData,
  },
  {
    id: 'e-program-merge',
    source: 'program-1',
    sourceHandle: 'result',
    target: 'merge-1',
    targetHandle: 'input2',
    type: defaultEdgeType,
    data: { sourceCategory: 'program' } as CategoryEdgeData,
  },
  {
    id: 'e-merge-output',
    source: 'merge-1',
    sourceHandle: 'merged',
    target: 'output-1',
    targetHandle: 'value',
    type: defaultEdgeType,
    data: { sourceCategory: 'primitive' } as CategoryEdgeData,
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
  const { isDirty, getSerializableState, markClean, applyAutoLayout } = useComposition();
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
        <Tooltip label="Auto-layout nodes">
          <IconButton
            aria-label="Auto-layout"
            icon={<FiGrid />}
            size="sm"
            variant="outline"
            onClick={() => applyAutoLayout()}
          />
        </Tooltip>
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

// Builder sidebar wrapper with add node logic
function BuilderSidebarWrapper() {
  const { addNode } = useComposition();
  const { getViewport } = useReactFlow();
  const { recentNodes, recordUsage } = useRecentlyUsedNodes();

  // Convert recent nodes to the format expected by BuilderSidebar
  // For built-in items, the itemId matches the pattern like 'primitive-loop', 'utility-input'
  const recentlyUsed: SidebarRecentlyUsedEntry[] = recentNodes.map((entry) => ({
    itemId: `${entry.nodeType}-${entry.nodeType}`, // Fallback - will be updated when we track asset IDs
    nodeType: entry.nodeType as string,
  }));

  const handleItemSelect = useCallback(
    (item: SidebarItem) => {
      // Get the current viewport to position the new node in view
      const viewport = getViewport();

      // Calculate a position in the center of the current view
      const position = {
        x: (-viewport.x + 400) / viewport.zoom,
        y: (-viewport.y + 200) / viewport.zoom,
      };

      // Create a new node from the sidebar item
      const nodeData: MelleaNodeData = {
        label: item.label,
        category: item.category,
        ...(item.defaultData as Partial<MelleaNodeData>),
      };

      const newNode: Node<MelleaNodeData> = {
        id: `${item.type}-${Date.now()}`,
        type: item.type as string,
        position,
        data: nodeData,
      };

      addNode(newNode);
      recordUsage(item.type);
    },
    [addNode, getViewport, recordUsage]
  );

  return (
    <BuilderSidebar recentlyUsed={recentlyUsed} onItemSelect={handleItemSelect} />
  );
}

// Main builder content
function BuilderContent() {
  return (
    <Box h="calc(100vh - 64px)" display="flex" flexDirection="column">
      <BuilderHeader />
      <Box flex="1" display="flex" overflow="hidden">
        <BuilderSidebarWrapper />
        <Box flex="1" bg="gray.50">
          <ConnectedCanvas nodeTypes={melleaNodeTypes} edgeTypes={melleaEdgeTypes} />
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
