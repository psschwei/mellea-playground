/**
 * ConnectionValidator - Type checking for node connections
 *
 * Validates connections between nodes based on:
 * - Handle existence (source/target handles must exist)
 * - Handle type compatibility (output types must match input types)
 * - Connection rules (no self-connections, no duplicate connections)
 * - Handle direction (source must be output, target must be input)
 */

import type { Node, Edge, Connection } from 'reactflow';
import type { MelleaNodeData } from '../CompositionContext';

// ============================================================================
// Port Type Definitions
// ============================================================================

/**
 * Primitive data types for port connections
 */
export type PortDataType =
  | 'any' // Universal type - compatible with all types
  | 'string'
  | 'number'
  | 'boolean'
  | 'object'
  | 'array'
  | 'collection' // Iterable collection type
  | 'function' // Callable/mapper type
  | 'predicate'; // Boolean function type

/**
 * Port definition with type information
 */
export interface PortDefinition {
  id: string;
  label: string;
  type: PortDataType;
  direction: 'input' | 'output';
}

/**
 * Result of a validation check
 */
export interface ValidationResult {
  valid: boolean;
  error?: string;
  errorCode?: ValidationErrorCode;
}

/**
 * Error codes for validation failures
 */
export type ValidationErrorCode =
  | 'SELF_CONNECTION'
  | 'DUPLICATE_CONNECTION'
  | 'MISSING_SOURCE_NODE'
  | 'MISSING_TARGET_NODE'
  | 'MISSING_SOURCE_HANDLE'
  | 'MISSING_TARGET_HANDLE'
  | 'TYPE_MISMATCH'
  | 'NO_HANDLES';

// ============================================================================
// Handle Configurations (matching node implementations)
// ============================================================================

type PrimitiveType = 'loop' | 'conditional' | 'merge' | 'map' | 'filter';
type UtilityType = 'input' | 'output' | 'note' | 'constant' | 'debug';

/**
 * Primitive node handles with type information
 */
const primitiveHandles: Record<PrimitiveType, { inputs: PortDefinition[]; outputs: PortDefinition[] }> = {
  loop: {
    inputs: [{ id: 'collection', label: 'Collection', type: 'collection', direction: 'input' }],
    outputs: [
      { id: 'item', label: 'Item', type: 'any', direction: 'output' },
      { id: 'index', label: 'Index', type: 'number', direction: 'output' },
      { id: 'done', label: 'Done', type: 'boolean', direction: 'output' },
    ],
  },
  conditional: {
    inputs: [
      { id: 'condition', label: 'Condition', type: 'boolean', direction: 'input' },
      { id: 'value', label: 'Value', type: 'any', direction: 'input' },
    ],
    outputs: [
      { id: 'true', label: 'True', type: 'any', direction: 'output' },
      { id: 'false', label: 'False', type: 'any', direction: 'output' },
    ],
  },
  merge: {
    inputs: [
      { id: 'input1', label: 'Input 1', type: 'any', direction: 'input' },
      { id: 'input2', label: 'Input 2', type: 'any', direction: 'input' },
      { id: 'input3', label: 'Input 3', type: 'any', direction: 'input' },
    ],
    outputs: [{ id: 'merged', label: 'Merged', type: 'any', direction: 'output' }],
  },
  map: {
    inputs: [
      { id: 'collection', label: 'Collection', type: 'collection', direction: 'input' },
      { id: 'mapper', label: 'Mapper', type: 'function', direction: 'input' },
    ],
    outputs: [{ id: 'result', label: 'Result', type: 'collection', direction: 'output' }],
  },
  filter: {
    inputs: [
      { id: 'collection', label: 'Collection', type: 'collection', direction: 'input' },
      { id: 'predicate', label: 'Predicate', type: 'predicate', direction: 'input' },
    ],
    outputs: [{ id: 'filtered', label: 'Filtered', type: 'collection', direction: 'output' }],
  },
};

/**
 * Utility node handles with type information
 */
