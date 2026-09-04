import { useEffect, useMemo, useState } from "react";
import { Activity, Database, GitBranch, SlidersHorizontal } from "lucide-react";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import { queryDashboardBoard, traverseOntologyObject } from "../../api";
import type { OntologyTraversal } from "../ontology/types";
import type { Evidence, EventSummary, Report } from "../../types";
import { filterEventsBySelection } from "./cross-filter-engine";
import type { RenderSpec, SelectionFilter } from "./types";
import { EChartsRenderer } from "./renderers/EChartsRenderer";
import { DataTableRenderer, type DataTableColumn, type TableDatum } from "./renderers/DataTableRenderer";
import { MetricRenderer } from "./renderers/MetricRenderer";
import { useI18n } from "../../ui/i18n/I18nProvider";

interface AdvancedBoardProps {
  boardId: string;
  dashboardId: string;
  workspaceId: string;
  events: EventSummary[];
  selectedEventId: string;
  evidence: Evidence;
  report: Report;
  parameterState: Record<string, unknown>;
  selectionFilters: SelectionFilter[];
  onSelectEvent: (eventId: string) => void;
  onSelectionFilter?: (filter: SelectionFilter) => void;
}

function probability(event: EventSummary) {
  return event.failure_probability ?? 0;
}

function visibleEvents(events: EventSummary[], parameterState: Record<string, unknown>) {
  const statusFilter = String(parameterState.status_filter ?? "all");
  return statusFilter === "all" ? events : events.filter((event) => event.status === statusFilter);
}

function statusTone(status: string) {
  if (["critical", "data_quality_hold"].includes(status)) return "danger" as const;
  if (["warning", "attention"].includes(status)) return "warning" as const;
  return "success" as const;
}

export function OperationsKpiBoard({ events, parameterState }: Pick<AdvancedBoardProps, "events" | "parameterState">) {
  const { t } = useI18n();
  const filtered = visibleEvents(events, parameterState);
  const critical = filtered.filter((event) => statusTone(event.status) === "danger").length;
  const attention = filtered.filter((event) => statusTone(event.status) === "warning").length;
  const averageRisk = filtered.length ? filtered.reduce((sum, event) => sum + probability(event), 0) / filtered.length : 0;
  const downtime = filtered.reduce((sum, event) => sum + event.equipment.estimated_downtime_minutes, 0);
  const monitored = events.length ? (filtered.length / events.length) * 100 : 0;

  return (
    <section className="advanced-board advanced-kpi-board">
      <MetricRenderer
        metrics={[
          { id: "objects", label: t("advanced.visibleObjects"), value: filtered.length, detail: t("advanced.currentParameterScope") },
          { id: "critical", label: t("advanced.criticalHold"), value: critical, detail: t("advanced.immediateReview"), tone: "danger" },
          { id: "attention", label: t("advanced.attention"), value: attention, detail: t("advanced.warningAttention"), tone: "warning" },
          { id: "risk", label: t("advanced.averageRisk"), value: `${(averageRisk * 100).toFixed(1)}%`, detail: t("advanced.failureProbability") },
          { id: "downtime", label: t("advanced.downtimeExposure"), value: downtime, detail: t("advanced.estimatedMinutes") },
        ]}
        footer={{ label: t("advanced.filterCoverage"), value: `${filtered.length}/${events.length}`, progress: monitored }}
      />
    </section>
  );
}

