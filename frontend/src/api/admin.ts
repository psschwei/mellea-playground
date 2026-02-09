import apiClient, { setToken } from './client';
import type { User, UserRole, UserStatus, UserQuotas } from '@/types';

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

export const adminApi = {
  // Get user statistics
  getUserStats: async (): Promise<AdminUserStats> => {
    const response = await apiClient.get<AdminUserStats>('/admin/users/stats');
    return response.data;
  },

  // List all users with filtering and pagination
  listUsers: async (params: AdminUserListParams = {}): Promise<AdminUserListResponse> => {
    const response = await apiClient.get<AdminUserListResponse>('/admin/users', { params });
    return response.data;
  },

  // Get a single user by ID
  getUser: async (userId: string): Promise<AdminUser> => {
    const response = await apiClient.get<AdminUser>(`/admin/users/${userId}`);
    return response.data;
  },

  // Update user details
  updateUser: async (userId: string, data: UpdateUserRequest): Promise<AdminUser> => {
    const response = await apiClient.patch<AdminUser>(`/admin/users/${userId}`, data);
    return response.data;
  },

  // Suspend a user
  suspendUser: async (userId: string, reason?: string): Promise<AdminUser> => {
    const response = await apiClient.post<AdminUser>(`/admin/users/${userId}/suspend`, { reason });
    return response.data;
  },

  // Reactivate a suspended user
  activateUser: async (userId: string): Promise<AdminUser> => {
    const response = await apiClient.post<AdminUser>(`/admin/users/${userId}/activate`);
    return response.data;
  },

  // Delete a user (soft delete)
  deleteUser: async (userId: string): Promise<void> => {
    await apiClient.delete(`/admin/users/${userId}`);
  },

  // Get system-wide quota usage statistics
  getQuotaUsageStats: async (): Promise<QuotaUsageStats> => {
    const response = await apiClient.get<QuotaUsageStats>('/admin/quotas/usage');
    return response.data;
  },

  // Get quota details for a specific user
  getUserQuotaDetails: async (userId: string): Promise<{ user: { id: string; displayName: string; email: string; role: string }; quotas: Record<string, unknown> }> => {
    const response = await apiClient.get(`/admin/quotas/user/${userId}`);
    return response.data;
  },

  // Start impersonating a user
  startImpersonation: async (userId: string): Promise<ImpersonationTokenResponse> => {
    const response = await apiClient.post<ImpersonationTokenResponse>(`/admin/impersonate/${userId}`);
    // Set the impersonation token
    setToken(response.data.token);
    return response.data;
  },

  // Stop impersonating and return to admin session
  stopImpersonation: async (): Promise<StopImpersonationResponse> => {
    const response = await apiClient.post<StopImpersonationResponse>('/admin/stop-impersonate');
    // Set the admin's regular token
    setToken(response.data.token);
    return response.data;
  },

  // Get current impersonation status
  getImpersonationStatus: async (): Promise<ImpersonationStatus> => {
    const response = await apiClient.get<ImpersonationStatus>('/admin/impersonation-status');
    return response.data;
  },
};
