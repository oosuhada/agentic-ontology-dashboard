import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addNote,
  createAuditExportCheckpoint,
  createDashboardShare,
  createExport,
  createModelReleaseRequest,
  createSavedView,
  deleteSavedView,
  followUp,
  getBoardCatalog,
  getDatasetCatalogDetail,
  getDatasetCatalogPage,
  getDashboardTemplatePreview,
  getResolvedDashboard,
  getSavedView,
  getSavedViews,
  invokeOntologyAction,
  publishDashboardTemplate,
  recommendBoards,
  recordDecision,
  requestDashboardTemplatePublish,
  resolveDashboardShare,
  restoreDashboardDefaults,
  saveDashboardPreferences,
} from "../../api";
import { analysisPath, datasetCatalogPath, navigate } from "../../routing";
import type { AppRole, Intent } from "../../types";
import { useAuth } from "../auth/AuthContext";
import { WorkbenchState } from "../../ui/foundry/WorkbenchState";
import { useI18n } from "../../ui/i18n/I18nProvider";
import type { AddAnalysisBoardRequest } from "../analysis/types";
import { BoardCanvas } from "../dashboard/BoardCanvas";
import { BoardCatalogPanel } from "../dashboard/BoardCatalogPanel";
import { BoardInspector } from "../dashboard/BoardInspector";
import { BoardRuntimeSurface } from "../dashboard/BoardRuntimeSurface";
import { ContextPanel, type DashboardDataConnection } from "../dashboard/ContextPanel";
import { DashboardShell, type WorkspaceView } from "../dashboard/DashboardShell";
import type { DatasetCatalogDetail, DatasetCatalogItem } from "../datasets/types";
import type {
  BoardCatalogDefinition,
  BoardCategory,
  BoardVisualizationRuntime,
  DashboardBoard,
  DashboardMode,
  ResolvedDashboard,
  SavedView,
  SelectionFilter,
  VisualizationSettings,
} from "../dashboard/types";
import { cloneDashboard } from "../dashboard/utils";
import {
  clearSelectionFilters,
  downstreamBoardIds,
  filtersForBoard,
  parameterIdForSelectionFilter,
  selectionFilterFromEvent,
  upsertSelectionFilter,
} from "../dashboard/cross-filter-engine";
import type { DashboardDraftResponse } from "../planner/types";
import { primaryRole, ROLE_LANDING } from "./roleLanding";
import { PredictiveMaintenanceReplayPanel } from "../predictive-maintenance/PredictiveMaintenanceReplayPanel";
import {
  useEventDetail,
  usePredictiveMaintenanceDashboardSource,
  useRoleWorkspace,
  useWorkspaceCatalog,
} from "./useManufacturingData";
import { useDashboardEditor } from "./useDashboardEditor";
import { VisualizationSwitcher } from "../dashboard/visualization/VisualizationSwitcher";
import { visualizationSettings } from "../dashboard/visualization/visualizationProfile";
import { RoleReportWorkbench } from "../reports/RoleReportWorkbench";
import { applyAdaptiveDashboardProfile, deriveAdaptiveExperience } from "./adaptiveExperience";
import { localizeAdaptiveProfile, localizeRoleLanding } from "./localizedExperience";
import {
  optimizeDashboardLayout,
  type BoardContentMetric,
  type DashboardLayoutStrategy,
} from "../dashboard/layoutOptimizer";

const AnalysisWorkbench = lazy(() =>
  import("../dashboard/AnalysisWorkbench").then((module) => ({ default: module.AnalysisWorkbench })),
);
const DashboardBoardRenderer = lazy(() =>
  import("../dashboard/DashboardBoardRenderer").then((module) => ({ default: module.DashboardBoardRenderer })),
);

interface ManufacturingAppProps {
  initialWorkspaceView?: WorkspaceView;
  analysisId?: string;
}

interface PendingOntologyGraphBoard {
  projectId: string;
  workspaceId: string;
  objectType: string;
  objectId: string;
  title: string;
}

interface DashboardDraftRecovery {
  saved_at: string;
  base_revision: number;
  template_version: number;
  dashboard: ResolvedDashboard;
}

const PENDING_ONTOLOGY_GRAPH_BOARD = "ontology-dashboard:add-graph-board";
const DASHBOARD_DRAFT_RECOVERY_PREFIX = "ontology-dashboard:dashboard-draft";
const DASHBOARD_HISTORY_LIMIT = 50;

function dashboardDraftStorageKey(userId: string, workspaceId: string, role: AppRole) {
  return `${DASHBOARD_DRAFT_RECOVERY_PREFIX}:${userId}:${workspaceId}:${role}`;
}

function sameDashboardDraft(left: ResolvedDashboard | null, right: ResolvedDashboard | null) {
  if (!left || !right) return left === right;
  return JSON.stringify({
    active_tab_id: left.active_tab_id,
    tabs: left.tabs,
    parameter_state: left.parameter_state,
  }) === JSON.stringify({
    active_tab_id: right.active_tab_id,
    tabs: right.tabs,
    parameter_state: right.parameter_state,
  });
}

