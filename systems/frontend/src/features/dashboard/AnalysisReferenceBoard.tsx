import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ExternalLink } from "lucide-react";
import { getAnalysisNodeResult } from "../../api";
import { navigate } from "../../routing";
import { ChartPanel } from "../../ui/foundry/ChartPanel";
import type { AnalysisNodeResultResponse } from "../analysis/types";
import type { BoardVisualizationRuntime, DashboardBoard, RenderSpec, SelectionFilter } from "./types";
import { DataTableRenderer, type DataTableColumn, type TableDatum } from "./renderers/DataTableRenderer";
import { EChartsRenderer, type ChartDatum } from "./renderers/EChartsRenderer";
import { MetricRenderer } from "./renderers/MetricRenderer";
import { recommendVisualization, resolveVisualizationSpec, visualizationSettings } from "./visualization/visualizationProfile";

interface AnalysisReferenceBoardProps {
  board: DashboardBoard;
  workspaceId: string;
  onSelectionFilter?: (filter: SelectionFilter) => void;
  onVisualizationRuntime?: (boardId: string, runtime: BoardVisualizationRuntime) => void;
}

const CHART_KINDS = new Set(["bar", "stacked_bar", "line", "area", "pie", "histogram", "scatter", "heatmap"]);

function normalizeRenderSpec(value: Record<string, unknown>): RenderSpec {
  const kind = typeof value.kind === "string" && ["metric", "table", "bar", "stacked_bar", "line", "area", "pie", "histogram", "scatter", "heatmap"].includes(value.kind)
    ? value.kind as RenderSpec["kind"]
    : "table";
  return {
    kind,
    title: typeof value.title === "string" ? value.title : undefined,
    x_field: typeof value.x_field === "string" ? value.x_field : undefined,
    y_field: typeof value.y_field === "string" ? value.y_field : undefined,
    value_field: typeof value.value_field === "string" ? value.value_field : undefined,
    group_field: typeof value.group_field === "string" ? value.group_field : undefined,
    aggregation: ["count", "sum", "avg", "min", "max"].includes(String(value.aggregation))
      ? value.aggregation as RenderSpec["aggregation"]
      : undefined,
    selectable: Boolean(value.selectable),
    brushable: Boolean(value.brushable),
    page_size: typeof value.page_size === "number" ? value.page_size : undefined,
  };
}

function columnsFor(rows: Array<Record<string, unknown>>): DataTableColumn[] {
  const keys = Array.from(new Set(rows.slice(0, 20).flatMap((row) => Object.keys(row))));
  return keys.slice(0, 16).map((key) => ({
    id: key,
    label: key.replaceAll("_", " "),
    size: key.includes("id") ? 160 : 120,
    format: key.includes("id") ? "code" : key.includes("status") ? "status" : "text",
  }));
}

function freshnessLabel(generatedAt: string, freshnessAt: string | null) {
  const source = freshnessAt ?? generatedAt;
  const timestamp = Date.parse(source);
  if (!Number.isFinite(timestamp)) return source;
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60_000));
  if (minutes < 1) return "fresh now";
  if (minutes < 60) return `${minutes}m old`;
  const hours = Math.floor(minutes / 60);
  return hours < 24 ? `${hours}h old` : `${Math.floor(hours / 24)}d old`;
}

export function AnalysisReferenceBoard({
  board,
  workspaceId,
  onSelectionFilter,
  onVisualizationRuntime,
}: AnalysisReferenceBoardProps) {
  const source = board.source;
  const [payload, setPayload] = useState<AnalysisNodeResultResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    if (!source) {
      setPayload(null);
      setError("Analysis source reference가 설정되지 않았습니다.");
      return () => { active = false; };
    }
    setLoading(true);
    setError("");
    getAnalysisNodeResult({
      analysis_id: source.analysis_id,
      node_id: source.analysis_node_id,
      workspace_id: workspaceId,
      version_policy: source.version_policy,
      version: source.version,
    })
      .then((result) => active && setPayload(result))
      .catch((reason: unknown) => active && setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [source, workspaceId]);

  const rows = payload?.result.rows ?? [];
  const renderSpec = useMemo(() => normalizeRenderSpec(payload?.render_spec ?? {}), [payload]);
  const columns = useMemo(() => columnsFor(rows), [rows]);
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

  if (!source) return <div className="od-non-ideal-state"><strong>Analysis reference missing</strong></div>;
  if (loading && !payload) return <ChartPanel state="loading" stateTitle="Analysis result loading" stateDetail="Published node result와 visualization profile을 불러오고 있습니다."><span /></ChartPanel>;
  if (error) return <div className="od-non-ideal-state"><AlertTriangle /><strong>Analysis result unavailable</strong><span>{error}</span></div>;
  if (!payload) return null;

  return (
    <section className="advanced-board analysis-reference-runtime">
      <header className="advanced-toolbar">
        <div><strong>{board.title}</strong><small>Analysis v{payload.analysis_version} · run {payload.run_id}</small></div>
        <div className="advanced-toolbar-actions">
          <span className="runtime-badge">{source.version_policy}</span>
          <span className="runtime-badge">UTC · {freshnessLabel(payload.generated_at, payload.result.source_freshness_at)}</span>
          <button type="button" className="secondary" onClick={() => navigate(`/app/analysis/${encodeURIComponent(source.analysis_id)}`)}><ExternalLink size={12} /> Analysis</button>
        </div>
      </header>
      {payload.result.warnings.length ? <div className="analysis-reference-warnings">{payload.result.warnings.map((warning) => <span key={warning}><AlertTriangle size={11} />{warning}</span>)}</div> : null}
      {CHART_KINDS.has(resolvedSpec.kind) ? (
        <EChartsRenderer
          boardId={board.id}
          rows={rows as ChartDatum[]}
          spec={resolvedSpec}
          ariaLabel={`${board.title} analysis result chart`}
          onSelection={onSelectionFilter}
        />
      ) : resolvedSpec.kind === "metric" ? (
        <MetricRenderer
          metrics={rows.slice(0, 6).map((row, index) => ({
            id: String(row.metric ?? row.id ?? index),
            label: String(row.metric ?? row.label ?? `Metric ${index + 1}`),
            value: String(row.value ?? row.count ?? row.average_risk ?? "-"),
          }))}
        />
      ) : (
        <DataTableRenderer
          boardId={board.id}
          rows={rows as TableDatum[]}
          columns={columns}
          rowKey={columns.find((column) => column.id === "event_id")?.id ?? columns[0]?.id ?? "id"}
          searchPlaceholder="Analysis result 검색"
          onRowSelect={(_, filter) => onSelectionFilter?.(filter)}
        />
      )}
      <footer className="data-grid-footer"><span>{payload.result.row_count} rows · {payload.result.elapsed_ms}ms</span><span>{payload.result.cache_hit ? "cache HIT" : "cache MISS"}</span></footer>
    </section>
  );
}
