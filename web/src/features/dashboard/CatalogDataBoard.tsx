import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, LoaderCircle } from "lucide-react";
import { queryDashboardBoard } from "../../api";
import type { BoardCatalogDefinition, RenderSpec, SelectionFilter } from "./types";
import { DataTableRenderer, type DataTableColumn, type TableDatum } from "./renderers/DataTableRenderer";
import { EChartsRenderer, type ChartDatum } from "./renderers/EChartsRenderer";
import { MetricRenderer } from "./renderers/MetricRenderer";

interface CatalogDataBoardProps {
  boardId: string;
  dashboardId: string;
  workspaceId: string;
  definition: BoardCatalogDefinition;
  parameterState: Record<string, unknown>;
  selectionFilters: SelectionFilter[];
  onSelectionFilter: (filter: SelectionFilter) => void;
}

const CHART_KINDS = new Set(["bar", "line", "pie", "histogram"]);

function normalizedSpec(value: Record<string, unknown>, fallback: RenderSpec | null | undefined): RenderSpec {
  const source = { ...(fallback ?? {}), ...value } as Record<string, unknown>;
  const kind = typeof source.kind === "string" && ["metric", "bar", "line", "pie", "histogram", "table"].includes(source.kind)
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
  boardId,
  dashboardId,
  workspaceId,
  definition,
  parameterState,
  selectionFilters,
  onSelectionFilter,
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
      board_id: boardId,
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
  }, [boardId, dashboardId, definition.default_render_spec, parameterState, selectionFilters, workspaceId]);

  const columns = useMemo(() => dynamicColumns(rows), [rows]);
  if (loading && !rows.length) return <div className="od-non-ideal-state"><LoaderCircle className="spin" /><strong>Board query running</strong></div>;
  if (error) return <div className="od-non-ideal-state"><AlertTriangle /><strong>Board query failed</strong><span>{error}</span></div>;

  return (
    <section className="advanced-board generic-catalog-data-board">
      <header className="advanced-toolbar">
        <div><strong>{definition.display_name}</strong><small>{definition.description}</small></div>
        <div className="advanced-toolbar-actions"><span className="runtime-badge">{renderSpec.kind}</span><span className="runtime-badge">{freshnessAt ? `fresh ${new Date(freshnessAt).toLocaleTimeString()}` : "freshness unknown"}</span></div>
      </header>
      {CHART_KINDS.has(renderSpec.kind) ? (
        <EChartsRenderer boardId={boardId} rows={rows as ChartDatum[]} spec={renderSpec} ariaLabel={definition.display_name} onSelection={onSelectionFilter} />
      ) : renderSpec.kind === "metric" ? (
        <MetricRenderer metrics={rows.slice(0, 6).map((row, index) => ({ id: String(row.id ?? index), label: String(row.label ?? row.metric ?? `Metric ${index + 1}`), value: String(row.value ?? row.count ?? "-") }))} />
      ) : (
        <DataTableRenderer boardId={boardId} rows={rows as TableDatum[]} columns={columns} rowKey={columns[0]?.id ?? "id"} onRowSelect={(_, filter) => onSelectionFilter(filter)} />
      )}
      <footer className="data-grid-footer"><span>{rowCount} rows · server query</span><span>{generatedAt ? new Date(generatedAt).toLocaleString() : "not generated"}</span></footer>
    </section>
  );
}
