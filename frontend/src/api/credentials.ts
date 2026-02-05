import apiClient from './client';
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

interface ListCredentialsParams {
  type?: CredentialType;
  provider?: ModelProvider | string;
}

export const credentialsApi = {
  /**
   * Create a new credential
   */
  create: async (data: CreateCredentialRequest): Promise<Credential> => {
    const response = await apiClient.post<Credential>('/credentials', data);
    return response.data;
  },

  /**
   * Get a credential by ID (metadata only, no secrets)
   */
  get: async (id: string): Promise<Credential> => {
    const response = await apiClient.get<Credential>(`/credentials/${id}`);
    return response.data;
  },

  /**
   * List credentials for the current user
   */
  list: async (params?: ListCredentialsParams): Promise<Credential[]> => {
    const response = await apiClient.get<Credential[]>('/credentials', { params });
    return response.data;
  },

  /**
   * Update a credential
   */
  update: async (id: string, data: UpdateCredentialRequest): Promise<Credential> => {
    const response = await apiClient.put<Credential>(`/credentials/${id}`, data);
    return response.data;
  },

  /**
   * Delete a credential
   */
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/credentials/${id}`);
  },

  /**
   * Validate a credential (check if it exists and is not expired)
   */
  validate: async (id: string): Promise<{ valid: boolean }> => {
    const response = await apiClient.post<{ valid: boolean }>(`/credentials/${id}/validate`);
    return response.data;
  },

  /**
   * List credentials accessible to the current user (owned or shared)
   */
  listAccessible: async (params?: ListCredentialsParams): Promise<Credential[]> => {
    const response = await apiClient.get<Credential[]>('/credentials/accessible', { params });
    return response.data;
  },

  /**
   * Share a credential with another user
   */
  share: async (id: string, data: ShareCredentialRequest): Promise<ShareCredentialResponse> => {
    const response = await apiClient.post<ShareCredentialResponse>(
      `/credentials/${id}/share`,
      data,
    );
    return response.data;
  },

  /**
   * List users who have access to a credential
   */
  listShares: async (id: string): Promise<CredentialSharedAccess[]> => {
    const response = await apiClient.get<CredentialSharedAccess[]>(
      `/credentials/${id}/shared-with`,
    );
    return response.data;
  },

  /**
   * Revoke a user's access to a credential
   */
  revokeShare: async (credentialId: string, userId: string): Promise<void> => {
    await apiClient.delete(`/credentials/${credentialId}/shared-with/${userId}`);
  },
};