const utilityHandles: Record<UtilityType, { inputs: PortDefinition[]; outputs: PortDefinition[] }> = {
  input: {
    inputs: [],
    outputs: [{ id: 'value', label: 'Value', type: 'any', direction: 'output' }],
  },
  output: {
    inputs: [{ id: 'value', label: 'Value', type: 'any', direction: 'input' }],
    outputs: [],
  },
  note: {
    inputs: [],
    outputs: [],
  },
  constant: {
    inputs: [],
    outputs: [{ id: 'value', label: 'Value', type: 'any', direction: 'output' }],
  },
  debug: {
    inputs: [{ id: 'value', label: 'Value', type: 'any', direction: 'input' }],
    outputs: [{ id: 'value', label: 'Value', type: 'any', direction: 'output' }],
  },
};

// ============================================================================
// Type Compatibility
// ============================================================================

/**
 * Check if source type is compatible with target type
 * 'any' is compatible with all types
 * Other types must match exactly or be in the compatibility map
 */
function isTypeCompatible(sourceType: PortDataType, targetType: PortDataType): boolean {
  // 'any' is compatible with everything
  if (sourceType === 'any' || targetType === 'any') {
    return true;
  }

  // Exact match
  if (sourceType === targetType) {
    return true;
  }

  // Collection is compatible with array
  if (
    (sourceType === 'collection' && targetType === 'array') ||
    (sourceType === 'array' && targetType === 'collection')
  ) {
    return true;
  }

  // Function types
  if (sourceType === 'function' && (targetType === 'predicate' || targetType === 'function')) {
    return true;
  }

  return false;
}

// ============================================================================
// Node Port Extraction
// ============================================================================

interface NodePorts {
  inputs: PortDefinition[];
  outputs: PortDefinition[];
}

/**
 * Extract port definitions from a node based on its type and data
 */
function getNodePorts(node: Node<MelleaNodeData>): NodePorts {
  const nodeType = node.type;
  const data = node.data;

  switch (nodeType) {
    case 'program': {
      // Program nodes can have custom slots
      const slots = (data as { slots?: { inputs: Array<{ id: string; label: string; type?: string }>; outputs: Array<{ id: string; label: string; type?: string }> } }).slots;
      if (slots) {
        return {
          inputs: slots.inputs.map((s) => ({
            id: s.id,
            label: s.label,
            type: (s.type as PortDataType) || 'any',
            direction: 'input' as const,
          })),
          outputs: slots.outputs.map((s) => ({
            id: s.id,
            label: s.label,
            type: (s.type as PortDataType) || 'any',
            direction: 'output' as const,
          })),
        };
      }
      // Default program slots
      return {
        inputs: [{ id: 'input', label: 'Input', type: 'any', direction: 'input' }],
        outputs: [{ id: 'output', label: 'Output', type: 'any', direction: 'output' }],
      };
    }

    case 'model': {
      // Model nodes always have single input/output
      return {
        inputs: [{ id: 'input', label: 'Input', type: 'any', direction: 'input' }],
        outputs: [{ id: 'output', label: 'Output', type: 'any', direction: 'output' }],
      };
    }

    case 'primitive': {
      const primitiveType = (data as { primitiveType?: PrimitiveType }).primitiveType || 'merge';
      return primitiveHandles[primitiveType] || { inputs: [], outputs: [] };
    }

    case 'utility': {
      const utilityType = (data as { utilityType?: UtilityType }).utilityType || 'input';
      return utilityHandles[utilityType] || { inputs: [], outputs: [] };
    }

    default:
      // Unknown node type - assume single input/output
      return {
        inputs: [{ id: 'input', label: 'Input', type: 'any', direction: 'input' }],
        outputs: [{ id: 'output', label: 'Output', type: 'any', direction: 'output' }],
      };
  }
}

// ============================================================================
// ConnectionValidator Class
// ============================================================================

/**
 * ConnectionValidator provides validation for node connections
 */
export class ConnectionValidator {
  private nodes: Node<MelleaNodeData>[];
  private edges: Edge[];

  constructor(nodes: Node<MelleaNodeData>[], edges: Edge[]) {
    this.nodes = nodes;
    this.edges = edges;
  }

  /**
   * Update the nodes and edges for validation
   */
  update(nodes: Node<MelleaNodeData>[], edges: Edge[]): void {
    this.nodes = nodes;
    this.edges = edges;
  }