export function ManufacturingApp({ initialWorkspaceView, analysisId = "risk-event-portfolio" }: ManufacturingAppProps = {}) {
  const { user, logout, setActiveProject } = useAuth();
  const { locale, t } = useI18n();
  if (!user) throw new Error("ManufacturingApp requires an authenticated user");
  const authenticatedUser = user;
  const availableRoles = (authenticatedUser.active_project_roles.length
    ? authenticatedUser.active_project_roles
    : authenticatedUser.roles
  ).filter((role): role is AppRole => role in ROLE_LANDING);
  const roleStorageKey = `ontology-dashboard:active-role:${authenticatedUser.user_id}:${authenticatedUser.active_project_id ?? "default"}`;
  const [appRole, setAppRole] = useState<AppRole>(() => {
    const saved = window.localStorage.getItem(roleStorageKey) as AppRole | null;
    return saved && availableRoles.includes(saved) ? saved : primaryRole(availableRoles);
  });
  useEffect(() => {
    setAppRole((current) => {
      const saved = window.localStorage.getItem(roleStorageKey) as AppRole | null;
      if (saved && availableRoles.includes(saved)) return saved;
      if (availableRoles.includes(current)) return current;
      return primaryRole(availableRoles);
    });
  }, [authenticatedUser.active_project_id, authenticatedUser.active_project_roles.join("|")]);
  const roleConfig = ROLE_LANDING[appRole];
  const localizedRoleConfig = useMemo(
    () => localizeRoleLanding(appRole, roleConfig, t),
    [appRole, roleConfig, t],
  );
  const role = roleConfig.legacyRole;
  const hasDecisionPermission = authenticatedUser.permissions.includes("events.decision");
  const hasNotePermission = authenticatedUser.permissions.includes("events.note");
  const canManageTemplates = authenticatedUser.permissions.includes("dashboards.templates.manage");

  const [intent, setIntent] = useState<Intent>(roleConfig.defaultIntent);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [layoutOptimizing, setLayoutOptimizing] = useState(false);
  const boardContentMetricsRef = useRef<BoardContentMetric[]>([]);
  const previousLocaleRef = useRef(locale);
  const activeProjectRef = useRef(authenticatedUser.active_project_id);
  useEffect(() => {
    activeProjectRef.current = authenticatedUser.active_project_id;
  }, [authenticatedUser.active_project_id]);
  const activateProject = useCallback(async (projectId: string) => {
    if (projectId === activeProjectRef.current) return;
    const previousProjectId = activeProjectRef.current;
    activeProjectRef.current = projectId;
    try {
      await setActiveProject(projectId);
    } catch (reason) {
      activeProjectRef.current = previousProjectId;
      throw reason;
    }
  }, [setActiveProject]);
  const {
    events: fixtureEvents,
    projects,
    workspaces,
    selectedProjectId,
    setSelectedProjectId,
    selectedWorkspaceId,
    setSelectedWorkspaceId,
    selectedEventId,
    setSelectedEventId,
  } = useWorkspaceCatalog(
    authenticatedUser.active_project_id,
    activateProject,
    setError,
  );
  const {
    data: predictiveMaintenanceDashboard,
    loading: predictiveMaintenanceDashboardLoading,
    fallbackReason: predictiveMaintenanceFallbackReason,
  } = usePredictiveMaintenanceDashboardSource(
    selectedProjectId,
    selectedWorkspaceId,
    selectedEventId,
    intent,
    role,
    locale,
    setError,
  );
  const events = predictiveMaintenanceDashboard?.events ?? fixtureEvents;
  const canonicalDashboardActive = Boolean(predictiveMaintenanceDashboard);
  useEffect(() => {
    const canonicalEventId = predictiveMaintenanceDashboard?.selected_event_id;
    if (canonicalEventId && canonicalEventId !== selectedEventId) {
      setSelectedEventId(canonicalEventId);
    }
  }, [predictiveMaintenanceDashboard?.selected_event_id, selectedEventId, setSelectedEventId]);
  const projectActionsConfigured = selectedProjectId === "manufacturing-demo-project";
  const canRecordDecision = hasDecisionPermission && projectActionsConfigured && !canonicalDashboardActive;
  const canRecordNote = hasNotePermission && projectActionsConfigured && !canonicalDashboardActive;
  const {
    evidence,
    report,
    layout,
    lastFollowUp,
    loading: detailLoading,
    load: loadDetail,
    setReport,
    setLayout,
    setLastFollowUp,
  } = useEventDetail(
    selectedEventId,
    intent,
    role,
    locale,
    setError,
    predictiveMaintenanceDashboard?.selected_event_detail,
    canonicalDashboardActive,
  );
  const {
    data: roleWorkspaceData,
    loading: roleWorkspaceLoading,
    load: loadRoleWorkspace,
  } = useRoleWorkspace(
    appRole,
    selectedProjectId,
    selectedWorkspaceId,
    selectedEventId,
    setError,
  );

  const [persistedDashboard, setPersistedDashboard] = useState<ResolvedDashboard | null>(null);
  const [draftDashboard, setDraftDashboard] = useState<ResolvedDashboard | null>(null);
  const [catalogItems, setCatalogItems] = useState<BoardCatalogDefinition[]>([]);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [selectedSavedViewId, setSelectedSavedViewId] = useState("");
  const [mode, setMode] = useState<DashboardMode>("view");
  const [dirty, setDirty] = useState(false);
  const [undoStack, setUndoStack] = useState<ResolvedDashboard[]>([]);
  const [redoStack, setRedoStack] = useState<ResolvedDashboard[]>([]);
  const [recoveryCandidate, setRecoveryCandidate] = useState<DashboardDraftRecovery | null>(null);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [dataConnection, setDataConnection] = useState<DashboardDataConnection>({
    loading: true,
    datasetCount: 0,
    recordCount: 0,
    relationalReadyCount: 0,
    sourceTypes: [],
    datasetNames: [],
    sourceVersions: [],
    externalConnection: false,
    error: null,
  });
  const [datasetItems, setDatasetItems] = useState<DatasetCatalogItem[]>([]);
  const [datasetDetails, setDatasetDetails] = useState<DatasetCatalogDetail[]>([]);
  const selectedProject = projects.find((project) => project.id === selectedProjectId);
  const selectedPack = undefined;
  const adaptiveProfile = useMemo(
    () => deriveAdaptiveExperience(selectedProjectId, selectedProject, selectedPack, datasetItems, datasetDetails),
    [datasetDetails, datasetItems, selectedPack, selectedProject, selectedProjectId],
  );
  const localizedAdaptiveProfile = useMemo(
    () => localizeAdaptiveProfile(
      adaptiveProfile,
      t,
      datasetItems.length,
      datasetItems.reduce((sum, item) => sum + item.record_count, 0),
    ),
    [adaptiveProfile, datasetItems, t],
  );
  const effectiveInitialWorkspaceView: WorkspaceView = initialWorkspaceView ?? roleConfig.defaultWorkspaceView;

  const [selectedBoardId, setSelectedBoardId] = useState<string | null>(null);
  const [fullscreenBoardId, setFullscreenBoardId] = useState<string | null>(null);
  const [affectedBoards, setAffectedBoards] = useState<string[]>([]);
  const [selectionFilters, setSelectionFilters] = useState<SelectionFilter[]>([]);
  const [visualizationRuntimeByBoard, setVisualizationRuntimeByBoard] = useState<Record<string, BoardVisualizationRuntime>>({});
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [catalogSearch, setCatalogSearch] = useState("");
  const [catalogCategory, setCatalogCategory] = useState<BoardCategory | "all">("all");
  const [catalogTargetTabId, setCatalogTargetTabId] = useState("");
  const [targetTemplateRole, setTargetTemplateRole] = useState<AppRole>(appRole);

  const affectedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dashboardRequestSequence = useRef(0);
  const autoSaveFingerprint = useRef("");
  const shareApplied = useRef(false);
  const shareToken = useMemo(() => new URLSearchParams(window.location.search).get("share"), []);

  useEffect(() => {
    if (!selectedProjectId || !selectedWorkspaceId) {
      setDataConnection((current) => ({ ...current, loading: false, datasetCount: 0, recordCount: 0 }));
      return;
    }
    if (authenticatedUser.active_project_id !== selectedProjectId) {
      setDataConnection((current) => ({ ...current, loading: true, error: null }));
      return;
    }
    let cancelled = false;
    setDataConnection((current) => ({ ...current, loading: true, error: null }));
    getDatasetCatalogPage({
      project_id: selectedProjectId,
      workspace_id: selectedWorkspaceId,
      offset: 0,
      limit: 200,
    })
      .then((page) => {
        if (cancelled) return;
        setDatasetItems(page.items);
        const sourceTypes = [...new Set(page.items.map((item) => item.source_type))].sort();
        const datasetNames = page.items.map((item) => item.display_name);
        const sourceVersions = [...new Set(page.items.map((item) => item.latest_source_version).filter(Boolean) as string[])].sort();
        setDataConnection({
          loading: false,
          datasetCount: page.total,
          recordCount: page.items.reduce((sum, item) => sum + item.record_count, 0),
          relationalReadyCount: page.items.filter((item) => item.projection_health.relational === "ready").length,
          sourceTypes,
          datasetNames,
          sourceVersions,
          externalConnection: sourceTypes.some((source) => source !== "local_fixture"),
          error: null,
        });
        return Promise.all(
          page.items.slice(0, 12).map((item) => getDatasetCatalogDetail(selectedProjectId, item.id)),
        );
      })
      .then((details) => {
        if (cancelled || !details) return;
        setDatasetDetails(details);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setDatasetItems([]);
        setDatasetDetails([]);
        setDataConnection({
          loading: false,
          datasetCount: 0,
          recordCount: 0,
          relationalReadyCount: 0,
          sourceTypes: [],
          datasetNames: [],
          sourceVersions: [],
          externalConnection: false,
          error: reason instanceof Error ? reason.message : "Dataset connection status unavailable",
        });
      });
    return () => { cancelled = true; };
  }, [authenticatedUser.active_project_id, selectedProjectId, selectedWorkspaceId]);

  const loadDashboardFoundation = useCallback(async (workspaceId: string) => {
    if (!workspaceId) return;
    const requestId = ++dashboardRequestSequence.current;
    setLoading(true);
    setError("");
    try {
      const [resolvedDashboard, catalog, views] = await Promise.all([
        getResolvedDashboard(workspaceId),
        getBoardCatalog(workspaceId),
        getSavedViews(workspaceId),
      ]);
      const resolved = applyAdaptiveDashboardProfile(resolvedDashboard, adaptiveProfile, catalog);
      if (requestId !== dashboardRequestSequence.current) return;

      let nextDraft = cloneDashboard(resolved);
      if (shareToken && !shareApplied.current) {
        const shared = await resolveDashboardShare(shareToken);
        if (requestId !== dashboardRequestSequence.current) return;
        if (shared.workspace_id !== workspaceId) {
          throw new Error("공유 View의 workspace에 접근할 수 없습니다.");
        }
        nextDraft = {
          ...nextDraft,
          active_tab_id: shared.active_tab_id,
          parameter_state: { ...nextDraft.parameter_state, ...shared.parameter_state },
        };
        shareApplied.current = true;
        setNotice("공유 링크의 tab과 parameter 상태를 현재 세션에 복원했습니다.");
      }

      let nextRecovery: DashboardDraftRecovery | null = null;
      if (!shareToken) {
        const recoveryKey = dashboardDraftStorageKey(authenticatedUser.user_id, workspaceId, appRole);
        const rawRecovery = window.localStorage.getItem(recoveryKey);
        if (rawRecovery) {
          try {
            const parsed = JSON.parse(rawRecovery) as DashboardDraftRecovery;
            if (
              parsed.dashboard?.dashboard_id === resolved.dashboard_id
              && parsed.dashboard.workspace_id === resolved.workspace_id
              && parsed.dashboard.role_code === resolved.role_code
              && parsed.template_version === resolved.template_version
              && parsed.base_revision === resolved.preference_revision
            ) {
              nextRecovery = parsed;
            } else {
              window.localStorage.removeItem(recoveryKey);
            }
          } catch {
            window.localStorage.removeItem(recoveryKey);
          }
        }
      }

      setPersistedDashboard(resolved);
      setDraftDashboard(nextDraft);
      setRecoveryCandidate(nextRecovery);
      setUndoStack([]);
      setRedoStack([]);
      setCatalogTargetTabId(nextDraft.active_tab_id);
      setTargetTemplateRole(appRole);
      setDirty(false);
      setSelectedBoardId(null);
      setFullscreenBoardId(null);
      setSelectionFilters([]);

      setCatalogItems(catalog);
      setSavedViews(views);
    } catch (reason) {
      if (requestId === dashboardRequestSequence.current) {
        setError(reason instanceof Error ? reason.message : "Dashboard를 불러오지 못했습니다.");
      }
    } finally {
      if (requestId === dashboardRequestSequence.current) setLoading(false);
    }
  }, [adaptiveProfile, appRole, authenticatedUser.user_id, shareToken]);

  useEffect(() => {
    if (!selectedProjectId) return;
    const expectedPath = `/app/projects/${encodeURIComponent(selectedProjectId)}`;
    const currentPath = window.location.pathname;
    if (
      (currentPath === "/app" || currentPath.startsWith("/app/projects/"))
      && currentPath !== expectedPath
    ) {
      navigate(`${expectedPath}${window.location.search}`, { replace: true });
    }
  }, [selectedProjectId]);

  useEffect(() => {
    void loadDashboardFoundation(selectedWorkspaceId);
  }, [selectedWorkspaceId, loadDashboardFoundation]);

  const draftRecoveryKey = useMemo(
    () => selectedWorkspaceId
      ? dashboardDraftStorageKey(authenticatedUser.user_id, selectedWorkspaceId, appRole)
      : "",
    [appRole, authenticatedUser.user_id, selectedWorkspaceId],
  );

  useEffect(() => {
    if (!dirty || !draftDashboard || !persistedDashboard || !draftRecoveryKey) return;
    const timer = window.setTimeout(() => {
      const recovery: DashboardDraftRecovery = {
        saved_at: new Date().toISOString(),
        base_revision: persistedDashboard.preference_revision,
        template_version: draftDashboard.template_version,
        dashboard: cloneDashboard(draftDashboard),
      };
      window.localStorage.setItem(draftRecoveryKey, JSON.stringify(recovery));
    }, 400);
    return () => window.clearTimeout(timer);
  }, [dirty, draftDashboard, draftRecoveryKey, persistedDashboard]);

  useEffect(() => {
    if (!dirty) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [dirty]);

  useEffect(() => {
    if (!draftDashboard || !events.length) return;
    const sharedEventId = draftDashboard.parameter_state.selected_event_id;
    const validShared = typeof sharedEventId === "string" && events.some((event) => event.event_id === sharedEventId);
    setSelectedEventId((current) => current || (validShared ? sharedEventId : events[0].event_id));
    const parameterIntent = draftDashboard.parameter_state.intent;
    if (typeof parameterIntent === "string") setIntent(parameterIntent as Intent);
  }, [draftDashboard?.dashboard_id, events, draftDashboard]);

  useEffect(() => () => {
    if (affectedTimer.current) clearTimeout(affectedTimer.current);
  }, []);

  const activeTab = draftDashboard?.tabs.find((tab) => tab.id === draftDashboard.active_tab_id) ?? null;
  const selectedBoard = useMemo(
    () => draftDashboard?.tabs.flatMap((tab) => tab.boards).find((board) => board.id === selectedBoardId) ?? null,
    [draftDashboard, selectedBoardId],
  );
  const selectedBoardTabId = useMemo(
    () => draftDashboard?.tabs.find((tab) => tab.boards.some((board) => board.id === selectedBoardId))?.id ?? null,
    [draftDashboard, selectedBoardId],
  );
  const definitionById = useMemo(
    () => new Map(catalogItems.map((definition) => [definition.id, definition])),
    [catalogItems],
  );
  const selectedDefinition = selectedBoard ? definitionById.get(selectedBoard.definition_id) ?? null : null;
  const pushDashboardHistory = useCallback((current: ResolvedDashboard) => {
    setUndoStack((stack) => [...stack, cloneDashboard(current)].slice(-DASHBOARD_HISTORY_LIMIT));
    setRedoStack([]);
  }, []);
  const {
    updateDraft,
    handleActiveTab,
    handleReorderTabs,
    handleMoveBoard,
    handleLayoutChange,
    handleUpdateBoard,
    handleUpdateBoardById,
    handleRemoveBoard,
    handleToggleHidden,
    handleToggleFavorite,
    handleDuplicateBoard,
    handleAddTab,
    handleAddBoard,
  } = useDashboardEditor({
    draftDashboard,
    selectedBoardId,
    selectedBoard,
    setDraftDashboard,
    setSelectedBoardId,
    setCatalogTargetTabId,
    setMode,
    setDirty,
    setError,
    onBeforeChange: pushDashboardHistory,
  });

  const handleVisualizationRuntime = useCallback((boardId: string, runtime: BoardVisualizationRuntime) => {
    setVisualizationRuntimeByBoard((current) => {
      const previous = current[boardId];
      if (previous
        && previous.active_kind === runtime.active_kind
        && previous.mode === runtime.mode
        && previous.recommendation.profile_hash === runtime.recommendation.profile_hash) return current;
      return { ...current, [boardId]: runtime };
    });
  }, []);

  const handleOptimizeLayout = useCallback(async (strategy: DashboardLayoutStrategy) => {
    if (!draftDashboard?.active_tab_id) return;
    setLayoutOptimizing(true);
    try {
      const rendererByDefinition = new Map(catalogItems.map((definition) => [definition.id, definition.renderer]));
      let recommendedDefinitionIds: string[] = [];
      let plannerMode = "deterministic layout engine";
      try {
        if (strategy === "ai-recommendation") {
          const recommendation = await recommendBoards({
            workspace_id: selectedWorkspaceId,
            goal: locale === "ko-KR"
              ? `${localizedRoleConfig.label} 역할이 현재 데이터에서 중요한 판단을 빠르게 할 수 있도록 Board 우선순위와 레이아웃을 추천해줘`
              : `Recommend board priority and layout so the ${localizedRoleConfig.label} role can make the most important decisions quickly from the current data.`,
            use_llm: true,
            limit: Math.max(5, draftDashboard.tabs.find((tab) => tab.id === draftDashboard.active_tab_id)?.boards.length ?? 5),
          });
          recommendedDefinitionIds = recommendation.recommendations.map((item) => item.definition_id);
          plannerMode = `${recommendation.mode} · ${recommendation.provider}`;
        }
      } catch {
        plannerMode = "deterministic fallback";
      }

      updateDraft((current) => ({
        ...current,
        tabs: current.tabs.map((tab) => {
          if (tab.id !== current.active_tab_id) return tab;
          const rank = new Map(recommendedDefinitionIds.map((definitionId, index) => [definitionId, index]));
          const ordered = strategy === "ai-recommendation"
            ? [...tab.boards].sort((left, right) => {
                const leftRank = rank.get(left.definition_id) ?? Number.MAX_SAFE_INTEGER;
                const rightRank = rank.get(right.definition_id) ?? Number.MAX_SAFE_INTEGER;
                return leftRank - rightRank || left.order - right.order;
              }).map((board, order) => ({ ...board, order }))
            : tab.boards;
          return {
            ...tab,
            boards: optimizeDashboardLayout(
              ordered,
              boardContentMetricsRef.current,
              strategy,
              window.innerWidth,
              rendererByDefinition,
            ),
          };
        }),
      }));
      setNotice(strategy === "content-fit"
        ? t("dashboard.layoutAutoFitApplied")
        : t("dashboard.layoutAiAppliedMode", { mode: plannerMode }));
    } finally {
      setLayoutOptimizing(false);
    }
  }, [catalogItems, draftDashboard, locale, localizedRoleConfig.label, selectedWorkspaceId, t, updateDraft]);

  useEffect(() => {
    if (previousLocaleRef.current === locale) return undefined;
    previousLocaleRef.current = locale;
    const timer = window.setTimeout(() => { void handleOptimizeLayout("content-fit"); }, 450);
    return () => window.clearTimeout(timer);
  }, [handleOptimizeLayout, locale]);

  function handleVisualizationChange(boardId: string, visualization: VisualizationSettings) {
    const board = draftDashboard?.tabs.flatMap((tab) => tab.boards).find((item) => item.id === boardId);
    if (!board) return;
    handleUpdateBoardById(boardId, { settings: { ...board.settings, visualization } });
  }

  function handleUndo() {
    const previous = undoStack.at(-1);
    if (!previous || !draftDashboard) return;
    const next = cloneDashboard(previous);
    setUndoStack((stack) => stack.slice(0, -1));
    setRedoStack((stack) => [...stack, cloneDashboard(draftDashboard)].slice(-DASHBOARD_HISTORY_LIMIT));
    setDraftDashboard(next);
    setSelectedBoardId(null);
    setDirty(!sameDashboardDraft(next, persistedDashboard));
  }

  function handleRedo() {
    const nextEntry = redoStack.at(-1);
    if (!nextEntry || !draftDashboard) return;
    const next = cloneDashboard(nextEntry);
    setRedoStack((stack) => stack.slice(0, -1));
    setUndoStack((stack) => [...stack, cloneDashboard(draftDashboard)].slice(-DASHBOARD_HISTORY_LIMIT));
    setDraftDashboard(next);
    setSelectedBoardId(null);
    setDirty(!sameDashboardDraft(next, persistedDashboard));
  }

  function clearDraftRecovery() {
    if (draftRecoveryKey) window.localStorage.removeItem(draftRecoveryKey);
    setRecoveryCandidate(null);
  }

  function recoverDraft() {
    if (!recoveryCandidate) return;
    setUndoStack(draftDashboard ? [cloneDashboard(draftDashboard)] : []);
    setRedoStack([]);
    setDraftDashboard(cloneDashboard(recoveryCandidate.dashboard));
    setCatalogTargetTabId(recoveryCandidate.dashboard.active_tab_id);
    setRecoveryCandidate(null);
    setMode("edit");
    setDirty(true);
    setNotice(`자동 저장 초안을 복구했습니다. ${new Date(recoveryCandidate.saved_at).toLocaleString()}`);
  }

  function discardDraftRecovery() {
    clearDraftRecovery();
    setNotice("자동 저장 초안을 폐기했습니다.");
  }

  function showAffected(sourceBoardId: string, parameterId: string) {
    if (!draftDashboard) return;
    let ids = downstreamBoardIds(draftDashboard.dependency_graph, sourceBoardId, parameterId);
    if (!ids.length) {
      ids = draftDashboard.tabs
        .flatMap((tab) => tab.boards)
        .filter((board) => definitionById.get(board.definition_id)?.accepts.includes(parameterId))
        .map((board) => board.id);
    }
    setAffectedBoards(ids);
    if (affectedTimer.current) clearTimeout(affectedTimer.current);
    affectedTimer.current = setTimeout(() => setAffectedBoards([]), 5000);
  }

  function handleSelectionFilter(filter: SelectionFilter) {
    setSelectionFilters((current) => upsertSelectionFilter(current, filter));
    showAffected(filter.source_board_id, parameterIdForSelectionFilter(filter) ?? filter.field);
  }

  function handleAddAnalysisBoard(request: AddAnalysisBoardRequest) {
    const definition = definitionById.get("analysis-result");
    if (!definition || !draftDashboard) {
      setError("Analysis Result board definition을 불러오지 못했습니다.");
      return;
    }
    const boardId = `custom:analysis-result:${crypto.randomUUID()}`;
    updateDraft((current) => ({
      ...current,
      tabs: current.tabs.map((tab) => {
        if (tab.id !== current.active_tab_id) return tab;
        const nextY = tab.boards.reduce((maximum, board) => Math.max(maximum, (board.layout?.y ?? board.order * 2) + (board.layout?.h ?? 2)), 0);
        const board: DashboardBoard = {
          id: boardId,
          definition_id: definition.id,
          title: request.title,
          width: definition.default_width,
          order: tab.boards.length,
          layout: {
            x: 0,
            y: nextY,
            w: definition.default_width,
            h: Math.max(1, Number(definition.default_settings.height_units ?? 3)),
            min_w: definition.minimum_width,
            min_h: 1,
            max_w: definition.maximum_width,
            max_h: 12,
          },
          source: {
            kind: "analysis_board",
            analysis_id: request.analysisId,
            analysis_node_id: request.nodeId,
            version_policy: request.versionPolicy,
            version: request.version,
          },
          hidden: false,
          mandatory: false,
          custom: true,
          bindings: {},
          settings: { ...definition.default_settings },
        };
        return { ...tab, boards: [...tab.boards, board] };
      }),
    }));
    setSelectedBoardId(boardId);
    setNotice(`${request.title}을 현재 Dashboard 탭에 Analysis reference로 추가했습니다.`);
  }

  function handleAddOntologyGraphBoard(request: PendingOntologyGraphBoard) {
    const definition = definitionById.get("ontology-relationship");
    if (!definition || !draftDashboard) {
      setError("Ontology Relationship board definition을 불러오지 못했습니다.");
      return false;
    }
    const boardId = `custom:ontology-relationship:${crypto.randomUUID()}`;
    updateDraft((current) => ({
      ...current,
      parameter_state: {
        ...current.parameter_state,
        selected_equipment_id: request.objectId,
        selected_object_type: request.objectType,
      },
      tabs: current.tabs.map((tab) => {
        if (tab.id !== current.active_tab_id) return tab;
        const nextY = tab.boards.reduce(
          (maximum, board) => Math.max(maximum, (board.layout?.y ?? board.order * 2) + (board.layout?.h ?? 2)),
          0,
        );
        const board: DashboardBoard = {
          id: boardId,
          definition_id: definition.id,
          title: request.title,
          width: definition.default_width,
          order: tab.boards.length,
          layout: {
            x: 0,
            y: nextY,
            w: definition.default_width,
            h: Math.max(2, Number(definition.default_settings.height_units ?? 4)),
            min_w: definition.minimum_width,
            min_h: 2,
            max_w: definition.maximum_width,
            max_h: 12,
          },
          source: null,
          hidden: false,
          mandatory: false,
          custom: true,
          bindings: {
            ...definition.default_bindings,
            selected_object_id: request.objectId,
            selected_object_type: request.objectType,
          },
          settings: {
            ...definition.default_settings,
            root_object_id: request.objectId,
            root_object_type: request.objectType,
            traversal_depth: 2,
          },
        };
        return { ...tab, boards: [...tab.boards, board] };
      }),
    }));
    setSelectedBoardId(boardId);
    setNotice(`${request.title}을 현재 Dashboard 탭에 Graph board로 추가했습니다.`);
    return true;
  }

  useEffect(() => {
    if (!draftDashboard || !selectedProjectId || !selectedWorkspaceId) return;
    const raw = sessionStorage.getItem(PENDING_ONTOLOGY_GRAPH_BOARD);
    if (!raw) return;
    try {
      const request = JSON.parse(raw) as PendingOntologyGraphBoard;
      if (request.projectId !== selectedProjectId || request.workspaceId !== selectedWorkspaceId) return;
      if (handleAddOntologyGraphBoard(request)) {
        sessionStorage.removeItem(PENDING_ONTOLOGY_GRAPH_BOARD);
      }
    } catch {
      sessionStorage.removeItem(PENDING_ONTOLOGY_GRAPH_BOARD);
    }
  }, [draftDashboard?.dashboard_id, definitionById, selectedProjectId, selectedWorkspaceId]);

  function handleSelectEvent(sourceBoardId: string, eventId: string) {
    const event = events.find((item) => item.event_id === eventId);
    setSelectedEventId(eventId);
    if (event) setSelectionFilters((current) => upsertSelectionFilter(current, selectionFilterFromEvent(sourceBoardId, event)));
    updateDraft((current) => ({
      ...current,
      parameter_state: {
        ...current.parameter_state,
        selected_event_id: eventId,
        selected_equipment_id: event?.equipment.equipment_id ?? "",
      },
    }), false);
    showAffected(sourceBoardId, "selected_event_id");
  }

  function handleParameterChange(parameterId: string, value: unknown) {
    updateDraft((current) => ({
      ...current,
      parameter_state: { ...current.parameter_state, [parameterId]: value },
    }));
    showAffected("context-panel", parameterId);
    if (parameterId === "intent" && typeof value === "string") {
      const nextIntent = value as Intent;
      setIntent(nextIntent);
      void loadDetail(selectedEventId, nextIntent);
    }
  }

  async function handleDecision(decision: string, note: string) {
    if (!evidence) return;
    await recordDecision(evidence.event_id, authenticatedUser.display_name, decision, note);
    setNotice("판단과 메모를 Ontology Action 및 감사 기록에 저장했습니다.");
  }

  async function handleNote(body: string) {
    if (!evidence) return;
    await addNote(evidence.event_id, authenticatedUser.display_name, body);
    setNotice("점검 기록을 Ontology Action으로 저장했습니다.");
  }

  async function handleAuditCheckpoint(format: "json" | "csv" | "pdf", reason: string) {
    if (!selectedEventId) return;
    await createAuditExportCheckpoint({
      workspace_id: selectedWorkspaceId,
      event_id: selectedEventId,
      export_format: format,
      reason,
    });
    await loadRoleWorkspace(selectedWorkspaceId, selectedEventId);
    setNotice("현재 사건 snapshot의 export checkpoint와 감사 hash를 기록했습니다.");
  }

  async function handleFieldAction(
    action: "complete" | "issue_found" | "blocked",
    input: {
      checklist: string[];
      measurements: Record<string, number | string>;
      photo_metadata: Array<Record<string, unknown>>;
      note: string;
      location: string;
      safety_risk: boolean;
    },
  ) {
    if (!selectedEventId) return;
    const actionType = action === "complete"
      ? "complete_work_order"
      : action === "issue_found"
        ? "report_work_order_issue"
        : "mark_work_order_blocked";
    const parameters = action === "blocked"
      ? { note: input.note, location: input.location, safety_risk: input.safety_risk }
      : {
          checklist: input.checklist,
          measurements: input.measurements,
          photo_metadata: input.photo_metadata,
          note: input.note,
          location: input.location,
        };
    await invokeOntologyAction({
      action_type: actionType,
      object_id: `work_order:${selectedEventId}`,
      workspace_id: selectedWorkspaceId,
      parameters,
      idempotency_key: `field:${action}:${crypto.randomUUID()}`,
    });
    await loadRoleWorkspace(selectedWorkspaceId, selectedEventId);
    setNotice(action === "complete" ? "현장 작업 완료와 엔지니어 handoff를 기록했습니다." : action === "issue_found" ? "현장 문제를 기록하고 엔지니어 handoff를 생성했습니다." : "안전·접근 사유로 작업 불가 상태를 기록했습니다.");
  }

  async function handleModelRelease(input: {
    model_version: string;
    dataset_version: string;
    policy_version: string;
    metrics: Record<string, string | number>;
    threshold_evaluation: Record<string, string | number>;
    notes: string;
  }) {
    await createModelReleaseRequest({ workspace_id: selectedWorkspaceId, ...input });
    await loadRoleWorkspace(selectedWorkspaceId, selectedEventId);
    setNotice("Model release candidate를 관리자 승인 요청으로 제출했습니다.");
  }

  async function handleAsk(question: string) {
    if (!evidence) return;
    setError("");
    try {
      const response = await followUp(evidence.event_id, role, question, locale);
      setLastFollowUp(response);
      setIntent(response.intent);
      setReport(response.report);
      setLayout(response.layout);
      updateDraft((current) => ({
        ...current,
        parameter_state: { ...current.parameter_state, intent: response.intent },
      }), false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "질문을 처리하지 못했습니다.");
    }
  }

  async function handleSave(silent = false) {
    if (!draftDashboard || !persistedDashboard) return;
    if (draftDashboard.role_code !== appRole) {
      setError("다른 역할의 template preview는 개인 설정으로 저장할 수 없습니다. Template 게시를 사용하세요.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const saved = await saveDashboardPreferences({
        workspace_id: selectedWorkspaceId,
        base_revision: persistedDashboard.preference_revision,
        active_tab_id: draftDashboard.active_tab_id,
        tabs: draftDashboard.tabs,
        parameter_state: draftDashboard.parameter_state,
      });
      setPersistedDashboard(saved);
      setDraftDashboard(cloneDashboard(saved));
      clearDraftRecovery();
      setUndoStack([]);
      setRedoStack([]);
      setDirty(false);
      if (!silent) setNotice("개인 Dashboard 설정을 저장했습니다. 다음 로그인에서도 복원됩니다.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Dashboard 설정을 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    if (!dirty || !draftDashboard || !persistedDashboard || saving) return;
    if (draftDashboard.role_code !== appRole) return;
    const fingerprint = JSON.stringify({
      active_tab_id: draftDashboard.active_tab_id,
      tabs: draftDashboard.tabs,
      parameter_state: draftDashboard.parameter_state,
    });
    if (autoSaveFingerprint.current === fingerprint) return;
    const timer = window.setTimeout(() => {
      autoSaveFingerprint.current = fingerprint;
      void handleSave(true);
    }, 1400);
    return () => window.clearTimeout(timer);
  }, [appRole, dirty, draftDashboard, persistedDashboard, saving, selectedWorkspaceId]);

  async function handleRestore() {
    if (!draftDashboard) return;
    if (!window.confirm("현재 개인 변경을 버리고 역할 기본값으로 복원할까요?")) return;
    setError("");
    try {
      if (draftDashboard.role_code !== appRole) {
        const [preview, catalog] = await Promise.all([
          getDashboardTemplatePreview(selectedWorkspaceId, targetTemplateRole),
          getBoardCatalog(selectedWorkspaceId, { role_code: targetTemplateRole }),
        ]);
        setDraftDashboard(preview);
        setCatalogItems(catalog);
        clearDraftRecovery();
        setUndoStack([]);
        setRedoStack([]);
        setDirty(false);
        setNotice(`${targetTemplateRole} template preview를 다시 불러왔습니다.`);
        return;
      }
      const restored = await restoreDashboardDefaults(selectedWorkspaceId);
      setPersistedDashboard(restored);
      setDraftDashboard(cloneDashboard(restored));
      clearDraftRecovery();
      setUndoStack([]);
      setRedoStack([]);
      setDirty(false);
      setNotice("역할 기본 Dashboard로 복원했습니다.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "기본값을 복원하지 못했습니다.");
    }
  }

  async function handleSaveView() {
    if (!draftDashboard || draftDashboard.role_code !== appRole) {
      setError("다른 역할의 template preview에서는 개인 Saved View를 만들 수 없습니다.");
      return;
    }
    const name = window.prompt("Saved View 이름", "새 Saved View")?.trim();
    if (!name) return;
    try {
      const view = await createSavedView({
        workspace_id: selectedWorkspaceId,
        name,
        active_tab_id: draftDashboard.active_tab_id,
        tabs: draftDashboard.tabs,
        parameter_state: draftDashboard.parameter_state,
      });
      setSavedViews((current) => [view, ...current]);
      setSelectedSavedViewId(view.id);
      setNotice(`Saved View '${view.name}'를 저장했습니다.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Saved View를 저장하지 못했습니다.");
    }
  }

  async function handleApplySavedView() {
    if (!selectedSavedViewId) return;
    try {
      const view = await getSavedView(selectedSavedViewId);
      updateDraft((current) => ({
        ...current,
        tabs: structuredClone(view.tabs),
        active_tab_id: view.active_tab_id,
        parameter_state: { ...current.parameter_state, ...view.parameter_state },
      }));
      const eventId = view.parameter_state.selected_event_id;
      if (typeof eventId === "string" && eventId) setSelectedEventId(eventId);
      setNotice(`Saved View '${view.name}'를 현재 세션에 적용했습니다. 저장 전까지 영구 반영되지 않습니다.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Saved View를 적용하지 못했습니다.");
    }
  }

  async function handleDeleteSavedView() {
    if (!selectedSavedViewId) return;
    try {
      await deleteSavedView(selectedSavedViewId);
      setSavedViews((current) => current.filter((view) => view.id !== selectedSavedViewId));
      setSelectedSavedViewId("");
      setNotice("Saved View를 삭제했습니다.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Saved View를 삭제하지 못했습니다.");
    }
  }

  async function handleShare() {
    if (!draftDashboard || draftDashboard.role_code !== appRole) {
      setError("다른 역할의 template preview는 공유할 수 없습니다.");
      return;
    }
    try {
      const share = await createDashboardShare({
        workspace_id: selectedWorkspaceId,
        active_tab_id: draftDashboard.active_tab_id,
        parameter_state: draftDashboard.parameter_state,
      });
      const url = `${window.location.origin}${share.path}`;
      try { await navigator.clipboard.writeText(url); } catch { /* clipboard may be unavailable */ }
      setNotice(`공유 링크를 생성했습니다: ${url}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "공유 링크를 생성하지 못했습니다.");
    }
  }

  async function handleExport(format: "json" | "csv" | "pdf") {
    setExporting(true);
    setError("");
    try {
      const artifact = await createExport({
        workspace_id: selectedWorkspaceId,
        scope: "dashboard",
        format,
        title: `${localizedRoleConfig.label} Dashboard Export`,
      });
      const url = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = artifact.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setNotice(`${format.toUpperCase()} export와 checkpoint ${artifact.checkpointId}를 생성했습니다.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Export를 생성하지 못했습니다.");
    } finally {
      setExporting(false);
    }
  }

  async function handleApplyPlannerDraft(draft: DashboardDraftResponse) {
    setError("");
    try {
      const [preview, catalog] = await Promise.all([
        getDashboardTemplatePreview(selectedWorkspaceId, draft.target_role),
        getBoardCatalog(selectedWorkspaceId, { role_code: draft.target_role }),
      ]);
      setTargetTemplateRole(draft.target_role);
      setDraftDashboard({
        ...preview,
        display_name: draft.display_name,
        tabs: draft.tabs,
        active_tab_id: draft.tabs[0]?.id ?? preview.active_tab_id,
        parameter_definitions: draft.parameter_definitions,
      });
      setCatalogItems(catalog);
      setCatalogTargetTabId(draft.tabs[0]?.id ?? preview.active_tab_id);
      setSelectedBoardId(null);
      setMode("edit");
      setDirty(true);
      setNotice(`${draft.target_role} Planner draft를 검토용 canvas에 적용했습니다. 아직 저장·게시되지 않았습니다.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Planner draft를 canvas에 적용하지 못했습니다.");
    }
  }

  async function handleTargetTemplateRoleChange(nextRole: AppRole) {
    setTargetTemplateRole(nextRole);
    setError("");
    try {
      const [preview, catalog] = await Promise.all([
        getDashboardTemplatePreview(selectedWorkspaceId, nextRole),
        getBoardCatalog(selectedWorkspaceId, { role_code: nextRole }),
      ]);
      setDraftDashboard(preview);
      setCatalogItems(catalog);
      setCatalogTargetTabId(preview.active_tab_id);
      setSelectedBoardId(null);
      setDirty(false);
      setNotice(`${nextRole} template preview를 편집 canvas에 불러왔습니다.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Template preview를 불러오지 못했습니다.");
    }
  }

  async function handlePublishTemplate() {
    if (!draftDashboard) return;
    if (draftDashboard.role_code !== targetTemplateRole) {
      setError("선택한 역할의 template preview를 먼저 불러오세요.");
      return;
    }
    const displayName = window.prompt(appRole === "fde" ? "승인 요청할 Template 이름" : "게시할 Template 이름", `${targetTemplateRole} Dashboard v${draftDashboard.template_version + 1}`)?.trim();
    if (!displayName) return;
    try {
      if (appRole === "fde") {
        const changeSummary = window.prompt("변경 요약", "고객 workflow와 역할별 board 구성을 반영했습니다.")?.trim();
        if (!changeSummary) return;
        await requestDashboardTemplatePublish(targetTemplateRole, {
          workspace_id: selectedWorkspaceId,
          target_role: targetTemplateRole,
          display_name: displayName,
          tabs: draftDashboard.tabs,
          parameter_definitions: draftDashboard.parameter_definitions,
          change_summary: changeSummary,
        });
        setDirty(false);
        setNotice(`${targetTemplateRole} template 변경을 관리자 승인 요청으로 제출했습니다.`);
        await loadRoleWorkspace(selectedWorkspaceId, selectedEventId);
      } else {
        await publishDashboardTemplate(targetTemplateRole, {
          workspace_id: selectedWorkspaceId,
          display_name: displayName,
          tabs: draftDashboard.tabs,
          parameter_definitions: draftDashboard.parameter_definitions,
        });
        setDirty(false);
        setNotice(`${targetTemplateRole} 역할 template의 새 version을 게시했습니다.`);
        await handleTargetTemplateRoleChange(targetTemplateRole);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Template을 게시하지 못했습니다.");
    }
  }

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  if (loading && !draftDashboard) {
    return <div className="route-loading"><WorkbenchState kind="loading" title="Resolving role Dashboard" detail="Merging governed template and personal preferences." /></div>;
  }

  const contextPanel = draftDashboard ? (
    <ContextPanel
      events={events}
      selectedEventId={selectedEventId}
      parameterState={draftDashboard.parameter_state}
      parameterDefinitions={draftDashboard.parameter_definitions}
      affectedCount={affectedBoards.length}
      savedViews={savedViews}
      selectedSavedViewId={selectedSavedViewId}
      activeSelectionCount={selectionFilters.length}
      dataConnection={{
        ...dataConnection,
        loading: dataConnection.loading || predictiveMaintenanceDashboardLoading,
        activeSource: predictiveMaintenanceDashboard?.data_source ?? null,
        fallbackReason: predictiveMaintenanceFallbackReason,
      }}
      onSelectEvent={(eventId) => handleSelectEvent("context-panel", eventId)}
      onOpenDatasets={() => navigate(datasetCatalogPath(selectedProjectId))}
      onClearSelections={() => setSelectionFilters((current) => clearSelectionFilters(current))}
      onParameterChange={handleParameterChange}
      onSelectSavedView={setSelectedSavedViewId}
      onApplySavedView={() => void handleApplySavedView()}
      onDeleteSavedView={() => void handleDeleteSavedView()}
    />
  ) : null;

  const boardCanvas = draftDashboard && evidence && report && layout ? (
    <>
      <PredictiveMaintenanceReplayPanel
        projectId={selectedProjectId}
        workspaceId={selectedWorkspaceId}
        appRole={appRole}
      />
      {detailLoading || roleWorkspaceLoading ? <div className="loading-panel"><WorkbenchState kind="refreshing" title={detailLoading ? "Refreshing object evidence" : "Refreshing role workspace"} /></div> : null}
      <BoardCanvas
        tab={activeTab}
        mode={mode}
        selectedBoardId={selectedBoardId}
        fullscreenBoardId={fullscreenBoardId}
        affectedBoardIds={affectedBoards}
        renderBoardHeader={(board) => {
          const definition = definitionById.get(board.definition_id);
          const visualizationCapable = definition?.renderer === "GenericDataBoard" || definition?.renderer === "AnalysisReference";
          if (!visualizationCapable) return null;
          const runtime = visualizationRuntimeByBoard[board.id];
          if (!runtime) return <span className="visualization-switcher-skeleton" role="status" aria-label="Visualization profile loading" />;
          return (
            <VisualizationSwitcher
              runtime={runtime}
              settings={visualizationSettings(board.settings.visualization)}
              onChange={(settings) => handleVisualizationChange(board.id, settings)}
              compact
            />
          );
        }}
        renderBoard={(board) => {
          const definition = definitionById.get(board.definition_id);
          if (!definition) return <div className="card"><p>Board definition을 찾을 수 없습니다: {board.definition_id}</p></div>;
          return (
            <BoardRuntimeSurface
              board={board}
              definition={definition}
              parameterState={draftDashboard.parameter_state}
              affected={affectedBoards.includes(board.id)}
            >
              <Suspense fallback={<div className="loading-panel"><WorkbenchState kind="loading" compact title="Loading board renderer" /></div>}>
                <DashboardBoardRenderer
              board={board}
              definition={definition}
              evidence={evidence}
              report={report}
              layout={layout}
              events={events}
              selectedEventId={selectedEventId}
              dashboardId={draftDashboard.dashboard_id}
              projectId={selectedProjectId}
              workspaceId={selectedWorkspaceId}
              appRole={appRole}
              role={role}
              canRecordDecision={canRecordDecision}
              canRecordNote={canRecordNote}
              parameterState={draftDashboard.parameter_state}
              selectionFilters={filtersForBoard(
                selectionFilters,
                board.id,
                draftDashboard.dependency_graph,
                definition.accepts,
              )}
              affectedCount={affectedBoards.length}
              roleWorkspaceData={roleWorkspaceData}
              onSelectEvent={handleSelectEvent}
              onSelectionFilter={handleSelectionFilter}
              onVisualizationRuntime={handleVisualizationRuntime}
              onAuditCheckpoint={handleAuditCheckpoint}
              onFieldAction={handleFieldAction}
              onApplyPlannerDraft={(draft) => void handleApplyPlannerDraft(draft)}
              onModelRelease={handleModelRelease}
              onDecision={handleDecision}
              onNote={handleNote}
              onAsk={handleAsk}
              lastFollowUp={lastFollowUp}
                />
              </Suspense>
            </BoardRuntimeSurface>
          );
        }}
        onSelectBoard={setSelectedBoardId}
        onLayoutChange={handleLayoutChange}
        onMoveBoard={handleMoveBoard}
        onDuplicateBoard={handleDuplicateBoard}
        onRemoveBoard={handleRemoveBoard}
        onToggleHidden={handleToggleHidden}
        onToggleFavorite={handleToggleFavorite}
        onContentMetricsChange={(metrics) => { boardContentMetricsRef.current = metrics; }}
        onEnterArrange={() => setMode("edit")}
        saving={saving}
        onFullscreen={setFullscreenBoardId}
      />
    </>
  ) : <div className="loading-panel"><WorkbenchState kind="loading" title="Preparing Dashboard boards" /></div>;

  const inspector = draftDashboard ? (
    <BoardInspector
      board={selectedBoard}
      definition={selectedDefinition}
      tabs={draftDashboard.tabs}
      currentTabId={selectedBoardTabId}
      visualizationRuntime={selectedBoardId ? visualizationRuntimeByBoard[selectedBoardId] ?? null : null}
      workspaceId={selectedWorkspaceId}
      dashboardId={draftDashboard.dashboard_id}
      onUpdate={handleUpdateBoard}
      onMove={(targetTabId) => selectedBoardId && handleMoveBoard(selectedBoardId, targetTabId)}
      onClose={() => setSelectedBoardId(null)}
    />
  ) : null;

  const catalog = catalogOpen && draftDashboard ? (
    <BoardCatalogPanel
      items={catalogItems}
      tabs={draftDashboard.tabs}
      targetTabId={catalogTargetTabId || draftDashboard.active_tab_id}
      search={catalogSearch}
      category={catalogCategory}
      onTargetTabChange={setCatalogTargetTabId}
      onSearchChange={setCatalogSearch}
      onCategoryChange={setCatalogCategory}
      onAddBoard={handleAddBoard}
      onCreateTab={handleAddTab}
      onClose={() => setCatalogOpen(false)}
    />
  ) : null;

  function confirmDashboardNavigation() {
    return !dirty || window.confirm("저장되지 않은 변경이 있습니다. 초안은 자동 저장되며 나중에 복구할 수 있습니다. 계속 이동할까요?");
  }

  const draftRecovery = recoveryCandidate ? (
    <section className="dashboard-draft-recovery" role="status">
      <div>
        <strong>저장되지 않은 Dashboard 초안이 있습니다</strong>
        <span>{new Date(recoveryCandidate.saved_at).toLocaleString()} · revision {recoveryCandidate.base_revision}</span>
      </div>
      <div className="button-row">
        <button type="button" className="primary" onClick={recoverDraft}>초안 복구</button>
        <button type="button" className="secondary" onClick={discardDraftRecovery}>폐기</button>
      </div>
    </section>
  ) : null;

  return (
    <DashboardShell
      user={authenticatedUser}
      roleLabel={localizedRoleConfig.label}
      roleEyebrow={roleConfig.eyebrow}
      roleDescription={localizedRoleConfig.description}
      roleFocus={localizedRoleConfig.focus}
      projects={projects}
      selectedProjectId={selectedProjectId}
      workspaces={workspaces}
      selectedWorkspaceId={selectedWorkspaceId}
      domainPack={selectedPack}
      adaptiveProfile={localizedAdaptiveProfile}
      tabs={draftDashboard?.tabs ?? []}
      activeTabId={draftDashboard?.active_tab_id ?? ""}
      templateVersion={draftDashboard?.template_version ?? 0}
      preferenceRevision={persistedDashboard?.preference_revision ?? 0}
      layoutMode={layout?.mode ?? null}
      mode={mode}
      dirty={dirty}
      saving={saving}
      exporting={exporting}
      layoutOptimizing={layoutOptimizing}
      notice={notice}
      error={error}
      canManageTemplates={canManageTemplates}
      templateActionLabel={appRole === "fde" ? "Template 승인 요청" : "Template 게시"}
      targetTemplateRole={targetTemplateRole}
      availableRoles={availableRoles}
      activeRole={appRole}
      contextPanel={contextPanel}
      boardCanvas={boardCanvas}
      reportWorkbench={(openDashboard) => (
        <RoleReportWorkbench
          workspaceId={selectedWorkspaceId}
          roleLabel={localizedRoleConfig.label}
          projectName={selectedProject?.display_name ?? selectedProjectId}
          profile={localizedAdaptiveProfile}
          report={report}
          evidence={evidence}
          events={events}
          selectedEventId={selectedEventId}
          canEdit={roleConfig.reportMode === "editor" && hasNotePermission}
          onSelectEvent={(eventId) => handleSelectEvent("role-report", eventId)}
          onOpenDashboard={openDashboard}
        />
      )}
      inspector={inspector}
      catalog={catalog}
      draftRecovery={draftRecovery}
      canUndo={undoStack.length > 0}
      canRedo={redoStack.length > 0}
      analysisWorkbench={(
        <Suspense fallback={<div className="loading-panel"><WorkbenchState kind="loading" title="Loading Analysis Workbench" /></div>}>
          <AnalysisWorkbench
            analysisId={analysisId}
            projectId={selectedProjectId}
            canMaterialize={authenticatedUser.permissions.includes("datasets.ingest")}
            events={events}
            selectedEventId={selectedEventId}
            evidence={evidence}
            workspaceId={selectedWorkspaceId}
            onSelectEvent={(eventId) => handleSelectEvent("analysis-path", eventId)}
            onAddToDashboard={handleAddAnalysisBoard}
          />
        </Suspense>
      )}
      initialWorkspaceView={effectiveInitialWorkspaceView}
      onWorkspaceViewChange={(view) => {
        const target = view === "analysis"
          ? analysisPath(analysisId)
          : selectedProjectId
            ? `/app/projects/${encodeURIComponent(selectedProjectId)}`
            : "/app";
        if (window.location.pathname !== target) window.history.pushState({}, "", target);
      }}
      onProjectChange={(projectId) => {
        if (!confirmDashboardNavigation()) return;
        setSelectedProjectId(projectId);
        setSelectedWorkspaceId("");
        setSelectedEventId("");
        setDraftDashboard(null);
        navigate(`/app/projects/${encodeURIComponent(projectId)}`, { replace: true });
      }}
      onWorkspaceChange={(workspaceId) => {
        if (!confirmDashboardNavigation()) return;
        setSelectedWorkspaceId(workspaceId);
        setSelectedEventId("");
        setDraftDashboard(null);
      }}
      onActiveTabChange={handleActiveTab}
      onReorderTabs={handleReorderTabs}
      onModeChange={setMode}
      onUndo={handleUndo}
      onRedo={handleRedo}
      onOpenCatalog={() => {
        setCatalogTargetTabId(draftDashboard?.active_tab_id ?? "");
        setCatalogOpen(true);
      }}
      onAddTab={handleAddTab}
      onAutoFitLayout={() => void handleOptimizeLayout("content-fit")}
      onAiOptimizeLayout={() => void handleOptimizeLayout("ai-recommendation")}
      onSave={() => void handleSave(false)}
      onRestore={() => void handleRestore()}
      onSaveView={() => void handleSaveView()}
      onShare={() => void handleShare()}
      onExport={(format) => void handleExport(format)}
      onPublishTemplate={() => void handlePublishTemplate()}
      onTargetTemplateRoleChange={(nextRole) => void handleTargetTemplateRoleChange(nextRole)}
      onActiveRoleChange={(nextRole) => {
        if (!confirmDashboardNavigation()) return;
        window.localStorage.setItem(roleStorageKey, nextRole);
        setAppRole(nextRole);
        setTargetTemplateRole(nextRole);
        setNotice(`${ROLE_LANDING[nextRole].label} 역할 관점으로 전환했습니다.`);
      }}
      onDismissNotice={() => setNotice("")}
      onRetry={() => {
        void loadDashboardFoundation(selectedWorkspaceId);
        void loadDetail(selectedEventId, intent);
      }}
      onAdmin={() => navigate("/admin")}
      onLogout={() => void handleLogout()}
    />
  );
}
