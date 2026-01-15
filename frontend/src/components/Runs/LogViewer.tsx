import {
  Box,
  VStack,
  HStack,
  Text,
  Card,
  CardHeader,
  CardBody,
  Heading,
  useColorModeValue,
  Collapse,
  IconButton,
  Spinner,
  Badge,
} from '@chakra-ui/react';
import {
  FiChevronDown,
  FiChevronUp,
  FiTerminal,
  FiWifi,
  FiWifiOff,
  FiRefreshCw,
} from 'react-icons/fi';
import { useState, useRef, useEffect, useCallback } from 'react';
import { useLogStream, LogStreamStatus } from '@/hooks';

interface LogViewerProps {
  runId: string | null | undefined;
  isMinimizable?: boolean;
  maxHeight?: string;
  title?: string;
  onComplete?: (status: string) => void;
}

function getStatusBadge(status: LogStreamStatus) {
  switch (status) {
    case 'connecting':
      return { color: 'yellow', label: 'Connecting', icon: Spinner };
    case 'connected':
      return { color: 'green', label: 'Live', icon: FiWifi };
    case 'completed':
      return { color: 'blue', label: 'Complete', icon: null };
    case 'error':
      return { color: 'red', label: 'Error', icon: FiWifiOff };
    default:
      return { color: 'gray', label: 'Idle', icon: null };
  }
}

export function LogViewer({
  runId,
  isMinimizable = true,
  maxHeight = '300px',
  title = 'Live Output',
  onComplete,
}: LogViewerProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [autoScroll, setAutoScroll] = useState(true);
  const outputRef = useRef<HTMLDivElement>(null);

  const bg = useColorModeValue('white', 'gray.800');
  const outputBg = useColorModeValue('gray.900', 'gray.900');
  const outputColor = useColorModeValue('green.300', 'green.300');
  const borderColor = useColorModeValue('gray.200', 'gray.600');

  const { logs, status, error, connect } = useLogStream(runId, {
    onComplete,
  });

  const statusBadge = getStatusBadge(status);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  // Handle user scroll to disable auto-scroll when scrolled up
  const handleScroll = useCallback(() => {
    if (!outputRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = outputRef.current;
    // Re-enable auto-scroll if user scrolls to bottom (within 10px tolerance)
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 10;
    setAutoScroll(isAtBottom);
  }, []);

  if (!runId) {
    return (
      <Card variant="outline" borderColor={borderColor}>
        <CardBody>
          <Text color="gray.500" textAlign="center" py={8}>
            No run selected. Click "Run" to execute your program.
          </Text>
        </CardBody>
      </Card>
    );
  }

  const logLines = logs ? logs.split('\n') : [];

  return (
    <Card variant="outline" borderColor={borderColor} bg={bg}>
      <CardHeader py={3}>
        <HStack justify="space-between">
          <HStack spacing={3}>
            <Heading size="sm">{title}</Heading>
            <Badge colorScheme={statusBadge.color} display="flex" alignItems="center" gap={1}>
              {statusBadge.icon && status === 'connecting' ? (
                <Spinner size="xs" />
              ) : statusBadge.icon ? (
                <Box as={statusBadge.icon} />
              ) : null}
              {statusBadge.label}
            </Badge>
          </HStack>
          <HStack spacing={2}>
            {status === 'error' && (
              <IconButton
                aria-label="Reconnect"
                icon={<FiRefreshCw />}
                size="xs"
                variant="ghost"
                onClick={connect}
              />
            )}
            {isMinimizable && (
              <IconButton
                aria-label={isExpanded ? 'Minimize' : 'Expand'}
                icon={isExpanded ? <FiChevronDown /> : <FiChevronUp />}
                size="xs"
                variant="ghost"
                onClick={() => setIsExpanded(!isExpanded)}
              />
            )}
          </HStack>
        </HStack>
      </CardHeader>

      <Collapse in={isExpanded}>
        <CardBody pt={0}>
          <Box
            ref={outputRef}
            bg={outputBg}
            p={4}
            borderRadius="md"
            fontFamily="mono"
            fontSize="sm"
            maxH={maxHeight}
            overflowY="auto"
            onScroll={handleScroll}
          >
            {logLines.length > 0 ? (
              <VStack align="stretch" spacing={0}>
                {logLines.map((line, i) => (
                  <HStack key={i} spacing={2} align="start">
                    <Text color="gray.600" minW="20px" userSelect="none">
                      <FiTerminal />
                    </Text>
                    <Text color={outputColor} whiteSpace="pre-wrap">
                      {line}
                    </Text>
                  </HStack>
                ))}
              </VStack>
            ) : status === 'connecting' || status === 'connected' ? (
              <HStack color="gray.500">
                <Spinner size="sm" />
                <Text>Waiting for output...</Text>
              </HStack>
            ) : status === 'error' ? (
              <Text color="red.400">{error?.message || 'Connection failed'}</Text>
            ) : (
              <Text color="gray.500">No output</Text>
            )}
          </Box>

          {!autoScroll && status === 'connected' && (
            <Text fontSize="xs" color="gray.500" mt={2} textAlign="center">
              Auto-scroll paused. Scroll to bottom to resume.
            </Text>
          )}
        </CardBody>
      </Collapse>
    </Card>
  );
}
