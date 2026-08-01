import { useCallback, useEffect, useMemo, useState } from "react";
import {
  addEdge,
  MarkerType,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Connection,
  type EdgeChange,
  type NodeChange,
} from "@xyflow/react";
import {
  ApiError,
  createAnalysis,
  getAnalysis,
  runAnalysis,
  updateAnalysis,
} from "../../api";
import type { Evidence, EventSummary } from "../../types";
import { AnalysisBoardRail } from "./AnalysisBoardRail";
import { AnalysisPathCanvas } from "./AnalysisPathCanvas";
import { AnalysisResultInspector } from "./AnalysisResultInspector";
import { AnalysisShell } from "./AnalysisShell";
import { ANALYSIS_BOARD_LIBRARY, defaultAnalysisConfig, outputKind } from "./catalog";
import type {
  AddAnalysisBoardRequest,
  AnalysisFlowEdge,
  AnalysisFlowNode,
  AnalysisNodeExecutionResult,
  AnalysisResult,
  AnalysisRow,
  AnalysisServerSnapshot,
  AnalysisStepKind,
} from "./types";

export interface AnalysisPageProps {
  analysisId: string;
  events: EventSummary[];
  selectedEventId: string;
  evidence: Evidence | null;
  workspaceId: string;
  onSelectEvent: (eventId: string) => void;
  onAddToDashboard?: (request: AddAnalysisBoardRequest) => void;
}

function risk(event: EventSummary) {
  return event.failure_probability ?? 0;
}

function initialNodes(eventCount: number): AnalysisFlowNode[] {
  const definitions: Array<[AnalysisStepKind, string]> = [
    ["input", "Risk Event objects"],
    ["filter", "Critical event filter"],
    ["aggregate", "Portfolio metrics"],
    ["chart", "Risk by production line"],
  ];
  return definitions.map(([kind, title], index) => ({
    id: `${kind}:${index}`,
    type: "analysisStep",
    position: { x: 180 + (index % 2) * 330, y: 40 + index * 145 },
    data: {
      kind,
      title,
      config: defaultAnalysisConfig(kind),
      rows: eventCount,
      outputKind: outputKind(kind),
      elapsedMs: 0,
      status: "idle",
    },
  }));
}

function initialEdges(): AnalysisFlowEdge[] {
  return [
    ["input:0", "filter:1"],
    ["filter:1", "aggregate:2"],
    ["aggregate:2", "chart:3"],
  ].map(([source, target], index) => ({
    id: `edge:${index}`,
    source,
    target,
    type: "smoothstep",
    animated: true,
    markerEnd: { type: MarkerType.ArrowClosed },
  }));
}

function fieldValue(row: AnalysisRow, field: string): string | number {
  if (field in row) return row[field as keyof AnalysisRow];
  return "";
}

function applyFilter(rows: AnalysisRow[], config: Record<string, string>) {
  const field = config.field ?? "status";
  const operator = config.operator ?? "equals";
  const value = config.value ?? "critical";
  return rows.filter((row) => {
    const current = fieldValue(row, field);
    if (operator === "not_equals") return String(current) !== value;
    if (operator === "greater_than") return Number(current) > Number(value);
    if (operator === "less_than") return Number(current) < Number(value);
    if (operator === "contains") return String(current).toLowerCase().includes(value.toLowerCase());
    return String(current) === value;
  });
}

