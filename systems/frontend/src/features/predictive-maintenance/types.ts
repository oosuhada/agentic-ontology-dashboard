import type { Evidence, EventSummary, Layout, Report } from "../../types";

export type GraphReplayStatus = "pending" | "indexing" | "ready" | "failed" | "unavailable";

export interface PredictiveMaintenanceRuntimeContext {
  organization_id: string;
  project_id: string;
  workspace_id: string;
  dataset_id: string;
  dataset_version_id: string;
  source_version: string;
  bundle_checksum_sha256: string;
  version_number: number;
  record_count: number;
  dataset_status: string;
  row_counts: Record<string, number>;
  source_contract: Record<string, unknown>;
  model_version: string | null;
  result_artifact_schema_version: string | null;
  prediction_task: "binary_failure_within_horizon" | null;
  relational_status: GraphReplayStatus;
  relational_record_count: number;
  semantic_catalog_version: string;
  governance: {
    release_identity: Record<string, unknown>;
    tool_wear_continuity: Record<string, unknown>;
    agent_example_evaluation: Record<string, unknown>;
    ai4i_physics: Record<string, unknown>;
    ai4i_contract: Record<string, unknown>;
    query_time_derived_measures: Record<string, string>;
    governance_artifacts: Array<Record<string, unknown>>;
    prediction_label_semantics: "generic_binary_risk_not_ai4i_failure_mode";
    release_evidence_is_prediction_label: false;
    maintenance_evidence_accuracy_is_instance_accuracy: false;
  };
  semantic_query: {
    dimensions: string[];
    canonical_measures: string[];
    derived_measures: Record<string, string>;
    latest_result_contract: "result_artifact" | "prediction_snapshot_compatibility";
    replay_prediction_contract: "precomputed_prediction_timeline";
    supported_grains: Array<"raw" | "10m" | "1h">;
    evaluation_truth_queryable: false;
    model_training_available: false;
  };
  graph: {
    status: GraphReplayStatus;
    record_count: number;
    provider_run_id: string | null;
    last_error: string | null;
    attempt_count: number;
    updated_at: string | null;
    required_for_runtime: false;
  };
}

export interface PredictiveMaintenanceDatasetVersionOption {
  dataset_id: string;
  dataset_name: string;
  dataset_version_id: string;
  version_number: number;
  source_version: string;
  bundle_checksum_sha256: string;
  dataset_status: string;
  record_count: number;
  row_counts: Record<string, number>;
  result_artifact_count: number;
  prediction_timeline_count: number;
  relational_status: GraphReplayStatus;
  relational_record_count: number;
  model_version: string | null;
  result_artifact_schema_version: string | null;
  prediction_task: "binary_failure_within_horizon" | null;
  graph: PredictiveMaintenanceRuntimeContext["graph"];
  release_ready: boolean;
  is_latest: boolean;
  is_v3_1: boolean;
}

export interface PredictiveMaintenanceDatasetVersions {
  organization_id: string;
  project_id: string;
  workspace_id: string;
  items: PredictiveMaintenanceDatasetVersionOption[];
  default_dataset_version_id: string | null;
  selection_mode: "automatic" | "explicit";
  selection_reason:
    | "canonical_v3_1_release_ready"
    | "latest_published_predictive_maintenance"
    | "latest_predictive_maintenance"
    | "explicit_user_selection"
    | "no_runtime_dataset";
  immutable_versioning: true;
  rollback_supported: boolean;
}

export interface PredictiveMaintenanceDashboardDataSource {
  dataset_id: string;
  dataset_name: string;
  dataset_version_id: string;
  source_version: string;
  model_version: string | null;
  result_artifact_schema_version: string | null;
  prediction_task: "binary_failure_within_horizon" | null;
  bundle_checksum_sha256: string;
  record_count: number;
  row_counts: Record<string, number>;
  result_artifact_count: number;
  prediction_timeline_count: number;
  relational_status: "pending" | "indexing" | "ready" | "failed" | "unavailable";
  relational_record_count: number;
  dataset_status: string;
  release_ready: boolean;
  selection_mode: "automatic" | "explicit";
  selection_reason: string;
  source_kind: "postgresql_result_artifact";
  graph: PredictiveMaintenanceRuntimeContext["graph"];
}

export interface PredictiveMaintenanceDashboardResponse {
  data_source: PredictiveMaintenanceDashboardDataSource;
  context: PredictiveMaintenanceRuntimeContext;
  versions: PredictiveMaintenanceDatasetVersions;
  events: EventSummary[];
  selected_event_id: string | null;
  selected_event_detail: {
    event_id: string;
    evidence: Evidence;
    report: Report;
    layout: Layout;
    maintenance_events: Array<Record<string, unknown>>;
  } | null;
  fallback_available: true;
  fallback_name: "Hanbit Tech Operations Reference";
  replay_source: "postgresql_prediction_timeline";
}

