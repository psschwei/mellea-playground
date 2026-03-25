import { setToken } from './client';
import type { User, UserRole, UserStatus, UserQuotas } from '@/types';
import {
  delay,
  users,
  currentUserId,
  setCurrentUserId,
  setImpersonatingFromId,
  impersonatingFromId,
  runs,
  programs,
} from './mock-store';

export interface AdminUserStats {
  totalUsers: number;
  activeUsers: number;
  suspendedUsers: number;
  pendingUsers: number;
  usersByRole: {
    admin: number;
    developer: number;
    end_user: number;
  };
}

export interface QuotaUserUsage {
  userId: string;
  displayName: string;
  email: string;
  cpuHoursUsed?: number;
  cpuHoursLimit?: number;
  runsToday?: number;
  runsLimit?: number;
  percentUsed: number;
}

export interface QuotaUsageStats {
  totalUsers: number;
  usersAtLimit: number;
  totalCpuHoursUsed: number;
  totalRunsToday: number;
  topUsersByCpu: QuotaUserUsage[];
  topUsersByRuns: QuotaUserUsage[];
}

export interface AdminUserListParams {
  page?: number;
  limit?: number;
  search?: string;
  role?: UserRole;
  status?: UserStatus;
  sortBy?: 'createdAt' | 'email' | 'displayName' | 'lastLoginAt';
  sortOrder?: 'asc' | 'desc';
}

export interface AdminUser extends User {
  createdAt: string;
  lastLoginAt?: string;
  quotas?: UserQuotas;
  usageStats?: {
    totalRuns: number;
    totalPrograms: number;
    storageUsedMB: number;
  };
}

