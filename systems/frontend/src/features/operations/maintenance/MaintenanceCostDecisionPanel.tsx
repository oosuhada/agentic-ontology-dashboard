import { Calculator, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  calculateMaintenanceCost,
  getMaintenanceActionCandidates,
  getMaintenanceEventLineage,
  type MaintenanceActionCandidateReadModel,
  type MaintenanceActionCode,
  type MaintenanceCostAnalysisRequest,
  type MaintenanceCostAnalysisReadModel,
  type MaintenanceEventLineageReadModel,
  type MaintenanceExecutionTiming,
  type MaintenanceInspectionResultReadModel,
} from "../../../api";
import type { OperationsInspectionGuidance } from "../api/operationsContracts";

const TIMING_LABEL: Record<MaintenanceExecutionTiming, string> = {
  immediate: "즉시 정비",
  planned_window: "계획 정비 창",
  reinspect_after: "재점검 후",
  no_action_baseline: "미조치 기준",
};

const ACTION_LABEL: Record<MaintenanceActionCode, string> = {
  TOOL_REPLACEMENT: "공구 교체",
  COOLING_SYSTEM_RESTORE: "냉각 시스템 복구",
};

const CONFIDENCE_LABEL = {
  high: "높음",
  medium: "보통",
  low: "낮음",
  insufficient: "근거 부족",
} as const;

export function latestEligibleInspection(
  lineage: MaintenanceEventLineageReadModel | null,
): MaintenanceInspectionResultReadModel | null {
  if (!lineage) return null;
  const latestInspectionWorkOrder = lineage.work_orders
    .filter((item) => item.work_type === "inspection")
    .at(-1);
  if (!latestInspectionWorkOrder || latestInspectionWorkOrder.status !== "completed") {
    return null;
  }
  const latestResult = [...lineage.inspection_results]
    .filter((item) => item.work_order_id === latestInspectionWorkOrder.work_order_id)
    .sort((left, right) => right.recorded_at.localeCompare(left.recorded_at))[0] ?? null;
  return latestResult?.outcome === "maintenance_recommended" ? latestResult : null;
}

export function isCostAnalysisStageOpen(
  lineage: MaintenanceEventLineageReadModel | null,
  inspection: MaintenanceInspectionResultReadModel | null,
): boolean {
  if (!lineage || !inspection) return false;
  const recommendationCreated = lineage.recommendations.some((item) => (
    item.source_inspection_reference === inspection.inspection_result_id
    || item.source_inspection_work_order_id === inspection.work_order_id
  ));
  const maintenanceStarted = lineage.work_orders.some((item) => item.work_type === "maintenance")
    || Boolean(lineage.maintenance_actions?.length)
    || Boolean(lineage.maintenance_events?.length);
  return !recommendationCreated && !maintenanceStarted;
}

export function latestCostAnalysisForInspection(
  analyses: MaintenanceCostAnalysisReadModel[],
  inspection: MaintenanceInspectionResultReadModel | null,
  actionCode?: MaintenanceActionCode | null,
): MaintenanceCostAnalysisReadModel | null {
  if (!inspection) return null;
  return analyses
    .filter((analysis) => (
      analysis.based_on.inspection_work_order_id === inspection.work_order_id
      && analysis.based_on.inspection_result_id === inspection.inspection_result_id
      && (
        !actionCode
        || analysis.options.some((option) => option.action_code === actionCode)
      )
    ))
    .sort((left, right) => right.calculated_at.localeCompare(left.calculated_at))[0] ?? null;
}

export function costOptionsForDisplay(
  analysis: MaintenanceCostAnalysisReadModel,
  actionCode: MaintenanceActionCode | null,
): MaintenanceCostAnalysisReadModel["options"] {
  if (actionCode === "COOLING_SYSTEM_RESTORE") {
    return analysis.options.filter((option) => option.execution_timing === "immediate");
  }
  if (actionCode === "TOOL_REPLACEMENT") {
    return analysis.options.filter((option) => option.execution_timing !== "reinspect_after");
  }
  return [];
}

export function buildCostRequest(
  guidance: Pick<OperationsInspectionGuidance, "sopId" | "version">,
  actionCode: MaintenanceActionCode = "TOOL_REPLACEMENT",
): MaintenanceCostAnalysisRequest {
  return {
    action_code: actionCode,
    sop_id: guidance.sopId,
    sop_version: guidance.version,
  };
}

