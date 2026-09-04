import {
  Activity,
  AlertTriangle,
  Boxes,
  BriefcaseBusiness,
  Building2,
  ChartNoAxesCombined,
  CircleDollarSign,
  ClipboardCheck,
  FileClock,
  FileText,
  Gauge,
  GitBranch,
  History,
  Info,
  ListChecks,
  PackageSearch,
  RadioTower,
  RotateCcw,
  ShieldAlert,
  TimerReset,
  TrendingDown,
  Wrench,
} from "lucide-react";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  createOperationsAgentReviewSummary,
  getOperationsAgentReviewSummary,
} from "../../../api";
import type { ReportType, Role } from "../../../types";
import { loadOperationsReportVariant } from "../../operations/api/operationsApi";
import type {
  OperationsAgentReviewSummaryResponse,
  OperationsAsset,
  OperationsBootstrapModel,
  OperationsCompanyContext,
  OperationsDecisionBriefRole,
  OperationsEvent,
  OperationsEventDetailModel,
  OperationsReportTab,
  OperationsRoleLens,
  OperationsView,
} from "../../operations/api/operationsContracts";
import {
  displayExplanationMethod,
  displayArtifactKind,
  displayEvidenceReference,
  displayInspectionAssociation,
  displayReportType,
  displaySensorFactorLabel,
  fieldFailureLabel,
} from "../../operations/displayLabels";
import { MaintenanceWorkflowActionPanel } from "../../operations/maintenance/MaintenanceWorkflowActionPanel";
import { MaintenanceCostDecisionPanel } from "../../operations/maintenance/MaintenanceCostDecisionPanel";
import { OperationalDecisionSupportPanel } from "../../operations/overview/OperationalDecisionSupportPanel";
import { useI18n } from "../../../ui/i18n/I18nProvider";
import { useDisplayPreferences } from "../../../ui/foundry/displayPreferences";
import type { ReliabilityExperienceKind } from "./roleExperience";
import {
  resolveReliabilityComposition,
  type ReliabilityBlockId,
} from "./roleComposition";
import "./role-composed-workspace.css";

const WorkspaceEnglishContext = createContext(false);

function useWorkspaceEnglish() {
  return useContext(WorkspaceEnglishContext);
}

function localized(english: boolean, ko: string, en: string) {
  return english ? en : ko;
}

function formatNumber(value: number, english: boolean, options?: Intl.NumberFormatOptions) {
  return value.toLocaleString(english ? "en-US" : "ko-KR", options);
}

interface RoleComposedWorkspaceProps {
  experienceKind: ReliabilityExperienceKind;
  view: OperationsView;
  surfaceId: string | null;
  model: OperationsBootstrapModel;
  selectedEvent: OperationsEvent | null;
  detail: OperationsEventDetailModel | null;
  detailLoading: boolean;
  companyContext: OperationsCompanyContext | null;
  role: OperationsRoleLens;
  currentUserId: string;
  canManageWorkflow: boolean;
  canExecuteFieldWorkflow: boolean;
  canMaterializeAgentSummary: boolean;
  onSelectEvent: (event: OperationsEvent) => void;
  onOpenAsset: (assetId: string, eventId: string | null) => void;
  onOpenReport: (
    eventId: string | null,
    assetId: string | null,
    reportTab?: OperationsReportTab,
  ) => void;
  onWorkflowChanged: () => void;
}

function Block({
  title,
  eyebrow,
  icon,
  guidance,
  className = "",
  children,
}: {
  title: string;
  eyebrow?: string;
  icon?: ReactNode;
  guidance?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`rw-composed-block ${className}`}>
      <header>
        {icon}
        <div>
          {eyebrow ? <span>{eyebrow}</span> : null}
          <strong>{title}</strong>
        </div>
        {guidance ? <GuidanceHint text={guidance} /> : null}
      </header>
      <div className="rw-composed-block__body">{children}</div>
    </section>
  );
}

function GuidanceHint({ text }: { text: string }) {
  const { preferences } = useDisplayPreferences();
  if (!preferences.showGuidance) return null;
  return (
    <span className="rw-guidance-hint">
      <button type="button" aria-label={text}>
        <Info size={13} aria-hidden="true" />
      </button>
      <span role="tooltip">{text}</span>
    </span>
  );
}

function probability(value: number | null | undefined) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

function money(value: number | null | undefined, english = false) {
  return typeof value === "number"
    ? english
      ? `₩${Math.round(value).toLocaleString("en-US")}`
      : `${Math.round(value).toLocaleString("ko-KR")}원`
    : "—";
}

function compactMoney(value: number | null | undefined, english = false) {
  if (typeof value !== "number") return "—";
  if (english) return `₩${Math.round(value).toLocaleString("en-US")}`;
  if (Math.abs(value) >= 100_000_000)
    return `${(value / 100_000_000).toFixed(1)}억원`;
  if (Math.abs(value) >= 10_000)
    return `${Math.round(value / 10_000).toLocaleString("ko-KR")}만원`;
  return money(value);
}

function dateTime(value: string | null | undefined, english = false) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString(english ? "en-US" : "ko-KR", {
        dateStyle: "short",
        timeStyle: "short",
      });
}

function minutesBetween(
  start: string | null | undefined,
  end: string | null | undefined,
): number | null {
  if (!start || !end) return null;
  const startMs = new Date(start).getTime();
  const endMs = new Date(end).getTime();
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs)
    return null;
  return Math.round((endMs - startMs) / 60_000);
}

function duration(value: number | null | undefined, english = false) {
  if (typeof value !== "number") return "—";
  if (value < 60) return english ? `${value} min` : `${value}분`;
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  return english
    ? (minutes ? `${hours}h ${minutes}m` : `${hours}h`)
    : (minutes ? `${hours}시간 ${minutes}분` : `${hours}시간`);
}

function decisionLabel(
  value: OperationsEvent["recommendedDecision"] | null | undefined,
  english = false,
) {
  const labels: Record<OperationsEvent["recommendedDecision"], [string, string]> = {
    continue_monitoring: ["계속 관찰", "Continue monitoring"],
    request_inspection: ["현장 점검 요청", "Request field inspection"],
    review_shutdown: ["정지 검토 요청", "Review shutdown"],
    hold_for_data_check: ["데이터 확인 후 판단", "Review after data check"],
  };
  return value ? labels[value][english ? 1 : 0] : localized(english, "판단 대기", "Decision pending");
}

function riskLabel(value: OperationsEvent["status"] | null | undefined, english = false) {
  if (value === "critical") return localized(english, "고위험", "Critical");
  if (value === "warning") return localized(english, "경고", "Warning");
  if (value === "attention") return localized(english, "주의", "Attention");
  if (value === "data_quality_hold") return localized(english, "데이터 확인 필요", "Data quality hold");
  if (value === "normal") return localized(english, "정상", "Normal");
  return localized(english, "상태 확인 중", "Status pending");
}

function ownerLabel(value: string | null | undefined, english = false) {
  if (!value || /unassigned|pending/i.test(value)) return localized(english, "담당 미지정", "Unassigned");
  return value;
}

function criticalityLabel(
  value: OperationsEvent["criticality"] | null | undefined,
  english = false,
) {
  if (value === "high") return localized(english, "높음", "High");
  if (value === "medium") return localized(english, "중간", "Medium");
  if (value === "low") return localized(english, "낮음", "Low");
  return localized(english, "확인 필요", "Needs review");
}

function operationalDecisionBriefRole(
  value: OperationsRoleLens,
): OperationsDecisionBriefRole {
  return value === "process_manager" ? "process_manager" : "process_engineer";
}

function factorDirectionLabel(value: "risk_up" | "risk_down", english = false) {
  return value === "risk_up"
    ? localized(english, "위험 증가 방향", "Risk increasing")
    : localized(english, "위험 감소 방향", "Risk decreasing");
}

const ENGLISH_SENSOR_LABELS: Record<string, string> = {
  rotation_raw: "Rotation average",
  vibration_raw: "Vibration average",
  pressure_raw: "Pressure average",
  air_temperature_k: "Intake air temperature",
  process_temperature_k: "Process temperature",
  rotational_speed_rpm: "Spindle speed",
  torque_nm: "Torque",
  tool_wear_min: "Tool wear",
  mechanical_power_w: "Motor power",
  power_w: "Motor power",
  overstrain_index: "Overstrain index",
  overstrain_load: "Overstrain index",
  temperature_difference_k: "Process-air temperature gap",
  temperature_gap_k: "Process-air temperature gap",
  generator_failure_score: "Model risk score",
  model_selected_threshold: "Risk decision threshold",
  asset_criticality_adjustment: "Asset criticality adjustment",
  generator_model_artifact_manifest: "Applied model release",
};

function englishSensorFactorLabel(key: string) {
  const windowMatch = key.match(/_(1h|6h|12h|24h|7d|30d)_(max_abs|abs_max|abs_mean|change|max|min|mean|std|last)$/);
  const currentMatch = key.match(/_(abs_current|current)$/);
  const baseKey = key
    .replace(/_(1h|6h|12h|24h|7d|30d)_(max_abs|abs_max|abs_mean|change|max|min|mean|std|last)$/, "")
    .replace(/_(abs_current|current)$/, "");
  const base = ENGLISH_SENSOR_LABELS[key] ?? ENGLISH_SENSOR_LABELS[baseKey] ?? baseKey.replaceAll("_", " ");
  if (windowMatch) {
    const [, window, aggregate] = windowMatch;
    const aggregateLabel: Record<string, string> = {
      max_abs: "max absolute",
      abs_max: "max absolute",
      abs_mean: "absolute average",
      change: "change",
      max: "max",
      min: "min",
      mean: "average",
      std: "variation",
      last: "latest",
    };
    return `${base} · ${window} ${aggregateLabel[aggregate] ?? aggregate}`;
  }
  if (currentMatch) return `${base} · ${currentMatch[1] === "abs_current" ? "current absolute" : "current"}`;
  return base;
}

