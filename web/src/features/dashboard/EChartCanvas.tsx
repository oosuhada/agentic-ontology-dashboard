import { useEffect, useRef } from "react";
import { BarChart, LineChart, PieChart, type BarSeriesOption, type LineSeriesOption, type PieSeriesOption } from "echarts/charts";
import {
  BrushComponent,
  DataZoomComponent,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  TitleComponent,
  ToolboxComponent,
  TooltipComponent,
  TransformComponent,
  type BrushComponentOption,
  type DataZoomComponentOption,
  type DatasetComponentOption,
  type GridComponentOption,
  type LegendComponentOption,
  type TitleComponentOption,
  type ToolboxComponentOption,
  type TooltipComponentOption,
} from "echarts/components";
import { getInstanceByDom, init, use, type ComposeOption } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";

use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  BrushComponent,
  ToolboxComponent,
  LegendComponent,
  TitleComponent,
  DatasetComponent,
  TransformComponent,
  CanvasRenderer,
]);

export type DashboardChartOption = ComposeOption<
  | BarSeriesOption
  | LineSeriesOption
  | PieSeriesOption
  | GridComponentOption
  | TooltipComponentOption
  | DataZoomComponentOption
  | BrushComponentOption
  | ToolboxComponentOption
  | LegendComponentOption
  | TitleComponentOption
  | DatasetComponentOption
>;

interface EChartCanvasProps {
  option: DashboardChartOption;
  className?: string;
  ariaLabel: string;
  onDataClick?: (params: { name?: string; dataIndex?: number; seriesName?: string; value?: unknown; data?: unknown }) => void;
  onBrushSelected?: (params: unknown) => void;
}

export function EChartCanvas({ option, className = "", ariaLabel, onDataClick, onBrushSelected }: EChartCanvasProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const clickRef = useRef(onDataClick);
  const brushRef = useRef(onBrushSelected);
  clickRef.current = onDataClick;
  brushRef.current = onBrushSelected;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const chart = init(host, undefined, { renderer: "canvas" });
    chart.setOption(option, { notMerge: true, lazyUpdate: false });
    const handleClick = (params: unknown) => clickRef.current?.(params as Parameters<NonNullable<typeof clickRef.current>>[0]);
    const handleBrush = (params: unknown) => brushRef.current?.(params);
    chart.on("click", handleClick);
    chart.on("brushSelected", handleBrush);
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(host);
    return () => {
      observer.disconnect();
      chart.off("click", handleClick);
      chart.off("brushSelected", handleBrush);
      chart.dispose();
    };
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    getInstanceByDom(host)?.setOption(option, { notMerge: true, lazyUpdate: true });
  }, [option]);

  return <div ref={hostRef} className={`echart-canvas ${className}`} role="img" aria-label={ariaLabel} />;
}