function requestKey(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function formatWon(value: number | null | undefined): string {
  return value === null || value === undefined ? "산정 불가" : `${value.toLocaleString()}원`;
}

export function MaintenanceCostDecisionPanel({
  projectId,
  workspaceId,
  eventId,
  guidance,
  onChanged,
  onEligibilityChanged,
}: {
  projectId: string;
  workspaceId: string;
  eventId: string;
  guidance: OperationsInspectionGuidance | null;
  onChanged?: () => void;
  onEligibilityChanged?: (eligible: boolean) => void;
}) {
  const [lineage, setLineage] = useState<MaintenanceEventLineageReadModel | null>(null);
  const [actionCandidates, setActionCandidates] = useState<MaintenanceActionCandidateReadModel[]>([]);
  const [selectedActionCode, setSelectedActionCode] = useState<MaintenanceActionCode | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sopId, setSopId] = useState(guidance?.sopId ?? "");
  const [sopVersion, setSopVersion] = useState(guidance?.version ?? "");

  const load = async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const nextLineage = await getMaintenanceEventLineage(
        projectId,
        workspaceId,
        eventId,
        signal,
      );
      setLineage(nextLineage);
      const nextInspection = latestEligibleInspection(nextLineage);
      const nextStageOpen = isCostAnalysisStageOpen(nextLineage, nextInspection);
      onEligibilityChanged?.(nextStageOpen);
      if (nextInspection && nextStageOpen) {
        const candidates = await getMaintenanceActionCandidates(
          projectId,
          workspaceId,
          nextInspection.inspection_result_id,
          signal,
        );
        setActionCandidates(candidates.items);
        setSelectedActionCode((currentAction) => (
          currentAction && candidates.items.some(
            (candidate) => candidate.action_code === currentAction
          )
            ? currentAction
            : candidates.items[0]?.action_code ?? null
        ));
      } else {
        setActionCandidates([]);
        setSelectedActionCode(null);
      }
    } catch (caught) {
      if (signal?.aborted) return;
      onEligibilityChanged?.(false);
      setError(caught instanceof Error ? caught.message : "비용 분석 이력을 불러오지 못했습니다.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [projectId, workspaceId, eventId]);

  useEffect(() => {
    if (guidance?.sopId) setSopId(guidance.sopId);
    if (guidance?.version) setSopVersion(guidance.version);
  }, [guidance?.sopId, guidance?.version]);

  const inspection = useMemo(() => latestEligibleInspection(lineage), [lineage]);
  const stageOpen = useMemo(
    () => isCostAnalysisStageOpen(lineage, inspection),
    [inspection, lineage],
  );
  const analyses = useMemo(() => [...(lineage?.cost_analyses ?? [])]
    .sort((left, right) => right.calculated_at.localeCompare(left.calculated_at)), [lineage]);
  const current = useMemo(
    () => latestCostAnalysisForInspection(analyses, inspection, selectedActionCode),
    [analyses, inspection, selectedActionCode],
  );
  const visibleOptions = useMemo(
    () => current ? costOptionsForDisplay(current, selectedActionCode) : [],
    [current, selectedActionCode],
  );
  const isImmediateCooling = selectedActionCode === "COOLING_SYSTEM_RESTORE";
  const visibleCalculationComplete = visibleOptions.length > 0
    && visibleOptions.every((option) => option.calculation_status === "calculated");
  const calculate = async () => {
    if (!inspection || !selectedActionCode) return;
    if (!sopId.trim() || !sopVersion.trim()) {
      setError("점검에 참고한 SOP ID와 버전을 입력해 주세요.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await calculateMaintenanceCost(
        projectId,
        workspaceId,
        inspection.inspection_result_id,
        buildCostRequest(
          { sopId: sopId.trim(), version: sopVersion.trim() },
          selectedActionCode,
        ),
        requestKey("cost-analysis"),
      );
      await load();
      onChanged?.();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "비용 분석을 실행하지 못했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  const blocker = actionCandidates.length === 0
      ? "점검 결과에서 실행 가능한 정비 Action 후보가 확인되지 않았습니다."
    : !sopId.trim() || !sopVersion.trim()
      ? "점검에 참고한 SOP 기준정보가 필요합니다."
    : null;
  if (loading || !inspection || !stageOpen) return null;

  return (
    <section className="operations-maintenance-cost-panel" aria-label="정비 비용 분석">
      <header>
        <Calculator size={14} />
        <strong>{isImmediateCooling ? "즉시 복구 예상 비용" : "정비 비용 분석"}</strong>
        <button type="button" className="operations-icon-button" onClick={() => void load()} disabled={loading} aria-label="비용 분석 새로고침">
          <RefreshCw size={13} />
        </button>
      </header>
      <p>
        {isImmediateCooling
          ? "현재 데이터로 근거를 확인할 수 있는 즉시 냉각 복구 비용만 제공합니다. 버튼을 누르기 전에는 계산하지 않습니다."
          : "점검 결과에서 확인된 정비 Action 후보의 비용만 비교합니다. 버튼을 누르기 전에는 분석하지 않습니다."}
      </p>
      {blocker ? <small className="operations-cost-warning">{blocker}</small> : null}
      {error ? <small className="operations-cost-error">{error}</small> : null}

      {actionCandidates.length ? (
        <div className="operations-cost-action-candidates" aria-label="정비 Action 후보">
          <strong>정비 Action 후보</strong>
          {actionCandidates.map((candidate) => (
            <button
              key={candidate.action_candidate_id}
              type="button"
              className={selectedActionCode === candidate.action_code ? "operations-button" : "operations-button ghost"}
              onClick={() => {
                setSelectedActionCode(candidate.action_code);
              }}
              disabled={submitting}
            >
              {ACTION_LABEL[candidate.action_code]}
            </button>
          ))}
        </div>
      ) : null}

      {selectedActionCode ? (
        <div className="operations-cost-inputs">
          <p>
            {selectedActionCode === "TOOL_REPLACEMENT"
              ? "인서트 1개 비용과 노무 기준은 Backend의 버전 관리 기준정보를 사용합니다."
              : "사내 냉각 경로 세척·막힘 해소·동작 확인 범위의 비용 기준은 Backend가 관리합니다. 부품 교체가 필요하면 이 기준을 사용할 수 없습니다."}
            {" "}{isImmediateCooling
              ? "현재 서버 시각에 따라 주간 또는 야간 요율이 자동 선택됩니다."
              : "즉시·12시간 후 비용 산정 가정 시각에 따라 주간 또는 야간 요율이 자동 선택됩니다."}
          </p>
          <small>참고 SOP: {sopId || "-"} · {sopVersion || "-"}</small>
          <button type="button" className="operations-button" disabled={Boolean(blocker) || loading || submitting} onClick={() => void calculate()}>
            {isImmediateCooling ? "즉시 복구 비용 확인" : "비용 분석 요청"}
          </button>
        </div>
      ) : null}

      {current ? (
        <div className="operations-cost-result">
          <header>
            <strong>
              {isImmediateCooling
                ? "즉시 냉각 복구 예상 비용"
                : `최근 분석 · ${selectedActionCode ? ACTION_LABEL[selectedActionCode] : "정비 Action"}`}
            </strong>
            <span>{visibleCalculationComplete ? "참고 계산 완료" : "입력 부족"}</span>
          </header>
          <small>{new Date(current.calculated_at).toLocaleString()} · {current.price_version}</small>
          <small>현재 운영 기준값 · 최종 비용은 사업장 견적·ERP·MES·급여 실적으로 재검증합니다.</small>
          <div className="operations-cost-options">
            {visibleOptions.map((option) => {
              const isLowest = !isImmediateCooling
                && option.option_id === current.lowest_calculated_cost_option_id;
              return (
                <article key={option.option_id}>
                  <div>
                    <strong>{ACTION_LABEL[option.action_code]} · {TIMING_LABEL[option.execution_timing]}</strong>
                    {isLowest ? <b>계산상 최저비용</b> : null}
                  </div>
                  <span>{formatWon(option.total_expected_cost?.base_minor)}</span>
                  {option.assumed_execution_at ? (
                    <small>
                      비용 산정 가정 {new Date(option.assumed_execution_at).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}
                      {option.labor_rate_base_minor_per_minute !== null && option.labor_rate_base_minor_per_minute !== undefined
                        ? ` · ${option.labor_rate_type === "night" ? "야간" : "주간"} ${option.labor_rate_base_minor_per_minute.toLocaleString()}원/분`
                        : ""}
                    </small>
                  ) : null}
                  <small>{option.expected_downtime ? `예상 정지 ${option.expected_downtime.base_minutes}분` : `부족: ${option.missing_inputs.join(", ")}`}</small>
                  <small>신뢰도: {CONFIDENCE_LABEL[option.confidence]}</small>
                </article>
              );
            })}
          </div>
          <p>
            {isImmediateCooling
              ? "냉각 전용 미래 위험 데이터가 없어 계획·미조치 비용은 표시하지 않습니다. 이 예상 비용은 정비 추천·승인·WorkOrder·실행을 생성하지 않는 참고 정보입니다."
              : "최저비용 표시는 현재 가정의 계산 참고값일 뿐입니다. 비용 분석은 정비 추천·승인·WorkOrder·실행을 생성하지 않습니다."}
          </p>
        </div>
      ) : null}
    </section>
  );
}
