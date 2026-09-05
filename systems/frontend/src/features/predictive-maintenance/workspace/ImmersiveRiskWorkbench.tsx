import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  CircleDot,
  Gauge,
  RadioTower,
  ShieldAlert,
} from "lucide-react";
import { animate, createScope, stagger } from "animejs";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getPredictiveMaintenanceRiskIndex, selectPredictiveMaintenanceVersion } from "../../../api";
import type {
  OperationsBootstrapModel,
  OperationsEvent,
  OperationsEventDetailModel,
} from "../../operations/api/operationsContracts";
import { displayAssetName, displayLineLabel } from "../../operations/displayLabels";
import type {
  PredictiveMaintenanceRiskIndexResponse,
  PredictiveMaintenanceRiskSourceMode,
  PredictiveMaintenanceRiskWindow,
} from "../types";
import { BklitLiveRiskChart, type BklitLiveRiskPoint } from "./BklitLiveRiskChart";
import "./immersive-risk-workbench.css";

interface ImmersiveRiskWorkbenchProps {
  model: OperationsBootstrapModel;
  detail: OperationsEventDetailModel | null;
  selectedEvent: OperationsEvent | null;
  onSelectEvent: (event: OperationsEvent) => void;
  onRefresh: () => void;
  english: boolean;
}

