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
  immutable_versioning: true;
  rollback_supported: boolean;
}

export interface GovernedProductResultSummary {
  artifact_id: string | null;
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
    feature_value: number;
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
  provenance: {
    dataset_id: string;
    dataset_version_id: string;
    source_version: string;
    bundle_checksum_sha256: string;
    model_version: string;
    schema_version: string;
    prediction_task: "binary_failure_within_horizon";
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