  /**
   * Validate a proposed connection
   */
  validateConnection(connection: Connection): ValidationResult {
    const { source, target, sourceHandle, targetHandle } = connection;

    // 1. Check for self-connection
    if (source === target) {
      return {
        valid: false,
        error: 'Cannot connect a node to itself',
        errorCode: 'SELF_CONNECTION',
      };
    }

    // 2. Find source and target nodes
    const sourceNode = this.nodes.find((n) => n.id === source);
    const targetNode = this.nodes.find((n) => n.id === target);

    if (!sourceNode) {
      return {
        valid: false,
        error: 'Source node not found',
        errorCode: 'MISSING_SOURCE_NODE',
      };
    }

    if (!targetNode) {
      return {
        valid: false,
        error: 'Target node not found',
        errorCode: 'MISSING_TARGET_NODE',
      };
    }

    // 3. Get port definitions
    const sourcePorts = getNodePorts(sourceNode);
    const targetPorts = getNodePorts(targetNode);

    // 4. Check if nodes have handles
    if (sourcePorts.outputs.length === 0) {
      return {
        valid: false,
        error: `${sourceNode.data.label || 'Source node'} has no output handles`,
        errorCode: 'NO_HANDLES',
      };
    }

    if (targetPorts.inputs.length === 0) {
      return {
        valid: false,
        error: `${targetNode.data.label || 'Target node'} has no input handles`,
        errorCode: 'NO_HANDLES',
      };
    }

    // 5. Find the specific handles
    const handleId = sourceHandle || 'output';
    const sourcePort = sourcePorts.outputs.find((p) => p.id === handleId);

    const targetHandleId = targetHandle || 'input';
    const targetPort = targetPorts.inputs.find((p) => p.id === targetHandleId);

    if (!sourcePort) {
      return {
        valid: false,
        error: `Output handle "${handleId}" not found on ${sourceNode.data.label || 'source node'}`,
        errorCode: 'MISSING_SOURCE_HANDLE',
      };
    }

    if (!targetPort) {
      return {
        valid: false,
        error: `Input handle "${targetHandleId}" not found on ${targetNode.data.label || 'target node'}`,
        errorCode: 'MISSING_TARGET_HANDLE',
      };
    }

    // 6. Check for duplicate connection
    const existingConnection = this.edges.find(
      (e) =>
        e.source === source &&
        e.target === target &&
        (e.sourceHandle || 'output') === handleId &&
        (e.targetHandle || 'input') === targetHandleId
    );

    if (existingConnection) {
      return {
        valid: false,
        error: 'Connection already exists',
        errorCode: 'DUPLICATE_CONNECTION',
      };
    }

    // 7. Check type compatibility
    if (!isTypeCompatible(sourcePort.type, targetPort.type)) {
      return {
        valid: false,
        error: `Type mismatch: cannot connect ${sourcePort.type} output to ${targetPort.type} input`,
        errorCode: 'TYPE_MISMATCH',
      };
    }

    // All checks passed
    return { valid: true };
  }

  /**
   * Check if a connection would be valid (convenience method)
   */
  isValidConnection(connection: Connection): boolean {
    return this.validateConnection(connection).valid;
  }

  /**
   * Get the port type for a specific handle on a node
   */
  getPortType(nodeId: string, handleId: string, direction: 'input' | 'output'): PortDataType | null {
    const node = this.nodes.find((n) => n.id === nodeId);
    if (!node) return null;

    const ports = getNodePorts(node);
    const portList = direction === 'input' ? ports.inputs : ports.outputs;
    const port = portList.find((p) => p.id === handleId);

    return port?.type || null;
  }

  /**
   * Get all ports for a node
   */
  getNodePorts(nodeId: string): NodePorts | null {
    const node = this.nodes.find((n) => n.id === nodeId);
    if (!node) return null;
    return getNodePorts(node);
  }
}

// ============================================================================
// Factory function for easy creation
// ============================================================================

/**
 * Create a new ConnectionValidator instance
 */
export function createConnectionValidator(
  nodes: Node<MelleaNodeData>[],
  edges: Edge[]
): ConnectionValidator {
  return new ConnectionValidator(nodes, edges);
}

// ============================================================================
// Hook-friendly validation function
// ============================================================================

/**
 * Standalone validation function for use in callbacks
 * Useful when you don't want to maintain a validator instance
 */
export function validateConnection(
  connection: Connection,
  nodes: Node<MelleaNodeData>[],
  edges: Edge[]
): ValidationResult {
  const validator = new ConnectionValidator(nodes, edges);
  return validator.validateConnection(connection);
}