function percent(value: number | null | undefined, digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${(value * 100).toFixed(digits)}%`
    : "—";
}

function timeLabel(value: number | null, english: boolean) {
  if (!value) return "—";
  return new Date(value * 1000).toLocaleString(english ? "en-US" : "ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function riskTone(status: OperationsEvent["status"] | null | undefined) {
  if (status === "critical") return "critical";
  if (status === "warning") return "warning";
  if (status === "attention") return "attention";
  if (status === "data_quality_hold") return "hold";
  return "normal";
}

function statusLabel(status: OperationsEvent["status"], english: boolean) {
  const labels: Record<OperationsEvent["status"], [string, string]> = {
    critical: ["고위험", "Critical"],
    warning: ["경고", "Warning"],
    attention: ["주의", "Attention"],
    normal: ["정상", "Normal"],
    data_quality_hold: ["데이터 확인", "Data hold"],
  };
  return labels[status][english ? 1 : 0];
}

function ageLabel(seconds: number | null | undefined, english: boolean) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return "—";
  if (seconds < 90) return english ? "just now" : "방금 전";
  if (seconds < 3600) return english ? `${Math.round(seconds / 60)}m ago` : `${Math.round(seconds / 60)}분 전`;
  if (seconds < 86400) return english ? `${Math.round(seconds / 3600)}h ago` : `${Math.round(seconds / 3600)}시간 전`;
  return english ? `${Math.round(seconds / 86400)}d ago` : `${Math.round(seconds / 86400)}일 전`;
}

export function ImmersiveRiskWorkbench({
  model,
  detail,
  selectedEvent,
  onSelectEvent,
  onRefresh,
  english,
}: ImmersiveRiskWorkbenchProps) {
  const rootRef = useRef<HTMLElement>(null);
  const animationScopeRef = useRef<ReturnType<typeof createScope> | null>(null);
  const reducedMotion = useReducedMotion();
  const [range, setRange] = useState<PredictiveMaintenanceRiskWindow>("24h");
  const [sourceMode, setSourceMode] = useState<PredictiveMaintenanceRiskSourceMode>("live");
  const [riskIndex, setRiskIndex] = useState<PredictiveMaintenanceRiskIndexResponse | null>(null);
  const [riskLoading, setRiskLoading] = useState(true);
  const [riskError, setRiskError] = useState<string | null>(null);
  const [followLivePending, setFollowLivePending] = useState(false);
  const [hoveredPoint, setHoveredPoint] = useState<BklitLiveRiskPoint | null>(null);
  const assetId = selectedEvent?.assetId ?? null;

  useEffect(() => {
    const controller = new AbortController();
    setRiskLoading(true);
    setRiskError(null);
    void getPredictiveMaintenanceRiskIndex(
      model.context.projectId,
      model.context.workspaceId,
      {
        source_mode: sourceMode,
        dataset_version_id: model.context.datasetVersionId,
        asset_id: assetId,
        window: range,
      },
      controller.signal,
    ).then((payload) => {
      setRiskIndex(payload);
      setHoveredPoint(null);
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return;
      setRiskError(reason instanceof Error ? reason.message : "risk_index_unavailable");
    }).finally(() => {
      if (!controller.signal.aborted) setRiskLoading(false);
    });
    return () => controller.abort();
  }, [assetId, model.context.datasetVersionId, model.context.projectId, model.context.refreshedAt, model.context.workspaceId, range, sourceMode]);

  const queriedSeries = useMemo<BklitLiveRiskPoint[]>(() => (
    (riskIndex?.points ?? [])
      .map((point) => ({
        time: Date.parse(point.observed_at) / 1000,
        value: point.value,
        status: point.status,
      }))
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
      .sort((left, right) => left.time - right.time)
  ), [riskIndex?.points]);
  const detailFallbackSeries = useMemo<BklitLiveRiskPoint[]>(() => (
    (detail?.riskSeries ?? [])
      .map((point) => ({
        time: Date.parse(point.observedAt) / 1000,
        value: point.failureProbability,
        status: point.status,
      }))
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
      .sort((left, right) => left.time - right.time)
  ), [detail?.riskSeries]);
  const usingDetailFallback = Boolean(riskError && assetId && detailFallbackSeries.length);
  const visibleSeries = queriedSeries.length
    ? queriedSeries
    : usingDetailFallback
      ? detailFallbackSeries
      : [];
  const currentRisk = hoveredPoint?.value
    ?? visibleSeries.at(-1)?.value
    ?? selectedEvent?.failureProbability
    ?? null;
  const currentTime = hoveredPoint?.time
    ?? visibleSeries.at(-1)?.time
    ?? (selectedEvent?.observedAt ? Date.parse(selectedEvent.observedAt) / 1000 : null);
  const firstRisk = visibleSeries.at(0)?.value ?? currentRisk;
  const delta = currentRisk !== null && firstRisk !== null ? currentRisk - firstRisk : null;
  const values = visibleSeries.map((point) => point.value);
  const min = values.length ? Math.min(...values) : currentRisk;
  const max = values.length ? Math.max(...values) : currentRisk;
  const rankedEvents = useMemo(() => [...model.events]
    .sort((left, right) => (right.failureProbability ?? -1) - (left.failureProbability ?? -1))
    .slice(0, 7), [model.events]);
  const activeAssetLabel = selectedEvent
    ? (english
      ? (selectedEvent.assetName || selectedEvent.assetId)
      : displayAssetName({ assetId: selectedEvent.assetId, displayName: selectedEvent.assetName }))
    : (english ? "Plant risk P95" : "공장 위험 P95");
  const sourceCanSwitch = Boolean(riskIndex?.workspace_is_pinned);
  const sourceBadge = usingDetailFallback
    ? (english ? "CASE DETAIL FALLBACK" : "CASE DETAIL FALLBACK")
    : sourceMode === "live"
    ? (english ? "LIVE GENERATOR" : "LIVE GENERATOR")
    : (english ? "WORKSPACE DATASET" : "WORKSPACE DATASET");
  const emptyTitle = riskLoading
    ? (english ? "Loading governed risk history" : "정본 위험 이력 불러오는 중")
    : riskError && !usingDetailFallback
      ? (english ? "Risk history query failed" : "위험 이력 조회 실패")
      : (english ? "No predictions in this range" : "선택 범위에 위험 관측 없음");
  const emptyDetail = riskLoading
    ? (english ? "Reading the selected live or workspace Dataset Version." : "선택한 live/workspace Dataset Version을 조회하고 있습니다.")
    : riskError && !usingDetailFallback
      ? riskError
      : (english ? "Try a wider time range or verify the selected data source." : "기간을 넓히거나 데이터 소스를 확인하세요.");

  async function followLiveDataset() {
    setFollowLivePending(true);
    setRiskError(null);
    try {
      await selectPredictiveMaintenanceVersion(
        model.context.projectId,
        model.context.workspaceId,
        null,
      );
      setSourceMode("live");
      onRefresh();
    } catch (reason) {
      setRiskError(reason instanceof Error ? reason.message : "follow_live_dataset_failed");
    } finally {
      setFollowLivePending(false);
    }
  }

  useEffect(() => {
    animationScopeRef.current?.revert();
    if (!rootRef.current || reducedMotion) return undefined;
    animationScopeRef.current = createScope({ root: rootRef }).add(() => {
      animate(".rw-market-workbench__metric", {
        opacity: [0, 1],
        translateY: [8, 0],
        duration: 430,
        delay: stagger(55),
        ease: "out(3)",
      });
      animate(".rw-market-signal-row", {
        opacity: [0, 1],
        translateX: [8, 0],
        duration: 380,
        delay: stagger(38, { start: 140 }),
        ease: "out(3)",
      });
      animate(".rw-market-live-pulse", {
        scale: [0.7, 1.35, 1],
        opacity: [0.35, 1, 0.75],
        duration: 780,
        ease: "out(4)",
      });
    });
    return () => {
      animationScopeRef.current?.revert();
      animationScopeRef.current = null;
    };
  }, [reducedMotion, selectedEvent?.eventId]);

  return (
    <motion.section
      ref={rootRef}
      className={`rw-market-workbench tone-${riskTone(selectedEvent?.status)}`}
      initial={reducedMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reducedMotion ? 0 : 0.34, ease: [0.22, 1, 0.36, 1] }}
      aria-label={english ? "Risk market-style workbench" : "위험 시계열 워크벤치"}
    >
      <div className="rw-market-workbench__primary">
        <header className="rw-market-workbench__headline">
          <div>
            <span className="rw-market-workbench__eyebrow"><RadioTower size={12} /> {english ? "LIVE RISK INDEX" : "실시간 위험 지수"}</span>
            <h2>{activeAssetLabel}</h2>
            <div className="rw-market-workbench__current">
              <strong>{percent(currentRisk)}</strong>
              {delta !== null ? (
                <em className={delta >= 0 ? "is-up" : "is-down"}>
                  {delta >= 0 ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                  {delta >= 0 ? "+" : ""}{percent(delta, 2)}
                </em>
              ) : null}
            </div>
            <small>{hoveredPoint ? (english ? "Hovered observation" : "선택 관측") : (english ? "Latest observation" : "최신 관측")} · {timeLabel(currentTime, english)} · {sourceBadge}</small>
          </div>
          <div className="rw-market-workbench__metrics">
            <article className="rw-market-workbench__metric"><span>{english ? "Start" : "시작"}</span><strong>{percent(firstRisk)}</strong></article>
            <article className="rw-market-workbench__metric"><span>{english ? "Low" : "최저"}</span><strong>{percent(min)}</strong></article>
            <article className="rw-market-workbench__metric"><span>{english ? "High" : "최고"}</span><strong>{percent(max)}</strong></article>
            <article className="rw-market-workbench__metric"><span>{english ? "Critical boundary" : "고위험 경계"}</span><strong>{percent(riskIndex?.threshold ?? detail?.threshold)}</strong></article>
          </div>
        </header>

        <div className="rw-market-workbench__range" role="group" aria-label={english ? "Risk history range" : "위험 이력 범위"}>
          {(["1h", "6h", "24h", "7d", "30d"] as const).map((item) => (
            <motion.button
              type="button"
              key={item}
              className={range === item ? "is-active" : ""}
              onClick={() => setRange(item)}
              whileTap={reducedMotion ? undefined : { scale: 0.96 }}
            >
              {range === item ? <motion.span className="rw-market-workbench__range-indicator" layoutId="rw-risk-range" /> : null}
              <b>{item.toUpperCase()}</b>
            </motion.button>
          ))}
          <span className="rw-market-workbench__live"><i className="rw-market-live-pulse" />{sourceMode === "live" ? (english ? "Live generator" : "Live generator") : (english ? "Pinned workspace" : "고정 workspace")}</span>
          {sourceCanSwitch ? (
            <div className="rw-market-workbench__source-switch" role="group" aria-label={english ? "Risk data source" : "위험 데이터 소스"}>
              <button type="button" className={sourceMode === "live" ? "is-active" : ""} onClick={() => setSourceMode("live")}>LIVE</button>
              <button type="button" className={sourceMode === "workspace" ? "is-active" : ""} onClick={() => setSourceMode("workspace")}>{english ? "PINNED" : "고정"}</button>
            </div>
          ) : null}
        </div>

        {riskIndex ? (
          <div className={`rw-market-workbench__provenance ${riskIndex.workspace_is_pinned ? "is-pinned" : ""}`}>
            <span>{riskIndex.aggregation === "plant_failure_probability_p95" ? (english ? "Plant P95 · auditable aggregate" : "공장 P95 · 감사 가능한 집계") : (english ? "Selected asset · bucket mean" : "선택 설비 · 구간 평균")}</span>
            <span>{english ? "Latest" : "최신"} {ageLabel(riskIndex.data_age_seconds, english)}</span>
            <span className="rw-technical-metadata">{riskIndex.dataset_version_id}</span>
            {riskIndex.workspace_is_pinned ? <strong>{english ? "Workspace is pinned to an older Dataset Version" : "Workspace가 과거 Dataset Version에 고정됨"}</strong> : null}
            {riskIndex.workspace_is_pinned && sourceMode === "live" ? (
              <button type="button" disabled={followLivePending} onClick={() => void followLiveDataset()}>
                {followLivePending
                  ? (english ? "Following live…" : "전환 중…")
                  : (english ? "Use live dataset for workspace" : "Workspace도 live 데이터로 전환")}
              </button>
            ) : null}
          </div>
        ) : usingDetailFallback ? (
          <div className="rw-market-workbench__provenance is-fallback">
            <span>{english ? "Selected case detail · canonical fallback" : "선택 Case 상세 · canonical fallback"}</span>
            <span>{english ? "Plant aggregate unavailable in this runtime" : "이 runtime에서는 공장 집계 미지원"}</span>
          </div>
        ) : null}

        <div className="rw-market-workbench__chart">
          <BklitLiveRiskChart
            data={visibleSeries}
            value={currentRisk}
            threshold={riskIndex?.threshold ?? detail?.threshold ?? null}
            locale={english ? "en-US" : "ko-KR"}
            height={365}
            onHoverPoint={setHoveredPoint}
            emptyTitle={emptyTitle}
            emptyDetail={emptyDetail}
          />
        </div>
        <footer className="rw-market-workbench__chart-foot">
          <span><CircleDot size={11} /> Bklit UI · VisX</span>
          <span>{english ? `${visibleSeries.length} queried points` : `조회 ${visibleSeries.length}개`}</span>
          <span>{riskIndex ? `${riskIndex.window} · ${riskIndex.bucket_interval}` : usingDetailFallback ? (english ? "case detail fallback" : "Case 상세 fallback") : range}</span>
          <span>{selectedEvent?.eventId ?? (english ? "No case selected" : "Case 미선택")}</span>
        </footer>
      </div>

      <aside className="rw-market-workbench__index" aria-label={english ? "Risk index" : "위험 인덱스"}>
        <header>
          <div><Gauge size={14} /><strong>{english ? "Risk index" : "위험 인덱스"}</strong></div>
          <small>{english ? "Plant · live cases" : "공장 · 실시간 Case"}</small>
        </header>
        <div className="rw-market-workbench__index-summary">
          <span><ShieldAlert size={12} />{english ? "Critical" : "고위험"}<b>{model.metrics.critical}</b></span>
          <span><Activity size={12} />{english ? "Pending" : "판단 대기"}<b>{model.metrics.pendingDecisions}</b></span>
        </div>
        <div className="rw-market-workbench__signals">
          <AnimatePresence initial={false}>
            {rankedEvents.map((event) => {
              const active = event.eventId === selectedEvent?.eventId;
              return (
                <motion.button
                  type="button"
                  layout
                  key={event.eventId}
                  className={`rw-market-signal-row ${active ? "is-active" : ""}`}
                  onClick={() => onSelectEvent(event)}
                  whileHover={reducedMotion ? undefined : { x: 3 }}
                  whileTap={reducedMotion ? undefined : { scale: 0.985 }}
                >
                  <i className={`tone-${riskTone(event.status)}`} />
                  <div>
                    <strong>{english ? (event.assetName || event.assetId) : displayAssetName({ assetId: event.assetId, displayName: event.assetName })}</strong>
                    <small>{english ? event.line : displayLineLabel(event.line)} · {statusLabel(event.status, english)}</small>
                  </div>
                  <b>{percent(event.failureProbability)}</b>
                </motion.button>
              );
            })}
          </AnimatePresence>
        </div>
      </aside>
    </motion.section>
  );
}
