/**
 * CompositionContext - Canvas state management for the Visual Builder
 *
 * Provides centralized state management for:
 * - Nodes and edges (graph structure)
 * - Selection state (selected nodes/edges)
 * - Viewport state (zoom, pan position)
 * - Execution state (per-node run status)
 *
 * Uses ReactFlow's useNodesState/useEdgesState internally for optimal performance.
 */
import {
  createContext,
  useContext,
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  useNodesState,
  useEdgesState,
  addEdge,
  type Node,
  type Edge,
  type Connection,
  type OnNodesChange,
  type OnEdgesChange,
  type Viewport,
  type NodeChange,
  type EdgeChange,
} from 'reactflow';
import { type NodeCategory, type NodeExecutionState } from './theme';

// ============================================================================
// Supporting Types (spec 6.2.1)
// ============================================================================

/**
 * Slot signature for @generative functions
 * Describes typed arguments and return values
 */
export interface SlotSignature {
  name: string;
  docstring: string;
  args: Array<{ name: string; type: string; description?: string }>;
  returns: { type: string; description?: string };
}

/**
 * Parameter value types for node configuration
 */
export type ParameterValue =
  | string
  | number
  | boolean
  | null
  | ParameterValue[]
  | { [key: string]: ParameterValue };

/**
 * Sampling strategy configuration for samplers/IVR nodes
 */
export interface SamplingConfig {
  /** Maximum number of sampling attempts */
  loopBudget?: number;
  /** Template for repair attempts */
  repairTemplate?: string;
  /** Retry policy: 'none' | 'fixed' | 'exponential' */
  retryPolicy?: 'none' | 'fixed' | 'exponential';
  /** Delay between retries in milliseconds */
  retryDelayMs?: number;
  /** Maximum retries before failing */
  maxRetries?: number;
}

/**
 * Reference to an artifact produced during node execution
 */
export interface ArtifactRef {
  id: string;
  name: string;
  type: 'file' | 'json' | 'text' | 'image';
  path?: string;
  size?: number;
  mimeType?: string;
  createdAt: string;
}

// ============================================================================
// Node Data Interface (spec 6.2.1)
// ============================================================================

/**
 * MelleaNodeData - Common data shape for all node types
 * Enables consistent handling across program, model, primitive, and utility nodes
 */
export interface MelleaNodeData {
  // Display
  /** Node display label */
  label: string;
  /** Node category determines color and behavior */
  category: NodeCategory;
  /** Icon identifier or path */
  icon?: string;

  // Mellea-specific
  /** For @generative nodes: typed args/returns */
  slotSignature?: SlotSignature;
  /** Dependency libraries */
  requirements?: string[];
  /** Generated or custom code snippet */
  pythonCode?: string;

  // Configuration
  /** Node parameters */
  parameters?: Record<string, ParameterValue>;
  /** Sampling strategy: loop_budget, repair_template, etc. */
  samplingStrategy?: SamplingConfig;
  /** Per-node model selection override */
  modelOverride?: string;

  // Callbacks (injected by canvas)
  /** Called when a parameter value changes */
  onParameterChange?: (nodeId: string, param: string, value: ParameterValue) => void;
  /** Called when a slot is wired to another node */
  onSlotWire?: (nodeId: string, slotName: string, sourceNodeId: string) => void;

  // Runtime state
  /** Node execution state for visualization */
  executionState?: NodeExecutionState;
  /** Whether the node is currently being updated */
  isUpdating?: boolean;
  /** Last run status */
  lastRunStatus?: 'pending' | 'running' | 'succeeded' | 'failed';
  /** Artifacts produced by last run */
  lastRunArtifacts?: ArtifactRef[];
}

// Selection state
interface SelectionState {
  nodes: string[];
  edges: string[];
}

// Composition state shape
interface CompositionState {
  // Graph state
  nodes: Node<MelleaNodeData>[];
  edges: Edge[];

  // Selection
  selection: SelectionState;
  selectedNode: Node<MelleaNodeData> | null;

  // Viewport
  viewport: Viewport;

  // Metadata
  isDirty: boolean; // Has unsaved changes
}

