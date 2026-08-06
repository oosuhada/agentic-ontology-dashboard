import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import type {
  MvpAsset,
  MvpBootstrapModel,
  MvpDecision,
  MvpEvent,
  MvpEventDetailModel,
  MvpRoleLens,
  MvpView,
} from "./api/mvpContracts";
import {
  loadMvpBootstrap,
  loadMvpEventDetail,
  submitMvpDecision,
  submitMvpNote,
} from "./api/mvpApi";
import { MvpState } from "./components/MvpUi";
import { MvpSelectionProvider, useMvpSelection } from "./context/MvpSelectionContext";
import { MvpObjectsPage } from "./objects/MvpObjectsPage";
import { MvpOperationsPage } from "./operations/MvpOperationsPage";
import { MvpOverviewPage } from "./overview/MvpOverviewPage";
import { MvpExecutiveReportPage } from "./report/MvpExecutiveReportPage";
import { MvpShell } from "./shell/MvpShell";
import "./mvp.css";

function defaultRoleLens(roles: string[]): MvpRoleLens {
  return roles.some((role) => role === "process_engineer" || role === "maintenance_technician")
    ? "field_operator"
    : "process_manager";
}

export function MvpApplication({ projectId }: { projectId: string }) {
  const { user } = useAuth();
  const role = defaultRoleLens(user?.active_project_roles.length ? user.active_project_roles : user?.roles ?? []);
  return (
    <MvpSelectionProvider projectId={projectId} defaultRole={role}>
      <MvpApplicationController projectId={projectId} />
    </MvpSelectionProvider>
  );
}
export default MvpApplication;

