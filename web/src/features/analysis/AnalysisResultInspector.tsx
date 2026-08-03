import { Activity, AlertTriangle, Clock3, GitBranch, ListChecks, Settings2, Table2, Trash2 } from "lucide-react";
import { useState } from "react";
import type { Evidence } from "../../types";
import { InspectorTabs } from "../../ui/foundry/InspectorTabs";
import { PropertyTable } from "../../ui/foundry/PropertyTable";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { EmptyState } from "../../ui/foundry/WorkbenchState";
import { AnalysisInspector } from "./AnalysisInspector";
import { AnalysisLineageMiniGraph } from "./AnalysisLineageMiniGraph";
import { AnalysisTimeSeriesForecast } from "./AnalysisTimeSeriesForecast";
import { InputObjectSetPreview } from "./boards/InputObjectSetPreview";
import type {
  AnalysisFlowEdge,
  AnalysisFlowNode,
  AnalysisNodeExecutionResult,
  AnalysisResult,
} from "./types";

type InspectorTab = "configuration" | "result" | "forecast" | "quality" | "lineage" | "runtime";

interface AnalysisResultInspectorProps {
  node: AnalysisFlowNode | undefined;
  nodes: AnalysisFlowNode[];
  edges: AnalysisFlowEdge[];
  result: AnalysisResult;
  serverResult?: AnalysisNodeExecutionResult;
  workspaceId: string;
  selectedEventId: string;
  evidence: Evidence | null;
  revision: number;
  sourceOptions?: Array<{ value: string; label: string }>;
  onConfigChange: (key: string, value: string) => void;
  onDeleteNode: () => void;
  onSelectEvent: (eventId: string) => void;
}

function freshnessLabel(value: string | null | undefined) {
  if (!value) return "unknown";
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return value;
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m old`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h old`;
  return `${Math.floor(hours / 24)}d old`;
}

function clientWarnings(node: AnalysisFlowNode) {
  const warnings: string[] = [];
  if (Object.values(node.data.config).some((value) => value.toLowerCase().includes("now"))) warnings.push("현재 시각에 의존하는 설정은 실행 시점마다 결과가 달라질 수 있습니다.");
  if (node.data.kind === "group") warnings.push("명시적인 Sort 단계가 없으면 그룹 출력 순서는 결정적이지 않을 수 있습니다.");
  return warnings;
}