export interface GovernedProductResultSummary {
  artifact_id: string | null;
  source_contract: "result_artifact" | "prediction_snapshot_compatibility";
  asset_id: string;
  asset_type: "compressor" | "cnc";
  site_id: string;
  cell_id: string;
  observed_at: string;
  prediction_task: "binary_failure_within_horizon";
  failure_probability: number;
  predicted_failure_type: "failure_risk" | "no_significant_risk";
  status_grade: "normal" | "attention" | "warning" | "critical";
  confidence: number;
  top_factors: Array<{
    rank: number;
    feature: string;
    display_name?: string | null;
    feature_value: number;
    unit?: string | null;
    signed_contribution: number;
    direction: "risk_up" | "risk_down";
    explanation_method: string;
  }>;
  recommended_action: {
    action: string;
    priority: string;
    semantic_type: "policy_recommendation";
    approval_state: "not_requested";
    execution_state: "not_executed";
    creates_work_order_automatically: false;
  } | null;
  evidence_summary: {
    available: boolean;
    batch_lineage: {
      batch_id: string | null;
      event_id: string | null;
      emitted_at: string | null;
      generated_at: string | null;
      source_kind: string | null;
      producer_id: string | null;
      model_id: string | null;
      source_reference: string | null;
      simulation_session_id?: string | null;
      overlay_branch_id?: string | null;
      history_segment_id?: string | null;
      maintenance_action_id?: string | null;
      maintenance_event_id?: string | null;
      state_version?: number | null;
    } | null;
    evidence_payload_reference: Record<string, unknown> | null;
    sensor_window_rows: number;
    sensor_window: Record<string, unknown>;
    component_hypotheses: Array<Record<string, unknown>>;
    recommended_actions: Array<{
      action_id: string;
      label: string;
      kind: string;
      requires_human_approval: boolean;
      basis: string[];
    }>;
    source_fields: Array<{
      field_id: string;
      label: string;
      source_path: string;
      description: string | null;
    }>;
    evidence_gaps: Array<{
      gap_id: string;
      field: string;
      owner_domain: string;
      display_policy: string;
      reason: string | null;
      required_source: string | null;
    }>;
  } | null;
  provenance: {
    dataset_id: string;
    dataset_version_id: string;
    source_version: string;
    bundle_checksum_sha256: string;
    model_version: string;
    schema_version: string;
    prediction_task: "binary_failure_within_horizon";
    simulation_session_id?: string | null;
    overlay_branch_id?: string | null;
    history_segment_id?: string | null;
    maintenance_action_id?: string | null;
    maintenance_event_id?: string | null;
    state_version?: number | null;
  };
}

export interface ProductResultPage {
  context: PredictiveMaintenanceRuntimeContext;
  items: GovernedProductResultSummary[];
  total: number;
  latest_product_contract: "result_artifact" | "prediction_snapshot_compatibility";
}

export interface ReplayCursor {
  session_id: string;
  state: "stopped" | "running" | "paused" | "completed";
  sequence: number;
  simulation_time: string;
  wall_clock_observed_at: string;
  source_freshness_at: string;
  speed_minutes_per_second: number;
  progress: number;
  model_retrained: false;
}

export interface ReplaySessionSnapshot {
  context: PredictiveMaintenanceRuntimeContext;
  cursor: ReplayCursor;
  canonical_sensor_time: string;
  nearest_prediction_time: string | null;
  compressor_observations: unknown[];
  cnc_observations: unknown[];
  predictions: unknown[];
  graph: PredictiveMaintenanceRuntimeContext["graph"];
  replay_source: "postgresql_prediction_timeline";
  truth_exposed: false;
  sensor_values_generated: false;
}

export interface PredictiveMaintenanceSensorObservation {
  observed_at: string;
  asset_id: string;
  asset_type: "compressor" | "cnc";
  site_id: string;
  cell_id: string;
  is_operating: boolean;
  operating_state: string;
  measurements: Record<string, number | string | boolean>;
  derived_measures: Record<string, number>;
  source_kind: "canonical_observation";
}

export interface PredictiveMaintenanceObservationResponse {
  context: PredictiveMaintenanceRuntimeContext;
  window_start: string;
  window_end: string;
  grain: "raw" | "10m" | "1h";
  source_rows_mutated: false;
  observations: PredictiveMaintenanceSensorObservation[];
  returned_observation_count: number;
  limit: number;
  truncated: boolean;
}

export interface PredictiveMaintenanceReleaseOverview {
  active: PredictiveMaintenanceRuntimeContext;
  versions: PredictiveMaintenanceDatasetVersions;
  phase_contract: "predictive-maintenance-canonical-v3.1";
  immutable_upgrade_verified: boolean;
  result_artifact_coverage: number;
  projection_status: PredictiveMaintenanceRuntimeContext["graph"];
  safe_release_gates: Record<string, unknown>;
  limitations: string[];
  hidden_truth_exposed: false;
  evaluation_truth_exposed: false;
}