// Actions available on the composition
interface CompositionActions {
  // Node operations
  addNode: (node: Node<MelleaNodeData>) => void;
  updateNode: (nodeId: string, data: Partial<MelleaNodeData>) => void;
  removeNode: (nodeId: string) => void;
  setNodes: (nodes: Node<MelleaNodeData>[]) => void;

  // Edge operations
  addEdge: (connection: Connection) => void;
  removeEdge: (edgeId: string) => void;
  setEdges: (edges: Edge[]) => void;

  // ReactFlow change handlers (for internal use)
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  onConnect: (connection: Connection) => void;

  // Selection
  setSelection: (selection: SelectionState) => void;
  selectNode: (nodeId: string | null) => void;
  clearSelection: () => void;
  selectAll: () => void;
  removeSelectedNodes: () => void;
  duplicateSelectedNodes: () => void;

  // Viewport
  setViewport: (viewport: Viewport) => void;

  // Execution state
  setNodeExecutionState: (nodeId: string, state: NodeExecutionState) => void;
  resetExecutionStates: () => void;

  // Persistence helpers
  markClean: () => void;
  getSerializableState: () => SerializableComposition;
  loadState: (state: SerializableComposition) => void;
}

// Serializable format for persistence
export interface SerializableComposition {
  nodes: Array<{
    id: string;
    type: string;
    position: { x: number; y: number };
    data: MelleaNodeData;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    sourceHandle?: string;
    targetHandle?: string;
  }>;
  viewport: Viewport;
}

// Context type
interface CompositionContextType extends CompositionState, CompositionActions {}

const CompositionContext = createContext<CompositionContextType | null>(null);

// Provider props
interface CompositionProviderProps {
  children: ReactNode;
  initialNodes?: Node<MelleaNodeData>[];
  initialEdges?: Edge[];
  initialViewport?: Viewport;
  onChange?: (state: SerializableComposition) => void;
}

const defaultViewport: Viewport = { x: 0, y: 0, zoom: 1 };

