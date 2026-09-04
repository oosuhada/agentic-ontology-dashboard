import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { matchOperationsProjectPath, operationsSurfacePath, navigate } from "../../../routing";
import type { OperationsDashboardMode, OperationsReportTab, OperationsRoleLens, OperationsSelection, OperationsView } from "../api/operationsContracts";

const SESSION_PREFIX = "ontology-dashboard:operations-selection:";

interface OperationsSelectionContextValue {
  selection: OperationsSelection;
  updateSelection: (patch: Partial<Omit<OperationsSelection, "projectId">>, options?: { replace?: boolean }) => void;
}

const OperationsSelectionContext = createContext<OperationsSelectionContextValue | null>(null);

function validView(value: string | null): OperationsView {
  if (value === "objects" || value === "operations" || value === "reports" || value === "system") return value;
  if (value === "executive-report" || value === "inspection-report") return "reports";
  return "overview";
}

function validReportTab(value: string | null, legacyView?: string | null): OperationsReportTab {
  if (value === "inspection-request" || value === "status-map" || value === "summary-report" || value === "executive-brief") return value;
  if (legacyView === "inspection-report") return "inspection-request";
  if (legacyView === "executive-report") return "executive-brief";
  return "status-map";
}

function validRole(value: string | null, fallback: OperationsRoleLens): OperationsRoleLens {
  return value === "field_operator" || value === "process_manager" ? value : fallback;
}

function validDashboard(value: string | null): OperationsDashboardMode {
  return value === "classic" ? "classic" : "workflow";
}

function optionalValue(value: string | null): string | null {
  const normalized = value?.trim();
  return normalized ? normalized : null;
}

export function parseOperationsSelection(input: {
  projectId: string;
  search: string;
  defaultRole: OperationsRoleLens;
  defaultView?: OperationsView;
  defaultSurface?: string | null;
  pathSurface?: string | null;
  defaultReportTab?: OperationsReportTab;
  sessionValue?: string | null;
}): OperationsSelection {
  let session: Partial<OperationsSelection> = {};
  if (input.sessionValue) {
    try {
      session = JSON.parse(input.sessionValue) as Partial<OperationsSelection>;
    } catch {
      session = {};
    }
  }
  const params = new URLSearchParams(input.search);
  const queryHasView = params.has("view");
  const queryView = params.get("view");
  const queryHasSurface = params.has("surface");
  const queryHasReportTab = params.has("report");
  const queryHasDashboard = params.has("dashboard");
  const queryHasRole = params.has("role");
  const queryHasWorkspace = params.has("workspace_id");
  const queryHasAsset = params.has("asset_id");
  const queryHasEvent = params.has("event_id");
  const routeHasSurface = Boolean(input.pathSurface);
  const explicitNavigation = Boolean(
    routeHasSurface
    || queryHasView
    || queryHasSurface
    || queryHasReportTab
    || queryHasDashboard
    || queryHasRole
    || queryHasWorkspace,
  );
  const shouldRestoreSessionSelection = !explicitNavigation || queryHasAsset || queryHasEvent;
  const defaultView = input.defaultView ?? "overview";
  const sessionView = typeof session.view === "string" ? validView(session.view) : null;
  return {
    projectId: input.projectId,
    view: queryHasView ? validView(queryView) : sessionView ?? defaultView,
    surface: queryHasSurface
      ? optionalValue(params.get("surface"))
      : optionalValue(input.pathSurface ?? session.surface ?? input.defaultSurface ?? null),
    dashboard: queryHasDashboard
      ? validDashboard(params.get("dashboard"))
      : validDashboard(typeof session.dashboard === "string" ? session.dashboard : null),
    reportTab: queryHasReportTab
      ? validReportTab(params.get("report"), queryView)
      : queryHasView && (queryView === "executive-report" || queryView === "inspection-report")
        ? validReportTab(null, queryView)
      : typeof session.reportTab === "string"
        ? validReportTab(session.reportTab, queryView ?? sessionView)
        : input.defaultReportTab ?? validReportTab(null, defaultView),
    role: queryHasRole
      ? validRole(params.get("role"), input.defaultRole)
      : validRole(typeof session.role === "string" ? session.role : null, input.defaultRole),
    workspaceId: queryHasWorkspace ? optionalValue(params.get("workspace_id")) : optionalValue(session.workspaceId ?? null),
    assetId: queryHasAsset
      ? optionalValue(params.get("asset_id"))
      : shouldRestoreSessionSelection
        ? optionalValue(session.assetId ?? null)
        : null,
    eventId: queryHasEvent
      ? optionalValue(params.get("event_id"))
      : shouldRestoreSessionSelection
        ? optionalValue(session.eventId ?? null)
        : null,
  };
}

