import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  VStack,
  HStack,
  Heading,
  Button,
  Text,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  Spinner,
  Center,
  IconButton,
  Badge,
  useToast,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  TableContainer,
} from '@chakra-ui/react';
import { FiArrowLeft, FiPlay, FiClock } from 'react-icons/fi';
import { CodeViewer } from '@/components/Programs';
import { RunPanel, RunStatusBadge } from '@/components/Runs';
import { programsApi, runsApi } from '@/api';
import type { ProgramAsset, Run } from '@/types';

function formatDate(dateString?: string): string {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleString();
}

function formatDuration(ms?: number): string {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function ProgramDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();

  const [program, setProgram] = useState<ProgramAsset | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [currentRun, setCurrentRun] = useState<Run | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isBuilding, setIsBuilding] = useState(false);
  const [isRunning, setIsRunning] = useState(false);

  const loadProgram = useCallback(async () => {
    if (!id) return;
    try {
      const data = await programsApi.get(id);
      setProgram(data);
    } catch (error) {
      console.error('Failed to load program:', error);
      toast({
        title: 'Error',
        description: 'Failed to load program',
        status: 'error',
        duration: 5000,
      });
      navigate('/programs');
    } finally {
      setIsLoading(false);
    }
  }, [id, navigate, toast]);

  const loadRuns = useCallback(async () => {
    if (!id) return;
    try {
      const data = await runsApi.listByProgram(id);
      setRuns(data);
    } catch (error) {
      console.error('Failed to load runs:', error);
    }
  }, [id]);

  useEffect(() => {
    loadProgram();
    loadRuns();
  }, [loadProgram, loadRuns]);

  const handleRun = async () => {
    if (!program) return;

    // Check if image needs to be built first
    if (!program.imageTag || program.imageBuildStatus !== 'ready') {
      setIsBuilding(true);
      try {
        toast({
          title: 'Building image...',
          description: 'This may take a minute',
          status: 'info',
          duration: null,
          isClosable: true,
          id: 'build-toast',
        });

        const buildResult = await programsApi.build(program.id);

        toast.close('build-toast');

        if (!buildResult.success) {
          toast({
            title: 'Build failed',
            description: buildResult.errorMessage || 'Unknown error',
            status: 'error',
            duration: 5000,
          });
          setIsBuilding(false);
          return;
        }

        toast({
          title: 'Build succeeded',
          description: buildResult.cacheHit
            ? 'Used cached image'
            : `Built in ${buildResult.totalDurationSeconds.toFixed(1)}s`,
          status: 'success',
          duration: 3000,
        });

        // Reload program to get updated imageTag
        await loadProgram();
      } catch (error: unknown) {
        toast.close('build-toast');
        const message = error instanceof Error ? error.message : 'Failed to build image';
        toast({
          title: 'Build error',
          description: message,
          status: 'error',
          duration: 5000,
        });
        setIsBuilding(false);
        return;
      } finally {
        setIsBuilding(false);
      }
    }

    // Now run the program
    setIsRunning(true);
    try {
      const run = await runsApi.create({ programId: program.id });
      setCurrentRun(run);

      toast({
        title: 'Run started',
        status: 'info',
        duration: 2000,
      });

      // Poll for status updates
      let updatedRun = run;
      while (
        updatedRun.status === 'queued' ||
        updatedRun.status === 'starting' ||
        updatedRun.status === 'running'
      ) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        updatedRun = await runsApi.get(run.id);
        setCurrentRun(updatedRun);
      }

      // Show completion toast
      if (updatedRun.status === 'succeeded') {
        toast({
          title: 'Run succeeded',
          status: 'success',
          duration: 3000,
        });
      } else if (updatedRun.status === 'failed') {
        toast({
          title: 'Run failed',
          description: updatedRun.errorMessage,
          status: 'error',
          duration: 5000,
        });
      }

      // Refresh runs list
      loadRuns();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to start run';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsRunning(false);
    }
  };

  const handleCancelRun = async () => {
    if (!currentRun) return;
    try {
      const cancelled = await runsApi.cancel(currentRun.id);
      setCurrentRun(cancelled);
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

  if (!program) {
    return (
      <Center h="300px">
        <Text color="gray.500">Program not found</Text>
      </Center>
    );
  }

  return (
    <Box>
      {/* Header */}
      <HStack justify="space-between" mb={6}>
        <HStack spacing={4}>
          <IconButton
            aria-label="Back"
            icon={<FiArrowLeft />}
            variant="ghost"
            onClick={() => navigate('/programs')}
          />
          <VStack align="start" spacing={0}>
            <Heading size="lg">{program.name}</Heading>
            {program.description && (
              <Text color="gray.500" fontSize="sm">
                {program.description}
              </Text>
            )}
          </VStack>
        </HStack>
        <Button
          colorScheme="brand"
          leftIcon={<FiPlay />}
          onClick={handleRun}
          isLoading={isBuilding || isRunning}
          loadingText={isBuilding ? 'Building...' : 'Running...'}
        >
          Run
        </Button>
      </HStack>

      {/* Program info badges */}
      <HStack spacing={3} mb={6}>
        <Badge colorScheme="blue">Python</Badge>
        <Badge variant="outline">v{program.version}</Badge>
        {program.imageBuildStatus === 'ready' && (
          <Badge colorScheme="green">Image Ready</Badge>
        )}
        {program.imageBuildStatus === 'building' && (
          <Badge colorScheme="yellow">Building Image...</Badge>
        )}
        {program.imageBuildStatus === 'failed' && (
          <Badge colorScheme="red">Build Failed</Badge>
        )}
      </HStack>

      {/* Tabs */}
      <Tabs colorScheme="brand" variant="enclosed">
        <TabList>
          <Tab>Code</Tab>
          <Tab>Runs {runs.length > 0 && <Badge ml={2}>{runs.length}</Badge>}</Tab>
          <Tab>Settings</Tab>
        </TabList>

        <TabPanels>
          {/* Code Tab */}
          <TabPanel px={0}>
            <VStack spacing={6} align="stretch">
              <CodeViewer
                code={program.sourceCode || '# No source code available'}
                filename={program.entrypoint}
                maxHeight="400px"
              />

              {/* Run Panel */}
              <RunPanel
                run={currentRun}
                onCancel={handleCancelRun}
                onClose={() => setCurrentRun(null)}
              />
            </VStack>
          </TabPanel>

          {/* Runs Tab */}
          <TabPanel px={0}>
            {runs.length === 0 ? (
              <Center py={8}>
                <VStack spacing={2}>
                  <FiClock size={32} color="gray" />
                  <Text color="gray.500">No runs yet</Text>
                  <Button
                    size="sm"
                    colorScheme="brand"
                    onClick={handleRun}
                    isLoading={isBuilding || isRunning}
                    loadingText={isBuilding ? 'Building...' : 'Running...'}
                  >
                    Run now
                  </Button>
                </VStack>
              </Center>
            ) : (
              <TableContainer>
                <Table variant="simple" size="sm">
                  <Thead>
                    <Tr>
                      <Th>Run ID</Th>
                      <Th>Status</Th>
                      <Th>Started</Th>
                      <Th>Duration</Th>
                      <Th>Exit Code</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {runs.map((run) => (
                      <Tr
                        key={run.id}
                        _hover={{ bg: 'gray.50', cursor: 'pointer' }}
                        onClick={() => setCurrentRun(run)}
                      >
                        <Td fontFamily="mono" fontSize="xs">
                          {run.id.slice(0, 8)}...
                        </Td>
                        <Td>
                          <RunStatusBadge status={run.status} size="sm" />
                        </Td>
                        <Td>{formatDate(run.startedAt)}</Td>
                        <Td>{formatDuration(run.metrics?.totalDurationMs)}</Td>
                        <Td>{run.exitCode ?? '-'}</Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>
              </TableContainer>
            )}
          </TabPanel>

          {/* Settings Tab */}
          <TabPanel px={0}>
            <VStack align="stretch" spacing={4}>
              <Box>
                <Text fontWeight="bold" mb={1}>
                  Name
                </Text>
                <Text>{program.name}</Text>
              </Box>
              <Box>
                <Text fontWeight="bold" mb={1}>
                  Description
                </Text>
                <Text color={program.description ? 'inherit' : 'gray.500'}>
                  {program.description || 'No description'}
                </Text>
              </Box>
              <Box>
                <Text fontWeight="bold" mb={1}>
                  Entrypoint
                </Text>
                <Text fontFamily="mono">{program.entrypoint}</Text>
              </Box>
              <Box>
                <Text fontWeight="bold" mb={1}>
                  Created
                </Text>
                <Text>{formatDate(program.createdAt)}</Text>
              </Box>
              <Box>
                <Text fontWeight="bold" mb={1}>
                  Resource Limits
                </Text>
                <Text>
                  CPU: {program.resourceProfile?.cpuLimit || '1'} | Memory:{' '}
                  {program.resourceProfile?.memoryLimit || '512Mi'} | Timeout:{' '}
                  {program.resourceProfile?.timeoutSeconds || 300}s
                </Text>
              </Box>
            </VStack>
          </TabPanel>
        </TabPanels>
      </Tabs>
    </Box>
  );
}