export function AnalysisResultInspector({
  node,
  nodes,
  edges,
  result,
  serverResult,
  workspaceId,
  selectedEventId,
  evidence,
  revision,
  sourceOptions = [],
  onConfigChange,
  onDeleteNode,
  onSelectEvent,
}: AnalysisResultInspectorProps) {
  const [activeTab, setActiveTab] = useState<InspectorTab>("configuration");
  if (!node) return <aside className="analysis-result-inspector"><EmptyState title="Select a board" detail="Configuration, result quality, lineage, and runtime will appear here." /></aside>;

  const rows: Array<Record<string, unknown>> = serverResult?.rows ?? result.rows.map((row) => ({ ...row }));
  const profileEntries = Object.values(serverResult?.profile ?? {});
  const nullRate = serverResult?.quality.null_rate ?? (profileEntries.length ? profileEntries.reduce((sum, item) => sum + item.null_rate, 0) / profileEntries.length : 0);
  const duplicateKey = serverResult?.quality.duplicate_key_count ?? rows.length - new Set(rows.map((row) => String(row.event_id ?? row.object_id ?? row.id ?? JSON.stringify(row)))).size;
  const warnings = Array.from(new Set([...(serverResult?.warnings ?? []), ...clientWarnings(node)]));
  const source = String(serverResult?.source_metadata.dataset_id ?? serverResult?.source_metadata.object_type ?? node.data.config.source ?? "unknown");

  return (
    <aside className="analysis-result-inspector">
      <div className="analysis-inspector-heading">
        <div><span className="section-label">BOARD INSPECTOR</span><strong>{node.data.title}</strong><small>{node.id}</small></div>
        {node.data.kind !== "input" ? <button type="button" title="Node 삭제" onClick={onDeleteNode}><Trash2 size={13} /></button> : null}
      </div>
      <div className="analysis-runtime-badges">
        <StatusPill intent="primary"><Clock3 size={10} /> {serverResult?.timezone ?? "Asia/Seoul"}</StatusPill>
        <StatusPill intent={serverResult?.source_freshness_at ? "success" : "warning"}>freshness · {freshnessLabel(serverResult?.source_freshness_at)}</StatusPill>
        <StatusPill>{serverResult ? "server run" : "client preview"}</StatusPill>
      </div>
      <InspectorTabs
        activeTab={activeTab}
        onChange={setActiveTab}
        label="Analysis inspector sections"
        tabs={[
          { id: "configuration", label: "Config", icon: <Settings2 size={11} /> },
          { id: "result", label: "Result", count: rows.length, icon: <Table2 size={11} /> },
          { id: "forecast", label: "Forecast", icon: <Activity size={11} /> },
          { id: "quality", label: "Quality", count: warnings.length, icon: <ListChecks size={11} /> },
          { id: "lineage", label: "Lineage", icon: <GitBranch size={11} /> },
          { id: "runtime", label: "Runtime", icon: <Clock3 size={11} /> },
        ]}
      />

      <div className="analysis-inspector-tab-body">
        {activeTab === "configuration" ? (
          <>
            <AnalysisInspector node={node} sourceOptions={sourceOptions} onConfigChange={onConfigChange} />
            {node.data.kind === "input" && !node.data.config.source?.startsWith("dataset:") ? (
              <InputObjectSetPreview workspaceId={workspaceId} objectType={node.data.config.source === "events" ? "risk_event" : node.data.config.source || "risk_event"} selectedEventId={selectedEventId} onSelectEvent={onSelectEvent} />
            ) : null}
          </>
        ) : null}

        {activeTab === "result" ? (
          <section>
            <h3>Sample rows</h3>
            <div className="analysis-sample-table">
              {rows.slice(0, 10).map((row, index) => {
                const eventId = String(row.event_id ?? "");
                const key = String((row.object_id ?? row.id ?? eventId) || index);
                const label = String(row.equipment ?? row.line ?? row.key ?? row.object_type ?? "row");
                const numericRisk = Number(row.risk ?? row.average_risk ?? row.value ?? 0);
                return <button type="button" key={`${key}:${index}`} className={eventId && eventId === selectedEventId ? "active" : ""} disabled={!eventId} onClick={() => eventId && onSelectEvent(eventId)}><code>{eventId || key}</code><span>{label}</span><strong>{Number.isFinite(numericRisk) ? `${(numericRisk * (numericRisk <= 1 ? 100 : 1)).toFixed(1)}%` : "-"}</strong></button>;
              })}
              {!rows.length ? <EmptyState title="No result rows" detail="Run the path or change the selected board configuration." /> : null}
            </div>
          </section>
        ) : null}

        {activeTab === "forecast" ? <AnalysisTimeSeriesForecast result={result} serverResult={serverResult} /> : null}

        {activeTab === "quality" ? (
          <section>
            <PropertyTable rows={[
              { id: "rows", label: "Row count", value: serverResult?.quality.row_count ?? rows.length, type: "integer", numeric: true },
              { id: "columns", label: "Column count", value: serverResult?.quality.column_count ?? (rows[0] ? Object.keys(rows[0]).length : 0), type: "integer", numeric: true },
              { id: "null", label: "Null rate", value: `${(nullRate * 100).toFixed(1)}%`, status: { label: nullRate > .1 ? "warning" : "healthy", intent: nullRate > .1 ? "warning" : "success" } },
              { id: "duplicates", label: "Duplicate keys", value: duplicateKey, status: { label: duplicateKey ? "review" : "clean", intent: duplicateKey ? "warning" : "success" }, numeric: true },
              { id: "computed", label: "Computed by", value: serverResult?.quality.computed_by ?? "client preview", type: "source" },
            ]} />
            {warnings.length ? <div className="analysis-determinism-warnings">{warnings.map((warning) => <p key={warning}><AlertTriangle size={12} /> {warning}</p>)}</div> : <StatusPill intent="success">No determinism warnings</StatusPill>}
          </section>
        ) : null}

        {activeTab === "lineage" ? (
          <section className="analysis-lineage-detail">
            <PropertyTable rows={[
              { id: "source", label: "Source", value: source, type: "resource", mono: true },
              { id: "version", label: "Analysis revision", value: revision, type: "pinned", numeric: true },
              { id: "model", label: "Model version", value: evidence?.model.model_version ?? "model pending", type: "model" },
              { id: "nodes", label: "Upstream boards", value: nodes.length, type: "graph", numeric: true },
            ]} />
          </section>
        ) : null}

        {activeTab === "runtime" ? (
          <section className="analysis-result-stats">
            <PropertyTable rows={[
              { id: "status", label: "Status", value: serverResult?.status ?? node.data.status, status: { label: serverResult?.status ?? node.data.status, intent: (serverResult?.status ?? node.data.status) === "succeeded" || node.data.status === "success" ? "success" : node.data.status === "error" ? "danger" : "neutral" } },
              { id: "elapsed", label: "Elapsed", value: `${serverResult?.elapsed_ms ?? node.data.elapsedMs}ms`, type: "duration", numeric: true },
              { id: "cache", label: "Cache", value: serverResult?.cache_hit ? "HIT" : "MISS", status: { label: serverResult?.cache_hit ? "hit" : "miss", intent: serverResult?.cache_hit ? "success" : "neutral" } },
              { id: "generated", label: "Generated", value: serverResult?.generated_at ? new Date(serverResult.generated_at).toLocaleString() : "preview", type: "datetime" },
              { id: "freshness", label: "Source freshness", value: freshnessLabel(serverResult?.source_freshness_at), type: "freshness" },
              { id: "dataset", label: "Dataset version", value: String(serverResult?.source_metadata.dataset_version_id ?? "—"), type: "version", mono: true },
            ]} />
          </section>
        ) : null}
      </div>

      <AnalysisLineageMiniGraph nodes={nodes} edges={edges} selectedNodeId={node.id} modelVersion={evidence?.model.model_version ?? "model pending"} revision={revision} />
    </aside>
  );
}
