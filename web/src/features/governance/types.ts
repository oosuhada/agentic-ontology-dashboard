import type { AgentEvidenceItem } from "../agent/types";

export interface GovernanceProjection {
  id: string;
  dataset_id: string;
  dataset_name: string;
  dataset_version_id: string;
  version_label: string;
  store_kind: "relational" | "graph" | "vector";
  status: string;
  source_version: string;
  object_namespace: string;
  record_count: number;
  attempt_count: number;
  last_error: string | null;
  updated_at: string;
  can_retry: boolean;
}

export interface GovernanceAgentRun {
  run_id: string;
  workspace_id: string;
  question: string;
  route: string;
  status: string;
  evidence_count: number;
  claim_count: number;
  checkpoint_sequence: number;
  caveats: string[];
  error: string | null;
}

export interface GovernanceApproval {
  id: string;
  workflow_type: string;
  workspace_id: string;
  target_role: string | null;
  requested_by: string;
  requested_by_name: string;
  status: string;
  payload: Record<string, unknown>;
  created_at: string;
  decision_by_name: string | null;
  decision_note: string | null;
}

export interface GovernanceLineage {
  dataset_id: string;
  dataset_name: string;
  latest_version_id: string | null;
  latest_source_version: string | null;
  version_count: number;
  materialization_count: number;
  downstream_references: string[];
}

export interface GovernanceOverview {
  generated_at: string;
  access: {
    organization_id: string;
    project_id: string;
    workspace_id: string;
    user_id: string;
    roles: string[];
    permissions: string[];
    can_retry_projection: boolean;
    tenant_admin_controls_excluded: boolean;
  };
  counts: {
    datasets: number;
    dataset_versions: number;
    materializations: number;
    projections: number;
    failed_projections: number;
    pending_projections: number;
    agent_runs: number;
    failed_agent_runs: number;
    pending_approvals: number;
  };
  projections: GovernanceProjection[];
  agent_runs: GovernanceAgentRun[];
  approvals: GovernanceApproval[];
  lineage: GovernanceLineage[];
  policy_boundaries: string[];
}

export interface GovernanceAgentRunDetail {
  state: {
    run_id: string;
    project_id: string;
    workspace_id: string;
    question: string;
    route: string;
    status: string;
    evidence: AgentEvidenceItem[];
    claims: Array<{
      claim_id: string;
      text: string;
      evidence_ids: string[];
      confidence: string;
      validated: boolean;
    }>;
    answer: string;
    caveats: string[];
    error: string | null;
    checkpoint_sequence: number;
  };
  traces: Array<{
    id: string;
    run_id: string;
    step_name: string;
    store_kind: string | null;
    status: string;
    input: Record<string, unknown>;
    output: Record<string, unknown>;
    latency_ms: number | null;
    created_at: string;
  }>;
  checkpoints: Array<{
    id: string;
    run_id: string;
    workspace_id: string;
    sequence: number;
    node_name: string;
    state: Record<string, unknown>;
    created_at: string;
  }>;
}

export interface ProjectionRetryResult {
  projection: GovernanceProjection;
  message: string;
}
