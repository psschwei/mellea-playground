/**
 * Token management utilities.
 * The axios HTTP client has been removed — all API modules use the in-memory mock store.
 */

const TOKEN_KEY = 'mellea_token';

export const setToken = (token: string): void => {
  localStorage.setItem(TOKEN_KEY, token);
};

export const getToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY);
};

export const clearToken = (): void => {
  localStorage.removeItem(TOKEN_KEY);
};

export const isAuthenticated = (): boolean => {
  return !!getToken();
};

// Default export kept for backward compatibility with index.ts re-export.
// Mock modules do not use this.
const apiClient = {} as never;
export default apiClient;
