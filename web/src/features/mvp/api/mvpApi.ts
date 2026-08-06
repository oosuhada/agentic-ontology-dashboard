import {
  API_BASE,
  ApiError,
  addNote,
  getEvidence,
  getPredictiveMaintenanceDashboard,
  getPredictiveMaintenanceLatestResults,
  getProject,
  getProjectEvents,
  getProjectWorkspaces,
  getReport,
  recordDecision,
} from "../../../api";
import type { Evidence, Report } from "../../../types";
import { adaptEvent, composeEventDetail, computeLineRisk, computeMetrics, mergeAssets, sortRisk } from "./mvpAdapters";
import type {
  MvpBootstrapModel,
  MvpDecision,
  MvpEvent,
  MvpEventDetailModel,
  MvpMetrics,
  MvpRoleLens,
} from "./mvpContracts";

async function getEventActivity(eventId: string): Promise<unknown> {
  const response = await fetch(`${API_BASE}/api/events/${encodeURIComponent(eventId)}/activity`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload?.error?.code ?? "activity_request_failed",
      payload?.error?.message ?? `Activity request failed: ${response.status}`,
    );
  }
  return payload;
}

function staleFrom(observedAt: string | null): boolean {
  if (!observedAt) return false;
  const value = Date.parse(observedAt);
  if (!Number.isFinite(value)) return false;
  return Date.now() - value > 24 * 60 * 60 * 1000;
}

function warningMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

export async function loadMvpBootstrap(
  projectId: string,
  requestedWorkspaceId?: string | null,
  selectedEventId?: string | null,
): Promise<MvpBootstrapModel> {
  const [project, workspaces] = await Promise.all([
    getProject(projectId),
    getProjectWorkspaces(projectId),
  ]);
  const workspace = workspaces.find((item) => item.id === requestedWorkspaceId)
    ?? workspaces.find((item) => item.id === project.default_workspace_id)
    ?? workspaces[0];
  if (!workspace) throw new Error("이 Project에 연결된 Workspace가 없습니다.");

  const dashboardPromise = getPredictiveMaintenanceDashboard(projectId, workspace.id, {
    selected_event_id: selectedEventId ?? undefined,
    role: "manager",
    intent: "overview",
    locale: "ko-KR",
  });
  const resultPromise = getPredictiveMaintenanceLatestResults(projectId, workspace.id, 1000);
  const [dashboardState, resultState] = await Promise.allSettled([dashboardPromise, resultPromise]);

  const warnings: string[] = [];
  let rawEvents = dashboardState.status === "fulfilled" ? dashboardState.value.events : [];
  if (dashboardState.status === "rejected") {
    warnings.push(`Canonical Runtime Dashboard: ${warningMessage(dashboardState.reason, "사용 불가")}`);
    try {
      rawEvents = await getProjectEvents(projectId);
    } catch (reason) {
      warnings.push(`Gold Fixture Events: ${warningMessage(reason, "사용 불가")}`);
    }
  }

  const events = sortRisk(rawEvents.map(adaptEvent));
  const results = resultState.status === "fulfilled" ? resultState.value.items : [];
  if (resultState.status === "rejected") {
    warnings.push(`Canonical Result Artifact: ${warningMessage(resultState.reason, "사용 불가")}`);
  }
  const assets = mergeAssets(results, events);
  const metrics = computeMetrics(assets, events);
  const lineRisk = computeLineRisk(assets);
  const latestObservedAt = assets
    .map((item) => item.observedAt)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1) ?? null;

  const canonical = dashboardState.status === "fulfilled" ? dashboardState.value : null;
  const resultContext = resultState.status === "fulfilled" ? resultState.value.context : null;
  const dataSource = canonical?.data_source;
  const context = canonical?.context ?? resultContext;
  const sourceMode = canonical || resultState.status === "fulfilled"
    ? "canonical-runtime" as const
    : "gold-fixture-fallback" as const;
  const datasetVersionId = dataSource?.dataset_version_id
    ?? context?.dataset_version_id
    ?? events[0]?.datasetVersionId
    ?? "dsv-canonical-v3-1";
  const sourceVersion = dataSource?.source_version ?? context?.source_version ?? "Canonical V3.1";

  return {
    context: {
      projectId: project.id,
      projectName: project.display_name,
      workspaceId: workspace.id,
      workspaceName: workspace.display_name,
      datasetVersionId,
      datasetLabel: dataSource?.dataset_name
        ? `${dataSource.dataset_name} · ${sourceVersion}`
        : "UCI AI4I 2020 Manufacturing Predictive Maintenance — Physics & Maintenance Canonical V3.1",
      sourceVersion,
      modelVersion: dataSource?.model_version ?? context?.model_version ?? null,
      schemaVersion: dataSource?.result_artifact_schema_version ?? context?.result_artifact_schema_version ?? null,
      sourceMode,
      sourceStatus: sourceMode === "canonical-runtime"
        ? `${dataSource?.dataset_status ?? context?.dataset_status ?? "available"} · Result Artifact`
        : "Gold Fixture fallback · Canonical Runtime unavailable",
      refreshedAt: new Date().toISOString(),
      observedAt: latestObservedAt,
      stale: staleFrom(latestObservedAt),
      warnings,
    },
    assets,
    events,
    metrics,
    lineRisk,
  };
}

