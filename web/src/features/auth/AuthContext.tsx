import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  setActiveProject as setActiveProjectRequest,
} from "../../api";
import type { AuthUser } from "../../types";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<AuthUser | null>;
  setActiveProject: (projectId: string) => Promise<AuthUser>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh(): Promise<AuthUser | null> {
    try {
      const current = await getCurrentUser();
      setUser(current);
      return current;
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 401) throw error;
      setUser(null);
      return null;
    }
  }

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then((current) => active && setUser(current))
      .catch((error) => {
        if (active && (!(error instanceof ApiError) || error.status !== 401)) {
          console.error(error);
        }
      })
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    login: async (email, password) => {
      const authenticated = await loginRequest(email, password);
      setUser(authenticated);
      return authenticated;
    },
    logout: async () => {
      await logoutRequest();
      setUser(null);
    },
    refresh,
    setActiveProject: async (projectId) => {
      const updated = await setActiveProjectRequest(projectId);
      setUser(updated);
      return updated;
    },
  }), [user, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