/** Fast local preview only. Authoritative execution is performed by /api/analyses/{id}/run. */
function evaluate(events: EventSummary[], nodes: AnalysisFlowNode[]): AnalysisResult {
  let rows: AnalysisRow[] = events.map((event) => ({
    event_id: event.event_id,
    equipment: event.equipment.display_name,
    equipment_id: event.equipment.equipment_id,
    line: event.equipment.line,
    status: event.status,
    risk: risk(event),
    downtime: event.equipment.estimated_downtime_minutes,
    failure_type: event.predicted_failure_type,
    confidence: event.confidence,
    priority_score: risk(event) * event.equipment.estimated_downtime_minutes,
  }));
  for (const node of nodes) {
    if (node.data.kind === "filter") rows = applyFilter(rows, node.data.config);
    if (node.data.kind === "formula") {
      const left = node.data.config.left ?? "risk";
      const right = node.data.config.right ?? "downtime";
      const operator = node.data.config.operator ?? "multiply";
      rows = rows.map((row) => {
        const leftValue = Number(fieldValue(row, left));
        const rightValue = Number(fieldValue(row, right));
        const priority = operator === "add"
          ? leftValue + rightValue
          : operator === "subtract"
            ? leftValue - rightValue
            : operator === "divide"
              ? leftValue / Math.max(1, rightValue)
              : leftValue * rightValue;
        return { ...row, priority_score: priority };
      });
    }
  }
  const grouped = Object.entries(rows.reduce<Record<string, { count: number; risk: number; downtime: number }>>((acc, row) => {
    const key = row.line || "unknown";
    const current = acc[key] ?? { count: 0, risk: 0, downtime: 0 };
    acc[key] = {
      count: current.count + 1,
      risk: current.risk + row.risk,
      downtime: current.downtime + row.downtime,
    };
    return acc;
  }, {})).map(([key, value]) => ({
    key,
    count: value.count,
    averageRisk: value.risk / value.count,
    downtime: value.downtime,
  }));
  return {
    rows,
    grouped,
    averageRisk: rows.length ? rows.reduce((sum, row) => sum + row.risk, 0) / rows.length : 0,
    totalDowntime: rows.reduce((sum, row) => sum + row.downtime, 0),
  };
}

