/**
 * PrimitiveNode - Custom node for control flow primitives
 *
 * Supports:
 * - Loop: Iteration over collections
 * - Conditional: If/else branching
 * - Merge: Combining multiple inputs
 * - Map: Transform each item
 * - Filter: Select items matching criteria
 */
import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { Box, HStack, VStack, Text, Icon } from '@chakra-ui/react';
import {
  FiRepeat,
  FiGitBranch,
  FiGitMerge,
  FiMap,
  FiFilter,
  FiLoader,
  FiCheck,
  FiX,
  FiClock,
  FiSkipForward,
  FiStopCircle,
} from 'react-icons/fi';
import { type MelleaNodeData } from '../CompositionContext';
import { nodeColors, executionStateStyles, reactFlowStyles } from '../theme';

// Primitive types and their icons
type PrimitiveType = 'loop' | 'conditional' | 'merge' | 'map' | 'filter';

const primitiveIcons: Record<PrimitiveType, React.ComponentType> = {
  loop: FiRepeat,
  conditional: FiGitBranch,
  merge: FiGitMerge,
  map: FiMap,
  filter: FiFilter,
};

// Handle configurations for each primitive type
const primitiveHandles: Record<PrimitiveType, { inputs: string[]; outputs: string[] }> = {
  loop: {
    inputs: ['collection'],
    outputs: ['item', 'index', 'done'],
  },
  conditional: {
    inputs: ['condition', 'value'],
    outputs: ['true', 'false'],
  },
  merge: {
    inputs: ['input1', 'input2', 'input3'],
    outputs: ['merged'],
  },
  map: {
    inputs: ['collection', 'mapper'],
    outputs: ['result'],
  },
  filter: {
    inputs: ['collection', 'predicate'],
    outputs: ['filtered'],
  },
};

// Icon mapping for execution states
const stateIcons = {
  idle: null,
  queued: FiClock,
  running: FiLoader,
  succeeded: FiCheck,
  failed: FiX,
  skipped: FiSkipForward,
  cancelled: FiStopCircle,
};

interface PrimitiveNodeData extends MelleaNodeData {
  // Primitive-specific data
  primitiveType?: PrimitiveType;
  config?: Record<string, unknown>;
}

function PrimitiveNodeComponent({ data, selected }: NodeProps<PrimitiveNodeData>) {
  const executionState = data.executionState || 'idle';
  const stateStyle = executionStateStyles[executionState];
  const StateIcon = stateIcons[executionState];

  const primitiveType = data.primitiveType || 'merge';
  const PrimitiveIcon = primitiveIcons[primitiveType];
  const handles = primitiveHandles[primitiveType];

  // Calculate node height based on handle count
  const maxHandles = Math.max(handles.inputs.length, handles.outputs.length);

  return (
    <Box
      bg="white"
      borderWidth={reactFlowStyles.node.borderWidth}
      borderStyle="solid"
      borderColor={selected ? nodeColors.primitive : stateStyle.borderColor}
      borderRadius={reactFlowStyles.node.borderRadius}
      boxShadow={selected ? reactFlowStyles.node.shadowSelected : reactFlowStyles.node.shadow}
      minW={reactFlowStyles.node.width}
      minH={Math.max(reactFlowStyles.node.minHeight, 60 + maxHandles * 24)}
      opacity={stateStyle.opacity}
      className={executionState === 'queued' ? 'node-state-queued' : executionState === 'running' ? 'node-state-running' : undefined}
      position="relative"
    >
      {/* Header */}
      <Box
        bg={nodeColors.primitive}
        color="white"
        px={3}
        py={2}
        borderTopRadius={reactFlowStyles.node.borderRadius - 2}
      >
        <HStack justify="space-between">
          <HStack spacing={2}>
            <Icon as={PrimitiveIcon} boxSize={4} />
            <Text fontSize="sm" fontWeight="semibold" textTransform="capitalize">
              {data.label || primitiveType}
            </Text>
          </HStack>
          {StateIcon && (
            <Icon
              as={StateIcon}
              boxSize={4}
              className={executionState === 'running' ? 'node-icon' : undefined}
            />
          )}
        </HStack>
      </Box>

      {/* Body with handles */}
      <Box px={3} py={2} position="relative">
        <HStack justify="space-between" align="flex-start" spacing={4}>
          {/* Input handles */}
          <VStack align="flex-start" spacing={1} flex={1}>
            {handles.inputs.map((handleId, index) => (
              <Box key={handleId} position="relative" w="100%">
                <Handle
                  type="target"
                  position={Position.Left}
                  id={handleId}
                  style={{
                    background: nodeColors.primitive,
                    width: 10,
                    height: 10,
                    border: '2px solid white',
                    left: -5,
                    top: index * 24 + 12,
                  }}
                />
                <Text fontSize="xs" color="gray.600" pl={2}>
                  {handleId}
                </Text>
              </Box>
            ))}
          </VStack>

          {/* Output handles */}
          <VStack align="flex-end" spacing={1} flex={1}>
            {handles.outputs.map((handleId, index) => (
              <Box key={handleId} position="relative" w="100%">
                <Handle
                  type="source"
                  position={Position.Right}
                  id={handleId}
                  style={{
                    background: nodeColors.primitive,
                    width: 10,
                    height: 10,
                    border: '2px solid white',
                    right: -5,
                    top: index * 24 + 12,
                  }}
                />
                <Text fontSize="xs" color="gray.600" pr={2} textAlign="right">
                  {handleId}
                </Text>
              </Box>
            ))}
          </VStack>
        </HStack>
      </Box>
    </Box>
  );
}

export const PrimitiveNode = memo(PrimitiveNodeComponent);
