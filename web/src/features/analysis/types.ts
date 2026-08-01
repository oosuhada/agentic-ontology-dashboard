import type { Edge, Node } from "@xyflow/react";

export type AnalysisStepKind = "input" | "filter" | "group" | "aggregate" | "formula" | "join" | "chart" | "table" | "evidence";
export type ExecutionStatus = "idle" | "running" | "success" | "error";

export interface AnalysisNodeData extends Record<string, unknown> {
  kind: AnalysisStepKind;
  title: string;
  config: Record<string, string>;
  rows: number;
  outputKind: string;
  elapsedMs: number;
  status: ExecutionStatus;
}

export type AnalysisFlowNode = Node<AnalysisNodeData, "analysisStep">;
export type AnalysisFlowEdge = Edge;

export interface AnalysisRow {
  event_id: string;
  equipment: string;
  equipment_id: string;
  line: string;
  status: string;
  risk: number;
  downtime: number;
  failure_type: string;
  confidence: string;
  priority_score: number;
}

export interface AnalysisGroupResult {
  key: string;
  count: number;
  averageRisk: number;
  downtime: number;
}

export interface AnalysisResult {
  rows: AnalysisRow[];
  grouped: AnalysisGroupResult[];
  averageRisk: number;
  totalDowntime: number;
}

export interface AnalysisBoardDefinition {
  kind: Exclude<AnalysisStepKind, "input">;
  title: string;
  description: string;
  input: string;
  output: string;
}

export interface AddAnalysisBoardRequest {
  analysisId: string;
  nodeId: string;
  title: string;
  version: number;
  versionPolicy: "pinned" | "latest_published";
}

export interface AnalysisServerSnapshot {
  id: string;
  organization_id: string;
  project_id: string;
  workspace_id: string;
  display_name: string;
  status: "draft" | "published" | "archived";
  current_version: number;
  published_version: number | null;
  nodes: AnalysisFlowNode[];
  edges: AnalysisFlowEdge[];
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AnalysisNodeExecutionResult {
  status: "succeeded" | "failed" | "blocked";
  kind: AnalysisStepKind;
  title: string;
  rows: Array<Record<string, unknown>>;
  row_count: number;
  columns: Array<{ name: string; value_type: string }>;
  profile: Record<string, { null_count: number; null_rate: number; distinct_count: number }>;
  render_spec: Record<string, unknown>;
  elapsed_ms: number;
  cache_hit: boolean;
  generated_at: string;
  source_freshness_at: string | null;
  timezone: string;
  warnings: string[];
}

export interface AnalysisRunResponse {
  id: string;
  analysis_id: string;
  analysis_version: number;
  organization_id: string;
  project_id: string;
  workspace_id: string;
  requested_by: string;
  status: "queued" | "running" | "succeeded" | "failed";
  parameters: Record<string, unknown>;
  node_results: Record<string, AnalysisNodeExecutionResult>;
  started_at: string;
  finished_at: string | null;
  error: { code: string; message: string } | null;
}

export interface AnalysisNodeResultResponse {
  analysis_id: string;
  analysis_version: number;
  node_id: string;
  version_policy: "pinned" | "latest_published";
  render_spec: Record<string, unknown>;
  result: AnalysisNodeExecutionResult;
  run_id: string;
  generated_at: string;
}
