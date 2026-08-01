import { useEffect, useState } from "react";

export function navigate(path: string, options?: { replace?: boolean }) {
  if (options?.replace) window.history.replaceState({}, "", path);
  else window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function analysisPath(analysisId: string) {
  return `/app/analysis/${encodeURIComponent(analysisId)}`;
}

export function matchAnalysisPath(pathname: string): string | null {
  const match = pathname.match(/^\/app\/analysis\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

export function usePathname() {
  const [pathname, setPathname] = useState(() => window.location.pathname);

  useEffect(() => {
    const update = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);

  return pathname;
}
