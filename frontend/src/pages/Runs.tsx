import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  HStack,
  Heading,
  Text,
  Select,
  Input,
  InputGroup,
  InputLeftElement,
  Button,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  TableContainer,
  Spinner,
  Center,
  Icon,
  Checkbox,
  Tooltip,
  IconButton,
  useToast,
  useDisclosure,
  AlertDialog,
  AlertDialogBody,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogContent,
  AlertDialogOverlay,
  Badge,
  Collapse,
} from '@chakra-ui/react';
import { FiClock, FiSearch, FiTrash2, FiChevronDown, FiChevronRight, FiExternalLink, FiRefreshCw } from 'react-icons/fi';
import { RunStatusBadge, RunPanel } from '@/components/Runs';
import { runsApi, programsApi } from '@/api';
import type { Run, ProgramAsset, RunExecutionStatus } from '@/types';

function formatDate(dateString?: string): string {
  if (!dateString) return '-';
  return new Date(dateString).toLocaleString();
}

function formatDuration(ms?: number): string {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function isTerminalStatus(status: string): boolean {
  return status === 'succeeded' || status === 'failed' || status === 'cancelled';
}

interface RunFilters {
  status: RunExecutionStatus | 'all';
  programId: string;
  search: string;
}

export function RunsPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const cancelBulkRef = useRef<HTMLButtonElement>(null);
  const cancelDeleteRef = useRef<HTMLButtonElement>(null);

  const [runs, setRuns] = useState<Run[]>([]);
  const [programs, setPrograms] = useState<ProgramAsset[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [filters, setFilters] = useState<RunFilters>({
    status: 'all',
    programId: '',
    search: '',
  });
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [isDeletingRuns, setIsDeletingRuns] = useState(false);
  const [runToDelete, setRunToDelete] = useState<Run | null>(null);

  const {
    isOpen: isBulkDeleteOpen,
    onOpen: onBulkDeleteOpen,
    onClose: onBulkDeleteClose,
  } = useDisclosure();
  const {
    isOpen: isDeleteOpen,
    onOpen: onDeleteOpen,
    onClose: onDeleteClose,
  } = useDisclosure();

  const loadPrograms = useCallback(async () => {
    try {
      const data = await programsApi.list();
      setPrograms(data);
    } catch (error) {
      console.error('Failed to load programs:', error);
    }
  }, []);

  const loadRuns = useCallback(async (showRefreshing = false) => {
    if (showRefreshing) {
      setIsRefreshing(true);
    }
    try {
      const data = await runsApi.list({
        programId: filters.programId || undefined,
        status: filters.status !== 'all' ? filters.status : undefined,
      });
      setRuns(data);
    } catch (error) {
      console.error('Failed to load runs:', error);
      toast({
        title: 'Error',
        description: 'Failed to load runs',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [filters.programId, filters.status, toast]);

  useEffect(() => {
    loadPrograms();
  }, [loadPrograms]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  // Filter runs by search term (client-side)
  const filteredRuns = runs.filter((run) => {
    if (!filters.search) return true;
    const searchLower = filters.search.toLowerCase();
    const program = programs.find((p) => p.id === run.programId);
    return (
      run.id.toLowerCase().includes(searchLower) ||
      program?.name.toLowerCase().includes(searchLower)
    );
  });

  const handleRefresh = () => {
    loadRuns(true);
  };

  const handleDeleteRun = (run: Run, e: React.MouseEvent) => {
    e.stopPropagation();
    setRunToDelete(run);
    onDeleteOpen();
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
      if (expandedRunId === runToDelete.id) {
        setExpandedRunId(null);
      }
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
      onDeleteClose();
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

      if (expandedRunId && selectedRunIds.has(expandedRunId)) {
        setExpandedRunId(null);
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
    const deletableRuns = filteredRuns.filter((r) => isTerminalStatus(r.status));
    if (selectedRunIds.size === deletableRuns.length && deletableRuns.length > 0) {
      setSelectedRunIds(new Set());
    } else {
      setSelectedRunIds(new Set(deletableRuns.map((r) => r.id)));
    }
  };

  const toggleExpand = (runId: string) => {
    setExpandedRunId(expandedRunId === runId ? null : runId);
  };

  const getProgramName = (programId: string): string => {
    const program = programs.find((p) => p.id === programId);
    return program?.name || programId.slice(0, 8) + '...';
  };

  const deletableRunsCount = filteredRuns.filter((r) => isTerminalStatus(r.status)).length;
  const allDeletableSelected = deletableRunsCount > 0 && selectedRunIds.size === deletableRunsCount;

  if (isLoading) {
    return (
      <Center h="300px">
        <Spinner size="lg" color="brand.500" />
      </Center>
    );
  }

  return (
    <Box>
      {/* Header */}
      <HStack justify="space-between" mb={6}>
        <Heading size="lg">Runs</Heading>
        <Button
          leftIcon={<FiRefreshCw />}
          variant="outline"
          onClick={handleRefresh}
          isLoading={isRefreshing}
          loadingText="Refreshing"
        >
          Refresh
        </Button>
      </HStack>

      {/* Filters */}
      <HStack spacing={4} mb={6} flexWrap="wrap">
        <Select
          w="180px"
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value as RunFilters['status'] })}
        >
          <option value="all">All Statuses</option>
          <option value="queued">Queued</option>
          <option value="starting">Starting</option>
          <option value="running">Running</option>
          <option value="succeeded">Succeeded</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </Select>

        <Select
          w="200px"
          value={filters.programId}
          onChange={(e) => setFilters({ ...filters, programId: e.target.value })}
        >
          <option value="">All Programs</option>
          {programs.map((program) => (
            <option key={program.id} value={program.id}>
              {program.name}
            </option>
          ))}
        </Select>

        <InputGroup w="250px">
          <InputLeftElement pointerEvents="none">
            <Icon as={FiSearch} color="gray.400" />
          </InputLeftElement>
          <Input
            placeholder="Search runs..."
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
          />
        </InputGroup>

        {(filters.status !== 'all' || filters.programId || filters.search) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setFilters({ status: 'all', programId: '', search: '' })}
          >
            Clear filters
          </Button>
        )}
      </HStack>

      {/* Stats badges */}
      <HStack spacing={4} mb={4}>
        <Badge colorScheme="gray" px={2} py={1}>
          Total: {filteredRuns.length}
        </Badge>
        <Badge colorScheme="green" px={2} py={1}>
          Succeeded: {filteredRuns.filter((r) => r.status === 'succeeded').length}
        </Badge>
        <Badge colorScheme="red" px={2} py={1}>
          Failed: {filteredRuns.filter((r) => r.status === 'failed').length}
        </Badge>
        <Badge colorScheme="blue" px={2} py={1}>
          Running: {filteredRuns.filter((r) => r.status === 'running' || r.status === 'starting' || r.status === 'queued').length}
        </Badge>
      </HStack>

      {/* Bulk actions bar */}
      {selectedRunIds.size > 0 && (
        <HStack bg="blue.50" p={3} borderRadius="md" justify="space-between" mb={4}>
          <Text fontSize="sm" fontWeight="medium" color="blue.700">
            {selectedRunIds.size} run{selectedRunIds.size !== 1 ? 's' : ''} selected
          </Text>
          <Button
            size="sm"
            colorScheme="red"
            variant="solid"
            leftIcon={<FiTrash2 />}
            onClick={onBulkDeleteOpen}
          >
            Delete selected
          </Button>
        </HStack>
      )}

      {/* Runs table */}
      {filteredRuns.length === 0 ? (
        <Center
          py={16}
          flexDirection="column"
          borderWidth={2}
          borderStyle="dashed"
          borderColor="gray.300"
          borderRadius="lg"
        >
          <Icon as={FiClock} boxSize={12} color="gray.400" mb={4} />
          <Text color="gray.500" fontSize="lg" mb={2}>
            No runs found
          </Text>
          <Text color="gray.400">
            {filters.status !== 'all' || filters.programId || filters.search
              ? 'Try adjusting your filters'
              : 'Run a program to see executions here'}
          </Text>
        </Center>
      ) : (
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
                <Th w="40px"></Th>
                <Th>Run ID</Th>
                <Th>Program</Th>
                <Th>Status</Th>
                <Th>Started</Th>
                <Th>Duration</Th>
                <Th>Exit Code</Th>
                <Th w="100px">Actions</Th>
              </Tr>
            </Thead>
            <Tbody>
              {filteredRuns.map((run) => {
                const canDelete = isTerminalStatus(run.status);
                const isExpanded = expandedRunId === run.id;
                return (
                  <>
                    <Tr
                      key={run.id}
                      _hover={{ bg: 'gray.50', cursor: 'pointer' }}
                      onClick={() => toggleExpand(run.id)}
                      bg={selectedRunIds.has(run.id) ? 'blue.50' : isExpanded ? 'gray.50' : undefined}
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
                      <Td>
                        <Icon
                          as={isExpanded ? FiChevronDown : FiChevronRight}
                          color="gray.500"
                        />
                      </Td>
                      <Td fontFamily="mono" fontSize="xs">
                        {run.id.slice(0, 8)}...
                      </Td>
                      <Td>
                        <HStack spacing={2}>
                          <Text fontSize="sm" noOfLines={1} maxW="150px">
                            {getProgramName(run.programId)}
                          </Text>
                          <Tooltip label="View program">
                            <IconButton
                              aria-label="View program"
                              icon={<FiExternalLink />}
                              size="xs"
                              variant="ghost"
                              onClick={(e) => {
                                e.stopPropagation();
                                navigate(`/programs/${run.programId}`);
                              }}
                            />
                          </Tooltip>
                        </HStack>
                      </Td>
                      <Td>
                        <RunStatusBadge status={run.status} size="sm" />
                      </Td>
                      <Td fontSize="sm">{formatDate(run.startedAt)}</Td>
                      <Td fontSize="sm">{formatDuration(run.metrics?.totalDurationMs)}</Td>
                      <Td fontSize="sm">{run.exitCode ?? '-'}</Td>
                      <Td>
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
                      </Td>
                    </Tr>
                    {isExpanded && (
                      <Tr key={`${run.id}-expanded`}>
                        <Td colSpan={9} p={0} borderBottom="none">
                          <Collapse in={isExpanded} animateOpacity>
                            <Box p={4} bg="gray.50" borderBottomWidth={1}>
                              <RunPanel
                                run={run}
                                onClose={() => setExpandedRunId(null)}
                              />
                            </Box>
                          </Collapse>
                        </Td>
                      </Tr>
                    )}
                  </>
                );
              })}
            </Tbody>
          </Table>
        </TableContainer>
      )}

      {/* Delete Single Run Dialog */}
      <AlertDialog
        isOpen={isDeleteOpen}
        leastDestructiveRef={cancelDeleteRef}
        onClose={onDeleteClose}
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
              <Button ref={cancelDeleteRef} onClick={onDeleteClose}>
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
