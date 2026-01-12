import apiClient, { setToken, clearToken } from './client';
import type { AuthConfig, LoginRequest, RegisterRequest, TokenResponse, User } from '@/types';

export const authApi = {
  // Get auth configuration
  getConfig: async (): Promise<AuthConfig> => {
    const response = await apiClient.get<AuthConfig>('/auth/config');
    return response.data;
  },

  // Login with email and password
  login: async (credentials: LoginRequest): Promise<TokenResponse> => {
    const response = await apiClient.post<TokenResponse>('/auth/login', credentials);
    setToken(response.data.token);
    return response.data;
  },

  // Register new user
  register: async (data: RegisterRequest): Promise<TokenResponse> => {
    const response = await apiClient.post<TokenResponse>('/auth/register', data);
    setToken(response.data.token);
    return response.data;
  },

  // Get current user
  me: async (): Promise<User> => {
    const response = await apiClient.get<User>('/auth/me');
    return response.data;
  },

  // Logout
  logout: async (): Promise<void> => {
    try {
      await apiClient.post('/auth/logout');
    } finally {
      clearToken();
    }
  },
};
