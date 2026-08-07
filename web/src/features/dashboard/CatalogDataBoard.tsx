import { useEffect, useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { queryDashboardBoard } from "../../api";
import { ChartPanel } from "../../ui/foundry/ChartPanel";
import type { BoardCatalogDefinition, BoardVisualizationRuntime, DashboardBoard, RenderSpec, SelectionFilter } from "./types";
import { DataTableRenderer, type DataTableColumn, type TableDatum } from "./renderers/DataTableRenderer";
import { EChartsRenderer, type ChartDatum } from "./renderers/EChartsRenderer";
import { MetricRenderer } from "./renderers/MetricRenderer";
import { recommendVisualization, resolveVisualizationSpec, visualizationSettings } from "./visualization/visualizationProfile";

interface CatalogDataBoardProps {
  board: DashboardBoard;
  dashboardId: string;
  workspaceId: string;
  definition: BoardCatalogDefinition;
  parameterState: Record<string, unknown>;
  selectionFilters: SelectionFilter[];
  onSelectionFilter: (filter: SelectionFilter) => void;
  onVisualizationRuntime?: (boardId: string, runtime: BoardVisualizationRuntime) => void;
}

const CHART_KINDS = new Set(["bar", "stacked_bar", "line", "area", "pie", "histogram", "scatter", "heatmap"]);

function normalizedSpec(value: Record<string, unknown>, fallback: RenderSpec | null | undefined): RenderSpec {
  const source = { ...(fallback ?? {}), ...value } as Record<string, unknown>;
  const kind = typeof source.kind === "string" && ["metric", "table", "bar", "stacked_bar", "line", "area", "pie", "histogram", "scatter", "heatmap"].includes(source.kind)
    ? source.kind as RenderSpec["kind"]
    : "table";
  return {
    kind,
    title: typeof source.title === "string" ? source.title : undefined,
    x_field: typeof source.x_field === "string" ? source.x_field : undefined,
    y_field: typeof source.y_field === "string" ? source.y_field : undefined,
    value_field: typeof source.value_field === "string" ? source.value_field : undefined,
    group_field: typeof source.group_field === "string" ? source.group_field : undefined,
    aggregation: ["count", "sum", "avg", "min", "max"].includes(String(source.aggregation))
      ? source.aggregation as RenderSpec["aggregation"]
      : undefined,
    selectable: Boolean(source.selectable),
    brushable: Boolean(source.brushable),
    page_size: typeof source.page_size === "number" ? source.page_size : undefined,
    orientation: source.orientation === "horizontal" ? "horizontal" : "vertical",
    stack: ["off", "normal", "percent"].includes(String(source.stack)) ? source.stack as RenderSpec["stack"] : undefined,
    legend: ["auto", "show", "hide"].includes(String(source.legend)) ? source.legend as RenderSpec["legend"] : undefined,
    labels: ["auto", "show", "hide"].includes(String(source.labels)) ? source.labels as RenderSpec["labels"] : undefined,
    curve: ["straight", "smooth", "step"].includes(String(source.curve)) ? source.curve as RenderSpec["curve"] : undefined,
    color_strategy: ["categorical", "semantic", "single_accent"].includes(String(source.color_strategy)) ? source.color_strategy as RenderSpec["color_strategy"] : undefined,
    pie_style: source.pie_style === "pie" ? "pie" : "donut",
  };
}

function dynamicColumns(rows: Array<Record<string, unknown>>): DataTableColumn[] {
  return Array.from(new Set(rows.slice(0, 20).flatMap((row) => Object.keys(row)))).slice(0, 14).map((id) => ({
    id,
    label: id.replaceAll("_", " "),
    format: id.includes("id") ? "code" : id.includes("status") ? "status" : "text",
    size: id.includes("id") ? 160 : 120,
  }));
}

export function CatalogDataBoard({
  board,
  dashboardId,
  workspaceId,
  definition,
  parameterState,
  selectionFilters,
  onSelectionFilter,
  onVisualizationRuntime,
}: CatalogDataBoardProps) {
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  const [rowCount, setRowCount] = useState(0);
  const [renderSpec, setRenderSpec] = useState<RenderSpec>(() => normalizedSpec({}, definition.default_render_spec));
  const [generatedAt, setGeneratedAt] = useState("");
  const [freshnessAt, setFreshnessAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    queryDashboardBoard({
      dashboard_id: dashboardId,
      board_id: board.id,
      workspace_id: workspaceId,
      parameter_state: parameterState,
      selection_filters: selectionFilters,
      limit: 500,
    })
      .then((payload) => {
        if (!active) return;
        setRows(payload.rows);
        setRowCount(payload.row_count);
        setRenderSpec(normalizedSpec(payload.render_spec, definition.default_render_spec));
        setGeneratedAt(payload.generated_at);
        setFreshnessAt(payload.source_freshness_at);
      })
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [board.id, dashboardId, definition.default_render_spec, parameterState, selectionFilters, workspaceId]);

  const columns = useMemo(() => dynamicColumns(rows), [rows]);
  const recommendation = useMemo(() => recommendVisualization(rows, renderSpec), [renderSpec, rows]);
  const settings = useMemo(() => visualizationSettings(board.settings.visualization), [board.settings.visualization]);
  const resolvedSpec = useMemo(() => resolveVisualizationSpec(renderSpec, recommendation, settings), [recommendation, renderSpec, settings]);
  useEffect(() => {
    onVisualizationRuntime?.(board.id, {
      recommendation,
      active_kind: resolvedSpec.kind as BoardVisualizationRuntime["active_kind"],
      mode: settings.mode,
    });
  }, [board.id, onVisualizationRuntime, recommendation, resolvedSpec.kind, settings.mode]);
  if (loading && !rows.length) return <ChartPanel state="loading" stateTitle="Board query running" stateDetail="Server rows와 visualization profile을 불러오고 있습니다."><span /></ChartPanel>;
  if (error) return <div className="od-non-ideal-state"><AlertTriangle /><strong>Board query failed</strong><span>{error}</span></div>;

  return (
    <section className="advanced-board generic-catalog-data-board">
      <header className="advanced-toolbar">
        <div><strong>{definition.display_name}</strong><small>{definition.description}</small></div>
        <div className="advanced-toolbar-actions"><span className="runtime-badge">{settings.mode} · {resolvedSpec.kind}</span><span className="runtime-badge">{freshnessAt ? `fresh ${new Date(freshnessAt).toLocaleTimeString()}` : "freshness unknown"}</span></div>
      </header>
      {CHART_KINDS.has(resolvedSpec.kind) ? (
        <EChartsRenderer boardId={board.id} rows={rows as ChartDatum[]} spec={resolvedSpec} ariaLabel={definition.display_name} onSelection={onSelectionFilter} />
      ) : resolvedSpec.kind === "metric" ? (
        <MetricRenderer metrics={rows.slice(0, 6).map((row, index) => ({ id: String(row.id ?? index), label: String(row.label ?? row.metric ?? `Metric ${index + 1}`), value: String(row.value ?? row.count ?? "-") }))} />
      ) : (
        <DataTableRenderer boardId={board.id} rows={rows as TableDatum[]} columns={columns} rowKey={columns[0]?.id ?? "id"} onRowSelect={(_, filter) => onSelectionFilter(filter)} />
      )}
      <footer className="data-grid-footer"><span>{rowCount} rows · server query</span><span>{generatedAt ? new Date(generatedAt).toLocaleString() : "not generated"}</span></footer>
    </section>
  );
}
