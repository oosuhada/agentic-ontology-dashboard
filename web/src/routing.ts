import { useEffect, useState } from "react";

const basePath = import.meta.env.BASE_URL === "/"
  ? ""
  : import.meta.env.BASE_URL.replace(/\/$/, "");

function normalizePathname(pathname: string) {
  const withoutBase = !basePath
    ? pathname
    : pathname === basePath
      ? "/"
      : pathname.startsWith(`${basePath}/`)
        ? pathname.slice(basePath.length) || "/"
        : pathname;
  return withoutBase.length > 1 ? withoutBase.replace(/\/+$/, "") : withoutBase;
}

function withBasePath(path: string) {
  if (!basePath || !path.startsWith("/")) return path;
  return `${basePath}${path}`;
}

export function navigate(path: string, options?: { replace?: boolean }) {
  const target = withBasePath(path);
  if (options?.replace) window.history.replaceState({}, "", target);
  else window.history.pushState({}, "", target);
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

export function projectDashboardPath(projectId: string) {
  return `/app/projects/${encodeURIComponent(projectId)}`;
}

export function blueprintProjectPath(projectId: string) {
  return `/app/projects/${encodeURIComponent(projectId)}/blueprint`;
}

export function matchBlueprintProjectPath(pathname: string): { projectId: string } | null {
  const match = pathname.match(/^\/app\/projects\/([^/]+)\/blueprint$/);
  return match ? { projectId: decodeURIComponent(match[1]) } : null;
}

export function blueprintV2ProjectPath(projectId: string) {
  return `/app/projects/${encodeURIComponent(projectId)}/blueprint-v2`;
}

export function matchBlueprintV2ProjectPath(pathname: string): { projectId: string } | null {
  const match = pathname.match(/^\/app\/projects\/([^/]+)\/blueprint-v2$/);
  return match ? { projectId: decodeURIComponent(match[1]) } : null;
}

export function blueprintComparisonPath(projectId: string) {
  return `/app/projects/${encodeURIComponent(projectId)}/blueprint-compare`;
}

export function matchBlueprintComparisonPath(pathname: string): { projectId: string } | null {
  const match = pathname.match(/^\/app\/projects\/([^/]+)\/blueprint-compare$/);
  return match ? { projectId: decodeURIComponent(match[1]) } : null;
}

export function matchProjectDashboardPath(pathname: string): { projectId: string } | null {
  const match = pathname.match(/^\/app\/projects\/([^/]+)$/);
  return match ? { projectId: decodeURIComponent(match[1]) } : null;
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

export function modelingPath(projectId: string, workspaceId: string) {
  return `/app/projects/${encodeURIComponent(projectId)}/workspaces/${encodeURIComponent(workspaceId)}/modeling`;
}

export function matchModelingPath(pathname: string): { projectId: string; workspaceId: string } | null {
  const match = pathname.match(/^\/app\/projects\/([^/]+)\/workspaces\/([^/]+)\/modeling$/);
  return match
    ? { projectId: decodeURIComponent(match[1]), workspaceId: decodeURIComponent(match[2]) }
    : null;
}

export function usePathname() {
  const [pathname, setPathname] = useState(() => normalizePathname(window.location.pathname));

  useEffect(() => {
    const update = () => setPathname(normalizePathname(window.location.pathname));
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, []);

  return pathname;
}
