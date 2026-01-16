import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link as RouterLink } from 'react-router-dom';
import {
  Box,
  VStack,
  HStack,
  Heading,
  Text,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  Spinner,
  Center,
  IconButton,
  Button,
  Card,
  CardBody,
  useToast,
  Stat,
  StatLabel,
  StatNumber,
  StatHelpText,
  SimpleGrid,
  Link,
  Divider,
  useColorModeValue,
} from '@chakra-ui/react';
import { FiArrowLeft, FiRefreshCw, FiExternalLink, FiClock, FiTerminal } from 'react-icons/fi';
import { RunStatusBadge, LogViewer } from '@/components/Runs';
import { runsApi, programsApi } from '@/api';
import type { Run, ProgramAsset } from '@/types';

function formatDate(dateString?: string): string {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleString();
}

function formatDuration(ms?: number): string {
  if (ms === undefined || ms === null) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = ((ms % 60000) / 1000).toFixed(0);
  return `${minutes}m ${seconds}s`;
}

export function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();

  const [run, setRun] = useState<Run | null>(null);
  const [program, setProgram] = useState<ProgramAsset | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRetrying, setIsRetrying] = useState(false);

  const outputBg = useColorModeValue('gray.900', 'gray.900');
  const outputColor = useColorModeValue('green.300', 'green.300');
  const errorColor = useColorModeValue('red.300', 'red.300');

  const loadRun = useCallback(async () => {
    if (!id) return;
    try {
      const data = await runsApi.get(id);
      setRun(data);

      // Also load the program if we have a programId
      if (data.programId) {
        try {
          const programData = await programsApi.get(data.programId);
          setProgram(programData);
        } catch {
          // Program may have been deleted
          console.warn('Could not load program:', data.programId);
        }
      }
    } catch (error) {
      console.error('Failed to load run:', error);
      toast({
        title: 'Error',
        description: 'Failed to load run',
        status: 'error',
        duration: 5000,
      });
      navigate('/runs');
    } finally {
      setIsLoading(false);
    }
  }, [id, navigate, toast]);

  useEffect(() => {
    loadRun();
  }, [loadRun]);

  // Poll for updates when run is active
  useEffect(() => {
    if (!run) return;

    const isActive =
      run.status === 'queued' ||
      run.status === 'starting' ||
      run.status === 'running';

    if (!isActive) return;

    const pollInterval = setInterval(async () => {
      try {
        const updated = await runsApi.get(run.id);
        setRun(updated);

        // Stop polling if run completed
        if (
          updated.status !== 'queued' &&
          updated.status !== 'starting' &&
          updated.status !== 'running'
        ) {
          clearInterval(pollInterval);
        }
      } catch (error) {
        console.error('Failed to poll run status:', error);
      }
    }, 1000);

    return () => clearInterval(pollInterval);
  }, [run?.id, run?.status]);

  const handleRetry = async () => {
    if (!run?.programId) return;

    setIsRetrying(true);
    try {
      const newRun = await runsApi.create({ programId: run.programId });
      toast({
        title: 'Run started',
        status: 'info',
        duration: 2000,
      });
      // Navigate to the new run
      navigate(`/runs/${newRun.id}`);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to start run';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsRetrying(false);
    }
  };

  const handleCancel = async () => {
    if (!run) return;
    try {
      const cancelled = await runsApi.cancel(run.id);
      setRun(cancelled);
      toast({
        title: 'Run cancelled',
        status: 'info',
        duration: 3000,
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to cancel run';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    }
  };

  if (isLoading) {
    return (
      <Center h="300px">
        <Spinner size="lg" color="brand.500" />
      </Center>
    );
  }

  if (!run) {
    return (
      <Center h="300px">
        <Text color="gray.500">Run not found</Text>
      </Center>
    );
  }

  const isActive =
    run.status === 'queued' ||
    run.status === 'starting' ||
    run.status === 'running';

  const isRetryable = run.status === 'failed' || run.status === 'cancelled';
  const hasError = run.status === 'failed' && run.errorMessage;

  return (
    <Box>
      {/* Header */}
      <HStack justify="space-between" mb={6}>
        <HStack spacing={4}>
          <IconButton
            aria-label="Back"
            icon={<FiArrowLeft />}
            variant="ghost"
            onClick={() => navigate('/runs')}
          />
          <VStack align="start" spacing={0}>
            <HStack spacing={3}>
              <Heading size="lg">Run {run.id.slice(0, 8)}</Heading>
              <RunStatusBadge status={run.status} size="lg" />
            </HStack>
            {program && (
              <Link
                as={RouterLink}
                to={`/programs/${program.id}`}
                color="brand.500"
                fontSize="sm"
              >
                <HStack spacing={1}>
                  <Text>{program.name}</Text>
                  <FiExternalLink />
                </HStack>
              </Link>
            )}
          </VStack>
        </HStack>
        <HStack spacing={2}>
          {isActive && (
            <Button
              colorScheme="red"
              variant="outline"
              onClick={handleCancel}
            >
              Cancel
            </Button>
          )}
          {isRetryable && (
            <Button
              colorScheme="brand"
              leftIcon={<FiRefreshCw />}
              onClick={handleRetry}
              isLoading={isRetrying}
              loadingText="Starting..."
            >
              Retry
            </Button>
          )}
        </HStack>
      </HStack>

      {/* Tabs */}
      <Tabs colorScheme="brand" variant="enclosed">
        <TabList>
          <Tab>Overview</Tab>
          <Tab>Logs</Tab>
          <Tab>Metrics</Tab>
        </TabList>

        <TabPanels>
          {/* Overview Tab */}
          <TabPanel px={0}>
            <VStack spacing={6} align="stretch">
              {/* Quick Stats */}
              <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
                <Card>
                  <CardBody>
                    <Stat>
                      <StatLabel>Status</StatLabel>
                      <StatNumber>
                        <RunStatusBadge status={run.status} />
                      </StatNumber>
                    </Stat>
                  </CardBody>
                </Card>
                <Card>
                  <CardBody>
                    <Stat>
                      <StatLabel>Duration</StatLabel>
                      <StatNumber fontSize="xl">
                        {formatDuration(run.metrics?.totalDurationMs)}
                      </StatNumber>
                    </Stat>
                  </CardBody>
                </Card>
                <Card>
                  <CardBody>
                    <Stat>
                      <StatLabel>Exit Code</StatLabel>
                      <StatNumber fontSize="xl">
                        {run.exitCode ?? '-'}
                      </StatNumber>
                    </Stat>
                  </CardBody>
                </Card>
                <Card>
                  <CardBody>
                    <Stat>
                      <StatLabel>Program</StatLabel>
                      <StatNumber fontSize="md" noOfLines={1}>
                        {program?.name || run.programId.slice(0, 8)}
                      </StatNumber>
                    </Stat>
                  </CardBody>
                </Card>
              </SimpleGrid>

              {/* Details */}
              <Card>
                <CardBody>
                  <VStack align="stretch" spacing={4}>
                    <Heading size="sm">Details</Heading>
                    <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4}>
                      <Box>
                        <Text fontWeight="bold" fontSize="sm" color="gray.500">
                          Run ID
                        </Text>
                        <Text fontFamily="mono">{run.id}</Text>
                      </Box>
                      <Box>
                        <Text fontWeight="bold" fontSize="sm" color="gray.500">
                          Program ID
                        </Text>
                        <Text fontFamily="mono">{run.programId}</Text>
                      </Box>
                      <Box>
                        <Text fontWeight="bold" fontSize="sm" color="gray.500">
                          Created
                        </Text>
                        <Text>{formatDate(run.createdAt)}</Text>
                      </Box>
                      <Box>
                        <Text fontWeight="bold" fontSize="sm" color="gray.500">
                          Started
                        </Text>
                        <Text>{formatDate(run.startedAt)}</Text>
                      </Box>
                      <Box>
                        <Text fontWeight="bold" fontSize="sm" color="gray.500">
                          Completed
                        </Text>
                        <Text>{formatDate(run.completedAt)}</Text>
                      </Box>
                      {run.jobName && (
                        <Box>
                          <Text fontWeight="bold" fontSize="sm" color="gray.500">
                            Job Name
                          </Text>
                          <Text fontFamily="mono">{run.jobName}</Text>
                        </Box>
                      )}
                    </SimpleGrid>
                  </VStack>
                </CardBody>
              </Card>

              {/* Output Preview */}
              <Card>
                <CardBody>
                  <VStack align="stretch" spacing={4}>
                    <HStack justify="space-between">
                      <Heading size="sm">Output</Heading>
                    </HStack>
                    <Box
                      bg={outputBg}
                      p={4}
                      borderRadius="md"
                      fontFamily="mono"
                      fontSize="sm"
                      maxH="200px"
                      overflowY="auto"
                    >
                      {run.output ? (
                        <VStack align="stretch" spacing={0}>
                          {run.output.split('\n').slice(0, 10).map((line, i) => (
                            <HStack key={i} spacing={2} align="start">
                              <Text color="gray.600" minW="20px" userSelect="none">
                                <FiTerminal />
                              </Text>
                              <Text color={outputColor} whiteSpace="pre-wrap">
                                {line}
                              </Text>
                            </HStack>
                          ))}
                          {run.output.split('\n').length > 10 && (
                            <Text color="gray.500" mt={2}>
                              ... {run.output.split('\n').length - 10} more lines (see Logs tab)
                            </Text>
                          )}
                        </VStack>
                      ) : isActive ? (
                        <HStack color="gray.500">
                          <Spinner size="sm" />
                          <Text>Waiting for output...</Text>
                        </HStack>
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
              </Card>
            </VStack>
          </TabPanel>

          {/* Logs Tab */}
          <TabPanel px={0}>
            {isActive ? (
              <LogViewer
                runId={run.id}
                maxHeight="500px"
                isMinimizable={false}
                onComplete={() => loadRun()}
              />
            ) : (
              <Card>
                <CardBody>
                  <VStack align="stretch" spacing={4}>
                    <HStack justify="space-between">
                      <Heading size="sm">Run Logs</Heading>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => runsApi.downloadLogs(run.id)}
                      >
                        Download
                      </Button>
                    </HStack>
                    <Box
                      bg={outputBg}
                      p={4}
                      borderRadius="md"
                      fontFamily="mono"
                      fontSize="sm"
                      maxH="500px"
                      overflowY="auto"
                    >
                      {run.output ? (
                        <VStack align="stretch" spacing={0}>
                          {run.output.split('\n').map((line, i) => (
                            <HStack key={i} spacing={2} align="start">
                              <Text color="gray.600" minW="30px" userSelect="none" textAlign="right">
                                {i + 1}
                              </Text>
                              <Text color={outputColor} whiteSpace="pre-wrap">
                                {line}
                              </Text>
                            </HStack>
                          ))}
                        </VStack>
                      ) : (
                        <Text color="gray.500">No logs available</Text>
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
              </Card>
            )}
          </TabPanel>

          {/* Metrics Tab */}
          <TabPanel px={0}>
            <VStack spacing={6} align="stretch">
              {/* Timing Breakdown */}
              <Card>
                <CardBody>
                  <VStack align="stretch" spacing={4}>
                    <Heading size="sm">Timing Breakdown</Heading>
                    <SimpleGrid columns={{ base: 2, md: 4 }} spacing={4}>
                      <Stat>
                        <StatLabel>
                          <HStack spacing={1}>
                            <FiClock />
                            <Text>Queue Time</Text>
                          </HStack>
                        </StatLabel>
                        <StatNumber fontSize="xl">
                          {formatDuration(run.metrics?.queueDurationMs)}
                        </StatNumber>
                        <StatHelpText>Time in queue</StatHelpText>
                      </Stat>
                      <Stat>
                        <StatLabel>
                          <HStack spacing={1}>
                            <FiClock />
                            <Text>Startup Time</Text>
                          </HStack>
                        </StatLabel>
                        <StatNumber fontSize="xl">
                          {formatDuration(run.metrics?.startupDurationMs)}
                        </StatNumber>
                        <StatHelpText>Container startup</StatHelpText>
                      </Stat>
                      <Stat>
                        <StatLabel>
                          <HStack spacing={1}>
                            <FiClock />
                            <Text>Execution Time</Text>
                          </HStack>
                        </StatLabel>
                        <StatNumber fontSize="xl">
                          {formatDuration(run.metrics?.executionDurationMs)}
                        </StatNumber>
                        <StatHelpText>Program runtime</StatHelpText>
                      </Stat>
                      <Stat>
                        <StatLabel>
                          <HStack spacing={1}>
                            <FiClock />
                            <Text>Total Time</Text>
                          </HStack>
                        </StatLabel>
                        <StatNumber fontSize="xl">
                          {formatDuration(run.metrics?.totalDurationMs)}
                        </StatNumber>
                        <StatHelpText>End to end</StatHelpText>
                      </Stat>
                    </SimpleGrid>
                  </VStack>
                </CardBody>
              </Card>

              {/* Timestamps */}
              <Card>
                <CardBody>
                  <VStack align="stretch" spacing={4}>
                    <Heading size="sm">Timestamps</Heading>
                    <VStack align="stretch" spacing={2} divider={<Divider />}>
                      <HStack justify="space-between">
                        <Text color="gray.500">Created</Text>
                        <Text fontFamily="mono">{formatDate(run.createdAt)}</Text>
                      </HStack>
                      <HStack justify="space-between">
                        <Text color="gray.500">Started</Text>
                        <Text fontFamily="mono">{formatDate(run.startedAt)}</Text>
                      </HStack>
                      <HStack justify="space-between">
                        <Text color="gray.500">Completed</Text>
                        <Text fontFamily="mono">{formatDate(run.completedAt)}</Text>
                      </HStack>
                    </VStack>
                  </VStack>
                </CardBody>
              </Card>
            </VStack>
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
}
