import { CheckCircle2, LoaderCircle } from "lucide-react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { analysisNodeIcon } from "./catalog";
import type { AnalysisFlowNode } from "./types";

export function AnalysisBoardCard({ data, selected }: NodeProps<AnalysisFlowNode>) {
  const Icon = analysisNodeIcon(data.kind);
  return (
    <article className={`analysis-flow-node status-${data.status} ${selected ? "selected" : ""}`}>
      {data.kind !== "input" ? <Handle type="target" position={Position.Top} /> : null}
      <header>
        <span><Icon size={14} /></span>
        <div><small>{data.kind.toUpperCase()}</small><strong>{data.title}</strong></div>
        {data.status === "running" ? <LoaderCircle className="spin" size={14} /> : data.status === "success" ? <CheckCircle2 size={14} /> : null}
      </header>
      <p>{Object.entries(data.config).map(([key, value]) => `${key}: ${value}`).join(" · ")}</p>
      <footer><span><b>{data.rows}</b> rows</span><span>{data.outputKind}</span><span>{data.elapsedMs}ms</span></footer>
      <Handle type="source" position={Position.Bottom} />
    </article>
  );
}
