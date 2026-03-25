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
import {
  delay,
  generateId,
  now,
  shareLinks,
  programs,
  models,
  compositions,
  currentUserId,
} from './mock-store';

function findResourceName(resourceId: string): string {
  const p = programs.get(resourceId);
  if (p) return p.name;
  const m = models.get(resourceId);
  if (m) return m.name;
  const c = compositions.get(resourceId);
  if (c) return c.name;
  return 'Unknown';
}

export const sharingApi = {
  // =========================================================================
  // Share Link Operations
  // =========================================================================

  createShareLink: async (request: CreateShareLinkRequest): Promise<ShareLink> => {
    await delay(150);
    const id = generateId();
    const token = generateId();
    const link: ShareLink = {
      id,
      token,
      resourceId: request.resourceId,
      resourceType: request.resourceType,
      permission: request.permission || 'view',
      createdBy: currentUserId || 'unknown',
      createdAt: now(),
      expiresAt: request.expiresInHours
        ? new Date(Date.now() + request.expiresInHours * 3600000).toISOString()
        : undefined,
      label: request.label,
      accessCount: 0,
      isActive: true,
      shareUrl: `${window.location.origin}/share/${token}`,
    };
    shareLinks.set(id, link);
    return link;
  },

  listShareLinks: async (params?: {
    resourceId?: string;
    resourceType?: ResourceType;
    includeInactive?: boolean;
  }): Promise<ShareLinkListResponse> => {
    await delay();
    let links = Array.from(shareLinks.values());
    if (params?.resourceId) links = links.filter((l) => l.resourceId === params.resourceId);
    if (params?.resourceType) links = links.filter((l) => l.resourceType === params.resourceType);
    if (!params?.includeInactive) links = links.filter((l) => l.isActive);
    return { links, total: links.length };
  },

  getShareLink: async (linkId: string): Promise<ShareLink> => {
    await delay();
    const link = shareLinks.get(linkId);
    if (!link) throw { response: { status: 404, data: { detail: 'Share link not found' } } };
    return link;
  },

  deleteShareLink: async (linkId: string): Promise<void> => {
    await delay();
    shareLinks.delete(linkId);
  },

  deactivateShareLink: async (linkId: string): Promise<ShareLink> => {
    await delay();
    const link = shareLinks.get(linkId);
    if (!link) throw { response: { status: 404, data: { detail: 'Share link not found' } } };
    link.isActive = false;
    return link;
  },

  verifyShareLink: async (token: string): Promise<ShareLinkVerification> => {
    await delay();
    for (const link of shareLinks.values()) {
      if (link.token === token && link.isActive) {
        link.accessCount++;
        link.lastAccessedAt = now();
        return {
          valid: true,
          resourceId: link.resourceId,
          resourceType: link.resourceType,
          resourceName: findResourceName(link.resourceId),
          permission: link.permission,
        };
      }
    }
    return {
      valid: false,
      resourceId: '',
      resourceType: 'program',
      permission: 'view',
    };
  },

  // =========================================================================
  // User Sharing Operations
  // =========================================================================

  shareWithUser: async (
    request: ShareWithUserRequest
  ): Promise<{ success: boolean; userId: string; permission: Permission }> => {
    await delay();
    return {
      success: true,
      userId: request.userId,
      permission: request.permission || 'view',
    };
  },

  revokeUserAccess: async (
    _resourceType: ResourceType,
    _resourceId: string,
    _userId: string
  ): Promise<void> => {
    await delay();
  },

  listSharedUsers: async (
    _resourceType: ResourceType,
    _resourceId: string
  ): Promise<{ users: SharedUser[]; total: number }> => {
    await delay();
    return { users: [], total: 0 };
  },

  // =========================================================================
  // Shared With Me
  // =========================================================================

  getSharedWithMe: async (): Promise<SharedWithMeResponse> => {
    await delay();
    return { items: [], total: 0 };
  },
};

export default sharingApi;
