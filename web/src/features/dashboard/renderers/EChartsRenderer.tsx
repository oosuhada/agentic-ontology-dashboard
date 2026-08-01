import { useMemo } from "react";
import type { RenderSpec, SelectionFilter } from "../types";
import { EChartCanvas, type DashboardChartOption } from "../EChartCanvas";

export type ChartDatum = Record<string, string | number | boolean | null | undefined>;

interface EChartsRendererProps {
  boardId: string;
  rows: ChartDatum[];
  spec: RenderSpec;
  selectedValue?: string | number | boolean | null;
  ariaLabel: string;
  onSelection?: (filter: SelectionFilter) => void;
}

function numeric(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function aggregateRows(rows: ChartDatum[], spec: RenderSpec) {
  const xField = spec.x_field ?? spec.group_field ?? "label";
  const valueField = spec.y_field ?? spec.value_field ?? "value";
  const aggregation = spec.aggregation ?? "avg";
  const buckets = new Map<string, number[]>();
  for (const row of rows) {
    const key = String(row[xField] ?? "unknown");
    const values = buckets.get(key) ?? [];
    values.push(numeric(row[valueField]));
    buckets.set(key, values);
  }
  return Array.from(buckets.entries()).map(([label, values]) => {
    let value = values.length;
    if (aggregation === "sum") value = values.reduce((sum, item) => sum + item, 0);
    if (aggregation === "avg") value = values.length ? values.reduce((sum, item) => sum + item, 0) / values.length : 0;
    if (aggregation === "min") value = Math.min(...values);
    if (aggregation === "max") value = Math.max(...values);
    return { label, value };
  });
}

function brushIndexes(params: unknown): number[] {
  if (!params || typeof params !== "object") return [];
  const batch = (params as { batch?: unknown[] }).batch;
  if (!Array.isArray(batch) || !batch.length) return [];
  const selected = (batch[0] as { selected?: unknown[] }).selected;
  if (!Array.isArray(selected) || !selected.length) return [];
  const indexes = (selected[0] as { dataIndex?: unknown }).dataIndex;
  return Array.isArray(indexes) ? indexes.map(Number).filter(Number.isFinite) : [];
}

function histogram(rows: ChartDatum[], field: string) {
  const values = rows.map((row) => numeric(row[field])).filter(Number.isFinite);
  if (!values.length) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const bucketCount = Math.min(12, Math.max(4, Math.ceil(Math.sqrt(values.length))));
  const step = max === min ? 1 : (max - min) / bucketCount;
  return Array.from({ length: bucketCount }, (_, index) => {
    const lower = min + index * step;
    const upper = index === bucketCount - 1 ? max : lower + step;
    const count = values.filter((value) => value >= lower && (index === bucketCount - 1 ? value <= upper : value < upper)).length;
    return { label: `${lower.toFixed(1)}–${upper.toFixed(1)}`, value: count };
  });
}

export function EChartsRenderer({ boardId, rows, spec, selectedValue, ariaLabel, onSelection }: EChartsRendererProps) {
  const data = useMemo(
    () => spec.kind === "histogram"
      ? histogram(rows, spec.value_field ?? spec.y_field ?? "value")
      : aggregateRows(rows, spec),
    [rows, spec],
  );
  const option = useMemo<DashboardChartOption>(() => {
    const categories = data.map((item) => item.label);
    const values = data.map((item) => item.value);
    if (spec.kind === "pie") {
      return {
        backgroundColor: "transparent",
        tooltip: { trigger: "item" },
        legend: { type: "scroll", bottom: 0, textStyle: { color: "#738091", fontSize: 9 } },
        series: [{
          type: "pie",
          radius: ["42%", "70%"],
          center: ["50%", "44%"],
          data: data.map((item) => ({ name: item.label, value: item.value })),
          label: { color: "#738091", fontSize: 9 },
          itemStyle: { borderRadius: 4, borderWidth: 2, borderColor: "rgba(255,255,255,.75)" },
        }],
      };
    }
    return {
      backgroundColor: "transparent",
      grid: { top: 20, right: 16, bottom: spec.brushable ? 50 : 34, left: 44 },
      tooltip: { trigger: "axis", confine: true },
      dataZoom: spec.brushable ? [{ type: "inside" }, { type: "slider", height: 14, bottom: 3 }] : undefined,
      toolbox: spec.brushable ? { right: 8, top: 0, feature: { brush: { type: ["rect", "clear"] } } } : undefined,
      brush: spec.brushable ? { toolbox: ["rect", "clear"], xAxisIndex: "all", brushMode: "single", throttleType: "debounce", throttleDelay: 120 } : undefined,
      xAxis: { type: "category", data: categories, axisLabel: { color: "#738091", fontSize: 9 }, axisLine: { lineStyle: { color: "#c8d0da" } } },
      yAxis: { type: "value", axisLabel: { color: "#738091", fontSize: 9 }, splitLine: { lineStyle: { color: "#e5e9ef" } } },
      series: [{
        type: spec.kind === "line" ? "line" : "bar",
        smooth: spec.kind === "line",
        symbolSize: 7,
        barMaxWidth: 36,
        data: values.map((value, index) => ({
          value,
          itemStyle: {
            color: categories[index] === String(selectedValue ?? "") ? "#d9822b" : "#2d72d2",
            borderRadius: spec.kind === "line" ? 0 : [4, 4, 0, 0],
          },
        })),
        lineStyle: { width: 2.5, color: "#2d72d2" },
        areaStyle: spec.kind === "line" ? { color: "rgba(45,114,210,.12)" } : undefined,
      }],
    };
  }, [data, selectedValue, spec]);

  return (
    <EChartCanvas
      option={option}
      ariaLabel={ariaLabel}
      className="generic-echarts-renderer"
      onBrushSelected={(params) => {
        if (!spec.brushable || !onSelection) return;
        const indexes = brushIndexes(params);
        const values = indexes.map((index) => data[index]?.label).filter((value): value is string => Boolean(value));
        if (!values.length) return;
        onSelection({
          id: crypto.randomUUID(),
          source_board_id: boardId,
          field: spec.x_field ?? spec.group_field ?? "label",
          operator: "in",
          values,
          created_at: new Date().toISOString(),
        });
      }}
      onDataClick={(params) => {
        if (!spec.selectable || !onSelection) return;
        const index = Number(params.dataIndex ?? -1);
        const selected = data[index];
        if (!selected) return;
        onSelection({
          id: crypto.randomUUID(),
          source_board_id: boardId,
          field: spec.x_field ?? spec.group_field ?? "label",
          operator: "eq",
          values: [selected.label],
          created_at: new Date().toISOString(),
        });
      }}
    />
  );
}
