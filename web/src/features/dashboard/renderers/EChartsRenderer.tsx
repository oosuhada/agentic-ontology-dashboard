import { useMemo } from "react";
import { ChartPanel } from "../../../ui/foundry/ChartPanel";
import { categoryColor, CHART_NEUTRAL, CHART_SEMANTIC, CHART_SERIES, withAlpha } from "../../../ui/foundry/chartPalette";
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

interface AggregatedDatum {
  label: string;
  value: number;
  series: string;
}

function numeric(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function hasField(rows: ChartDatum[], field: string | undefined) {
  if (!field) return false;
  return rows.some((row) => Object.prototype.hasOwnProperty.call(row, field) && row[field] !== null && row[field] !== undefined);
}

function hasNumericField(rows: ChartDatum[], field: string | undefined) {
  if (!field) return false;
  return rows.some((row) => row[field] !== null && row[field] !== undefined && Number.isFinite(Number(row[field])));
}

function compatibilityIssue(rows: ChartDatum[], spec: RenderSpec): string | null {
  if (!rows.length) return null;
  if (spec.kind === "histogram") {
    const valueField = spec.value_field ?? spec.y_field;
    return hasNumericField(rows, valueField) ? null : `Histogram에는 numeric value field가 필요합니다${valueField ? `: ${valueField}` : "."}`;
  }
  if (spec.kind === "scatter") {
    const missing = [spec.x_field, spec.y_field ?? spec.value_field].filter((field) => !hasNumericField(rows, field));
    return missing.length ? "Scatter에는 두 개의 numeric field가 필요합니다. Inspector에서 X와 Y mapping을 확인하세요." : null;
  }
  if (spec.kind === "heatmap") {
    const xField = spec.x_field;
    const rowField = spec.group_field;
    const valueField = spec.value_field ?? spec.y_field;
    if (!hasField(rows, xField) || !hasField(rows, rowField) || !hasNumericField(rows, valueField)) {
      return "Heatmap에는 column, row, numeric value field가 모두 필요합니다.";
    }
    return null;
  }
  const xField = spec.x_field ?? spec.group_field;
  const valueField = spec.y_field ?? spec.value_field;
  if (!hasField(rows, xField)) return `Category 또는 time field를 찾을 수 없습니다${xField ? `: ${xField}` : "."}`;
  if (!hasNumericField(rows, valueField) && spec.aggregation !== "count") return `Numeric value field를 찾을 수 없습니다${valueField ? `: ${valueField}` : "."}`;
  if (spec.kind === "stacked_bar" && !hasField(rows, spec.group_field)) return "Stacked bar에는 series field가 필요합니다.";
  return null;
}

function aggregate(values: number[], aggregation: RenderSpec["aggregation"]) {
  if (aggregation === "count") return values.length;
  if (aggregation === "sum") return values.reduce((sum, item) => sum + item, 0);
  if (aggregation === "min") return Math.min(...values);
  if (aggregation === "max") return Math.max(...values);
  return values.length ? values.reduce((sum, item) => sum + item, 0) / values.length : 0;
}

function aggregateRows(rows: ChartDatum[], spec: RenderSpec): AggregatedDatum[] {
  const xField = spec.x_field ?? "label";
  const valueField = spec.y_field ?? spec.value_field ?? "value";
  const groupField = spec.group_field;
  const buckets = new Map<string, { label: string; series: string; values: number[] }>();
  for (const row of rows) {
    const label = String(row[xField] ?? "unknown");
    const series = groupField ? String(row[groupField] ?? "Other") : "Value";
    const bucketKey = `${label}\u0000${series}`;
    const bucket = buckets.get(bucketKey) ?? { label, series, values: [] };
    bucket.values.push(numeric(row[valueField]));
    buckets.set(bucketKey, bucket);
  }
  return Array.from(buckets.values()).map((bucket) => ({
    label: bucket.label,
    series: bucket.series,
    value: aggregate(bucket.values, spec.aggregation ?? "avg"),
  }));
}

function histogram(rows: ChartDatum[], field: string): AggregatedDatum[] {
  const values = rows.map((row) => Number(row[field])).filter(Number.isFinite);
  if (!values.length) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const bucketCount = Math.min(12, Math.max(4, Math.ceil(Math.sqrt(values.length))));
  const step = max === min ? 1 : (max - min) / bucketCount;
  return Array.from({ length: bucketCount }, (_, index) => {
    const lower = min + index * step;
    const upper = index === bucketCount - 1 ? max : lower + step;
    const count = values.filter((value) => value >= lower && (index === bucketCount - 1 ? value <= upper : value < upper)).length;
    return { label: `${lower.toFixed(1)}–${upper.toFixed(1)}`, value: count, series: "Frequency" };
  });
}

function brushIndexes(params: unknown): number[] {
  if (!params || typeof params !== "object") return [];
  const batch = (params as { batch?: unknown[] }).batch;
  if (!Array.isArray(batch) || !batch.length) return [];
  const selected = (batch[0] as { selected?: unknown[] }).selected;
  if (!Array.isArray(selected)) return [];
  return selected.flatMap((item) => {
    const indexes = (item as { dataIndex?: unknown }).dataIndex;
    return Array.isArray(indexes) ? indexes.map(Number).filter(Number.isFinite) : [];
  });
}

function cartesianOption(data: AggregatedDatum[], spec: RenderSpec, selectedValue: EChartsRendererProps["selectedValue"]): DashboardChartOption {
  const categories = Array.from(new Set(data.map((item) => item.label)));
  const seriesNames = Array.from(new Set(data.map((item) => item.series)));
  const horizontal = spec.orientation === "horizontal";
  const isLine = spec.kind === "line" || spec.kind === "area";
  const isArea = spec.kind === "area";
  const stacked = spec.kind === "stacked_bar" || spec.stack === "normal" || spec.stack === "percent";
  const series = seriesNames.map((seriesName, seriesIndex) => {
    const color = seriesNames.length > 1 ? categoryColor(seriesName) : CHART_SERIES[0];
    const byCategory = new Map(data.filter((item) => item.series === seriesName).map((item) => [item.label, item.value]));
    return {
      name: seriesName,
      type: isLine ? "line" : "bar",
      stack: stacked ? "total" : undefined,
      smooth: spec.curve === "smooth" || (spec.curve === undefined && isLine),
      step: spec.curve === "step" ? "middle" : undefined,
      symbolSize: 7,
      barMaxWidth: 36,
      emphasis: { focus: "series" },
      itemStyle: { color, borderRadius: isLine || horizontal ? 0 : [3, 3, 0, 0] },
      lineStyle: { width: 2.25, color },
      areaStyle: isArea ? { color: withAlpha(color, seriesIndex === 0 ? .22 : .14) } : undefined,
      label: { show: spec.labels === "show", color: CHART_NEUTRAL.muted, fontSize: 11 },
      data: categories.map((category) => ({
        value: byCategory.get(category) ?? 0,
        itemStyle: category === String(selectedValue ?? "")
          ? { color: CHART_SEMANTIC.accent, borderColor: CHART_NEUTRAL.ink, borderWidth: 2 }
          : undefined,
      })),
    };
  });
  const categoryAxis = { type: "category", data: categories, axisLabel: { color: CHART_NEUTRAL.muted, fontSize: 11 }, axisLine: { lineStyle: { color: CHART_NEUTRAL.border } } };
  const valueAxis = { type: "value", axisLabel: { color: CHART_NEUTRAL.muted, fontSize: 11 }, splitLine: { lineStyle: { color: withAlpha(CHART_NEUTRAL.border, .75) } } };
  return {
    color: CHART_SERIES,
    backgroundColor: "transparent",
    grid: { top: seriesNames.length > 1 ? 34 : 18, right: 16, bottom: spec.brushable ? 50 : 34, left: 48, containLabel: true },
    tooltip: { trigger: "axis", confine: true },
    legend: { show: spec.legend !== "hide" && seriesNames.length > 1, top: 0, textStyle: { color: CHART_NEUTRAL.muted, fontSize: 11 } },
    dataZoom: spec.brushable ? [{ type: "inside" }, { type: "slider", height: 14, bottom: 3 }] : undefined,
    toolbox: spec.brushable ? { right: 8, top: 0, feature: { brush: { type: ["rect", "clear"] } } } : undefined,
    brush: spec.brushable ? { toolbox: ["rect", "clear"], xAxisIndex: "all", brushMode: "single", throttleType: "debounce", throttleDelay: 120 } : undefined,
    xAxis: horizontal ? valueAxis : categoryAxis,
    yAxis: horizontal ? categoryAxis : valueAxis,
    series,
  };
}

function scatterOption(rows: ChartDatum[], spec: RenderSpec): DashboardChartOption {
  const xField = spec.x_field ?? "x";
  const yField = spec.y_field ?? spec.value_field ?? "y";
  const groupField = spec.group_field;
  const groups = Array.from(new Set(rows.map((row) => groupField ? String(row[groupField] ?? "Other") : "Value")));
  return {
    color: CHART_SERIES,
    backgroundColor: "transparent",
    grid: { top: groups.length > 1 ? 34 : 18, right: 18, bottom: spec.brushable ? 46 : 32, left: 48, containLabel: true },
    tooltip: { trigger: "item", confine: true },
    legend: { show: spec.legend !== "hide" && groups.length > 1, top: 0, textStyle: { color: CHART_NEUTRAL.muted, fontSize: 11 } },
    brush: spec.brushable ? { toolbox: ["rect", "clear"], brushMode: "single" } : undefined,
    xAxis: { type: "value", name: xField, nameTextStyle: { color: CHART_NEUTRAL.muted }, axisLabel: { color: CHART_NEUTRAL.muted }, splitLine: { lineStyle: { color: CHART_NEUTRAL.border } } },
    yAxis: { type: "value", name: yField, nameTextStyle: { color: CHART_NEUTRAL.muted }, axisLabel: { color: CHART_NEUTRAL.muted }, splitLine: { lineStyle: { color: CHART_NEUTRAL.border } } },
    series: groups.map((group) => ({
      name: group,
      type: "scatter",
      symbolSize: 9,
      itemStyle: { color: categoryColor(group), opacity: .82 },
      data: rows.filter((row) => !groupField || String(row[groupField] ?? "Other") === group).map((row) => [numeric(row[xField]), numeric(row[yField])]),
    })),
  };
}

function heatmapOption(rows: ChartDatum[], spec: RenderSpec): DashboardChartOption {
  const columnField = spec.x_field ?? "column";
  const rowField = spec.group_field ?? "row";
  const valueField = spec.value_field ?? spec.y_field ?? "value";
  const columns = Array.from(new Set(rows.map((row) => String(row[columnField] ?? "unknown"))));
  const rowLabels = Array.from(new Set(rows.map((row) => String(row[rowField] ?? "unknown"))));
  const values = rows.map((row) => [columns.indexOf(String(row[columnField] ?? "unknown")), rowLabels.indexOf(String(row[rowField] ?? "unknown")), numeric(row[valueField])]);
  const max = Math.max(1, ...values.map((item) => Number(item[2])));
  return {
    backgroundColor: "transparent",
    grid: { top: 16, right: 22, bottom: 42, left: 62, containLabel: true },
    tooltip: { position: "top" },
    xAxis: { type: "category", data: columns, splitArea: { show: true }, axisLabel: { color: CHART_NEUTRAL.muted, fontSize: 11 } },
    yAxis: { type: "category", data: rowLabels, splitArea: { show: true }, axisLabel: { color: CHART_NEUTRAL.muted, fontSize: 11 } },
    visualMap: { min: 0, max, calculable: true, orient: "horizontal", left: "center", bottom: 0, inRange: { color: [withAlpha(CHART_SERIES[0], .08), CHART_SERIES[0]] }, textStyle: { color: CHART_NEUTRAL.muted, fontSize: 11 } },
    series: [{ type: "heatmap", data: values, label: { show: spec.labels === "show", color: CHART_NEUTRAL.ink, fontSize: 11 }, itemStyle: { borderColor: CHART_NEUTRAL.white, borderWidth: 1 }, emphasis: { itemStyle: { borderColor: CHART_SEMANTIC.accent, borderWidth: 2 } } }],
  };
}

export function EChartsRenderer({ boardId, rows, spec, selectedValue, ariaLabel, onSelection }: EChartsRendererProps) {
  const issue = useMemo(() => compatibilityIssue(rows, spec), [rows, spec]);
  const data = useMemo(
    () => spec.kind === "histogram" ? histogram(rows, spec.value_field ?? spec.y_field ?? "value") : aggregateRows(rows, spec),
    [rows, spec],
  );
  const interactionValues = useMemo(() => {
    if (spec.kind === "scatter") return rows.map((row) => String(row[spec.x_field ?? "x"] ?? ""));
    if (spec.kind === "heatmap") return rows.map((row) => String(row[spec.x_field ?? "column"] ?? ""));
    return Array.from(new Set(data.map((item) => item.label)));
  }, [data, rows, spec]);
  const option = useMemo<DashboardChartOption>(() => {
    if (spec.kind === "pie") {
      return {
        color: data.map((item) => categoryColor(item.label)),
        backgroundColor: "transparent",
        tooltip: { trigger: "item" },
        legend: { show: spec.legend !== "hide", type: "scroll", bottom: 0, textStyle: { color: CHART_NEUTRAL.muted, fontSize: 11 } },
        series: [{
          type: "pie",
          radius: spec.pie_style === "pie" ? "70%" : ["42%", "70%"],
          center: ["50%", "44%"],
          data: data.map((item) => ({ name: item.label, value: item.value, itemStyle: { color: categoryColor(item.label) } })),
          label: { show: spec.labels !== "hide", color: CHART_NEUTRAL.muted, fontSize: 11 },
          itemStyle: { borderRadius: 3, borderWidth: 2, borderColor: CHART_NEUTRAL.white },
          emphasis: { scaleSize: 7, itemStyle: { borderColor: CHART_SEMANTIC.accent, borderWidth: 2 } },
        }],
      };
    }
    if (spec.kind === "scatter") return scatterOption(rows, spec);
    if (spec.kind === "heatmap") return heatmapOption(rows, spec);
    return cartesianOption(data, spec, selectedValue);
  }, [data, rows, selectedValue, spec]);

  return (
    <ChartPanel
      className="generic-chart-panel"
      state={!rows.length ? "empty" : issue ? "incompatible" : "ready"}
      stateTitle={!rows.length ? "No rows in current scope" : issue ? "Chart mapping unavailable" : undefined}
      stateDetail={!rows.length ? "현재 filter와 cross-filter 조건에 일치하는 query row가 없습니다." : issue ?? undefined}
    >
      <EChartCanvas
        option={option}
        ariaLabel={ariaLabel}
        className="generic-echarts-renderer"
        onBrushSelected={(params) => {
          if (!spec.brushable || !onSelection) return;
          const values = brushIndexes(params).map((index) => interactionValues[index]).filter(Boolean);
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
          const value = params.name ?? interactionValues[index];
          if (value === undefined || value === "") return;
          onSelection({
            id: crypto.randomUUID(),
            source_board_id: boardId,
            field: spec.x_field ?? spec.group_field ?? "label",
            operator: "eq",
            values: [String(value)],
            created_at: new Date().toISOString(),
          });
        }}
      />
    </ChartPanel>
  );
}
