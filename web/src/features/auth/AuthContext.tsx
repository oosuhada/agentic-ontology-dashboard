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
const AUTH_BOOTSTRAP_TIMEOUT_MS = 6_000;

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
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), AUTH_BOOTSTRAP_TIMEOUT_MS);
    getCurrentUser(controller.signal)
      .then((current) => active && setUser(current))
      .catch((error) => {
        if (active && error instanceof DOMException && error.name === "AbortError") {
          console.warn("Session check timed out; returning to sign in.");
          setUser(null);
        } else if (active && (!(error instanceof ApiError) || error.status !== 401)) {
          console.error(error);
        }
      })
      .finally(() => {
        window.clearTimeout(timeout);
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
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
