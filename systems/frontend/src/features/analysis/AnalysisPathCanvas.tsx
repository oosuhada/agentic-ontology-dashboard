import { useMemo } from "react";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  ReactFlow,
  getSmoothStepPath,
  useViewport,
  type Connection,
  type EdgeChange,
  type EdgeProps,
  type NodeChange,
} from "@xyflow/react";
import { Plus } from "lucide-react";
import { ChartPanel } from "../../ui/foundry/ChartPanel";
import { CHART_NEUTRAL, CHART_SERIES } from "../../ui/foundry/chartPalette";
import { StatusPill } from "../../ui/foundry/StatusPill";
import type { DashboardChartOption } from "../dashboard/EChartCanvas";
import { EChartCanvas } from "../dashboard/EChartCanvas";
import { AnalysisBoardCard } from "./AnalysisBoardCard";
import type { AnalysisFlowEdge, AnalysisFlowNode, AnalysisResult } from "./types";

const NODE_TYPES = { analysisStep: AnalysisBoardCard };

interface InsertEdgeData extends Record<string, unknown> {
  onInsert?: () => void;
  contract?: string;
  semantic?: "filter" | "join" | "transform";
}

function AnalysisInsertEdge(props: EdgeProps) {
  const [edgePath, labelX, labelY] = getSmoothStepPath(props);
  const { zoom } = useViewport();
  const data = props.data as InsertEdgeData | undefined;
  const inverseScale = 1 / Math.max(zoom, 0.35);
  return (
    <>
      <BaseEdge path={edgePath} markerEnd={props.markerEnd} style={props.style} />
      <EdgeLabelRenderer>
        <div className={`analysis-edge-label semantic-${data?.semantic ?? "transform"} nodrag nopan`} style={{ transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px) scale(${inverseScale})` }}>
          <span>{data?.contract ?? "rows<T>"}</span>
          <button type="button" title="Add board after current step" aria-label="Add board after current step" onClick={(event) => { event.stopPropagation(); data?.onInsert?.(); }}><Plus size={11} /></button>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

const EDGE_TYPES = { analysisInsert: AnalysisInsertEdge };

interface AnalysisPathCanvasProps {
  workspaceId: string;
  nodes: AnalysisFlowNode[];
  edges: AnalysisFlowEdge[];
  result: AnalysisResult;
  running?: boolean;
  runProgress?: number;
  onNodesChange: (changes: NodeChange<AnalysisFlowNode>[]) => void;
  onEdgesChange: (changes: EdgeChange<AnalysisFlowEdge>[]) => void;
  onConnect: (connection: Connection) => void;
  onSelectNode: (nodeId: string) => void;
  onInsertStep: () => void;
}

export function AnalysisPathCanvas({
  workspaceId,
  nodes,
  edges,
  result,
  running = false,
  runProgress = 0,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onSelectNode,
  onInsertStep,
}: AnalysisPathCanvasProps) {
  const option = useMemo<DashboardChartOption>(() => ({
    backgroundColor: "transparent",
    grid: { top: 18, right: 14, bottom: 30, left: 42 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: result.grouped.map((group) => group.key), axisLabel: { color: CHART_NEUTRAL.muted, fontSize: 11 } },
    yAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%", color: CHART_NEUTRAL.muted, fontSize: 11 }, splitLine: { lineStyle: { color: CHART_NEUTRAL.border } } },
    series: [{ type: "bar", data: result.grouped.map((group) => Number((group.averageRisk * 100).toFixed(2))), itemStyle: { color: CHART_SERIES[0], borderRadius: [2, 2, 0, 0] }, barMaxWidth: 34 }],
  }), [result.grouped]);

  const verticalNodes = useMemo(
    () => nodes.map((node, index) => ({
      ...node,
      draggable: false,
      position: { x: 90, y: 58 + index * 154 },
    })),
    [nodes],
  );
  const insertEdges = useMemo(
    () => {
      const nodeMap = new Map(nodes.map((node) => [node.id, node]));
      return edges.map((edge) => {
        const source = nodeMap.get(edge.source);
        const target = nodeMap.get(edge.target);
        const semantic = source?.data.kind === "filter" ? "filter" : target?.data.kind === "join" ? "join" : "transform";
        const contract = source?.data.kind === "filter" ? "matched rows" : target?.data.kind === "join" ? "join input" : source?.data.outputKind ?? "rows<T>";
        return {
          ...edge,
          sourceHandle: "output",
          targetHandle: "input",
          type: "analysisInsert",
          animated: false,
          style: { strokeWidth: semantic === "join" ? 2 : 1.2, strokeDasharray: semantic === "filter" ? "4 3" : undefined },
          data: { ...(edge.data ?? {}), onInsert: onInsertStep, contract, semantic },
        };
      });
    },
    [edges, nodes, onInsertStep],
  );

  return (
    <section className="analysis-flow-canvas" aria-label="Analysis path canvas">
      <div className="analysis-flow-graph">
        <div className="analysis-path-meta">
          <span>Workspace · {workspaceId}</span>
          <span>Timezone · Asia/Seoul</span>
          <span>Source · risk_event objects</span>
          <span>{nodes.length} boards · {edges.length} links</span>
        </div>
        {running ? <div className="analysis-run-overlay"><StatusPill intent="primary">RUNNING {runProgress}%</StatusPill><i style={{ width: `${Math.max(2, runProgress)}%` }} /></div> : null}
        <ReactFlow
          id="analysis-path-flow"
          nodes={verticalNodes}
          edges={insertEdges}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, node) => onSelectNode(node.id)}
          fitView
          fitViewOptions={{ padding: 0.18 }}
          minZoom={0.35}
          maxZoom={1.2}
          nodesDraggable={false}
          nodesConnectable={false}
          panOnDrag
          zoomOnDoubleClick={false}
          deleteKeyCode={null}
        >
          <Background gap={18} size={1} />
          <Controls showInteractive={false} />
        </ReactFlow>
        <button type="button" className="analysis-add-output" onClick={onInsertStep}><Plus size={12} /> Add output board</button>
      </div>
      <ChartPanel className="analysis-flow-preview" empty={!result.grouped.length} emptyTitle="No grouped result">
        <header><div><span className="section-label">SELECTED OUTPUT</span><strong>Risk by production line</strong></div><div><span>{result.rows.length} rows</span><span>{result.grouped.length} groups</span><span>{(result.averageRisk * 100).toFixed(1)}% avg risk</span></div></header>
        <EChartCanvas option={option} ariaLabel="Analysis result chart" className="analysis-result-echart" />
      </ChartPanel>
    </section>
  );
}
