import { ArrowDown, ArrowUp, EyeOff, GitBranch } from "lucide-react";
import { DataPill } from "../../ui/foundry/DataPill";
import { EmptyState } from "../../ui/foundry/WorkbenchState";
import { analysisCardMetadata } from "./catalog";
import type { AnalysisFlowEdge, AnalysisFlowNode } from "./types";

interface AnalysisDependencyPanelProps {
  nodes: AnalysisFlowNode[];
  edges: AnalysisFlowEdge[];
  selectedNodeId: string;
  hiddenNodeIds: Set<string>;
  onSelectNode: (nodeId: string) => void;
}

export function AnalysisDependencyPanel({ nodes, edges, selectedNodeId, hiddenNodeIds, onSelectNode }: AnalysisDependencyPanelProps) {
  const selected = nodes.find((node) => node.id === selectedNodeId);
  if (!selected) return <aside className="analysis-dependency-panel"><EmptyState title="Select a card" detail="Upstream and downstream dependencies will appear here." /></aside>;
  const upstream = edges.filter((edge) => edge.target === selected.id).map((edge) => nodes.find((node) => node.id === edge.source)).filter(Boolean) as AnalysisFlowNode[];
  const downstream = edges.filter((edge) => edge.source === selected.id).map((edge) => nodes.find((node) => node.id === edge.target)).filter(Boolean) as AnalysisFlowNode[];
  const metadata = analysisCardMetadata(selected.data.kind);
  const dependencyRow = (node: AnalysisFlowNode, direction: "upstream" | "downstream") => {
    const itemMetadata = analysisCardMetadata(node.data.kind);
    return <button type="button" key={node.id} onClick={() => onSelectNode(node.id)}>{direction === "upstream" ? <ArrowUp size={11} /> : <ArrowDown size={11} />}<DataPill kind={direction === "upstream" ? itemMetadata.output : metadata.output} compact /><span><strong>{node.data.title}</strong><small>{itemMetadata.output} · {node.data.status}</small></span>{hiddenNodeIds.has(node.id) ? <EyeOff size={11} /> : null}</button>;
  };
  return (
    <aside className="analysis-dependency-panel">
      <header><span className="section-label">DEPENDENCIES</span><strong>{selected.data.title}</strong><small>{selected.id}</small></header>
      <div className="analysis-dependency-current"><GitBranch size={14} /><DataPill kind={metadata.output} /><span>{metadata.computational ? "Computational card" : "Visible result card"}</span></div>
      <section><h3>Inputs <span>{upstream.length}</span></h3>{upstream.map((node) => dependencyRow(node, "upstream"))}{!upstream.length ? <p>No upstream card. This is a root input.</p> : null}</section>
      <section><h3>Outputs <span>{downstream.length}</span></h3>{downstream.map((node) => dependencyRow(node, "downstream"))}{!downstream.length ? <p>No downstream cards consume this result.</p> : null}</section>
      <footer><EyeOff size={11} /><span>Hidden computational cards remain part of execution and lineage.</span></footer>
    </aside>
  );
}
