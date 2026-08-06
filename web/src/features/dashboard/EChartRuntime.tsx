import { useEffect, useRef } from "react";
import type { EChartsType } from "echarts/core";
import { observeElementSize } from "../../ui/foundry/resizeObserver";

export type DashboardChartOption = Record<string, unknown>;

export interface EChartCanvasProps {
  option: DashboardChartOption;
  className?: string;
  ariaLabel: string;
  onDataClick?: (params: { name?: string; dataIndex?: number; seriesName?: string; value?: unknown; data?: unknown }) => void;
  onBrushSelected?: (params: unknown) => void;
}

interface EChartRuntimeProps extends EChartCanvasProps {
  initChart: (host: HTMLDivElement) => EChartsType;
  getChart: (host: HTMLDivElement) => EChartsType | undefined;
}

export function EChartRuntime({
  option,
  className = "",
  ariaLabel,
  onDataClick,
  onBrushSelected,
  initChart,
  getChart,
}: EChartRuntimeProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const clickRef = useRef(onDataClick);
  const brushRef = useRef(onBrushSelected);
  clickRef.current = onDataClick;
  brushRef.current = onBrushSelected;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const chart = initChart(host);
    chart.setOption(option, { notMerge: true, lazyUpdate: false });
    const handleClick = (params: unknown) => clickRef.current?.(params as Parameters<NonNullable<typeof clickRef.current>>[0]);
    const handleBrush = (params: unknown) => brushRef.current?.(params);
    chart.on("click", handleClick);
    chart.on("brushSelected", handleBrush);
    const stopObserving = observeElementSize(host, () => chart.resize());
    return () => {
      stopObserving();
      chart.off("click", handleClick);
      chart.off("brushSelected", handleBrush);
      chart.dispose();
    };
  }, [getChart, initChart]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    getChart(host)?.setOption(option, { notMerge: true, lazyUpdate: true });
  }, [getChart, option]);

  return <div ref={hostRef} className={`echart-canvas ${className}`} role="img" aria-label={ariaLabel} />;
}
