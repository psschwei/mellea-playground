import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { authApi, isAuthenticated, clearToken } from '@/api';
import { adminApi, ImpersonationStatus } from '@/api/admin';
import type { User, LoginRequest, RegisterRequest } from '@/types';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isLoggedIn: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  // Impersonation
  impersonationStatus: ImpersonationStatus | null;
  startImpersonation: (userId: string) => Promise<void>;
  stopImpersonation: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [impersonationStatus, setImpersonationStatus] = useState<ImpersonationStatus | null>(null);

  const checkImpersonationStatus = useCallback(async () => {
    if (!isAuthenticated()) {
      setImpersonationStatus(null);
      return;
    }

    try {
      const status = await adminApi.getImpersonationStatus();
      setImpersonationStatus(status);
    } catch {
      // Not an admin or not authenticated - that's ok
      setImpersonationStatus(null);
    }
  }, []);

  const refreshUser = useCallback(async () => {
    if (!isAuthenticated()) {
      setUser(null);
      setImpersonationStatus(null);
      setIsLoading(false);
      return;
    }

    try {
      const userData = await authApi.me();
      setUser(userData);
      // Check impersonation status after getting user
      await checkImpersonationStatus();
    } catch {
      clearToken();
      setUser(null);
      setImpersonationStatus(null);
    } finally {
      setIsLoading(false);
    }
  }, [checkImpersonationStatus]);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (credentials: LoginRequest) => {
    const response = await authApi.login(credentials);
    setUser(response.user);
  };

  const register = async (data: RegisterRequest) => {
    const response = await authApi.register(data);
    setUser(response.user);
  };

  const logout = async () => {
    await authApi.logout();
    setUser(null);
    setImpersonationStatus(null);
  };

  const startImpersonation = async (userId: string) => {
    await adminApi.startImpersonation(userId);
    // Refresh user to get the impersonated user's data
    await refreshUser();
  };

  const stopImpersonation = async () => {
    await adminApi.stopImpersonation();
    // Refresh user to get the admin's data back
    await refreshUser();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isLoggedIn: !!user,
        login,
        register,
        logout,
        refreshUser,
        impersonationStatus,
        startImpersonation,
        stopImpersonation,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
