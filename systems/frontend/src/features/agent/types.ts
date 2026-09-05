export type AgentRoute = "relational" | "graph" | "vector" | "hybrid";
export type AgentStatus = "running" | "succeeded" | "failed" | "awaiting_approval";
export type EvidenceStore = "postgresql" | "neo4j" | "pgvector" | "project3_rag";

export interface AgentEvidenceItem {
  evidence_id: string;
  store: EvidenceStore;
  reference: string;
  project_id: string;
  workspace_id: string;
  dataset_version_id: string | null;
  object_id: string | null;
  title: string;
  content: string;
  score: number | null;
  metadata: Record<string, unknown>;
}

export interface GroundedClaim {
  claim_id: string;
  text: string;
  evidence_ids: string[];
  confidence: "high" | "medium" | "low";
  validated: boolean;
}

export interface OrchestrationStep {
  name: string;
  store: EvidenceStore | null;
  status: "succeeded" | "failed" | "skipped";
  latency_ms: number | null;
  detail: string;
}

export interface AgentTraceRecord {
  id: string;
  run_id: string;
  step_name: string;
  store_kind: string | null;
  status: string;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  latency_ms: number | null;
  created_at: string;
}

export interface AgentState {
  run_id: string;
  organization_id: string;
  project_id: string;
  workspace_id: string;
  user_id: string;
  question: string;
  route: AgentRoute;
  status: AgentStatus;
  object_type: string | null;
  object_id: string | null;
  event_id?: string | null;
  evidence: AgentEvidenceItem[];
  claims: GroundedClaim[];
  steps: OrchestrationStep[];
  answer: string;
  caveats: string[];
  error: string | null;
  checkpoint_sequence: number;
  duration_ms?: number | null;
  activity_persistence?: "persisted" | "unavailable";
}

export interface AgentRunSummary {
  run_id: string;
  project_id: string;
  workspace_id: string;
  question: string;
  route: AgentRoute;
  status: AgentStatus;
  object_type?: string | null;
  object_id?: string | null;
  event_id?: string | null;
  evidence_count: number;
  claim_count: number;
  checkpoint_sequence: number;
  created_at: string;
  updated_at: string;
}

export interface AgentRunPage {
  items: AgentRunSummary[];
  offset: number;
  limit: number;
  total: number;
}

export interface AgentRunResponse {
  state: AgentState;
  traces: AgentTraceRecord[];
}

export interface AgentQueryInput {
  project_id: string;
  workspace_id: string;
  question: string;
  route?: "auto" | AgentRoute;
  audience?: "engineering" | "operations" | "executive" | "maintenance";
  object_type?: string;
  object_id?: string;
  event_id?: string;
  top_k?: number;
}
