export type MetricSet = {
  average_precision: number | null;
  roc_auc: number | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  brier_score: number | null;
  positive_prediction_rate: number | null;
  confusion_matrix: number[][] | null;
  sample_count: number;
  positive_count: number;
  positive_rate: number;
  unavailable_reason: string | null;
};

export type CandidateResult = {
  candidate_id: string;
  algorithm: string;
  status: string;
  selected: boolean;
  validation_metrics: MetricSet | null;
  held_out_test_metrics: MetricSet | null;
  dependency_version: string | null;
  error_reason: string | null;
};

export type ExperimentRun = {
  experiment_id: string;
  status: string;
  progress: number;
  dataset_version_id: string;
  mapping_set_id: string;
  recipe_set_id: string;
  feature_dataset_version_id: string;
  label_policy_id: string;
  selected_candidate_id: string | null;
  threshold_policy_id: string | null;
  split_policy: Record<string, unknown>;
  candidates: CandidateResult[];
  created_at: string;
  updated_at: string;
};

export type ModelVersion = {
  model_version_id: string;
  experiment_id: string;
  algorithm: string;
  prediction_task: string;
  status: string;
  dataset_version_id: string;
  mapping_set_id: string;
  recipe_set_id: string;
  feature_dataset_version_id: string;
  label_policy_id: string;
  input_features: string[];
  input_schema_checksum_sha256: string;
  confidence_status: string;
  threshold_policy: {
    selected_operational_threshold: number;
    recall_constrained_threshold: number;
    cost_minimizing_threshold: number;
    recall_target: number;
  };
  artifact: { uri: string; checksum_sha256: string };
  revision: number;
};

export type ReleaseRequest = {
  release_request_id: string;
  model_version_id: string;
  status: string;
  requested_by: string;
  request_rationale: string;
  decided_by: string | null;
  decision_rationale: string | null;
  revision: number;
};

export type WorkbenchPayload = {
  schema_version: string;
  scope: { organization_id: string; project_id: string; workspace_id: string };
  capabilities: {
    artifact_store: { status: string; reason: string | null };
    experiment_execution: string;
    worker_health: {
      status: string;
      reason: string | null;
      running_count: number;
      queued_count: number;
    };
    synchronous_training_endpoint: boolean;
  };
  readiness: {
    status: string;
    steps: Array<{ step: string; status: string; identity: string | null }>;
    missing_prerequisites: string[];
  };
  experiments: ExperimentRun[];
  selected_experiment_id: string | null;
  leaderboard: CandidateResult[];
  report: {
    status: string;
    reason: string | null;
    split: Record<string, unknown> | null;
    threshold_policy: Record<string, unknown> | null;
    threshold_curve: Array<Record<string, number>>;
    precision_recall_curve: Array<Record<string, number>>;
    roc_curve: Array<Record<string, number>>;
    calibration: Array<Record<string, number>>;
    slice_metrics: Array<Record<string, unknown>>;
    runtime_versions: Record<string, string> | null;
    lineage: Record<string, string> | null;
    limitations: string[];
    validation_used_for_selection: boolean | null;
    test_used_for_selection: boolean | null;
  };
  models: ModelVersion[];
  active_models: ModelVersion[];
  release_requests: ReleaseRequest[];
  lineage_detail: {
    mapping_set: Record<string, unknown> | null;
    feature_recipe_set: Record<string, unknown> | null;
    feature_dataset_version: Record<string, unknown> | null;
  };
  global_feature_importance: {
    status: string;
    reason: string;
    items: Array<Record<string, unknown>>;
  };
  operational_monitoring: { status: string; reason: string };
  audit_events: Array<Record<string, unknown>>;
  rollback_history: Array<Record<string, unknown>>;
  empty: boolean;
};

export type ExplanationArtifact = {
  explanation_id: string;
  provider: string;
  provider_version: string;
  status: string;
  causal_proof: false;
  unavailable_reason: string | null;
  top_factors: Array<{
    rank: number;
    feature: string;
    observed_value: unknown;
    direction: string;
    contribution: number;
    contribution_kind: "local_contribution";
  }>;
};
