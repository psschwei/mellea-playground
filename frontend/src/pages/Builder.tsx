import {
  Box,
  Heading,
  HStack,
  VStack,
  Text,
  Button,
  useColorModeValue,
  Badge,
  Divider,
  IconButton,
  Tooltip,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  ModalCloseButton,
  useDisclosure,
  Input,
  FormControl,
  FormLabel,
  Textarea,
  useToast,
  Spinner,
  Alert,
  AlertIcon,
  Select,
  Progress,
} from '@chakra-ui/react';
import { FiSave, FiPlay, FiTrash2, FiCopy, FiGrid, FiCode, FiSquare, FiCheck, FiX } from 'react-icons/fi';
import { ReactFlowProvider, useReactFlow } from 'reactflow';
import { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ConnectedCanvas,
  CompositionProvider,
  useCompositionSelection,
  useComposition,
  melleaNodeTypes,
  melleaEdgeTypes,
  defaultEdgeType,
  BuilderSidebar,
  CodePreviewPanel,
  NodeLogsPanel,
  type MelleaNodeData,
  type CategoryEdgeData,
  type SidebarItem,
  type SidebarRecentlyUsedEntry,
  type SerializableComposition,
} from '@/components/Builder';
import { useRecentlyUsedNodes } from '@/hooks/useRecentlyUsedNodes';
import { useCompositionExecution } from '@/hooks/useCompositionExecution';
import { compositionsApi } from '@/api/assets';
import type { CompositionAsset } from '@/types';
import type { Node, Edge } from 'reactflow';
import type { CompositionRun } from '@/api/compositionRuns';

// Minimal Environment type for the run dialog
interface Environment {
  id: string;
  programId: string;
  imageTag: string;
  status: string;
}

// Default empty composition for new compositions
const emptyNodes: Node<MelleaNodeData>[] = [];
const emptyEdges: Edge<CategoryEdgeData>[] = [];

// Composition metadata state
interface CompositionMeta {
  id?: string;
  name: string;
  description: string;
  tags: string[];
  version: string;
}

// Node details sidebar - uses composition context
interface NodeDetailsSidebarProps {
  /** Node execution states from the current run (if any) */
  nodeStates?: Record<string, import('@/api/compositionRuns').NodeExecutionState>;
}

