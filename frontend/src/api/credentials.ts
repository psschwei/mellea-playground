import type {
  Credential,
  CredentialSharedAccess,
  CreateCredentialRequest,
  UpdateCredentialRequest,
  ShareCredentialRequest,
  ShareCredentialResponse,
  CredentialType,
  ModelProvider,
} from '@/types';
import { delay, generateId, now, credentials, currentUserId } from './mock-store';

interface ListCredentialsParams {
  type?: CredentialType;
  provider?: ModelProvider | string;
}

function filterCredentials(params?: ListCredentialsParams): Credential[] {
  let result = Array.from(credentials.values());
  if (params?.type) result = result.filter((c) => c.type === params.type);
  if (params?.provider) result = result.filter((c) => c.provider === params.provider);
  return result;
}

export const credentialsApi = {
  create: async (data: CreateCredentialRequest): Promise<Credential> => {
    await delay(150);
    const id = generateId();
    const cred: Credential = {
      id,
      name: data.name,
      description: data.description || '',
      type: data.type,
      provider: data.provider,
      ownerId: currentUserId || 'unknown',
      tags: data.tags || [],
      createdAt: now(),
      updatedAt: now(),
      expiresAt: data.expiresAt,
      isExpired: false,
    };
    credentials.set(id, cred);
    return cred;
  },

  get: async (id: string): Promise<Credential> => {
    await delay();
    const cred = credentials.get(id);
    if (!cred) throw { response: { status: 404, data: { detail: 'Credential not found' } } };
    return cred;
  },

  list: async (params?: ListCredentialsParams): Promise<Credential[]> => {
    await delay();
    return filterCredentials(params);
  },

  update: async (id: string, data: UpdateCredentialRequest): Promise<Credential> => {
    await delay();
    const cred = credentials.get(id);
    if (!cred) throw { response: { status: 404, data: { detail: 'Credential not found' } } };
    if (data.name !== undefined) cred.name = data.name;
    if (data.description !== undefined) cred.description = data.description;
    if (data.tags !== undefined) cred.tags = data.tags;
    if (data.expiresAt !== undefined) cred.expiresAt = data.expiresAt;
    cred.updatedAt = now();
    return cred;
  },

  delete: async (id: string): Promise<void> => {
    await delay();
    credentials.delete(id);
  },

  validate: async (_id: string): Promise<{ valid: boolean }> => {
    await delay(200);
    return { valid: true };
  },

  listAccessible: async (params?: ListCredentialsParams): Promise<Credential[]> => {
    await delay();
    return filterCredentials(params);
  },

  share: async (id: string, data: ShareCredentialRequest): Promise<ShareCredentialResponse> => {
    await delay();
    const cred = credentials.get(id);
    if (!cred) throw { response: { status: 404, data: { detail: 'Credential not found' } } };
    const access: CredentialSharedAccess = {
      type: 'user',
      id: data.userId,
      permission: data.permission,
      sharedAt: now(),
      sharedBy: currentUserId || 'unknown',
    };
    if (!cred.sharedWith) cred.sharedWith = [];
    cred.sharedWith.push(access);
    return {
      credentialId: id,
      userId: data.userId,
      permission: data.permission,
      sharedAt: access.sharedAt,
      sharedBy: access.sharedBy,
    };
  },

  listShares: async (id: string): Promise<CredentialSharedAccess[]> => {
    await delay();
    const cred = credentials.get(id);
    if (!cred) throw { response: { status: 404, data: { detail: 'Credential not found' } } };
    return cred.sharedWith || [];
  },

  revokeShare: async (credentialId: string, userId: string): Promise<void> => {
    await delay();
    const cred = credentials.get(credentialId);
    if (!cred) throw { response: { status: 404, data: { detail: 'Credential not found' } } };
    cred.sharedWith = (cred.sharedWith || []).filter((s) => s.id !== userId);
  },
};
