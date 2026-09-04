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

const TIMING_LABEL: Record<MaintenanceExecutionTiming, [string, string]> = {
  immediate: ["즉시 정비", "Immediate maintenance"],
  planned_window: ["계획 정비 창", "Planned maintenance window"],
  reinspect_after: ["재점검 후", "After reinspection"],
  no_action_baseline: ["미조치 기준", "No-action baseline"],
};

const ACTION_LABEL: Record<MaintenanceActionCode, [string, string]> = {
  TOOL_REPLACEMENT: ["공구 교체", "Tool replacement"],
  COOLING_SYSTEM_RESTORE: ["냉각 시스템 복구", "Cooling system restore"],
};

const CONFIDENCE_LABEL = {
  high: ["높음", "High"],
  medium: ["보통", "Medium"],
  low: ["낮음", "Low"],
  insufficient: ["근거 부족", "Insufficient"],
} as const;

function localize(english: boolean, ko: string, en: string): string {
  return english ? en : ko;
}

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

function formatWon(value: number | null | undefined, english: boolean): string {
  if (value === null || value === undefined) return localize(english, "산정 불가", "Not calculable");
  return english ? `₩${value.toLocaleString("en-US")}` : `${value.toLocaleString("ko-KR")}원`;
}

export function MaintenanceCostDecisionPanel({
  projectId,
  workspaceId,
  eventId,
  guidance,
  locale = "ko-KR",
  onChanged,
  onEligibilityChanged,
}: {
  projectId: string;
  workspaceId: string;
  eventId: string;
  guidance: OperationsInspectionGuidance | null;
  locale?: "ko-KR" | "en-US";
  onChanged?: () => void;
  onEligibilityChanged?: (eligible: boolean) => void;
}) {
  const english = locale === "en-US";
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
      setError(caught instanceof Error ? caught.message : localize(english, "비용 분석 이력을 불러오지 못했습니다.", "Unable to load cost-analysis history."));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [english, projectId, workspaceId, eventId]);

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
      setError(localize(english, "점검에 참고한 SOP ID와 버전을 입력해 주세요.", "Enter the SOP ID and version referenced during inspection."));
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
      setError(caught instanceof Error ? caught.message : localize(english, "비용 분석을 실행하지 못했습니다.", "Unable to run the cost analysis."));
    } finally {
      setSubmitting(false);
    }
  };

  const blocker = actionCandidates.length === 0
      ? localize(english, "점검 결과에서 실행 가능한 정비 Action 후보가 확인되지 않았습니다.", "No executable maintenance action candidate was identified from the inspection result.")
    : !sopId.trim() || !sopVersion.trim()
      ? localize(english, "점검에 참고한 SOP 기준정보가 필요합니다.", "SOP reference information used for the inspection is required.")
    : null;
  if (loading || !inspection || !stageOpen) return null;

  return (
    <section className="operations-maintenance-cost-panel" aria-label={localize(english, "정비 비용 분석", "Maintenance cost analysis")}>
      <header>
        <Calculator size={14} />
        <strong>{isImmediateCooling ? localize(english, "즉시 복구 예상 비용", "Estimated immediate-recovery cost") : localize(english, "정비 비용 분석", "Maintenance cost analysis")}</strong>
        <button type="button" className="operations-icon-button" onClick={() => void load()} disabled={loading} aria-label={localize(english, "비용 분석 새로고침", "Refresh cost analysis")}>
          <RefreshCw size={13} />
        </button>
      </header>
      <p>
        {isImmediateCooling
          ? localize(english, "현재 데이터로 근거를 확인할 수 있는 즉시 냉각 복구 비용만 제공합니다. 버튼을 누르기 전에는 계산하지 않습니다.", "Only the immediate cooling-recovery cost supported by current evidence is provided. Nothing is calculated until you request it.")
          : localize(english, "점검 결과에서 확인된 정비 Action 후보의 비용만 비교합니다. 버튼을 누르기 전에는 분석하지 않습니다.", "Compares costs only for maintenance action candidates identified from the inspection result. Nothing is analyzed until you request it.")}
      </p>
      {blocker ? <small className="operations-cost-warning">{blocker}</small> : null}
      {error ? <small className="operations-cost-error">{error}</small> : null}

      {actionCandidates.length ? (
        <div className="operations-cost-action-candidates" aria-label={localize(english, "정비 Action 후보", "Maintenance action candidates")}>
          <strong>{localize(english, "정비 Action 후보", "Maintenance action candidates")}</strong>
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
              {ACTION_LABEL[candidate.action_code][english ? 1 : 0]}
            </button>
          ))}
        </div>
      ) : null}

      {selectedActionCode ? (
        <div className="operations-cost-inputs">
          <p>
            {selectedActionCode === "TOOL_REPLACEMENT"
              ? localize(english, "인서트 1개 비용과 노무 기준은 Backend의 버전 관리 기준정보를 사용합니다.", "Insert unit cost and labor rates use versioned backend reference data.")
              : localize(english, "사내 냉각 경로 세척·막힘 해소·동작 확인 범위의 비용 기준은 Backend가 관리합니다. 부품 교체가 필요하면 이 기준을 사용할 수 없습니다.", "Backend reference data covers in-house cooling-path cleaning, blockage removal, and operation verification. This basis is not valid when component replacement is required.")}
            {" "}{isImmediateCooling
              ? localize(english, "현재 서버 시각에 따라 주간 또는 야간 요율이 자동 선택됩니다.", "Day or night labor rate is selected from the current server time.")
              : localize(english, "즉시·12시간 후 비용 산정 가정 시각에 따라 주간 또는 야간 요율이 자동 선택됩니다.", "Day or night labor rate is selected from the assumed immediate or 12-hour execution time.")}
          </p>
          <small>{localize(english, "참고 SOP", "Reference SOP")}: {sopId || "-"} · {sopVersion || "-"}</small>
          <button type="button" className="operations-button" disabled={Boolean(blocker) || loading || submitting} onClick={() => void calculate()}>
            {isImmediateCooling ? localize(english, "즉시 복구 비용 확인", "Check immediate-recovery cost") : localize(english, "비용 분석 요청", "Run cost analysis")}
          </button>
        </div>
      ) : null}

      {current ? (
        <div className="operations-cost-result">
          <header>
            <strong>
              {isImmediateCooling
                ? localize(english, "즉시 냉각 복구 예상 비용", "Estimated immediate cooling-recovery cost")
                : `${localize(english, "최근 분석", "Latest analysis")} · ${selectedActionCode ? ACTION_LABEL[selectedActionCode][english ? 1 : 0] : localize(english, "정비 Action", "Maintenance action")}`}
            </strong>
            <span>{visibleCalculationComplete ? localize(english, "참고 계산 완료", "Reference calculation complete") : localize(english, "입력 부족", "Missing inputs")}</span>
          </header>
          <small>{new Date(current.calculated_at).toLocaleString(english ? "en-US" : "ko-KR")} · {current.price_version}</small>
          <small>{localize(english, "현재 운영 기준값 · 최종 비용은 사업장 견적·ERP·MES·급여 실적으로 재검증합니다.", "Current operational reference values · Final cost must be revalidated against site quotes, ERP, MES, and payroll actuals.")}</small>
          <div className="operations-cost-options">
            {visibleOptions.map((option) => {
              const isLowest = !isImmediateCooling
                && option.option_id === current.lowest_calculated_cost_option_id;
              return (
                <article key={option.option_id}>
                  <div>
                    <strong>{ACTION_LABEL[option.action_code][english ? 1 : 0]} · {TIMING_LABEL[option.execution_timing][english ? 1 : 0]}</strong>
                    {isLowest ? <b>{localize(english, "계산상 최저비용", "Lowest calculated cost")}</b> : null}
                  </div>
                  <span>{formatWon(option.total_expected_cost?.base_minor, english)}</span>
                  {option.assumed_execution_at ? (
                    <small>
                      {localize(english, "비용 산정 가정", "Cost assumption")} {new Date(option.assumed_execution_at).toLocaleString(english ? "en-US" : "ko-KR", { timeZone: "Asia/Seoul" })}
                      {option.labor_rate_base_minor_per_minute !== null && option.labor_rate_base_minor_per_minute !== undefined
                        ? english
                          ? ` · ${option.labor_rate_type === "night" ? "Night" : "Day"} ₩${option.labor_rate_base_minor_per_minute.toLocaleString("en-US")}/min`
                          : ` · ${option.labor_rate_type === "night" ? "야간" : "주간"} ${option.labor_rate_base_minor_per_minute.toLocaleString("ko-KR")}원/분`
                        : ""}
                    </small>
                  ) : null}
                  <small>{option.expected_downtime ? localize(english, `예상 정지 ${option.expected_downtime.base_minutes}분`, `Expected downtime ${option.expected_downtime.base_minutes} min`) : `${localize(english, "부족", "Missing")}: ${option.missing_inputs.join(", ")}`}</small>
                  <small>{localize(english, "신뢰도", "Confidence")}: {CONFIDENCE_LABEL[option.confidence][english ? 1 : 0]}</small>
                </article>
              );
            })}
          </div>
          <p>
            {isImmediateCooling
              ? localize(english, "냉각 전용 미래 위험 데이터가 없어 계획·미조치 비용은 표시하지 않습니다. 이 예상 비용은 정비 추천·승인·WorkOrder·실행을 생성하지 않는 참고 정보입니다.", "Planned and no-action costs are omitted because cooling-specific future-risk data is unavailable. This estimate is reference information only and does not create a recommendation, approval, WorkOrder, or execution.")
              : localize(english, "최저비용 표시는 현재 가정의 계산 참고값일 뿐입니다. 비용 분석은 정비 추천·승인·WorkOrder·실행을 생성하지 않습니다.", "The lowest-cost marker is only a calculation reference under the current assumptions. Cost analysis does not create a maintenance recommendation, approval, WorkOrder, or execution.")}
          </p>
        </div>
      ) : null}
    </section>
  );
}
