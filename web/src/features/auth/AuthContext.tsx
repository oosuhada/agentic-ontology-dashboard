import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  openPublicBlueprintComparison,
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
const PUBLIC_COMPARISON_PATH = "/app/projects/manufacturing-demo-project/blueprint-compare";

function isPublicComparisonPath() {
  return window.location.pathname.replace(/\/$/, "") === PUBLIC_COMPARISON_PATH;
}

type ComparisonHostWindow = Window & {
  __ONTOLOGY_COMPARISON_USER__?: AuthUser | null;
};

function inheritedComparisonUser(): AuthUser | null {
  const params = new URLSearchParams(window.location.search);
  if (params.get("comparison_embed") !== "1" || window.parent === window) return null;
  try {
    if (window.parent.location.origin !== window.location.origin) return null;
    return (window.parent as ComparisonHostWindow).__ONTOLOGY_COMPARISON_USER__ ?? null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const embeddedUser = inheritedComparisonUser();
  const [user, setUser] = useState<AuthUser | null>(() => embeddedUser);
  const [loading, setLoading] = useState(() => !embeddedUser);

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
    const inherited = inheritedComparisonUser();
    if (inherited) {
      setUser(inherited);
      setLoading(false);
      return;
    }
    let active = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), AUTH_BOOTSTRAP_TIMEOUT_MS);
    const bootstrap = async () => {
      try {
        return await getCurrentUser(controller.signal);
      } catch (error) {
        if (error instanceof ApiError && error.status === 401 && isPublicComparisonPath()) {
          return openPublicBlueprintComparison(controller.signal);
        }
        throw error;
      }
    };
    bootstrap()
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