export interface AdminUserListResponse {
  users: AdminUser[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

export interface UpdateUserRequest {
  displayName?: string;
  role?: UserRole;
  status?: UserStatus;
  quotas?: Partial<UserQuotas>;
}

export interface ImpersonationTokenResponse {
  token: string;
  expiresAt: string;
  targetUserId: string;
  targetUserEmail: string;
  targetUserName: string;
  targetUserRole: string;
  impersonatorId: string;
  impersonatorEmail: string;
}

export interface StopImpersonationResponse {
  token: string;
  expiresAt: string;
  message: string;
}

export interface ImpersonationStatus {
  isImpersonating: boolean;
  impersonatorId?: string;
  impersonatorEmail?: string;
  targetUserId?: string;
  targetUserEmail?: string;
  targetUserName?: string;
  targetUserRole?: string;
}

function toAdminUser(u: any): AdminUser {
  const userRuns = Array.from(runs.values()).filter((r) => r.ownerId === u.id);
  const userProgs = Array.from(programs.values()).filter((p) => p.owner === u.id);
  return {
    ...u,
    usageStats: {
      totalRuns: userRuns.length,
      totalPrograms: userProgs.length,
      storageUsedMB: Math.floor(Math.random() * 500),
    },
  };
}

export const adminApi = {
  getUserStats: async (): Promise<AdminUserStats> => {
    await delay();
    const all = Array.from(users.values());
    return {
      totalUsers: all.length,
      activeUsers: all.filter((u) => u.status === 'active').length,
      suspendedUsers: all.filter((u) => u.status === 'suspended').length,
      pendingUsers: all.filter((u) => u.status === 'pending').length,
      usersByRole: {
        admin: all.filter((u) => u.role === 'admin').length,
        developer: all.filter((u) => u.role === 'developer').length,
        end_user: all.filter((u) => u.role === 'end_user').length,
      },
    };
  },

  listUsers: async (params: AdminUserListParams = {}): Promise<AdminUserListResponse> => {
    await delay();
    let all = Array.from(users.values());
    if (params.search) {
      const q = params.search.toLowerCase();
      all = all.filter(
        (u) =>
          u.email.toLowerCase().includes(q) ||
          u.displayName.toLowerCase().includes(q)
      );
    }
    if (params.role) all = all.filter((u) => u.role === params.role);
    if (params.status) all = all.filter((u) => u.status === params.status);

    const page = params.page || 1;
    const limit = params.limit || 20;
    const total = all.length;
    const totalPages = Math.ceil(total / limit);
    const start = (page - 1) * limit;
    const paged = all.slice(start, start + limit);

    return {
      users: paged.map(toAdminUser),
      total,
      page,
      limit,
      totalPages,
    };
  },

  getUser: async (userId: string): Promise<AdminUser> => {
    await delay();
    const user = users.get(userId);
    if (!user) throw { response: { status: 404, data: { detail: 'User not found' } } };
    return toAdminUser(user);
  },

  updateUser: async (userId: string, data: UpdateUserRequest): Promise<AdminUser> => {
    await delay();
    const user = users.get(userId);
    if (!user) throw { response: { status: 404, data: { detail: 'User not found' } } };
    if (data.displayName !== undefined) user.displayName = data.displayName;
    if (data.role !== undefined) user.role = data.role;
    if (data.status !== undefined) user.status = data.status;
    if (data.quotas) user.quotas = { ...user.quotas!, ...data.quotas };
    return toAdminUser(user);
  },

  suspendUser: async (userId: string, _reason?: string): Promise<AdminUser> => {
    await delay();
    const user = users.get(userId);
    if (!user) throw { response: { status: 404, data: { detail: 'User not found' } } };
    user.status = 'suspended';
    return toAdminUser(user);
  },

  activateUser: async (userId: string): Promise<AdminUser> => {
    await delay();
    const user = users.get(userId);
    if (!user) throw { response: { status: 404, data: { detail: 'User not found' } } };
    user.status = 'active';
    return toAdminUser(user);
  },

  deleteUser: async (userId: string): Promise<void> => {
    await delay();
    users.delete(userId);
  },

  getQuotaUsageStats: async (): Promise<QuotaUsageStats> => {
    await delay();
    const all = Array.from(users.values());
    return {
      totalUsers: all.length,
      usersAtLimit: 0,
      totalCpuHoursUsed: 42.5,
      totalRunsToday: 12,
      topUsersByCpu: all.slice(0, 3).map((u) => ({
        userId: u.id,
        displayName: u.displayName,
        email: u.email,
        cpuHoursUsed: Math.random() * 50,
        cpuHoursLimit: u.quotas?.maxCpuHoursPerMonth || 100,
        percentUsed: Math.random() * 60,
      })),
      topUsersByRuns: all.slice(0, 3).map((u) => ({
        userId: u.id,
        displayName: u.displayName,
        email: u.email,
        runsToday: Math.floor(Math.random() * 20),
        runsLimit: u.quotas?.maxRunsPerDay || 50,
        percentUsed: Math.random() * 40,
      })),
    };
  },

  getUserQuotaDetails: async (
    userId: string
  ): Promise<{
    user: { id: string; displayName: string; email: string; role: string };
    quotas: Record<string, unknown>;
  }> => {
    await delay();
    const user = users.get(userId);
    if (!user) throw { response: { status: 404, data: { detail: 'User not found' } } };
    return {
      user: { id: user.id, displayName: user.displayName, email: user.email, role: user.role },
      quotas: user.quotas as any || {},
    };
  },

  startImpersonation: async (userId: string): Promise<ImpersonationTokenResponse> => {
    await delay();
    const target = users.get(userId);
    if (!target) throw { response: { status: 404, data: { detail: 'User not found' } } };
    const admin = users.get(currentUserId || '');
    if (!admin) throw { response: { status: 401, data: { detail: 'Not authenticated' } } };

    setImpersonatingFromId(currentUserId);
    setCurrentUserId(userId);
    const token = `mock-impersonation-token-${userId}`;
    setToken(token);

    return {
      token,
      expiresAt: new Date(Date.now() + 3600000).toISOString(),
      targetUserId: target.id,
      targetUserEmail: target.email,
      targetUserName: target.displayName,
      targetUserRole: target.role,
      impersonatorId: admin.id,
      impersonatorEmail: admin.email,
    };
  },

  stopImpersonation: async (): Promise<StopImpersonationResponse> => {
    await delay();
    if (!impersonatingFromId) {
      throw { response: { status: 400, data: { detail: 'Not impersonating anyone' } } };
    }
    setCurrentUserId(impersonatingFromId);
    setImpersonatingFromId(null);
    const token = `mock-jwt-token-mellea-${currentUserId}`;
    setToken(token);

    return {
      token,
      expiresAt: new Date(Date.now() + 86400000).toISOString(),
      message: 'Impersonation stopped',
    };
  },

  getImpersonationStatus: async (): Promise<ImpersonationStatus> => {
    await delay();
    if (!impersonatingFromId) {
      return { isImpersonating: false };
    }
    const impersonator = users.get(impersonatingFromId);
    const target = users.get(currentUserId || '');
    return {
      isImpersonating: true,
      impersonatorId: impersonatingFromId,
      impersonatorEmail: impersonator?.email,
      targetUserId: currentUserId || undefined,
      targetUserEmail: target?.email,
      targetUserName: target?.displayName,
      targetUserRole: target?.role,
    };
  },
};
