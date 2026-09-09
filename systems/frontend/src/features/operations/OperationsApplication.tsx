import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { navigate } from "../../routing";
import { getOpenInspectionWorkOrders } from "../../api";
import type {
  OperationsAsset,
  OperationsBootstrapModel,
  OperationsCompanyContext,
  OperationsDecision,
  OperationsEvent,
  OperationsEventDetailModel,
  OperationsReportTab,
  OperationsRoleLens,
  OperationsSensorWindowId,
  OperationsView,
} from "./api/operationsContracts";
import {
  loadOperationsBootstrap,
  loadOperationsCompanyContext,
  loadOperationsEventDetail,
  submitOperationsDecision,
  submitOperationsNote,
} from "./api/operationsApi";
import { OperationsState } from "./components/OperationsUi";
import { OperationsSelectionProvider, useOperationsSelection } from "./context/OperationsSelectionContext";
import { OperationsObjectsPage } from "./objects/OperationsObjectsPage";
import { OperationsOperationsPage } from "./operations/OperationsOperationsPage";
import { OperationsOverviewPage } from "./overview/OperationsOverviewPage";
import { OperationsReportsPage } from "./report/OperationsReportsPage";
import { OperationsShell } from "./shell/OperationsShell";
import { OperationsSystemAdminPage } from "./system/OperationsSystemAdminPage";
import {
  ReliabilityWorkspacePreview,
  ReliabilityWorkspaceLoadingPlaceholder,
  reliabilityWorkspacePreviewEnabled,
} from "../predictive-maintenance/ReliabilityWorkspacePreview";
import { resolveReliabilityRoleExperience } from "../predictive-maintenance/workspace/roleExperience";
import { RoleComposedWorkspace } from "../predictive-maintenance/workspace/RoleComposedWorkspace";
import type { ReliabilitySearchEntity } from "../predictive-maintenance/workspace/ReliabilityCommandPalette";
import {
  adaptiveReliabilityLandingSurface,
  defaultReliabilitySurface,
  reliabilitySurfaceForView,
  reliabilitySurfaces,
} from "../predictive-maintenance/workspace/roleSurfaces";
import {
  canMaterializeAgentReviewSummary,
  canReadOperationsSystemLogs,
} from "./permissions";
import "./operations.css";

const Operations_REFRESH_INTERVAL_SECONDS = 10;
const RELIABILITY_DETAIL_CACHE_LIMIT = 32;

const reliabilityEventDetailCache = new Map<string, OperationsEventDetailModel>();

function reliabilityDetailCacheKey(input: {
  projectId: string;
  workspaceId: string;
  datasetVersionId: string;
  eventId: string;
  sensorWindow: OperationsSensorWindowId;
  role: OperationsRoleLens;
  experienceKind: string;
}) {
  return [
    input.projectId,
    input.workspaceId,
    input.datasetVersionId,
    input.eventId,
    input.sensorWindow,
    input.role,
    input.experienceKind,
  ].join(":");
}

function storeReliabilityDetail(key: string, value: OperationsEventDetailModel) {
  reliabilityEventDetailCache.delete(key);
  reliabilityEventDetailCache.set(key, value);
  while (reliabilityEventDetailCache.size > RELIABILITY_DETAIL_CACHE_LIMIT) {
    const oldest = reliabilityEventDetailCache.keys().next().value;
    if (!oldest) break;
    reliabilityEventDetailCache.delete(oldest);
  }
}

function defaultRoleLens(roles: string[]): OperationsRoleLens {
  return roles.some((role) => role === "process_engineer" || role === "maintenance_technician")
    ? "field_operator"
    : "process_manager";
}

function isRestorableRuntimeEvent(event: OperationsEvent): boolean {
  return event.scenarioId === "runtime-product-result";
}

function latestRestorableEventForAsset(
  model: OperationsBootstrapModel,
  assetId: string | null | undefined,
): OperationsEvent | null {
  if (!assetId) return null;
  return model.events
    .filter((event) => event.assetId === assetId && isRestorableRuntimeEvent(event))
    .sort((left, right) => (right.observedAt ?? "").localeCompare(left.observedAt ?? ""))[0] ?? null;
}

