import { AlertTriangle, Braces, CheckCircle2, Combine, GitFork, LoaderCircle } from "lucide-react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { StatusPill } from "../../ui/foundry/StatusPill";
import { DataPill } from "../../ui/foundry/DataPill";
import { analysisCardMetadata, analysisNodeIcon } from "./catalog";
import type { AnalysisFlowNode } from "./types";

export function AnalysisBoardCard({ data, selected }: NodeProps<AnalysisFlowNode>) {
  const Icon = analysisNodeIcon(data.kind);
  const metadata = analysisCardMetadata(data.kind);
  const statusIntent = data.status === "success" ? "success" : data.status === "error" ? "danger" : data.status === "running" ? "primary" : "neutral";
  const schemas: Record<string, { input: string[]; output: string[] }> = {
    input: { input: ["Ontology object set"], output: ["event_id:string", "risk:number", "status:string"] },
    filter: { input: ["rows<T>"], output: ["rows<T>", "rejected<T>"] },
    group: { input: ["rows<T>"], output: ["groups<K,T>"] },
    aggregate: { input: ["groups<K,T>"], output: ["key:string", "count:integer", "metric:number"] },
    formula: { input: ["rows<T>"], output: ["rows<T+derived>"] },
    join: { input: ["left<T>", "right<U>"], output: ["rows<T∩U>"] },
    chart: { input: ["rows<T>"], output: ["render_spec", "selection"] },
    table: { input: ["rows<T>"], output: ["page<T>", "selection"] },
    evidence: { input: ["object refs"], output: ["evidence refs"] },
  };
  const schema = schemas[data.kind] ?? { input: ["rows<T>"], output: [data.outputKind] };
  return (
    <article className={`analysis-flow-node kind-${data.kind} status-${data.status} ${selected ? "selected" : ""}`}>
      {data.kind !== "input" ? <><span className="analysis-port-label input-port">INPUT</span><Handle id="input" type="target" position={Position.Top} /></> : null}
      <header>
        <span><Icon size={14} /></span>
        <div><small>{data.kind.toUpperCase()}</small><strong>{data.title}</strong></div>
        <div className="analysis-node-header-state">{data.kind === "filter" ? <GitFork size={12} aria-label="Branching transform" /> : data.kind === "join" ? <Combine size={12} aria-label="Join transform" /> : <Braces size={12} aria-label="Typed transform" />}{data.status === "running" ? <LoaderCircle className="spin" size={14} /> : data.status === "success" ? <CheckCircle2 size={14} /> : data.status === "error" ? <AlertTriangle size={14} /> : null}</div>
      </header>
      <div className="analysis-node-io">
        <div><small>INPUT CONTRACT</small><DataPill kind={metadata.input[0] ?? "none"} /><strong>{data.kind === "input" ? "Ontology / Dataset" : `${data.rows.toLocaleString()} rows`}</strong>{schema.input.map((field) => <code key={field}>{field}</code>)}</div>
        <div><small>OUTPUT CONTRACT</small><DataPill kind={metadata.output} /><strong>{data.outputKind}</strong>{schema.output.map((field) => <code key={field}>{field}</code>)}</div>
      </div>
      <div className="analysis-node-config">{Object.entries(data.config).slice(0, 3).map(([key, value]) => <span key={key}><small>{key}</small><code>{value}</code></span>)}</div>
      <footer>
        <span><b>{data.rows.toLocaleString()}</b> rows</span>
        <StatusPill intent={statusIntent}>{data.status}</StatusPill>
        <span>{data.elapsedMs}ms</span>
      </footer>
      <span className="analysis-port-label output-port">OUTPUT</span><Handle id="output" type="source" position={Position.Bottom} />
    </article>
  );
}
