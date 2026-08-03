import { useMemo } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Connection,
  type EdgeChange,
  type NodeChange,
} from "@xyflow/react";
import type { DashboardChartOption } from "../dashboard/EChartCanvas";
import { EChartCanvas } from "../dashboard/EChartCanvas";
import { AnalysisBoardCard } from "./AnalysisBoardCard";
import type { AnalysisFlowEdge, AnalysisFlowNode, AnalysisResult } from "./types";

const NODE_TYPES = { analysisStep: AnalysisBoardCard };

interface AnalysisPathCanvasProps {
  workspaceId: string;
  nodes: AnalysisFlowNode[];
  edges: AnalysisFlowEdge[];
  result: AnalysisResult;
  onNodesChange: (changes: NodeChange<AnalysisFlowNode>[]) => void;
  onEdgesChange: (changes: EdgeChange<AnalysisFlowEdge>[]) => void;
  onConnect: (connection: Connection) => void;
  onSelectNode: (nodeId: string) => void;
}

export function AnalysisPathCanvas({
  workspaceId,
  nodes,
  edges,
  result,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onSelectNode,
}: AnalysisPathCanvasProps) {
  const option = useMemo<DashboardChartOption>(() => ({
    backgroundColor: "transparent",
    grid: { top: 18, right: 14, bottom: 30, left: 42 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: result.grouped.map((group) => group.key), axisLabel: { color: "#738091", fontSize: 9 } },
    yAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%", color: "#738091", fontSize: 9 }, splitLine: { lineStyle: { color: "#e5e9ef" } } },
    series: [{ type: "bar", data: result.grouped.map((group) => Number((group.averageRisk * 100).toFixed(2))), itemStyle: { color: "#2d72d2", borderRadius: [4, 4, 0, 0] }, barMaxWidth: 38 }],
  }), [result.grouped]);

  return (
    <main className="analysis-flow-canvas">
      <div className="analysis-flow-graph">
        <div className="analysis-path-meta"><span>Workspace · {workspaceId}</span><span>Timezone · Asia/Seoul</span><span>Source · risk_event objects</span><span>{nodes.length} nodes · {edges.length} edges</span></div>
        <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={(_, node) => onSelectNode(node.id)}
        fitView
        minZoom={0.25}
        maxZoom={1.5}
        snapToGrid
        snapGrid={[15, 15]}
        deleteKeyCode={null}
        >
          <Background gap={18} size={1} /><MiniMap pannable zoomable nodeStrokeWidth={3} /><Controls />
        </ReactFlow>
      </div>
      <section className="analysis-flow-preview">
        <header><div><span className="section-label">RESULT PREVIEW</span><strong>Risk by production line</strong></div><div><span>{result.rows.length} rows</span><span>{result.grouped.length} groups</span><span>{(result.averageRisk * 100).toFixed(1)}% avg risk</span></div></header>
        <EChartCanvas option={option} ariaLabel="Analysis result chart" className="analysis-result-echart" />
      </section>
    </main>
  );
}
