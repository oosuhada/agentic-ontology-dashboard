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
  ListChecks,
  PackageSearch,
  RadioTower,
  RotateCcw,
  ShieldAlert,
  TimerReset,
  TrendingDown,
  Wrench,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
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
  OperationsEvent,
  OperationsEventDetailModel,
  OperationsReportTab,
  OperationsRoleLens,
  OperationsView,
} from "../../operations/api/operationsContracts";
import {
  displayExplanationMethod,
  displayArtifactKind,
  displayInspectionAssociation,
  displayReportType,
  displaySensorFactorLabel,
  displaySensorLabel,
  fieldFailureLabel,
} from "../../operations/displayLabels";
import { MaintenanceWorkflowActionPanel } from "../../operations/maintenance/MaintenanceWorkflowActionPanel";
import { MaintenanceCostDecisionPanel } from "../../operations/maintenance/MaintenanceCostDecisionPanel";
import type { ReliabilityExperienceKind } from "./roleExperience";
import {
  resolveReliabilityComposition,
  type ReliabilityBlockId,
} from "./roleComposition";
import "./role-composed-workspace.css";

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
  className = "",
  children,
}: {
  title: string;
  eyebrow?: string;
  icon?: ReactNode;
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
      </header>
      <div className="rw-composed-block__body">{children}</div>
    </section>
  );
}

function probability(value: number | null | undefined) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

function money(value: number | null | undefined) {
  return typeof value === "number"
    ? `${Math.round(value).toLocaleString("ko-KR")}원`
    : "—";
}

function compactMoney(value: number | null | undefined) {
  if (typeof value !== "number") return "—";
  if (Math.abs(value) >= 100_000_000)
    return `${(value / 100_000_000).toFixed(1)}억원`;
  if (Math.abs(value) >= 10_000)
    return `${Math.round(value / 10_000).toLocaleString("ko-KR")}만원`;
  return money(value);
}