export function selectionSearch(selection: OperationsSelection): string {
  const params = new URLSearchParams();
  params.set("view", selection.view);
  params.set("dashboard", selection.dashboard);
  if (selection.view === "reports") params.set("report", selection.reportTab);
  params.set("role", selection.role);
  if (selection.workspaceId) params.set("workspace_id", selection.workspaceId);
  if (selection.assetId) params.set("asset_id", selection.assetId);
  if (selection.eventId) params.set("event_id", selection.eventId);
  return params.toString();
}

export function OperationsSelectionProvider({
  projectId,
  defaultRole,
  defaultView = "overview",
  defaultSurface = null,
  defaultReportTab = "status-map",
  storageScope = "anonymous",
  navigationBasePath = null,
  children,
}: {
  projectId: string;
  defaultRole: OperationsRoleLens;
  defaultView?: OperationsView;
  defaultSurface?: string | null;
  defaultReportTab?: OperationsReportTab;
  storageScope?: string;
  navigationBasePath?: string | null;
  children: ReactNode;
}) {
  const storageKey = `${SESSION_PREFIX}${storageScope}:${projectId}`;
  const readSelection = useCallback(() => parseOperationsSelection({
    projectId,
    search: window.location.search,
    pathSurface: navigationBasePath ? null : matchOperationsProjectPath(window.location.pathname)?.surfaceId ?? null,
    defaultRole,
    defaultView,
    defaultSurface,
    defaultReportTab,
    sessionValue: window.sessionStorage.getItem(storageKey),
  }), [defaultReportTab, defaultRole, defaultSurface, defaultView, navigationBasePath, projectId, storageKey]);
  const [selection, setSelection] = useState<OperationsSelection>(readSelection);

  useEffect(() => {
    const sync = () => setSelection(readSelection());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, [readSelection]);

  useEffect(() => {
    window.sessionStorage.setItem(storageKey, JSON.stringify(selection));
  }, [selection, storageKey]);

  const updateSelection = useCallback((
    patch: Partial<Omit<OperationsSelection, "projectId">>,
    options?: { replace?: boolean },
  ) => {
    const current = readSelection();
    const next: OperationsSelection = { ...current, ...patch, projectId };
    // Keep React state authoritative immediately. Relying only on the
    // synthetic popstate below is racy because the application-level router
    // may process that event first and replace/remount route content before
    // this provider's popstate listener observes it.
    setSelection(next);
    window.sessionStorage.setItem(storageKey, JSON.stringify(next));
    const params = new URLSearchParams(selectionSearch(next));
    if (navigationBasePath && next.surface) params.set("surface", next.surface);
    const currentParams = new URLSearchParams(window.location.search);
    const workspaceShell = currentParams.get("workspace_shell");
    if (workspaceShell) params.set("workspace_shell", workspaceShell);
    const targetPath = navigationBasePath ?? operationsSurfacePath(projectId, next.surface);
    navigate(`${targetPath}?${params.toString()}`, { replace: options?.replace });
  }, [navigationBasePath, projectId, readSelection, storageKey]);

  const value = useMemo(() => ({ selection, updateSelection }), [selection, updateSelection]);
  return <OperationsSelectionContext.Provider value={value}>{children}</OperationsSelectionContext.Provider>;
}

export function useOperationsSelection() {
  const value = useContext(OperationsSelectionContext);
  if (!value) throw new Error("useOperationsSelection must be used inside OperationsSelectionProvider");
  return value;
}
