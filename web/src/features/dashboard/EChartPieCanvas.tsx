import { PieChart } from "echarts/charts";
import { LegendComponent, TooltipComponent } from "echarts/components";
import { getInstanceByDom, init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { EChartRuntime, type EChartCanvasProps } from "./EChartRuntime";

use([PieChart, TooltipComponent, LegendComponent, CanvasRenderer]);

export function EChartPieCanvas(props: EChartCanvasProps) {
  return (
    <EChartRuntime
      {...props}
      initChart={(host) => init(host, undefined, { renderer: "canvas" })}
      getChart={(host) => getInstanceByDom(host)}
    />
  );
}
