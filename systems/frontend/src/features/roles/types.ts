export interface ExecutiveOverview {
  workspace_id: string;
  generated_at: string;
  aggregate: {
    equipment_count: number;
    event_count: number;
    affected_event_count: number;
    unresolved_critical_count: number;
    average_failure_probability: number | null;
    estimated_downtime_minutes: number;
  };
  status_distribution: Array<{ status: string; count: number }>;
  risk_trend: Array<{
    observed_at: string;
    event_id: string;
    equipment: string;
    status: string;
    risk_score: number | null;
  }>;
  unresolved_critical_events: Array<Record<string, unknown> & {
    event_id: string;
    status: string;
    failure_probability: number | null;
    equipment: {
      equipment_id: string;
      display_name: string;
      line: string;
      estimated_downtime_minutes: number;
    };
  }>;
  business_impact: Record<string, unknown>;
  assumptions: string[];
}

export interface AuditReconstruction {
  workspace_id: string;
  event_id: string;
  reconstructed_at: string;
  input_snapshot: Record<string, unknown>;
  version_snapshot: Record<string, unknown>;
  evidence_to_report_trace: Array<{
    section_id: string;
    title: string;
    evidence_field_ids: string[];
    report_id: string;
  }>;
  action_history: Array<Record<string, unknown>>;
  export_checkpoints: Array<Record<string, unknown> & {
    id: string;
    export_format: string;
    reason: string;
    content_hash: string;
    requested_by_name: string;
    created_at: string;
  }>;
}

export interface FieldTask {
  task_id: string;
  event_id: string;
  equipment: {
    equipment_id: string;
    display_name: string;
    line: string;
    criticality: string;
    assigned_engineer: string;
  };
  risk_status: string;
  task_status: string;
  priority: number;
  location: string;
  safety: string[];
  checklist: string[];
  measurement_schema: Record<string, string>;
  photo_policy: Record<string, unknown>;
  latest_action: Record<string, unknown> | null;
}

export interface FieldTaskWorkspace {
  workspace_id: string;
  generated_at: string;
  tasks: FieldTask[];
  offline_queue_design: Record<string, unknown>;
}

export interface FDEWorkbench {
  workspace_id: string;
  generated_at: string;
  customer_workspace: Record<string, unknown>;
  ontology_registry: {
    object_type_count: number;
    link_type_count: number;
    action_type_count: number;
    object_types: Array<Record<string, unknown>>;
    link_types: Array<Record<string, unknown>>;
    action_types: Array<Record<string, unknown>>;
  };
  integration_health: Array<Record<string, unknown>>;
  deployment_checklist: Array<{ id: string; label: string; status: string }>;
  diagnostic_events: Array<Record<string, unknown>>;
  template_requests: WorkflowRequest[];
  security_boundaries: string[];
}

export interface ModelConsole {
  workspace_id: string;
  generated_at: string;
  model_versions: Array<Record<string, unknown>>;
  dataset_versions: Array<Record<string, unknown>>;
  training_metrics: Record<string, unknown>;
  operational_thresholds: Record<string, unknown>;
  threshold_cost: Array<Record<string, unknown>>;
  slices: Array<Record<string, unknown>>;
  drift_and_schema: Array<Record<string, unknown>>;
  gold_regression: {
    scenario_count: number;
    passed: number;
    failed: number;
    pass: boolean;
    items: Array<Record<string, unknown>>;
  };
  release_requests: WorkflowRequest[];
}

export interface WorkflowRequest {
  id: string;
  workflow_type: "template_publish" | "model_release";
  workspace_id: string;
  target_role?: string;
  status: "pending_approval" | "approved" | "rejected";
  requested_by: string;
  requested_by_name: string;
  payload: Record<string, unknown>;
  decision_by: string | null;
  decision_by_name: string | null;
  decision_note: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminWorkflowApprovals {
  template_publish_requests: WorkflowRequest[];
  model_release_requests: WorkflowRequest[];
}

export type RoleWorkspaceData =
  | ExecutiveOverview
  | AuditReconstruction
  | FieldTaskWorkspace
  | FDEWorkbench
  | ModelConsole;
