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
import "@xyflow/react/dist/style.css";
import { queryDashboardBoard, traverseOntologyObject } from "../../api";
import type { OntologyTraversal } from "../ontology/types";
import type { Evidence, EventSummary, Report } from "../../types";
import type { RenderSpec, SelectionFilter } from "./types";
import { EChartsRenderer } from "./renderers/EChartsRenderer";
import { DataTableRenderer, type DataTableColumn, type TableDatum } from "./renderers/DataTableRenderer";
import { MetricRenderer } from "./renderers/MetricRenderer";

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
          { id: "objects", label: "Visible objects", value: filtered.length, detail: "현재 parameter scope" },
          { id: "critical", label: "Critical / hold", value: critical, detail: "즉시 검토 대상", tone: "danger" },
          { id: "attention", label: "Attention", value: attention, detail: "경고·주의 상태", tone: "warning" },
          { id: "risk", label: "Average risk", value: `${(averageRisk * 100).toFixed(1)}%`, detail: "failure probability" },
          { id: "downtime", label: "Downtime exposure", value: downtime, detail: "estimated minutes" },
        ]}
        footer={{ label: "Filter coverage", value: `${filtered.length}/${events.length}`, progress: monitored }}
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
        <div><strong>Portfolio signal explorer</strong><small>데이터 점을 선택하면 Object Context와 downstream board가 갱신됩니다.</small></div>
        <div className="advanced-toolbar-actions">
          <div className="segmented-control">
            <button type="button" className={metric === "risk" ? "active" : ""} onClick={() => setMetric("risk")}>Risk</button>
            <button type="button" className={metric === "downtime" ? "active" : ""} onClick={() => setMetric("downtime")}>Downtime</button>
          </div>
          <div className="segmented-control">
            <button type="button" className={view === "bar" ? "active" : ""} onClick={() => setView("bar")}>Bar</button>
            <button type="button" className={view === "line" ? "active" : ""} onClick={() => setView("line")}>Line</button>
          </div>
        </div>
      </header>
      <EChartsRenderer
        boardId={boardId}
        rows={rows}
        spec={spec}
        selectedValue={selected}
        ariaLabel={`${metric} portfolio chart`}
        onSelection={(filter) => {
          onSelectionFilter?.(filter);
          const event = filtered.find((item) => item.equipment.display_name === filter.values[0]);
          if (event) onSelectEvent(event.event_id);
        }}
      />
    </section>
  );
}

const EVENT_COLUMNS: DataTableColumn[] = [
  { id: "event_id", label: "Event", size: 140, format: "code" },
  { id: "equipment", label: "Equipment", size: 190 },
  { id: "line", label: "Line", size: 100 },
  { id: "status", label: "Status", size: 120, format: "status" },
  { id: "risk", label: "Risk", size: 90, format: "percent" },
  { id: "failure_type", label: "Failure type", size: 180 },
  { id: "downtime", label: "Exposure", size: 100, format: "minutes" },
  { id: "confidence", label: "Confidence", size: 100, hidden: true },
];

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
  const [pageIndex, setPageIndex] = useState(0);
  const [pageSize, setPageSize] = useState(50);
  const [search, setSearch] = useState("");
  const [serverRows, setServerRows] = useState<TableDatum[]>([]);
  const [totalRows, setTotalRows] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fallbackRows = useMemo<TableDatum[]>(() => visibleEvents(events, parameterState).map((event) => ({
    event_id: event.event_id,
    equipment: event.equipment.display_name,
    line: event.equipment.line,
    status: event.status,
    risk: probability(event),
    failure_type: event.predicted_failure_type,
    downtime: event.equipment.estimated_downtime_minutes,
    confidence: event.confidence,
  })), [events, parameterState]);

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
        columns={EVENT_COLUMNS}
        rowKey="event_id"
        selectedRowKey={selectedEventId}
        searchPlaceholder="event, equipment, line, status 검색"
        serverPagination={{
          pageIndex,
          pageSize,
          totalRows,
          loading,
          error: error ? `Server query fallback · ${error}` : undefined,
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
      <footer className="data-grid-footer"><span>Server pagination · page virtual scroll</span><span>행 선택 → server cross-filter 재조회</span></footer>
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
    const eventId = object.object_type === "risk_event" ? object.id.split(":", 2)[1] : "";
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
    traverseOntologyObject(`risk_event:${selected.event_id}`, {
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
  if (!selected) return <div className="advanced-empty">Ontology context가 없습니다.</div>;
  return (
    <section className="advanced-board ontology-board react-flow-board">
      <header className="advanced-toolbar">
        <div><strong>Ontology object graph</strong><small>실제 workspace-scoped traverse 결과 · 최대 2 hop</small></div>
        <span className="runtime-badge"><GitBranch size={12} /> {loading ? "loading" : `${graph.nodes.length} objects`}</span>
      </header>
      {error ? <div className="od-non-ideal-state"><strong>Ontology traversal failed</strong><span>{error}</span></div> : null}
      {!error && graph.nodes.length ? (
        <div className="ontology-react-flow">
          <ReactFlow nodes={graph.nodes} edges={graph.edges} fitView minZoom={0.45} maxZoom={1.6} nodesDraggable nodesConnectable={false} elementsSelectable onNodeClick={(_, node) => { const eventId = String(node.data.eventId ?? ""); if (eventId) onSelectEvent(eventId); }}>
            <Background gap={18} size={1} /><MiniMap pannable zoomable nodeStrokeWidth={3} /><Controls showInteractive={false} />
          </ReactFlow>
        </div>
      ) : !loading && !error ? <div className="advanced-empty">연결된 Ontology Object가 없습니다.</div> : null}
    </section>
  );
}

export function ActivityStreamBoard({ events, selectedEventId, evidence, report, onSelectEvent }: Pick<AdvancedBoardProps, "events" | "selectedEventId" | "evidence" | "report" | "onSelectEvent">) {
  const items = [
    { id: evidence.evidence_id, title: "Evidence package resolved", detail: `${evidence.model.model_version} · ${evidence.maintenance_context.provider}`, meta: evidence.generated_at, eventId: evidence.event_id, icon: Database },
    { id: report.report_id, title: "Grounded report generated", detail: report.headline, meta: report.generated_at, eventId: report.event_id, icon: Activity },
    ...events.slice(0, 8).map((event, index) => ({ id: event.event_id, title: `${event.equipment.display_name} · ${event.status}`, detail: `${event.predicted_failure_type} · ${(probability(event) * 100).toFixed(1)}% risk`, meta: `T-${index + 1} signal`, eventId: event.event_id, icon: SlidersHorizontal })),
  ];
  return (
    <section className="advanced-board activity-stream-board">
      <header className="advanced-toolbar"><div><strong>Operational activity</strong><small>Object, Evidence, Report와 Signal 변경 이력</small></div><span className="runtime-badge"><Activity size={12} /> Live</span></header>
      <ol>{items.map((item) => { const Icon = item.icon; return <li key={item.id} className={item.eventId === selectedEventId ? "active" : ""}><button type="button" onClick={() => onSelectEvent(item.eventId)}><i><Icon size={11} /></i><span><strong>{item.title}</strong><small>{item.detail}</small></span><time>{item.meta}</time></button></li>; })}</ol>
    </section>
  );
}
