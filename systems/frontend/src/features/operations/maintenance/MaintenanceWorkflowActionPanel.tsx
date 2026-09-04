import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  acceptInspectionWorkOrder,
  approveMaintenanceWorkOrder,
  completeInspectionWorkOrder,
  completeMaintenanceAction,
  createOperationsManualRecommendation,
  decideOperationsManualRecommendation,
  getMaintenanceActionCandidates,
  getMaintenanceEventLineage,
  getPostMaintenanceProductResults,
  requestInspectionWorkOrder,
  requestMaintenanceReplay,
  startInspectionWorkOrder,
  startMaintenanceAction,
  type InspectionChecklistStatus,
  type InspectionCompletionFacts,
  type InspectionOutcome,
  type MaintenanceActionCandidateReadModel,
  type MaintenanceEventLineageReadModel,
} from "../../../api";
import type { OperationsEvidenceSnapshotBasis, OperationsRoleLens } from "../api/operationsContracts";

function commandKey(eventId: string, action: string, target: string): string {
  return `operations-${eventId}-${action}-${target}`.replace(/[^a-zA-Z0-9_.:-]/g, "-").slice(0, 190);
}

function latest<T>(items: T[]): T | null {
  return items.length ? items[items.length - 1] : null;
}

function optionalNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

const ACTION_LABEL = {
  TOOL_REPLACEMENT: "공구 교체",
  COOLING_SYSTEM_RESTORE: "냉각 시스템 복구",
} as const;

export function postMaintenancePollingFailure(
  reason: unknown,
  consecutiveFailures: number,
): { message: string | null; stop: boolean } {
  const rendered = reason instanceof Error
    ? reason.message
    : "정비 후 예측 결과 조회에 실패했습니다.";
  if (reason instanceof ApiError && reason.status >= 400 && reason.status < 500) {
    return {
      message: `정비 후 결과 조회가 거부되었습니다: ${rendered}`,
      stop: true,
    };
  }
  return {
    message: consecutiveFailures >= 3
      ? `정비 후 결과 조회가 ${consecutiveFailures}회 연속 실패했습니다: ${rendered}`
      : null,
    stop: false,
  };
}

export type MaintenanceWorkflowDisplayStatus =
  | "candidate_recommended"
  | "work_requested"
  | "assigned"
  | "inspection_started"
  | "inspection_completed"
  | "maintenance_started"
  | "maintenance_completed"
  | "observation_pending"
  | "ready_for_reprediction";

export interface PostMaintenancePredictionSummary {
  failureProbability: number;
  statusGrade: "normal" | "attention" | "warning" | "critical";
  observedAt: string;
}

function displayStatus(
  lineage: MaintenanceEventLineageReadModel,
  postMaintenancePredictionAvailable = false,
): MaintenanceWorkflowDisplayStatus {
  const action = latest(lineage.maintenance_actions ?? []);
  if (action?.status === "completed") {
    if (postMaintenancePredictionAvailable) return "ready_for_reprediction";
    return action.restart_at ? "observation_pending" : "maintenance_completed";
  }
  if (action?.status === "in_progress") return "maintenance_started";
  if (action?.status === "planned") return "assigned";
  const maintenanceWorkOrder = latest(
    lineage.work_orders.filter((item) => item.work_type === "maintenance"),
  );
  if (maintenanceWorkOrder?.status === "requested") return "inspection_completed";
  const inspectionWorkOrder = latest(
    lineage.work_orders.filter((item) => item.work_type === "inspection"),
  );
  if (inspectionWorkOrder?.status === "completed") return "inspection_completed";
  if (inspectionWorkOrder?.status === "in_progress") return "inspection_started";
  if (inspectionWorkOrder?.status === "approved") return "assigned";
  if (inspectionWorkOrder?.status === "requested") return "work_requested";
  return "candidate_recommended";
}

