/**
 * useCompositionExecution - Hook for managing composition execution and per-node status visualization.
 *
 * This hook:
 * - Submits composition runs to the backend
 * - Polls for execution progress
 * - Updates node execution states on the canvas in real-time
 * - Handles cancellation and error states
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import {
  compositionRunsApi,
  type CompositionRun,
  type ProgressResponse,
  type NodeExecutionStatus,
  type ResumeRunResponse,
} from '@/api/compositionRuns';
import { type NodeExecutionState as CanvasNodeExecutionState } from '@/components/Builder/theme';

// Map backend node status to canvas execution state
function mapNodeStatusToCanvasState(
  status: NodeExecutionStatus,
  isCurrentNode: boolean
): CanvasNodeExecutionState {
  switch (status) {
    case 'pending':
      return isCurrentNode ? 'queued' : 'idle';
    case 'running':
      return 'running';
    case 'succeeded':
      return 'succeeded';
    case 'failed':
      return 'failed';
    case 'skipped':
      return 'skipped';
    default:
      return 'idle';
  }
}

export interface ExecutionState {
  /** Whether a run is currently active */
  isRunning: boolean;
  /** Current composition run (if any) */
  currentRun: CompositionRun | null;
  /** Error message if execution failed to start */
  error: string | null;
  /** Progress stats */
  progress: {
    total: number;
    pending: number;
    running: number;
    succeeded: number;
    failed: number;
    skipped: number;
  } | null;
}

export interface UseCompositionExecutionOptions {
  /** Callback to update a node's execution state */
  onNodeStateChange: (nodeId: string, state: CanvasNodeExecutionState) => void;
  /** Callback to reset all node states to idle */
  onResetStates: () => void;
  /** Poll interval in milliseconds */
  pollIntervalMs?: number;
  /** Callback when execution completes */
  onComplete?: (run: CompositionRun) => void;
  /** Callback on progress update */
  onProgress?: (progress: ProgressResponse) => void;
}

export interface UseCompositionExecutionReturn extends ExecutionState {
  /** Start a new composition run */
  startRun: (params: {
    compositionId: string;
    environmentId: string;
    inputs?: Record<string, unknown>;
    credentialIds?: string[];
  }) => Promise<CompositionRun | null>;
  /** Resume a failed composition run from a specific node */
  resumeRun: (
    runId: string,
    fromNodeId?: string
  ) => Promise<ResumeRunResponse | null>;
  /** Cancel the current run */
  cancelRun: (force?: boolean) => Promise<void>;
  /** Reset execution state */
  reset: () => void;
}

