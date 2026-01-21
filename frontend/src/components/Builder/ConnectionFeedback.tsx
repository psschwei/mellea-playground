/**
 * ConnectionFeedback - Visual feedback for connection attempts
 *
 * Provides real-time validation feedback during connection drag operations:
 * - Tracks which node/handle the user is dragging from
 * - Calculates which handles are valid connection targets
 * - Exposes state for styling connection lines and handles
 */
import {
  createContext,
  useContext,
  useCallback,
  useState,
  useMemo,
  type ReactNode,
} from 'react';
import type { Node, Edge, Connection, OnConnectStartParams } from 'reactflow';
import type { MelleaNodeData } from './CompositionContext';
import { ConnectionValidator, type PortDataType } from './utils';

// ============================================================================
// Types
// ============================================================================

/**
 * Information about the active connection being dragged
 */
export interface ActiveConnection {
  /** Node ID where the connection starts */
  nodeId: string;
  /** Handle ID on the source node */
  handleId: string;
  /** Whether dragging from input (target) or output (source) handle */
  handleType: 'source' | 'target';
  /** Data type of the source handle */
  dataType: PortDataType | null;
}

/**
 * Information about a potential connection target
 */
export interface HandleValidation {
  nodeId: string;
  handleId: string;
  handleType: 'source' | 'target';
  isValid: boolean;
  errorCode?: string;
}

/**
 * Current validation state during drag
 */
export interface ConnectionValidationState {
  /** Whether currently hovering over a valid target */
  isCurrentTargetValid: boolean;
  /** Error message if current target is invalid */
  currentError?: string;
  /** Error code if current target is invalid */
  currentErrorCode?: string;
}

// ============================================================================
// Context
// ============================================================================

interface ConnectionFeedbackContextType {
  // Active connection state
  activeConnection: ActiveConnection | null;
  isConnecting: boolean;

  // Validation state
  validationState: ConnectionValidationState;

  // Valid target handles for current connection
  validTargetHandles: Set<string>; // Format: "nodeId:handleId"

  // Actions
  startConnection: (
    params: OnConnectStartParams,
    nodes: Node<MelleaNodeData>[],
    edges: Edge[]
  ) => void;
  endConnection: () => void;
  updateHoverTarget: (
    connection: Connection | null,
    nodes: Node<MelleaNodeData>[],
    edges: Edge[]
  ) => void;

  // Helpers
  isHandleValidTarget: (nodeId: string, handleId: string) => boolean;
  getHandleKey: (nodeId: string, handleId: string) => string;
}

const ConnectionFeedbackContext = createContext<ConnectionFeedbackContextType | null>(null);

// ============================================================================
// Provider
// ============================================================================

interface ConnectionFeedbackProviderProps {
  children: ReactNode;
}

export function ConnectionFeedbackProvider({ children }: ConnectionFeedbackProviderProps) {
  const [activeConnection, setActiveConnection] = useState<ActiveConnection | null>(null);
  const [validTargetHandles, setValidTargetHandles] = useState<Set<string>>(new Set());
  const [validationState, setValidationState] = useState<ConnectionValidationState>({
    isCurrentTargetValid: true,
  });

  // Helper to create handle key
  const getHandleKey = useCallback((nodeId: string, handleId: string): string => {
    return `${nodeId}:${handleId}`;
  }, []);

  // Check if a handle is a valid target
  const isHandleValidTarget = useCallback(
    (nodeId: string, handleId: string): boolean => {
      return validTargetHandles.has(getHandleKey(nodeId, handleId));
    },
    [validTargetHandles, getHandleKey]
  );

  // Start a new connection drag
  const startConnection = useCallback(
    (
      params: OnConnectStartParams,
      nodes: Node<MelleaNodeData>[],
      edges: Edge[]
    ) => {
      const { nodeId, handleId, handleType } = params;
      if (!nodeId || !handleId) return;

      const validator = new ConnectionValidator(nodes, edges);

      // Get the data type of the source handle
      const dataType = validator.getPortType(
        nodeId,
        handleId,
        handleType === 'source' ? 'output' : 'input'
      );

      setActiveConnection({
        nodeId,
        handleId,
        handleType: handleType || 'source',
        dataType,
      });

      // Calculate all valid target handles
      const validHandles = new Set<string>();

      for (const node of nodes) {
        if (node.id === nodeId) continue; // Skip self

        const ports = validator.getNodePorts(node.id);
        if (!ports) continue;

        // If dragging from source (output), check input handles
        // If dragging from target (input), check output handles
        const targetPorts = handleType === 'source' ? ports.inputs : ports.outputs;

        for (const port of targetPorts) {
          // Create a test connection
          const testConnection: Connection = handleType === 'source'
            ? {
                source: nodeId,
                sourceHandle: handleId,
                target: node.id,
                targetHandle: port.id,
              }
            : {
                source: node.id,
                sourceHandle: port.id,
                target: nodeId,
                targetHandle: handleId,
              };

          const result = validator.validateConnection(testConnection);
          if (result.valid) {
            validHandles.add(getHandleKey(node.id, port.id));
          }
        }
      }

      setValidTargetHandles(validHandles);
      setValidationState({ isCurrentTargetValid: true });
    },
    [getHandleKey]
  );

  // End the connection drag
  const endConnection = useCallback(() => {
    setActiveConnection(null);
    setValidTargetHandles(new Set());
    setValidationState({ isCurrentTargetValid: true });
  }, []);

  // Update validation when hovering over a target
  const updateHoverTarget = useCallback(
    (
      connection: Connection | null,
      nodes: Node<MelleaNodeData>[],
      edges: Edge[]
    ) => {
      if (!connection || !activeConnection) {
        setValidationState({ isCurrentTargetValid: true });
        return;
      }

      const validator = new ConnectionValidator(nodes, edges);
      const result = validator.validateConnection(connection);

      setValidationState({
        isCurrentTargetValid: result.valid,
        currentError: result.error,
        currentErrorCode: result.errorCode,
      });
    },
    [activeConnection]
  );

  const value = useMemo<ConnectionFeedbackContextType>(
    () => ({
      activeConnection,
      isConnecting: activeConnection !== null,
      validationState,
      validTargetHandles,
      startConnection,
      endConnection,
      updateHoverTarget,
      isHandleValidTarget,
      getHandleKey,
    }),
    [
      activeConnection,
      validationState,
      validTargetHandles,
      startConnection,
      endConnection,
      updateHoverTarget,
      isHandleValidTarget,
      getHandleKey,
    ]
  );

  return (
    <ConnectionFeedbackContext.Provider value={value}>
      {children}
    </ConnectionFeedbackContext.Provider>
  );
}

// ============================================================================
// Hooks
// ============================================================================

/**
 * Hook to access connection feedback state and actions
 */
export function useConnectionFeedback(): ConnectionFeedbackContextType {
  const context = useContext(ConnectionFeedbackContext);
  if (!context) {
    throw new Error('useConnectionFeedback must be used within a ConnectionFeedbackProvider');
  }
  return context;
}

/**
 * Hook for components that only need to check handle validity
 */
export function useHandleValidation() {
  const { isConnecting, isHandleValidTarget, activeConnection } = useConnectionFeedback();
  return { isConnecting, isHandleValidTarget, activeConnection };
}
