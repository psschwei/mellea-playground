/**
 * Custom edge components for the Visual Builder
 *
 * Export all edge types and an edgeTypes object for ReactFlow registration.
 */
import type { EdgeTypes } from 'reactflow';
import { CategoryEdge } from './CategoryEdge';

// Export individual edge components
export { CategoryEdge } from './CategoryEdge';
export type { CategoryEdgeData } from './CategoryEdge';

// EdgeTypes object for ReactFlow registration
export const melleaEdgeTypes: EdgeTypes = {
  category: CategoryEdge,
};

// Type for edge type keys
export type MelleaEdgeType = keyof typeof melleaEdgeTypes;

// Default edge type to use when creating new edges
export const defaultEdgeType = 'category' as const;