function firstRestorableEvent(model: OperationsBootstrapModel): OperationsEvent | null {
  return model.events.find(isRestorableRuntimeEvent) ?? null;
}

export function OperationsApplication({ projectId, backupMode = false }: { projectId: string; backupMode?: boolean }) {
  const { user } = useAuth();
  const roles = user?.active_project_roles.length ? user.active_project_roles : user?.roles ?? [];
  const role = defaultRoleLens(roles);
  const experience = user ? resolveReliabilityRoleExperience(user) : null;
  const defaultSurface = experience ? defaultReliabilitySurface(experience.kind, backupMode) : null;
  const defaultView = defaultSurface?.view ?? experience?.defaultView ?? "overview";
  const defaultReportTab: OperationsReportTab = experience?.kind === "executive" ? "executive-brief" : "status-map";
  return (
    <OperationsSelectionProvider
      projectId={projectId}
      defaultRole={role}
      defaultView={defaultView}
      defaultSurface={defaultSurface?.id ?? null}
      defaultReportTab={defaultReportTab}
      storageScope={`${user?.user_id ?? "anonymous"}${backupMode ? ":backup-v1" : ""}`}
      navigationBasePath={backupMode ? "/backup" : null}
    >
      <OperationsApplicationController projectId={projectId} backupMode={backupMode} />
    </OperationsSelectionProvider>
  );
}
export default OperationsApplication;

