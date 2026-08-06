import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { mvpProjectPath, navigate } from "../../../routing";
import type { MvpRoleLens, MvpSelection, MvpView } from "../api/mvpContracts";

const SESSION_PREFIX = "ontology-dashboard:mvp-selection:";

interface MvpSelectionContextValue {
  selection: MvpSelection;
  updateSelection: (patch: Partial<Omit<MvpSelection, "projectId">>, options?: { replace?: boolean }) => void;
}

const MvpSelectionContext = createContext<MvpSelectionContextValue | null>(null);

function validView(value: string | null): MvpView {
  if (value === "objects" || value === "operations" || value === "executive-report") return value;
  return "overview";
}

function validRole(value: string | null, fallback: MvpRoleLens): MvpRoleLens {
  return value === "field_operator" || value === "process_manager" ? value : fallback;
}

function optionalValue(value: string | null): string | null {
  const normalized = value?.trim();
  return normalized ? normalized : null;
}

export function parseMvpSelection(input: {
  projectId: string;
  search: string;
  defaultRole: MvpRoleLens;
  sessionValue?: string | null;
}): MvpSelection {
  let session: Partial<MvpSelection> = {};
  if (input.sessionValue) {
    try {
      session = JSON.parse(input.sessionValue) as Partial<MvpSelection>;
    } catch {
      session = {};
    }
  }
  const params = new URLSearchParams(input.search);
  const queryHasView = params.has("view");
  const queryHasRole = params.has("role");
  const queryHasWorkspace = params.has("workspace_id");
  const queryHasAsset = params.has("asset_id");
  const queryHasEvent = params.has("event_id");
  return {
    projectId: input.projectId,
    view: queryHasView ? validView(params.get("view")) : validView(typeof session.view === "string" ? session.view : null),
    role: queryHasRole
      ? validRole(params.get("role"), input.defaultRole)
      : validRole(typeof session.role === "string" ? session.role : null, input.defaultRole),
    workspaceId: queryHasWorkspace ? optionalValue(params.get("workspace_id")) : optionalValue(session.workspaceId ?? null),
    assetId: queryHasAsset ? optionalValue(params.get("asset_id")) : optionalValue(session.assetId ?? null),
    eventId: queryHasEvent ? optionalValue(params.get("event_id")) : optionalValue(session.eventId ?? null),
  };
}

export function selectionSearch(selection: MvpSelection): string {
  const params = new URLSearchParams();
  params.set("view", selection.view);
  params.set("role", selection.role);
  if (selection.workspaceId) params.set("workspace_id", selection.workspaceId);
  if (selection.assetId) params.set("asset_id", selection.assetId);
  if (selection.eventId) params.set("event_id", selection.eventId);
  return params.toString();
}

export function MvpSelectionProvider({
  projectId,
  defaultRole,
  children,
}: {
  projectId: string;
  defaultRole: MvpRoleLens;
  children: ReactNode;
}) {
  const storageKey = `${SESSION_PREFIX}${projectId}`;
  const readSelection = useCallback(() => parseMvpSelection({
    projectId,
    search: window.location.search,
    defaultRole,
    sessionValue: window.sessionStorage.getItem(storageKey),
  }), [defaultRole, projectId, storageKey]);
  const [selection, setSelection] = useState<MvpSelection>(readSelection);

  useEffect(() => {
    const sync = () => setSelection(readSelection());
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, [readSelection]);

  useEffect(() => {
    window.sessionStorage.setItem(storageKey, JSON.stringify(selection));
  }, [selection, storageKey]);

  const updateSelection = useCallback((
    patch: Partial<Omit<MvpSelection, "projectId">>,
    options?: { replace?: boolean },
  ) => {
    const current = readSelection();
    const next: MvpSelection = { ...current, ...patch, projectId };
    window.sessionStorage.setItem(storageKey, JSON.stringify(next));
    navigate(`${mvpProjectPath(projectId)}?${selectionSearch(next)}`, { replace: options?.replace });
  }, [projectId, readSelection, storageKey]);

  const value = useMemo(() => ({ selection, updateSelection }), [selection, updateSelection]);
  return <MvpSelectionContext.Provider value={value}>{children}</MvpSelectionContext.Provider>;
}

export function useMvpSelection() {
  const value = useContext(MvpSelectionContext);
  if (!value) throw new Error("useMvpSelection must be used inside MvpSelectionProvider");
  return value;
}
