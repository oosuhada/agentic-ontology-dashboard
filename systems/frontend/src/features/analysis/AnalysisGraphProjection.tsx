import { Background, Controls, MarkerType, MiniMap, ReactFlow, type Edge, type Node } from "@xyflow/react";
import { Eye, EyeOff, Focus, GitBranch } from "lucide-react";
import { useMemo, useState } from "react";
import { DataPill } from "../../ui/foundry/DataPill";
import { analysisCardMetadata } from "./catalog";
import type { AnalysisFlowEdge, AnalysisFlowNode } from "./types";

interface AnalysisGraphProjectionProps {
  nodes: AnalysisFlowNode[];
  edges: AnalysisFlowEdge[];
  selectedNodeId: string;
  hiddenNodeIds: Set<string>;
  showComputationalNodes: boolean;
  onShowComputationalNodesChange: (show: boolean) => void;
  onSelectNode: (nodeId: string) => void;
}

function relatedIds(nodes: AnalysisFlowNode[], edges: AnalysisFlowEdge[], selectedNodeId: string) {
  const result = new Set([selectedNodeId]);
  let changed = true;
  while (changed) {
    changed = false;
    edges.forEach((edge) => {
      if (result.has(edge.source) || result.has(edge.target)) {
        if (!result.has(edge.source)) { result.add(edge.source); changed = true; }
        if (!result.has(edge.target)) { result.add(edge.target); changed = true; }
      }
    });
  }
  return new Set(nodes.filter((node) => result.has(node.id)).map((node) => node.id));
}

function collapseHiddenEdges(edges: AnalysisFlowEdge[], hidden: Set<string>) {
  const visible = edges.filter((edge) => !hidden.has(edge.source) && !hidden.has(edge.target)).map((edge) => ({ ...edge }));
  hidden.forEach((hiddenId) => {
    const upstream = edges.filter((edge) => edge.target === hiddenId).map((edge) => edge.source);
    const downstream = edges.filter((edge) => edge.source === hiddenId).map((edge) => edge.target);
    upstream.forEach((source) => downstream.forEach((target) => {
      if (!hidden.has(source) && !hidden.has(target) && !visible.some((edge) => edge.source === source && edge.target === target)) visible.push({ id: `collapsed:${source}:${target}`, source, target, data: { collapsed: true } });
    }));
  });
  return visible;
}

export function AnalysisGraphProjection({ nodes, edges, selectedNodeId, hiddenNodeIds, showComputationalNodes, onShowComputationalNodesChange, onSelectNode }: AnalysisGraphProjectionProps) {
  const [focusMode, setFocusMode] = useState(false);
  const [layout, setLayout] = useState<"horizontal" | "vertical">("horizontal");
  const collapsedIds = useMemo(() => showComputationalNodes ? new Set<string>() : new Set([...hiddenNodeIds, ...nodes.filter((node) => analysisCardMetadata(node.data.kind).computational).map((node) => node.id)]), [hiddenNodeIds, nodes, showComputationalNodes]);
  const related = useMemo(() => relatedIds(nodes, edges, selectedNodeId), [edges, nodes, selectedNodeId]);
  const visibleNodes = nodes.filter((node) => !collapsedIds.has(node.id) && (!focusMode || related.has(node.id)));
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  const projectedEdges = collapseHiddenEdges(edges, collapsedIds).filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
  const flowNodes = useMemo<Node[]>(() => visibleNodes.map((node, index) => {
    const metadata = analysisCardMetadata(node.data.kind);
    const major = layout === "horizontal" ? { x: 70 + index * 260, y: 100 + (index % 2) * 170 } : { x: 110 + (index % 2) * 300, y: 70 + index * 145 };
    return {
      id: node.id,
      position: major,
      selected: node.id === selectedNodeId,
      className: `analysis-dependency-node kind-${node.data.kind}`,
      data: { label: <div className="analysis-dependency-node__content"><header><GitBranch size={12} /><small>{metadata.category}</small><DataPill kind={metadata.output} compact /></header><strong>{node.data.title}</strong><span>{node.data.rows.toLocaleString()} rows · {node.data.status}</span><div><DataPill kind={metadata.input[0] ?? "none"} /><span>→</span><DataPill kind={metadata.output} /></div></div> },
    };
  }), [layout, selectedNodeId, visibleNodes]);
  const flowEdges = useMemo<Edge[]>(() => projectedEdges.map((edge) => ({ ...edge, markerEnd: { type: MarkerType.ArrowClosed }, animated: false, className: edge.data?.collapsed ? "collapsed-computation-edge" : "" })), [projectedEdges]);
  return (
    <section className="analysis-dependency-graph">
      <header><div><strong>Dependency graph</strong><span>{focusMode ? "Focused dependency chain" : `${visibleNodes.length} visible cards`}</span></div><div><button type="button" className={focusMode ? "active" : ""} onClick={() => setFocusMode((value) => !value)}><Focus size={11} /> Focus</button><button type="button" onClick={() => onShowComputationalNodesChange(!showComputationalNodes)}>{showComputationalNodes ? <EyeOff size={11} /> : <Eye size={11} />}{showComputationalNodes ? "Collapse computation" : "Show computation"}</button><select aria-label="Graph layout" value={layout} onChange={(event) => setLayout(event.target.value as "horizontal" | "vertical")}><option value="horizontal">Left to right</option><option value="vertical">Top to bottom</option></select></div></header>
      <div className="analysis-dependency-graph__canvas"><ReactFlow nodes={flowNodes} edges={flowEdges} fitView minZoom={0.3} maxZoom={1.5} nodesDraggable={false} nodesConnectable={false} onNodeClick={(_, node) => onSelectNode(node.id)}><Background gap={18} size={1} /><MiniMap pannable zoomable /><Controls showInteractive={false} /></ReactFlow></div>
    </section>
  );
}
