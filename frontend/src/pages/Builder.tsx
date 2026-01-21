import { useState, useCallback } from 'react';
import {
  Box,
  Heading,
  HStack,
  VStack,
  Text,
  Button,
  useColorModeValue,
} from '@chakra-ui/react';
import { FiPlus, FiSave, FiPlay } from 'react-icons/fi';
import { Node, Edge } from 'reactflow';
import { Canvas, nodeColors } from '@/components/Builder';

// Demo nodes to show the canvas is working
const initialNodes: Node[] = [
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

const initialEdges: Edge[] = [
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

export function BuilderPage() {
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

  const handleNodeSelect = useCallback((node: Node | null) => {
    setSelectedNode(node);
  }, []);

  return (
    <Box h="calc(100vh - 64px)" display="flex" flexDirection="column">
      {/* Header toolbar */}
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
          </Text>
        </HStack>
        <HStack spacing={2}>
          <Button leftIcon={<FiPlus />} size="sm" variant="outline">
            Add Node
          </Button>
          <Button leftIcon={<FiSave />} size="sm" variant="outline">
            Save
          </Button>
          <Button leftIcon={<FiPlay />} size="sm" colorScheme="brand">
            Run
          </Button>
        </HStack>
      </HStack>

      {/* Main content area */}
      <Box flex="1" display="flex" overflow="hidden">
        {/* Canvas area */}
        <Box flex="1" bg="gray.50">
          <Canvas
            initialNodes={initialNodes}
            initialEdges={initialEdges}
            onNodeSelect={handleNodeSelect}
          />
        </Box>

        {/* Right sidebar for node details (when a node is selected) */}
        {selectedNode && (
          <VStack
            w="300px"
            p={4}
            borderLeft="1px"
            borderColor={borderColor}
            bg={bgColor}
            align="stretch"
            spacing={4}
          >
            <Heading size="sm">Node Details</Heading>
            <Box>
              <Text fontSize="sm" fontWeight="medium" color="gray.500">
                ID
              </Text>
              <Text fontSize="sm">{selectedNode.id}</Text>
            </Box>
            <Box>
              <Text fontSize="sm" fontWeight="medium" color="gray.500">
                Label
              </Text>
              <Text fontSize="sm">{selectedNode.data?.label || 'Unnamed'}</Text>
            </Box>
            <Box>
              <Text fontSize="sm" fontWeight="medium" color="gray.500">
                Category
              </Text>
              <Text fontSize="sm">{selectedNode.data?.category || 'None'}</Text>
            </Box>
            <Box>
              <Text fontSize="sm" fontWeight="medium" color="gray.500">
                Position
              </Text>
              <Text fontSize="sm">
                x: {Math.round(selectedNode.position.x)}, y:{' '}
                {Math.round(selectedNode.position.y)}
              </Text>
            </Box>
          </VStack>
        )}
      </Box>
    </Box>
  );
}