export function MaintenanceWorkflowActionPanel({
  projectId,
  workspaceId,
  datasetVersionId,
  eventId,
  assetId,
  assetType,
  role,
  currentUserId,
  snapshotBasis,
  canManage,
  canFieldExecute,
  canMaintenanceExecute,
  onChanged,
  onStatusChanged,
  onPostMaintenancePrediction,
}: {
  projectId: string;
  workspaceId: string;
  datasetVersionId: string;
  eventId: string;
  assetId: string;
  assetType: string;
  role: OperationsRoleLens;
  currentUserId: string;
  snapshotBasis: OperationsEvidenceSnapshotBasis | null;
  canManage: boolean;
  canFieldExecute: boolean;
  canMaintenanceExecute: boolean;
  onChanged?: () => void;
  onStatusChanged?: (status: MaintenanceWorkflowDisplayStatus) => void;
  onPostMaintenancePrediction?: (prediction: PostMaintenancePredictionSummary) => void;
}) {
  const [lineage, setLineage] = useState<MaintenanceEventLineageReadModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [pollingError, setPollingError] = useState<string | null>(null);
  const [postMaintenancePrediction, setPostMaintenancePrediction] = useState<PostMaintenancePredictionSummary | null>(null);
  const [actionCandidates, setActionCandidates] = useState<MaintenanceActionCandidateReadModel[]>([]);
  const [selectedActionCandidateId, setSelectedActionCandidateId] = useState("");
  const [inspectionOutcome, setInspectionOutcome] = useState<InspectionOutcome>("maintenance_recommended");
  const [toolWearStatus, setToolWearStatus] = useState<InspectionChecklistStatus>("not_checked");
  const [toolWearMin, setToolWearMin] = useState("");
  const [coolingPathStatus, setCoolingPathStatus] = useState<InspectionChecklistStatus>("not_checked");
  const [coolantTemperatureC, setCoolantTemperatureC] = useState("");
  const [inHouseStatus, setInHouseStatus] = useState<"pass" | "fail" | "">("");
  const [sparePartAvailableStatus, setSparePartAvailableStatus] = useState<"pass" | "fail" | "">("");
  const [vendorDispatchRequiredStatus, setVendorDispatchRequiredStatus] = useState<"pass" | "fail" | "">("");
  const [componentReplacementRequiredStatus, setComponentReplacementRequiredStatus] = useState<"pass" | "fail" | "">("");
  const [inspectionFindings, setInspectionFindings] = useState("");
  const [inspectionNote, setInspectionNote] = useState("");
  const supportsCncMaintenance = assetType.toLowerCase().includes("cnc");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await getMaintenanceEventLineage(projectId, workspaceId, eventId);
      setLineage(next);
      onStatusChanged?.(displayStatus(next, Boolean(postMaintenancePrediction)));
    } catch (reason) {
      setMessage({ tone: "error", text: reason instanceof Error ? reason.message : "작업 상태를 불러오지 못했습니다." });
    } finally {
      setLoading(false);
    }
  }, [eventId, onStatusChanged, postMaintenancePrediction, projectId, workspaceId]);

  useEffect(() => { void refresh(); }, [refresh]);

  const state = useMemo(() => {
    const workOrders = lineage?.work_orders ?? [];
    const inspectionWorkOrder = latest(workOrders.filter((item) => item.work_type === "inspection"));
    const maintenanceWorkOrder = latest(workOrders.filter((item) => item.work_type === "maintenance"));
    const inspectionResult = latest(lineage?.inspection_results ?? []);
    const recommendation = latest(lineage?.recommendations ?? []);
    const action = latest(lineage?.maintenance_actions ?? []);
    const maintenanceEvent = latest(lineage?.maintenance_events ?? []);
    const selectedActionCandidate = actionCandidates.find(
      (item) => item.action_candidate_id === selectedActionCandidateId,
    ) ?? null;
    const inspectionCostAnalyses = (lineage?.cost_analyses ?? []).filter(
      (item) => item.based_on.inspection_result_id === inspectionResult?.inspection_result_id,
    );
    const costAnalysis = latest(
      inspectionCostAnalyses.filter(
        (item) => item.options.some(
          (option) => option.action_candidate_id === selectedActionCandidate?.action_candidate_id,
        ),
      ),
    );
    return {
      inspectionWorkOrder,
      maintenanceWorkOrder,
      inspectionResult,
      recommendation,
      action,
      maintenanceEvent,
      costAnalysis,
      hasReviewedCostAnalysis: inspectionCostAnalyses.length > 0,
      selectedActionCandidate,
    };
  }, [actionCandidates, lineage, selectedActionCandidateId]);

  useEffect(() => {
    const inspectionResultId = state.inspectionResult?.inspection_result_id;
    if (
      role !== "process_manager"
      || !inspectionResultId
      || state.inspectionResult?.outcome !== "maintenance_recommended"
    ) {
      setActionCandidates([]);
      setSelectedActionCandidateId("");
      return;
    }
    const controller = new AbortController();
    void getMaintenanceActionCandidates(
      projectId,
      workspaceId,
      inspectionResultId,
      controller.signal,
    ).then((response) => {
      setActionCandidates(response.items);
      setSelectedActionCandidateId((current) => (
        response.items.some((item) => item.action_candidate_id === current) ? current : ""
      ));
    }).catch((reason) => {
      if (controller.signal.aborted) return;
      setActionCandidates([]);
      setSelectedActionCandidateId("");
      setMessage({
        tone: "error",
        text: reason instanceof Error ? reason.message : "정비 Action 후보를 불러오지 못했습니다.",
      });
    });
    return () => controller.abort();
  }, [projectId, role, state.inspectionResult?.inspection_result_id, state.inspectionResult?.outcome, workspaceId]);

  useEffect(() => {
    setInspectionOutcome("maintenance_recommended");
    setToolWearStatus("not_checked");
    setToolWearMin("");
    setCoolingPathStatus("not_checked");
    setCoolantTemperatureC("");
    setInHouseStatus("");
    setSparePartAvailableStatus("");
    setVendorDispatchRequiredStatus("");
    setComponentReplacementRequiredStatus("");
    setInspectionFindings("");
    setInspectionNote("");
  }, [state.inspectionWorkOrder?.work_order_id]);

  useEffect(() => {
    const maintenanceEventId = state.maintenanceEvent?.maintenance_event_id;
    if (!maintenanceEventId || !state.action?.restart_at || postMaintenancePrediction) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;
    let consecutiveFailures = 0;
    setPollingError(null);

    const poll = async () => {
      try {
        const result = await getPostMaintenanceProductResults(
          projectId,
          workspaceId,
          assetId,
          maintenanceEventId,
          controller.signal,
        );
        consecutiveFailures = 0;
        setPollingError(null);
        if (result) {
          const prediction: PostMaintenancePredictionSummary = {
            failureProbability: result.failure_probability,
            statusGrade: result.status_grade,
            observedAt: result.observed_at,
          };
          setPostMaintenancePrediction(prediction);
          onPostMaintenancePrediction?.(prediction);
          onStatusChanged?.("ready_for_reprediction");
          setMessage({ tone: "success", text: "정비 후 관측과 예측 처리가 완료됐습니다." });
          return;
        }
      } catch (reason) {
        if (controller.signal.aborted) return;
        consecutiveFailures += 1;
        const failure = postMaintenancePollingFailure(reason, consecutiveFailures);
        if (failure.message) setPollingError(failure.message);
        if (failure.stop) return;
      }
      if (!stopped) {
        const retryDelay = consecutiveFailures > 0
          ? Math.min(1_500 * (2 ** consecutiveFailures), 10_000)
          : 1_500;
        timer = setTimeout(() => void poll(), retryDelay);
      }
    };

    onStatusChanged?.("observation_pending");
    void poll();
    return () => {
      stopped = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [
    assetId,
    onPostMaintenancePrediction,
    onStatusChanged,
    postMaintenancePrediction,
    projectId,
    state.action?.restart_at,
    state.maintenanceEvent?.maintenance_event_id,
    workspaceId,
  ]);

  const run = async (label: string, command: () => Promise<unknown>) => {
    setRunning(true);
    setMessage(null);
    try {
      await command();
      setMessage({ tone: "success", text: `${label} 처리가 완료됐습니다.` });
      await refresh();
      onChanged?.();
    } catch (reason) {
      setMessage({ tone: "error", text: reason instanceof Error ? reason.message : `${label} 처리에 실패했습니다.` });
    } finally {
      setRunning(false);
    }
  };

  const inspectionFacts: InspectionCompletionFacts = {
    outcome: inspectionOutcome,
    toolWearStatus,
    toolWearMin: optionalNumber(toolWearMin),
    coolingPathStatus,
    coolantTemperatureC: optionalNumber(coolantTemperatureC),
    inHouseStatus,
    sparePartAvailableStatus,
    vendorDispatchRequiredStatus,
    componentReplacementRequiredStatus,
    findings: inspectionFindings,
    note: inspectionNote,
  };
  const hasToolEvidence = toolWearStatus === "fail"
    && inspectionFacts.toolWearMin !== null
    && inspectionFacts.toolWearMin >= 0;
  const hasCoolingEvidence = coolingPathStatus === "fail"
    && inspectionFacts.coolantTemperatureC !== null
    && inspectionFacts.coolantTemperatureC >= 0;
  const sharedCostBasisReady = Boolean(inHouseStatus && vendorDispatchRequiredStatus);
  const candidateCostBasisReady = sharedCostBasisReady
    && (!hasToolEvidence || Boolean(sparePartAvailableStatus))
    && (!hasCoolingEvidence || Boolean(componentReplacementRequiredStatus));
  const inspectionReady = Boolean(inspectionFindings.trim()) && (
    inspectionOutcome === "data_check_required"
    || (inspectionOutcome === "no_action_required"
      && toolWearStatus === "pass"
      && coolingPathStatus === "pass")
    || (inspectionOutcome === "maintenance_recommended"
      && (hasToolEvidence || hasCoolingEvidence)
      && candidateCostBasisReady)
  );

  let label = "다음 작업 대기";
  let helper = "현재 역할에서 실행할 수 있는 다음 단계가 없습니다.";
  let enabled = false;
  let command: (() => Promise<unknown>) | null = null;

  if (role === "process_manager") {
    if (!state.inspectionWorkOrder) {
      label = "점검 작업요청 생성";
      helper = snapshotBasis ? "현재 Product Result/Evidence 스냅샷을 기준으로 요청합니다." : "정본 근거가 로드될 때까지 기다려 주세요.";
      enabled = canManage && Boolean(snapshotBasis);
      command = snapshotBasis ? () => requestInspectionWorkOrder({
        projectId,
        workspaceId,
        eventId,
        snapshotBasis: {
          artifact_id: snapshotBasis.artifactId,
          evidence_payload_reference: snapshotBasis.evidencePayloadReference,
          asset_id: snapshotBasis.assetId,
          event_id: snapshotBasis.eventId,
          observed_at: snapshotBasis.observedAt,
          model_version: snapshotBasis.modelVersion,
          dataset_version: snapshotBasis.datasetVersion,
          source_sha256: snapshotBasis.sourceSha256,
        },
        idempotencyKey: commandKey(eventId, "inspection-request", snapshotBasis.artifactId ?? eventId),
      }) : null;
    } else if (state.inspectionWorkOrder.status === "requested") {
      label = "현장 관리자 수락 대기";
      helper = "현장 담당자가 요청을 수락하면 해당 담당자에게 자동 배정됩니다.";
    } else if (state.inspectionResult?.outcome === "no_action_required") {
      label = "점검 완료 · 정비 불필요";
      helper = "현장 점검 결과 추가 정비가 필요하지 않은 것으로 기록됐습니다.";
    } else if (state.inspectionResult?.outcome === "data_check_required") {
      label = "추가 데이터 확인 필요";
      helper = "점검 결과만으로 정비 판단을 내리지 않고 추가 데이터 확인 상태로 유지합니다.";
    } else if (state.inspectionResult && !state.recommendation) {
      label = "정비안 생성";
      helper = !state.hasReviewedCostAnalysis
        ? "먼저 아래 비용 분석을 실행해 참고 결과를 확인하세요."
        : !state.selectedActionCandidate
          ? "비용 분석을 참고한 뒤 Backend가 산출한 정비 Action 후보를 직접 선택하세요."
          : state.costAnalysis
            ? "비용은 참고값입니다. 선택한 Action 후보를 근거로 Operations 수동 정비안을 생성합니다."
            : "선택한 Action 후보의 비용 분석을 먼저 실행해 참고 결과를 확인하세요.";
      enabled = canManage && Boolean(state.costAnalysis && state.selectedActionCandidate);
      command = state.costAnalysis && state.selectedActionCandidate ? () => createOperationsManualRecommendation({
        projectId,
        workspaceId,
        inspectionResultId: state.inspectionResult!.inspection_result_id,
        actionCode: state.selectedActionCandidate!.action_code,
        costAnalysisId: state.costAnalysis!.analysis_id,
        actionCandidateId: state.selectedActionCandidate!.action_candidate_id,
        idempotencyKey: commandKey(
          eventId,
          "recommendation-create",
          `${state.selectedActionCandidate!.action_candidate_id}:${state.costAnalysis!.analysis_id}`,
        ),
      }) : null;
    } else if (state.recommendation && !state.maintenanceWorkOrder) {
      label = "정비안 승인";
      helper = "비용은 참고값이며 이 버튼이 사람의 명시적 정비 승인입니다.";
      enabled = canManage && !["accepted", "rejected"].includes(state.recommendation.status);
      command = () => decideOperationsManualRecommendation({
        projectId,
        workspaceId,
        recommendationId: state.recommendation!.recommendation_id,
        disposition: "accept",
        idempotencyKey: commandKey(eventId, "recommendation-accept", state.recommendation!.recommendation_id),
      });
    } else if (state.maintenanceWorkOrder?.status === "requested") {
      label = "정비 WorkOrder 승인";
      helper = "승인된 Product Result의 source runtime lineage를 이어 정비 Action을 계획합니다.";
      enabled = canManage;
      command = () => approveMaintenanceWorkOrder({
        projectId,
        workspaceId,
        workOrderId: state.maintenanceWorkOrder!.work_order_id,
        datasetVersionId,
        idempotencyKey: commandKey(eventId, "maintenance-approve", state.maintenanceWorkOrder!.work_order_id),
      });
    }
  } else {
    if (!state.inspectionWorkOrder) {
      label = "운영 관리자 점검 요청 대기";
      helper = "현재 Case의 근거는 준비되어 있습니다. 운영 관리자가 점검 작업요청을 생성하면 이 화면에서 수락할 수 있습니다.";
    } else if (state.inspectionWorkOrder?.status === "requested") {
      label = "요청 수락·내게 배정";
      helper = "수락과 동시에 이 점검 요청의 담당자로 배정됩니다.";
      enabled = canFieldExecute;
      command = () => acceptInspectionWorkOrder({
        projectId, workspaceId, workOrderId: state.inspectionWorkOrder!.work_order_id,
        idempotencyKey: commandKey(eventId, "inspection-accept", state.inspectionWorkOrder!.work_order_id),
      });
    } else if (state.inspectionWorkOrder?.status === "approved") {
      label = "점검 시작";
      const assignedToCurrentUser = state.inspectionWorkOrder.assigned_to === currentUserId;
      helper = assignedToCurrentUser
        ? "SOP를 확인한 뒤 현장 점검을 시작합니다."
        : `이 요청은 ${state.inspectionWorkOrder.assigned_to ?? "다른 담당자"}에게 배정되었습니다.`;
      enabled = canFieldExecute && assignedToCurrentUser;
      command = () => startInspectionWorkOrder({
        projectId, workspaceId, workOrderId: state.inspectionWorkOrder!.work_order_id,
        idempotencyKey: commandKey(eventId, "inspection-start", state.inspectionWorkOrder!.work_order_id),
      });
    } else if (state.inspectionWorkOrder?.status === "in_progress") {
      label = "점검 결과 기록·완료";
      helper = !supportsCncMaintenance
        ? "현재 정비·Overlay 실행은 CNC 설비만 지원합니다. 이 설비의 점검 완료는 후속 계약이 필요합니다."
        : inspectionReady
          ? "입력한 점검 사실을 기록합니다. 정비 Action 후보는 Backend가 이 결과에서 산출합니다."
          : "점검 판정, 체크리스트, 측정값과 발견 내용을 입력하세요.";
      enabled = canFieldExecute && supportsCncMaintenance && inspectionReady;
      command = supportsCncMaintenance && inspectionReady ? () => completeInspectionWorkOrder({
        projectId,
        workspaceId,
        workOrderId: state.inspectionWorkOrder!.work_order_id,
        facts: inspectionFacts,
        idempotencyKey: commandKey(eventId, "inspection-complete", state.inspectionWorkOrder!.work_order_id),
      }) : null;
    } else if (state.action?.status === "planned") {
      label = "정비 시작";
      helper = canMaintenanceExecute
        ? "승인된 정비 작업을 시작합니다."
        : "정비 실행 권한이 있는 정비 담당자에게 인계된 단계입니다.";
      enabled = canMaintenanceExecute;
      command = () => startMaintenanceAction({
        projectId, workspaceId, maintenanceActionId: state.action!.maintenance_action_id,
        idempotencyKey: commandKey(eventId, "maintenance-start", state.action!.maintenance_action_id),
      });
    } else if (state.action?.status === "in_progress") {
      label = "정비 완료";
      helper = canMaintenanceExecute
        ? "정비 결과를 기록하고 변경 불가능한 정비 이력을 생성합니다."
        : "정비 완료 기록은 배정된 정비 담당자만 수행할 수 있습니다.";
      enabled = canMaintenanceExecute;
      command = () => completeMaintenanceAction({
        projectId,
        workspaceId,
        maintenanceActionId: state.action!.maintenance_action_id,
        actionCode: state.action!.action_code,
        idempotencyKey: commandKey(eventId, "maintenance-complete", state.action!.maintenance_action_id),
      });
    } else if (state.maintenanceEvent && !state.action?.restart_at) {
      label = "정비 후 관측 재개";
      helper = canMaintenanceExecute
        ? "정비 결과를 반영한 설비 관측을 재개하고 실제 재예측을 요청합니다."
        : "관측 재개는 정비 완료를 기록한 정비 담당자가 수행합니다.";
      enabled = canMaintenanceExecute;
      command = () => requestMaintenanceReplay({
        projectId,
        workspaceId,
        maintenanceEventId: state.maintenanceEvent!.maintenance_event_id,
        idempotencyKey: commandKey(eventId, "maintenance-replay", state.maintenanceEvent!.maintenance_event_id),
      });
    }
  }

  if (postMaintenancePrediction) {
    const percent = (postMaintenancePrediction.failureProbability * 100).toFixed(2);
    const isNormal = postMaintenancePrediction.statusGrade === "normal";
    label = isNormal ? "정상 운영 중" : "정비 후 위험 지속";
    helper = isNormal
      ? `정비 후 예측 위험도 ${percent}% · Overlay 공정이 계속 진행 중입니다.`
      : `정비 후 예측 위험도 ${percent}% · 추가 점검 또는 정비 판단이 필요합니다.`;
    enabled = false;
    command = null;
  } else if (state.action?.restart_at) {
    label = "정비 후 관측 수집 중";
    helper = "대상 설비 Overlay Observation을 생성하고 예측 결과를 기다리고 있습니다.";
    enabled = false;
    command = null;
  }

  return (
    <section className="operations-maintenance-workflow-panel" aria-label="Closed-loop 작업 실행" data-event-id={eventId}>
      <header><div><span>Closed-loop</span><strong>{role === "process_manager" ? "운영 관리자 작업" : "현장 점검 작업"}</strong></div><button type="button" className="operations-icon-button" onClick={() => void refresh()} aria-label="작업 상태 새로고침">↻</button></header>
      <p>{loading ? "작업 상태를 확인하고 있습니다." : helper}</p>
      {role === "process_manager"
        && state.inspectionResult?.outcome === "maintenance_recommended"
        && state.hasReviewedCostAnalysis
        && !state.recommendation ? (
        <label className="operations-field">
          <span>정비 Action 판단</span>
          <select
            value={selectedActionCandidateId}
            onChange={(event) => setSelectedActionCandidateId(event.target.value)}
            disabled={!canManage || running}
          >
            <option value="">Action 후보 선택</option>
            {actionCandidates.map((candidate) => (
              <option key={candidate.action_candidate_id} value={candidate.action_candidate_id}>
                {ACTION_LABEL[candidate.action_code]}
              </option>
            ))}
          </select>
          <small>최저비용 option은 자동 선택되지 않으며, Action 판단은 생산 관리자가 명시적으로 수행합니다.</small>
        </label>
      ) : null}
      {role === "field_operator" && supportsCncMaintenance && state.inspectionWorkOrder?.status === "in_progress" ? (
        <fieldset className="operations-inspection-form" disabled={!canFieldExecute || running}>
          <legend>현장 점검 사실</legend>
          <label className="operations-field">
            <span>점검 판정</span>
            <select value={inspectionOutcome} onChange={(event) => setInspectionOutcome(event.target.value as InspectionOutcome)}>
              <option value="maintenance_recommended">정비 검토 필요</option>
              <option value="no_action_required">추가 정비 불필요</option>
              <option value="data_check_required">추가 데이터 확인 필요</option>
            </select>
          </label>
          <div className="operations-inspection-grid">
            <label className="operations-field">
              <span>공구 마모 점검</span>
              <select value={toolWearStatus} onChange={(event) => setToolWearStatus(event.target.value as InspectionChecklistStatus)}>
                <option value="not_checked">미확인</option>
                <option value="pass">정상</option>
                <option value="fail">이상</option>
              </select>
            </label>
            <label className="operations-field">
              <span>공구 누적 사용시간 (분)</span>
              <input type="number" min="0" step="1" value={toolWearMin} onChange={(event) => setToolWearMin(event.target.value)} placeholder="예: 220" />
            </label>
            <label className="operations-field">
              <span>냉각 경로 점검</span>
              <select value={coolingPathStatus} onChange={(event) => setCoolingPathStatus(event.target.value as InspectionChecklistStatus)}>
                <option value="not_checked">미확인</option>
                <option value="pass">정상</option>
                <option value="fail">이상</option>
              </select>
            </label>
            <label className="operations-field">
              <span>냉각수 온도 (°C)</span>
              <input type="number" min="0" step="0.1" value={coolantTemperatureC} onChange={(event) => setCoolantTemperatureC(event.target.value)} placeholder="예: 92" />
            </label>
          </div>
          {inspectionOutcome === "maintenance_recommended" ? (
            <>
              <strong className="operations-inspection-subtitle">비용 산정 기준 확인</strong>
              <div className="operations-inspection-grid">
                <label className="operations-field">
                  <span>사내 정비 가능</span>
                  <select value={inHouseStatus} onChange={(event) => setInHouseStatus(event.target.value as "pass" | "fail" | "")}>
                    <option value="">선택</option><option value="pass">예</option><option value="fail">아니오</option>
                  </select>
                </label>
                <label className="operations-field">
                  <span>교체용 인서트 확보</span>
                  <select value={sparePartAvailableStatus} onChange={(event) => setSparePartAvailableStatus(event.target.value as "pass" | "fail" | "")}>
                    <option value="">선택</option><option value="pass">예</option><option value="fail">아니오</option>
                  </select>
                </label>
                <label className="operations-field">
                  <span>외부 업체 출동 필요</span>
                  <select value={vendorDispatchRequiredStatus} onChange={(event) => setVendorDispatchRequiredStatus(event.target.value as "pass" | "fail" | "")}>
                    <option value="">선택</option><option value="pass">예</option><option value="fail">아니오</option>
                  </select>
                </label>
                <label className="operations-field">
                  <span>냉각 계통 부품 교체 필요</span>
                  <select value={componentReplacementRequiredStatus} onChange={(event) => setComponentReplacementRequiredStatus(event.target.value as "pass" | "fail" | "")}>
                    <option value="">선택</option><option value="pass">예</option><option value="fail">아니오</option>
                  </select>
                </label>
              </div>
            </>
          ) : null}
          <label className="operations-field">
            <span>발견 내용</span>
            <textarea value={inspectionFindings} onChange={(event) => setInspectionFindings(event.target.value)} placeholder="현장에서 확인한 상태를 기록하세요." />
          </label>
          <label className="operations-field">
            <span>추가 메모</span>
            <textarea value={inspectionNote} onChange={(event) => setInspectionNote(event.target.value)} placeholder="필요할 때만 추가 근거를 남기세요." />
          </label>
          <small>현장에서는 사실만 기록합니다. 정비 Action 후보는 Backend가 체크리스트와 측정값에서 산출합니다.</small>
        </fieldset>
      ) : null}
      <button
        type="button"
        className="operations-button primary"
        disabled={loading || running || !enabled || !command}
        onClick={() => command && void run(label, command)}
      >
        {running ? "처리 중" : label}
      </button>
      {message ? <small className={message.tone === "error" ? "operations-cost-error" : "operations-workflow-success"}>{message.text}</small> : null}
      {pollingError ? <small className="operations-cost-error">{pollingError}</small> : null}
    </section>
  );
}
