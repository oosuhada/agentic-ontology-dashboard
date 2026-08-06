import { useEffect, useState } from "react";

export function navigate(path: string, options: { replace?: boolean } = {}) {
  if (options.replace) window.history.replaceState({}, "", path);
  else window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function usePathname() {
  const [pathname, setPathname] = useState(window.location.pathname);
  useEffect(() => {
    const onChange = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", onChange);
    return () => window.removeEventListener("popstate", onChange);
  }, []);
  return pathname;
}

export function mvpProjectPath(projectId: string) {
  return `/app/projects/${encodeURIComponent(projectId)}/mvp`;
}

export function matchMvpProjectPath(pathname: string): { projectId: string } | null {
  const match = pathname.match(/^\/app\/projects\/([^/]+)\/mvp\/?$/);
  return match ? { projectId: decodeURIComponent(match[1]) } : null;
}

export function loginPath(returnTo?: string) {
  return returnTo ? `/login?returnTo=${encodeURIComponent(returnTo)}` : "/login";
}

export function safeApplicationReturnPath(value: string | null): string | null {
  if (!value || !value.startsWith("/app/")) return null;
  return matchMvpProjectPath(value.split("?")[0]) ? value : null;
}
