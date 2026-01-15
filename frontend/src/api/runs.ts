import apiClient from './client';
import type { Run, CreateRunRequest } from '@/types';

interface RunResponse {
  run: Run;
}

interface RunsListResponse {
  runs: Run[];
  total: number;
}

interface BulkDeleteResponse {
  results: Record<string, boolean | string>;
  deletedCount: number;
  failedCount: number;
}

export const runsApi = {
  /**
   * Create and start a new run
   */
  create: async (data: CreateRunRequest): Promise<Run> => {
    const response = await apiClient.post<RunResponse>('/runs', data);
    return response.data.run;
  },

  /**
   * Get a run by ID
   */
  get: async (id: string): Promise<Run> => {
    const response = await apiClient.get<RunResponse>(`/runs/${id}`);
    return response.data.run;
  },

  /**
   * List runs for a program
   */
  listByProgram: async (programId: string): Promise<Run[]> => {
    try {
      const response = await apiClient.get<RunsListResponse>('/runs', {
        params: { programId },
      });
      return response.data.runs;
    } catch {
      console.warn('List runs endpoint not available, returning empty array');
      return [];
    }
  },

  /**
   * Cancel a running execution
   */
  cancel: async (id: string): Promise<Run> => {
    const response = await apiClient.post<RunResponse>(`/runs/${id}/cancel`);
    return response.data.run;
  },

  /**
   * Poll for run status updates
   * Returns when status changes or timeout reached
   */
  pollStatus: async (
    id: string,
    currentStatus: string,
    timeoutMs: number = 30000
  ): Promise<Run> => {
    const startTime = Date.now();
    const pollInterval = 1000; // 1 second

    while (Date.now() - startTime < timeoutMs) {
      const run = await runsApi.get(id);
      if (run.status !== currentStatus) {
        return run;
      }
      // Wait before next poll
      await new Promise((resolve) => setTimeout(resolve, pollInterval));
    }

    // Return latest state on timeout
    return runsApi.get(id);
  },

  /**
   * Download run logs as a text file
   */
  downloadLogs: async (id: string): Promise<void> => {
    const response = await apiClient.get(`/runs/${id}/logs/download`, {
      responseType: 'blob',
    });

    // Create download link and trigger download
    const blob = new Blob([response.data], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `run-${id}.log`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },

  /**
   * Delete a run by ID
   * Only works for runs in terminal states (succeeded, failed, cancelled)
   */
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/runs/${id}`);
  },

  /**
   * Delete multiple runs at once
   * Only runs in terminal states can be deleted
   * Returns results for each run
   */
  bulkDelete: async (runIds: string[]): Promise<BulkDeleteResponse> => {
    const response = await apiClient.post<BulkDeleteResponse>('/runs/bulk-delete', {
      runIds,
    });
    return response.data;
  },
};
