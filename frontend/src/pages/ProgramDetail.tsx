import { useState, useEffect, useCallback, useRef } from 'react';
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
  useDisclosure,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  TableContainer,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  Divider,
  Checkbox,
  Tooltip,
} from '@chakra-ui/react';
import { FiArrowLeft, FiPlay, FiClock, FiTrash2, FiRefreshCw } from 'react-icons/fi';

// Helper to check if a run can be deleted (must be in terminal state)
function isTerminalStatus(status: string): boolean {
  return status === 'succeeded' || status === 'failed' || status === 'cancelled';
}
import { CodeViewer } from '@/components/Programs';
import { RunPanel, RunStatusBadge, LogViewer } from '@/components/Runs';
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
  const [isDeleting, setIsDeleting] = useState(false);
  const [isDeletingRuns, setIsDeletingRuns] = useState(false);
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());
  const [runToDelete, setRunToDelete] = useState<Run | null>(null);
  const {
    isOpen: isDeleteOpen,
    onOpen: onDeleteOpen,
    onClose: onDeleteClose,
  } = useDisclosure();
  const {
    isOpen: isDeleteRunOpen,
    onOpen: onDeleteRunOpen,
    onClose: onDeleteRunClose,
  } = useDisclosure();
  const {
    isOpen: isBulkDeleteOpen,
    onOpen: onBulkDeleteOpen,
    onClose: onBulkDeleteClose,
  } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const cancelRunRef = useRef<HTMLButtonElement>(null);
  const cancelBulkRef = useRef<HTMLButtonElement>(null);

  // Poll for updates when viewing an active run
  useEffect(() => {
    if (!currentRun) return;

    const isActive =
      currentRun.status === 'queued' ||
      currentRun.status === 'starting' ||
      currentRun.status === 'running';

    if (!isActive) return;

    const pollInterval = setInterval(async () => {
      try {
        const updated = await runsApi.get(currentRun.id);
        setCurrentRun(updated);

        // Stop polling if run completed
        if (
          updated.status !== 'queued' &&
          updated.status !== 'starting' &&
          updated.status !== 'running'
        ) {
          clearInterval(pollInterval);
          loadRuns(); // Refresh the runs list
        }
      } catch (error) {
        console.error('Failed to poll run status:', error);
      }
    }, 1000);

    return () => clearInterval(pollInterval);
  }, [currentRun?.id, currentRun?.status]);

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

  const handleRetryRun = async () => {
    if (!program) return;

    // Just trigger a new run - same as clicking the Run button
    handleRun();
  };

  const handleDeleteConfirm = async () => {
    if (!program) return;

    setIsDeleting(true);
    try {
      await programsApi.delete(program.id);
      toast({
        title: 'Program deleted',
        description: `"${program.name}" has been deleted.`,
        status: 'success',
        duration: 3000,
      });
      navigate('/programs');
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to delete program';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsDeleting(false);
      onDeleteClose();
    }
  };

  const handleDeleteRun = (run: Run, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent row click from selecting the run
    setRunToDelete(run);
    onDeleteRunOpen();
  };

  const handleDeleteRunConfirm = async () => {
    if (!runToDelete) return;

    setIsDeletingRuns(true);
    try {
      await runsApi.delete(runToDelete.id);
      toast({
        title: 'Run deleted',
        status: 'success',
        duration: 3000,
      });
      // Clear current run if it was the deleted one
      if (currentRun?.id === runToDelete.id) {
        setCurrentRun(null);
      }
      // Remove from selection
      setSelectedRunIds((prev) => {
        const next = new Set(prev);
        next.delete(runToDelete.id);
        return next;
      });
      loadRuns();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to delete run';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsDeletingRuns(false);
      setRunToDelete(null);
      onDeleteRunClose();
    }
  };

  const handleBulkDeleteConfirm = async () => {
    if (selectedRunIds.size === 0) return;

    setIsDeletingRuns(true);
    try {
      const result = await runsApi.bulkDelete(Array.from(selectedRunIds));

      if (result.failedCount > 0) {
        toast({
          title: `Deleted ${result.deletedCount} run(s)`,
          description: `${result.failedCount} run(s) could not be deleted`,
          status: 'warning',
          duration: 5000,
        });
      } else {
        toast({
          title: `Deleted ${result.deletedCount} run(s)`,
          status: 'success',
          duration: 3000,
        });
      }

      // Clear current run if it was deleted
      if (currentRun && selectedRunIds.has(currentRun.id)) {
        setCurrentRun(null);
      }

      setSelectedRunIds(new Set());
      loadRuns();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to delete runs';
      toast({
        title: 'Error',
        description: message,
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsDeletingRuns(false);
      onBulkDeleteClose();
    }
  };

  const toggleRunSelection = (runId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedRunIds((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) {
        next.delete(runId);
      } else {
        next.add(runId);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    const deletableRuns = runs.filter((r) => isTerminalStatus(r.status));
    if (selectedRunIds.size === deletableRuns.length) {
      setSelectedRunIds(new Set());
    } else {
      setSelectedRunIds(new Set(deletableRuns.map((r) => r.id)));
    }
  };

  // Count of deletable runs (in terminal state)
  const deletableRunsCount = runs.filter((r) => isTerminalStatus(r.status)).length;
  const allDeletableSelected = deletableRunsCount > 0 && selectedRunIds.size === deletableRunsCount;

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

              {/* Live Log Viewer for active runs, RunPanel for completed */}
              {currentRun && (currentRun.status === 'queued' || currentRun.status === 'starting' || currentRun.status === 'running') ? (
                <LogViewer
                  runId={currentRun.id}
                  onComplete={() => {
                    // Refresh run data when stream completes
                    runsApi.get(currentRun.id).then(setCurrentRun);
                    loadRuns();
                  }}
                />
              ) : (
                <RunPanel
                  run={currentRun}
                  onCancel={handleCancelRun}
                  onRetry={handleRetryRun}
                  onClose={() => setCurrentRun(null)}
                />
              )}
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
              <VStack align="stretch" spacing={4}>
                {/* Selected run output panel */}
                {currentRun && (currentRun.status === 'queued' || currentRun.status === 'starting' || currentRun.status === 'running') ? (
                  <LogViewer
                    runId={currentRun.id}
                    onComplete={() => {
                      runsApi.get(currentRun.id).then(setCurrentRun);
                      loadRuns();
                    }}
                  />
                ) : currentRun ? (
                  <RunPanel
                    run={currentRun}
                    onCancel={handleCancelRun}
                    onRetry={handleRetryRun}
                    onClose={() => setCurrentRun(null)}
                  />
                ) : null}

                {/* Bulk actions bar */}
                {selectedRunIds.size > 0 && (
                  <HStack bg="gray.50" p={2} borderRadius="md" justify="space-between">
                    <Text fontSize="sm" color="gray.600">
                      {selectedRunIds.size} run{selectedRunIds.size !== 1 ? 's' : ''} selected
                    </Text>
                    <Button
                      size="sm"
                      colorScheme="red"
                      variant="ghost"
                      leftIcon={<FiTrash2 />}
                      onClick={onBulkDeleteOpen}
                    >
                      Delete selected
                    </Button>
                  </HStack>
                )}
                <TableContainer>
                  <Table variant="simple" size="sm">
                    <Thead>
                      <Tr>
                        <Th w="40px">
                          <Tooltip label={allDeletableSelected ? 'Deselect all' : 'Select all deletable runs'}>
                            <Checkbox
                              isChecked={allDeletableSelected}
                              isIndeterminate={selectedRunIds.size > 0 && !allDeletableSelected}
                              onChange={toggleSelectAll}
                              isDisabled={deletableRunsCount === 0}
                            />
                          </Tooltip>
                        </Th>
                        <Th>Run ID</Th>
                        <Th>Status</Th>
                        <Th>Started</Th>
                        <Th>Duration</Th>
                        <Th>Exit Code</Th>
                        <Th w="100px">Actions</Th>
                      </Tr>
                    </Thead>
                    <Tbody>
                      {runs.map((run) => {
                        const canDelete = isTerminalStatus(run.status);
                        const canRetry = run.status === 'failed' || run.status === 'cancelled';
                        return (
                          <Tr
                            key={run.id}
                            _hover={{ bg: 'gray.50', cursor: 'pointer' }}
                            onClick={() => setCurrentRun(run)}
                            bg={selectedRunIds.has(run.id) ? 'blue.50' : undefined}
                          >
                            <Td onClick={(e) => e.stopPropagation()}>
                              <Tooltip label={canDelete ? 'Select for deletion' : 'Cannot delete active runs'}>
                                <Checkbox
                                  isChecked={selectedRunIds.has(run.id)}
                                  onChange={(e) => toggleRunSelection(run.id, e as unknown as React.MouseEvent)}
                                  isDisabled={!canDelete}
                                />
                              </Tooltip>
                            </Td>
                            <Td fontFamily="mono" fontSize="xs">
                              {run.id.slice(0, 8)}...
                            </Td>
                            <Td>
                              <RunStatusBadge status={run.status} size="sm" />
                            </Td>
                            <Td>{formatDate(run.startedAt)}</Td>
                            <Td>{formatDuration(run.metrics?.totalDurationMs)}</Td>
                            <Td>{run.exitCode ?? '-'}</Td>
                            <Td>
                              <HStack spacing={1}>
                                {canRetry && (
                                  <Tooltip label="Retry run">
                                    <IconButton
                                      aria-label="Retry run"
                                      icon={<FiRefreshCw />}
                                      size="xs"
                                      variant="ghost"
                                      colorScheme="blue"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleRetryRun();
                                      }}
                                    />
                                  </Tooltip>
                                )}
                                <Tooltip label={canDelete ? 'Delete run' : 'Cannot delete active runs'}>
                                  <IconButton
                                    aria-label="Delete run"
                                    icon={<FiTrash2 />}
                                    size="xs"
                                    variant="ghost"
                                    colorScheme="red"
                                    isDisabled={!canDelete}
                                    onClick={(e) => handleDeleteRun(run, e)}
                                  />
                                </Tooltip>
                              </HStack>
                            </Td>
                          </Tr>
                        );
                      })}
                    </Tbody>
                  </Table>
                </TableContainer>
              </VStack>
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

              <Divider my={4} />

              {/* Danger Zone */}
              <Box>
                <Text fontWeight="bold" mb={1} color="red.500">
                  Danger Zone
                </Text>
                <Text color="gray.500" mb={3} fontSize="sm">
                  Permanently delete this program and all associated files.
                </Text>
                <Button
                  colorScheme="red"
                  variant="outline"
                  leftIcon={<FiTrash2 />}
                  onClick={onDeleteOpen}
                >
                  Delete Program
                </Button>
              </Box>
            </VStack>
          </TabPanel>
        </TabPanels>
      </Tabs>

      {/* Delete Program Dialog */}
      <AlertDialog
        isOpen={isDeleteOpen}
        leastDestructiveRef={cancelRef}
        onClose={onDeleteClose}
      >
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Delete Program
            </AlertDialogHeader>

            <AlertDialogBody>
              Are you sure you want to delete "{program.name}"?
              {runs.length > 0 && (
                <Text mt={2} color="orange.500">
                  This program has {runs.length} run{runs.length !== 1 ? 's' : ''} that will no longer be accessible.
                </Text>
              )}
              <Text mt={2} color="gray.500">
                This action cannot be undone.
              </Text>
            </AlertDialogBody>

            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onDeleteClose}>
                Cancel
              </Button>
              <Button
                colorScheme="red"
                onClick={handleDeleteConfirm}
                ml={3}
                isLoading={isDeleting}
              >
                Delete
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>

      {/* Delete Single Run Dialog */}
      <AlertDialog
        isOpen={isDeleteRunOpen}
        leastDestructiveRef={cancelRunRef}
        onClose={onDeleteRunClose}
      >
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Delete Run
            </AlertDialogHeader>

            <AlertDialogBody>
              Are you sure you want to delete this run?
              {runToDelete && (
                <Text mt={2} fontFamily="mono" fontSize="sm" color="gray.600">
                  Run ID: {runToDelete.id}
                </Text>
              )}
              <Text mt={2} color="gray.500">
                This will permanently remove the run and its logs. This action cannot be undone.
              </Text>
            </AlertDialogBody>

            <AlertDialogFooter>
              <Button ref={cancelRunRef} onClick={onDeleteRunClose}>
                Cancel
              </Button>
              <Button
                colorScheme="red"
                onClick={handleDeleteRunConfirm}
                ml={3}
                isLoading={isDeletingRuns}
              >
                Delete
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>

      {/* Bulk Delete Runs Dialog */}
      <AlertDialog
        isOpen={isBulkDeleteOpen}
        leastDestructiveRef={cancelBulkRef}
        onClose={onBulkDeleteClose}
      >
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader fontSize="lg" fontWeight="bold">
              Delete {selectedRunIds.size} Run{selectedRunIds.size !== 1 ? 's' : ''}
            </AlertDialogHeader>

            <AlertDialogBody>
              Are you sure you want to delete {selectedRunIds.size} run{selectedRunIds.size !== 1 ? 's' : ''}?
              <Text mt={2} color="gray.500">
                This will permanently remove the selected runs and their logs. This action cannot be undone.
              </Text>
            </AlertDialogBody>

            <AlertDialogFooter>
              <Button ref={cancelBulkRef} onClick={onBulkDeleteClose}>
                Cancel
              </Button>
              <Button
                colorScheme="red"
                onClick={handleBulkDeleteConfirm}
                ml={3}
                isLoading={isDeletingRuns}
              >
                Delete {selectedRunIds.size} Run{selectedRunIds.size !== 1 ? 's' : ''}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
}
