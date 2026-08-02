import { AlertTriangle, CheckCircle2, LoaderCircle } from "lucide-react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { analysisNodeIcon } from "./catalog";
import type { AnalysisFlowNode } from "./types";

export function AnalysisBoardCard({ data, selected }: NodeProps<AnalysisFlowNode>) {
  const Icon = analysisNodeIcon(data.kind);
  const statusIntent = data.status === "success" ? "success" : data.status === "error" ? "danger" : data.status === "running" ? "primary" : "neutral";
  return (
    <article className={`analysis-flow-node kind-${data.kind} status-${data.status} ${selected ? "selected" : ""}`}>
      {data.kind !== "input" ? <Handle type="target" position={Position.Top} /> : null}
      <header>
        <span><Icon size={14} /></span>
        <div><small>{data.kind.toUpperCase()}</small><strong>{data.title}</strong></div>
        {data.status === "running" ? <LoaderCircle className="spin" size={14} /> : data.status === "success" ? <CheckCircle2 size={14} /> : data.status === "error" ? <AlertTriangle size={14} /> : null}
      </header>
      <div className="analysis-node-io">
        <div><small>INPUT</small><strong>{data.kind === "input" ? "Ontology / Dataset" : `${data.rows.toLocaleString()} rows`}</strong></div>
        <div><small>OUTPUT</small><strong>{data.outputKind}</strong></div>
      </div>
      <p>{Object.entries(data.config).map(([key, value]) => `${key}: ${value}`).join(" · ")}</p>
      <footer>
        <span><b>{data.rows.toLocaleString()}</b> rows</span>
        <StatusPill intent={statusIntent}>{data.status}</StatusPill>
        <span>{data.elapsedMs}ms</span>
      </footer>
      <Handle type="source" position={Position.Bottom} />
    </article>
  );
}
