/**
 * UtilityNode - Custom node for utility functions
 *
 * Supports:
 * - Input: Entry point for data
 * - Output: Exit point for results
 * - Note: Annotation/comment node (no handles)
 * - Constant: Fixed value provider
 * - Debug: Inspection point
 */
import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { Box, HStack, VStack, Text, Icon } from '@chakra-ui/react';
import {
  FiLogIn,
  FiLogOut,
  FiFileText,
  FiHash,
  FiTerminal,
  FiLoader,
  FiCheck,
  FiX,
  FiClock,
  FiSkipForward,
  FiStopCircle,
} from 'react-icons/fi';
import { type MelleaNodeData } from '../CompositionContext';
import { nodeColors, executionStateStyles, reactFlowStyles } from '../theme';

// Utility types and their icons
type UtilityType = 'input' | 'output' | 'note' | 'constant' | 'debug';

const utilityIcons: Record<UtilityType, React.ComponentType> = {
  input: FiLogIn,
  output: FiLogOut,
  note: FiFileText,
  constant: FiHash,
  debug: FiTerminal,
};

// Handle configurations for each utility type
const utilityHandles: Record<UtilityType, { inputs: string[]; outputs: string[] }> = {
  input: {
    inputs: [],
    outputs: ['value'],
  },
  output: {
    inputs: ['value'],
    outputs: [],
  },
  note: {
    inputs: [],
    outputs: [],
  },
  constant: {
    inputs: [],
    outputs: ['value'],
  },
  debug: {
    inputs: ['value'],
    outputs: ['value'],
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

interface UtilityNodeData extends MelleaNodeData {
  // Utility-specific data
  utilityType?: UtilityType;
  value?: string | number | boolean;
  noteText?: string;
  dataType?: 'string' | 'number' | 'boolean' | 'object' | 'array';
}

function UtilityNodeComponent({ data, selected }: NodeProps<UtilityNodeData>) {
  const executionState = data.executionState || 'idle';
  const stateStyle = executionStateStyles[executionState];
  const StateIcon = stateIcons[executionState];

  const utilityType = data.utilityType || 'input';
  const UtilityIcon = utilityIcons[utilityType];
  const handles = utilityHandles[utilityType];

  // Note nodes have a different style
  const isNote = utilityType === 'note';

  return (
    <Box
      bg={isNote ? '#FFFBEB' : 'white'}
      borderWidth={reactFlowStyles.node.borderWidth}
      borderStyle={isNote ? 'dashed' : 'solid'}
      borderColor={selected ? nodeColors.utility : isNote ? '#F59E0B' : stateStyle.borderColor}
      borderRadius={reactFlowStyles.node.borderRadius}
      boxShadow={selected ? reactFlowStyles.node.shadowSelected : reactFlowStyles.node.shadow}
      minW={isNote ? 200 : reactFlowStyles.node.width}
      minH={isNote ? 80 : reactFlowStyles.node.minHeight}
      opacity={stateStyle.opacity}
      className={executionState === 'queued' ? 'node-state-queued' : executionState === 'running' ? 'node-state-running' : undefined}
      position="relative"
    >
      {/* Input handles */}
      {handles.inputs.map((handleId, index) => (
        <Handle
          key={handleId}
          type="target"
          position={Position.Left}
          id={handleId}
          style={{
            background: nodeColors.utility,
            width: 10,
            height: 10,
            border: '2px solid white',
            top: `${50 + index * 20}%`,
          }}
        />
      ))}

      {/* Output handles */}
      {handles.outputs.map((handleId, index) => (
        <Handle
          key={handleId}
          type="source"
          position={Position.Right}
          id={handleId}
          style={{
            background: nodeColors.utility,
            width: 10,
            height: 10,
            border: '2px solid white',
            top: `${50 + index * 20}%`,
          }}
        />
      ))}

      {/* Header - not shown for notes */}
      {!isNote && (
        <Box
          bg={nodeColors.utility}
          color="white"
          px={3}
          py={2}
          borderTopRadius={reactFlowStyles.node.borderRadius - 2}
        >
          <HStack justify="space-between">
            <HStack spacing={2}>
              <Icon as={UtilityIcon} boxSize={4} />
              <Text fontSize="sm" fontWeight="semibold" textTransform="capitalize">
                {data.label || utilityType}
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
      )}

      {/* Body */}
      <Box px={3} py={2}>
        {isNote ? (
          /* Note content */
          <VStack align="stretch" spacing={1}>
            <HStack spacing={1} color="amber.600">
              <Icon as={FiFileText} boxSize={3} />
              <Text fontSize="xs" fontWeight="medium">
                Note
              </Text>
            </HStack>
            <Text fontSize="sm" color="gray.700" whiteSpace="pre-wrap">
              {data.noteText || 'Add a note...'}
            </Text>
          </VStack>
        ) : utilityType === 'constant' ? (
          /* Constant value display */
          <VStack align="stretch" spacing={2}>
            <HStack justify="space-between">
              <Text fontSize="xs" color="gray.500">
                Type
              </Text>
              <Text fontSize="xs" fontWeight="medium" textTransform="capitalize">
                {data.dataType || 'string'}
              </Text>
            </HStack>
            <Box
              bg="gray.50"
              p={2}
              borderRadius={4}
              fontFamily="mono"
              fontSize="xs"
              maxH="60px"
              overflow="auto"
            >
              {String(data.value ?? '')}
            </Box>
          </VStack>
        ) : utilityType === 'debug' ? (
          /* Debug info */
          <VStack align="stretch" spacing={1}>
            <Text fontSize="xs" color="gray.500">
              Inspect value at this point
            </Text>
            {data.value !== undefined && (
              <Box
                bg="gray.50"
                p={2}
                borderRadius={4}
                fontFamily="mono"
                fontSize="xs"
                maxH="60px"
                overflow="auto"
              >
                {typeof data.value === 'object'
                  ? JSON.stringify(data.value, null, 2)
                  : String(data.value)}
              </Box>
            )}
          </VStack>
        ) : (
          /* Input/Output type info */
          <VStack align="stretch" spacing={2}>
            {data.dataType && (
              <HStack justify="space-between">
                <Text fontSize="xs" color="gray.500">
                  Data Type
                </Text>
                <Text fontSize="xs" fontWeight="medium" textTransform="capitalize">
                  {data.dataType}
                </Text>
              </HStack>
            )}
            <Text fontSize="xs" color="gray.400">
              {utilityType === 'input'
                ? 'Entry point for composition'
                : 'Exit point for composition'}
            </Text>
          </VStack>
        )}
      </Box>
    </Box>
  );
}

export const UtilityNode = memo(UtilityNodeComponent);
