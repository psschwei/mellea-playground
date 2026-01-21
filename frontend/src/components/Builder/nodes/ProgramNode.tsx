/**
 * ProgramNode - Custom node for program/composition references
 *
 * Features:
 * - Slot handles for inputs (left) and outputs (right)
 * - Category-colored border (purple)
 * - Execution state visualization
 * - Icon and label display
 */
import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { Box, HStack, Text, Icon } from '@chakra-ui/react';
import { FiBox, FiLoader, FiCheck, FiX, FiClock, FiSkipForward, FiStopCircle } from 'react-icons/fi';
import { type MelleaNodeData } from '../CompositionContext';
import { nodeColors, executionStateStyles, reactFlowStyles } from '../theme';

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

interface ProgramNodeData extends MelleaNodeData {
  // Program-specific data
  programId?: string;
  version?: string;
  slots?: {
    inputs: Array<{ id: string; label: string; type?: string }>;
    outputs: Array<{ id: string; label: string; type?: string }>;
  };
}

function ProgramNodeComponent({ data, selected }: NodeProps<ProgramNodeData>) {
  const executionState = data.executionState || 'idle';
  const stateStyle = executionStateStyles[executionState];
  const StateIcon = stateIcons[executionState];

  // Default slots if none provided
  const slots = data.slots || {
    inputs: [{ id: 'input', label: 'Input' }],
    outputs: [{ id: 'output', label: 'Output' }],
  };

  return (
    <Box
      bg="white"
      borderWidth={reactFlowStyles.node.borderWidth}
      borderStyle="solid"
      borderColor={selected ? nodeColors.program : stateStyle.borderColor}
      borderRadius={reactFlowStyles.node.borderRadius}
      boxShadow={selected ? reactFlowStyles.node.shadowSelected : reactFlowStyles.node.shadow}
      minW={reactFlowStyles.node.width}
      minH={reactFlowStyles.node.minHeight}
      opacity={stateStyle.opacity}
      className={executionState === 'queued' ? 'node-state-queued' : executionState === 'running' ? 'node-state-running' : undefined}
      position="relative"
    >
      {/* Header */}
      <Box
        bg={nodeColors.program}
        color="white"
        px={3}
        py={2}
        borderTopRadius={reactFlowStyles.node.borderRadius - 2}
      >
        <HStack justify="space-between">
          <HStack spacing={2}>
            <Icon as={FiBox} boxSize={4} />
            <Text fontSize="sm" fontWeight="semibold" noOfLines={1}>
              {data.label || 'Program'}
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

      {/* Body with slots */}
      <Box px={3} py={2} position="relative">
        <HStack justify="space-between" align="flex-start" spacing={4}>
          {/* Input slots */}
          <Box flex={1}>
            {slots.inputs.map((slot, index) => (
              <Box key={slot.id} position="relative" mb={index < slots.inputs.length - 1 ? 2 : 0}>
                <Handle
                  type="target"
                  position={Position.Left}
                  id={slot.id}
                  style={{
                    background: nodeColors.program,
                    width: 10,
                    height: 10,
                    border: '2px solid white',
                    left: -5,
                  }}
                />
                <Text fontSize="xs" color="gray.600" pl={2}>
                  {slot.label}
                </Text>
              </Box>
            ))}
          </Box>

          {/* Output slots */}
          <Box flex={1} textAlign="right">
            {slots.outputs.map((slot, index) => (
              <Box key={slot.id} position="relative" mb={index < slots.outputs.length - 1 ? 2 : 0}>
                <Handle
                  type="source"
                  position={Position.Right}
                  id={slot.id}
                  style={{
                    background: nodeColors.program,
                    width: 10,
                    height: 10,
                    border: '2px solid white',
                    right: -5,
                  }}
                />
                <Text fontSize="xs" color="gray.600" pr={2}>
                  {slot.label}
                </Text>
              </Box>
            ))}
          </Box>
        </HStack>

        {/* Version badge */}
        {data.version && (
          <Text fontSize="xs" color="gray.400" mt={2}>
            v{data.version}
          </Text>
        )}
      </Box>
    </Box>
  );
}

export const ProgramNode = memo(ProgramNodeComponent);
