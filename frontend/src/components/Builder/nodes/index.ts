/**
 * Custom node components for the Visual Builder
 *
 * Export all node types and a nodeTypes object for ReactFlow registration.
 */
import type { NodeTypes } from 'reactflow';
import { ProgramNode } from './ProgramNode';
import { ModelNode } from './ModelNode';
import { PrimitiveNode } from './PrimitiveNode';
import { UtilityNode } from './UtilityNode';

// Export individual node components
export { ProgramNode } from './ProgramNode';
export { ModelNode } from './ModelNode';
export { PrimitiveNode } from './PrimitiveNode';
export { UtilityNode } from './UtilityNode';

// NodeTypes object for ReactFlow registration
export const melleaNodeTypes: NodeTypes = {
  program: ProgramNode,
  model: ModelNode,
  primitive: PrimitiveNode,
  utility: UtilityNode,
};

// Type for node type keys
export type MelleaNodeType = keyof typeof melleaNodeTypes;
