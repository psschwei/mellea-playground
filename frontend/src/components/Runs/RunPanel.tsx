import {
  Box,
  VStack,
  HStack,
  Text,
  Button,
  Card,
  CardHeader,
  CardBody,
  Heading,
  useColorModeValue,
  Collapse,
  IconButton,
} from '@chakra-ui/react';
import { FiX, FiChevronDown, FiChevronUp, FiClock, FiTerminal, FiRefreshCw } from 'react-icons/fi';
import { useState } from 'react';
import { RunStatusBadge } from './RunStatusBadge';
import type { Run } from '@/types';

interface RunPanelProps {
  run: Run | null;
  onCancel?: () => void;
  onRetry?: () => void;
  onClose?: () => void;
  isMinimizable?: boolean;
}

function formatDuration(ms?: number): string {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  const seconds = (ms / 1000).toFixed(1);
  return `${seconds}s`;
}

function formatTime(dateString?: string): string {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleTimeString();
}

export function RunPanel({ run, onCancel, onRetry, onClose, isMinimizable = true }: RunPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const bg = useColorModeValue('white', 'gray.800');
  const outputBg = useColorModeValue('gray.900', 'gray.900');
  const outputColor = useColorModeValue('green.300', 'green.300');
  const errorColor = useColorModeValue('red.300', 'red.300');
  const borderColor = useColorModeValue('gray.200', 'gray.600');

  if (!run) {
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

  const isActive = run.status === 'queued' || run.status === 'starting' || run.status === 'running';
  const isRetryable = run.status === 'failed' || run.status === 'cancelled';
  const hasError = run.status === 'failed' && run.errorMessage;

  return (
    <Card variant="outline" borderColor={borderColor} bg={bg}>
      <CardHeader py={3}>
        <HStack justify="space-between">
          <HStack spacing={3}>
            <Heading size="sm">Run Output</Heading>
            <RunStatusBadge status={run.status} />
          </HStack>
          <HStack spacing={2}>
            {isActive && onCancel && (
              <Button size="xs" colorScheme="red" variant="outline" onClick={onCancel}>
                Cancel
              </Button>
            )}
            {isRetryable && onRetry && (
              <Button
                size="xs"
                colorScheme="blue"
                variant="outline"
                leftIcon={<FiRefreshCw />}
                onClick={onRetry}
              >
                Retry
              </Button>
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
            {onClose && (
              <IconButton
                aria-label="Close"
                icon={<FiX />}
                size="xs"
                variant="ghost"
                onClick={onClose}
              />
            )}
          </HStack>
        </HStack>
      </CardHeader>

      <Collapse in={isExpanded}>
        <CardBody pt={0}>
          <VStack align="stretch" spacing={3}>
            {/* Timing info */}
            <HStack spacing={6} fontSize="sm" color="gray.500">
              <HStack spacing={1}>
                <FiClock />
                <Text>Started: {formatTime(run.startedAt)}</Text>
              </HStack>
              {run.completedAt && (
                <HStack spacing={1}>
                  <FiClock />
                  <Text>Duration: {formatDuration(run.metrics?.totalDurationMs)}</Text>
                </HStack>
              )}
              {run.exitCode !== undefined && (
                <Text>Exit code: {run.exitCode}</Text>
              )}
            </HStack>

            {/* Output */}
            <Box
              bg={outputBg}
              p={4}
              borderRadius="md"
              fontFamily="mono"
              fontSize="sm"
              maxH="300px"
              overflowY="auto"
            >
              {run.output ? (
                <VStack align="stretch" spacing={0}>
                  {run.output.split('\n').map((line, i) => (
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
              ) : isActive ? (
                <Text color="gray.500">Waiting for output...</Text>
              ) : (
                <Text color="gray.500">No output</Text>
              )}

              {hasError && (
                <Box mt={3} pt={3} borderTop="1px solid" borderColor="gray.700">
                  <Text color={errorColor} fontWeight="bold" mb={1}>
                    Error:
                  </Text>
                  <Text color={errorColor}>{run.errorMessage}</Text>
                </Box>
              )}
            </Box>
          </VStack>
        </CardBody>
      </Collapse>
    </Card>
  );
}