function NodeDetailsSidebar({ nodeStates }: NodeDetailsSidebarProps) {
  const {
    selection,
    selectedNode,
    removeSelectedNodes,
    duplicateSelectedNodes,
    clearSelection,
  } = useCompositionSelection();
  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

  const selectedCount = selection.nodes.length;
  const selectedEdgeCount = selection.edges.length;

  // Get execution state for selected node
  const selectedNodeState = selectedNode?.id && nodeStates
    ? nodeStates[selectedNode.id]
    : undefined;

  // No selection
  if (selectedCount === 0) {
    return null;
  }

  // Multi-selection view
  if (selectedCount > 1) {
    return (
      <VStack
        w="300px"
        p={4}
        borderLeft="1px"
        borderColor={borderColor}
        bg={bgColor}
        align="stretch"
        spacing={4}
      >
        <Heading size="sm">Multi-Selection</Heading>
        <Box>
          <Text fontSize="sm" fontWeight="medium" color="gray.500">
            Selected Items
          </Text>
          <Text fontSize="sm">
            {selectedCount} node{selectedCount !== 1 ? 's' : ''}
            {selectedEdgeCount > 0 && (
              <>, {selectedEdgeCount} edge{selectedEdgeCount !== 1 ? 's' : ''}</>
            )}
          </Text>
        </Box>
        <Divider />
        <Box>
          <Text fontSize="xs" fontWeight="medium" color="gray.500" mb={2}>
            Actions
          </Text>
          <HStack spacing={2}>
            <Tooltip label="Duplicate selected (Ctrl+D)">
              <IconButton
                aria-label="Duplicate selected"
                icon={<FiCopy />}
                size="sm"
                variant="outline"
                onClick={duplicateSelectedNodes}
              />
            </Tooltip>
            <Tooltip label="Delete selected (Delete)">
              <IconButton
                aria-label="Delete selected"
                icon={<FiTrash2 />}
                size="sm"
                variant="outline"
                colorScheme="red"
                onClick={removeSelectedNodes}
              />
            </Tooltip>
          </HStack>
        </Box>
        <Divider />
        <Button size="sm" variant="ghost" onClick={clearSelection}>
          Clear Selection
        </Button>
        <Text fontSize="xs" color="gray.400">
          Tip: Press Esc to clear selection
        </Text>
      </VStack>
    );
  }

  // Single selection view
  const category = selectedNode?.data?.category;

  return (
    <VStack
      w="300px"
      p={4}
      borderLeft="1px"
      borderColor={borderColor}
      bg={bgColor}
      align="stretch"
      spacing={4}
    >
      <HStack justify="space-between">
        <Heading size="sm">Node Details</Heading>
        <HStack spacing={1}>
          <Tooltip label="Duplicate">
            <IconButton
              aria-label="Duplicate node"
              icon={<FiCopy />}
              size="xs"
              variant="ghost"
              onClick={duplicateSelectedNodes}
            />
          </Tooltip>
          <Tooltip label="Delete">
            <IconButton
              aria-label="Delete node"
              icon={<FiTrash2 />}
              size="xs"
              variant="ghost"
              colorScheme="red"
              onClick={removeSelectedNodes}
            />
          </Tooltip>
        </HStack>
      </HStack>
      <Box>
        <Text fontSize="sm" fontWeight="medium" color="gray.500">
          ID
        </Text>
        <Text fontSize="sm">{selectedNode?.id}</Text>
      </Box>
      <Box>
        <Text fontSize="sm" fontWeight="medium" color="gray.500">
          Label
        </Text>
        <Text fontSize="sm">{selectedNode?.data?.label || 'Unnamed'}</Text>
      </Box>
      <Box>
        <Text fontSize="sm" fontWeight="medium" color="gray.500">
          Category
        </Text>
        {category && (
          <Badge
            colorScheme={
              category === 'program'
                ? 'purple'
                : category === 'model'
                  ? 'pink'
                  : category === 'primitive'
                    ? 'blue'
                    : 'green'
            }
          >
            {category}
          </Badge>
        )}
      </Box>
      <Box>
        <Text fontSize="sm" fontWeight="medium" color="gray.500">
          Position
        </Text>
        <Text fontSize="sm">
          x: {Math.round(selectedNode?.position.x ?? 0)}, y:{' '}
          {Math.round(selectedNode?.position.y ?? 0)}
        </Text>
      </Box>
      {/* Node execution logs */}
      {selectedNodeState && (
        <>
          <Divider />
          <NodeLogsPanel
            nodeState={selectedNodeState}
            nodeLabel={selectedNode?.data?.label}
            maxHeight="200px"
          />
        </>
      )}
    </VStack>
  );
}

// Save dialog for naming new compositions
interface SaveDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (meta: CompositionMeta) => void;
  initialMeta: CompositionMeta;
  isSaving: boolean;
}

