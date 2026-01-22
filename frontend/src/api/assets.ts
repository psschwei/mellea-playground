import apiClient from './client';
import type { Asset, AssetType, SharingMode, CompositionAsset } from '@/types';

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

export type CreateAssetRequest = Omit<Asset, 'id' | 'createdAt' | 'updatedAt' | 'owner'>;

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

  /**
   * Create a new asset
   */
  create: async (data: CreateAssetRequest): Promise<Asset> => {
    const response = await apiClient.post<{ asset: Asset }>('/assets', data);
    return response.data.asset;
  },

  /**
   * Full update of an asset (replaces entire asset data)
   */
  replace: async (id: string, data: Asset): Promise<Asset> => {
    const response = await apiClient.put<{ asset: Asset }>(`/assets/${id}`, data);
    return response.data.asset;
  },
};

/**
 * Composition-specific API helpers
 */
export const compositionsApi = {
  /**
   * List all compositions
   */
  list: async (): Promise<CompositionAsset[]> => {
    const response = await assetsApi.list({ type: 'composition' });
    return response.assets.filter((a): a is CompositionAsset => a.type === 'composition');
  },

  /**
   * Get a composition by ID
   */
  get: async (id: string): Promise<CompositionAsset> => {
    const asset = await assetsApi.get(id);
    if (asset.type !== 'composition') {
      throw new Error(`Asset ${id} is not a composition`);
    }
    return asset as CompositionAsset;
  },

  /**
   * Create a new composition
   */
  create: async (data: Omit<CompositionAsset, 'id' | 'createdAt' | 'updatedAt' | 'owner'>): Promise<CompositionAsset> => {
    const asset = await assetsApi.create(data);
    return asset as CompositionAsset;
  },

  /**
   * Save a composition (creates new or updates existing)
   * Auto-increments patch version on update
   */
  save: async (composition: CompositionAsset): Promise<CompositionAsset> => {
    if (composition.id) {
      // Update existing - increment patch version
      const versionParts = composition.version.split('.');
      const patch = parseInt(versionParts[2] || '0', 10) + 1;
      const newVersion = `${versionParts[0]}.${versionParts[1]}.${patch}`;

      const updated = {
        ...composition,
        version: newVersion,
        updatedAt: new Date().toISOString(),
      };

      return await assetsApi.replace(composition.id, updated) as CompositionAsset;
    } else {
      // Create new
      const { id: _id, createdAt: _createdAt, updatedAt: _updatedAt, owner: _owner, ...createData } = composition;
      return await compositionsApi.create(createData);
    }
  },

  /**
   * Delete a composition
   */
  delete: async (id: string): Promise<void> => {
    await assetsApi.delete(id);
  },
};
