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

// Node data interface aligned with spec 6.2.1
export interface MelleaNodeData {
  label: string;
  category: NodeCategory;
  icon?: string;
  parameters?: Record<string, unknown>;
  executionState?: NodeExecutionState;
  lastRunStatus?: 'pending' | 'running' | 'succeeded' | 'failed';
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
  const { selection, selectedNode, selectNode, clearSelection, setSelection } =
    useComposition();
  return { selection, selectedNode, selectNode, clearSelection, setSelection };
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