export function RiskTrendWorkbench({
  boardId,
  events,
  selectedEventId,
  parameterState,
  onSelectEvent,
  onSelectionFilter,
}: Pick<AdvancedBoardProps, "boardId" | "events" | "selectedEventId" | "parameterState" | "onSelectEvent" | "onSelectionFilter">) {
  const { t } = useI18n();
  const [metric, setMetric] = useState<"risk" | "downtime">("risk");
  const [view, setView] = useState<"bar" | "line">("bar");
  const filtered = useMemo(
    () => [...visibleEvents(events, parameterState)].sort((left, right) => probability(right) - probability(left)),
    [events, parameterState],
  );
  const rows = useMemo(() => filtered.map((event) => ({
    equipment: event.equipment.display_name,
    event_id: event.event_id,
    risk: probability(event) * 100,
    downtime: event.equipment.estimated_downtime_minutes,
  })), [filtered]);
  const spec: RenderSpec = {
    kind: view,
    x_field: "equipment",
    y_field: metric,
    aggregation: "avg",
    selectable: true,
    brushable: true,
  };
  const selected = filtered.find((event) => event.event_id === selectedEventId)?.equipment.display_name;

  return (
    <section className="advanced-board risk-workbench">
      <header className="advanced-toolbar">
        <div><strong>{t("advanced.portfolioExplorer")}</strong><small>{t("advanced.portfolioExplorerDetail")}</small></div>
        <div className="advanced-toolbar-actions">
          <div className="segmented-control">
            <button type="button" className={metric === "risk" ? "active" : ""} onClick={() => setMetric("risk")}>{t("advanced.risk")}</button>
            <button type="button" className={metric === "downtime" ? "active" : ""} onClick={() => setMetric("downtime")}>{t("advanced.downtime")}</button>
          </div>
          <div className="segmented-control">
            <button type="button" className={view === "bar" ? "active" : ""} onClick={() => setView("bar")}>{t("advanced.bar")}</button>
            <button type="button" className={view === "line" ? "active" : ""} onClick={() => setView("line")}>{t("advanced.line")}</button>
          </div>
        </div>
      </header>
      <EChartsRenderer
        boardId={boardId}
        rows={rows}
        spec={spec}
        selectedValue={selected}
        ariaLabel={t("advanced.chartAria", { metric: metric === "risk" ? t("advanced.risk") : t("advanced.downtime") })}
        onSelection={(filter) => {
          onSelectionFilter?.(filter);
          const event = filtered.find((item) => item.equipment.display_name === filter.values[0]);
          if (event) onSelectEvent(event.event_id);
        }}
      />
    </section>
  );
}

export function EventDataGridBoard({
  boardId,
  dashboardId,
  workspaceId,
  events,
  selectedEventId,
  parameterState,
  selectionFilters,
  onSelectEvent,
  onSelectionFilter,
}: Pick<AdvancedBoardProps, "boardId" | "dashboardId" | "workspaceId" | "events" | "selectedEventId" | "parameterState" | "selectionFilters" | "onSelectEvent" | "onSelectionFilter">) {
  const { t } = useI18n();
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [search, setSearch] = useState("");
  const [serverRows, setServerRows] = useState<TableDatum[]>([]);
  const [totalRows, setTotalRows] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const columns = useMemo<DataTableColumn[]>(() => [
    { id: "event_id", label: t("advanced.column.event"), size: 140, format: "code" },
    { id: "equipment", label: t("advanced.column.equipment"), size: 190 },
    { id: "line", label: t("advanced.column.line"), size: 100 },
    { id: "status", label: t("advanced.column.status"), size: 120, format: "status" },
    { id: "risk", label: t("advanced.column.risk"), size: 90, format: "percent" },
    { id: "failure_type", label: t("advanced.column.failureType"), size: 180 },
    { id: "downtime", label: t("advanced.column.exposure"), size: 100, format: "minutes" },
    { id: "confidence", label: t("advanced.column.confidence"), size: 100, hidden: true },
  ], [t]);

  const fallbackRows = useMemo<TableDatum[]>(() => visibleEvents(filterEventsBySelection(events, selectionFilters), parameterState).map((event) => ({
    event_id: event.event_id,
    equipment: event.equipment.display_name,
    line: event.equipment.line,
    status: event.status,
    risk: probability(event),
    failure_type: event.predicted_failure_type,
    downtime: event.equipment.estimated_downtime_minutes,
    confidence: event.confidence,
  })), [events, parameterState, selectionFilters]);

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
      offset: pageIndex * pageSize,
      limit: pageSize,
      search,
    })
      .then((payload) => {
        if (!active) return;
        setServerRows(payload.rows as TableDatum[]);
        setTotalRows(payload.row_count);
      })
      .catch((reason: unknown) => {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : String(reason));
        const filtered = search
          ? fallbackRows.filter((row) => JSON.stringify(row).toLowerCase().includes(search.toLowerCase()))
          : fallbackRows;
        setServerRows(filtered.slice(pageIndex * pageSize, pageIndex * pageSize + pageSize));
        setTotalRows(filtered.length);
      })
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [boardId, dashboardId, fallbackRows, pageIndex, pageSize, parameterState, search, selectionFilters, workspaceId]);

  useEffect(() => { setPageIndex(0); }, [parameterState, search, selectionFilters]);

  return (
    <section className="advanced-board data-grid-board">
      <DataTableRenderer
        boardId={boardId}
        rows={serverRows}
        columns={columns}
        rowKey="event_id"
        selectedRowKey={selectedEventId}
        searchPlaceholder={t("advanced.searchPlaceholder")}
        serverPagination={{
          pageIndex,
          pageSize,
          totalRows,
          loading,
          error: error ? `${t("advanced.serverFallback")} · ${error}` : undefined,
          search,
          onPageIndexChange: setPageIndex,
          onPageSizeChange: (size) => { setPageSize(size); setPageIndex(0); },
          onSearchChange: (value) => { setSearch(value); setPageIndex(0); },
        }}
        onRowSelect={(row, filter) => {
          onSelectionFilter?.(filter);
          onSelectEvent(String(row.event_id));
        }}
      />
      <footer className="data-grid-footer"><span>{t("advanced.serverPagination")}</span><span>{t("advanced.rowSelection")}</span></footer>
    </section>
  );
}

