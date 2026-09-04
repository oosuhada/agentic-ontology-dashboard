import { BarChart, HeatmapChart, LineChart, ScatterChart } from "echarts/charts";
import {
  BrushComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  ToolboxComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { getInstanceByDom, init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { EChartRuntime, type EChartCanvasProps } from "./EChartRuntime";

use([
  BarChart,
  LineChart,
  ScatterChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  VisualMapComponent,
  DataZoomComponent,
  BrushComponent,
  ToolboxComponent,
  CanvasRenderer,
]);

export function EChartCartesianCanvas(props: EChartCanvasProps) {
  return (
    <EChartRuntime
      {...props}
      initChart={(host) => init(host, undefined, { renderer: "canvas" })}
      getChart={(host) => getInstanceByDom(host)}
    />
  );
}
