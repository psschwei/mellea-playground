// User types
export type UserRole = 'end_user' | 'developer' | 'admin';
export type UserStatus = 'active' | 'suspended' | 'pending';

export interface User {
  id: string;
  email: string;
  username?: string;
  displayName: string;
  avatarUrl?: string;
  role: UserRole;
  status: UserStatus;
}

export interface UserQuotas {
  maxConcurrentRuns: number;
  maxStorageMB: number;
  maxCpuHoursPerMonth: number;
  maxRunsPerDay: number;
}

// Auth types
export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  displayName: string;
  username?: string;
}

export interface TokenResponse {
  token: string;
  expiresAt: string;
  user: User;
}

export interface AuthConfig {
  mode: string;
  providers: string[];
  registrationEnabled: boolean;
  sessionDurationHours: number;
}

// Asset types
export type SharingMode = 'private' | 'shared' | 'public';
export type RunStatus = 'never_run' | 'succeeded' | 'failed';

export interface AssetMetadata {
  id: string;
  name: string;
  description: string;
  tags: string[];
  version: string;
  owner: string;
  sharing: SharingMode;
  createdAt: string;
  updatedAt: string;
  lastRunStatus?: RunStatus;
  lastRunAt?: string;
}

// API response types
export interface ApiError {
  detail: string;
}
