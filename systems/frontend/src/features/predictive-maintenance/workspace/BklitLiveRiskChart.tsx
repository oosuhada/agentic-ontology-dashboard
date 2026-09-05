// Registry-derived integration of Bklit UI's MIT-licensed live-line chart pattern.
// Source reference: https://ui.bklit.com/r/live-line-chart.json
// The project intentionally keeps this adapter self-contained instead of enabling
// shadcn/Tailwind globally, because Reliability Operations already owns a mature
// CSS token system. Core Bklit dependencies (VisX + Motion) remain intact.

import { curveMonotoneX } from "@visx/curve";
import { localPoint } from "@visx/event";
import { ParentSize } from "@visx/responsive";
import { scaleLinear, scaleTime } from "@visx/scale";
import { AreaClosed, LinePath } from "@visx/shape";
import { bisector } from "d3-array";
import { motion, useReducedMotion } from "motion/react";
import { useId, useMemo, useState } from "react";

export interface BklitLiveRiskPoint {
  time: number;
  value: number;
  status?: string | null;
}

interface BklitLiveRiskChartProps {
  data: BklitLiveRiskPoint[];
  value: number | null;
  threshold?: number | null;
  height?: number;
  locale?: "ko-KR" | "en-US";
  onHoverPoint?: (point: BklitLiveRiskPoint | null) => void;
}

const bisectTime = bisector<BklitLiveRiskPoint, number>((point) => point.time).left;

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function nearestPoint(data: BklitLiveRiskPoint[], targetTime: number) {
  if (!data.length) return null;
  const index = bisectTime(data, targetTime, 1);
  const previous = data[index - 1] ?? data[0];
  const next = data[index] ?? previous;
  return targetTime - previous.time > next.time - targetTime ? next : previous;
}