function SaveDialog({ isOpen, onClose, onSave, initialMeta, isSaving }: SaveDialogProps) {
  const [name, setName] = useState(initialMeta.name);
  const [description, setDescription] = useState(initialMeta.description);

  useEffect(() => {
    setName(initialMeta.name);
    setDescription(initialMeta.description);
  }, [initialMeta, isOpen]);

  const handleSave = () => {
    if (!name.trim()) return;
    onSave({
      ...initialMeta,
      name: name.trim(),
      description: description.trim(),
    });
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>{initialMeta.id ? 'Save Composition' : 'Save New Composition'}</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <VStack spacing={4}>
            <FormControl isRequired>
              <FormLabel>Name</FormLabel>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Composition"
                autoFocus
              />
            </FormControl>
            <FormControl>
              <FormLabel>Description</FormLabel>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe what this composition does..."
                rows={3}
              />
            </FormControl>
            {initialMeta.id && (
              <Text fontSize="sm" color="gray.500">
                Current version: {initialMeta.version} (will auto-increment on save)
              </Text>
            )}
          </VStack>
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose} isDisabled={isSaving}>
            Cancel
          </Button>
          <Button
            colorScheme="brand"
            onClick={handleSave}
            isLoading={isSaving}
            isDisabled={!name.trim()}
          >
            Save
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

// Header toolbar - uses composition context for dirty state
interface BuilderHeaderProps {
  meta: CompositionMeta;
  onSave: () => void;
  isSaving: boolean;
  showCodePreview: boolean;
  onToggleCodePreview: () => void;
  // Execution props
  onRun: () => void;
  onCancelRun: () => void;
  isRunning: boolean;
  progress: {
    total: number;
    pending: number;
    running: number;
    succeeded: number;
    failed: number;
    skipped: number;
  } | null;
  runStatus?: string;
}

function BuilderHeader({
  meta,
  onSave,
  isSaving,
  showCodePreview,
  onToggleCodePreview,
  onRun,
  onCancelRun,
  isRunning,
  progress,
  runStatus,
}: BuilderHeaderProps) {
  const { isDirty, applyAutoLayout } = useComposition();
  const bgColor = useColorModeValue('white', 'gray.800');
  const borderColor = useColorModeValue('gray.200', 'gray.700');

  // Calculate progress percentage
  const progressPercent = progress
    ? ((progress.succeeded + progress.failed + progress.skipped) / progress.total) * 100
    : 0;

  return (
    <VStack spacing={0} align="stretch">
      <HStack
        px={4}
        py={2}
        borderBottom="1px"
        borderColor={borderColor}
        bg={bgColor}
        justify="space-between"
      >
        <HStack spacing={4}>
          <Heading size="md">Visual Builder</Heading>
          <Text color="gray.500" fontSize="sm">
            {meta.name || 'Untitled Composition'}
            {meta.id && (
              <Text as="span" color="gray.400" ml={2}>
                v{meta.version}
              </Text>
            )}
            {isDirty && (
              <Text as="span" color="orange.500" ml={1}>
                (unsaved)
              </Text>
            )}
          </Text>
        </HStack>
        <HStack spacing={2}>
          <Tooltip label="Auto-layout nodes">
            <IconButton
              aria-label="Auto-layout"
              icon={<FiGrid />}
              size="sm"
              variant="outline"
              onClick={() => applyAutoLayout()}
            />
          </Tooltip>
          <Tooltip label={showCodePreview ? 'Hide code preview' : 'Show code preview'}>
            <IconButton
              aria-label="Toggle code preview"
              icon={<FiCode />}
              size="sm"
              variant={showCodePreview ? 'solid' : 'outline'}
              colorScheme={showCodePreview ? 'brand' : undefined}
              onClick={onToggleCodePreview}
            />
          </Tooltip>
          <Button
            leftIcon={<FiSave />}
            size="sm"
            variant="outline"
            onClick={onSave}
            isLoading={isSaving}
            isDisabled={isRunning}
          >
            Save
          </Button>
          {isRunning ? (
            <Button
              leftIcon={<FiSquare />}
              size="sm"
              colorScheme="red"
              variant="outline"
              onClick={onCancelRun}
            >
              Cancel
            </Button>
          ) : (
            <Button
              leftIcon={<FiPlay />}
              size="sm"
              colorScheme="brand"
              onClick={onRun}
              isDisabled={!meta.id}
            >
              Run
            </Button>
          )}
        </HStack>
      </HStack>
      {/* Execution progress bar */}
      {isRunning && progress && (
        <Box px={4} py={2} bg={bgColor} borderBottom="1px" borderColor={borderColor}>
          <HStack spacing={4} mb={1}>
            <Text fontSize="xs" color="gray.500" fontWeight="medium">
              Executing...
            </Text>
            <HStack spacing={2} fontSize="xs">
              {progress.running > 0 && (
                <Badge colorScheme="blue" variant="subtle">
                  {progress.running} running
                </Badge>
              )}
              {progress.succeeded > 0 && (
                <Badge colorScheme="green" variant="subtle">
                  <HStack spacing={1}>
                    <FiCheck size={10} />
                    <Text>{progress.succeeded}</Text>
                  </HStack>
                </Badge>
              )}
              {progress.failed > 0 && (
                <Badge colorScheme="red" variant="subtle">
                  <HStack spacing={1}>
                    <FiX size={10} />
                    <Text>{progress.failed}</Text>
                  </HStack>
                </Badge>
              )}
              <Text color="gray.400">
                {progress.succeeded + progress.failed + progress.skipped} / {progress.total}
              </Text>
            </HStack>
          </HStack>
          <Progress
            value={progressPercent}
            size="xs"
            colorScheme={progress.failed > 0 ? 'red' : 'brand'}
            borderRadius="full"
          />
        </Box>
      )}
      {/* Completed run status */}
      {!isRunning && runStatus && runStatus !== 'running' && (
        <Box px={4} py={2} bg={bgColor} borderBottom="1px" borderColor={borderColor}>
          <HStack spacing={2}>
            {runStatus === 'succeeded' ? (
              <>
                <FiCheck color="green" />
                <Text fontSize="sm" color="green.600">
                  Execution completed successfully
                </Text>
              </>
            ) : runStatus === 'failed' ? (
              <>
                <FiX color="red" />
                <Text fontSize="sm" color="red.600">
                  Execution failed
                </Text>
              </>
            ) : runStatus === 'cancelled' ? (
              <>
                <FiSquare color="orange" />
                <Text fontSize="sm" color="orange.600">
                  Execution cancelled
                </Text>
              </>
            ) : null}
          </HStack>
        </Box>
      )}
    </VStack>
  );
}

// Builder sidebar wrapper with add node logic
function BuilderSidebarWrapper() {
  const { addNode } = useComposition();
  const { getViewport } = useReactFlow();
  const { recentNodes, recordUsage } = useRecentlyUsedNodes();

  // Convert recent nodes to the format expected by BuilderSidebar
  const recentlyUsed: SidebarRecentlyUsedEntry[] = recentNodes.map((entry) => ({
    itemId: `${entry.nodeType}-${entry.nodeType}`,
    nodeType: entry.nodeType as string,
  }));

  const handleItemSelect = useCallback(
    (item: SidebarItem) => {
      const viewport = getViewport();
      const position = {
        x: (-viewport.x + 400) / viewport.zoom,
        y: (-viewport.y + 200) / viewport.zoom,
      };

      const nodeData: MelleaNodeData = {
        label: item.label,
        category: item.category,
        ...(item.defaultData as Partial<MelleaNodeData>),
      };

      const newNode: Node<MelleaNodeData> = {
        id: `${item.type}-${Date.now()}`,
        type: item.type as string,
        position,
        data: nodeData,
      };

      addNode(newNode);
      recordUsage(item.type);
    },
    [addNode, getViewport, recordUsage]
  );

  return (
    <BuilderSidebar recentlyUsed={recentlyUsed} onItemSelect={handleItemSelect} />
  );
}

// Run Dialog for selecting environment
interface RunDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onRun: (environmentId: string) => void;
  isSubmitting: boolean;
  environments: Environment[];
}

