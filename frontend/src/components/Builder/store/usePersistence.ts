/**
 * Persistence hook for composition state
 *
 * Connects the Zustand store to the mock API for:
 * - Loading compositions
 * - Auto-saving changes
 * - Manual save operations
 */
import { useEffect, useCallback } from 'react';
import { compositionsApi } from '@/api/assets';
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
        let composition: CompositionAsset;

        if (currentMetadata.id) {
          // Update existing composition via save (which handles versioning)
          const existing = await compositionsApi.get(currentMetadata.id);
          composition = await compositionsApi.save({
            ...existing,
            graph: {
              nodes: state.nodes as any,
              edges: state.edges,
              viewport: state.viewport,
            },
          });
        } else {
          // Create new composition
          composition = await compositionsApi.create({
            type: 'composition',
            name: currentMetadata.name || 'Untitled Composition',
            description: currentMetadata.description || '',
            tags: [],
            version: '1.0.0',
            sharing: 'private',
            graph: {
              nodes: state.nodes as any,
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
            id: composition.id,
            createdAt: composition.createdAt,
          });
        }

        setMetadata({ updatedAt: new Date().toISOString() });
        onSaveComplete?.(composition);
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
        const composition = await compositionsApi.get(id);

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
        return await compositionsApi.get(currentMetadata.id);
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
    isLoading: false,
    isSaving: autoSaveState.isSaving,
    lastSavedAt: autoSaveState.lastSavedAt,
    saveError: autoSaveState.saveError,
    compositionId: metadata.id,
  };
}