function objectLabel(objectType: string, id: string, properties: Record<string, unknown>) {
  const name = properties.display_name ?? properties.status ?? properties.model_version ?? properties.action ?? id.split(":", 2)[1] ?? id;
  return `${objectType.replaceAll("_", " ")}\n${String(name)}`;
}

function traversalGraph(traversal: OntologyTraversal | null): { nodes: Node[]; edges: Edge[] } {
  if (!traversal) return { nodes: [], edges: [] };
  const objects = [traversal.root, ...traversal.nodes];
  const levels: Record<string, number> = {
    equipment: 0,
    risk_event: 1,
    evidence_package: 2,
    work_order: 2,
    inspection: 2,
    maintenance_action: 3,
  };
  const grouped = objects.reduce<Record<number, typeof objects>>((acc, object) => {
    const level = levels[object.object_type] ?? 2;
    (acc[level] ??= []).push(object);
    return acc;
  }, {});
  const nodes = Object.entries(grouped).flatMap(([levelValue, items]) => items.map((object, index): Node => {
    const level = Number(levelValue);
    const eventId = object.object_type === "risk_event"
      ? String(object.properties.artifact_id ?? object.properties.event_id ?? "")
      : "";
    return {
      id: object.id,
      position: { x: level * 225 + 20, y: index * 125 + 40 },
      data: { label: objectLabel(object.object_type, object.id, object.properties), eventId },
      type: level === 0 ? "input" : level >= 3 ? "output" : undefined,
      className: `ontology-node ${object.object_type}-node`,
    };
  }));
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = traversal.edges
    .filter((edge) => nodeIds.has(edge.source_object_id) && nodeIds.has(edge.target_object_id))
    .map((edge): Edge => ({
      id: edge.id,
      source: edge.source_object_id,
      target: edge.target_object_id,
      label: edge.link_type,
      markerEnd: { type: MarkerType.ArrowClosed },
      animated: edge.source_object_id === traversal.root.id,
    }));
  return { nodes, edges };
}