export function CompositionProvider({
  children,
  initialNodes = [],
  initialEdges = [],
  initialViewport = defaultViewport,
  onChange: _onChange,
}: CompositionProviderProps) {
  // Core graph state using ReactFlow hooks
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Selection state
  const [selection, setSelection] = useState<SelectionState>({
    nodes: [],
    edges: [],
  });

  // Viewport state
  const [viewport, setViewport] = useState<Viewport>(initialViewport);

  // Dirty flag for unsaved changes
  const [isDirty, setIsDirty] = useState(false);

  // Compute selected node from selection
  const selectedNode = useMemo(() => {
    if (selection.nodes.length === 1) {
      return nodes.find((n) => n.id === selection.nodes[0]) || null;
    }
    return null;
  }, [selection.nodes, nodes]);

  // Wrap change handlers to track dirty state
  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      onNodesChange(changes);
      setIsDirty(true);
    },
    [onNodesChange]
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      onEdgesChange(changes);
      setIsDirty(true);
    },
    [onEdgesChange]
  );

  // Connection handler
  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => addEdge(connection, eds));
      setIsDirty(true);
    },
    [setEdges]
  );

  // Node operations
  const handleAddNode = useCallback(
    (node: Node<MelleaNodeData>) => {
      setNodes((nds) => [...nds, node]);
      setIsDirty(true);
    },
    [setNodes]
  );

  const handleUpdateNode = useCallback(
    (nodeId: string, data: Partial<MelleaNodeData>) => {
      setNodes((nds) =>
        nds.map((node) =>
          node.id === nodeId
            ? { ...node, data: { ...node.data, ...data } }
            : node
        )
      );
      setIsDirty(true);
    },
    [setNodes]
  );

  const handleRemoveNode = useCallback(
    (nodeId: string) => {
      setNodes((nds) => nds.filter((node) => node.id !== nodeId));
      // Also remove connected edges
      setEdges((eds) =>
        eds.filter((edge) => edge.source !== nodeId && edge.target !== nodeId)
      );
      // Clear from selection
      setSelection((sel) => ({
        ...sel,
        nodes: sel.nodes.filter((id) => id !== nodeId),
      }));
      setIsDirty(true);
    },
    [setNodes, setEdges]
  );

  // Edge operations
  const handleAddEdge = useCallback(
    (connection: Connection) => {
      setEdges((eds) => addEdge(connection, eds));
      setIsDirty(true);
    },
    [setEdges]
  );

  const handleRemoveEdge = useCallback(
    (edgeId: string) => {
      setEdges((eds) => eds.filter((edge) => edge.id !== edgeId));
      setSelection((sel) => ({
        ...sel,
        edges: sel.edges.filter((id) => id !== edgeId),
      }));
      setIsDirty(true);
    },
    [setEdges]
  );

  // Selection operations
  const selectNode = useCallback((nodeId: string | null) => {
    setSelection({
      nodes: nodeId ? [nodeId] : [],
      edges: [],
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelection({ nodes: [], edges: [] });
  }, []);

  // Select all nodes and edges
  const selectAll = useCallback(() => {
    setSelection({
      nodes: nodes.map((n) => n.id),
      edges: edges.map((e) => e.id),
    });
  }, [nodes, edges]);

  // Remove all selected nodes (and their connected edges)
  const removeSelectedNodes = useCallback(() => {
    if (selection.nodes.length === 0 && selection.edges.length === 0) return;

    // Remove selected nodes
    setNodes((nds) => nds.filter((n) => !selection.nodes.includes(n.id)));

    // Remove edges connected to selected nodes AND selected edges
    setEdges((eds) =>
      eds.filter(
        (e) =>
          !selection.edges.includes(e.id) &&
          !selection.nodes.includes(e.source) &&
          !selection.nodes.includes(e.target)
      )
    );

    clearSelection();
    setIsDirty(true);
  }, [selection, setNodes, setEdges, clearSelection]);

  // Duplicate selected nodes
  const duplicateSelectedNodes = useCallback(() => {
    if (selection.nodes.length === 0) return;

    const selectedNodesData = nodes.filter((n) => selection.nodes.includes(n.id));
    const idMap = new Map<string, string>();

    // Create duplicated nodes with offset position
    const newNodes = selectedNodesData.map((node) => {
      const newId = `${node.id}-copy-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
      idMap.set(node.id, newId);
      return {
        ...node,
        id: newId,
        position: {
          x: node.position.x + 50,
          y: node.position.y + 50,
        },
        selected: true,
      };
    });

    // Duplicate edges between selected nodes
    const selectedEdges = edges.filter(
      (e) => selection.nodes.includes(e.source) && selection.nodes.includes(e.target)
    );
    const newEdges = selectedEdges.map((edge) => ({
      ...edge,
      id: `${edge.id}-copy-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      source: idMap.get(edge.source) || edge.source,
      target: idMap.get(edge.target) || edge.target,
    }));

    // Add new nodes and edges
    setNodes((nds) => [
      ...nds.map((n) => ({ ...n, selected: false })),
      ...newNodes,
    ]);
    setEdges((eds) => [...eds, ...newEdges]);

    // Select the new nodes
    setSelection({
      nodes: newNodes.map((n) => n.id),
      edges: newEdges.map((e) => e.id),
    });

    setIsDirty(true);
  }, [selection, nodes, edges, setNodes, setEdges]);

  // Execution state operations
  const setNodeExecutionState = useCallback(
    (nodeId: string, state: NodeExecutionState) => {
      setNodes((nds) =>
        nds.map((node) =>
          node.id === nodeId
            ? { ...node, data: { ...node.data, executionState: state } }
            : node
        )
      );
    },
    [setNodes]
  );

  const resetExecutionStates = useCallback(() => {
    setNodes((nds) =>
      nds.map((node) => ({
        ...node,
        data: { ...node.data, executionState: 'idle' as NodeExecutionState },
      }))
    );
  }, [setNodes]);

  // Persistence helpers
  const markClean = useCallback(() => {
    setIsDirty(false);
  }, []);

  const getSerializableState = useCallback((): SerializableComposition => {
    return {
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.type || 'default',
        position: n.position,
        data: n.data,
      })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.sourceHandle ?? undefined,
        targetHandle: e.targetHandle ?? undefined,
      })),
      viewport,
    };
  }, [nodes, edges, viewport]);

  const loadState = useCallback(
    (state: SerializableComposition) => {
      setNodes(
        state.nodes.map((n) => ({
          id: n.id,
          type: n.type,
          position: n.position,
          data: n.data,
        }))
      );
      setEdges(
        state.edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          sourceHandle: e.sourceHandle,
          targetHandle: e.targetHandle,
        }))
      );
      setViewport(state.viewport);
      setIsDirty(false);
      clearSelection();
    },
    [setNodes, setEdges, clearSelection]
  );

  // Notify parent of changes
  const handleSetNodes = useCallback(
    (newNodes: Node<MelleaNodeData>[]) => {
      setNodes(newNodes);
      setIsDirty(true);
    },
    [setNodes]
  );

  const handleSetEdges = useCallback(
    (newEdges: Edge[]) => {
      setEdges(newEdges);
      setIsDirty(true);
    },
    [setEdges]
  );

  // Build context value
  const value = useMemo<CompositionContextType>(
    () => ({
      // State
      nodes,
      edges,
      selection,
      selectedNode,
      viewport,
      isDirty,

      // Node operations
      addNode: handleAddNode,
      updateNode: handleUpdateNode,
      removeNode: handleRemoveNode,
      setNodes: handleSetNodes,

      // Edge operations
      addEdge: handleAddEdge,
      removeEdge: handleRemoveEdge,
      setEdges: handleSetEdges,

      // ReactFlow handlers
      onNodesChange: handleNodesChange,
      onEdgesChange: handleEdgesChange,
      onConnect,

      // Selection
      setSelection,
      selectNode,
      clearSelection,
      selectAll,
      removeSelectedNodes,
      duplicateSelectedNodes,

      // Viewport
      setViewport,

      // Execution
      setNodeExecutionState,
      resetExecutionStates,

      // Persistence
      markClean,
      getSerializableState,
      loadState,
    }),
    [
      nodes,
      edges,
      selection,
      selectedNode,
      viewport,
      isDirty,
      handleAddNode,
      handleUpdateNode,
      handleRemoveNode,
      handleSetNodes,
      handleAddEdge,
      handleRemoveEdge,
      handleSetEdges,
      handleNodesChange,
      handleEdgesChange,
      onConnect,
      selectNode,
      clearSelection,
      selectAll,
      removeSelectedNodes,
      duplicateSelectedNodes,
      setNodeExecutionState,
      resetExecutionStates,
      markClean,
      getSerializableState,
      loadState,
    ]
  );

  return (
    <CompositionContext.Provider value={value}>
      {children}
    </CompositionContext.Provider>
  );
}