function MvpApplicationController({ projectId }: { projectId: string }) {
  const { user } = useAuth();
  const { selection, updateSelection } = useMvpSelection();
  const [model, setModel] = useState<MvpBootstrapModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [detail, setDetail] = useState<MvpEventDetailModel | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailVersion, setDetailVersion] = useState(0);

  const refresh = useCallback(() => setRefreshVersion((value) => value + 1), []);
  const retryDetail = useCallback(() => setDetailVersion((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    loadMvpBootstrap(projectId, selection.workspaceId, selection.eventId)
      .then((payload) => {
        if (cancelled) return;
        setModel(payload);
        const selectedEvent = payload.events.find((item) => item.eventId === selection.eventId) ?? null;
        const selectedAsset = payload.assets.find((item) => item.assetId === selection.assetId) ?? null;
        const patch: Parameters<typeof updateSelection>[0] = {};
        if (!selection.workspaceId) patch.workspaceId = payload.context.workspaceId;
        if (!selection.eventId && selectedAsset?.eventId) patch.eventId = selectedAsset.eventId;
        if (!selection.assetId && selectedEvent) patch.assetId = selectedEvent.assetId;
        if (!selection.assetId && !selection.eventId && payload.events[0]) {
          patch.eventId = payload.events[0].eventId;
          patch.assetId = payload.events[0].assetId;
        }
        if (Object.keys(patch).length) updateSelection(patch, { replace: true });
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "MVP 데이터를 불러오지 못했습니다.");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [projectId, refreshVersion, selection.workspaceId]);

  const selectedEvent = useMemo(
    () => model?.events.find((item) => item.eventId === selection.eventId) ?? null,
    [model, selection.eventId],
  );

  useEffect(() => {
    if (!model || !selectedEvent) {
      setDetail(null);
      setDetailError(null);
      setDetailLoading(false);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    loadMvpEventDetail({
      projectId,
      workspaceId: model.context.workspaceId,
      datasetVersionId: model.context.datasetVersionId,
      event: selectedEvent,
      role: selection.role,
      metrics: model.metrics,
    })
      .then((payload) => !cancelled && setDetail(payload))
      .catch((reason: unknown) => {
        if (cancelled) return;
        setDetail(null);
        setDetailError(reason instanceof Error ? reason.message : "선택 Event 상세를 불러오지 못했습니다.");
      })
      .finally(() => !cancelled && setDetailLoading(false));
    return () => { cancelled = true; };
  }, [detailVersion, model?.context.datasetVersionId, model?.context.workspaceId, projectId, selectedEvent?.eventId, selection.role]);

  const openView = useCallback((view: MvpView) => {
    const patch: Parameters<typeof updateSelection>[0] = { view };
    if ((view === "operations" || view === "executive-report") && !selection.eventId && model?.events[0]) {
      patch.eventId = model.events[0].eventId;
      patch.assetId = model.events[0].assetId;
    }
    updateSelection(patch);
  }, [model?.events, selection.eventId, updateSelection]);

  const openAsset = useCallback((assetId: string, eventId: string | null) => {
    updateSelection({ view: "objects", assetId, eventId });
  }, [updateSelection]);

  const openEvent = useCallback((eventId: string, assetId: string) => {
    updateSelection({ view: "operations", eventId, assetId });
  }, [updateSelection]);

  const openReport = useCallback((eventId: string | null, assetId: string | null) => {
    const fallback = model?.events[0] ?? null;
    updateSelection({
      view: "executive-report",
      eventId: eventId ?? fallback?.eventId ?? null,
      assetId: assetId ?? fallback?.assetId ?? null,
    });
  }, [model?.events, updateSelection]);

  const selectAsset = useCallback((asset: MvpAsset) => {
    updateSelection({ assetId: asset.assetId, eventId: asset.eventId });
  }, [updateSelection]);

  const openAssetOperations = useCallback((asset: MvpAsset) => {
    if (!asset.eventId) return;
    updateSelection({ view: "operations", assetId: asset.assetId, eventId: asset.eventId });
  }, [updateSelection]);

  const selectEvent = useCallback((event: MvpEvent) => {
    updateSelection({ eventId: event.eventId, assetId: event.assetId });
  }, [updateSelection]);

  const openEventAsset = useCallback((event: MvpEvent) => {
    updateSelection({ view: "objects", eventId: event.eventId, assetId: event.assetId });
  }, [updateSelection]);

  const openEventReport = useCallback((event: MvpEvent) => {
    updateSelection({ view: "executive-report", eventId: event.eventId, assetId: event.assetId });
  }, [updateSelection]);

  const submitDecision = useCallback(async (decision: MvpDecision, note: string) => {
    if (!selectedEvent || !user) throw new Error("저장할 Event 또는 사용자 문맥이 없습니다.");
    await submitMvpDecision({ eventId: selectedEvent.eventId, actor: user.display_name, decision, note });
    retryDetail();
  }, [retryDetail, selectedEvent, user]);

  const submitNote = useCallback(async (body: string) => {
    if (!selectedEvent || !user) throw new Error("저장할 Event 또는 사용자 문맥이 없습니다.");
    await submitMvpNote({ eventId: selectedEvent.eventId, actor: user.display_name, body });
    retryDetail();
  }, [retryDetail, selectedEvent, user]);

  if (loading && !model) return <div className="mvp-route-state"><MvpState kind="loading" title="멘토링 기준 MVP 구성 중" detail="Project, Canonical V3.1 Result Artifact와 네 화면 문맥을 연결하고 있습니다." /></div>;
  if (error && !model) return <div className="mvp-route-state"><MvpState kind="error" title="MVP를 열지 못했습니다" detail={error} onRetry={refresh} /></div>;
  if (!model) return <div className="mvp-route-state"><MvpState kind="empty" title="MVP 데이터가 없습니다" detail="Project와 Workspace 연결 상태를 확인하세요." /></div>;

  const canDecide = Boolean(user?.permissions.includes("events.decision"));
  const canNote = Boolean(user?.permissions.includes("events.note"));
  const selectedAssetId = selection.assetId;

  let content;
  if (selection.view === "objects") {
    content = <MvpObjectsPage model={model} selectedAssetId={selectedAssetId} detail={detail} detailLoading={detailLoading} detailError={detailError} onSelectAsset={selectAsset} onOpenOperations={openAssetOperations} onRetryDetail={retryDetail} />;
  } else if (selection.view === "operations") {
    content = <MvpOperationsPage model={model} selectedEventId={selection.eventId} detail={detail} detailLoading={detailLoading} detailError={detailError} canDecide={canDecide} canNote={canNote} onSelectEvent={selectEvent} onOpenAsset={openEventAsset} onOpenReport={openEventReport} onDecision={submitDecision} onNote={submitNote} onRetryDetail={retryDetail} />;
  } else if (selection.view === "executive-report") {
    content = <MvpExecutiveReportPage model={model} selectedEvent={selectedEvent} detail={detail} detailLoading={detailLoading} detailError={detailError} onBackToOverview={() => openView("overview")} onOpenOperations={(event) => openEvent(event.eventId, event.assetId)} onRetryDetail={retryDetail} />;
  } else {
    content = <MvpOverviewPage model={model} onOpenAsset={openAsset} onOpenEvent={openEvent} onOpenReport={openReport} onRefresh={refresh} />;
  }

  return (
    <MvpShell
      context={model.context}
      activeView={selection.view}
      role={selection.role}
      onNavigate={openView}
      onRoleChange={(role: MvpRoleLens) => updateSelection({ role })}
      onRefresh={refresh}
      refreshing={loading}
    >
      {error ? <div className="mvp-inline-warning" role="alert"><strong>새로고침 실패</strong><span>{error}</span></div> : null}
      {content}
    </MvpShell>
  );
}
