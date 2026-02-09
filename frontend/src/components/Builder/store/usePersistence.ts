/**
 * Persistence hook for composition state
 *
 * Connects the Zustand store to the backend API for:
 * - Loading compositions
 * - Auto-saving changes
 * - Manual save operations
 */
import { useEffect, useCallback } from 'react';
import apiClient from '@/api/client';
import { useCompositionStore, type SerializableComposition } from './compositionStore';
import type { CompositionAsset } from '@/types';

export interface PersistenceConfig {
  /** Composition ID (null for new compositions) */
  compositionId: string | null;
  /** Enable auto-save (default: true) */
  autoSave?: boolean;
  /** Callback when save completes */
  onSaveComplete?: (composition: CompositionAsset) => void;
  /** Callback when save fails */
  onSaveError?: (error: Error) => void;
  /** Callback when load completes */
  onLoadComplete?: (composition: CompositionAsset) => void;
  /** Callback when load fails */
  onLoadError?: (error: Error) => void;
}

/**
 * Hook to manage composition persistence
 *
 * Usage:
 * ```tsx
 * const { save, load, isLoading, isSaving, error } = useCompositionPersistence({
 *   compositionId: 'comp-123',
 *   autoSave: true,
 *   onSaveComplete: (comp) => console.log('Saved:', comp.id),
 * });
 * ```
 */
export function useCompositionPersistence(config: PersistenceConfig) {
  const {
    compositionId,
    autoSave = true,
    onSaveComplete,
    onSaveError,
    onLoadComplete,
    onLoadError,
  } = config;

  const {
    loadState,
    setMetadata,
    getSerializableState,
    enableAutoSave,
    setOnPersist,
    autoSave: autoSaveState,
    metadata,
  } = useCompositionStore();

  // Create the persist callback for auto-save
  const persistToApi = useCallback(
    async (state: SerializableComposition): Promise<void> => {
      const currentMetadata = useCompositionStore.getState().metadata;

      try {
        let response: { data: CompositionAsset };

        if (currentMetadata.id) {
          // Update existing composition
          response = await apiClient.patch<CompositionAsset>(
            `/compositions/${currentMetadata.id}`,
            {
              graph: {
                nodes: state.nodes,
                edges: state.edges,
                viewport: state.viewport,
              },
            }
          );
        } else {
          // Create new composition
          response = await apiClient.post<CompositionAsset>('/compositions', {
            type: 'composition',
            name: currentMetadata.name || 'Untitled Composition',
            description: currentMetadata.description || '',
            graph: {
              nodes: state.nodes,
              edges: state.edges,
              viewport: state.viewport,
            },
            spec: {
              inputs: [],
              outputs: [],
              nodeExecutionOrder: [],
            },
            programRefs: [],
            modelRefs: [],
          });

          // Update metadata with the new ID
          setMetadata({
            id: response.data.id,
            createdAt: response.data.createdAt,
          });
        }

        setMetadata({ updatedAt: new Date().toISOString() });
        onSaveComplete?.(response.data);
      } catch (error) {
        const err = error instanceof Error ? error : new Error('Save failed');
        onSaveError?.(err);
        throw err;
      }
    },
    [setMetadata, onSaveComplete, onSaveError]
  );

  // Load composition from API
  const load = useCallback(
    async (id: string): Promise<CompositionAsset | null> => {
      try {
        const response = await apiClient.get<CompositionAsset>(`/compositions/${id}`);
        const composition = response.data;

        // Load the graph state
        loadState(
          {
            nodes: composition.graph.nodes.map((n) => ({
              ...n,
              data: n.data as import('../CompositionContext').MelleaNodeData,
            })),
            edges: composition.graph.edges,
            viewport: composition.graph.viewport,
          },
          {
            id: composition.id,
            name: composition.name,
            description: composition.description,
            ownerId: composition.owner,
            version: parseInt(composition.version, 10) || 1,
            createdAt: composition.createdAt,
            updatedAt: composition.updatedAt,
          }
        );

        onLoadComplete?.(composition);
        return composition;
      } catch (error) {
        const err = error instanceof Error ? error : new Error('Load failed');
        onLoadError?.(err);
        return null;
      }
    },
    [loadState, onLoadComplete, onLoadError]
  );

  // Manual save
  const save = useCallback(async (): Promise<CompositionAsset | null> => {
    const state = getSerializableState();
    try {
      await persistToApi(state);
      const currentMetadata = useCompositionStore.getState().metadata;
      if (currentMetadata.id) {
        const response = await apiClient.get<CompositionAsset>(
          `/compositions/${currentMetadata.id}`
        );
        return response.data;
      }
      return null;
    } catch {
      return null;
    }
  }, [getSerializableState, persistToApi]);

  // Set up auto-save on mount
  useEffect(() => {
    enableAutoSave(autoSave);
    setOnPersist(autoSave ? persistToApi : null);

    return () => {
      setOnPersist(null);
    };
  }, [autoSave, persistToApi, enableAutoSave, setOnPersist]);

  // Load composition if ID provided on mount
  useEffect(() => {
    if (compositionId) {
      load(compositionId);
    }
  }, [compositionId, load]);

  return {
    save,
    load,
    isLoading: false, // Could track this in store if needed
    isSaving: autoSaveState.isSaving,
    lastSavedAt: autoSaveState.lastSavedAt,
    saveError: autoSaveState.saveError,
    compositionId: metadata.id,
  };
}
