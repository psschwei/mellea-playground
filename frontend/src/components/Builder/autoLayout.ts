/**
 * Auto-layout utility for visual builder canvas
 *
 * Uses dagre library to automatically arrange nodes in a directed graph layout.
 * Supports both horizontal (LR) and vertical (TB) layouts.
 */
import dagre from '@dagrejs/dagre';
import type { Node, Edge } from 'reactflow';
import type { MelleaNodeData } from './CompositionContext';

export type LayoutDirection = 'TB' | 'LR'; // Top-to-Bottom or Left-to-Right

export interface AutoLayoutOptions {
  /** Layout direction: 'TB' (top-to-bottom) or 'LR' (left-to-right) */
  direction?: LayoutDirection;
  /** Horizontal spacing between nodes */
  nodeWidth?: number;
  /** Vertical spacing between nodes */
  nodeHeight?: number;
  /** Horizontal gap between columns */
  horizontalGap?: number;
  /** Vertical gap between rows */
  verticalGap?: number;
}

const defaultOptions: Required<AutoLayoutOptions> = {
  direction: 'LR',
  nodeWidth: 200,
  nodeHeight: 100,
  horizontalGap: 80,
  verticalGap: 50,
};

/**
 * Calculate auto-layout positions for nodes using dagre
 *
 * @param nodes - Array of React Flow nodes
 * @param edges - Array of React Flow edges
 * @param options - Layout configuration options
 * @returns New array of nodes with updated positions
 */
export function autoLayout(
  nodes: Node<MelleaNodeData>[],
  edges: Edge[],
  options: AutoLayoutOptions = {}
): Node<MelleaNodeData>[] {
  if (nodes.length === 0) return nodes;

  const opts = { ...defaultOptions, ...options };

  // Create dagre graph
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({
    rankdir: opts.direction,
    nodesep: opts.direction === 'LR' ? opts.verticalGap : opts.horizontalGap,
    ranksep: opts.direction === 'LR' ? opts.horizontalGap : opts.verticalGap,
    marginx: 20,
    marginy: 20,
  });

  // Add nodes to dagre graph
  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, {
      width: opts.nodeWidth,
      height: opts.nodeHeight,
    });
  });

  // Add edges to dagre graph
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  // Calculate layout
  dagre.layout(dagreGraph);

  // Update node positions from dagre layout
  return nodes.map((node) => {
    const dagreNode = dagreGraph.node(node.id);
    if (!dagreNode) return node;

    // Dagre positions are centered, React Flow expects top-left
    return {
      ...node,
      position: {
        x: dagreNode.x - opts.nodeWidth / 2,
        y: dagreNode.y - opts.nodeHeight / 2,
      },
    };
  });
}

/**
 * Check if nodes are "messy" - overlapping or poorly spaced
 * Can be used to determine if auto-layout should be suggested
 */
export function isGraphMessy(
  nodes: Node[],
  threshold: { overlapCount?: number; minSpacing?: number } = {}
): boolean {
  const { overlapCount = 2, minSpacing = 30 } = threshold;

  if (nodes.length < 2) return false;

  let overlaps = 0;
  const nodeWidth = 200;
  const nodeHeight = 100;

  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i];
      const b = nodes[j];

      // Check for overlap or very close proximity
      const xOverlap =
        Math.abs(a.position.x - b.position.x) < nodeWidth - minSpacing;
      const yOverlap =
        Math.abs(a.position.y - b.position.y) < nodeHeight - minSpacing;

      if (xOverlap && yOverlap) {
        overlaps++;
        if (overlaps >= overlapCount) return true;
      }
    }
  }

  return false;
}
