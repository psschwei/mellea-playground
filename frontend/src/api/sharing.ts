import apiClient from './client';
import type {
  CreateShareLinkRequest,
  Permission,
  ResourceType,
  ShareLink,
  ShareLinkListResponse,
  ShareLinkVerification,
  SharedUser,
  SharedWithMeResponse,
  ShareWithUserRequest,
} from '@/types';

/**
 * Sharing API for managing share links and user sharing
 */
export const sharingApi = {
  // =========================================================================
  // Share Link Operations
  // =========================================================================

  /**
   * Create a new share link for a resource
   */
  createShareLink: async (request: CreateShareLinkRequest): Promise<ShareLink> => {
    const response = await apiClient.post<ShareLink>('/sharing/links', request);
    return response.data;
  },

  /**
   * List share links for a resource or all links created by the current user
   */
  listShareLinks: async (params?: {
    resourceId?: string;
    resourceType?: ResourceType;
    includeInactive?: boolean;
  }): Promise<ShareLinkListResponse> => {
    const response = await apiClient.get<ShareLinkListResponse>('/sharing/links', {
      params: {
        resourceId: params?.resourceId,
        resourceType: params?.resourceType,
        includeInactive: params?.includeInactive,
      },
    });
    return response.data;
  },

  /**
   * Get a share link by ID
   */
  getShareLink: async (linkId: string): Promise<ShareLink> => {
    const response = await apiClient.get<ShareLink>(`/sharing/links/${linkId}`);
    return response.data;
  },

  /**
   * Delete a share link
   */
  deleteShareLink: async (linkId: string): Promise<void> => {
    await apiClient.delete(`/sharing/links/${linkId}`);
  },

  /**
   * Deactivate a share link (keeps history but prevents access)
   */
  deactivateShareLink: async (linkId: string): Promise<ShareLink> => {
    const response = await apiClient.post<ShareLink>(`/sharing/links/${linkId}/deactivate`);
    return response.data;
  },

  /**
   * Verify a share link token and get resource info
   */
  verifyShareLink: async (token: string): Promise<ShareLinkVerification> => {
    const response = await apiClient.get<ShareLinkVerification>(`/sharing/verify/${token}`);
    return response.data;
  },

  // =========================================================================
  // User Sharing Operations
  // =========================================================================

  /**
   * Share a resource with a specific user
   */
  shareWithUser: async (request: ShareWithUserRequest): Promise<{ success: boolean; userId: string; permission: Permission }> => {
    const response = await apiClient.post<{ success: boolean; userId: string; permission: Permission }>('/sharing/users', request);
    return response.data;
  },

  /**
   * Revoke a user's access to a resource
   */
  revokeUserAccess: async (resourceType: ResourceType, resourceId: string, userId: string): Promise<void> => {
    await apiClient.delete(`/sharing/users/${resourceType}/${resourceId}/${userId}`);
  },

  /**
   * List users a resource is shared with
   */
  listSharedUsers: async (resourceType: ResourceType, resourceId: string): Promise<{ users: SharedUser[]; total: number }> => {
    const response = await apiClient.get<{ users: SharedUser[]; total: number }>(`/sharing/users/${resourceType}/${resourceId}`);
    return response.data;
  },

  // =========================================================================
  // Shared With Me
  // =========================================================================

  /**
   * Get all resources shared with the current user
   */
  getSharedWithMe: async (): Promise<SharedWithMeResponse> => {
    const response = await apiClient.get<SharedWithMeResponse>('/sharing/shared-with-me');
    return response.data;
  },
};

export default sharingApi;
