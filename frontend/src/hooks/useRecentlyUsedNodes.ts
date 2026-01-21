/**
 * Hook for tracking recently used node types in the Visual Builder
 *
 * Persists to localStorage and provides methods to record usage and retrieve
 * the most recently used node types.
 */
import { useState, useCallback, useEffect } from 'react';
import type { MelleaNodeType } from '@/components/Builder/nodes';

interface NodeUsageEntry {
  nodeType: MelleaNodeType;
  timestamp: number;
}

interface UseRecentlyUsedNodesOptions {
  /** Maximum number of entries to track */
  maxEntries?: number;
  /** localStorage key for persistence */
  storageKey?: string;
}

const DEFAULT_MAX_ENTRIES = 10;
const DEFAULT_STORAGE_KEY = 'mellea-recently-used-nodes';

export function useRecentlyUsedNodes(options: UseRecentlyUsedNodesOptions = {}) {
  const { maxEntries = DEFAULT_MAX_ENTRIES, storageKey = DEFAULT_STORAGE_KEY } =
    options;

  const [recentNodes, setRecentNodes] = useState<NodeUsageEntry[]>([]);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const parsed = JSON.parse(stored) as NodeUsageEntry[];
        setRecentNodes(parsed);
      }
    } catch (error) {
      console.warn('Failed to load recently used nodes from localStorage:', error);
    }
  }, [storageKey]);

  // Save to localStorage whenever entries change
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(recentNodes));
    } catch (error) {
      console.warn('Failed to save recently used nodes to localStorage:', error);
    }
  }, [recentNodes, storageKey]);

  /**
   * Record usage of a node type
   * Moves the node to the front of the list if already present
   */
  const recordUsage = useCallback(
    (nodeType: MelleaNodeType) => {
      setRecentNodes((prev) => {
        // Remove existing entry for this node type
        const filtered = prev.filter((entry) => entry.nodeType !== nodeType);

        // Add new entry at the front
        const newEntry: NodeUsageEntry = {
          nodeType,
          timestamp: Date.now(),
        };

        // Limit to maxEntries
        const updated = [newEntry, ...filtered].slice(0, maxEntries);
        return updated;
      });
    },
    [maxEntries]
  );

  /**
   * Get the list of recently used node types (most recent first)
   */
  const getRecentNodeTypes = useCallback((): MelleaNodeType[] => {
    return recentNodes.map((entry) => entry.nodeType);
  }, [recentNodes]);

  /**
   * Clear all recently used entries
   */
  const clearHistory = useCallback(() => {
    setRecentNodes([]);
    try {
      localStorage.removeItem(storageKey);
    } catch (error) {
      console.warn('Failed to clear recently used nodes from localStorage:', error);
    }
  }, [storageKey]);

  return {
    /** List of recent node usage entries with timestamps */
    recentNodes,
    /** Record usage of a node type */
    recordUsage,
    /** Get just the node types (most recent first) */
    getRecentNodeTypes,
    /** Clear all history */
    clearHistory,
  };
}