async function loadLegacyReport(eventId: string): Promise<{ report: Report | null; warning: string | null }> {
  try {
    return { report: await getReport(eventId, "manager", true, "ko-KR"), warning: null };
  } catch (llmReason) {
    try {
      const report = await getReport(eventId, "manager", false, "ko-KR");
      return {
        report,
        warning: `LLM report failed; deterministic fallback used: ${warningMessage(llmReason, "unknown error")}`,
      };
    } catch (fallbackReason) {
      return {
        report: null,
        warning: `Report API unavailable; template fallback used: ${warningMessage(fallbackReason, "unknown error")}`,
      };
    }
  }
}

export async function loadMvpEventDetail(input: {
  projectId: string;
  workspaceId: string;
  datasetVersionId: string;
  event: MvpEvent;
  role: MvpRoleLens;
  metrics?: MvpMetrics;
}): Promise<MvpEventDetailModel> {
  const predictivePromise = getPredictiveMaintenanceDashboard(input.projectId, input.workspaceId, {
    dataset_version_id: input.datasetVersionId,
    selected_event_id: input.event.eventId,
    role: input.role === "process_manager" ? "manager" : "engineer",
    intent: input.role === "process_manager" ? "summarize-manager" : "detail-engineer",
    locale: "ko-KR",
  });
  const evidencePromise = getEvidence(input.event.eventId);
  const reportPromise = loadLegacyReport(input.event.eventId);
  const activityPromise = getEventActivity(input.event.eventId);
  const [predictiveState, evidenceState, reportState, activityState] = await Promise.allSettled([
    predictivePromise,
    evidencePromise,
    reportPromise,
    activityPromise,
  ]);
  const predictiveDetail = predictiveState.status === "fulfilled"
    ? predictiveState.value.selected_event_detail
    : null;
  const evidence: Evidence | null = evidenceState.status === "fulfilled"
    ? evidenceState.value
    : predictiveDetail?.evidence ?? null;
  const legacyReport = reportState.status === "fulfilled" ? reportState.value : { report: null, warning: null };
  const report = legacyReport.report ?? predictiveDetail?.report ?? null;
  const activity = activityState.status === "fulfilled" ? activityState.value : null;
  const warnings = [
    legacyReport.warning,
    evidenceState.status === "rejected" && !predictiveDetail?.evidence
      ? `Evidence API: ${warningMessage(evidenceState.reason, "사용 불가")}`
      : null,
    activityState.status === "rejected"
      ? `Activity API: ${warningMessage(activityState.reason, "사용 불가")}`
      : null,
  ].filter((value): value is string => Boolean(value));
  return composeEventDetail({
    event: input.event,
    evidence,
    report,
    activity,
    metrics: input.metrics,
    warnings,
  });
}

export async function submitMvpDecision(input: {
  eventId: string;
  actor: string;
  decision: MvpDecision;
  note: string;
}): Promise<void> {
  await recordDecision(input.eventId, input.actor, input.decision, input.note);
}

export async function submitMvpNote(input: {
  eventId: string;
  actor: string;
  body: string;
}): Promise<void> {
  await addNote(input.eventId, input.actor, input.body);
}
