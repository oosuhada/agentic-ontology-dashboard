import { BarChart, LineChart } from "echarts/charts";
import {
  BrushComponent,
  DataZoomComponent,
  GridComponent,
  ToolboxComponent,
  TooltipComponent,
} from "echarts/components";
import { getInstanceByDom, init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { EChartRuntime, type EChartCanvasProps } from "./EChartRuntime";

use([
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
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
