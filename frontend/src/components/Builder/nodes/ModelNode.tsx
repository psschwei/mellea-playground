/**
 * ModelNode - Custom node for AI model references
 *
 * Features:
 * - Provider badge (OpenAI, Anthropic, etc.)
 * - Model name display
 * - Single input/output handles
 * - Execution state visualization
 */
import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import { Box, HStack, VStack, Text, Icon, Badge } from '@chakra-ui/react';
import { FiCpu, FiLoader, FiCheck, FiX, FiClock, FiSkipForward, FiStopCircle } from 'react-icons/fi';
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

// Provider badge colors
const providerColors: Record<string, string> = {
  openai: 'green',
  anthropic: 'orange',
  google: 'blue',
  cohere: 'purple',
  huggingface: 'yellow',
  local: 'gray',
};

interface ModelNodeData extends MelleaNodeData {
  // Model-specific data
  modelId?: string;
  provider?: string;
  modelName?: string;
  temperature?: number;
  maxTokens?: number;
}

function ModelNodeComponent({ data, selected }: NodeProps<ModelNodeData>) {
  const executionState = data.executionState || 'idle';
  const stateStyle = executionStateStyles[executionState];
  const StateIcon = stateIcons[executionState];
  const provider = data.provider || 'local';
  const providerColor = providerColors[provider.toLowerCase()] || 'gray';

  return (
    <Box
      bg="white"
      borderWidth={reactFlowStyles.node.borderWidth}
      borderStyle="solid"
      borderColor={selected ? nodeColors.model : stateStyle.borderColor}
      borderRadius={reactFlowStyles.node.borderRadius}
      boxShadow={selected ? reactFlowStyles.node.shadowSelected : reactFlowStyles.node.shadow}
      minW={reactFlowStyles.node.width}
      minH={reactFlowStyles.node.minHeight}
      opacity={stateStyle.opacity}
      className={executionState === 'queued' ? 'node-state-queued' : executionState === 'running' ? 'node-state-running' : undefined}
      position="relative"
    >
      {/* Input handle */}
      <Handle
        type="target"
        position={Position.Left}
        id="input"
        style={{
          background: nodeColors.model,
          width: 10,
          height: 10,
          border: '2px solid white',
          top: '50%',
        }}
      />

      {/* Output handle */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        style={{
          background: nodeColors.model,
          width: 10,
          height: 10,
          border: '2px solid white',
          top: '50%',
        }}
      />

      {/* Header */}
      <Box
        bg={nodeColors.model}
        color="white"
        px={3}
        py={2}
        borderTopRadius={reactFlowStyles.node.borderRadius - 2}
      >
        <HStack justify="space-between">
          <HStack spacing={2}>
            <Icon as={FiCpu} boxSize={4} />
            <Text fontSize="sm" fontWeight="semibold" noOfLines={1}>
              {data.label || 'Model'}
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

      {/* Body */}
      <Box px={3} py={2}>
        <VStack align="stretch" spacing={2}>
          {/* Provider badge */}
          <HStack justify="space-between">
            <Text fontSize="xs" color="gray.500">
              Provider
            </Text>
            <Badge colorScheme={providerColor} fontSize="xs" textTransform="capitalize">
              {provider}
            </Badge>
          </HStack>

          {/* Model name */}
          {data.modelName && (
            <HStack justify="space-between">
              <Text fontSize="xs" color="gray.500">
                Model
              </Text>
              <Text fontSize="xs" fontWeight="medium" noOfLines={1} maxW="150px">
                {data.modelName}
              </Text>
            </HStack>
          )}

          {/* Temperature */}
          {data.temperature !== undefined && (
            <HStack justify="space-between">
              <Text fontSize="xs" color="gray.500">
                Temperature
              </Text>
              <Text fontSize="xs" fontWeight="medium">
                {data.temperature}
              </Text>
            </HStack>
          )}

          {/* Max tokens */}
          {data.maxTokens !== undefined && (
            <HStack justify="space-between">
              <Text fontSize="xs" color="gray.500">
                Max Tokens
              </Text>
              <Text fontSize="xs" fontWeight="medium">
                {data.maxTokens}
              </Text>
            </HStack>
          )}
        </VStack>
      </Box>
    </Box>
  );
}

export const ModelNode = memo(ModelNodeComponent);
