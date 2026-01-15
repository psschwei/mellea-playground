import apiClient from './client';
import type { Asset, AssetType, SharingMode } from '@/types';

export interface ListAssetsParams {
  type?: AssetType;
  owner?: string;
  tags?: string[];
  q?: string;
  sharing?: SharingMode;
}

export interface ListAssetsResponse {
  assets: Asset[];
  total: number;
}

export interface UpdateAssetRequest {
  name?: string;
  description?: string;
  tags?: string[];
  version?: string;
}

export const assetsApi = {
  /**
   * List/search assets with optional filters
   */
  list: async (params?: ListAssetsParams): Promise<ListAssetsResponse> => {
    const response = await apiClient.get<ListAssetsResponse>('/assets', {
      params: {
        type: params?.type,
        owner: params?.owner,
        tags: params?.tags?.join(','),
        q: params?.q,
        sharing: params?.sharing,
      },
    });
    return response.data;
  },

  /**
   * Get a single asset by ID
   */
  get: async (id: string): Promise<Asset> => {
    const response = await apiClient.get<{ asset: Asset }>(`/assets/${id}`);
    return response.data.asset;
  },

  /**
   * Delete an asset by ID
   */
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/assets/${id}`);
  },

  /**
   * Update an asset's metadata
   */
  update: async (id: string, data: UpdateAssetRequest): Promise<Asset> => {
    const response = await apiClient.put<{ asset: Asset }>(`/assets/${id}`, data);
    return response.data.asset;
  },

  /**
   * Get all unique tags used across assets
   */
  getTags: async (): Promise<string[]> => {
    try {
      const response = await apiClient.get<{ tags: string[] }>('/assets/tags');
      return response.data.tags;
    } catch {
      // Fallback if endpoint doesn't exist
      return [];
    }
  },
};