export function useCompositionExecution(
  options: UseCompositionExecutionOptions
): UseCompositionExecutionReturn {
  const {
    onNodeStateChange,
    onResetStates,
    pollIntervalMs = 1000,
    onComplete,
    onProgress,
  } = options;

  const [state, setState] = useState<ExecutionState>({
    isRunning: false,
    currentRun: null,
    error: null,
    progress: null,
  });

  // Track polling state
  const pollingRef = useRef<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      pollingRef.current = false;
      abortControllerRef.current?.abort();
    };
  }, []);

  // Update canvas node states based on progress
  const updateNodeStates = useCallback(
    (progress: ProgressResponse) => {
      const { nodeStates, currentNodeId } = progress;

      Object.entries(nodeStates).forEach(([nodeId, nodeState]) => {
        const canvasState = mapNodeStatusToCanvasState(
          nodeState.status,
          nodeId === currentNodeId
        );
        onNodeStateChange(nodeId, canvasState);
      });
    },
    [onNodeStateChange]
  );

  // Poll for execution progress
  const pollProgress = useCallback(
    async (runId: string) => {
      pollingRef.current = true;

      while (pollingRef.current) {
        try {
          const run = await compositionRunsApi.get(runId);
          const progress = await compositionRunsApi.getProgress(runId);

          // Update state
          setState((prev) => ({
            ...prev,
            currentRun: run,
            progress: {
              total: progress.total,
              pending: progress.pending,
              running: progress.running,
              succeeded: progress.succeeded,
              failed: progress.failed,
              skipped: progress.skipped,
            },
          }));

          // Update canvas node states
          updateNodeStates(progress);

          // Notify progress callback
          onProgress?.(progress);

          // Check if run is complete
          if (['succeeded', 'failed', 'cancelled'].includes(run.status)) {
            pollingRef.current = false;
            setState((prev) => ({
              ...prev,
              isRunning: false,
            }));
            onComplete?.(run);
            return;
          }

          // Wait before next poll
          await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
        } catch (error) {
          console.error('Error polling execution progress:', error);
          // Continue polling on transient errors
          await new Promise((resolve) => setTimeout(resolve, pollIntervalMs * 2));
        }
      }
    },
    [pollIntervalMs, updateNodeStates, onComplete, onProgress]
  );

  // Start a new composition run
  const startRun = useCallback(
    async (params: {
      compositionId: string;
      environmentId: string;
      inputs?: Record<string, unknown>;
      credentialIds?: string[];
    }): Promise<CompositionRun | null> => {
      // Reset state
      setState({
        isRunning: true,
        currentRun: null,
        error: null,
        progress: null,
      });

      // Reset canvas node states
      onResetStates();

      try {
        // Create the run
        const run = await compositionRunsApi.create({
          compositionId: params.compositionId,
          environmentId: params.environmentId,
          inputs: params.inputs,
          credentialIds: params.credentialIds,
          validate: true,
        });

        setState((prev) => ({
          ...prev,
          currentRun: run,
        }));

        // Initialize all nodes to queued state
        run.executionOrder.forEach((nodeId) => {
          onNodeStateChange(nodeId, 'queued');
        });

        // Start polling for progress
        pollProgress(run.id);

        return run;
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to start composition run';

        setState((prev) => ({
          ...prev,
          isRunning: false,
          error: errorMessage,
        }));

        return null;
      }
    },
    [onResetStates, onNodeStateChange, pollProgress]
  );

  // Cancel the current run
  const cancelRun = useCallback(async (force = false): Promise<void> => {
    const currentRun = state.currentRun;
    if (!currentRun) return;

    try {
      // Stop polling
      pollingRef.current = false;

      // Cancel the run
      const cancelledRun = await compositionRunsApi.cancel(currentRun.id, force);

      // Update state
      setState((prev) => ({
        ...prev,
        isRunning: false,
        currentRun: cancelledRun,
      }));

      // Mark running nodes as cancelled
      Object.entries(cancelledRun.nodeStates).forEach(([nodeId, nodeState]) => {
        if (nodeState.status === 'running' || nodeState.status === 'pending') {
          onNodeStateChange(nodeId, 'cancelled');
        }
      });
    } catch (error) {
      console.error('Error cancelling run:', error);
      throw error;
    }
  }, [state.currentRun, onNodeStateChange]);

  // Reset execution state
  const reset = useCallback(() => {
    pollingRef.current = false;
    abortControllerRef.current?.abort();

    setState({
      isRunning: false,
      currentRun: null,
      error: null,
      progress: null,
    });

    onResetStates();
  }, [onResetStates]);

  // Resume a failed composition run from a specific node
  const resumeRun = useCallback(
    async (
      runId: string,
      fromNodeId?: string
    ): Promise<ResumeRunResponse | null> => {
      // Reset state
      setState({
        isRunning: true,
        currentRun: null,
        error: null,
        progress: null,
      });

      // Reset canvas node states
      onResetStates();

      try {
        // Resume the run
        const resumeResponse = await compositionRunsApi.resume(runId, {
          fromNodeId,
        });

        setState((prev) => ({
          ...prev,
          currentRun: resumeResponse.run,
        }));

        // Initialize canvas states based on the new run's node states
        // Skipped nodes should show as skipped, others as queued
        resumeResponse.run.executionOrder.forEach((nodeId) => {
          const nodeState = resumeResponse.run.nodeStates[nodeId];
          if (nodeState?.status === 'skipped') {
            onNodeStateChange(nodeId, 'skipped');
          } else {
            onNodeStateChange(nodeId, 'queued');
          }
        });

        // Start polling for progress
        pollProgress(resumeResponse.run.id);

        return resumeResponse;
      } catch (error) {
        const errorMessage =
          error instanceof Error
            ? error.message
            : 'Failed to resume composition run';

        setState((prev) => ({
          ...prev,
          isRunning: false,
          error: errorMessage,
        }));

        return null;
      }
    },
    [onResetStates, onNodeStateChange, pollProgress]
  );

  return {
    ...state,
    startRun,
    resumeRun,
    cancelRun,
    reset,
  };
}
