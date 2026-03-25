import type {
  ModelAsset,
  CreateModelRequest,
  TestModelRequest,
  TestModelResponse,
} from '@/types';
import { delay, generateId, now, models, currentUserId } from './mock-store';

export const modelsApi = {
  create: async (data: CreateModelRequest): Promise<ModelAsset> => {
    await delay(150);
    const id = generateId();
    const model: ModelAsset = {
      id,
      type: 'model',
      name: data.name,
      description: data.description || '',
      tags: data.tags || [],
      version: '1.0.0',
      owner: currentUserId || 'unknown',
      sharing: 'private',
      createdAt: now(),
      updatedAt: now(),
      provider: data.provider,
      modelId: data.modelId,
      endpoint: data.endpoint,
      credentialsRef: data.credentialsRef,
      defaultParams: data.defaultParams,
      capabilities: data.capabilities,
      accessControl: data.accessControl,
      scope: data.scope,
    };
    models.set(id, model);
    return model;
  },

  get: async (id: string): Promise<ModelAsset> => {
    await delay();
    const model = models.get(id);
    if (!model) throw { response: { status: 404, data: { detail: 'Model not found' } } };
    return model;
  },

  list: async (): Promise<ModelAsset[]> => {
    await delay();
    return Array.from(models.values());
  },

  delete: async (id: string): Promise<void> => {
    await delay();
    models.delete(id);
  },

  test: async (_id: string, _request?: TestModelRequest): Promise<TestModelResponse> => {
    await delay(800);
    return {
      success: true,
      response: 'Hello! This is a mock response from the model. Everything is working correctly.',
      latencyMs: 450,
    };
  },
};
