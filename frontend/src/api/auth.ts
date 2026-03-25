import { setToken, clearToken } from './client';
import type { AuthConfig, LoginRequest, RegisterRequest, TokenResponse, User } from '@/types';
import {
  delay,
  generateId,
  now,
  users,
  passwords,
  getUserByEmail,
  setCurrentUserId,
  getCurrentUser,
} from './mock-store';

const FAKE_TOKEN = 'mock-jwt-token-mellea';

export const authApi = {
  getConfig: async (): Promise<AuthConfig> => {
    await delay();
    return {
      mode: 'local',
      providers: ['local'],
      registrationEnabled: true,
      sessionDurationHours: 24,
    };
  },

  login: async (credentials: LoginRequest): Promise<TokenResponse> => {
    await delay(150);
    const user = getUserByEmail(credentials.email);
    if (!user) {
      throw { response: { status: 401, data: { detail: 'Invalid email or password' } } };
    }
    const storedPw = passwords.get(credentials.email);
    if (storedPw !== credentials.password) {
      throw { response: { status: 401, data: { detail: 'Invalid email or password' } } };
    }
    const token = `${FAKE_TOKEN}-${user.id}`;
    setToken(token);
    setCurrentUserId(user.id);
    user.lastLoginAt = now();
    return {
      token,
      expiresAt: new Date(Date.now() + 86400000).toISOString(),
      user,
    };
  },

  register: async (data: RegisterRequest): Promise<TokenResponse> => {
    await delay(200);
    if (getUserByEmail(data.email)) {
      throw { response: { status: 409, data: { detail: 'Email already registered' } } };
    }
    const id = generateId();
    const newUser = {
      id,
      email: data.email,
      username: data.username,
      displayName: data.displayName,
      role: 'developer' as const,
      status: 'active' as const,
      createdAt: now(),
      lastLoginAt: now(),
    };
    users.set(id, newUser);
    passwords.set(data.email, data.password);
    const token = `${FAKE_TOKEN}-${id}`;
    setToken(token);
    setCurrentUserId(id);
    return {
      token,
      expiresAt: new Date(Date.now() + 86400000).toISOString(),
      user: newUser,
    };
  },

  me: async (): Promise<User> => {
    await delay();
    const user = getCurrentUser();
    if (!user) {
      throw { response: { status: 401, data: { detail: 'Not authenticated' } } };
    }
    return user;
  },

  logout: async (): Promise<void> => {
    await delay();
    setCurrentUserId(null);
    clearToken();
  },
};
