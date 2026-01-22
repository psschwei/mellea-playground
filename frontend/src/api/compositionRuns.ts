/**
 * API client for composition runs - manages composition workflow execution.
 */
import apiClient from './client';
import type { RunExecutionStatus } from '@/types';

// =============================================================================
// Types
// =============================================================================

/** Status for individual nodes during execution */
export type NodeExecutionStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'skipped';

/** Execution state for a single node */
export interface NodeExecutionState {
  nodeId: string;
  status: NodeExecutionStatus;
  startedAt: string | null;
  completedAt: string | null;
  output: unknown | null;
  errorMessage: string | null;
  logs: string[];
}

/** Composition run model */
export interface CompositionRun {
  id: string;
  ownerId: string;
  environmentId: string;
  compositionId: string;
  status: RunExecutionStatus;
  jobName: string | null;
  exitCode: number | null;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  output: string | null;
  executionOrder: string[];
  nodeStates: Record<string, NodeExecutionState>;
  generatedCode: string | null;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  currentNodeId: string | null;
  credentialIds: string[];
}

/** Request to create a new composition run */
export interface CreateCompositionRunRequest {
  compositionId: string;
  environmentId: string;
  inputs?: Record<string, unknown>;
  credentialIds?: string[];
  validate?: boolean;
}

/** Progress response from the API */
export interface ProgressResponse {
  total: number;
  pending: number;
  running: number;
  succeeded: number;
  failed: number;
  skipped: number;
  currentNodeId: string | null;
  nodeStates: Record<string, NodeExecutionState>;
}

/** Validation result response */
export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  programIds: string[];
  modelIds: string[];
}

/** Generated code response */
export interface GeneratedCodeResponse {
  code: string;
  executionOrder: string[];
  warnings: string[];
}

// =============================================================================
// API Response Wrappers
// =============================================================================

interface CompositionRunResponse {
  run: CompositionRun;
}

interface CompositionRunsListResponse {
  runs: CompositionRun[];
  total: number;
}

// =============================================================================
// API Client
// =============================================================================

export const compositionRunsApi = {
  /**
   * Create and submit a new composition run.
   * Validates the composition, generates code, and submits a K8s job.
   */
  create: async (data: CreateCompositionRunRequest): Promise<CompositionRun> => {
    const response = await apiClient.post<CompositionRunResponse>(
      '/composition-runs',
      data
    );
    return response.data.run;
  },

  /**
   * Get a composition run by ID.
   */
  get: async (id: string): Promise<CompositionRun> => {
    const response = await apiClient.get<CompositionRunResponse>(
      `/composition-runs/${id}`
    );
    return response.data.run;
  },

  /**
   * List composition runs with optional filters.
   */
  list: async (params?: {
    compositionId?: string;
    status?: RunExecutionStatus;
  }): Promise<CompositionRun[]> => {
    const response = await apiClient.get<CompositionRunsListResponse>(
      '/composition-runs',
      { params }
    );
    return response.data.runs;
  },

  /**
   * Get execution progress for a composition run.
   * Returns node states and current execution status.
   */
  getProgress: async (id: string): Promise<ProgressResponse> => {
    const response = await apiClient.get<ProgressResponse>(
      `/composition-runs/${id}/progress`
    );
    return response.data;
  },

  /**
   * Cancel a running composition.
   */
  cancel: async (id: string, force = false): Promise<CompositionRun> => {
    const response = await apiClient.post<CompositionRunResponse>(
      `/composition-runs/${id}/cancel`,
      null,
      { params: { force } }
    );
    return response.data.run;
  },

  /**
   * Manually sync a composition run's status with its K8s job.
   */
  sync: async (id: string): Promise<CompositionRun> => {
    const response = await apiClient.post<CompositionRunResponse>(
      `/composition-runs/${id}/sync`
    );
    return response.data.run;
  },

  /**
   * Validate a composition for execution.
   */
  validate: async (compositionId: string): Promise<ValidationResult> => {
    const response = await apiClient.post<ValidationResult>(
      `/composition-runs/validate/${compositionId}`
    );
    return response.data;
  },

  /**
   * Generate executable Python code from a composition.
   */
  generateCode: async (compositionId: string): Promise<GeneratedCodeResponse> => {
    const response = await apiClient.post<GeneratedCodeResponse>(
      `/composition-runs/generate/${compositionId}`
    );
    return response.data;
  },

  /**
   * Get the generated Python code for a composition run.
   */
  getCode: async (id: string): Promise<string> => {
    const response = await apiClient.get<string>(
      `/composition-runs/${id}/code`,
      { responseType: 'text' as const }
    );
    return response.data;
  },

  /**
   * Download composition run logs as a text file.
   */
  downloadLogs: async (id: string): Promise<void> => {
    const response = await apiClient.get(`/composition-runs/${id}/logs/download`, {
      responseType: 'blob',
    });

    const blob = new Blob([response.data], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `composition-run-${id}.log`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },

  /**
   * Poll for composition run progress updates.
   * Returns when the run reaches a terminal state or timeout.
   */
  pollProgress: async (
    id: string,
    onProgress: (progress: ProgressResponse) => void,
    options?: {
      intervalMs?: number;
      timeoutMs?: number;
    }
  ): Promise<CompositionRun> => {
    const { intervalMs = 1000, timeoutMs = 300000 } = options || {};
    const startTime = Date.now();

    while (Date.now() - startTime < timeoutMs) {
      const run = await compositionRunsApi.get(id);
      const progress = await compositionRunsApi.getProgress(id);

      onProgress(progress);

      // Check if run is in terminal state
      if (['succeeded', 'failed', 'cancelled'].includes(run.status)) {
        return run;
      }

      // Wait before next poll
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }

    // Return latest state on timeout
    return compositionRunsApi.get(id);
  },
};
