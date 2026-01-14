import apiClient from './client';
import type { ProgramAsset, CreateProgramRequest, BuildImageRequest, BuildResult } from '@/types';

export const programsApi = {
  /**
   * Create a new program
   */
  create: async (data: CreateProgramRequest): Promise<ProgramAsset> => {
    const response = await apiClient.post<{ asset: ProgramAsset }>('/assets', data);
    return response.data.asset;
  },

  /**
   * Get a program by ID
   */
  get: async (id: string): Promise<ProgramAsset> => {
    const response = await apiClient.get<{ asset: ProgramAsset }>(`/assets/${id}`);
    return response.data.asset;
  },

  /**
   * List all programs for the current user
   */
  list: async (): Promise<ProgramAsset[]> => {
    try {
      const response = await apiClient.get<{ assets: ProgramAsset[]; total: number }>('/assets', {
        params: { type: 'program' },
      });
      return response.data.assets;
    } catch {
      // Fallback on error
      console.warn('List programs endpoint not available, returning empty array');
      return [];
    }
  },

  /**
   * Delete a program
   * Note: This endpoint needs to be implemented (f6f.10)
   */
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/assets/${id}`);
  },

  /**
   * Build a container image for a program
   */
  build: async (id: string, options?: BuildImageRequest): Promise<BuildResult> => {
    const response = await apiClient.post<{ result: BuildResult }>(`/assets/${id}/build`, options);
    return response.data.result;
  },
};
