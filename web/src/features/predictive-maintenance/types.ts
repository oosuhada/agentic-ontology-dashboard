export type GraphReplayStatus = "pending" | "indexing" | "ready" | "failed" | "unavailable";

export interface PredictiveMaintenanceRuntimeContext {
  organization_id: string;
  project_id: string;
  workspace_id: string;
  dataset_id: string;
  dataset_version_id: string;
  source_version: string;
  bundle_checksum_sha256: string;
  record_count: number;
  row_counts: Record<string, number>;
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
    required_for_runtime: false;
  };
}

export interface GovernedProductResultSummary {
  artifact_id: string | null;
  asset_id: string;
  asset_type: "compressor" | "cnc";
  observed_at: string;
  prediction_task: "binary_failure_within_horizon";
  failure_probability: number;
  predicted_failure_type: "failure_risk" | "no_significant_risk";
  status_grade: "normal" | "attention" | "warning" | "critical";
  recommended_action: {
    action: string;
    priority: string;
    semantic_type: "policy_recommendation";
    approval_state: "not_requested";
    execution_state: "not_executed";
    creates_work_order_automatically: false;
  } | null;
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
