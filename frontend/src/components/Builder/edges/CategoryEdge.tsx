/**
 * CategoryEdge - Custom edge component with category-based coloring
 *
 * Colors edges based on the source node's category:
 * - program: Purple (#8B5CF6)
 * - model: Pink (#EC4899)
 * - primitive: Blue (#3B82F6)
 * - utility: Green (#10B981)
 *
 * From spec section 6.4.2
 */
import { memo } from 'react';
import {
  BaseEdge,
  EdgeProps,
  getBezierPath,
  EdgeLabelRenderer,
} from 'reactflow';
import { nodeColors, reactFlowStyles, type NodeCategory } from '../theme';

/**
 * Extended edge data to include source category for styling
 */
export interface CategoryEdgeData {
  sourceCategory?: NodeCategory;
  label?: string;
  animated?: boolean;
}

/**
 * Get edge color based on source node category
 */
function getEdgeStrokeColor(
  sourceCategory?: NodeCategory,
  selected?: boolean
): string {
  if (selected) {
    return reactFlowStyles.edge.selected.stroke;
  }
  if (!sourceCategory) {
    return reactFlowStyles.edge.default.stroke;
  }
  return nodeColors[sourceCategory] || reactFlowStyles.edge.default.stroke;
}

/**
 * CategoryEdge component
 * Custom edge that inherits color from source node category
 */
export const CategoryEdge = memo(function CategoryEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
  style,
}: EdgeProps<CategoryEdgeData>) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const strokeColor = getEdgeStrokeColor(data?.sourceCategory, selected);
  const strokeWidth = selected
    ? reactFlowStyles.edge.selected.strokeWidth
    : reactFlowStyles.edge.default.strokeWidth;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          ...style,
          stroke: strokeColor,
          strokeWidth,
        }}
      />
      {data?.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              fontSize: 12,
              fontWeight: 500,
              pointerEvents: 'all',
              backgroundColor: 'white',
              padding: '2px 6px',
              borderRadius: 4,
              border: `1px solid ${strokeColor}`,
              color: strokeColor,
            }}
            className="nodrag nopan"
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
});