function AnalysisPageInner({
  analysisId,
  events,
  selectedEventId,
  evidence,
  workspaceId,
  onSelectEvent,
  onAddToDashboard,
}: AnalysisPageProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<AnalysisFlowNode>(initialNodes(events.length));
  const [edges, setEdges, onEdgesChange] = useEdgesState<AnalysisFlowEdge>(initialEdges());
  const [selectedNodeId, setSelectedNodeId] = useState("filter:1");
  const [revision, setRevision] = useState(1);
  const [serverSnapshot, setServerSnapshot] = useState<AnalysisServerSnapshot | null>(null);
  const [serverResults, setServerResults] = useState<Record<string, AnalysisNodeExecutionResult>>({});
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("Analysis definition을 서버에서 불러오는 중입니다.");
  const [showInspector, setShowInspector] = useState(true);
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0];
  const result = useMemo(() => evaluate(events, nodes), [events, nodes]);

  useEffect(() => {
    let active = true;
    const seedNodes = initialNodes(events.length);
    const seedEdges = initialEdges();
    setBusy(true);
    getAnalysis(analysisId, workspaceId)
      .then((snapshot) => {
        if (!active) return;
        setServerSnapshot(snapshot);
        setRevision(snapshot.current_version);
        setNodes(snapshot.nodes);
        setEdges(snapshot.edges);
        setSelectedNodeId(snapshot.nodes[0]?.id ?? "");
        setDirty(false);
        setNotice(`Server Analysis v${snapshot.current_version} · ${snapshot.status}`);
      })
      .catch(async (error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 404) {
          try {
            const snapshot = await createAnalysis({
              id: analysisId,
              workspace_id: workspaceId,
              display_name: analysisId.replaceAll("-", " "),
              nodes: seedNodes,
              edges: seedEdges,
            });
            if (!active) return;
            setServerSnapshot(snapshot);
            setRevision(snapshot.current_version);
            setNodes(snapshot.nodes);
            setEdges(snapshot.edges);
            setDirty(false);
            setNotice("Analysis definition을 서버에 생성했습니다.");
            return;
          } catch (createError) {
            if (!active) return;
            setNotice(`서버 Analysis 생성 실패 · 로컬 preview fallback: ${createError instanceof Error ? createError.message : String(createError)}`);
            setDirty(true);
            return;
          }
        }
        setNotice(`서버 Analysis 조회 실패 · 로컬 preview fallback: ${error instanceof Error ? error.message : String(error)}`);
        setDirty(true);
      })
      .finally(() => active && setBusy(false));
    return () => { active = false; };
  }, [analysisId, events.length, setEdges, setNodes, workspaceId]);

  const onConnect = useCallback((connection: Connection) => {
    setEdges((current) => addEdge({
      ...connection,
      type: "smoothstep",
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
    }, current));
    setDirty(true);
  }, [setEdges]);

  const handleNodesChange = useCallback((changes: NodeChange<AnalysisFlowNode>[]) => {
    onNodesChange(changes);
    if (changes.some((change) => change.type !== "select")) setDirty(true);
  }, [onNodesChange]);

  const handleEdgesChange = useCallback((changes: EdgeChange<AnalysisFlowEdge>[]) => {
    onEdgesChange(changes);
    if (changes.some((change) => change.type !== "select")) setDirty(true);
  }, [onEdgesChange]);

  function addStep(kind: Exclude<AnalysisStepKind, "input">) {
    const definition = ANALYSIS_BOARD_LIBRARY.find((item) => item.kind === kind)!;
    const id = `${kind}:${crypto.randomUUID()}`;
    const last = nodes[nodes.length - 1];
    const next: AnalysisFlowNode = {
      id,
      type: "analysisStep",
      position: {
        x: last ? last.position.x + (nodes.length % 2 ? 300 : -300) : 180,
        y: last ? last.position.y + 150 : 40,
      },
      data: {
        kind,
        title: definition.title,
        config: defaultAnalysisConfig(kind),
        rows: result.rows.length,
        outputKind: outputKind(kind),
        elapsedMs: 0,
        status: "idle",
      },
    };
    setNodes((current) => [...current, next]);
    if (last) {
      setEdges((current) => [...current, {
        id: `edge:${last.id}:${id}`,
        source: last.id,
        target: id,
        type: "smoothstep",
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed },
      }]);
    }
    setSelectedNodeId(id);
    setDirty(true);
    setNotice(`${definition.title} node를 경로에 추가했습니다.`);
  }

  function updateConfig(key: string, value: string) {
    setNodes((current) => current.map((node) => node.id === selectedNodeId
      ? {
          ...node,
          data: {
            ...node.data,
            config: { ...node.data.config, [key]: value },
            status: "idle",
          },
        }
      : node));
    setDirty(true);
  }

  function deleteNode() {
    if (!selectedNode || selectedNode.data.kind === "input") return;
    setNodes((current) => current.filter((node) => node.id !== selectedNode.id));
    setEdges((current) => current.filter((edge) => edge.source !== selectedNode.id && edge.target !== selectedNode.id));
    setSelectedNodeId("input:0");
    setDirty(true);
    setNotice("선택 node와 연결 edge를 제거했습니다.");
  }

  async function ensureSaved(publish: boolean): Promise<AnalysisServerSnapshot> {
    if (!serverSnapshot) {
      const created = await createAnalysis({
        id: analysisId,
        workspace_id: workspaceId,
        display_name: analysisId.replaceAll("-", " "),
        nodes,
        edges,
        publish,
      });
      setServerSnapshot(created);
      setRevision(created.current_version);
      setDirty(false);
      return created;
    }
    const requiresWrite = dirty || (publish && serverSnapshot.published_version !== serverSnapshot.current_version);
    if (!requiresWrite) return serverSnapshot;
    const updated = await updateAnalysis(analysisId, {
      workspace_id: workspaceId,
      display_name: serverSnapshot.display_name,
      nodes,
      edges,
      base_version: serverSnapshot.current_version,
      publish,
    });
    setServerSnapshot(updated);
    setRevision(updated.current_version);
    setDirty(false);
    return updated;
  }

  function applyRunResults(nodeResults: Record<string, AnalysisNodeExecutionResult>) {
    setServerResults(nodeResults);
    setNodes((current) => current.map((node) => {
      const execution = nodeResults[node.id];
      if (!execution) return { ...node, data: { ...node.data, status: "error" } };
      return {
        ...node,
        data: {
          ...node.data,
          status: execution.status === "succeeded" ? "success" : "error",
          rows: execution.row_count,
          elapsedMs: execution.elapsed_ms,
        },
      };
    }));
  }

  async function run() {
    setBusy(true);
    setNotice(`Server run 준비 · ${nodes.length} nodes`);
    setNodes((current) => current.map((node) => ({ ...node, data: { ...node.data, status: "running" } })));
    try {
      const saved = await ensureSaved(false);
      const response = await runAnalysis(analysisId, {
        workspace_id: workspaceId,
        version_policy: "pinned",
        version: saved.current_version,
        preview_limit: 500,
      });
      if (response.status !== "succeeded") throw new Error(response.error?.message ?? "Analysis run failed");
      applyRunResults(response.node_results);
      setNotice(`Run ${response.id} succeeded · Analysis v${response.analysis_version} · server execution`);
    } catch (error) {
      setNodes((current) => current.map((node, index) => ({
        ...node,
        data: {
          ...node.data,
          status: "success",
          rows: node.data.kind === "input" ? events.length : result.rows.length,
          elapsedMs: 14 + index * 11,
        },
      })));
      setNotice(`서버 실행 실패 · client fallback 적용: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function saveDataset() {
    setBusy(true);
    try {
      const saved = await ensureSaved(true);
      const response = await runAnalysis(analysisId, {
        workspace_id: workspaceId,
        version_policy: "pinned",
        version: saved.current_version,
        preview_limit: 1000,
      });
      if (response.status !== "succeeded") throw new Error(response.error?.message ?? "Analysis materialization failed");
      applyRunResults(response.node_results);
      setNotice(`Analysis v${saved.current_version} published · server dataset snapshot ${response.id}`);
    } catch (error) {
      setNotice(`서버 저장 실패: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setBusy(false);
    }
  }

  function addToDashboard() {
    if (!selectedNode || !onAddToDashboard) return;
    onAddToDashboard({
      analysisId,
      nodeId: selectedNode.id,
      title: `${selectedNode.data.title} · ${analysisId}`,
      version: serverSnapshot?.current_version ?? revision,
      versionPolicy: "pinned",
    });
    setNotice(`${selectedNode.data.title}을 현재 Dashboard에 pinned reference로 추가했습니다.`);
  }

  return (
    <AnalysisShell
      analysisId={analysisId}
      revision={revision}
      notice={busy ? `Working · ${notice}` : notice}
      showInspector={showInspector}
      canAddToDashboard={Boolean(selectedNode && onAddToDashboard)}
      onRun={run}
      onSaveDataset={saveDataset}
      onAddToDashboard={addToDashboard}
      onToggleInspector={() => setShowInspector((current) => !current)}
      rail={<AnalysisBoardRail onAddStep={addStep} />}
      canvas={(
        <AnalysisPathCanvas
          workspaceId={workspaceId}
          nodes={nodes}
          edges={edges}
          result={result}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onConnect={onConnect}
          onSelectNode={setSelectedNodeId}
        />
      )}
      inspector={(
        <AnalysisResultInspector
          node={selectedNode}
          result={result}
          serverResult={selectedNode ? serverResults[selectedNode.id] : undefined}
          workspaceId={workspaceId}
          selectedEventId={selectedEventId}
          evidence={evidence}
          revision={revision}
          onConfigChange={updateConfig}
          onDeleteNode={deleteNode}
          onSelectEvent={onSelectEvent}
        />
      )}
    />
  );
}

export function AnalysisPage(props: AnalysisPageProps) {
  return <ReactFlowProvider><AnalysisPageInner {...props} /></ReactFlowProvider>;
}
