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
import type {
  OperationsBootstrapModel,
  OperationsEvent,
  OperationsEventDetailModel,
} from "../../operations/api/operationsContracts";
import { displayAssetName, displayLineLabel } from "../../operations/displayLabels";
import { BklitLiveRiskChart, type BklitLiveRiskPoint } from "./BklitLiveRiskChart";
import "./immersive-risk-workbench.css";

type RangeId = "1h" | "6h" | "24h" | "all";

interface ImmersiveRiskWorkbenchProps {
  model: OperationsBootstrapModel;
  detail: OperationsEventDetailModel | null;
  selectedEvent: OperationsEvent | null;
  onSelectEvent: (event: OperationsEvent) => void;
  english: boolean;
}

const RANGE_SECONDS: Record<Exclude<RangeId, "all">, number> = {
  "1h": 60 * 60,
  "6h": 6 * 60 * 60,
  "24h": 24 * 60 * 60,
};

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

export function ImmersiveRiskWorkbench({
  model,
  detail,
  selectedEvent,
  onSelectEvent,
  english,
}: ImmersiveRiskWorkbenchProps) {
  const rootRef = useRef<HTMLElement>(null);
  const animationScopeRef = useRef<ReturnType<typeof createScope> | null>(null);
  const reducedMotion = useReducedMotion();
  const [range, setRange] = useState<RangeId>("24h");
  const [hoveredPoint, setHoveredPoint] = useState<BklitLiveRiskPoint | null>(null);
  const fullSeries = useMemo<BklitLiveRiskPoint[]>(() => (
    (detail?.riskSeries ?? [])
      .map((point) => ({
        time: Date.parse(point.observedAt) / 1000,
        value: point.failureProbability,
        status: point.status,
      }))
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value))
      .sort((left, right) => left.time - right.time)
  ), [detail?.riskSeries]);
  const visibleSeries = useMemo(() => {
    if (range === "all" || !fullSeries.length) return fullSeries;
    const end = fullSeries.at(-1)?.time ?? 0;
    const start = end - RANGE_SECONDS[range];
    const filtered = fullSeries.filter((point) => point.time >= start);
    return filtered.length >= 2 ? filtered : fullSeries;
  }, [fullSeries, range]);
  const currentRisk = hoveredPoint?.value
    ?? selectedEvent?.failureProbability
    ?? visibleSeries.at(-1)?.value
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
    : (english ? "Plant risk index" : "공장 위험 지수");

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
            <small>{hoveredPoint ? (english ? "Hovered observation" : "선택 관측") : (english ? "Latest observation" : "최신 관측")} · {timeLabel(currentTime, english)}</small>
          </div>
          <div className="rw-market-workbench__metrics">
            <article className="rw-market-workbench__metric"><span>{english ? "Start" : "시작"}</span><strong>{percent(firstRisk)}</strong></article>
            <article className="rw-market-workbench__metric"><span>{english ? "Low" : "최저"}</span><strong>{percent(min)}</strong></article>
            <article className="rw-market-workbench__metric"><span>{english ? "High" : "최고"}</span><strong>{percent(max)}</strong></article>
            <article className="rw-market-workbench__metric"><span>{english ? "Threshold" : "판단 기준"}</span><strong>{percent(detail?.threshold)}</strong></article>
          </div>
        </header>

        <div className="rw-market-workbench__range" role="group" aria-label={english ? "Risk history range" : "위험 이력 범위"}>
          {(["1h", "6h", "24h", "all"] as const).map((item) => (
            <motion.button
              type="button"
              key={item}
              className={range === item ? "is-active" : ""}
              onClick={() => setRange(item)}
              whileTap={reducedMotion ? undefined : { scale: 0.96 }}
            >
              {range === item ? <motion.span className="rw-market-workbench__range-indicator" layoutId="rw-risk-range" /> : null}
              <b>{item === "all" ? (english ? "ALL" : "전체") : item.toUpperCase()}</b>
            </motion.button>
          ))}
          <span className="rw-market-workbench__live"><i className="rw-market-live-pulse" />{english ? "Observed data" : "관측 데이터"}</span>
        </div>

        <div className="rw-market-workbench__chart">
          <BklitLiveRiskChart
            data={visibleSeries}
            value={selectedEvent?.failureProbability ?? null}
            threshold={detail?.threshold ?? null}
            locale={english ? "en-US" : "ko-KR"}
            height={365}
            onHoverPoint={setHoveredPoint}
          />
        </div>
        <footer className="rw-market-workbench__chart-foot">
          <span><CircleDot size={11} /> Bklit UI · VisX</span>
          <span>{english ? `${visibleSeries.length} observed points` : `관측 ${visibleSeries.length}개`}</span>
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