function failureTypeLabel(value: string, english = false) {
  if (!english) return fieldFailureLabel(value);
  const labels: Record<string, string> = {
    failure_risk: "General failure risk",
    none: "No specific failure type",
    power_or_overstrain_failure: "Suspected drive overload",
    tool_wear_failure: "Suspected tool/die wear",
    heat_dissipation_failure: "Suspected cooling/heat dissipation issue",
    invalid_sensor_data: "Sensor data quality review",
    multi_factor_risk: "Suspected multi-factor risk",
    uncertain: "Uncertain failure type",
    unavailable: "Insufficient failure-type evidence",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function explanationMethodLabel(value: string | null | undefined, english = false) {
  if (!english) return displayExplanationMethod(value);
  if (!value) return null;
  if (value.includes("proxy_attribution") || value.includes("attribution")) return "Model contribution analysis";
  if (value.includes("shap")) return "Model impact analysis";
  return null;
}

function inspectionAssociationLabel(value: string | null | undefined, english = false) {
  if (!english) return displayInspectionAssociation(value);
  if (!value) return "Inspection method needs review";
  if (value === "inspection_candidate") return "Model-evidence inspection candidate";
  if (value === "inspection_required") return "Field inspection required";
  return value.replaceAll("_", " ");
}

function reportTypeLabel(value: string | null | undefined, english = false) {
  if (!english) return displayReportType(value);
  const labels: Record<string, string> = {
    "inspection-summary": "Inspection result summary",
    "operations-decision": "Operations decision report",
    "executive-brief": "Executive operations brief",
    "maintenance-effect": "Maintenance effect comparison",
    "weekly-risk": "Weekly operational risk",
  };
  return value ? (labels[value] ?? "Operations report") : "Report type needs review";
}

function artifactKindLabel(value: string | null | undefined, english = false) {
  if (!english) return displayArtifactKind(value);
  if (!value) return "Evidence bundle needs review";
  if (value.startsWith("pm-report:")) return "Current-case report draft";
  if (value.startsWith("RESULT#")) return "Selected-case prediction evidence";
  if (value.startsWith("result-artifact://")) return "Prediction-result evidence";
  return "Linked technical evidence";
}

function evidenceReferenceLabel(value: string | null | undefined, english = false) {
  if (!english) return displayEvidenceReference(value);
  if (!value) return "Linked operational evidence";
  const normalized = value.toLowerCase();
  if (normalized.includes("inspection")) return "Field inspection result";
  if (normalized.includes("maintenance")) return "Maintenance history and action result";
  if (normalized.includes("observation") || normalized.includes("sensor")) return "Asset sensor observation";
  if (normalized.includes("prediction") || normalized.includes("result")) return "Failure-risk prediction result";
  if (normalized.includes("model")) return "Applied model decision evidence";
  if (normalized.includes("work-order") || normalized.includes("work_order")) return "Linked work request";
  return "Linked operational evidence";
}

function waitingMinutes(value: string | null | undefined) {
  if (!value) return null;
  const start = Date.parse(value);
  if (!Number.isFinite(start)) return null;
  return Math.max(0, Math.round((Date.now() - start) / 60_000));
}

function workflowStatusLabel(value: string | null | undefined, english = false) {
  const labels: Record<string, [string, string]> = {
    requested: ["승인 대기", "Awaiting approval"],
    approved: ["승인됨", "Approved"],
    in_progress: ["진행 중", "In progress"],
    completed: ["완료", "Completed"],
    planned: ["계획됨", "Planned"],
    prediction: ["예측", "Prediction"],
    evidence: ["근거 확인", "Evidence review"],
    decision: ["운영 판단", "Decision"],
    inspection_requested: ["점검 요청", "Inspection requested"],
    inspection_approved: ["점검 승인", "Inspection approved"],
    inspection_in_progress: ["점검 중", "Inspection in progress"],
    inspection_completed: ["점검 완료", "Inspection completed"],
    recommendation_proposed: ["정비안 검토 대기", "Maintenance recommendation proposed"],
    maintenance_requested: ["정비 요청", "Maintenance requested"],
    maintenance_approved: ["정비 승인", "Maintenance approved"],
    maintenance_in_progress: ["정비 중", "Maintenance in progress"],
    maintenance_completed: ["정비 완료", "Maintenance completed"],
    post_maintenance_observation_pending: ["정비 후 관측 대기", "Post-maintenance observation pending"],
    ready_for_reprediction: ["재예측 가능", "Ready for re-prediction"],
  };
  return value ? (labels[value]?.[english ? 1 : 0] ?? value.replaceAll("_", " ")) : localized(english, "대기", "Pending");
}

function workflowActionLabel(
  action: { actionId: string; label?: string | null } | null | undefined,
  english = false,
) {
  if (!action) return null;
  if (!english) return action.label ?? action.actionId;
  const labels: Record<string, string> = {
    create_inspection_work_order: "Create inspection work request",
    request_inspection_work_order: "Create inspection work request",
    request_inspection: "Request inspection",
    approve_inspection_work_order: "Approve inspection work request",
    start_inspection_work_order: "Start inspection",
    start_inspection: "Start inspection",
    complete_inspection_work_order: "Record and complete inspection",
    complete_inspection: "Record and complete inspection",
    calculate_maintenance_cost: "Run maintenance cost analysis",
    create_operations_manual_recommendation: "Create maintenance recommendation",
    decide_operations_manual_recommendation: "Review maintenance recommendation",
    approve_maintenance_work_order: "Approve maintenance WorkOrder",
    start_maintenance_action: "Start maintenance",
    complete_maintenance_action: "Complete maintenance",
    request_maintenance_replay: "Resume post-maintenance observation",
  };
  return labels[action.actionId] ?? action.actionId.replaceAll("_", " ");
}

function average(values: Array<number | null | undefined>): number | null {
  const numeric = values.filter(
    (value): value is number =>
      typeof value === "number" && Number.isFinite(value),
  );
  if (!numeric.length) return null;
  return numeric.reduce((sum, value) => sum + value, 0) / numeric.length;
}

function maintenanceCompletedAt(
  detail: OperationsEventDetailModel | null,
): string | null {
  const eventTimes =
    detail?.closedLoop?.maintenanceEvents
      .map((item) => item.completedAt)
      .filter((value): value is string => Boolean(value)) ?? [];
  const actionTimes =
    detail?.closedLoop?.maintenanceActions
      .filter((item) => item.status === "completed")
      .map((item) => item.completedAt)
      .filter((value): value is string => Boolean(value)) ?? [];
  return [...eventTimes, ...actionTimes].sort().at(-1) ?? null;
}

function selectedAsset(
  model: OperationsBootstrapModel,
  selectedEvent: OperationsEvent | null,
): OperationsAsset | null {
  if (!selectedEvent) return null;
  return (
    model.assets.find((asset) => asset.assetId === selectedEvent.assetId) ??
    null
  );
}

function relevantMaterials(
  companyContext: OperationsCompanyContext | null,
  assetId: string | null | undefined,
) {
  if (!companyContext || !assetId) return [];
  return companyContext.materials.filter((item) =>
    item.related_asset_ids.includes(assetId),
  );
}

function exposure(input: {
  companyContext: OperationsCompanyContext | null;
  detail: OperationsEventDetailModel | null;
}) {
  const variant =
    input.detail?.operationContext?.eventImpact?.productVariant ?? null;
  const product =
    input.companyContext?.products.find((item) => item.variant === variant) ??
    null;
  const lostUnits =
    input.detail?.operationContext?.eventImpact?.estimatedLostUnits ?? null;
  const contributionExposure =
    product && typeof lostUnits === "number"
      ? product.unit_contribution_margin_krw * lostUnits
      : null;
  const revenueExposure =
    product && typeof lostUnits === "number"
      ? product.unit_sales_price_krw * lostUnits
      : null;
  return { product, lostUnits, contributionExposure, revenueExposure };
}

function RiskMetricsBlock({
  model,
  detail,
  compact = false,
}: {
  model: OperationsBootstrapModel;
  detail: OperationsEventDetailModel | null;
  compact?: boolean;
}) {
  const english = useWorkspaceEnglish();
  const activeWork = detail?.closedLoop?.workOrders.some((item) =>
    ["approved", "in_progress"].includes(item.status),
  )
    ? 1
    : 0;
  const allMetrics = [
    [localized(english, "전체 연결 설비", "Connected assets"), formatNumber(model.metrics.totalAssets, english)],
    [localized(english, "정상 설비", "Normal assets"), formatNumber(model.metrics.normal, english)],
    [
      localized(english, "주의 설비", "Attention assets"),
      formatNumber(model.metrics.attention + model.metrics.warning, english),
    ],
    [localized(english, "긴급 설비", "Critical assets"), formatNumber(model.metrics.critical, english)],
    [localized(english, "선택 Case 진행 작업", "Selected case work"), formatNumber(activeWork, english)],
    [localized(english, "판단 대기", "Decisions pending"), formatNumber(model.metrics.pendingDecisions, english)],
    [
      localized(english, "마지막 수신", "Last received"),
      dateTime(model.context.observedAt ?? model.context.refreshedAt, english),
    ],
  ];
  const metrics = compact
    ? allMetrics.filter(([label]) =>
        [
          localized(english, "긴급 설비", "Critical assets"),
          localized(english, "주의 설비", "Attention assets"),
          localized(english, "판단 대기", "Decisions pending"),
          localized(english, "마지막 수신", "Last received"),
        ].includes(label),
      )
    : allMetrics;
  return (
    <Block
      title={compact ? localized(english, "전체 운영 리스크", "Overall operational risk") : localized(english, "현재 운영 신호", "Current operating signals")}
      eyebrow="LIVE STATUS"
      icon={<Gauge size={15} />}
      guidance={localized(english, "전체 설비 상태와 선택 Case의 작업·판단 대기 규모를 한눈에 확인하는 운영 요약입니다.", "An operational summary of fleet status plus work and decision backlog for the selected case.")}
      className={compact ? "span-6 executive-summary-card" : "span-12"}
    >
      <div className="rw-composed-metrics">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
    </Block>
  );
}

function FactoryMapBlock({
  model,
  selectedEvent,
  onSelectEvent,
}: {
  model: OperationsBootstrapModel;
  selectedEvent: OperationsEvent | null;
  onSelectEvent: (event: OperationsEvent) => void;
}) {
  const english = useWorkspaceEnglish();
  const eventByAsset = new Map(
    model.events.map((event) => [event.assetId, event]),
  );
  const lines = [...new Set(model.assets.map((asset) => asset.line))].sort();
  return (
    <Block
      title={localized(english, "공장 설비 상태맵", "Factory equipment status map")}
      eyebrow="REAL-TIME FACTORY STATUS"
      icon={<Building2 size={15} />}
      guidance={localized(english, "라인별 설비의 현재 위험 상태와 고장 확률을 비교하고 클릭해 해당 Case로 전환합니다.", "Compares current risk state and failure probability by line; select an asset to open its case.")}
      className="span-12"
    >
      <div className="rw-factory-map">
        {lines.map((line) => {
          const assets = model.assets.filter((asset) => asset.line === line);
          return (
            <section key={line}>
              <header>
                <strong>{line}</strong>
                <span>{formatNumber(assets.length, english)} {english ? "assets" : "대"}</span>
              </header>
              <div>
                {assets.map((asset) => {
                  const event = eventByAsset.get(asset.assetId) ?? null;
                  return (
                    <button
                      key={asset.assetId}
                      type="button"
                      className={`status-${asset.status} ${selectedEvent?.assetId === asset.assetId ? "is-selected" : ""}`}
                      onClick={() => event && onSelectEvent(event)}
                      title={`${asset.displayName} · ${riskLabel(asset.status, english)} · ${probability(asset.failureProbability)}`}
                    >
                      <span>{asset.displayName}</span>
                      <i>{probability(asset.failureProbability)}</i>
                      {asset.status !== "normal" ? <b /> : null}
                    </button>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </Block>
  );
}

function shortTime(value: string | null | undefined, english = false) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleTimeString(english ? "en-US" : "ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
      });
}

function clampChart(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value));
}

function sampleTrendPoints<T>(points: T[], maxPoints = 150): T[] {
  if (points.length <= maxPoints) return points;
  const sampled: T[] = [];
  const seen = new Set<number>();
  const lastIndex = points.length - 1;
  for (let index = 0; index < maxPoints; index += 1) {
    const sourceIndex = Math.round((index / Math.max(1, maxPoints - 1)) * lastIndex);
    if (seen.has(sourceIndex)) continue;
    seen.add(sourceIndex);
    sampled.push(points[sourceIndex]);
  }
  if (sampled.at(-1) !== points[lastIndex]) sampled.push(points[lastIndex]);
  return sampled;
}

function trendSlope(values: number[]) {
  if (values.length < 2) return 0;
  return (values.at(-1)! - values[0]) / Math.max(1, values.length - 1);
}

function buildForecastBand(points: Array<{ x: number; upperY: number; lowerY: number }>, start: { x: number; y: number } | null) {
  if (!points.length || !start) return "";
  return [
    `M ${start.x.toFixed(1)} ${start.y.toFixed(1)}`,
    ...points.map((point) => `L ${point.x.toFixed(1)} ${point.upperY.toFixed(1)}`),
    ...[...points].reverse().map((point) => `L ${point.x.toFixed(1)} ${point.lowerY.toFixed(1)}`),
    "Z",
  ].join(" ");
}

function CompactRiskTrend({
  detail,
}: {
  detail: OperationsEventDetailModel | null;
}) {
  const english = useWorkspaceEnglish();
  const [activeIndex, setActiveIndex] = useState(0);
  if (!detail || detail.riskSeries.length < 2) return null;
  const history = [...detail.riskSeries].sort((left, right) =>
    left.observedAt.localeCompare(right.observedAt),
  );
  const currentAt = detail.event.observedAt;
  const lastHistoryAt = history.at(-1)?.observedAt ?? null;
  const series = [...history];
  if (
    currentAt &&
    detail.event.failureProbability !== null &&
    (!lastHistoryAt || Date.parse(currentAt) > Date.parse(lastHistoryAt))
  ) {
    series.push({
      observedAt: currentAt,
      failureProbability: detail.event.failureProbability,
      status:
        detail.event.status === "data_quality_hold"
          ? null
          : detail.event.status,
    });
  }
  const plottedSeries = sampleTrendPoints(series, 150);
  const values = series.map((point) => point.failureProbability);
  const anchors =
    typeof detail.threshold === "number"
      ? [...values, detail.threshold]
      : values;
  const min = Math.max(0, Math.min(...anchors) - 0.05);
  const max = Math.min(1, Math.max(...anchors) + 0.05);
  const range = max - min || 1;
  const color = "#285fcb";
  const chartWidth = 1040;
  const chartHeight = 260;
  const frame = { left: 48, right: 934, top: 34, bottom: 204 };
  const forecastRight = 1002;
  const xAxisY = chartHeight - 30;
  const xAxisTitleY = chartHeight - 10;
  const xAt = (index: number) =>
    frame.left +
    (index / Math.max(1, plottedSeries.length - 1)) * (frame.right - frame.left);
  const yAt = (value: number) =>
    frame.bottom - ((value - min) / range) * (frame.bottom - frame.top);
  const coords = plottedSeries.map((point, index) => ({
    ...point,
    x: xAt(index),
    y: yAt(point.failureProbability),
  }));
  const path = coords
    .map(
      (point, index) =>
        `${index ? "L" : "M"}${point.x.toFixed(1)},${point.y.toFixed(1)}`,
    )
    .join(" ");
  const safeIndex = Math.min(activeIndex, coords.length - 1);
  const activePoint = coords[safeIndex];
  const markerIndexes = new Set([0, safeIndex, coords.length - 1]);
  const move = (delta: number) =>
    setActiveIndex((index) =>
      Math.max(0, Math.min(coords.length - 1, index + delta)),
    );
  const activeLabel = `${dateTime(activePoint.observedAt, english)} · ${localized(english, "위험도", "Risk")} ${probability(activePoint.failureProbability)} · ${riskLabel(activePoint.status as OperationsEvent["status"] | null, english)}`;
  const livePoint = coords.at(-1) ?? null;
  const liveLabel = livePoint ? probability(livePoint.failureProbability) : "—";
  const livePillWidth = Math.min(78, Math.max(48, liveLabel.length * 8 + 18));
  const livePillX = livePoint
    ? clampChart(livePoint.x - livePillWidth / 2, frame.left + 4, forecastRight - livePillWidth - 4)
    : forecastRight - livePillWidth - 4;
  const livePillY = livePoint
    ? clampChart(livePoint.y - 32, frame.top + 3, frame.bottom - 32)
    : frame.top + 3;
  const recentFailureValues = plottedSeries.slice(-4).map((point) => point.failureProbability);
  const slope = trendSlope(recentFailureValues);
  const forecastPoints =
    livePoint
      ? [1, 2, 3].map((step) => {
          const x = frame.right + ((forecastRight - frame.right) * step) / 3;
          const center = clampChart(livePoint.failureProbability + slope * step, min, max);
          const spread = Math.max(range * 0.035 * step, 0.015 * step);
          return {
            x,
            center,
            y: yAt(center),
            upperY: yAt(clampChart(center + spread, min, max)),
            lowerY: yAt(clampChart(center - spread, min, max)),
          };
        })
      : [];
  const forecastBandPath = buildForecastBand(forecastPoints, livePoint);
  const forecastLinePoints =
    livePoint && forecastPoints.length
      ? [`${livePoint.x.toFixed(1)},${livePoint.y.toFixed(1)}`, ...forecastPoints.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)].join(" ")
      : "";
  return (
    <article className="asset-series-block is-primary is-live-chart rw-feature-risk-chart">
      <header className="asset-series-heading">
        <div><RotateCcw size={17} /><strong>{localized(english, "고장 위험 추세", "Failure-risk trend")}</strong></div>
        <span className="asset-baseline-key">
          <i style={{ background: color }} />
          {localized(english, "관측 이력 · 최신 관측", "Observation history · latest observation")}
          {" · "}
          {probability(detail.event.failureProbability)}
        </span>
      </header>
      <svg
        className="asset-series-chart"
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        role="img"
        tabIndex={0}
        aria-label={localized(english, `고장 위험 추세와 판단 임계값. 좌우 방향키로 ${formatNumber(coords.length, false)}개 관측을 탐색합니다.`, `Failure-risk trend and decision threshold. Use arrow keys to explore ${formatNumber(coords.length, true)} observations.`)}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight" || event.key === "ArrowUp") {
            event.preventDefault();
            move(1);
          } else if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
            event.preventDefault();
            move(-1);
          } else if (event.key === "Home") {
            event.preventDefault();
            setActiveIndex(0);
          } else if (event.key === "End") {
            event.preventDefault();
            setActiveIndex(coords.length - 1);
          }
        }}
      >
        <rect
          className="asset-chart-frame"
          x={frame.left}
          y={frame.top}
          width={frame.right - frame.left}
          height={frame.bottom - frame.top}
        />
        <rect
          className="asset-live-sweep"
          x={frame.left}
          y={frame.top}
          width={frame.right - frame.left}
          height={frame.bottom - frame.top}
        />
        <rect
          className="asset-forecast-lane"
          x={frame.right}
          y={frame.top}
          width={forecastRight - frame.right}
          height={frame.bottom - frame.top}
        />
        <line
          className="asset-chart-grid"
          x1={frame.left}
          x2={frame.right}
          y1={yAt((min + max) / 2)}
          y2={yAt((min + max) / 2)}
        />
        {typeof detail.threshold === "number" ? (
          <>
            <line
          className="rw-feature-threshold-line"
              x1={frame.left}
              x2={frame.right}
              y1={yAt(detail.threshold)}
              y2={yAt(detail.threshold)}
            />
            <text
              className="rw-feature-threshold-label"
              x={frame.right - 2}
              y={yAt(detail.threshold) - 3}
              textAnchor="end"
            >
              {localized(english, "판단 경계", "Decision threshold")} {Math.round(detail.threshold * 100)}%
            </text>
          </>
        ) : null}
        <path className="asset-series-line" d={path} style={{ stroke: color }} />
        {forecastBandPath ? <path className="asset-forecast-band" d={forecastBandPath} /> : null}
        {forecastLinePoints ? <polyline className="asset-forecast-line" points={forecastLinePoints} style={{ stroke: color }} /> : null}
        {forecastPoints.length ? (
          <text
            className="asset-forecast-label"
            x={forecastRight}
            y={frame.bottom - 9}
            textAnchor="end"
          >
            {localized(english, "단기 추세 범위", "Short-term range")}
          </text>
        ) : null}
        {livePoint ? (
          <g className="asset-live-layer">
            <line
              className="asset-live-cursor"
              x1={livePoint.x}
              x2={livePoint.x}
              y1={frame.top}
              y2={frame.bottom}
            />
            <circle className="asset-live-ring" cx={livePoint.x} cy={livePoint.y} r="9" style={{ stroke: color }} />
            <circle className="asset-live-dot" cx={livePoint.x} cy={livePoint.y} r="4.8" style={{ fill: color }} />
            <g className="asset-live-value-pill is-top" transform={`translate(${livePillX} ${livePillY})`}>
              <rect width={livePillWidth} height="26" rx="7" />
              <text x={livePillWidth / 2} y="17" textAnchor="middle">
                {liveLabel}
              </text>
            </g>
          </g>
        ) : null}
        {coords.map((point, index) => markerIndexes.has(index) || point.status !== "normal" ? (
          <g key={`${point.observedAt}-${index}`}>
            <circle
              className={`rw-feature-point quality-${point.status ?? "unknown"}`}
              cx={point.x}
              cy={point.y}
              r={index === coords.length - 1 ? 3.4 : 2.2}
            />
            <circle
              className={`rw-feature-hit ${index === safeIndex ? "is-keyboard-active" : ""}`}
              cx={point.x}
              cy={point.y}
              r="8"
            >
              <title>{`${dateTime(point.observedAt, english)} · ${localized(english, "위험도", "Risk")} ${probability(point.failureProbability)} · ${riskLabel(point.status as OperationsEvent["status"] | null, english)}`}</title>
            </circle>
          </g>
        ) : null)}
        <text
          className="asset-chart-axis"
          x={frame.left}
          y={xAxisY}
          textAnchor="start"
        >
          {shortTime(plottedSeries[0]?.observedAt, english)}
        </text>
        <text
          className="asset-chart-axis"
          x={frame.right}
          y={xAxisY}
          textAnchor="end"
        >
          {shortTime(plottedSeries.at(-1)?.observedAt, english)}
        </text>
        <text
          className="asset-chart-axis"
          x={forecastRight}
          y={xAxisY}
          textAnchor="end"
        >
          +30s
        </text>
        <text className="asset-chart-axis-title" x={chartWidth / 2} y={xAxisTitleY} textAnchor="middle">{localized(english, "시간", "Time")}</text>
      </svg>
      <span className="rw-chart-keyboard-value" aria-live="polite">
        {localized(english, "선택 관측", "Selected observation")} · {activeLabel}
      </span>
      <small>
        {lastHistoryAt &&
        currentAt &&
        Date.parse(currentAt) > Date.parse(lastHistoryAt)
          ? localized(english, "현재값은 history plot 이후 새 관측으로 이어 표시합니다.", "The current value continues after the history plot as a new observation.")
          : localized(english, "현재 Case의 고정 관측 기준입니다.", "This is the selected case's fixed observation basis.")}
      </small>
    </article>
  );
}

function SensorTrendChart({
  sensor,
}: {
  sensor: OperationsEventDetailModel["sensors"][number];
}) {
  const english = useWorkspaceEnglish();
  const [activeIndex, setActiveIndex] = useState(0);
  const points = sensor.historyPoints ?? [];
  const numericHistory = points.filter(
    (point): point is typeof point & { value: number } =>
      typeof point.value === "number" && Number.isFinite(point.value),
  );
  const numericPoints = [...numericHistory];
  const latestHistory = numericHistory.at(-1) ?? null;
  if (
    typeof sensor.value === "number" &&
    sensor.observedAt &&
    (!latestHistory ||
      Date.parse(sensor.observedAt) > Date.parse(latestHistory.observedAt))
  ) {
    numericPoints.push({
      observedAt: sensor.observedAt,
      value: sensor.value,
      qualityStatus: sensor.qualityStatus ?? "unknown",
    });
  }
  if (numericPoints.length < 2) return null;
  const values = numericPoints.map((point) => point.value);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const plottedPoints = sampleTrendPoints(numericPoints, 150);
  const color = sensor.label.includes("진동") || sensor.label.includes("토크") ? "#a7630c" : "#285fcb";
  const chartWidth = 1040;
  const chartHeight = 260;
  const frame = { left: 48, right: 934, top: 34, bottom: 204 };
  const forecastRight = 1002;
  const xAxisY = chartHeight - 30;
  const xAxisTitleY = chartHeight - 10;
  const xAt = (index: number) =>
    frame.left +
    (index / Math.max(1, plottedPoints.length - 1)) *
      (frame.right - frame.left);
  const yAt = (value: number) =>
    frame.bottom - ((value - minimum) / range) * (frame.bottom - frame.top);
  const coords = plottedPoints.map((point, index) => ({
    ...point,
    x: xAt(index),
    y: yAt(point.value),
  }));
  const path = coords
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"}${point.x.toFixed(1)},${point.y.toFixed(1)}`,
    )
    .join(" ");
  const yTicks = [maximum, (minimum + maximum) / 2, minimum];
  const middleIndex = Math.floor((plottedPoints.length - 1) / 2);
  const coverage = sensor.historyWindow?.coverageStatus;
  const safeIndex = Math.min(activeIndex, coords.length - 1);
  const activePoint = coords[safeIndex];
  const markerIndexes = new Set([0, safeIndex, coords.length - 1]);
  const qualityLabel = (quality: string) => quality === "bad"
    ? localized(english, "불량", "Bad")
    : quality === "good"
      ? localized(english, "정상", "Good")
      : localized(english, "미확인", "Unknown");
  const activeLabel = `${dateTime(activePoint.observedAt, english)} · ${formatNumber(activePoint.value, english, { maximumFractionDigits: 3 })}${sensor.unit ? ` ${sensor.unit}` : ""} · ${localized(english, "품질", "Quality")} ${qualityLabel(activePoint.qualityStatus)}`;
  const move = (delta: number) =>
    setActiveIndex((index) =>
      Math.max(0, Math.min(coords.length - 1, index + delta)),
    );
  const livePoint = coords.at(-1) ?? null;
  const liveValueLabel = livePoint
    ? `${formatNumber(livePoint.value, english, { maximumFractionDigits: 2 })}${sensor.unit ? ` ${sensor.unit}` : ""}`
    : "—";
  const livePillWidth = Math.min(116, Math.max(52, liveValueLabel.length * 7.4 + 18));
  const livePillX = livePoint
    ? clampChart(livePoint.x - livePillWidth / 2, frame.left + 4, forecastRight - livePillWidth - 4)
    : forecastRight - livePillWidth - 4;
  const livePillY = livePoint
    ? clampChart(livePoint.y - 32, frame.top + 3, frame.bottom - 32)
    : frame.top + 3;
  const recentValues = plottedPoints.slice(-4).map((point) => point.value);
  const slope = trendSlope(recentValues);
  const forecastPoints =
    livePoint
      ? [1, 2, 3].map((step) => {
          const x = frame.right + ((forecastRight - frame.right) * step) / 3;
          const center = clampChart(livePoint.value + slope * step, minimum, maximum);
          const spread = Math.max(range * 0.035 * step, Math.abs(livePoint.value || 1) * 0.012 * step);
          return {
            x,
            center,
            y: yAt(center),
            upperY: yAt(clampChart(center + spread, minimum, maximum)),
            lowerY: yAt(clampChart(center - spread, minimum, maximum)),
          };
        })
      : [];
  const forecastBandPath = buildForecastBand(forecastPoints, livePoint);
  const forecastLinePoints =
    livePoint && forecastPoints.length
      ? [`${livePoint.x.toFixed(1)},${livePoint.y.toFixed(1)}`, ...forecastPoints.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`)].join(" ")
      : "";
  return (
    <article className="asset-series-block is-live-chart">
      <header className="asset-series-heading">
        <div><RotateCcw size={17} /><strong>{sensor.label}</strong></div>
        <span className="asset-baseline-key">
          <i style={{ background: color }} />
          {localized(english, "관측 이력 · 최신 관측", "Observation history · latest observation")}
          {" · "}
          {String(sensor.value ?? "—")}
          {sensor.unit ? ` ${sensor.unit}` : ""}
        </span>
      </header>
      <svg
        className="asset-series-chart"
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        role="img"
        tabIndex={0}
        aria-label={localized(english, `${sensor.label} 최근 추세. 좌우 방향키로 ${formatNumber(coords.length, false)}개 관측을 탐색합니다.`, `${sensor.label} recent trend. Use arrow keys to explore ${formatNumber(coords.length, true)} observations.`)}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight" || event.key === "ArrowUp") {
            event.preventDefault();
            move(1);
          } else if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
            event.preventDefault();
            move(-1);
          } else if (event.key === "Home") {
            event.preventDefault();
            setActiveIndex(0);
          } else if (event.key === "End") {
            event.preventDefault();
            setActiveIndex(coords.length - 1);
          }
        }}
      >
        <rect
          className="asset-chart-frame"
          x={frame.left}
          y={frame.top}
          width={frame.right - frame.left}
          height={frame.bottom - frame.top}
        />
        <rect
          className="asset-live-sweep"
          x={frame.left}
          y={frame.top}
          width={frame.right - frame.left}
          height={frame.bottom - frame.top}
        />
        <rect
          className="asset-forecast-lane"
          x={frame.right}
          y={frame.top}
          width={forecastRight - frame.right}
          height={frame.bottom - frame.top}
        />
        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              className="asset-chart-grid"
              x1={frame.left}
              x2={frame.right}
              y1={yAt(tick)}
              y2={yAt(tick)}
            />
            <text
              className="asset-chart-axis"
              x="48"
              y={clampChart(yAt(tick) + 3, frame.top + 8, frame.bottom + 2)}
              textAnchor="end"
            >
              {formatNumber(tick, english, { maximumFractionDigits: 1 })}
            </text>
          </g>
        ))}
        <path className="asset-series-line" d={path} style={{ stroke: color }} />
        {forecastBandPath ? <path className="asset-forecast-band" d={forecastBandPath} /> : null}
        {forecastLinePoints ? <polyline className="asset-forecast-line" points={forecastLinePoints} style={{ stroke: color }} /> : null}
        {forecastPoints.length ? (
          <text
            className="asset-forecast-label"
            x={forecastRight}
            y={frame.bottom - 9}
            textAnchor="end"
          >
            {localized(english, "단기 추세 범위", "Short-term range")}
          </text>
        ) : null}
        {livePoint ? (
          <g className="asset-live-layer">
            <line
              className="asset-live-cursor"
              x1={livePoint.x}
              x2={livePoint.x}
              y1={frame.top}
              y2={frame.bottom}
            />
            <circle className="asset-live-ring" cx={livePoint.x} cy={livePoint.y} r="9" style={{ stroke: color }} />
            <circle className="asset-live-dot" cx={livePoint.x} cy={livePoint.y} r="4.8" style={{ fill: color }} />
            <g className="asset-live-value-pill is-top" transform={`translate(${livePillX} ${livePillY})`}>
              <rect width={livePillWidth} height="26" rx="7" />
              <text x={livePillWidth / 2} y="17" textAnchor="middle">
                {liveValueLabel}
              </text>
            </g>
          </g>
        ) : null}
        {coords.map((point, index) => markerIndexes.has(index) || point.qualityStatus !== "good" ? (
          <g key={`${sensor.id}-${point.observedAt}-${index}`}>
            <circle
              className={`rw-feature-point quality-${point.qualityStatus}`}
              cx={point.x}
              cy={point.y}
              r={
                point.qualityStatus === "bad"
                  ? 3.5
                  : point.qualityStatus === "unknown"
                    ? 3
                    : index === coords.length - 1
                      ? 3.2
                      : 2.2
              }
            />
            <circle
              className={`rw-feature-hit ${index === safeIndex ? "is-keyboard-active" : ""}`}
              cx={point.x}
              cy={point.y}
              r="8"
            >
              <title>{`${dateTime(point.observedAt, english)} · ${formatNumber(point.value, english, { maximumFractionDigits: 3 })}${sensor.unit ? ` ${sensor.unit}` : ""} · ${localized(english, "품질", "Quality")} ${qualityLabel(point.qualityStatus)}`}</title>
            </circle>
          </g>
        ) : null)}
        {plottedPoints[0] ? (
          <text
            className="asset-chart-axis"
            x={frame.left}
            y={xAxisY}
            textAnchor="start"
          >
            {shortTime(plottedPoints[0].observedAt, english)}
          </text>
        ) : null}
        {plottedPoints.length > 2 ? (
          <text
            className="asset-chart-axis"
            x={xAt(middleIndex)}
            y={xAxisY}
            textAnchor="middle"
          >
            {shortTime(plottedPoints[middleIndex].observedAt, english)}
          </text>
        ) : null}
        {plottedPoints.at(-1) ? (
          <text
            className="asset-chart-axis"
            x={frame.right}
            y={xAxisY}
            textAnchor="end"
          >
            {shortTime(plottedPoints.at(-1)?.observedAt, english)}
          </text>
        ) : null}
        <text
          className="asset-chart-axis"
          x={forecastRight}
          y={xAxisY}
          textAnchor="end"
        >
          +30s
        </text>
        <text className="asset-chart-axis-title" x={chartWidth / 2} y={xAxisTitleY} textAnchor="middle">{localized(english, "시간", "Time")}</text>
      </svg>
      <span className="rw-chart-keyboard-value" aria-live="polite">
        {localized(english, "선택 관측", "Selected observation")} · {activeLabel}
      </span>
      <small>
        {english ? `History ${formatNumber(numericHistory.length, true)} · last plot ` : `history ${formatNumber(numericHistory.length, false)}개 · plot 마지막 `}
        {dateTime(latestHistory?.observedAt, english)}
        {sensor.observedAt &&
        latestHistory &&
        Date.parse(sensor.observedAt) > Date.parse(latestHistory.observedAt)
          ? (english ? ` · current value ${dateTime(sensor.observedAt, true)} is after the plot` : ` · 현재값 ${dateTime(sensor.observedAt, false)}는 plot 이후 관측`)
          : ""}
      </small>
    </article>
  );
}

function FeatureTrendLoadingPlaceholder() {
  return (
    <div className="rw-feature-trends is-loading" aria-busy="true">
      {[0, 1, 2].map((index) => (
        <article className="rw-feature-trend-skeleton" key={index}>
          <header>
            <div>
              <span />
              <strong />
            </div>
            <b />
          </header>
          <div>
            <i />
            <i />
            <i />
          </div>
        </article>
      ))}
    </div>
  );
}

function FeatureTrendBlock({
  detail,
  loading,
}: {
  detail: OperationsEventDetailModel | null;
  loading?: boolean;
}) {
  const english = useWorkspaceEnglish();
  const sensors =
    detail?.sensors
      .filter((sensor) => (sensor.historyPoints?.length ?? 0) > 1)
      .slice(0, 4) ?? [];
  const hasChartData = Boolean(detail?.riskSeries.length || sensors.length);
  return (
    <Block
      title={localized(english, "실시간 피쳐 그래프", "Live feature trends")}
      eyebrow="FEATURE TREND"
      icon={<RadioTower size={15} />}
      guidance={localized(english, "선택 Case의 고장 위험과 주요 센서 시계열을 같은 관측 기준으로 비교합니다. 예측 구간은 단기 추세 참고값입니다.", "Compares failure risk and key sensor time series on the selected case's observation basis. Forecast ranges are short-term trend references only.")}
      className="span-12"
    >
      {loading && !hasChartData ? (
        <FeatureTrendLoadingPlaceholder />
      ) : hasChartData ? (
        <div className="rw-feature-trends operations-side-map-report">
          <CompactRiskTrend detail={detail} />
          {sensors.map((sensor) => (
            <SensorTrendChart key={sensor.id} sensor={sensor} />
          ))}
        </div>
      ) : (
        <Empty text={localized(english, "선택 설비의 시계열 관측이 준비되면 핵심 피쳐 2~4개를 표시합니다.", "Two to four key features will appear when time-series observations are ready for the selected asset.")} />
      )}
    </Block>
  );
}

function BusinessKpisBlock({
  context,
}: {
  context: OperationsCompanyContext | null;
}) {
  const english = useWorkspaceEnglish();
  return (
    <Block
      title={localized(english, "경영 KPI 기준", "Business KPI basis")}
      eyebrow="BUSINESS CONTEXT"
      icon={<BriefcaseBusiness size={15} />}
      guidance={localized(english, "현재 운영 판단을 경영 지표와 연결하기 위한 회사 기준 KPI 문맥입니다.", "Company KPI context used to connect the current operational decision to business impact.")}
      className="span-6"
    >
      {context?.business_metrics.length ? (
        <div className="rw-composed-list">
          {context.business_metrics.slice(0, 4).map((item) => (
            <article key={item.id}>
              <div>
                <strong>{item.name}</strong>
                <small>
                  {item.period} · {item.source_label}
                </small>
              </div>
              <b>
                {item.unit === "KRW"
                  ? compactMoney(item.value, english)
                  : `${formatNumber(item.value, english)} ${item.unit}`}
              </b>
            </article>
          ))}
        </div>
      ) : (
        <Empty text={localized(english, "경영 KPI 문맥을 불러오는 중입니다.", "Loading business KPI context.")} />
      )}
    </Block>
  );
}

function OperationalKpisBlock({
  model,
  detail,
  companyContext,
}: {
  model: OperationsBootstrapModel;
  detail: OperationsEventDetailModel | null;
  companyContext: OperationsCompanyContext | null;
}) {
  const english = useWorkspaceEnglish();
  const firstDecision =
    detail?.activity
      .filter((item) => item.kind === "decision")
      .sort((left, right) =>
        left.createdAt.localeCompare(right.createdAt),
      )[0] ?? null;
  const recommendationDecisionActivity =
    detail?.closedLoop?.activities
      .filter(
        (item) =>
          item.activityType === "recommendation.decided" && item.createdAt,
      )
      .sort((left, right) =>
        String(left.createdAt).localeCompare(String(right.createdAt)),
      )[0] ?? null;
  const inspectionWorkOrder =
    detail?.closedLoop?.workOrders
      .filter((item) => item.workType === "inspection" && item.createdAt)
      .sort((left, right) =>
        String(left.createdAt).localeCompare(String(right.createdAt)),
      )[0] ?? null;
  const inspectionResult =
    detail?.closedLoop?.inspectionResults
      .filter((item) => item.recordedAt)
      .sort((left, right) =>
        String(left.recordedAt).localeCompare(String(right.recordedAt)),
      )[0] ?? null;
  const maintenanceApprovalActivity =
    detail?.closedLoop?.activities
      .filter(
        (item) =>
          item.activityType === "work_order.approved" &&
          item.workType === "maintenance" &&
          item.createdAt,
      )
      .sort((left, right) =>
        String(left.createdAt).localeCompare(String(right.createdAt)),
      )[0] ?? null;
  const maintenanceWorkOrder =
    detail?.closedLoop?.workOrders
      .filter(
        (item) =>
          item.workType === "maintenance" &&
          ["approved", "in_progress", "completed"].includes(item.status),
      )
      .sort((left, right) =>
        String(left.updatedAt ?? left.createdAt).localeCompare(
          String(right.updatedAt ?? right.createdAt),
        ),
      )[0] ?? null;
  const maintenanceAction =
    detail?.closedLoop?.maintenanceActions
      .filter((item) => item.startedAt)
      .sort((left, right) =>
        String(left.startedAt).localeCompare(String(right.startedAt)),
      )[0] ?? null;
  const value = exposure({ detail, companyContext });
  const decisionLeadTime = minutesBetween(
    detail?.event.observedAt,
    firstDecision?.createdAt ?? recommendationDecisionActivity?.createdAt,
  );
  const inspectionLeadTime = minutesBetween(
    inspectionWorkOrder?.createdAt,
    inspectionResult?.recordedAt,
  );
  const maintenanceLeadTime = minutesBetween(
    maintenanceApprovalActivity?.createdAt ??
      maintenanceWorkOrder?.updatedAt ??
      maintenanceWorkOrder?.createdAt,
    maintenanceAction?.startedAt,
  );
  const repeatedMaintenance = detail?.event.assetId
    ? (companyContext?.maintenance_records.filter(
        (item) => item.asset_id === detail.event.assetId,
      ).length ?? 0)
    : 0;
  const metrics = [
    ["Decision Lead Time", duration(decisionLeadTime, english)],
    [
      localized(english, "보고 검토 상태", "Report review status"),
      detail?.report.revision && detail.report.revision > 0
        ? `rev ${detail.report.revision}`
        : localized(english, "검토 전", "Not reviewed"),
    ],
    [localized(english, "점검 처리 시간", "Inspection turnaround"), duration(inspectionLeadTime, english)],
    [localized(english, "승인→정비 착수", "Approval → maintenance start"), duration(maintenanceLeadTime, english)],
    [
      localized(english, "판단 Backlog", "Decision backlog"),
      `${formatNumber(model.metrics.pendingDecisions, english)}${english ? " cases" : "건"}`,
    ],
    [
      localized(english, "생산 손실 노출", "Production-loss exposure"),
      value.lostUnits !== null
        ? `${formatNumber(value.lostUnits, english)}${english ? " units" : "개"}`
        : "—",
    ],
    [localized(english, "공헌이익 노출", "Contribution-margin exposure"), compactMoney(value.contributionExposure, english)],
    [localized(english, "동일 설비 과거 정비", "Prior maintenance on asset"), `${formatNumber(repeatedMaintenance, english)}${english ? " records" : "건"}`],
  ];
  const missingEvidence = [
    decisionLeadTime === null ? "Decision Lead Time" : null,
    inspectionLeadTime === null
      ? localized(english, "점검 처리 시간(점검 결과 기록 후 계산)", "Inspection turnaround (available after inspection result)")
      : null,
    maintenanceLeadTime === null ? localized(english, "승인→정비 착수(정비 승인 후 계산)", "Approval → maintenance start (available after approval)") : null,
    value.lostUnits === null ? localized(english, "생산 손실", "Production loss") : null,
    value.contributionExposure === null ? localized(english, "공헌이익 노출", "Contribution-margin exposure") : null,
  ].filter((item): item is string => Boolean(item));
  return (
    <Block
      title={localized(english, "운영 의사결정 KPI", "Operational decision KPIs")}
      eyebrow="CASE OPERATING KPI"
      icon={<TimerReset size={15} />}
      guidance={localized(english, "선택 Case의 판단·점검·정비 흐름에서 실제로 계산 가능한 리드타임과 손실 노출만 표시합니다.", "Shows only lead times and loss exposure that can be calculated from the selected case's decision, inspection, and maintenance evidence.")}
      className="span-12"
    >
      <div className="rw-operational-kpis">
        {metrics.map(([label, valueLabel]) => (
          <article key={label}>
            <span>{label}</span>
            <strong>{valueLabel}</strong>
          </article>
        ))}
      </div>
      {missingEvidence.length ? (
        <p className="rw-kpi-data-notice">
          {localized(english, "현재 Case에서 아직 연결되지 않은 KPI 근거:", "KPI evidence not yet connected for this case:")}{" "}
          {missingEvidence.join(" · ")}
        </p>
      ) : null}
    </Block>
  );
}

function RiskPortfolioBlock({
  model,
  onSelectEvent,
}: {
  model: OperationsBootstrapModel;
  onSelectEvent: (event: OperationsEvent) => void;
}) {
  const english = useWorkspaceEnglish();
  const ranked = [...model.events]
    .sort((a, b) => (b.failureProbability ?? -1) - (a.failureProbability ?? -1))
    .slice(0, 6);
  return (
    <Block
      title={localized(english, "운영 리스크 포트폴리오", "Operational risk portfolio")}
      eyebrow="RISK PORTFOLIO"
      icon={<ChartNoAxesCombined size={15} />}
      guidance={localized(english, "고장 확률이 높은 이벤트를 우선순위 순으로 비교해 어떤 Case를 먼저 볼지 판단합니다.", "Ranks high-risk events to help decide which case should be reviewed first.")}
      className="span-6"
    >
      <div className="rw-composed-list">
        {ranked.map((event) => (
          <button
            type="button"
            key={event.eventId}
            onClick={() => onSelectEvent(event)}
          >
            <div>
              <strong>{event.assetName}</strong>
              <small>
                {event.line} · {riskLabel(event.status, english)}
              </small>
            </div>
            <b>{probability(event.failureProbability)}</b>
          </button>
        ))}
      </div>
    </Block>
  );
}

function LineRiskBlock({ model }: { model: OperationsBootstrapModel }) {
  const english = useWorkspaceEnglish();
  return (
    <Block
      title={localized(english, "라인별 위험", "Risk by line")}
      eyebrow="LINE RISK"
      icon={<Activity size={15} />}
      guidance={localized(english, "라인 단위 평균 위험도를 비교해 위험이 특정 설비에 국한됐는지 라인 전체로 확산됐는지 확인합니다.", "Compares average risk by line to show whether risk is isolated to one asset or broader across a line.")}
      className="span-6"
    >
      <div className="rw-composed-bars">
        {model.lineRisk.slice(0, 8).map((line) => (
          <div key={line.line}>
            <span>{line.line}</span>
            <i>
              <b
                style={{
                  width: `${Math.max(3, (line.averageRisk ?? 0) * 100)}%`,
                }}
              />
            </i>
            <strong>{probability(line.averageRisk)}</strong>
          </div>
        ))}
      </div>
    </Block>
  );
}

function RiskQueueBlock({
  model,
  onSelectEvent,
}: {
  model: OperationsBootstrapModel;
  onSelectEvent: (event: OperationsEvent) => void;
}) {
  const english = useWorkspaceEnglish();
  const ranked = [...model.events]
    .sort((a, b) => (b.failureProbability ?? -1) - (a.failureProbability ?? -1))
    .slice(0, 7);
  return (
    <Block
      title={localized(english, "우선 확인 큐", "Priority review queue")}
      eyebrow="PRIORITY QUEUE"
      icon={<ShieldAlert size={15} />}
      guidance={localized(english, "위험도와 담당 정보를 함께 보여 현장 엔지니어가 먼저 확인할 설비 순서를 정합니다.", "Combines risk and ownership to prioritize which assets a field engineer should review first.")}
      className="span-6"
    >
      <div className="rw-composed-list">
        {ranked.map((event) => (
          <button
            type="button"
            key={event.eventId}
            onClick={() => onSelectEvent(event)}
          >
            <div>
              <strong>{event.assetName}</strong>
              <small>
                {failureTypeLabel(event.predictedFailureType, english)} ·{" "}
                {ownerLabel(event.assignedEngineer, english)}
              </small>
            </div>
            <b>{probability(event.failureProbability)}</b>
          </button>
        ))}
      </div>
    </Block>
  );
}

function AssetBriefBlock({
  model,
  event,
  onOpenAsset,
}: {
  model: OperationsBootstrapModel;
  event: OperationsEvent | null;
  onOpenAsset: (assetId: string, eventId: string | null) => void;
}) {
  const english = useWorkspaceEnglish();
  const asset = selectedAsset(model, event);
  return (
    <Block
      title={localized(english, "선택 설비", "Selected asset")}
      eyebrow="ASSET CONTEXT"
      icon={<Boxes size={15} />}
      guidance={localized(english, "현재 선택한 설비의 위치·중요도·담당·위험·예상 정지를 Case 문맥으로 요약합니다.", "Summarizes the selected asset's location, criticality, owner, risk, and expected downtime as case context.")}
      className="span-6"
    >
      {asset ? (
        <div className="rw-composed-kv">
          <div>
            <span>{localized(english, "설비", "Asset")}</span>
            <strong>{asset.displayName}</strong>
          </div>
          <div>
            <span>{localized(english, "라인", "Line")}</span>
            <strong>{asset.line}</strong>
          </div>
          <div>
            <span>{localized(english, "중요도", "Criticality")}</span>
            <strong>{criticalityLabel(asset.criticality, english)}</strong>
          </div>
          <div>
            <span>{localized(english, "담당", "Owner")}</span>
            <strong>{ownerLabel(asset.assignedEngineer, english)}</strong>
          </div>
          <div>
            <span>{localized(english, "위험", "Risk")}</span>
            <strong>{probability(asset.failureProbability)}</strong>
          </div>
          <div>
            <span>{localized(english, "예상 정지", "Expected downtime")}</span>
            <strong>
              {asset.estimatedDowntimeMinutes !== null
                ? duration(asset.estimatedDowntimeMinutes, english)
                : localized(english, "근거 미제공", "Evidence unavailable")}
            </strong>
          </div>
          <button
            type="button"
            onClick={() => onOpenAsset(asset.assetId, asset.eventId)}
          >
            {localized(english, "설비 근거 중심으로 보기", "Open asset evidence")}
          </button>
        </div>
      ) : (
        <Empty text={localized(english, "설비를 선택하면 역할에 맞는 상세 근거를 구성합니다.", "Select an asset to assemble role-specific evidence.")} />
      )}
    </Block>
  );
}

function ProductionExposureBlock({
  detail,
  companyContext,
}: {
  detail: OperationsEventDetailModel | null;
  companyContext: OperationsCompanyContext | null;
}) {
  const english = useWorkspaceEnglish();
  const value = exposure({ detail, companyContext });
  return (
    <Block
      title={localized(english, "생산 · 재무 영향", "Production & financial impact")}
      eyebrow="PRODUCTION EXPOSURE"
      icon={<CircleDollarSign size={15} />}
      guidance={localized(english, "현재 Case의 생산 손실 수량과 제품 단가·공헌이익 근거를 연결해 노출 규모를 보여줍니다.", "Connects production-loss units with product price and contribution-margin evidence to show the selected case's exposure.")}
      className="span-6"
    >
      {detail?.operationContext ? (
        <>
          <div className="rw-composed-kv">
            <div>
              <span>{localized(english, "생산 영향", "Production impact")}</span>
              <strong>
                {detail.operationContext.productionImpact === "high"
                  ? localized(english, "높음", "High")
                  : detail.operationContext.productionImpact === "medium"
                    ? localized(english, "중간", "Medium")
                    : detail.operationContext.productionImpact === "low"
                      ? localized(english, "낮음", "Low")
                      : detail.operationContext.productionImpact === "none"
                        ? localized(english, "현재 영향 없음", "No current impact")
                        : "—"}
              </strong>
            </div>
            <div>
              <span>{localized(english, "예상 손실 수량", "Estimated lost units")}</span>
              <strong>
                {value.lostUnits !== null
                  ? `${formatNumber(value.lostUnits, english)}${english ? " units" : "개"}`
                  : "—"}
              </strong>
            </div>
            <div>
              <span>{localized(english, "제품", "Product")}</span>
              <strong>
                {value.product?.name ??
                  detail.operationContext.eventImpact?.productVariant ??
                  "—"}
              </strong>
            </div>
            <div>
              <span>{localized(english, "매출 노출액", "Revenue exposure")}</span>
              <strong>{compactMoney(value.revenueExposure, english)}</strong>
            </div>
            <div>
              <span>{localized(english, "공헌이익 노출액", "Contribution-margin exposure")}</span>
              <strong>{compactMoney(value.contributionExposure, english)}</strong>
            </div>
          </div>
          {detail.operationContext.eventImpact?.basis.formula ? (
            <details className="rw-technical-details">
              <summary>{localized(english, "산정 근거 상세", "Calculation basis")}</summary>
              <code>{detail.operationContext.eventImpact.basis.formula}</code>
            </details>
          ) : null}
        </>
      ) : (
        <Empty text={localized(english, "선택 이벤트의 생산 영향 문맥이 없습니다.", "No production-impact context is connected to the selected event.")} />
      )}
    </Block>
  );
}

function DecisionQueueBlock({
  model,
  selectedEvent,
  onSelectEvent,
}: {
  model: OperationsBootstrapModel;
  selectedEvent: OperationsEvent | null;
  onSelectEvent: (event: OperationsEvent) => void;
}) {
  const english = useWorkspaceEnglish();
  const queue = model.events
    .filter((event) => event.recommendedDecision !== "continue_monitoring")
    .slice(0, 7);
  return (
    <Block
      title="Decision Case"
      eyebrow="DECISION QUEUE"
      icon={<ListChecks size={15} />}
      guidance={localized(english, "계속 관찰을 제외하고 운영 판단이나 현장 조치가 필요한 Case를 우선 보여줍니다.", "Prioritizes cases that need an operational decision or field action, excluding continue-monitoring cases.")}
      className="span-6"
    >
      <div className="rw-composed-list">
        {queue.map((event) => (
          <button
            type="button"
            key={event.eventId}
            className={
              selectedEvent?.eventId === event.eventId ? "is-active" : ""
            }
            onClick={() => onSelectEvent(event)}
          >
            <div>
              <strong>{event.assetName}</strong>
              <small>
                {decisionLabel(event.recommendedDecision, english)} ·{" "}
                {ownerLabel(event.assignedEngineer, english)}
                {waitingMinutes(event.observedAt) !== null
                  ? ` · ${localized(english, "대기", "waiting")} ${duration(waitingMinutes(event.observedAt), english)}`
                  : ""}
              </small>
            </div>
            <b>{riskLabel(event.status, english)}</b>
          </button>
        ))}
      </div>
    </Block>
  );
}

function DecisionBottleneckBlock({
  model,
  selectedEvent,
  detail,
  onSelectEvent,
  compact = false,
}: {
  model: OperationsBootstrapModel;
  selectedEvent: OperationsEvent | null;
  detail: OperationsEventDetailModel | null;
  onSelectEvent: (event: OperationsEvent) => void;
  compact?: boolean;
}) {
  const english = useWorkspaceEnglish();
  const delayed = model.events
    .filter((event) => event.recommendedDecision !== "continue_monitoring")
    .sort(
      (left, right) =>
        (waitingMinutes(right.observedAt) ?? 0) -
        (waitingMinutes(left.observedAt) ?? 0),
    )
    .slice(0, compact ? 3 : 5);
  return (
    <Block
      title={localized(english, "의사결정 병목", "Decision bottlenecks")}
      eyebrow="DECISION BOTTLENECK"
      icon={<TimerReset size={15} />}
      guidance={localized(english, "승인된 SLA가 없는 상태에서는 임의의 지연 판정을 하지 않고, Case 발생 후 경과시간만 비교합니다.", "When no approved SLA exists, this view avoids inventing an overdue threshold and compares elapsed time since each case began.")}
      className={compact ? "span-6 executive-summary-card" : "span-12"}
    >
      <p className="rw-bottleneck-sla-note">
        <strong>{localized(english, "대기시간 기준", "Waiting-time basis")}</strong>{" "}
        {localized(english, "현재 Backend에 승인된 Decision SLA 계약이 없어 SLA 초과 여부를 임의 계산하지 않습니다. 아래 값은 Case 발생 후 경과시간입니다.", "There is no approved Decision SLA contract in the backend, so this view does not infer an SLA breach. Values below are elapsed time since each case was created.")}
      </p>
      {compact && delayed.length ? (
        <div className="rw-composed-list rw-bottleneck-compact">
          {delayed.map((event) => (
            <button
              type="button"
              key={event.eventId}
              className={
                selectedEvent?.eventId === event.eventId ? "is-active" : ""
              }
              onClick={() => onSelectEvent(event)}
            >
              <div>
                <strong>{event.assetName}</strong>
                <small>
                  {ownerLabel(event.assignedEngineer, english)} ·{" "}
                  {decisionLabel(event.recommendedDecision, english)}
                </small>
              </div>
              <b>{duration(waitingMinutes(event.observedAt), english)}</b>
            </button>
          ))}
        </div>
      ) : delayed.length ? (
        <div
          className="rw-bottleneck-table"
          role="table"
          aria-label={localized(english, "지연 Decision Case", "Delayed decision cases")}
        >
          <header role="row">
            <span>Case</span>
            <span>{localized(english, "대기", "Waiting")}</span>
            <span>Owner</span>
            <span>{localized(english, "결정 요청", "Decision request")}</span>
            <span>{localized(english, "영향", "Impact")}</span>
          </header>
          {delayed.map((event) => {
            const active = selectedEvent?.eventId === event.eventId;
            const impact = active
              ? detail?.operationContext?.productionImpact
              : null;
            return (
              <button
                type="button"
                role="row"
                key={event.eventId}
                className={active ? "is-active" : ""}
                onClick={() => onSelectEvent(event)}
              >
                <strong>{event.assetName}</strong>
                <span>{duration(waitingMinutes(event.observedAt), english)}</span>
                <span>{ownerLabel(event.assignedEngineer, english)}</span>
                <span>{decisionLabel(event.recommendedDecision, english)}</span>
                <span>
                  {impact === "high"
                    ? localized(english, "높음", "High")
                    : impact === "medium"
                      ? localized(english, "중간", "Medium")
                      : impact === "low"
                        ? localized(english, "낮음", "Low")
                        : event.estimatedDowntimeMinutes !== null
                          ? localized(english, `${event.estimatedDowntimeMinutes}분 노출`, `${event.estimatedDowntimeMinutes} min exposure`)
                          : localized(english, "확인 중", "Reviewing")}
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <Empty text={localized(english, "현재 판단 대기 Case가 없습니다.", "There are no decision-pending cases.")} />
      )}
    </Block>
  );
}

function WorkflowLifecycleBlock({
  detail,
}: {
  detail: OperationsEventDetailModel | null;
}) {
  const english = useWorkspaceEnglish();
  const lifecycle = detail?.closedLoop?.lifecycleSummary ?? null;
  return (
    <Block
      title={localized(english, "현재 Workflow 단계", "Current workflow stage")}
      eyebrow="CLOSED LOOP"
      icon={<ClipboardCheck size={15} />}
      guidance={localized(english, "현재 Case가 점검·승인·정비·후속 관측 중 어디까지 진행됐는지와 다음 단계만 요약합니다.", "Summarizes how far the selected case has progressed through inspection, approval, maintenance, and follow-up observation, plus the next stage.")}
      className="span-6"
    >
      {lifecycle ? (
        <div className="rw-composed-lifecycle">
          <strong>{english ? workflowStatusLabel(lifecycle.currentStep, true) : lifecycle.currentStepLabel}</strong>
          <div>
            {lifecycle.completedSteps.map((step) => (
              <span key={step}>{workflowStatusLabel(step, english)}</span>
            ))}
          </div>
          <p>{localized(english, "다음 단계:", "Next stage:")} {workflowStatusLabel(lifecycle.nextStep, english)}</p>
        </div>
      ) : (
        <div className="rw-workflow-prerequisite">
          <strong>{localized(english, "작업 요청 전", "Before work request")}</strong>
          <p>
            {localized(english, "현재 Case의 근거 snapshot은 준비되어 있습니다. 운영 관리자가 점검 작업요청을 생성하면 closed-loop가 시작됩니다.", "The evidence snapshot for this case is ready. The closed loop begins when an operations manager creates an inspection work request.")}
          </p>
        </div>
      )}
    </Block>
  );
}

function CaseLineageBlock({ props }: { props: RoleComposedWorkspaceProps }) {
  const english = useWorkspaceEnglish();
  const event = props.selectedEvent;
  const detail = props.detail;
  const firstDecision =
    detail?.activity
      .filter((item) => item.kind === "decision")
      .sort((left, right) =>
        left.createdAt.localeCompare(right.createdAt),
      )[0] ?? null;
  const latestWork =
    detail?.closedLoop?.workOrders
      .slice()
      .sort((left, right) =>
        String(right.updatedAt ?? right.createdAt ?? "").localeCompare(
          String(left.updatedAt ?? left.createdAt ?? ""),
        ),
      )[0] ?? null;
  const completedAt = maintenanceCompletedAt(detail);
  const postMaintenanceObservation = completedAt
    ? (detail?.riskSeries.some(
        (point) => Date.parse(point.observedAt) > Date.parse(completedAt),
      ) ?? false)
    : false;
  const finalReportReady = Boolean(
    completedAt && postMaintenanceObservation && detail?.report.snapshotId,
  );
  const steps = [
    {
      id: "event",
      label: "Event",
      state: event ? "done" : "pending",
      headline: event
        ? `${event.assetName} · ${probability(event.failureProbability)}`
        : localized(english, "이벤트 선택 필요", "Select an event"),
      detail: event
        ? `${riskLabel(event.status, english)} · ${dateTime(event.observedAt, english)}`
        : localized(english, "공장 상태맵에서 설비를 선택하세요.", "Select an asset from the factory status map."),
    },
    {
      id: "evidence",
      label: "Evidence",
      state: detail?.topFactors.length ? "done" : "pending",
      headline: detail?.topFactors.length
        ? `${formatNumber(detail.topFactors.length, english)}${english ? " model evidence items" : "개 모델 근거"}`
        : localized(english, "근거 조회 중", "Loading evidence"),
      detail: detail?.inspectionTargets[0]?.componentLabel
        ? localized(english, `점검 대상 ${detail.inspectionTargets[0].componentLabel}`, `Inspection target: ${detail.inspectionTargets[0].componentLabel}`)
        : localized(english, "센서·모델·SOP 근거 연결", "Sensor, model, and SOP evidence connected"),
    },
    {
      id: "decision",
      label: "Decision",
      state: firstDecision ? "done" : event ? "active" : "pending",
      headline:
        firstDecision?.title ??
        decisionLabel(event?.recommendedDecision, english) ??
        localized(english, "판단 대기", "Decision pending"),
      detail: firstDecision
        ? `${firstDecision.actor} · ${dateTime(firstDecision.createdAt, english)}`
        : localized(english, "운영 판단과 Owner가 기록됩니다.", "The operational decision and owner will be recorded here."),
    },
    {
      id: "action",
      label: "Action",
      state: latestWork
        ? latestWork.status === "completed"
          ? "done"
          : "active"
        : "pending",
      headline: latestWork
        ? `${latestWork.workType} · ${workflowStatusLabel(latestWork.status, english)}`
        : (workflowActionLabel(detail?.closedLoop?.primaryAction, english) ?? localized(english, "점검 작업요청 미생성", "Inspection work request not created")),
      detail: latestWork
        ? `${latestWork.workOrderId} · ${latestWork.actorDisplayName ?? latestWork.assignedTo ?? localized(english, "담당 미정", "Owner pending")}`
        : localized(english, "승인된 점검·정비 작업이 연결됩니다.", "Approved inspection and maintenance work will be connected here."),
    },
    {
      id: "outcome",
      label: "Outcome",
      state: finalReportReady ? "done" : completedAt ? "active" : "pending",
      headline: finalReportReady
        ? localized(english, "정비 후 관측 확인 완료", "Post-maintenance observation verified")
        : completedAt
          ? localized(english, "정비 후 관측 대기", "Awaiting post-maintenance observation")
          : localized(english, "결과 대기", "Outcome pending"),
      detail: finalReportReady
        ? localized(english, `정비 완료 ${dateTime(completedAt, false)} · 검증된 후속 관측과 보고 snapshot 연결`, `Maintenance completed ${dateTime(completedAt, true)} · verified follow-up observation and report snapshot connected`)
        : completedAt
          ? localized(english, "정비 완료만으로 Outcome을 확정하지 않습니다. 후속 관측이 필요합니다.", "Maintenance completion alone does not confirm the outcome. Follow-up observation is required.")
          : localized(english, "승인된 Action이 완료된 뒤 Outcome 관측을 시작합니다.", "Outcome observation begins after the approved action is completed."),
    },
  ];
  return (
    <Block
      title="Event → Outcome lineage"
      eyebrow="CASE LINEAGE"
      icon={<GitBranch size={15} />}
      guidance={localized(english, "하나의 Case 안에서 Event → Evidence → Decision → Action → Outcome의 연결이 끊기지 않았는지 확인합니다.", "Checks that Event → Evidence → Decision → Action → Outcome remain connected within one case.")}
      className="span-12"
    >
      <div className="rw-case-lineage">
        {steps.map((step) => (
          <article key={step.id} className={`is-${step.state}`}>
            <i>{step.label}</i>
            <strong>{step.headline}</strong>
            <small>{step.detail}</small>
          </article>
        ))}
      </div>
      {event ? (
        <div className="rw-case-lineage-actions">
          <button
            type="button"
            onClick={() => props.onOpenAsset(event.assetId, event.eventId)}
          >
            {localized(english, "설비 근거 열기", "Open asset evidence")}
          </button>
          <button
            type="button"
            onClick={() =>
              props.onOpenReport(
                event.eventId,
                event.assetId,
                props.experienceKind === "executive"
                  ? "executive-brief"
                  : "summary-report",
              )
            }
          >
            {props.experienceKind === "operations"
              ? localized(english, "보고 초안 이어보기", "Continue report draft")
              : localized(english, "보고 산출물 보기", "Open report artifact")}
          </button>
        </div>
      ) : null}
    </Block>
  );
}

function WorkflowActionsBlock({
  props,
}: {
  props: RoleComposedWorkspaceProps;
}) {
  const english = useWorkspaceEnglish();
  const asset = selectedAsset(props.model, props.selectedEvent);
  if (!props.selectedEvent || !asset)
    return (
      <Block
        title={localized(english, "업무 실행", "Workflow actions")}
        eyebrow="ACTION"
        icon={<Wrench size={15} />}
        guidance={localized(english, "선택 Case의 승인 가능한 작업만 실행할 수 있으며 근거 snapshot과 작업 이력이 함께 남습니다.", "Only governed actions for the selected case can be executed, with the evidence snapshot and action history preserved.")}
        className="span-12"
      >
        <Empty text={localized(english, "작업할 이벤트를 선택하세요.", "Select an event to work on.")} />
      </Block>
    );
  return (
    <Block
      title={localized(english, "업무 실행", "Workflow actions")}
      eyebrow="GOVERNED ACTION"
      icon={<Wrench size={15} />}
      guidance={localized(english, "선택 Case의 승인 가능한 작업만 실행할 수 있으며 근거 snapshot과 작업 이력이 함께 남습니다.", "Only governed actions for the selected case can be executed, with the evidence snapshot and action history preserved.")}
      className="span-12"
    >
      <MaintenanceWorkflowActionPanel
        projectId={props.model.context.projectId}
        workspaceId={props.model.context.workspaceId}
        datasetVersionId={props.model.context.datasetVersionId}
        eventId={props.selectedEvent.eventId}
        assetId={asset.assetId}
        assetType={asset.assetType}
        role={props.role}
        currentUserId={props.currentUserId}
        snapshotBasis={props.detail?.snapshotBasis ?? null}
        canManage={props.canManageWorkflow}
        canFieldExecute={props.canExecuteFieldWorkflow}
        canMaintenanceExecute={props.experienceKind === "maintenance" && props.canExecuteFieldWorkflow}
        locale={english ? "en-US" : "ko-KR"}
        onChanged={props.onWorkflowChanged}
      />
      <MaintenanceCostDecisionPanel
        projectId={props.model.context.projectId}
        workspaceId={props.model.context.workspaceId}
        eventId={props.selectedEvent.eventId}
        guidance={props.detail?.inspectionTargets.find((item) => item.inspectionGuidance)?.inspectionGuidance ?? null}
        locale={english ? "en-US" : "ko-KR"}
        onChanged={props.onWorkflowChanged}
      />
      <OperationalDecisionSupportPanel
        assetId={asset.assetId}
        projectId={props.model.context.projectId}
        workspaceId={props.model.context.workspaceId}
        evidenceSnapshotId={props.detail?.snapshotBasis?.artifactId ?? null}
        decisionAsOf={props.selectedEvent.observedAt}
        riskStatus={props.selectedEvent.status}
        role={operationalDecisionBriefRole(props.role)}
        canMaterialize={props.canMaterializeAgentSummary}
        locale={english ? "en-US" : "ko-KR"}
      />
    </Block>
  );
}

function SensorSignalsBlock({
  detail,
}: {
  detail: OperationsEventDetailModel | null;
}) {
  const english = useWorkspaceEnglish();
  return (
    <Block
      title={localized(english, "센서 · 피쳐", "Sensors & features")}
      eyebrow="OBSERVED SIGNALS"
      icon={<RadioTower size={15} />}
      guidance={localized(english, "판단 시점에 연결된 센서 관측값과 품질 상태를 보여주며 원본 설비·센서 이름은 번역하지 않습니다.", "Shows sensor observations and quality status connected to the decision timestamp. Raw asset and sensor names remain unchanged.")}
      className="span-6"
    >
      {detail?.sensors.length ? (
        <div className="rw-composed-list static">
          {detail.sensors.slice(0, 8).map((sensor) => (
            <article key={sensor.id}>
              <div>
                <strong>{sensor.label}</strong>
                <small>
                  {sensor.observedAt
                    ? dateTime(sensor.observedAt, english)
                    : (sensor.qualityStatus ?? "")}
                </small>
              </div>
              <b>
                {String(sensor.value ?? "—")}
                {sensor.unit ? ` ${sensor.unit}` : ""}
              </b>
            </article>
          ))}
        </div>
      ) : (
        <Empty text={localized(english, "선택 설비의 센서 근거를 불러오는 중입니다.", "Loading sensor evidence for the selected asset.")} />
      )}
    </Block>
  );
}

function EvidenceFactorsBlock({
  detail,
}: {
  detail: OperationsEventDetailModel | null;
}) {
  const english = useWorkspaceEnglish();
  return (
    <Block
      title={localized(english, "위험 기여 근거", "Risk-contribution evidence")}
      eyebrow="MODEL EVIDENCE"
      icon={<ChartNoAxesCombined size={15} />}
      guidance={localized(english, "모델이 현재 위험도를 높이거나 낮춘 주요 피쳐와 기여 방향만 요약합니다.", "Summarizes the main features that increased or decreased the current risk score and their contribution direction.")}
      className="span-6"
    >
      {detail?.topFactors.length ? (
        <div
          className="rw-composed-list static"
          data-event-id={detail.event.eventId}
        >
          {detail.topFactors.slice(0, 7).map((factor) => (
            <article key={factor.id}>
              <div>
                <strong>
                  {english
                    ? englishSensorFactorLabel(factor.feature)
                    : displaySensorFactorLabel(factor.feature, factor.label)}
                </strong>
                <small>
                  {factorDirectionLabel(factor.direction, english)} ·{" "}
                  {explanationMethodLabel(factor.explanationMethod, english) ??
                    localized(english, "모델 근거", "Model evidence")}
                </small>
              </div>
              <b>{Math.round(Math.abs(factor.contribution) * 100)}%</b>
            </article>
          ))}
        </div>
      ) : (
        <Empty text={localized(english, "모델 기여 근거가 없습니다.", "No model-contribution evidence is available.")} />
      )}
    </Block>
  );
}

function InspectionTargetsBlock({
  detail,
}: {
  detail: OperationsEventDetailModel | null;
}) {
  const english = useWorkspaceEnglish();
  return (
    <Block
      title={localized(english, "점검 대상", "Inspection targets")}
      eyebrow="INSPECTION PLAN"
      icon={<ClipboardCheck size={15} />}
      guidance={localized(english, "센서·모델·SOP 근거에서 실제 현장 확인 대상으로 좁혀진 부품과 위치, 점검 방법을 보여줍니다.", "Shows components, locations, and inspection methods narrowed down from sensor, model, and SOP evidence for field verification.")}
      className="span-6"
    >
      {detail?.inspectionTargets.length ? (
        <div className="rw-composed-cards">
          {detail.inspectionTargets.slice(0, 5).map((target) => (
            <article key={target.targetId}>
              <strong>{target.componentLabel}</strong>
              <span>{target.locationLabel ?? localized(english, "위치 확인 필요", "Location needs review")}</span>
              <p>
                {target.inspectionMethod ??
                  inspectionAssociationLabel(target.association, english)}
              </p>
            </article>
          ))}
        </div>
      ) : (
        <Empty text={localized(english, "현재 근거에서 특정된 점검 대상이 없습니다.", "No inspection target has been identified from the current evidence.")} />
      )}
    </Block>
  );
}

function MaintenanceHistoryBlock({
  detail,
  companyContext,
  assetId,
}: {
  detail: OperationsEventDetailModel | null;
  companyContext: OperationsCompanyContext | null;
  assetId: string | null | undefined;
}) {
  const english = useWorkspaceEnglish();
  const records =
    companyContext?.maintenance_records.filter(
      (item) => item.asset_id === assetId,
    ) ?? [];
  const runtime = detail?.equipmentHistory ?? [];
  return (
    <Block
      title={localized(english, "정비 · 설비 이력", "Maintenance & asset history")}
      eyebrow="MAINTENANCE HISTORY"
      icon={<History size={15} />}
      guidance={localized(english, "선택 설비에 연결된 과거 정비 기록과 runtime 이력을 함께 보여주되 원문 기록 내용은 그대로 유지합니다.", "Shows historical maintenance records and runtime history connected to the selected asset while preserving source record text as-is.")}
      className="span-6"
    >
      {records.length || runtime.length ? (
        <div className="rw-composed-timeline">
          {records.slice(0, 4).map((item) => (
            <article key={item.id}>
              <time>{dateTime(item.occurred_at, english)}</time>
              <strong>{item.component}</strong>
              <p>{item.symptom}</p>
              <small>
                {item.action} · {localized(english, "결과:", "Result:")} {item.result}
              </small>
            </article>
          ))}
          {runtime.slice(0, 4).map((item, index) => (
            <article key={`${item.occurredAt}-${index}`}>
              <time>{dateTime(item.occurredAt, english)}</time>
              <strong>{item.kind}</strong>
              <p>{item.description}</p>
              <small>{item.source}</small>
            </article>
          ))}
        </div>
      ) : (
        <Empty text={localized(english, "연결된 과거 정비 기록이 없습니다.", "No linked maintenance history is available.")} />
      )}
    </Block>
  );
}

function MaintenanceEffectBlock({
  detail,
  companyContext,
  assetId,
}: {
  detail: OperationsEventDetailModel | null;
  companyContext: OperationsCompanyContext | null;
  assetId: string | null | undefined;
}) {
  const english = useWorkspaceEnglish();
  const completedAt = maintenanceCompletedAt(detail);
  const boundary = completedAt ? new Date(completedAt).getTime() : null;
  const riskPoints = [...(detail?.riskSeries ?? [])].sort((left, right) =>
    left.observedAt.localeCompare(right.observedAt),
  );
  const beforeRisk =
    boundary === null
      ? []
      : riskPoints
          .filter((item) => new Date(item.observedAt).getTime() <= boundary)
          .slice(-6);
  const afterRisk =
    boundary === null
      ? []
      : riskPoints
          .filter((item) => new Date(item.observedAt).getTime() > boundary)
          .slice(0, 6);
  const beforeAverage = average(
    beforeRisk.map((item) => item.failureProbability),
  );
  const afterAverage = average(
    afterRisk.map((item) => item.failureProbability),
  );
  const riskDelta =
    beforeAverage !== null && afterAverage !== null
      ? afterAverage - beforeAverage
      : null;
  const beforeAlerts = beforeRisk.filter(
    (item) => item.status && item.status !== "normal",
  ).length;
  const afterAlerts = afterRisk.filter(
    (item) => item.status && item.status !== "normal",
  ).length;
  const sensorEffects = (detail?.sensors ?? [])
    .map((sensor) => {
      const points = sensor.historyPoints ?? [];
      if (boundary === null) return null;
      const before = average(
        points
          .filter((item) => new Date(item.observedAt).getTime() <= boundary)
          .slice(-6)
          .map((item) => item.value),
      );
      const after = average(
        points
          .filter((item) => new Date(item.observedAt).getTime() > boundary)
          .slice(0, 6)
          .map((item) => item.value),
      );
      if (before === null || after === null) return null;
      return {
        id: sensor.id,
        label: sensor.label,
        unit: sensor.unit,
        before,
        after,
        delta: after - before,
      };
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item))
    .slice(0, 3);
  const historical = assetId
    ? (companyContext?.maintenance_records
        .filter((item) => item.asset_id === assetId)
        .at(-1) ?? null)
    : null;
  return (
    <Block
      title={localized(english, "정비 효과 Before / After", "Maintenance effect Before / After")}
      eyebrow="MAINTENANCE OUTCOME"
      icon={<TrendingDown size={15} />}
      guidance={localized(english, "정비 완료 시점을 기준으로 전후 위험도·알림·센서 관측을 비교하며, 후속 관측이 없으면 효과를 확정하지 않습니다.", "Compares risk, alerts, and sensor observations before and after maintenance completion. No effect is confirmed until follow-up observations exist.")}
      className="span-12"
    >
      {completedAt ? (
        <div className="rw-maintenance-effect">
          <header>
            <div>
              <span>{localized(english, "정비 완료 기준", "Maintenance completed")}</span>
              <strong>{dateTime(completedAt, english)}</strong>
            </div>
            <b
              className={
                riskDelta !== null && riskDelta < 0 ? "is-improved" : ""
              }
            >
              {riskDelta === null
                ? localized(english, "후속 관측 수집 중", "Collecting follow-up observations")
                : `${localized(english, "위험도", "Risk")} ${riskDelta > 0 ? "+" : ""}${Math.round(riskDelta * 100)}%p`}
            </b>
          </header>
          <div className="rw-maintenance-effect-grid">
            <article>
              <span>{localized(english, "정비 전 위험", "Risk before maintenance")}</span>
              <strong>{probability(beforeAverage)}</strong>
              <small>{localized(english, `관측 ${beforeRisk.length}건`, `${formatNumber(beforeRisk.length, true)} observations`)}</small>
            </article>
            <article>
              <span>{localized(english, "정비 후 위험", "Risk after maintenance")}</span>
              <strong>{probability(afterAverage)}</strong>
              <small>{localized(english, `관측 ${afterRisk.length}건`, `${formatNumber(afterRisk.length, true)} observations`)}</small>
            </article>
            <article>
              <span>{localized(english, "알림 빈도", "Alert frequency")}</span>
              <strong>
                {beforeRisk.length && afterRisk.length
                  ? `${beforeAlerts} → ${afterAlerts}`
                  : localized(english, "관측 대기", "Awaiting observations")}
              </strong>
              <small>{localized(english, "비정상 관측 수", "Abnormal observations")}</small>
            </article>
          </div>
          {sensorEffects.length ? (
            <div className="rw-maintenance-sensor-effect">
              {sensorEffects.map((item) => (
                <article key={item.id}>
                  <span>{item.label}</span>
                  <strong>
                    {formatNumber(item.before, english, {
                      maximumFractionDigits: 1,
                    })}{" "}
                    →{" "}
                    {formatNumber(item.after, english, {
                      maximumFractionDigits: 1,
                    })}
                    {item.unit ? ` ${item.unit}` : ""}
                  </strong>
                  <small>
                    {item.delta > 0 ? "+" : ""}
                    {formatNumber(item.delta, english, {
                      maximumFractionDigits: 1,
                    })}
                  </small>
                </article>
              ))}
            </div>
          ) : (
            <p>
              {localized(english, "정비 전후 관측 구간이 충분해지면 핵심 센서의 회복 여부를 함께 표시합니다.", "When enough observations exist before and after maintenance, recovery of key sensors will be shown here.")}
            </p>
          )}
        </div>
      ) : historical ? (
        <div className="rw-maintenance-history-fallback">
          <strong>{localized(english, "참고 · 과거 유사 정비", "Reference · similar prior maintenance")}</strong>
          <p>{historical.action}</p>
          <span>{historical.result}</span>
          <small>
            {dateTime(historical.occurred_at, english)} · {localized(english, "현재 Decision Case의 Outcome이 아닙니다.", "This is not the outcome of the current decision case.")}
          </small>
        </div>
      ) : (
        <Empty text={localized(english, "현재 Case에 연결된 정비 완료 및 정비 후 관측이 생기면 before/after 효과를 표시합니다.", "Before/after effects will appear after maintenance completion and post-maintenance observations are connected to this case.")} />
      )}
    </Block>
  );
}

function MaterialContextBlock({
  companyContext,
  assetId,
}: {
  companyContext: OperationsCompanyContext | null;
  assetId: string | null | undefined;
}) {
  const english = useWorkspaceEnglish();
  const materials = relevantMaterials(companyContext, assetId);
  return (
    <Block
      title={localized(english, "자재 · 예비품", "Materials & spare parts")}
      eyebrow="MATERIAL CONTEXT"
      icon={<PackageSearch size={15} />}
      guidance={localized(english, "선택 설비에 연결된 자재 재고와 재주문 기준, 리드타임을 함께 보여 정비 실행 제약을 확인합니다.", "Shows inventory, reorder points, and lead time for materials linked to the selected asset to surface maintenance execution constraints.")}
      className="span-6"
    >
      {materials.length ? (
        <div className="rw-composed-list static">
          {materials.map((item) => (
            <article key={item.id}>
              <div>
                <strong>{item.name}</strong>
                <small>
                  {item.category} · {localized(english, `리드타임 ${item.lead_time_days}일`, `lead time ${item.lead_time_days} days`)}
                </small>
              </div>
              <b
                className={
                  item.on_hand_quantity <= item.reorder_point
                    ? "is-warning"
                    : ""
                }
              >
                {formatNumber(item.on_hand_quantity, english)}{english ? " units" : "개"}
              </b>
            </article>
          ))}
        </div>
      ) : (
        <Empty text={localized(english, "선택 설비에 연결된 자재 master가 없습니다.", "No material master data is linked to the selected asset.")} />
      )}
    </Block>
  );
}

function DecisionHistoryBlock({
  detail,
  context,
  assetId,
}: {
  detail: OperationsEventDetailModel | null;
  context: OperationsCompanyContext | null;
  assetId: string | null | undefined;
}) {
  const english = useWorkspaceEnglish();
  const decisions =
    context?.decisions
      .filter(
        (item) =>
          !item.related_asset_ids.length ||
          (assetId ? item.related_asset_ids.includes(assetId) : false),
      )
      .slice(0, 5) ?? [];
  return (
    <Block
      title={localized(english, "판단 이력", "Decision history")}
      eyebrow="DECISION LINEAGE"
      icon={<FileClock size={15} />}
      guidance={localized(english, "선택 설비와 연결된 과거 판단과 현재 Case 활동을 시간순 근거로 확인합니다.", "Reviews prior decisions linked to the selected asset together with current case activity as chronological evidence.")}
      className="span-6"
    >
      {decisions.length || detail?.activity.length ? (
        <div className="rw-composed-timeline">
          {decisions.map((item) => (
            <article key={item.id}>
              <time>{dateTime(item.decided_at, english)}</time>
              <strong>{item.title}</strong>
              <p>{item.decision}</p>
              <small>{item.source_ref}</small>
            </article>
          ))}
          {detail?.activity.slice(0, 4).map((item) => (
            <article key={item.id}>
              <time>{dateTime(item.createdAt, english)}</time>
              <strong>{item.title}</strong>
              <p>{item.detail}</p>
              <small>{item.actor}</small>
            </article>
          ))}
        </div>
      ) : (
        <Empty text={localized(english, "연결된 판단 이력이 없습니다.", "No linked decision history is available.")} />
      )}
    </Block>
  );
}

function ReportSummaryBlock({
  detail,
  event,
  model,
  experienceKind,
  canMaterializeAgentSummary,
  onOpenReport,
  compact = false,
}: {
  detail: OperationsEventDetailModel | null;
  event: OperationsEvent | null;
  model: OperationsBootstrapModel;
  experienceKind: ReliabilityExperienceKind;
  canMaterializeAgentSummary: boolean;
  onOpenReport: RoleComposedWorkspaceProps["onOpenReport"];
  compact?: boolean;
}) {
  const english = useWorkspaceEnglish();
  const [brief, setBrief] =
    useState<OperationsAgentReviewSummaryResponse | null>(null);
  const defaultReportType: ReportType =
    experienceKind === "executive"
      ? "executive-brief"
      : experienceKind === "engineering"
        ? "inspection-summary"
        : "operations-decision";
  const [reportType, setReportType] = useState<ReportType>(defaultReportType);
  const [variantReport, setVariantReport] = useState<
    OperationsEventDetailModel["report"] | null
  >(null);
  const [variantLoading, setVariantLoading] = useState(false);

  useEffect(() => {
    setReportType(defaultReportType);
  }, [defaultReportType]);

  useEffect(() => {
    if (experienceKind !== "executive" || !event?.assetId) {
      setBrief(null);
      return;
    }
    let cancelled = false;
    const request = {
      assetId: event.assetId,
      projectId: model.context.projectId,
      datasetVersionId: model.context.datasetVersionId,
      eventId: event.eventId,
      historyWindow: "24h",
    };
    void getOperationsAgentReviewSummary(request)
      .then(async (payload) => {
        if (payload.summary || !canMaterializeAgentSummary) return payload;
        return createOperationsAgentReviewSummary({
          ...request,
          trigger: "ui_manual_regeneration",
        });
      })
      .then((payload) => {
        if (!cancelled) setBrief(payload);
      })
      .catch(() => {
        if (!cancelled) setBrief(null);
      });
    return () => {
      cancelled = true;
    };
  }, [
    canMaterializeAgentSummary,
    event?.assetId,
    event?.eventId,
    experienceKind,
    model.context.datasetVersionId,
    model.context.projectId,
  ]);

  useEffect(() => {
    if (!event) {
      setVariantReport(null);
      return;
    }
    if (detail?.report.reportType === reportType) {
      setVariantReport(detail.report);
      return;
    }
    let cancelled = false;
    setVariantLoading(true);
    const reportRole: Role =
      experienceKind === "executive"
        ? "executive"
        : experienceKind === "engineering"
          ? "engineer"
          : "manager";
    void loadOperationsReportVariant({
      projectId: model.context.projectId,
      workspaceId: model.context.workspaceId,
      datasetVersionId: model.context.datasetVersionId,
      event,
      role: reportRole,
      reportType,
    })
      .then((report) => {
        if (!cancelled) setVariantReport(report);
      })
      .catch(() => {
        if (!cancelled) setVariantReport(null);
      })
      .finally(() => {
        if (!cancelled) setVariantLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    detail?.report,
    event,
    experienceKind,
    model.context.datasetVersionId,
    model.context.projectId,
    model.context.workspaceId,
    reportType,
  ]);

  const report = variantReport ?? detail?.report ?? null;
  const useAgentBrief =
    reportType === "executive-brief" && experienceKind === "executive";
  const roleSummary =
    (useAgentBrief ? brief?.summary?.summary : null) ?? report?.summary ?? null;
  const headline =
    (useAgentBrief ? brief?.summary?.title : null) ?? report?.headline ?? null;
  const evidenceRefs =
    (useAgentBrief ? brief?.summary?.source_refs : null) ??
    report?.sections.flatMap((section) => section.evidenceFieldIds) ??
    [];
  const maintenanceDone = maintenanceCompletedAt(detail);
  const outcomeObserved = maintenanceDone
    ? (detail?.riskSeries.some(
        (point) => Date.parse(point.observedAt) > Date.parse(maintenanceDone),
      ) ?? false)
    : false;
  const artifactStatus =
    maintenanceDone && outcomeObserved
      ? localized(english, "검토 가능한 결과 보고", "Outcome report ready for review")
      : localized(english, "업무 진행 중 · 초안", "Work in progress · draft");
  return (
    <Block
      title={compact ? localized(english, "보고 준비 상태", "Report readiness") : localized(english, "역할별 보고 요약", "Role-specific report summary")}
      eyebrow="GROUNDED REPORT"
      icon={<FileText size={15} />}
      guidance={localized(english, "현재 Case의 고정 근거 snapshot을 바탕으로 역할별 보고 산출물의 준비 상태와 연결 근거를 확인합니다.", "Shows readiness and linked evidence for role-specific report artifacts grounded in the selected case's fixed evidence snapshot.")}
      className={compact ? "span-6 executive-summary-card" : "span-12"}
    >
      {roleSummary && headline ? (
        <div className="rw-composed-report">
          <div className="rw-report-controls">
            <label>
              <span>{localized(english, "보고 유형", "Report type")}</span>
              <select
                value={reportType}
                onChange={(event) =>
                  setReportType(event.target.value as ReportType)
                }
              >
                <option value="inspection-summary">{localized(english, "현장 점검 요약", "Field inspection summary")}</option>
                <option value="operations-decision">{localized(english, "운영 판단 보고", "Operations decision report")}</option>
                <option value="executive-brief">{localized(english, "경영진 Executive Brief", "Executive brief")}</option>
                <option value="maintenance-effect">
                  {localized(english, "정비 효과 before-after", "Maintenance effect before-after")}
                </option>
                <option value="weekly-risk">{localized(english, "주간 리스크 요약", "Weekly risk summary")}</option>
              </select>
            </label>
            <span>
              {variantLoading
                ? localized(english, "보고 전환 중", "Switching report")
                : brief?.summary?.mode === "llm" || report?.mode === "llm"
                  ? localized(english, "AI 근거 요약", "AI evidence summary")
                  : localized(english, "검증된 기본 보고", "Verified baseline report")}
            </span>
          </div>
          {report ? (
            <div className="rw-report-artifact-meta">
              <span>{artifactStatus}</span>
              <strong>{reportTypeLabel(report.reportType, english)}</strong>
              <small>{artifactKindLabel(report.reportId, english)}</small>
              <small>{localized(english, "관측 기준", "Observed as of")} {dateTime(report.asOf ?? detail?.event.observedAt, english)}</small>
              <small className="rw-technical-metadata">Case {event?.eventId ?? "—"}</small>
              <small className="rw-technical-metadata">artifact {report.reportId}</small>
              {report.revision > 0 ? (
                <small>{localized(english, `수정본 ${report.revision}`, `Revision ${report.revision}`)}</small>
              ) : null}
            </div>
          ) : null}
          <div>
            <strong>{headline}</strong>
            <p>{roleSummary}</p>
          </div>
          {report && !compact ? (
            <div className="rw-composed-report-sections">
              {report.sections
                .slice(0, experienceKind === "executive" ? 3 : 4)
                .map((section) => (
                  <article key={section.id}>
                    <span>{section.title}</span>
                    <p>{section.body}</p>
                  </article>
                ))}
            </div>
          ) : null}
          {!compact ? (
            <details className="rw-report-evidence">
              <summary>
                {localized(english, "세부 근거", "Evidence details")} · {formatNumber(new Set(evidenceRefs).size, english)}{english ? " items" : "건"}
              </summary>
              <ul>
                {[...new Set(evidenceRefs)].slice(0, 12).map((ref) => (
                  <li key={ref}>
                    <span>{evidenceReferenceLabel(ref, english)}</span>
                    <code className="rw-technical-metadata">{ref}</code>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
          <div className="rw-report-actions">
            <button
              type="button"
              onClick={() =>
                onOpenReport(
                  event?.eventId ?? null,
                  event?.assetId ?? null,
                  reportType === "inspection-summary"
                    ? "inspection-request"
                    : "executive-brief",
                )
              }
            >
              {localized(english, "내용 미리보기", "Preview content")}
            </button>
            <button
              type="button"
              onClick={() =>
                onOpenReport(
                  event?.eventId ?? null,
                  event?.assetId ?? null,
                  reportType === "inspection-summary"
                    ? "inspection-request"
                    : "executive-brief",
                )
              }
            >
              {localized(english, "보고서 출력 화면", "Open report output")}
            </button>
          </div>
        </div>
      ) : (
        <Empty text={localized(english, "선택 이벤트의 grounded report를 불러오는 중입니다.", "Loading the grounded report for the selected event.")} />
      )}
    </Block>
  );
}

function ContextEvidenceBlock({
  context,
  assetId,
}: {
  context: OperationsCompanyContext | null;
  assetId: string | null | undefined;
}) {
  const english = useWorkspaceEnglish();
  const decisions =
    context?.decisions
      .filter(
        (item) =>
          !item.related_asset_ids.length ||
          (assetId ? item.related_asset_ids.includes(assetId) : false),
      )
      .slice(0, 3) ?? [];
  return (
    <Block
      title={localized(english, "조직 · 회의 · 의사결정 문맥", "Organization, meeting & decision context")}
      eyebrow="ONTOLOGY CONTEXT"
      icon={<Building2 size={15} />}
      guidance={localized(english, "설비 사건을 조직 책임·회의 기록·기존 의사결정과 연결해 업무 문맥이 어디서 왔는지 보여줍니다.", "Connects the asset event to organizational ownership, meeting records, and prior decisions so the source of business context is visible.")}
      className="span-12"
    >
      {context ? (
        <div className="rw-composed-context">
          <div>
            <div className="rw-context-source-row">
              <strong>{context.company.name}</strong>
              <span
                className={
                  context.context_storage?.mode === "team_db_overlay"
                    ? "is-db"
                    : ""
                }
              >
                {context.context_storage?.mode === "team_db_overlay"
                  ? `Team DB · ${context.context_storage.persisted_record_count} records`
                  : "Reference bootstrap"}
              </span>
            </div>
            <p>{context.company.operating_principle}</p>
            <small>
              {context.company.industry} · {context.company.headquarters}
            </small>
          </div>
          <div className="rw-composed-context-grid">
            {context.organization_units.slice(0, 5).map((unit) => (
              <article key={unit.id}>
                <span>{unit.name}</span>
                <strong>{unit.leader}</strong>
                <small>{unit.responsibilities.slice(0, 2).join(" · ")}</small>
              </article>
            ))}
          </div>
          {context.meeting_minutes.slice(0, 2).map((meeting) => (
            <article className="rw-composed-meeting" key={meeting.id}>
              <span>{dateTime(meeting.occurred_at, english)}</span>
              <strong>{meeting.title}</strong>
              <p>{meeting.summary}</p>
            </article>
          ))}
          {decisions.map((decision) => (
            <article className="rw-composed-decision" key={decision.id}>
              <strong>{decision.title}</strong>
              <p>{decision.decision}</p>
              <small>{decision.source_ref}</small>
            </article>
          ))}
        </div>
      ) : (
        <Empty text={localized(english, "회사 및 조직 문맥을 불러오는 중입니다.", "Loading company and organization context.")} />
      )}
    </Block>
  );
}

function DataQualityBlock({
  detail,
  model,
}: {
  detail: OperationsEventDetailModel | null;
  model: OperationsBootstrapModel;
}) {
  const english = useWorkspaceEnglish();
  const warnings = detail?.dataQualityWarnings ?? [];
  return (
    <Block
      title={localized(english, "데이터 품질 확인 필요", "Data quality review required")}
      eyebrow="DATA QUALITY HOLD"
      icon={<AlertTriangle size={15} />}
      guidance={localized(english, "품질 경고가 남아 있는 동안에는 위험도·생산 영향·정비 필요성을 확정 판단하지 않도록 의사결정을 보류합니다.", "Keeps decisions on risk, production impact, and maintenance need on hold while data-quality warnings remain unresolved.")}
      className="span-12 is-warning-block"
    >
      <p>
        {localized(english, `현재 데이터 품질 보류 항목이 ${formatNumber(model.metrics.dataQualityHold, false)}건 있습니다. 품질 문제가 해소되기 전에는 고장 위험·생산 영향·정비 필요성을 확정하지 않습니다.`, `There are ${formatNumber(model.metrics.dataQualityHold, true)} data-quality hold item(s). Failure risk, production impact, and maintenance need are not confirmed until the quality issues are resolved.`)}
      </p>
      {warnings.length ? (
        <ul>
          {warnings.map((warning) => (
            <li key={`${warning.code}-${warning.field}`}>
              {warning.field}: {warning.message}
            </li>
          ))}
        </ul>
      ) : null}
    </Block>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="rw-composed-empty">{text}</div>;
}

function renderBlock(
  id: ReliabilityBlockId,
  props: RoleComposedWorkspaceProps,
) {
  const assetId = props.selectedEvent?.assetId ?? null;
  const compactExecutiveBrief =
    props.experienceKind === "executive" &&
    props.surfaceId === "executive-brief";
  switch (id) {
    case "risk-metrics":
      return (
        <RiskMetricsBlock
          key={id}
          model={props.model}
          detail={props.detail}
          compact={compactExecutiveBrief}
        />
      );
    case "factory-map":
      return (
        <FactoryMapBlock
          key={id}
          model={props.model}
          selectedEvent={props.selectedEvent}
          onSelectEvent={props.onSelectEvent}
        />
      );
    case "business-kpis":
      return <BusinessKpisBlock key={id} context={props.companyContext} />;
    case "operational-kpis":
      return (
        <OperationalKpisBlock
          key={id}
          model={props.model}
          detail={props.detail}
          companyContext={props.companyContext}
        />
      );
    case "risk-portfolio":
      return (
        <RiskPortfolioBlock
          key={id}
          model={props.model}
          onSelectEvent={props.onSelectEvent}
        />
      );
    case "line-risk":
      return <LineRiskBlock key={id} model={props.model} />;
    case "risk-queue":
      return (
        <RiskQueueBlock
          key={id}
          model={props.model}
          onSelectEvent={props.onSelectEvent}
        />
      );
    case "asset-brief":
      return (
        <AssetBriefBlock
          key={id}
          model={props.model}
          event={props.selectedEvent}
          onOpenAsset={props.onOpenAsset}
        />
      );
    case "production-exposure":
      return (
        <ProductionExposureBlock
          key={id}
          detail={props.detail}
          companyContext={props.companyContext}
        />
      );
    case "decision-queue":
      return (
        <DecisionQueueBlock
          key={id}
          model={props.model}
          selectedEvent={props.selectedEvent}
          onSelectEvent={props.onSelectEvent}
        />
      );
    case "decision-bottleneck":
      return (
        <DecisionBottleneckBlock
          key={id}
          model={props.model}
          selectedEvent={props.selectedEvent}
          detail={props.detail}
          onSelectEvent={props.onSelectEvent}
          compact={compactExecutiveBrief}
        />
      );
    case "workflow-lifecycle":
      return <WorkflowLifecycleBlock key={id} detail={props.detail} />;
    case "case-lineage":
      return <CaseLineageBlock key={id} props={props} />;
    case "workflow-actions":
      return <WorkflowActionsBlock key={id} props={props} />;
    case "sensor-signals":
      return <SensorSignalsBlock key={id} detail={props.detail} />;
    case "feature-trend":
      return (
        <FeatureTrendBlock
          key={id}
          detail={props.detail}
          loading={props.detailLoading}
        />
      );
    case "evidence-factors":
      return <EvidenceFactorsBlock key={id} detail={props.detail} />;
    case "inspection-targets":
      return <InspectionTargetsBlock key={id} detail={props.detail} />;
    case "maintenance-history":
      return (
        <MaintenanceHistoryBlock
          key={id}
          detail={props.detail}
          companyContext={props.companyContext}
          assetId={assetId}
        />
      );
    case "maintenance-effect":
      return (
        <MaintenanceEffectBlock
          key={id}
          detail={props.detail}
          companyContext={props.companyContext}
          assetId={assetId}
        />
      );
    case "material-context":
      return (
        <MaterialContextBlock
          key={id}
          companyContext={props.companyContext}
          assetId={assetId}
        />
      );
    case "decision-history":
      return (
        <DecisionHistoryBlock
          key={id}
          detail={props.detail}
          context={props.companyContext}
          assetId={assetId}
        />
      );
    case "report-summary":
      return (
        <ReportSummaryBlock
          key={id}
          detail={props.detail}
          event={props.selectedEvent}
          model={props.model}
          experienceKind={props.experienceKind}
          canMaterializeAgentSummary={props.canMaterializeAgentSummary}
          onOpenReport={props.onOpenReport}
          compact={compactExecutiveBrief}
        />
      );
    case "context-evidence":
      return (
        <ContextEvidenceBlock
          key={id}
          context={props.companyContext}
          assetId={assetId}
        />
      );
    case "data-quality":
      return (
        <DataQualityBlock key={id} detail={props.detail} model={props.model} />
      );
  }
}

export function RoleComposedWorkspace(props: RoleComposedWorkspaceProps) {
  const { locale } = useI18n();
  const english = locale === "en-US";
  const materials = relevantMaterials(
    props.companyContext,
    props.selectedEvent?.assetId,
  );
  const exposureValue = exposure({
    detail: props.detail,
    companyContext: props.companyContext,
  });
  const hasMaintenanceOutcome = Boolean(
    props.detail?.closedLoop?.maintenanceEvents.length ||
    props.detail?.closedLoop?.maintenanceActions.some(
      (item) => item.status === "completed",
    ),
  );
  const signals = {
    hasCriticalRisk: props.model.metrics.critical > 0,
    hasDataQualityHold:
      props.model.metrics.dataQualityHold > 0 ||
      Boolean(props.detail?.dataQualityWarnings.length),
    hasOpenWorkflow: Boolean(
      props.detail?.closedLoop?.workOrders.length ||
      props.detail?.closedLoop?.maintenanceActions.length,
    ),
    hasMaterialConstraint: materials.some(
      (item) => item.on_hand_quantity <= item.reorder_point,
    ),
    hasDecisionBacklog: props.model.metrics.pendingDecisions >= 3,
    hasHighProductionExposure:
      typeof exposureValue.revenueExposure === "number" &&
      exposureValue.revenueExposure >= 10_000_000,
    hasMaintenanceOutcome,
  };
  const blocks = resolveReliabilityComposition(
    props.experienceKind,
    props.view,
    signals,
    props.surfaceId,
  );
  const promotionReason = signals.hasDataQualityHold
    ? localized(english, `우선순위 상승 · 데이터 품질 확인 ${formatNumber(props.model.metrics.dataQualityHold, false)}건`, `Priority raised · ${formatNumber(props.model.metrics.dataQualityHold, true)} data-quality item(s) need review`)
    : props.experienceKind === "operations" && signals.hasDecisionBacklog
      ? localized(english, `우선순위 상승 · 판단 대기 ${formatNumber(props.model.metrics.pendingDecisions, false)}건`, `Priority raised · ${formatNumber(props.model.metrics.pendingDecisions, true)} decision(s) pending`)
      : props.experienceKind === "engineering" && signals.hasCriticalRisk
        ? localized(english, `우선순위 상승 · 긴급 설비 ${formatNumber(props.model.metrics.critical, false)}대`, `Priority raised · ${formatNumber(props.model.metrics.critical, true)} critical asset(s)`)
        : props.experienceKind === "executive" &&
            signals.hasHighProductionExposure
          ? localized(english, "우선순위 상승 · 선택 Case의 생산·재무 노출이 기준치를 초과했습니다", "Priority raised · selected case production and financial exposure exceeds the threshold")
          : signals.hasMaterialConstraint
            ? localized(english, "우선순위 상승 · 선택 Case의 자재 제약을 먼저 확인합니다", "Priority raised · review selected case material constraints first")
            : signals.hasMaintenanceOutcome
              ? localized(english, "우선순위 상승 · 정비 완료 후 효과 확인이 필요합니다", "Priority raised · confirm post-maintenance effect")
              : null;
  const promotionReasonSurfaces = new Set([
    "factory-status",
    "monitoring",
    "operations-overview",
    "operational-risk",
  ]);
  const shouldShowPromotionReason =
    props.view === "overview" &&
    (!props.surfaceId || promotionReasonSurfaces.has(props.surfaceId));

  return (
    <WorkspaceEnglishContext.Provider value={english}>
      <div
      className={`rw-composed-grid composition-${props.experienceKind}`}
      data-testid={`role-composed-${props.experienceKind}`}
      data-surface={props.surfaceId ?? "default"}
      data-selected-event-id={props.selectedEvent?.eventId ?? ""}
      data-composition={blocks.join(",")}
    >
      {shouldShowPromotionReason && promotionReason ? (
        <div className="rw-composition-reason" role="status">
          <strong>{promotionReason}</strong>
          <span>{localized(english, "현재 운영 상태에 따라 중요한 블록을 위로 배치했습니다.", "Important blocks were brought forward based on the current operating state.")}</span>
        </div>
      ) : null}
      {blocks.map((id) => renderBlock(id, props))}
      </div>
    </WorkspaceEnglishContext.Provider>
  );
}
