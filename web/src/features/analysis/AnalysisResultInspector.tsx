import { AlertTriangle, Clock3, Trash2 } from "lucide-react";
import type { Evidence } from "../../types";
import { AnalysisInspector } from "./AnalysisInspector";
import { AnalysisLineageMiniGraph } from "./AnalysisLineageMiniGraph";
import { InputObjectSetPreview } from "./boards/InputObjectSetPreview";
import type {
  AnalysisFlowEdge,
  AnalysisFlowNode,
  AnalysisNodeExecutionResult,
  AnalysisResult,
} from "./types";

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
  if (Object.values(node.data.config).some((value) => value.toLowerCase().includes("now"))) {
    warnings.push("현재 시각에 의존하는 설정은 실행 시점마다 결과가 달라질 수 있습니다.");
  }
  if (node.data.kind === "group") {
    warnings.push("명시적인 Sort 단계가 없으면 그룹 출력 순서는 결정적이지 않을 수 있습니다.");
  }
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
  if (!node) return <aside className="analysis-result-inspector"><p>Node를 선택하세요.</p></aside>;

  const rows: Array<Record<string, unknown>> = serverResult?.rows ?? result.rows.map((row) => ({ ...row }));
  const profileEntries = Object.values(serverResult?.profile ?? {});
  const nullRate = serverResult?.quality.null_rate ?? (profileEntries.length
    ? profileEntries.reduce((sum, item) => sum + item.null_rate, 0) / profileEntries.length
    : 0);
  const duplicateKey = serverResult?.quality.duplicate_key_count
    ?? rows.length - new Set(rows.map((row) => String(row.event_id ?? row.object_id ?? row.id ?? JSON.stringify(row)))).size;
  const warnings = Array.from(new Set([...(serverResult?.warnings ?? []), ...clientWarnings(node)]));

  return (
    <aside className="analysis-result-inspector">
      <div className="analysis-inspector-heading">
        <div><span className="section-label">NODE INSPECTOR</span><strong>{node.data.title}</strong></div>
        {node.data.kind !== "input" ? <button type="button" title="Node 삭제" onClick={onDeleteNode}><Trash2 size={13} /></button> : null}
      </div>
      <div className="analysis-runtime-badges">
        <span className="od-tag intent-primary"><Clock3 size={11} /> {serverResult?.timezone ?? "Asia/Seoul"}</span>
        <span className={`od-tag ${serverResult?.source_freshness_at ? "intent-success" : "intent-warning"}`}>
          freshness · {freshnessLabel(serverResult?.source_freshness_at)}
        </span>
        <span className="od-tag">{serverResult ? "server run" : "client preview"}</span>
      </div>
      {warnings.length ? (
        <section className="analysis-determinism-warnings">
          {warnings.map((warning) => <p key={warning}><AlertTriangle size={12} /> {warning}</p>)}
        </section>
      ) : null}
      <AnalysisInspector node={node} sourceOptions={sourceOptions} onConfigChange={onConfigChange} />
      {node.data.kind === "input" && !node.data.config.source?.startsWith("dataset:") ? (
        <InputObjectSetPreview
          workspaceId={workspaceId}
          objectType={node.data.config.source === "events" ? "risk_event" : node.data.config.source || "risk_event"}
          selectedEventId={selectedEventId}
          onSelectEvent={onSelectEvent}
        />
      ) : null}
      <section className="analysis-result-stats">
        <h3>Execution</h3>
        <dl>
          <dt>Status</dt><dd>{serverResult?.status ?? node.data.status}</dd>
          <dt>Rows</dt><dd>{serverResult?.row_count ?? node.data.rows}</dd>
          <dt>Columns</dt><dd>{serverResult?.columns.length ?? (rows[0] ? Object.keys(rows[0]).length : 0)}</dd>
          <dt>Null rate</dt><dd>{(nullRate * 100).toFixed(1)}%</dd>
          <dt>Duplicate key</dt><dd>{duplicateKey}</dd>
          <dt>Quality source</dt><dd>{serverResult?.quality.computed_by ?? "client preview"}</dd>
          <dt>Elapsed</dt><dd>{serverResult?.elapsed_ms ?? node.data.elapsedMs}ms</dd>
          <dt>Cache</dt><dd>{serverResult?.cache_hit ? "HIT" : "MISS"}</dd>
          <dt>Generated</dt><dd>{serverResult?.generated_at ? new Date(serverResult.generated_at).toLocaleString() : "preview"}</dd>
          <dt>Source</dt><dd>{String(serverResult?.source_metadata.dataset_id ?? serverResult?.source_metadata.object_type ?? node.data.config.source ?? "unknown")}</dd>
          {serverResult?.source_metadata.dataset_version_id ? <><dt>Dataset version</dt><dd>{String(serverResult.source_metadata.dataset_version_id)}</dd></> : null}
        </dl>
      </section>
      <section>
        <h3>Sample rows</h3>
        <div className="analysis-sample-table">
          {rows.slice(0, 7).map((row, index) => {
            const eventId = String(row.event_id ?? "");
            const key = String(row.object_id ?? row.id ?? eventId ?? index);
            const label = String(row.equipment ?? row.line ?? row.key ?? row.object_type ?? "row");
            const numericRisk = Number(row.risk ?? row.average_risk ?? row.value ?? 0);
            return (
              <button
                type="button"
                key={`${key}:${index}`}
                className={eventId && eventId === selectedEventId ? "active" : ""}
                disabled={!eventId}
                onClick={() => eventId && onSelectEvent(eventId)}
              >
                <code>{eventId || key}</code><span>{label}</span><strong>{Number.isFinite(numericRisk) ? `${(numericRisk * (numericRisk <= 1 ? 100 : 1)).toFixed(1)}%` : "-"}</strong>
              </button>
            );
          })}
        </div>
      </section>
      <AnalysisLineageMiniGraph
        nodes={nodes}
        edges={edges}
        selectedNodeId={node.id}
        modelVersion={evidence?.model.model_version ?? "model pending"}
        revision={revision}
      />
    </aside>
  );
}