function dateTime(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString("ko-KR", {
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

function duration(value: number | null | undefined) {
  if (typeof value !== "number") return "—";
  if (value < 60) return `${value}분`;
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  return minutes ? `${hours}시간 ${minutes}분` : `${hours}시간`;
}

function decisionLabel(
  value: OperationsEvent["recommendedDecision"] | null | undefined,
) {
  const labels: Record<OperationsEvent["recommendedDecision"], string> = {
    continue_monitoring: "계속 관찰",
    request_inspection: "현장 점검 요청",
    review_shutdown: "정지 검토 요청",
    hold_for_data_check: "데이터 확인 후 판단",
  };
  return value ? labels[value] : "판단 대기";
}

function riskLabel(value: OperationsEvent["status"] | null | undefined) {
  if (value === "critical") return "고위험";
  if (value === "warning") return "경고";
  if (value === "attention") return "주의";
  if (value === "data_quality_hold") return "데이터 확인 필요";
  if (value === "normal") return "정상";
  return "상태 확인 중";
}

function ownerLabel(value: string | null | undefined) {
  if (!value || /unassigned|pending/i.test(value)) return "담당 미지정";
  return value;
}

function criticalityLabel(
  value: OperationsEvent["criticality"] | null | undefined,
) {
  if (value === "high") return "높음";
  if (value === "medium") return "중간";
  if (value === "low") return "낮음";
  return "확인 필요";
}

function factorDirectionLabel(value: "risk_up" | "risk_down") {
  return value === "risk_up" ? "위험 증가 방향" : "위험 감소 방향";
}

function waitingMinutes(value: string | null | undefined) {
  if (!value) return null;
  const start = Date.parse(value);
  if (!Number.isFinite(start)) return null;
  return Math.max(0, Math.round((Date.now() - start) / 60_000));
}

function workflowStatusLabel(value: string | null | undefined) {
  const labels: Record<string, string> = {
    requested: "승인 대기",
    approved: "승인됨",
    in_progress: "진행 중",
    completed: "완료",
    planned: "계획됨",
    prediction: "예측",
    evidence: "근거 확인",
    decision: "운영 판단",
    inspection_requested: "점검 요청",
    inspection_approved: "점검 승인",
    inspection_in_progress: "점검 중",
    inspection_completed: "점검 완료",
    maintenance_requested: "정비 요청",
    maintenance_approved: "정비 승인",
    maintenance_in_progress: "정비 중",
    maintenance_completed: "정비 완료",
    post_maintenance_observation_pending: "정비 후 관측 대기",
    ready_for_reprediction: "재예측 가능",
  };
  return value ? (labels[value] ?? value.replaceAll("_", " ")) : "대기";
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
  const activeWork = detail?.closedLoop?.workOrders.some((item) =>
    ["approved", "in_progress"].includes(item.status),
  )
    ? 1
    : 0;
  const allMetrics = [
    ["전체 연결 설비", model.metrics.totalAssets.toLocaleString("ko-KR")],
    ["정상 설비", model.metrics.normal.toLocaleString("ko-KR")],
    [
      "주의 설비",
      (model.metrics.attention + model.metrics.warning).toLocaleString("ko-KR"),
    ],
    ["긴급 설비", model.metrics.critical.toLocaleString("ko-KR")],
    ["선택 Case 진행 작업", activeWork.toLocaleString("ko-KR")],
    ["판단 대기", model.metrics.pendingDecisions.toLocaleString("ko-KR")],
    [
      "마지막 수신",
      dateTime(model.context.observedAt ?? model.context.refreshedAt),
    ],
  ];
  const metrics = compact
    ? allMetrics.filter(([label]) =>
        ["긴급 설비", "주의 설비", "판단 대기", "마지막 수신"].includes(label),
      )
    : allMetrics;
  return (
    <Block
      title={compact ? "전체 운영 리스크" : "현재 운영 신호"}
      eyebrow="LIVE STATUS"
      icon={<Gauge size={15} />}
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
  const eventByAsset = new Map(
    model.events.map((event) => [event.assetId, event]),
  );
  const lines = [...new Set(model.assets.map((asset) => asset.line))].sort();
  return (
    <Block
      title="공장 설비 상태맵"
      eyebrow="REAL-TIME FACTORY STATUS"
      icon={<Building2 size={15} />}
      className="span-12"
    >
      <div className="rw-factory-map">
        {lines.map((line) => {
          const assets = model.assets.filter((asset) => asset.line === line);
          return (
            <section key={line}>
              <header>
                <strong>{line}</strong>
                <span>{assets.length} assets</span>
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
                      title={`${asset.displayName} · ${asset.status} · ${probability(asset.failureProbability)}`}
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

function shortTime(value: string | null | undefined) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleTimeString("ko-KR", {
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
  const activeLabel = `${dateTime(activePoint.observedAt)} · 위험도 ${probability(activePoint.failureProbability)} · ${riskLabel(activePoint.status as OperationsEvent["status"] | null)}`;
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
        <div><RotateCcw size={17} /><strong>고장 위험 추세</strong></div>
        <span className="asset-baseline-key">
          <i style={{ background: color }} />
          10분 요약 라인 · 터치/호버 정확값 · NOW 실시간
          {" · "}
          {probability(detail.event.failureProbability)}
        </span>
      </header>
      <svg
        className="asset-series-chart"
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        role="img"
        tabIndex={0}
        aria-label={`고장 위험 추세와 판단 임계값. 좌우 방향키로 ${coords.length}개 관측을 탐색합니다.`}
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
              판단 경계 {Math.round(detail.threshold * 100)}%
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
            단기 추세 범위
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
              <title>{`${dateTime(point.observedAt)} · 위험도 ${probability(point.failureProbability)} · ${riskLabel(point.status as OperationsEvent["status"] | null)}`}</title>
            </circle>
          </g>
        ) : null)}
        <text
          className="asset-chart-axis"
          x={frame.left}
          y={xAxisY}
          textAnchor="start"
        >
          {shortTime(plottedSeries[0]?.observedAt)}
        </text>
        <text
          className="asset-chart-axis"
          x={frame.right}
          y={xAxisY}
          textAnchor="end"
        >
          {shortTime(plottedSeries.at(-1)?.observedAt)}
        </text>
        <text
          className="asset-chart-axis"
          x={forecastRight}
          y={xAxisY}
          textAnchor="end"
        >
          +30s
        </text>
        <text className="asset-chart-axis-title" x={chartWidth / 2} y={xAxisTitleY} textAnchor="middle">시간</text>
      </svg>
      <span className="rw-chart-keyboard-value" aria-live="polite">
        선택 관측 · {activeLabel}
      </span>
      <small>
        {lastHistoryAt &&
        currentAt &&
        Date.parse(currentAt) > Date.parse(lastHistoryAt)
          ? "현재값은 history plot 이후 새 관측으로 이어 표시합니다."
          : "현재 Case의 고정 관측 기준입니다."}
      </small>
    </article>
  );
}

function SensorTrendChart({
  sensor,
}: {
  sensor: OperationsEventDetailModel["sensors"][number];
}) {
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
  const activeLabel = `${dateTime(activePoint.observedAt)} · ${activePoint.value.toLocaleString("ko-KR", { maximumFractionDigits: 3 })}${sensor.unit ? ` ${sensor.unit}` : ""} · 품질 ${activePoint.qualityStatus === "bad" ? "불량" : activePoint.qualityStatus === "good" ? "정상" : "미확인"}`;
  const move = (delta: number) =>
    setActiveIndex((index) =>
      Math.max(0, Math.min(coords.length - 1, index + delta)),
    );
  const livePoint = coords.at(-1) ?? null;
  const liveValueLabel = livePoint
    ? `${livePoint.value.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}${sensor.unit ? ` ${sensor.unit}` : ""}`
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
          10분 요약 라인 · 터치/호버 정확값 · NOW 실시간
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
        aria-label={`${sensor.label} 최근 추세. 좌우 방향키로 ${coords.length}개 관측을 탐색합니다.`}
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
              {tick.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}
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
            단기 추세 범위
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
              <title>{`${dateTime(point.observedAt)} · ${point.value.toLocaleString("ko-KR", { maximumFractionDigits: 3 })}${sensor.unit ? ` ${sensor.unit}` : ""} · 품질 ${point.qualityStatus === "bad" ? "불량" : point.qualityStatus === "good" ? "정상" : "미확인"}`}</title>
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
            {shortTime(plottedPoints[0].observedAt)}
          </text>
        ) : null}
        {plottedPoints.length > 2 ? (
          <text
            className="asset-chart-axis"
            x={xAt(middleIndex)}
            y={xAxisY}
            textAnchor="middle"
          >
            {shortTime(plottedPoints[middleIndex].observedAt)}
          </text>
        ) : null}
        {plottedPoints.at(-1) ? (
          <text
            className="asset-chart-axis"
            x={frame.right}
            y={xAxisY}
            textAnchor="end"
          >
            {shortTime(plottedPoints.at(-1)?.observedAt)}
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
        <text className="asset-chart-axis-title" x={chartWidth / 2} y={xAxisTitleY} textAnchor="middle">시간</text>
      </svg>
      <span className="rw-chart-keyboard-value" aria-live="polite">
        선택 관측 · {activeLabel}
      </span>
      <small>
        history {numericHistory.length}개 · plot 마지막{" "}
        {dateTime(latestHistory?.observedAt)}
        {sensor.observedAt &&
        latestHistory &&
        Date.parse(sensor.observedAt) > Date.parse(latestHistory.observedAt)
          ? ` · 현재값 ${dateTime(sensor.observedAt)}는 plot 이후 관측`
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
  const sensors =
    detail?.sensors
      .filter((sensor) => (sensor.historyPoints?.length ?? 0) > 1)
      .slice(0, 4) ?? [];
  const hasChartData = Boolean(detail?.riskSeries.length || sensors.length);
  return (
    <Block
      title="실시간 피쳐 그래프"
      eyebrow="FEATURE TREND"
      icon={<RadioTower size={15} />}
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
        <Empty text="선택 설비의 시계열 관측이 준비되면 핵심 피쳐 2~4개를 표시합니다." />
      )}
    </Block>
  );
}

function BusinessKpisBlock({
  context,
}: {
  context: OperationsCompanyContext | null;
}) {
  return (
    <Block
      title="경영 KPI 기준"
      eyebrow="BUSINESS CONTEXT"
      icon={<BriefcaseBusiness size={15} />}
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
                  ? compactMoney(item.value)
                  : `${item.value.toLocaleString("ko-KR")} ${item.unit}`}
              </b>
            </article>
          ))}
        </div>
      ) : (
        <Empty text="경영 KPI 문맥을 불러오는 중입니다." />
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
    ["Decision Lead Time", duration(decisionLeadTime)],
    [
      "보고 검토 상태",
      detail?.report.revision && detail.report.revision > 0
        ? `rev ${detail.report.revision}`
        : "검토 전",
    ],
    ["점검 처리 시간", duration(inspectionLeadTime)],
    ["승인→정비 착수", duration(maintenanceLeadTime)],
    [
      "판단 Backlog",
      `${model.metrics.pendingDecisions.toLocaleString("ko-KR")}건`,
    ],
    [
      "생산 손실 노출",
      value.lostUnits !== null
        ? `${value.lostUnits.toLocaleString("ko-KR")}개`
        : "—",
    ],
    ["공헌이익 노출", compactMoney(value.contributionExposure)],
    ["동일 설비 과거 정비", `${repeatedMaintenance.toLocaleString("ko-KR")}건`],
  ];
  const missingEvidence = [
    decisionLeadTime === null ? "Decision Lead Time" : null,
    inspectionLeadTime === null
      ? "점검 처리 시간(점검 결과 기록 후 계산)"
      : null,
    maintenanceLeadTime === null ? "승인→정비 착수(정비 승인 후 계산)" : null,
    value.lostUnits === null ? "생산 손실" : null,
    value.contributionExposure === null ? "공헌이익 노출" : null,
  ].filter((item): item is string => Boolean(item));
  return (
    <Block
      title="운영 의사결정 KPI"
      eyebrow="CASE OPERATING KPI"
      icon={<TimerReset size={15} />}
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
          현재 Case에서 아직 연결되지 않은 KPI 근거:{" "}
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
  const ranked = [...model.events]
    .sort((a, b) => (b.failureProbability ?? -1) - (a.failureProbability ?? -1))
    .slice(0, 6);
  return (
    <Block
      title="운영 리스크 포트폴리오"
      eyebrow="RISK PORTFOLIO"
      icon={<ChartNoAxesCombined size={15} />}
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
                {event.line} · {event.status}
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
  return (
    <Block
      title="라인별 위험"
      eyebrow="LINE RISK"
      icon={<Activity size={15} />}
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
  const ranked = [...model.events]
    .sort((a, b) => (b.failureProbability ?? -1) - (a.failureProbability ?? -1))
    .slice(0, 7);
  return (
    <Block
      title="우선 확인 큐"
      eyebrow="PRIORITY QUEUE"
      icon={<ShieldAlert size={15} />}
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
                {fieldFailureLabel(event.predictedFailureType)} ·{" "}
                {ownerLabel(event.assignedEngineer)}
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
  const asset = selectedAsset(model, event);
  return (
    <Block
      title="선택 설비"
      eyebrow="ASSET CONTEXT"
      icon={<Boxes size={15} />}
      className="span-6"
    >
      {asset ? (
        <div className="rw-composed-kv">
          <div>
            <span>설비</span>
            <strong>{asset.displayName}</strong>
          </div>
          <div>
            <span>라인</span>
            <strong>{asset.line}</strong>
          </div>
          <div>
            <span>중요도</span>
            <strong>{criticalityLabel(asset.criticality)}</strong>
          </div>
          <div>
            <span>담당</span>
            <strong>{ownerLabel(asset.assignedEngineer)}</strong>
          </div>
          <div>
            <span>위험</span>
            <strong>{probability(asset.failureProbability)}</strong>
          </div>
          <div>
            <span>예상 정지</span>
            <strong>
              {asset.estimatedDowntimeMinutes !== null
                ? `${asset.estimatedDowntimeMinutes}분`
                : "근거 미제공"}
            </strong>
          </div>
          <button
            type="button"
            onClick={() => onOpenAsset(asset.assetId, asset.eventId)}
          >
            설비 근거 중심으로 보기
          </button>
        </div>
      ) : (
        <Empty text="설비를 선택하면 역할에 맞는 상세 근거를 구성합니다." />
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
  const value = exposure({ detail, companyContext });
  return (
    <Block
      title="생산 · 재무 영향"
      eyebrow="PRODUCTION EXPOSURE"
      icon={<CircleDollarSign size={15} />}
      className="span-6"
    >
      {detail?.operationContext ? (
        <>
          <div className="rw-composed-kv">
            <div>
              <span>생산 영향</span>
              <strong>
                {detail.operationContext.productionImpact === "high"
                  ? "높음"
                  : detail.operationContext.productionImpact === "medium"
                    ? "중간"
                    : detail.operationContext.productionImpact === "low"
                      ? "낮음"
                      : detail.operationContext.productionImpact === "none"
                        ? "현재 영향 없음"
                        : "—"}
              </strong>
            </div>
            <div>
              <span>예상 손실 수량</span>
              <strong>
                {value.lostUnits !== null
                  ? `${value.lostUnits.toLocaleString("ko-KR")}개`
                  : "—"}
              </strong>
            </div>
            <div>
              <span>제품</span>
              <strong>
                {value.product?.name ??
                  detail.operationContext.eventImpact?.productVariant ??
                  "—"}
              </strong>
            </div>
            <div>
              <span>매출 노출액</span>
              <strong>{compactMoney(value.revenueExposure)}</strong>
            </div>
            <div>
              <span>공헌이익 노출액</span>
              <strong>{compactMoney(value.contributionExposure)}</strong>
            </div>
          </div>
          {detail.operationContext.eventImpact?.basis.formula ? (
            <details className="rw-technical-details">
              <summary>산정 근거 상세</summary>
              <code>{detail.operationContext.eventImpact.basis.formula}</code>
            </details>
          ) : null}
        </>
      ) : (
        <Empty text="선택 이벤트의 생산 영향 문맥이 없습니다." />
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
  const queue = model.events
    .filter((event) => event.recommendedDecision !== "continue_monitoring")
    .slice(0, 7);
  return (
    <Block
      title="Decision Case"
      eyebrow="DECISION QUEUE"
      icon={<ListChecks size={15} />}
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
                {decisionLabel(event.recommendedDecision)} ·{" "}
                {ownerLabel(event.assignedEngineer)}
                {waitingMinutes(event.observedAt) !== null
                  ? ` · 대기 ${duration(waitingMinutes(event.observedAt))}`
                  : ""}
              </small>
            </div>
            <b>{riskLabel(event.status)}</b>
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
      title="의사결정 병목"
      eyebrow="DECISION BOTTLENECK"
      icon={<TimerReset size={15} />}
      className={compact ? "span-6 executive-summary-card" : "span-12"}
    >
      <p className="rw-bottleneck-sla-note">
        <strong>대기시간 기준</strong> 현재 Backend에 승인된 Decision SLA 계약이
        없어 SLA 초과 여부를 임의 계산하지 않습니다. 아래 값은 Case 발생 후
        경과시간입니다.
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
                  {ownerLabel(event.assignedEngineer)} ·{" "}
                  {decisionLabel(event.recommendedDecision)}
                </small>
              </div>
              <b>{duration(waitingMinutes(event.observedAt))}</b>
            </button>
          ))}
        </div>
      ) : delayed.length ? (
        <div
          className="rw-bottleneck-table"
          role="table"
          aria-label="지연 Decision Case"
        >
          <header role="row">
            <span>Case</span>
            <span>대기</span>
            <span>Owner</span>
            <span>결정 요청</span>
            <span>영향</span>
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
                <span>{duration(waitingMinutes(event.observedAt))}</span>
                <span>{ownerLabel(event.assignedEngineer)}</span>
                <span>{decisionLabel(event.recommendedDecision)}</span>
                <span>
                  {impact === "high"
                    ? "높음"
                    : impact === "medium"
                      ? "중간"
                      : impact === "low"
                        ? "낮음"
                        : event.estimatedDowntimeMinutes !== null
                          ? `${event.estimatedDowntimeMinutes}분 노출`
                          : "확인 중"}
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <Empty text="현재 판단 대기 Case가 없습니다." />
      )}
    </Block>
  );
}

function WorkflowLifecycleBlock({
  detail,
}: {
  detail: OperationsEventDetailModel | null;
}) {
  const lifecycle = detail?.closedLoop?.lifecycleSummary ?? null;
  return (
    <Block
      title="현재 Workflow 단계"
      eyebrow="CLOSED LOOP"
      icon={<ClipboardCheck size={15} />}
      className="span-6"
    >
      {lifecycle ? (
        <div className="rw-composed-lifecycle">
          <strong>{lifecycle.currentStepLabel}</strong>
          <div>
            {lifecycle.completedSteps.map((step) => (
              <span key={step}>{workflowStatusLabel(step)}</span>
            ))}
          </div>
          <p>다음 단계: {workflowStatusLabel(lifecycle.nextStep)}</p>
        </div>
      ) : (
        <div className="rw-workflow-prerequisite">
          <strong>작업 요청 전</strong>
          <p>
            현재 Case의 근거 snapshot은 준비되어 있습니다. 운영 관리자가 점검
            작업요청을 생성하면 closed-loop가 시작됩니다.
          </p>
        </div>
      )}
    </Block>
  );
}

function CaseLineageBlock({ props }: { props: RoleComposedWorkspaceProps }) {
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
        : "이벤트 선택 필요",
      detail: event
        ? `${event.status} · ${dateTime(event.observedAt)}`
        : "공장 상태맵에서 설비를 선택하세요.",
    },
    {
      id: "evidence",
      label: "Evidence",
      state: detail?.topFactors.length ? "done" : "pending",
      headline: detail?.topFactors.length
        ? `${detail.topFactors.length}개 모델 근거`
        : "근거 조회 중",
      detail: detail?.inspectionTargets[0]?.componentLabel
        ? `점검 대상 ${detail.inspectionTargets[0].componentLabel}`
        : "센서·모델·SOP 근거 연결",
    },
    {
      id: "decision",
      label: "Decision",
      state: firstDecision ? "done" : event ? "active" : "pending",
      headline:
        firstDecision?.title ??
        decisionLabel(event?.recommendedDecision) ??
        "판단 대기",
      detail: firstDecision
        ? `${firstDecision.actor} · ${dateTime(firstDecision.createdAt)}`
        : "운영 판단과 Owner가 기록됩니다.",
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
        ? `${latestWork.workType} · ${workflowStatusLabel(latestWork.status)}`
        : (detail?.closedLoop?.primaryAction?.label ?? "점검 작업요청 미생성"),
      detail: latestWork
        ? `${latestWork.workOrderId} · ${latestWork.actorDisplayName ?? latestWork.assignedTo ?? "담당 미정"}`
        : "승인된 점검·정비 작업이 연결됩니다.",
    },
    {
      id: "outcome",
      label: "Outcome",
      state: finalReportReady ? "done" : completedAt ? "active" : "pending",
      headline: finalReportReady
        ? "정비 후 관측 확인 완료"
        : completedAt
          ? "정비 후 관측 대기"
          : "결과 대기",
      detail: finalReportReady
        ? `정비 완료 ${dateTime(completedAt)} · 검증된 후속 관측과 보고 snapshot 연결`
        : completedAt
          ? "정비 완료만으로 Outcome을 확정하지 않습니다. 후속 관측이 필요합니다."
          : "승인된 Action이 완료된 뒤 Outcome 관측을 시작합니다.",
    },
  ];
  return (
    <Block
      title="Event → Outcome lineage"
      eyebrow="CASE LINEAGE"
      icon={<GitBranch size={15} />}
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
            설비 근거 열기
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
              ? "보고 초안 이어보기"
              : "보고 산출물 보기"}
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
  const asset = selectedAsset(props.model, props.selectedEvent);
  if (!props.selectedEvent || !asset)
    return (
      <Block
        title="업무 실행"
        eyebrow="ACTION"
        icon={<Wrench size={15} />}
        className="span-12"
      >
        <Empty text="작업할 이벤트를 선택하세요." />
      </Block>
    );
  return (
    <Block
      title="업무 실행"
      eyebrow="GOVERNED ACTION"
      icon={<Wrench size={15} />}
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
        onChanged={props.onWorkflowChanged}
      />
      <MaintenanceCostDecisionPanel
        projectId={props.model.context.projectId}
        workspaceId={props.model.context.workspaceId}
        eventId={props.selectedEvent.eventId}
        guidance={props.detail?.inspectionTargets.find((item) => item.inspectionGuidance)?.inspectionGuidance ?? null}
        onChanged={props.onWorkflowChanged}
      />
    </Block>
  );
}

function SensorSignalsBlock({
  detail,
}: {
  detail: OperationsEventDetailModel | null;
}) {
  return (
    <Block
      title="센서 · 피쳐"
      eyebrow="OBSERVED SIGNALS"
      icon={<RadioTower size={15} />}
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
                    ? dateTime(sensor.observedAt)
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
        <Empty text="선택 설비의 센서 근거를 불러오는 중입니다." />
      )}
    </Block>
  );
}

function EvidenceFactorsBlock({
  detail,
}: {
  detail: OperationsEventDetailModel | null;
}) {
  return (
    <Block
      title="위험 기여 근거"
      eyebrow="MODEL EVIDENCE"
      icon={<ChartNoAxesCombined size={15} />}
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
                  {displaySensorFactorLabel(factor.feature, factor.label)}
                </strong>
                <small>
                  {factorDirectionLabel(factor.direction)} ·{" "}
                  {displayExplanationMethod(factor.explanationMethod) ??
                    "모델 근거"}
                </small>
              </div>
              <b>{Math.round(Math.abs(factor.contribution) * 100)}%</b>
            </article>
          ))}
        </div>
      ) : (
        <Empty text="모델 기여 근거가 없습니다." />
      )}
    </Block>
  );
}