/**
 * Hook to access composition state and actions
 * Must be used within a CompositionProvider
 */
export function useComposition(): CompositionContextType {
  const context = useContext(CompositionContext);
  if (!context) {
    throw new Error('useComposition must be used within a CompositionProvider');
  }
  return context;
}

/**
 * Hook to access only selection state (for components that only need selection)
 */
export function useCompositionSelection() {
  const {
    selection,
    selectedNode,
    selectNode,
    clearSelection,
    setSelection,
    selectAll,
    removeSelectedNodes,
    duplicateSelectedNodes,
  } = useComposition();
  return {
    selection,
    selectedNode,
    selectNode,
    clearSelection,
    setSelection,
    selectAll,
    removeSelectedNodes,
    duplicateSelectedNodes,
  };
}

/**
 * Hook to access only node operations (for node palette, etc.)
 */
export function useCompositionNodes() {
  const { nodes, addNode, updateNode, removeNode, setNodes } = useComposition();
  return { nodes, addNode, updateNode, removeNode, setNodes };
}

/**
 * Hook to access only edge operations
 */
export function useCompositionEdges() {
  const { edges, addEdge, removeEdge, setEdges } = useComposition();
  return { edges, addEdge, removeEdge, setEdges };
}

/**
 * Hook to access execution state operations
 */
export function useCompositionExecution() {
  const { nodes, setNodeExecutionState, resetExecutionStates } =
    useComposition();
  return { nodes, setNodeExecutionState, resetExecutionStates };
}
