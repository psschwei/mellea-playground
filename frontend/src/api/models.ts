import apiClient from './client';
import type {
  ModelAsset,
  CreateModelRequest,
  TestModelRequest,
  TestModelResponse,
} from '@/types';

interface AssetResponse {
  asset: ModelAsset;
}

export const modelsApi = {
  /**
   * Create a new model configuration
   */
  create: async (data: CreateModelRequest): Promise<ModelAsset> => {
    const response = await apiClient.post<AssetResponse>('/assets', data);
    return response.data.asset;
  },

  /**
   * Get a model by ID
   */
  get: async (id: string): Promise<ModelAsset> => {
    const response = await apiClient.get<AssetResponse>(`/assets/${id}`);
    return response.data.asset;
  },

  /**
   * List all model assets
   */
  list: async (): Promise<ModelAsset[]> => {
    const response = await apiClient.get<{ assets: ModelAsset[]; total: number }>(
      '/assets',
      { params: { type: 'model' } }
    );
    return response.data.assets;
  },

  /**
   * Delete a model
   */
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/assets/${id}`);
  },

  /**
   * Test model connectivity and configuration
   */
  test: async (id: string, request?: TestModelRequest): Promise<TestModelResponse> => {
    const response = await apiClient.post<TestModelResponse>(
      `/assets/${id}/test`,
      request || {}
    );
    return response.data;
  },
};