function InspectionTargetsBlock({
  detail,
}: {
  detail: OperationsEventDetailModel | null;
}) {
  return (
    <Block
      title="점검 대상"
      eyebrow="INSPECTION PLAN"
      icon={<ClipboardCheck size={15} />}
      className="span-6"
    >
      {detail?.inspectionTargets.length ? (
        <div className="rw-composed-cards">
          {detail.inspectionTargets.slice(0, 5).map((target) => (
            <article key={target.targetId}>
              <strong>{target.componentLabel}</strong>
              <span>{target.locationLabel ?? "위치 확인 필요"}</span>
              <p>
                {target.inspectionMethod ??
                  displayInspectionAssociation(target.association)}
              </p>
            </article>
          ))}
        </div>
      ) : (
        <Empty text="현재 근거에서 특정된 점검 대상이 없습니다." />
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
  const records =
    companyContext?.maintenance_records.filter(
      (item) => item.asset_id === assetId,
    ) ?? [];
  const runtime = detail?.equipmentHistory ?? [];
  return (
    <Block
      title="정비 · 설비 이력"
      eyebrow="MAINTENANCE HISTORY"
      icon={<History size={15} />}
      className="span-6"
    >
      {records.length || runtime.length ? (
        <div className="rw-composed-timeline">
          {records.slice(0, 4).map((item) => (
            <article key={item.id}>
              <time>{dateTime(item.occurred_at)}</time>
              <strong>{item.component}</strong>
              <p>{item.symptom}</p>
              <small>
                {item.action} · 결과: {item.result}
              </small>
            </article>
          ))}
          {runtime.slice(0, 4).map((item, index) => (
            <article key={`${item.occurredAt}-${index}`}>
              <time>{dateTime(item.occurredAt)}</time>
              <strong>{item.kind}</strong>
              <p>{item.description}</p>
              <small>{item.source}</small>
            </article>
          ))}
        </div>
      ) : (
        <Empty text="연결된 과거 정비 기록이 없습니다." />
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
      title="정비 효과 Before / After"
      eyebrow="MAINTENANCE OUTCOME"
      icon={<TrendingDown size={15} />}
      className="span-12"
    >
      {completedAt ? (
        <div className="rw-maintenance-effect">
          <header>
            <div>
              <span>정비 완료 기준</span>
              <strong>{dateTime(completedAt)}</strong>
            </div>
            <b
              className={
                riskDelta !== null && riskDelta < 0 ? "is-improved" : ""
              }
            >
              {riskDelta === null
                ? "후속 관측 수집 중"
                : `위험도 ${riskDelta > 0 ? "+" : ""}${Math.round(riskDelta * 100)}%p`}
            </b>
          </header>
          <div className="rw-maintenance-effect-grid">
            <article>
              <span>정비 전 위험</span>
              <strong>{probability(beforeAverage)}</strong>
              <small>관측 {beforeRisk.length}건</small>
            </article>
            <article>
              <span>정비 후 위험</span>
              <strong>{probability(afterAverage)}</strong>
              <small>관측 {afterRisk.length}건</small>
            </article>
            <article>
              <span>알림 빈도</span>
              <strong>
                {beforeRisk.length && afterRisk.length
                  ? `${beforeAlerts} → ${afterAlerts}`
                  : "관측 대기"}
              </strong>
              <small>비정상 관측 수</small>
            </article>
          </div>
          {sensorEffects.length ? (
            <div className="rw-maintenance-sensor-effect">
              {sensorEffects.map((item) => (
                <article key={item.id}>
                  <span>{item.label}</span>
                  <strong>
                    {item.before.toLocaleString("ko-KR", {
                      maximumFractionDigits: 1,
                    })}{" "}
                    →{" "}
                    {item.after.toLocaleString("ko-KR", {
                      maximumFractionDigits: 1,
                    })}
                    {item.unit ? ` ${item.unit}` : ""}
                  </strong>
                  <small>
                    {item.delta > 0 ? "+" : ""}
                    {item.delta.toLocaleString("ko-KR", {
                      maximumFractionDigits: 1,
                    })}
                  </small>
                </article>
              ))}
            </div>
          ) : (
            <p>
              정비 전후 관측 구간이 충분해지면 핵심 센서의 회복 여부를 함께 표시합니다.
            </p>
          )}
        </div>
      ) : historical ? (
        <div className="rw-maintenance-history-fallback">
          <strong>참고 · 과거 유사 정비</strong>
          <p>{historical.action}</p>
          <span>{historical.result}</span>
          <small>
            {dateTime(historical.occurred_at)} · 현재 Decision Case의 Outcome이
            아닙니다.
          </small>
        </div>
      ) : (
        <Empty text="현재 Case에 연결된 정비 완료 및 정비 후 관측이 생기면 before/after 효과를 표시합니다." />
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
  const materials = relevantMaterials(companyContext, assetId);
  return (
    <Block
      title="자재 · 예비품"
      eyebrow="MATERIAL CONTEXT"
      icon={<PackageSearch size={15} />}
      className="span-6"
    >
      {materials.length ? (
        <div className="rw-composed-list static">
          {materials.map((item) => (
            <article key={item.id}>
              <div>
                <strong>{item.name}</strong>
                <small>
                  {item.category} · 리드타임 {item.lead_time_days}일
                </small>
              </div>
              <b
                className={
                  item.on_hand_quantity <= item.reorder_point
                    ? "is-warning"
                    : ""
                }
              >
                {item.on_hand_quantity}개
              </b>
            </article>
          ))}
        </div>
      ) : (
        <Empty text="선택 설비에 연결된 자재 master가 없습니다." />
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
      title="판단 이력"
      eyebrow="DECISION LINEAGE"
      icon={<FileClock size={15} />}
      className="span-6"
    >
      {decisions.length || detail?.activity.length ? (
        <div className="rw-composed-timeline">
          {decisions.map((item) => (
            <article key={item.id}>
              <time>{dateTime(item.decided_at)}</time>
              <strong>{item.title}</strong>
              <p>{item.decision}</p>
              <small>{item.source_ref}</small>
            </article>
          ))}
          {detail?.activity.slice(0, 4).map((item) => (
            <article key={item.id}>
              <time>{dateTime(item.createdAt)}</time>
              <strong>{item.title}</strong>
              <p>{item.detail}</p>
              <small>{item.actor}</small>
            </article>
          ))}
        </div>
      ) : (
        <Empty text="연결된 판단 이력이 없습니다." />
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
      ? "검토 가능한 결과 보고"
      : "업무 진행 중 · 초안";
  return (
    <Block
      title={compact ? "보고 준비 상태" : "역할별 보고 요약"}
      eyebrow="GROUNDED REPORT"
      icon={<FileText size={15} />}
      className={compact ? "span-6 executive-summary-card" : "span-12"}
    >
      {roleSummary && headline ? (
        <div className="rw-composed-report">
          <div className="rw-report-controls">
            <label>
              <span>보고 유형</span>
              <select
                value={reportType}
                onChange={(event) =>
                  setReportType(event.target.value as ReportType)
                }
              >
                <option value="inspection-summary">현장 점검 요약</option>
                <option value="operations-decision">운영 판단 보고</option>
                <option value="executive-brief">경영진 Executive Brief</option>
                <option value="maintenance-effect">
                  정비 효과 before-after
                </option>
                <option value="weekly-risk">주간 리스크 요약</option>
              </select>
            </label>
            <span>
              {variantLoading
                ? "보고 전환 중"
                : brief?.summary?.mode === "llm" || report?.mode === "llm"
                  ? "AI 근거 요약"
                  : "검증된 기본 보고"}
            </span>
          </div>
          {report ? (
            <div className="rw-report-artifact-meta">
              <span>{artifactStatus}</span>
              <strong>{displayReportType(report.reportType)}</strong>
              <small>{displayArtifactKind(report.reportId)}</small>
              <small>관측 기준 {dateTime(report.asOf ?? detail?.event.observedAt)}</small>
              <small className="rw-technical-metadata">Case {event?.eventId ?? "—"}</small>
              <small className="rw-technical-metadata">artifact {report.reportId}</small>
              {report.revision > 0 ? (
                <small>수정본 {report.revision}</small>
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
            <details className="rw-report-evidence rw-technical-metadata">
              <summary>
                근거 데이터 확인 · {new Set(evidenceRefs).size} refs
              </summary>
              <ul>
                {[...new Set(evidenceRefs)].slice(0, 12).map((ref) => (
                  <li key={ref}>
                    <code>{ref}</code>
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
              내용 미리보기
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
              보고서 출력 화면
            </button>
          </div>
        </div>
      ) : (
        <Empty text="선택 이벤트의 grounded report를 불러오는 중입니다." />
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
      title="조직 · 회의 · 의사결정 문맥"
      eyebrow="ONTOLOGY CONTEXT"
      icon={<Building2 size={15} />}
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
              <span>{dateTime(meeting.occurred_at)}</span>
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
        <Empty text="회사 및 조직 문맥을 불러오는 중입니다." />
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
  const warnings = detail?.dataQualityWarnings ?? [];
  return (
    <Block
      title="데이터 품질 확인 필요"
      eyebrow="DATA QUALITY HOLD"
      icon={<AlertTriangle size={15} />}
      className="span-12 is-warning-block"
    >
      <p>
        현재 데이터 품질 보류 항목이 {model.metrics.dataQualityHold}건 있습니다.
        품질 문제가 해소되기 전에는 고장 위험·생산 영향·정비 필요성을 확정하지
        않습니다.
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
    ? `우선순위 상승 · 데이터 품질 확인 ${props.model.metrics.dataQualityHold.toLocaleString("ko-KR")}건`
    : props.experienceKind === "operations" && signals.hasDecisionBacklog
      ? `우선순위 상승 · 판단 대기 ${props.model.metrics.pendingDecisions.toLocaleString("ko-KR")}건`
      : props.experienceKind === "engineering" && signals.hasCriticalRisk
        ? `우선순위 상승 · 긴급 설비 ${props.model.metrics.critical.toLocaleString("ko-KR")}대`
        : props.experienceKind === "executive" &&
            signals.hasHighProductionExposure
          ? `우선순위 상승 · 선택 Case의 생산·재무 노출이 기준치를 초과했습니다`
          : signals.hasMaterialConstraint
            ? "우선순위 상승 · 선택 Case의 자재 제약을 먼저 확인합니다"
            : signals.hasMaintenanceOutcome
              ? "우선순위 상승 · 정비 완료 후 효과 확인이 필요합니다"
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
          <span>현재 운영 상태에 따라 중요한 블록을 위로 배치했습니다.</span>
        </div>
      ) : null}
      {blocks.map((id) => renderBlock(id, props))}
    </div>
  );
}