function OperationsApplicationController({ projectId, backupMode }: { projectId: string; backupMode: boolean }) {
  const { user, logout } = useAuth();
  const { selection, updateSelection } = useOperationsSelection();
  const authorizedRole = defaultRoleLens(
    user?.active_project_roles.length ? user.active_project_roles : user?.roles ?? [],
  );
  const [model, setModel] = useState<OperationsBootstrapModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [detail, setDetail] = useState<OperationsEventDetailModel | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailVersion, setDetailVersion] = useState(0);
  const [sensorWindow, setSensorWindow] = useState<OperationsSensorWindowId>("24h");
  const [companyContext, setCompanyContext] = useState<OperationsCompanyContext | null>(null);
  const [companyContextError, setCompanyContextError] = useState<string | null>(null);
  const adaptiveLandingResolvedRef = useRef(false);
  const selectionRef = useRef(selection);
  selectionRef.current = selection;
  const experienceKind = user
    ? resolveReliabilityRoleExperience(user).kind
    : authorizedRole === "field_operator"
      ? "engineering"
      : "operations";

  useEffect(() => {
    // URL query parameters are navigation hints, not authority. A copied
    // manager URL must never force an engineer into the manager workflow lens.
    if (!user || selection.role === authorizedRole) return;
    updateSelection({ role: authorizedRole }, { replace: true });
  }, [authorizedRole, selection.role, updateSelection, user]);

  useEffect(() => {
    const surfaces = reliabilitySurfaces(experienceKind, backupMode);
    const currentSurface = selection.surface
      ? surfaces.find((item) => item.id === selection.surface) ?? null
      : null;
    if (currentSurface) {
      // A saved/copied URL may contain a stale legacy `view` alongside a
      // valid role surface. Surface identity owns the workspace composition,
      // so keep the view in sync with that surface instead of rendering the
      // right navigation label with the wrong data-selection behavior.
      if (selection.view !== currentSurface.view) {
        updateSelection({ view: currentSurface.view }, { replace: true });
      }
      return;
    }
    const next = defaultReliabilitySurface(experienceKind, backupMode);
    updateSelection({ surface: next.id, view: next.view }, { replace: true });
  }, [backupMode, experienceKind, selection.surface, selection.view, updateSelection]);

  const refresh = useCallback(() => setRefreshVersion((value) => value + 1), []);
  const retryDetail = useCallback(() => {
    reliabilityEventDetailCache.clear();
    setDetailVersion((value) => value + 1);
  }, []);
  const workflowChanged = useCallback(() => {
    reliabilityEventDetailCache.clear();
    setDetailVersion((value) => value + 1);
    setRefreshVersion((value) => value + 1);
  }, []);
  const signOut = useCallback(async () => {
    await logout();
    navigate("/login", { replace: true });
  }, [logout]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setRefreshVersion((value) => value + 1);
    }, Operations_REFRESH_INTERVAL_SECONDS * 1_000);
    return () => window.clearInterval(timer);
  }, [projectId, selection.workspaceId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    loadOperationsBootstrap(projectId, selection.workspaceId, selection.eventId)
      .then((payload) => {
        if (cancelled) return;
        setModel(payload);
        const selectedEvent = payload.events.find((item) => item.eventId === selection.eventId) ?? null;
        const selectedAsset = payload.assets.find((item) => item.assetId === selection.assetId) ?? null;
        const patch: Parameters<typeof updateSelection>[0] = {};
        if (!selection.workspaceId) patch.workspaceId = payload.context.workspaceId;
        // An explicit Event selection is a frozen Decision Case snapshot.
        // Never replace it with the asset's newest Event during refresh.
        if (!selection.eventId && selectedAsset) {
          patch.eventId = latestRestorableEventForAsset(payload, selectedAsset.assetId)?.eventId ?? null;
        }
        if (!selection.assetId && selectedEvent) patch.assetId = selectedEvent.assetId;
        if (Object.keys(patch).length) updateSelection(patch, { replace: true });

        // The fleet workspace is usable as soon as bootstrap data arrives.
        // Resolve the most relevant active workflow afterwards so an auxiliary
        // work-order request never blocks the first render.
        void getOpenInspectionWorkOrders(projectId, payload.context.workspaceId)
          .catch(() => ({ items: [] }))
          .then((openWorkOrders) => {
            if (cancelled) return;
            const current = selectionRef.current;
            if (current.assetId || current.eventId) return;
            if (current.view !== "operations" && current.view !== "reports") return;
            const fallbackEvent = firstRestorableEvent(payload);
            const stepPriority: Record<string, number> = {
              maintenance_in_progress: 0,
              inspection_in_progress: 1,
              inspection_approved: 2,
              inspection_requested: 3,
              inspection_completed: 4,
              recommendation_proposed: 5,
              maintenance_requested: 6,
              maintenance_approved: 7,
              post_maintenance_observation_pending: 8,
              ready_for_reprediction: 9,
            };
            const activeWorkflow = [...openWorkOrders.items]
              .sort((left, right) => (
                (stepPriority[left.current_step ?? ""] ?? 99)
                - (stepPriority[right.current_step ?? ""] ?? 99)
              ))[0] ?? null;
            const activeEvent = activeWorkflow
              ? latestRestorableEventForAsset(payload, activeWorkflow.asset_id)
              : null;
            const nextEvent = activeWorkflow ? activeEvent : fallbackEvent;
            const nextAssetId = activeWorkflow?.asset_id ?? nextEvent?.assetId ?? null;
            if (!nextAssetId && !nextEvent) return;
            updateSelection({
              eventId: nextEvent?.eventId ?? null,
              assetId: nextAssetId,
            }, { replace: true });
          });
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "운영 데이터를 불러오지 못했습니다.");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [projectId, refreshVersion, selection.eventId, selection.workspaceId]);

  const selectedEvent = useMemo(() => {
    return model?.events.find((item) => item.eventId === selection.eventId) ?? null;
  }, [model, selection.eventId]);

  const selectedSnapshotUnavailable = Boolean(
    selection.eventId
    && model
    && (model.selectionRestoreError || !selectedEvent),
  );

  const latestEventForSelectedAsset = useMemo(() => {
    if (!model) return null;
    const assetId = selectedEvent?.assetId ?? selection.assetId;
    if (!assetId) return null;
    const latest = latestRestorableEventForAsset(model, assetId);
    if (!latest) return null;
    if (selectedEvent && latest.eventId === selectedEvent.eventId) return null;
    if (!selectedEvent) return latest;
    if (!latest?.observedAt || !selectedEvent.observedAt) return latest;
    return Date.parse(latest.observedAt) > Date.parse(selectedEvent.observedAt) ? latest : null;
  }, [model, selectedEvent, selection.assetId]);

  useEffect(() => {
    if (!model || adaptiveLandingResolvedRef.current || backupMode) return;
    adaptiveLandingResolvedRef.current = true;
    const defaultSurface = defaultReliabilitySurface(experienceKind, backupMode);
    if (selection.surface !== defaultSurface.id || selection.eventId || selection.assetId) return;
    const adaptiveSurface = adaptiveReliabilityLandingSurface(experienceKind, model.metrics, backupMode);
    if (adaptiveSurface.id !== selection.surface) {
      updateSelection({ surface: adaptiveSurface.id, view: adaptiveSurface.view }, { replace: true });
    }
  }, [backupMode, experienceKind, model, selection.assetId, selection.eventId, selection.surface, updateSelection]);

  useEffect(() => {
    const workspaceId = model?.context.workspaceId;
    if (!workspaceId) return;
    let cancelled = false;
    setCompanyContextError(null);
    loadOperationsCompanyContext(projectId, workspaceId)
      .then((payload) => {
        if (!cancelled) setCompanyContext(payload);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setCompanyContextError(reason instanceof Error ? reason.message : "회사 운영 문맥을 불러오지 못했습니다.");
      });
    return () => { cancelled = true; };
  }, [model?.context.workspaceId, projectId]);

  useEffect(() => {
    if (!model || !selectedEvent || selectedSnapshotUnavailable) {
      setDetail(null);
      setDetailError(null);
      setDetailLoading(false);
      return;
    }
    let cancelled = false;
    const cacheKey = reliabilityDetailCacheKey({
      projectId,
      workspaceId: model.context.workspaceId,
      datasetVersionId: model.context.datasetVersionId,
      eventId: selectedEvent.eventId,
      sensorWindow,
      role: authorizedRole,
      experienceKind,
    });
    const cached = reliabilityEventDetailCache.get(cacheKey);
    if (cached) {
      setDetail(cached);
      setDetailError(null);
      setDetailLoading(false);
      return () => { cancelled = true; };
    }
    setDetailLoading(true);
    setDetailError(null);
    loadOperationsEventDetail({
      projectId,
      workspaceId: model.context.workspaceId,
      datasetVersionId: model.context.datasetVersionId,
      event: selectedEvent,
      role: authorizedRole,
      reportRole: experienceKind === "executive" ? "executive" : experienceKind === "engineering" ? "engineer" : "manager",
      reportType: experienceKind === "executive" ? "executive-brief" : experienceKind === "engineering" ? "inspection-summary" : "operations-decision",
      historyWindow: sensorWindow,
      metrics: model.metrics,
    })
      .then((payload) => {
        if (cancelled) return;
        storeReliabilityDetail(cacheKey, payload);
        setDetail(payload);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setDetail(null);
        setDetailError(reason instanceof Error ? reason.message : "선택 Event 상세를 불러오지 못했습니다.");
      })
      .finally(() => !cancelled && setDetailLoading(false));
    return () => { cancelled = true; };
  }, [authorizedRole, detailVersion, experienceKind, model?.context.datasetVersionId, model?.context.workspaceId, projectId, selectedEvent?.eventId, selectedSnapshotUnavailable, sensorWindow]);

  const openView = useCallback((view: OperationsView) => {
    const surface = reliabilitySurfaceForView(experienceKind, view, backupMode);
    const patch: Parameters<typeof updateSelection>[0] = { view, surface: surface.id };
    if ((view === "operations" || view === "reports") && !selection.eventId && model) {
      const fallbackEvent = selection.assetId
        ? latestRestorableEventForAsset(model, selection.assetId)
        : firstRestorableEvent(model);
      patch.eventId = fallbackEvent?.eventId ?? null;
      if (!selection.assetId && fallbackEvent) patch.assetId = fallbackEvent.assetId;
    }
    updateSelection(patch);
  }, [backupMode, experienceKind, model, selection.assetId, selection.eventId, updateSelection]);

  const openSurface = useCallback((surfaceId: string, view: OperationsView) => {
    const patch: Parameters<typeof updateSelection>[0] = { surface: surfaceId, view };
    if ((view === "operations" || view === "reports") && !selection.eventId && model) {
      const fallbackEvent = selection.assetId
        ? latestRestorableEventForAsset(model, selection.assetId)
        : firstRestorableEvent(model);
      patch.eventId = fallbackEvent?.eventId ?? null;
      if (!selection.assetId && fallbackEvent) patch.assetId = fallbackEvent.assetId;
    }
    updateSelection(patch);
  }, [model, selection.assetId, selection.eventId, updateSelection]);

  const openAsset = useCallback((assetId: string, eventId: string | null) => {
    updateSelection({ view: "objects", surface: reliabilitySurfaceForView(experienceKind, "objects", backupMode).id, assetId, eventId });
  }, [backupMode, experienceKind, updateSelection]);

  const openEvent = useCallback((eventId: string, assetId: string) => {
    updateSelection({ view: "operations", surface: reliabilitySurfaceForView(experienceKind, "operations", backupMode).id, eventId, assetId });
  }, [backupMode, experienceKind, updateSelection]);

  const openReport = useCallback((eventId: string | null, assetId: string | null, reportTab: OperationsReportTab = "executive-brief") => {
    const fallback = model
      ? assetId
        ? latestRestorableEventForAsset(model, assetId)
        : firstRestorableEvent(model)
      : null;
    const requestedEvent = eventId && model
      ? model.events.find((event) => event.eventId === eventId && isRestorableRuntimeEvent(event)) ?? null
      : null;
    updateSelection({
      view: "reports",
      surface: reliabilitySurfaceForView(experienceKind, "reports", backupMode).id,
      reportTab,
      eventId: requestedEvent?.eventId ?? fallback?.eventId ?? null,
      assetId: assetId ?? requestedEvent?.assetId ?? fallback?.assetId ?? null,
    });
  }, [backupMode, experienceKind, model, updateSelection]);

  const previewAsset = useCallback((assetId: string, eventId: string | null) => {
    const requestedEvent = eventId && model
      ? model.events.find((event) => event.eventId === eventId && isRestorableRuntimeEvent(event)) ?? null
      : null;
    const restorableEvent = requestedEvent ?? (model ? latestRestorableEventForAsset(model, assetId) : null);
    updateSelection({ assetId, eventId: restorableEvent?.eventId ?? null });
  }, [model, updateSelection]);

  const selectAsset = useCallback((asset: OperationsAsset) => {
    const event = model ? latestRestorableEventForAsset(model, asset.assetId) : null;
    updateSelection({ assetId: asset.assetId, eventId: event?.eventId ?? null });
  }, [model, updateSelection]);

  const openAssetOperations = useCallback((asset: OperationsAsset) => {
    const event = model ? latestRestorableEventForAsset(model, asset.assetId) : null;
    updateSelection({ view: "operations", assetId: asset.assetId, eventId: event?.eventId ?? null });
  }, [model, updateSelection]);

  const openAssetReport = useCallback((asset: OperationsAsset) => {
    const event = model ? latestRestorableEventForAsset(model, asset.assetId) : null;
    updateSelection({ view: "reports", reportTab: "executive-brief", assetId: asset.assetId, eventId: event?.eventId ?? null });
  }, [model, updateSelection]);

  const selectEvent = useCallback((event: OperationsEvent) => {
    updateSelection({ eventId: event.eventId, assetId: event.assetId });
  }, [updateSelection]);

  const followLatestEvent = useCallback(() => {
    if (!latestEventForSelectedAsset) return;
    updateSelection({ eventId: latestEventForSelectedAsset.eventId, assetId: latestEventForSelectedAsset.assetId });
  }, [latestEventForSelectedAsset, updateSelection]);

  const searchEntities = useMemo<ReliabilitySearchEntity[]>(() => {
    if (!model) return [];
    const eventAssetIds = new Set(model.events.map((event) => event.assetId));
    const eventItems: ReliabilitySearchEntity[] = model.events.map((event) => ({
      id: `event:${event.eventId}`,
      kind: "event",
      label: event.assetName || event.assetId,
      detail: `${event.eventId} · ${event.line} · ${event.failureProbability !== null ? `${Math.round(event.failureProbability * 100)}% risk` : "risk n/a"}`,
      assetId: event.assetId,
      eventId: event.eventId,
      keywords: `${event.status} ${event.predictedFailureType ?? ""} ${event.recommendedDecision}`,
    }));
    const assetItems: ReliabilitySearchEntity[] = model.assets
      .filter((asset) => !eventAssetIds.has(asset.assetId))
      .map((asset) => ({
        id: `asset:${asset.assetId}`,
        kind: "asset",
        label: asset.displayName,
        detail: `${asset.assetId} · ${asset.line} · ${asset.failureProbability !== null ? `${Math.round(asset.failureProbability * 100)}% risk` : "risk n/a"}`,
        assetId: asset.assetId,
        eventId: asset.eventId,
        keywords: `${asset.status} ${asset.assetType}`,
      }));
    return [...eventItems, ...assetItems];
  }, [model]);

  const selectSearchEntity = useCallback((entity: ReliabilitySearchEntity) => {
    const preferredSurfaceId = experienceKind === "engineering"
      ? "assets"
      : experienceKind === "operations"
        ? entity.eventId ? "decision-case" : "factory-status"
        : experienceKind === "executive"
          ? "factory-status"
          : entity.eventId ? "work-targets" : "field-status";
    const targetSurface = reliabilitySurfaces(experienceKind, backupMode).find((item) => item.id === preferredSurfaceId)
      ?? defaultReliabilitySurface(experienceKind, backupMode);
    updateSelection({
      surface: targetSurface.id,
      view: targetSurface.view,
      assetId: entity.assetId,
      eventId: entity.eventId,
    });
  }, [backupMode, experienceKind, updateSelection]);

  const openEventAsset = useCallback((event: OperationsEvent) => {
    updateSelection({ view: "objects", eventId: event.eventId, assetId: event.assetId });
  }, [updateSelection]);

  const openEventReport = useCallback((event: OperationsEvent) => {
    updateSelection({ view: "reports", reportTab: "executive-brief", eventId: event.eventId, assetId: event.assetId });
  }, [updateSelection]);

  const selectReportTab = useCallback((reportTab: OperationsReportTab) => {
    const patch: Parameters<typeof updateSelection>[0] = { view: "reports", reportTab };
    if (!selection.eventId && model?.events[0]) {
      patch.eventId = model.events[0].eventId;
      patch.assetId = model.events[0].assetId;
    }
    updateSelection(patch);
  }, [model?.events, selection.eventId, updateSelection]);

  const submitDecision = useCallback(async (decision: OperationsDecision, note: string) => {
    if (!selectedEvent || !user) throw new Error("저장할 Event 또는 사용자 문맥이 없습니다.");
    const workspaceId = model?.context.workspaceId ?? selection.workspaceId;
    if (!workspaceId) throw new Error("작업요청을 생성할 Workspace 문맥이 없습니다.");
    await submitOperationsDecision({
      projectId,
      workspaceId,
      eventId: selectedEvent.eventId,
      userId: user.user_id,
      actor: user.display_name,
      decision,
      note,
      snapshotBasis: detail?.event.eventId === selectedEvent.eventId ? detail.snapshotBasis : null,
    });
    retryDetail();
    refresh();
  }, [detail, model?.context.workspaceId, projectId, refresh, retryDetail, selectedEvent, selection.workspaceId, user]);

  const submitNote = useCallback(async (body: string) => {
    if (!selectedEvent || !user) throw new Error("저장할 Event 또는 사용자 문맥이 없습니다.");
    await submitOperationsNote({ eventId: selectedEvent.eventId, actor: user.display_name, body });
    retryDetail();
  }, [retryDetail, selectedEvent, user]);

  const useReliabilityPreview = backupMode || reliabilityWorkspacePreviewEnabled();

  if (loading && !model) return useReliabilityPreview
    ? <ReliabilityWorkspaceLoadingPlaceholder />
    : <div className="operations-route-state"><OperationsState kind="loading" title="예지보전 화면 구성 중" detail="Project, Workspace, 설비 판단 데이터를 연결하고 있습니다." /></div>;
  if (error && !model) return <div className="operations-route-state"><OperationsState kind="error" title="예지보전 화면을 열지 못했습니다" detail={error} onRetry={refresh} /></div>;
  if (!model) return <div className="operations-route-state"><OperationsState kind="empty" title="표시할 운영 데이터가 없습니다" detail="Project와 Workspace 연결 상태를 확인하세요." /></div>;

  const canDecide = Boolean(user?.permissions.includes("events.decision"));
  const canNote = Boolean(user?.permissions.includes("events.note"));
  const canExecuteFieldWorkflow = Boolean(user?.permissions.includes("field.tasks.update"));
  const canMaterializeAgentSummary = canMaterializeAgentReviewSummary(user?.permissions);
  const canReadSystemLogs = canReadOperationsSystemLogs(user?.permissions);
  const selectedAssetId = selection.assetId;
  let content;
  if (
    useReliabilityPreview
    && selectedSnapshotUnavailable
    && selection.surface !== "factory-status"
    && selection.view !== "system"
  ) {
    content = <div className="operations-route-state"><OperationsState
      kind="empty"
      title="선택 Case 본문을 표시하지 않습니다"
      detail="immutable Result Artifact를 복원하기 전에는 Evidence, Action, Outcome, Report 본문을 표시하지 않습니다. 설비 현황에서 새 Case를 선택하거나 현재 설비의 최신 Case로 이동하세요."
    /></div>;
  } else if (useReliabilityPreview && !backupMode && selection.surface === "factory-status") {
    content = <OperationsOverviewPage model={model} role={authorizedRole} currentUserId={user?.user_id ?? ""} experienceKind={experienceKind} dashboard={selection.dashboard} selectedAssetId={selection.assetId} detail={detail} detailLoading={detailLoading} detailError={detailError} sensorWindow={sensorWindow} canMaterializeAgentSummary={canMaterializeAgentSummary} canManageWorkflow={canDecide} canExecuteFieldWorkflow={canExecuteFieldWorkflow} onSensorWindowChange={setSensorWindow} onOpenAsset={openAsset} onPreviewAsset={previewAsset} onOpenEvent={openEvent} onOpenReport={openReport} onRefresh={refresh} />;
  } else if (useReliabilityPreview && selection.view !== "system") {
    content = <RoleComposedWorkspace
      experienceKind={experienceKind}
      view={selection.view}
      surfaceId={selection.surface}
      model={model}
      selectedEvent={selectedEvent}
      detail={detail}
      detailLoading={detailLoading}
      companyContext={companyContext}
      role={authorizedRole}
      currentUserId={user?.user_id ?? ""}
      canManageWorkflow={canDecide}
      canExecuteFieldWorkflow={canExecuteFieldWorkflow}
      canMaterializeAgentSummary={canMaterializeAgentSummary}
      onSelectEvent={selectEvent}
      onOpenAsset={openAsset}
      onOpenReport={openReport}
      onWorkflowChanged={workflowChanged}
    />;
  } else if (selection.view === "objects") {
    content = <OperationsObjectsPage model={model} selectedAssetId={selectedAssetId} detail={detail} detailLoading={detailLoading} detailError={detailError} onSelectAsset={selectAsset} onOpenOperations={openAssetOperations} onOpenReport={openAssetReport} onRetryDetail={retryDetail} />;
  } else if (selection.view === "operations") {
    content = <OperationsOperationsPage model={model} selectedEventId={selection.eventId} detail={detail} detailLoading={detailLoading} detailError={detailError} canDecide={canDecide} canNote={canNote} onSelectEvent={selectEvent} onOpenAsset={openEventAsset} onOpenReport={openEventReport} onDecision={submitDecision} onNote={submitNote} onRetryDetail={retryDetail} />;
  } else if (selection.view === "reports") {
    content = <OperationsReportsPage activeTab={selection.reportTab} model={model} selectedEvent={selectedEvent} detail={detail} detailLoading={detailLoading} detailError={detailError} canMaterializeAgentSummary={canMaterializeAgentSummary} experienceKind={experienceKind} userScope={user?.user_id ?? "anonymous"} onSelectTab={selectReportTab} onSelectEvent={selectEvent} onBackToOverview={() => openView("overview")} onOpenOperations={(event) => openEvent(event.eventId, event.assetId)} onRetryDetail={retryDetail} />;
  } else if (selection.view === "system") {
    content = canReadSystemLogs
      ? <OperationsSystemAdminPage model={model} refreshing={loading} onRefresh={refresh} />
      : <OperationsState kind="error" title="시스템 관리자 권한 필요" detail="AI 요약 처리 로그는 관리자 감사 권한이 있는 사용자만 조회할 수 있습니다." />;
  } else {
    content = <OperationsOverviewPage model={model} role={authorizedRole} currentUserId={user?.user_id ?? ""} experienceKind={experienceKind} dashboard={selection.dashboard} selectedAssetId={selection.assetId} detail={detail} detailLoading={detailLoading} detailError={detailError} sensorWindow={sensorWindow} canMaterializeAgentSummary={canMaterializeAgentSummary} canManageWorkflow={canDecide} canExecuteFieldWorkflow={canExecuteFieldWorkflow} onSensorWindowChange={setSensorWindow} onOpenAsset={openAsset} onPreviewAsset={previewAsset} onOpenEvent={openEvent} onOpenReport={openReport} onRefresh={refresh} />;
  }

  const body = <>
    {error ? <div className="operations-inline-warning" role="alert"><strong>새로고침 실패</strong><span>{error}</span></div> : null}
    {selectedSnapshotUnavailable ? (
      <div className="operations-inline-warning is-selection-restore-warning" role="status">
        <strong>선택 Case를 다시 확인해 주세요</strong>
        <span>
          URL의 기존 Decision Case {selection.eventId}를 현재 immutable Result Artifact에서 찾지 못했습니다.
          최신 Event로 자동 대체하지는 않으며, 복원되지 않은 Case의 Evidence·Action·Report 본문도 표시하지 않습니다.
        </span>
        {latestEventForSelectedAsset ? (
          <button type="button" onClick={followLatestEvent}>현재 설비 최신 Case 보기</button>
        ) : null}
      </div>
    ) : null}
    {detailError && useReliabilityPreview ? <div className="operations-inline-warning" role="alert"><strong>상세 근거 조회 지연</strong><span>{detailError}</span></div> : null}
    {companyContextError && useReliabilityPreview ? <div className="operations-inline-warning" role="alert"><strong>회사 문맥 조회 지연</strong><span>{companyContextError}</span></div> : null}
    {detailLoading && useReliabilityPreview ? <div className="rw-composed-detail-loading">선택 설비 근거를 최신 상태로 동기화하고 있습니다.</div> : null}
    {content}
  </>;

  if (useReliabilityPreview && user) {
    return (
      <ReliabilityWorkspacePreview
        model={model}
        context={model.context}
        activeView={selection.view}
        activeSurface={selection.surface}
        user={user}
        selectedEvent={selectedEvent}
        latestEventForSelectedAsset={latestEventForSelectedAsset}
        detail={detail}
        onSelectEvent={selectEvent}
        onNavigate={openSurface}
        onRefresh={refresh}
        refreshing={loading}
        onLogout={signOut}
        searchEntities={searchEntities}
        onSearchSelect={selectSearchEntity}
        onFollowLatestEvent={followLatestEvent}
        backupMode={backupMode}
      >
        {body}
      </ReliabilityWorkspacePreview>
    );
  }

  return <OperationsShell
    context={model.context}
    activeView={selection.view}
    dashboard={selection.dashboard}
    role={authorizedRole}
    onNavigate={openView}
    onRoleChange={(role: OperationsRoleLens) => updateSelection({ role, view: "overview" })}
    onRefresh={refresh}
    refreshing={loading}
    refreshIntervalSeconds={Operations_REFRESH_INTERVAL_SECONDS}
    canReadSystemLogs={canReadSystemLogs}
    onLogout={signOut}
  >{body}</OperationsShell>;
}