function RunDialog({ isOpen, onClose, onRun, isSubmitting, environments }: RunDialogProps) {
  const [selectedEnvId, setSelectedEnvId] = useState<string>('');

  // Auto-select first environment
  useEffect(() => {
    if (environments.length > 0 && !selectedEnvId) {
      setSelectedEnvId(environments[0].id);
    }
  }, [environments, selectedEnvId]);

  const handleRun = () => {
    if (selectedEnvId) {
      onRun(selectedEnvId);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>Run Composition</ModalHeader>
        <ModalCloseButton />
        <ModalBody>
          <FormControl isRequired>
            <FormLabel>Environment</FormLabel>
            <Select
              value={selectedEnvId}
              onChange={(e) => setSelectedEnvId(e.target.value)}
              placeholder="Select environment"
            >
              {environments.map((env) => (
                <option key={env.id} value={env.id}>
                  {env.imageTag || env.id} {env.status === 'ready' ? '(Ready)' : `(${env.status})`}
                </option>
              ))}
            </Select>
          </FormControl>
          {environments.length === 0 && (
            <Alert status="warning" mt={4}>
              <AlertIcon />
              <Text fontSize="sm">
                No environments available. Create an environment first to run compositions.
              </Text>
            </Alert>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="ghost" mr={3} onClick={onClose} isDisabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            colorScheme="brand"
            onClick={handleRun}
            isLoading={isSubmitting}
            isDisabled={!selectedEnvId || environments.length === 0}
            leftIcon={<FiPlay />}
          >
            Run
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}

// Main builder content with save/load logic
interface BuilderContentProps {
  compositionId?: string;
  onLoad: (composition: CompositionAsset) => void;
  meta: CompositionMeta;
  setMeta: (meta: CompositionMeta) => void;
}

function BuilderContent({ compositionId, onLoad, meta, setMeta }: BuilderContentProps) {
  const { getSerializableState, markClean, loadState, setNodeExecutionState, resetExecutionStates } = useComposition();
  const { isOpen: isSaveDialogOpen, onOpen: onOpenSaveDialog, onClose: onCloseSaveDialog } = useDisclosure();
  const { isOpen: isRunDialogOpen, onOpen: onOpenRunDialog, onClose: onCloseRunDialog } = useDisclosure();
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(!!compositionId);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [showCodePreview, setShowCodePreview] = useState(false);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [lastRunStatus, setLastRunStatus] = useState<string | undefined>();
  const [nodeStates, setNodeStates] = useState<Record<string, import('@/api/compositionRuns').NodeExecutionState>>({});
  const navigate = useNavigate();
  const toast = useToast();

  // Execution hook
  const execution = useCompositionExecution({
    onNodeStateChange: setNodeExecutionState,
    onResetStates: resetExecutionStates,
    onProgress: (progress) => {
      // Store node states for the logs panel
      setNodeStates(progress.nodeStates);
    },
    onComplete: (run: CompositionRun) => {
      // Store final node states
      setNodeStates(run.nodeStates);
      setLastRunStatus(run.status);
      if (run.status === 'succeeded') {
        toast({
          title: 'Execution completed',
          description: 'All nodes executed successfully',
          status: 'success',
          duration: 5000,
        });
      } else if (run.status === 'failed') {
        toast({
          title: 'Execution failed',
          description: run.errorMessage || 'One or more nodes failed',
          status: 'error',
          duration: 5000,
        });
      } else if (run.status === 'cancelled') {
        toast({
          title: 'Execution cancelled',
          status: 'warning',
          duration: 3000,
        });
      }
    },
  });

  // Fetch environments on mount
  useEffect(() => {
    const fetchEnvironments = async () => {
      try {
        const response = await fetch('/api/v1/environments');
        if (response.ok) {
          const data = await response.json();
          setEnvironments(data.environments || []);
        }
      } catch (error) {
        console.error('Failed to fetch environments:', error);
      }
    };
    fetchEnvironments();
  }, []);

  // Load composition when ID is provided
  useEffect(() => {
    if (compositionId) {
      setIsLoading(true);
      setLoadError(null);
      compositionsApi
        .get(compositionId)
        .then((composition) => {
          onLoad(composition);
          // Load graph state into context
          const state: SerializableComposition = {
            nodes: composition.graph.nodes.map((n) => ({
              id: n.id,
              type: n.type,
              position: n.position,
              data: n.data as MelleaNodeData,
            })),
            edges: composition.graph.edges.map((e) => ({
              id: e.id,
              source: e.source,
              target: e.target,
              sourceHandle: e.sourceHandle,
              targetHandle: e.targetHandle,
              type: defaultEdgeType,
              data: e.style?.stroke ? { sourceCategory: undefined } : undefined,
            })),
            viewport: composition.graph.viewport,
          };
          loadState(state);
          setIsLoading(false);
        })
        .catch((err) => {
          setLoadError(err.message || 'Failed to load composition');
          setIsLoading(false);
        });
    }
  }, [compositionId, onLoad, loadState]);

  const handleSaveClick = () => {
    // For new compositions or if we want to update metadata, show dialog
    if (!meta.id || !meta.name) {
      onOpenSaveDialog();
    } else {
      // Direct save for existing compositions
      handleSave(meta);
    }
  };

  // Handle run button click
  const handleRunClick = () => {
    onOpenRunDialog();
  };

  // Handle execution start
  const handleStartRun = async (environmentId: string) => {
    if (!meta.id) {
      toast({
        title: 'Save required',
        description: 'Please save the composition before running',
        status: 'warning',
        duration: 3000,
      });
      return;
    }

    setLastRunStatus(undefined);
    onCloseRunDialog();

    const run = await execution.startRun({
      compositionId: meta.id,
      environmentId,
    });

    if (!run) {
      toast({
        title: 'Failed to start execution',
        description: execution.error || 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    }
  };

  // Handle cancel
  const handleCancelRun = async () => {
    try {
      await execution.cancelRun();
    } catch (error) {
      toast({
        title: 'Failed to cancel',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 3000,
      });
    }
  };

  const handleSave = async (saveMeta: CompositionMeta) => {
    setIsSaving(true);
    try {
      const graphState = getSerializableState();

      // Extract program and model refs from nodes
      // These are stored in node data when linking to catalog assets
      const programRefs: string[] = [];
      const modelRefs: string[] = [];
      graphState.nodes.forEach((n) => {
        // Access optional asset reference fields via type assertion
        const data = n.data as MelleaNodeData & { programId?: string; modelId?: string };
        if (n.data.category === 'program' && data.programId) {
          programRefs.push(data.programId);
        }
        if (n.data.category === 'model' && data.modelId) {
          modelRefs.push(data.modelId);
        }
      });

      const compositionData: CompositionAsset = {
        id: saveMeta.id || '',
        type: 'composition',
        name: saveMeta.name,
        description: saveMeta.description,
        tags: saveMeta.tags,
        version: saveMeta.version,
        owner: '',
        sharing: 'private',
        createdAt: '',
        updatedAt: '',
        graph: {
          nodes: graphState.nodes.map((n) => ({
            id: n.id,
            type: n.type,
            position: n.position,
            data: {
              label: n.data.label,
              category: n.data.category as 'program' | 'model' | 'primitive' | 'utility',
              icon: n.data.icon,
              parameters: n.data.parameters as Record<string, unknown>,
            },
          })),
          edges: graphState.edges.map((e) => ({
            id: e.id,
            source: e.source,
            target: e.target,
            sourceHandle: e.sourceHandle,
            targetHandle: e.targetHandle,
          })),
          viewport: graphState.viewport,
        },
        spec: {
          inputs: [],
          outputs: [],
          nodeExecutionOrder: [],
        },
        programRefs,
        modelRefs,
      };

      const saved = await compositionsApi.save(compositionData);

      // Update meta with saved data
      setMeta({
        id: saved.id,
        name: saved.name,
        description: saved.description,
        tags: saved.tags,
        version: saved.version,
      });

      markClean();
      onCloseSaveDialog();

      toast({
        title: saveMeta.id ? 'Composition saved' : 'Composition created',
        description: `${saved.name} v${saved.version}`,
        status: 'success',
        duration: 3000,
      });

      // Navigate to edit URL if this was a new composition
      if (!saveMeta.id) {
        navigate(`/compositions/${saved.id}/edit`, { replace: true });
      }
    } catch (err) {
      toast({
        title: 'Save failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <Box h="calc(100vh - 64px)" display="flex" alignItems="center" justifyContent="center">
        <VStack spacing={4}>
          <Spinner size="xl" color="brand.500" />
          <Text color="gray.500">Loading composition...</Text>
        </VStack>
      </Box>
    );
  }

  if (loadError) {
    return (
      <Box h="calc(100vh - 64px)" display="flex" alignItems="center" justifyContent="center" p={8}>
        <Alert status="error" maxW="md">
          <AlertIcon />
          <VStack align="start" spacing={2}>
            <Text fontWeight="bold">Failed to load composition</Text>
            <Text>{loadError}</Text>
            <Button size="sm" onClick={() => navigate('/compositions')}>
              Back to Compositions
            </Button>
          </VStack>
        </Alert>
      </Box>
    );
  }

  return (
    <Box h="calc(100vh - 64px)" display="flex" flexDirection="column">
      <BuilderHeader
        meta={meta}
        onSave={handleSaveClick}
        isSaving={isSaving}
        showCodePreview={showCodePreview}
        onToggleCodePreview={() => setShowCodePreview(!showCodePreview)}
        onRun={handleRunClick}
        onCancelRun={handleCancelRun}
        isRunning={execution.isRunning}
        progress={execution.progress}
        runStatus={lastRunStatus}
      />
      <Box flex="1" display="flex" overflow="hidden">
        <BuilderSidebarWrapper />
        <Box flex="1" bg="gray.50">
          <ConnectedCanvas nodeTypes={melleaNodeTypes} edgeTypes={melleaEdgeTypes} />
        </Box>
        <NodeDetailsSidebar nodeStates={nodeStates} />
        {showCodePreview && (
          <CodePreviewPanel
            isExpanded={true}
            onToggle={() => setShowCodePreview(false)}
          />
        )}
      </Box>
      <SaveDialog
        isOpen={isSaveDialogOpen}
        onClose={onCloseSaveDialog}
        onSave={handleSave}
        initialMeta={meta}
        isSaving={isSaving}
      />
      <RunDialog
        isOpen={isRunDialogOpen}
        onClose={onCloseRunDialog}
        onRun={handleStartRun}
        isSubmitting={execution.isRunning}
        environments={environments}
      />
    </Box>
  );
}

export function BuilderPage() {
  const { id } = useParams<{ id: string }>();
  const [meta, setMeta] = useState<CompositionMeta>({
    name: '',
    description: '',
    tags: [],
    version: '1.0.0',
  });

  const handleLoad = useCallback((composition: CompositionAsset) => {
    setMeta({
      id: composition.id,
      name: composition.name,
      description: composition.description,
      tags: composition.tags,
      version: composition.version,
    });
    // Initial nodes/edges will be loaded via loadState in BuilderContent
  }, []);

  return (
    <ReactFlowProvider>
      <CompositionProvider initialNodes={emptyNodes} initialEdges={emptyEdges}>
        <BuilderContent
          compositionId={id}
          onLoad={handleLoad}
          meta={meta}
          setMeta={setMeta}
        />
      </CompositionProvider>
    </ReactFlowProvider>
  );
}