function timeLabel(value: number, locale: "ko-KR" | "en-US") {
  return new Date(value * 1000).toLocaleTimeString(locale, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function RiskChartInner({
  width,
  height,
  data,
  value,
  threshold,
  locale,
  onHoverPoint,
}: BklitLiveRiskChartProps & { width: number; height: number }) {
  const reducedMotion = useReducedMotion();
  const clipId = `bklit-risk-${useId().replace(/:/g, "")}`;
  const [hovered, setHovered] = useState<BklitLiveRiskPoint | null>(null);
  const margin = { top: 18, right: 60, bottom: 28, left: 16 };
  const innerWidth = Math.max(10, width - margin.left - margin.right);
  const innerHeight = Math.max(10, height - margin.top - margin.bottom);
  const extent = useMemo(() => {
    const values = data.map((point) => point.value).filter(Number.isFinite);
    if (typeof value === "number" && Number.isFinite(value)) values.push(value);
    if (typeof threshold === "number" && Number.isFinite(threshold)) values.push(threshold);
    if (!values.length) return [0, 1];
    const min = Math.min(...values);
    const max = Math.max(...values);
    const spread = Math.max(0.03, max - min);
    return [Math.max(0, min - spread * 0.16), Math.min(1, max + spread * 0.16)];
  }, [data, threshold, value]);
  const xDomain = useMemo(() => {
    const first = data.at(0)?.time ?? Date.now() / 1000 - 60;
    const last = data.at(-1)?.time ?? first + 60;
    return [new Date(first * 1000), new Date(Math.max(first + 1, last) * 1000)];
  }, [data]);
  const xScale = useMemo(
    () => scaleTime<number>({ domain: xDomain, range: [0, innerWidth] }),
    [innerWidth, xDomain],
  );
  const yScale = useMemo(
    () => scaleLinear<number>({ domain: extent, range: [innerHeight, 0], nice: true }),
    [extent, innerHeight],
  );
  const selected = hovered ?? data.at(-1) ?? null;
  const yTicks = yScale.ticks(5);
  const xTicks = xScale.ticks(Math.max(2, Math.min(6, Math.floor(innerWidth / 130))));

  function setHover(next: BklitLiveRiskPoint | null) {
    setHovered(next);
    onHoverPoint?.(next);
  }

  function onPointerMove(event: React.PointerEvent<SVGRectElement>) {
    if (!data.length) return;
    const point = localPoint(event);
    if (!point) return;
    const localX = clamp(point.x - margin.left, 0, innerWidth);
    const time = xScale.invert(localX).getTime() / 1000;
    setHover(nearestPoint(data, time));
  }

  if (!data.length) {
    return (
      <div className="rw-bklit-risk-chart__empty">
        <strong>{locale === "en-US" ? "No time-series risk data" : "시계열 위험 데이터 없음"}</strong>
        <span>{locale === "en-US" ? "The chart appears when historical risk points are connected." : "과거 위험 관측이 연결되면 그래프를 표시합니다."}</span>
      </div>
    );
  }

  return (
    <svg
      className="rw-bklit-risk-chart__svg"
      width={width}
      height={height}
      role="img"
      aria-label={locale === "en-US" ? "Failure risk time series" : "고장 위험 시계열"}
    >
      <defs>
        <linearGradient id={`${clipId}-area`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--rw-risk-chart-line)" stopOpacity="0.26" />
          <stop offset="100%" stopColor="var(--rw-risk-chart-line)" stopOpacity="0" />
        </linearGradient>
        <clipPath id={`${clipId}-reveal`}>
          <motion.rect
            x="0"
            y="0"
            height={innerHeight}
            initial={reducedMotion ? false : { width: 0 }}
            animate={{ width: innerWidth }}
            transition={{ duration: reducedMotion ? 0 : 0.8, ease: [0.22, 1, 0.36, 1] }}
          />
        </clipPath>
      </defs>
      <g transform={`translate(${margin.left} ${margin.top})`}>
        {yTicks.map((tick) => {
          const y = yScale(tick);
          return (
            <g key={`y-${tick}`}>
              <line className="rw-bklit-risk-chart__grid" x1={0} x2={innerWidth} y1={y} y2={y} />
              <text className="rw-bklit-risk-chart__axis is-y" x={innerWidth + 10} y={y + 4}>
                {Math.round(tick * 100)}%
              </text>
            </g>
          );
        })}
        {xTicks.map((tick) => {
          const x = xScale(tick);
          return (
            <text key={tick.toISOString()} className="rw-bklit-risk-chart__axis" x={x} y={innerHeight + 22} textAnchor="middle">
              {tick.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })}
            </text>
          );
        })}
        {typeof threshold === "number" ? (
          <g>
            <line className="rw-bklit-risk-chart__threshold" x1={0} x2={innerWidth} y1={yScale(threshold)} y2={yScale(threshold)} />
            <text className="rw-bklit-risk-chart__threshold-label" x={innerWidth - 4} y={yScale(threshold) - 7} textAnchor="end">
              {locale === "en-US" ? "Threshold" : "판단 기준"} {Math.round(threshold * 100)}%
            </text>
          </g>
        ) : null}
        <g clipPath={`url(#${clipId}-reveal)`}>
          <AreaClosed
            data={data}
            x={(point) => xScale(new Date(point.time * 1000))}
            y={(point) => yScale(point.value)}
            yScale={yScale}
            curve={curveMonotoneX}
            fill={`url(#${clipId}-area)`}
          />
          <LinePath
            data={data}
            x={(point) => xScale(new Date(point.time * 1000))}
            y={(point) => yScale(point.value)}
            curve={curveMonotoneX}
            stroke="var(--rw-risk-chart-line)"
            strokeWidth={2.4}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </g>
        {selected ? (
          <g className="rw-bklit-risk-chart__hover">
            <line
              x1={xScale(new Date(selected.time * 1000))}
              x2={xScale(new Date(selected.time * 1000))}
              y1={0}
              y2={innerHeight}
            />
            <motion.circle
              cx={xScale(new Date(selected.time * 1000))}
              cy={yScale(selected.value)}
              r={4.5}
              initial={false}
              animate={{ r: hovered ? 5.5 : 4.2 }}
              transition={{ type: "spring", stiffness: 420, damping: 28 }}
            />
            {hovered ? (
              <g transform={`translate(${clamp(xScale(new Date(selected.time * 1000)) - 58, 2, innerWidth - 120)} ${clamp(yScale(selected.value) - 55, 4, innerHeight - 52)})`}>
                <rect className="rw-bklit-risk-chart__tooltip-bg" width="116" height="43" rx="9" />
                <text className="rw-bklit-risk-chart__tooltip-time" x="10" y="17">{timeLabel(selected.time, locale ?? "ko-KR")}</text>
                <text className="rw-bklit-risk-chart__tooltip-value" x="10" y="34">{(selected.value * 100).toFixed(1)}%</text>
              </g>
            ) : null}
          </g>
        ) : null}
        <rect
          className="rw-bklit-risk-chart__hit"
          x={0}
          y={0}
          width={innerWidth}
          height={innerHeight}
          onPointerMove={onPointerMove}
          onPointerLeave={() => setHover(null)}
        />
      </g>
    </svg>
  );
}
export function BklitLiveRiskChart({ height = 350, locale = "ko-KR", ...props }: BklitLiveRiskChartProps) {
  return (
    <div
      className="rw-bklit-risk-chart"
      style={{ height }}
      data-chart-library="bklit-registry-derived"
      data-bklit-source="live-line-chart"
    >
      <ParentSize debounceTime={80}>
        {({ width, height: measuredHeight }) => (
          <RiskChartInner
            {...props}
            locale={locale}
            width={Math.max(1, width)}
            height={Math.max(220, measuredHeight || height)}
          />
        )}
      </ParentSize>
    </div>
  );
}
export default BklitLiveRiskChart;
