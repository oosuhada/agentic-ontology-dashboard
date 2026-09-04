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
    pending_approvals: number;
  };
  projections: GovernanceProjection[];
  approvals: GovernanceApproval[];
  lineage: GovernanceLineage[];
  policy_boundaries: string[];
}

export interface ProjectionRetryResult {
  projection: GovernanceProjection;
  message: string;
}
