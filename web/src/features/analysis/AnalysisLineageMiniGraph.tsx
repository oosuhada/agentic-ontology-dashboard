import { useMemo, type ReactNode } from "react";
import {
  Background,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
} from "@xyflow/react";
import type { AnalysisFlowEdge, AnalysisFlowNode } from "./types";

interface AnalysisLineageMiniGraphProps {
  nodes: AnalysisFlowNode[];
  edges: AnalysisFlowEdge[];
  selectedNodeId: string;
  modelVersion: string;
  revision: number;
}

interface LineageNodeData extends Record<string, unknown> {
  label: ReactNode;
}

function upstreamNodeIds(edges: AnalysisFlowEdge[], selectedNodeId: string) {
  const visible = new Set([selectedNodeId]);
  const queue = [selectedNodeId];
  while (queue.length) {
    const target = queue.shift()!;
    for (const edge of edges) {
      if (edge.target !== target || visible.has(edge.source)) continue;
      visible.add(edge.source);
      queue.push(edge.source);
    }
  }
  return visible;
}

function AnalysisLineageMiniGraphInner({
  nodes,
  edges,
  selectedNodeId,
  modelVersion,
  revision,
}: AnalysisLineageMiniGraphProps) {
  const graph = useMemo(() => {
    const visibleIds = upstreamNodeIds(edges, selectedNodeId);
    const visibleNodes = nodes.filter((node) => visibleIds.has(node.id));
    const minimumX = Math.min(...visibleNodes.map((node) => node.position.x), 0);
    const minimumY = Math.min(...visibleNodes.map((node) => node.position.y), 0);
    const scale = 0.42;
    const miniNodes: Array<Node<LineageNodeData>> = visibleNodes.map((node) => ({
      id: node.id,
      position: {
        x: (node.position.x - minimumX) * scale,
        y: (node.position.y - minimumY) * scale,
      },
      data: {
        label: (
          <div className="analysis-lineage-node-copy">
            <strong>{node.data.title}</strong>
            <span>{node.data.kind} · {node.data.rows} rows</span>
          </div>
        ),
      },
      className: `analysis-lineage-node status-${node.data.status}${node.id === selectedNodeId ? " selected" : ""}`,
      selected: node.id === selectedNodeId,
      draggable: false,
      connectable: false,
      selectable: false,
    }));
    const miniEdges: Edge[] = edges
      .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
      .map((edge) => ({
        ...edge,
        animated: edge.target === selectedNodeId,
        selectable: false,
        focusable: false,
      }));
    return { nodes: miniNodes, edges: miniEdges };
  }, [edges, nodes, selectedNodeId]);

  return (
    <section className="analysis-lineage-mini" aria-label="Selected node upstream lineage">
      <header>
        <h3>Lineage</h3>
        <span>{graph.nodes.length} nodes · {graph.edges.length} edges</span>
      </header>
      <div className="analysis-lineage-mini-canvas">
        <ReactFlow
          nodes={graph.nodes}
          edges={graph.edges}
          fitView
          fitViewOptions={{ padding: 0.22, maxZoom: 1.1 }}
          minZoom={0.35}
          maxZoom={1.4}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={14} size={1} />
        </ReactFlow>
      </div>
      <div className="analysis-lineage-meta">
        <span>Selected · {selectedNodeId}</span>
        <span>Model · {modelVersion}</span>
        <span>Analysis v{revision}</span>
      </div>
    </section>
  );
}

export function AnalysisLineageMiniGraph(props: AnalysisLineageMiniGraphProps) {
  return (
    <ReactFlowProvider>
      <AnalysisLineageMiniGraphInner {...props} />
    </ReactFlowProvider>
  );
}
