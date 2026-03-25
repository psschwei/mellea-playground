import type { Asset, AssetType, SharingMode, CompositionAsset } from '@/types';
import {
  delay,
  generateId,
  now,
  programs,
  models,
  compositions,
  currentUserId,
} from './mock-store';

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

function getAllAssets(): Asset[] {
  return [
    ...Array.from(programs.values()),
    ...Array.from(models.values()),
    ...Array.from(compositions.values()),
  ];
}

function findAsset(id: string): Asset | undefined {
  return programs.get(id) ?? models.get(id) ?? compositions.get(id);
}

function deleteAsset(id: string): void {
  programs.delete(id);
  models.delete(id);
  compositions.delete(id);
}

function updateAssetInStore(id: string, updated: Asset): void {
  if (updated.type === 'program') programs.set(id, updated as any);
  else if (updated.type === 'model') models.set(id, updated as any);
  else if (updated.type === 'composition') compositions.set(id, updated as any);
}

export const assetsApi = {
  list: async (params?: ListAssetsParams): Promise<ListAssetsResponse> => {
    await delay();
    let assets = getAllAssets();
    if (params?.type) assets = assets.filter((a) => a.type === params.type);
    if (params?.owner) assets = assets.filter((a) => a.owner === params.owner);
    if (params?.sharing) assets = assets.filter((a) => a.sharing === params.sharing);
    if (params?.q) {
      const q = params.q.toLowerCase();
      assets = assets.filter(
        (a) =>
          a.name.toLowerCase().includes(q) || a.description.toLowerCase().includes(q)
      );
    }
    if (params?.tags && params.tags.length > 0) {
      assets = assets.filter((a) => params.tags!.some((t) => a.tags.includes(t)));
    }
    return { assets, total: assets.length };
  },

  get: async (id: string): Promise<Asset> => {
    await delay();
    const asset = findAsset(id);
    if (!asset) throw { response: { status: 404, data: { detail: 'Asset not found' } } };
    return asset;
  },

  delete: async (id: string): Promise<void> => {
    await delay();
    deleteAsset(id);
  },

  update: async (id: string, data: UpdateAssetRequest): Promise<Asset> => {
    await delay();
    const asset = findAsset(id);
    if (!asset) throw { response: { status: 404, data: { detail: 'Asset not found' } } };
    if (data.name !== undefined) asset.name = data.name;
    if (data.description !== undefined) asset.description = data.description;
    if (data.tags !== undefined) asset.tags = data.tags;
    if (data.version !== undefined) asset.version = data.version;
    asset.updatedAt = now();
    updateAssetInStore(id, asset);
    return asset;
  },

  getTags: async (): Promise<string[]> => {
    await delay();
    const tagSet = new Set<string>();
    for (const a of getAllAssets()) {
      a.tags.forEach((t) => tagSet.add(t));
    }
    return Array.from(tagSet).sort();
  },

  create: async (data: CreateAssetRequest): Promise<Asset> => {
    await delay(150);
    const id = generateId();
    const asset = {
      ...data,
      id,
      owner: currentUserId || 'unknown',
      createdAt: now(),
      updatedAt: now(),
    } as Asset;
    updateAssetInStore(id, asset);
    return asset;
  },

  replace: async (id: string, data: Asset): Promise<Asset> => {
    await delay();
    data.updatedAt = now();
    updateAssetInStore(id, data);
    return data;
  },
};

export const compositionsApi = {
  list: async (): Promise<CompositionAsset[]> => {
    await delay();
    return Array.from(compositions.values());
  },

  get: async (id: string): Promise<CompositionAsset> => {
    await delay();
    const comp = compositions.get(id);
    if (!comp) throw { response: { status: 404, data: { detail: 'Composition not found' } } };
    return comp;
  },

  create: async (
    data: Omit<CompositionAsset, 'id' | 'createdAt' | 'updatedAt' | 'owner'>
  ): Promise<CompositionAsset> => {
    await delay(150);
    const id = generateId();
    const comp: CompositionAsset = {
      ...data,
      id,
      owner: currentUserId || 'unknown',
      createdAt: now(),
      updatedAt: now(),
    };
    compositions.set(id, comp);
    return comp;
  },

  save: async (composition: CompositionAsset): Promise<CompositionAsset> => {
    await delay(150);
    if (composition.id && compositions.has(composition.id)) {
      const versionParts = composition.version.split('.');
      const patch = parseInt(versionParts[2] || '0', 10) + 1;
      composition.version = `${versionParts[0]}.${versionParts[1]}.${patch}`;
      composition.updatedAt = now();
      compositions.set(composition.id, composition);
      return composition;
    } else {
      const { id: _id, createdAt: _c, updatedAt: _u, owner: _o, ...createData } = composition;
      return compositionsApi.create(createData);
    }
  },

  delete: async (id: string): Promise<void> => {
    await delay();
    compositions.delete(id);
  },
};
