import apiClient from './client';
import type { Run, CreateRunRequest } from '@/types';

export const runsApi = {
  /**
   * Create and start a new run
   * Note: This endpoint needs to be wired up in backend
   */
  create: async (data: CreateRunRequest): Promise<Run> => {
    const response = await apiClient.post<Run>('/runs', data);
    return response.data;
  },

  /**
   * Get a run by ID
   */
  get: async (id: string): Promise<Run> => {
    const response = await apiClient.get<Run>(`/runs/${id}`);
    return response.data;
  },

  /**
   * List runs for a program
   */
  listByProgram: async (programId: string): Promise<Run[]> => {
    try {
      const response = await apiClient.get<Run[]>('/runs', {
        params: { programId },
      });
      return response.data;
    } catch {
      console.warn('List runs endpoint not available, returning empty array');
      return [];
    }
  },

  /**
   * Cancel a running execution
   */
  cancel: async (id: string): Promise<Run> => {
    const response = await apiClient.post<Run>(`/runs/${id}/cancel`);
    return response.data;
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
};
