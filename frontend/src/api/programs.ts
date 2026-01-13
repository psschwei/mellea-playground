import apiClient from './client';
import type { ProgramAsset, CreateProgramRequest } from '@/types';

export const programsApi = {
  /**
   * Create a new program
   */
  create: async (data: CreateProgramRequest): Promise<ProgramAsset> => {
    const response = await apiClient.post<ProgramAsset>('/assets', data);
    return response.data;
  },

  /**
   * Get a program by ID
   */
  get: async (id: string): Promise<ProgramAsset> => {
    const response = await apiClient.get<ProgramAsset>(`/assets/${id}`);
    return response.data;
  },

  /**
   * List all programs for the current user
   * Note: This endpoint needs to be implemented (f6f.7)
   * For now, returns empty array as fallback
   */
  list: async (): Promise<ProgramAsset[]> => {
    try {
      const response = await apiClient.get<ProgramAsset[]>('/assets', {
        params: { type: 'program' },
      });
      return response.data;
    } catch {
      // Fallback until list endpoint is implemented
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
};
