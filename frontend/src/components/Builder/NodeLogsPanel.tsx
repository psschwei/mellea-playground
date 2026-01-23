/**
 * NodeLogsPanel - Displays execution logs for a selected node.
 *
 * Shows logs from the node's execution state, with auto-scrolling
 * when new logs arrive and support for copying logs to clipboard.
 */
import {
  Box,
  VStack,
  HStack,
  Text,
  Code,
  IconButton,
  Tooltip,
  Collapse,
  useColorModeValue,
  Badge,
  Divider,
} from '@chakra-ui/react';
import { FiCopy, FiChevronDown, FiChevronUp, FiTerminal } from 'react-icons/fi';
import { useEffect, useRef, useState } from 'react';
import type { NodeExecutionState } from '@/api/compositionRuns';

export interface NodeLogsPanelProps {
  /** The node execution state containing logs */
  nodeState: NodeExecutionState | null;
  /** Node label for display */
  nodeLabel?: string;
  /** Whether the panel is initially expanded */
  defaultExpanded?: boolean;
  /** Maximum height for the log container */
  maxHeight?: string;
}

export function NodeLogsPanel({
  nodeState,
  nodeLabel,
  defaultExpanded = true,
  maxHeight = '300px',
}: NodeLogsPanelProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const bgColor = useColorModeValue('gray.50', 'gray.900');
  const logBgColor = useColorModeValue('gray.100', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (isExpanded && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [nodeState?.logs, isExpanded]);

  // Copy logs to clipboard
  const handleCopyLogs = async () => {
    if (nodeState?.logs) {
      await navigator.clipboard.writeText(nodeState.logs.join('\n'));
    }
  };

  const logs = nodeState?.logs || [];
  const hasLogs = logs.length > 0;

  // Get status color
  const getStatusColor = (status: string | undefined) => {
    switch (status) {
      case 'running':
        return 'blue';
      case 'succeeded':
        return 'green';
      case 'failed':
        return 'red';
      case 'skipped':
        return 'gray';
      default:
        return 'gray';
    }
  };

  return (
    <Box
      bg={bgColor}
      borderRadius="md"
      border="1px"
      borderColor={borderColor}
      overflow="hidden"
    >
      {/* Header */}
      <HStack
        px={3}
        py={2}
        justify="space-between"
        cursor="pointer"
        onClick={() => setIsExpanded(!isExpanded)}
        _hover={{ bg: useColorModeValue('gray.100', 'gray.700') }}
      >
        <HStack spacing={2}>
          <FiTerminal />
          <Text fontSize="sm" fontWeight="medium">
            Execution Logs
          </Text>
          {nodeLabel && (
            <Text fontSize="xs" color="gray.500">
              ({nodeLabel})
            </Text>
          )}
          {nodeState?.status && (
            <Badge colorScheme={getStatusColor(nodeState.status)} size="sm">
              {nodeState.status}
            </Badge>
          )}
          {hasLogs && (
            <Badge variant="subtle" colorScheme="gray" size="sm">
              {logs.length} {logs.length === 1 ? 'entry' : 'entries'}
            </Badge>
          )}
        </HStack>
        <HStack spacing={1}>
          {hasLogs && (
            <Tooltip label="Copy logs">
              <IconButton
                aria-label="Copy logs"
                icon={<FiCopy />}
                size="xs"
                variant="ghost"
                onClick={(e) => {
                  e.stopPropagation();
                  handleCopyLogs();
                }}
              />
            </Tooltip>
          )}
          <IconButton
            aria-label={isExpanded ? 'Collapse' : 'Expand'}
            icon={isExpanded ? <FiChevronUp /> : <FiChevronDown />}
            size="xs"
            variant="ghost"
          />
        </HStack>
      </HStack>

      {/* Log content */}
      <Collapse in={isExpanded} animateOpacity>
        <Divider />
        <Box
          maxH={maxHeight}
          overflowY="auto"
          p={2}
          bg={logBgColor}
          fontFamily="mono"
          fontSize="xs"
        >
          {!hasLogs ? (
            <Text color="gray.500" fontStyle="italic" textAlign="center" py={4}>
              No logs available
            </Text>
          ) : (
            <VStack align="stretch" spacing={1}>
              {logs.map((log, index) => (
                <LogEntry key={index} log={log} />
              ))}
              <div ref={logsEndRef} />
            </VStack>
          )}
        </Box>

        {/* Node timing info */}
        {nodeState && (nodeState.startedAt || nodeState.completedAt) && (
          <>
            <Divider />
            <HStack px={3} py={2} spacing={4} fontSize="xs" color="gray.500">
              {nodeState.startedAt && (
                <Text>Started: {new Date(nodeState.startedAt).toLocaleTimeString()}</Text>
              )}
              {nodeState.completedAt && (
                <Text>Completed: {new Date(nodeState.completedAt).toLocaleTimeString()}</Text>
              )}
              {nodeState.startedAt && nodeState.completedAt && (
                <Text>
                  Duration:{' '}
                  {Math.round(
                    (new Date(nodeState.completedAt).getTime() -
                      new Date(nodeState.startedAt).getTime()) /
                      1000
                  )}
                  s
                </Text>
              )}
            </HStack>
          </>
        )}

        {/* Error message */}
        {nodeState?.errorMessage && (
          <>
            <Divider />
            <Box px={3} py={2} bg="red.50">
              <Text fontSize="xs" fontWeight="medium" color="red.600">
                Error:
              </Text>
              <Code
                fontSize="xs"
                colorScheme="red"
                display="block"
                whiteSpace="pre-wrap"
                p={2}
              >
                {nodeState.errorMessage}
              </Code>
            </Box>
          </>
        )}
      </Collapse>
    </Box>
  );
}

/** Individual log entry with syntax highlighting for common patterns */
function LogEntry({ log }: { log: string }) {
  const textColor = useColorModeValue('gray.700', 'gray.300');
  const timestampColor = useColorModeValue('blue.600', 'blue.300');

  // Parse log entry for timestamp and level
  const timestampMatch = log.match(/^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]\s*/);
  const levelMatch = log.match(/\[(DEBUG|INFO|WARN|ERROR)\]/);

  let displayLog = log;
  let timestamp = '';
  let level = '';

  if (timestampMatch) {
    timestamp = timestampMatch[1];
    displayLog = displayLog.replace(timestampMatch[0], '');
  }

  if (levelMatch) {
    level = levelMatch[1];
    displayLog = displayLog.replace(`[${level}] `, '');
  }

  return (
    <HStack spacing={2} align="start" wrap="wrap">
      {timestamp && (
        <Text color={timestampColor} whiteSpace="nowrap" flexShrink={0}>
          [{timestamp}]
        </Text>
      )}
      {level && (
        <Badge
          colorScheme={
            level === 'ERROR'
              ? 'red'
              : level === 'WARN'
                ? 'orange'
                : level === 'INFO'
                  ? 'blue'
                  : 'gray'
          }
          size="sm"
          flexShrink={0}
        >
          {level}
        </Badge>
      )}
      <Text color={textColor} wordBreak="break-word" flex={1}>
        {displayLog}
      </Text>
    </HStack>
  );
}

export default NodeLogsPanel;