export function OntologyRelationshipBoard({ workspaceId, events, selectedEventId, onSelectEvent }: Pick<AdvancedBoardProps, "workspaceId" | "events" | "selectedEventId" | "onSelectEvent">) {
  const { t } = useI18n();
  const selected = events.find((event) => event.event_id === selectedEventId) ?? events[0];
  const [traversal, setTraversal] = useState<OntologyTraversal | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    if (!selected) {
      setTraversal(null);
      return () => { active = false; };
    }
    setLoading(true);
    setError("");
    traverseOntologyObject(selected.ontology_object_id ?? `risk_event:${selected.event_id}`, {
      workspace_id: workspaceId,
      direction: "both",
      depth: 2,
    })
      .then((payload) => active && setTraversal(payload))
      .catch((reason: unknown) => {
        if (!active) return;
        setTraversal(null);
        setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [selected, workspaceId]);

  const graph = useMemo(() => traversalGraph(traversal), [traversal]);
  if (!selected) return <div className="advanced-empty">{t("advanced.noOntologyContext")}</div>;
  return (
    <section className="advanced-board ontology-board react-flow-board">
      <header className="advanced-toolbar">
        <div><strong>{t("advanced.ontologyGraph")}</strong><small>{t("advanced.ontologyGraphDetail")}</small></div>
        <span className="runtime-badge"><GitBranch size={12} /> {loading ? t("advanced.loading") : t("advanced.objects", { count: graph.nodes.length })}</span>
      </header>
      {error ? <div className="od-non-ideal-state"><strong>{t("advanced.ontologyFailed")}</strong><span>{error}</span></div> : null}
      {!error && graph.nodes.length ? (
        <div className="ontology-react-flow">
          <ReactFlow nodes={graph.nodes} edges={graph.edges} fitView minZoom={0.45} maxZoom={1.6} nodesDraggable nodesConnectable={false} elementsSelectable onNodeClick={(_, node) => { const eventId = String(node.data.eventId ?? ""); if (eventId) onSelectEvent(eventId); }}>
            <Background gap={18} size={1} /><MiniMap pannable zoomable nodeStrokeWidth={3} /><Controls showInteractive={false} />
          </ReactFlow>
        </div>
      ) : !loading && !error ? <div className="advanced-empty">{t("advanced.noOntologyObjects")}</div> : null}
    </section>
  );
}

export function ActivityStreamBoard({ events, selectedEventId, evidence, report, onSelectEvent }: Pick<AdvancedBoardProps, "events" | "selectedEventId" | "evidence" | "report" | "onSelectEvent">) {
  const { locale, t } = useI18n();
  const items = [
    { id: evidence.evidence_id, title: t("advanced.evidenceResolved"), detail: `${evidence.model.model_version} · ${evidence.maintenance_context.provider}`, meta: evidence.generated_at, eventId: evidence.event_id, icon: Database },
    { id: report.report_id, title: t("advanced.reportGenerated"), detail: report.headline, meta: report.generated_at, eventId: report.event_id, icon: Activity },
    ...events.slice(0, 8).map((event, index) => ({ id: event.event_id, title: `${event.equipment.display_name} · ${event.status}`, detail: `${event.predicted_failure_type} · ${(probability(event) * 100).toLocaleString(locale, { maximumFractionDigits: 1 })}% ${t("advanced.riskSuffix")}`, meta: t("advanced.signalSequence", { index: index + 1 }), eventId: event.event_id, icon: SlidersHorizontal })),
  ];
  return (
    <section className="advanced-board activity-stream-board">
      <header className="advanced-toolbar"><div><strong>{t("advanced.operationalActivity")}</strong><small>{t("advanced.operationalActivityDetail")}</small></div><span className="runtime-badge"><Activity size={12} /> {t("advanced.live")}</span></header>
      <ol>{items.map((item) => { const Icon = item.icon; return <li key={item.id} className={item.eventId === selectedEventId ? "active" : ""}><button type="button" onClick={() => onSelectEvent(item.eventId)}><i><Icon size={11} /></i><span><strong>{item.title}</strong><small>{item.detail}</small></span><time>{item.meta}</time></button></li>; })}</ol>
    </section>
  );
}
