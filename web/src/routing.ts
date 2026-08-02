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

export function agentPath(
  projectId: string,
  workspaceId: string,
  context?: { question?: string; objectType?: string; objectId?: string; runId?: string },
) {
  const base = `/app/projects/${encodeURIComponent(projectId)}/workspaces/${encodeURIComponent(workspaceId)}/agent`;
  const params = new URLSearchParams();
  if (context?.question) params.set("question", context.question);
  if (context?.objectType) params.set("objectType", context.objectType);
  if (context?.objectId) params.set("objectId", context.objectId);
  if (context?.runId) params.set("run", context.runId);
  return params.size ? `${base}?${params.toString()}` : base;
}

export function matchAgentPath(pathname: string): { projectId: string; workspaceId: string } | null {
  const match = pathname.match(/^\/app\/projects\/([^/]+)\/workspaces\/([^/]+)\/agent$/);
  return match
    ? { projectId: decodeURIComponent(match[1]), workspaceId: decodeURIComponent(match[2]) }
    : null;
}

export function ontologyPath(projectId: string, workspaceId: string) {
  return `/app/projects/${encodeURIComponent(projectId)}/workspaces/${encodeURIComponent(workspaceId)}/ontology`;
}

export function matchOntologyPath(pathname: string): { projectId: string; workspaceId: string } | null {
  const match = pathname.match(/^\/app\/projects\/([^/]+)\/workspaces\/([^/]+)\/ontology$/);
  return match
    ? { projectId: decodeURIComponent(match[1]), workspaceId: decodeURIComponent(match[2]) }
    : null;
}

export function projectHomePath(projectId: string) {
  return `/app/projects/${encodeURIComponent(projectId)}/home`;
}

export function matchProjectHomePath(pathname: string): { projectId: string } | null {
  const match = pathname.match(/^\/app\/projects\/([^/]+)\/home$/);
  return match ? { projectId: decodeURIComponent(match[1]) } : null;
}

export function datasetCatalogPath(projectId: string) {
  return `/app/projects/${encodeURIComponent(projectId)}/datasets`;
}

export function matchDatasetCatalogPath(pathname: string): { projectId: string } | null {
  const match = pathname.match(/^\/app\/projects\/([^/]+)\/datasets$/);
  return match ? { projectId: decodeURIComponent(match[1]) } : null;
}

export function governancePath(projectId: string, workspaceId: string) {
  return `/app/projects/${encodeURIComponent(projectId)}/workspaces/${encodeURIComponent(workspaceId)}/governance`;
}

export function matchGovernancePath(pathname: string): { projectId: string; workspaceId: string } | null {
  const match = pathname.match(/^\/app\/projects\/([^/]+)\/workspaces\/([^/]+)\/governance$/);
  return match
    ? { projectId: decodeURIComponent(match[1]), workspaceId: decodeURIComponent(match[2]) }
    : null;
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
