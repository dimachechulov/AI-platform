import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { getProfile, loginUser, refreshTokenApi, registerUser } from "../api";
import { UserProfile } from "../types";
import { bindTokenSync, clearAuthTokens, setAuthTokens } from "../api/client";

type AuthContextValue = {
  token: string | null;
  user: UserProfile | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    fullName?: string
  ) => Promise<void>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
  refreshAccess: () => Promise<string | null>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem("ai_platform_token") || null
  );
  const [refreshToken, setRefreshToken] = useState<string | null>(
    () => localStorage.getItem("ai_platform_refresh") || null
  );
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState<boolean>(!!token);

  const loadProfile = useCallback(
    async (activeToken: string | null) => {
      if (!activeToken) {
        setUser(null);
        setLoading(false);
        return;
      }
      try {
        setLoading(true);
        const profile = await getProfile(activeToken);
        setUser(profile);
      } catch (error) {
        console.error("Failed to load profile", error);
        setUser(null);
        setToken(null);
        setRefreshToken(null);
        clearAuthTokens();
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (token) {
      void loadProfile(token);
    } else {
      setLoading(false);
    }
  }, [token, loadProfile]);

  const login = useCallback(
    async (email: string, password: string) => {
      setLoading(true);
      const result = await loginUser({ username: email, password });
      setToken(result.access_token);
      setRefreshToken(result.refresh_token);
      setAuthTokens(result.access_token, result.refresh_token);
      await loadProfile(result.access_token);
      setLoading(false);
    },
    [loadProfile]
  );

  const register = useCallback(
    async (email: string, password: string, fullName?: string) => {
      setLoading(true);
      await registerUser({ email, password, full_name: fullName });
      await login(email, password);
    },
    [login]
  );

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setRefreshToken(null);
    clearAuthTokens();
  }, []);

  const refreshProfile = useCallback(async () => {
    if (token) {
      await loadProfile(token);
    }
  }, [token, loadProfile]);

  const refreshAccess = useCallback(async () => {
    if (!refreshToken) {
      logout();
      return null;
    }
    try {
      const res = await refreshTokenApi({ refresh_token: refreshToken });
      setToken(res.access_token);
      setRefreshToken(res.refresh_token);
      setAuthTokens(res.access_token, res.refresh_token);
      return res.access_token;
    } catch {
      logout();
      return null;
    }
  }, [refreshToken, logout]);

  useEffect(() => {
    bindTokenSync((access, refresh) => {
      setToken(access);
      if (refresh !== undefined) {
        setRefreshToken(refresh);
      }
    });
  }, []);

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        loading,
        login,
        register,
        logout,
        refreshProfile,
        refreshAccess,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}

