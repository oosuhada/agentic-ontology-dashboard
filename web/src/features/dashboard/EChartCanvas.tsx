import { lazy, Suspense } from "react";
import type { DashboardChartOption, EChartCanvasProps } from "./EChartRuntime";

export type { DashboardChartOption } from "./EChartRuntime";

const EChartCartesianCanvas = lazy(() =>
  import("./EChartCartesianCanvas").then((module) => ({ default: module.EChartCartesianCanvas })),
);
const EChartPieCanvas = lazy(() =>
  import("./EChartPieCanvas").then((module) => ({ default: module.EChartPieCanvas })),
);

function chartKind(option: DashboardChartOption): string {
  const series = option.series;
  if (!Array.isArray(series) || !series.length || typeof series[0] !== "object" || series[0] === null) return "cartesian";
  return String((series[0] as { type?: unknown }).type ?? "cartesian");
}

export function EChartCanvas(props: EChartCanvasProps) {
  const Component = chartKind(props.option) === "pie" ? EChartPieCanvas : EChartCartesianCanvas;
  return (
    <Suspense fallback={<div className={`echart-canvas ${props.className ?? ""}`} role="img" aria-label={`${props.ariaLabel} loading`} data-chart-state="loading" />}>
      <Component {...props} />
    </Suspense>
  );
}
