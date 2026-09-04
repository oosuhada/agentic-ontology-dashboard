import type { Page } from "@playwright/test";

export const SHARE_PROJECT = "manufacturing-demo-project";
export const SHARE_WORKSPACE = "manufacturing-demo";
export const MODELING_ROUTE = `/app/projects/${SHARE_PROJECT}/workspaces/${SHARE_WORKSPACE}/modeling`;

const checksum = "12734b1eec67ae5ccf322221967d5628ba5cf1ecb0401e6daef5c3dd7a855682";

function metric(averagePrecision: number, rocAuc: number) {
  return {
    average_precision: averagePrecision,
    roc_auc: rocAuc,
    precision: 0.72,
    recall: 0.86,
    f1: 0.78,
    brier_score: 0.14,
    positive_prediction_rate: 0.31,
    confusion_matrix: [[51, 6], [3, 18]],
    sample_count: 78,
    positive_count: 21,
    positive_rate: 0.2692,
    unavailable_reason: null,
  };
}

export function adaptiveWorkbenchPayload() {
  return {
    schema_version: "ml-validator-workbench-v1",
    scope: {
      organization_id: "org-ontology-demo",
      project_id: SHARE_PROJECT,
      workspace_id: SHARE_WORKSPACE,
    },
    capabilities: {
      artifact_store: { status: "ready", reason: null },
      experiment_execution: "queued_worker_or_cli",
      worker_health: { status: "idle", reason: null, running_count: 0, queued_count: 0 },
      synchronous_training_endpoint: false,
    },
    readiness: {
      status: "ready",
      steps: [
        { step: "dataset_intake_profile", status: "ready_for_review", identity: "profile-1" },
        { step: "manifest_draft", status: "approved", identity: "manifest-1" },
        { step: "mapping_set", status: "approved", identity: "mapping-1" },
        { step: "feature_recipe_set", status: "approved", identity: "recipe-1" },
        { step: "feature_dataset_version", status: "succeeded", identity: "feature-1" },
      ],
      missing_prerequisites: [],
    },
    experiments: [{
      experiment_id: "experiment-1",
      status: "succeeded",
      progress: 1,
      dataset_version_id: "dsv-1914858a-cc17-57d8-819c-d8a2435fd805",
      mapping_set_id: "mapping-1",
      recipe_set_id: "recipe-1",
      feature_dataset_version_id: "feature-1",
      label_policy_id: "label-1",
      selected_candidate_id: "candidate-logistic",
      threshold_policy_id: "threshold-1",
      split_policy: { mode: "group_chronological", embargo_hours: 1 },
      candidates: [],
      created_at: "2026-08-05T00:00:00Z",
      updated_at: "2026-08-05T00:10:00Z",
    }],
    selected_experiment_id: "experiment-1",
    leaderboard: [
      {
        candidate_id: "candidate-dummy",
        algorithm: "dummy_prior",
        status: "succeeded",
        selected: false,
        dependency_version: "1.9.0",
        error_reason: null,
        validation_metrics: metric(0.2917, 0.5),
        held_out_test_metrics: null,
      },
      {
        candidate_id: "candidate-logistic",
        algorithm: "logistic_regression",
        status: "succeeded",
        selected: true,
        dependency_version: "1.9.0",
        error_reason: null,
        validation_metrics: metric(0.5882, 0.8824),
        held_out_test_metrics: metric(0.5003, 0.8235),
      },
      {
        candidate_id: "candidate-random-forest",
        algorithm: "random_forest",
        status: "succeeded",
        selected: false,
        dependency_version: "1.9.0",
        error_reason: null,
        validation_metrics: metric(0.2917, 0.5),
        held_out_test_metrics: null,
      },
      {
        candidate_id: "candidate-lightgbm",
        algorithm: "lightgbm",
        status: "blocked",
        selected: false,
        dependency_version: null,
        error_reason: "lightgbm is not installed",
        validation_metrics: null,
        held_out_test_metrics: null,
      },
    ],
    report: {
      status: "available",
      reason: null,
      split: { train: 216, validation: 72, test: 72 },
      threshold_policy: {
        selected_operational_threshold: 0.33,
        recall_target: 0.5,
        false_negative_cost: 10,
        false_positive_cost: 1,
      },
      threshold_curve: [
        { threshold: 0.2, precision: 0.5, recall: 1 },
        { threshold: 0.33, precision: 0.63, recall: 0.9524 },
        { threshold: 0.5, precision: 0.72, recall: 0.86 },
        { threshold: 0.7, precision: 0.84, recall: 0.48 },
      ],
      precision_recall_curve: [
        { recall: 1, precision: 0.2917, threshold: 0 },
        { recall: 0.9524, precision: 0.63, threshold: 0.33 },
        { recall: 0.86, precision: 0.72, threshold: 0.5 },
        { recall: 0.5, precision: 0.82, threshold: 0.62 },
      ],
      roc_curve: [
        { false_positive_rate: 0, true_positive_rate: 0, threshold: 1 },
        { false_positive_rate: 0.12, true_positive_rate: 0.86, threshold: 0.5 },
        { false_positive_rate: 1, true_positive_rate: 1, threshold: 0 },
      ],
      calibration: [
        { mean_predicted_probability: 0.12, observed_positive_rate: 0.08 },
        { mean_predicted_probability: 0.38, observed_positive_rate: 0.34 },
        { mean_predicted_probability: 0.72, observed_positive_rate: 0.68 },
      ],
      slice_metrics: [
        { dimension: "equipment_type", value: "CNC", sample_count: 60, suppressed: false, average_precision: 0.61 },
        { dimension: "equipment_type", value: "compressor", sample_count: 12, suppressed: true, reason: "minimum sample" },
      ],
      runtime_versions: { python: "3.14", sklearn: "1.9.0" },
      lineage: {
        dataset_version_id: "dsv-1914858a-cc17-57d8-819c-d8a2435fd805",
        mapping_set_id: "mapping-1",
        recipe_set_id: "recipe-1",
        feature_dataset_version_id: "feature-1",
        label_policy_id: "label-1",
      },
      limitations: ["Synthetic controlled release evidence", "Confidence unavailable without calibration"],
      validation_used_for_selection: true,
      test_used_for_selection: false,
    },
    models: [
      {
        model_version_id: "model-candidate",
        algorithm: "logistic_regression",
        status: "candidate",
        revision: 1,
        experiment_id: "experiment-1",
        candidate_id: "candidate-logistic",
        artifact: { uri: "artifact://model-candidate.joblib", checksum_sha256: "a".repeat(64), media_type: "application/octet-stream", size_bytes: 3066, created_at: "2026-08-05T00:12:00Z", store_capability: "ready" },
        threshold_policy: { selected_operational_threshold: 0.33 },
      },
      {
        model_version_id: "model-approved",
        algorithm: "random_forest",
        status: "approved",
        revision: 3,
        experiment_id: "experiment-0",
        candidate_id: "candidate-rf",
        artifact: { uri: "artifact://model-approved.joblib", checksum_sha256: "b".repeat(64), media_type: "application/octet-stream", size_bytes: 6000, created_at: "2026-08-04T00:12:00Z", store_capability: "ready" },
        threshold_policy: { selected_operational_threshold: 0.41 },
      },
    ],
    active_models: [],
    release_requests: [{
      release_request_id: "release-1",
      model_version_id: "model-candidate",
      status: "pending",
      requester_id: "user-ml",
      rationale: "validation and lineage reviewed",
      revision: 1,
      created_at: "2026-08-05T00:15:00Z",
      decided_at: null,
      approver_id: null,
      approver_rationale: null,
    }],
    lineage_detail: {
      mapping_set: { mapping_set_id: "mapping-1", status: "approved", checksum_sha256: "c".repeat(64) },
      feature_recipe_set: { recipe_set_id: "recipe-1", status: "approved", group_by: "equipment_id", order_by: "observed_at", leakage_policy: "past_and_present_only" },
      feature_dataset_version: { feature_dataset_version_id: "feature-1", status: "succeeded", materialization_checksum_sha256: "d".repeat(64) },
    },
    global_feature_importance: { status: "unavailable", reason: "No governed global importance artifact was produced.", items: [] },
    operational_monitoring: { status: "unavailable", reason: "Operational drift/outcome artifacts are not connected." },
    audit_events: [],
    rollback_history: [],
    empty: false,
  };
}

export async function mockAdaptiveModelingApi(page: Page) {
  await page.route("**/api/modeling/workbench**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(adaptiveWorkbenchPayload()) });
  });
  await page.route("**/api/modeling/model-versions/model-candidate/release-requests", async (route) => {
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ release_request_id: "release-2", status: "pending" }) });
  });
  await page.route("**/api/modeling/model-release-requests/release-1/decision", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "approved" }) });
  });
  await page.route("**/api/modeling/model-versions/model-approved/activate", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "active" }) });
  });
}

function runtimeContext() {
  return {
    organization_id: "org-ontology-demo",
    project_id: SHARE_PROJECT,
    workspace_id: SHARE_WORKSPACE,
    dataset_id: "dataset-predictive-maintenance",
    dataset_version_id: "dsv-1914858a-cc17-57d8-819c-d8a2435fd805",
    source_version: "canonical-ai4i-physics-v3.1",
    bundle_checksum_sha256: checksum,
    version_number: 31,
    record_count: 605000,
    dataset_status: "published",
    row_counts: { assets: 100, observations: 432000, prediction_timeline: 68208, result_artifacts: 100 },
    source_contract: { schema_version: "predictive-maintenance-canonical-v3.1" },
    model_version: "independent-logreg-v3.1",
    result_artifact_schema_version: "result-artifact-v1.0",
    prediction_task: "binary_failure_within_horizon",
    relational_status: "ready",
    relational_record_count: 672553,
    semantic_catalog_version: "predictive-maintenance-semantic-v3.1",
    governance: {
      release_identity: { source_version: "canonical-ai4i-physics-v3.1" },
      tool_wear_continuity: { tool_replacement_event_count: 731, aligned_reset_transition_count: 731 },
      agent_example_evaluation: { false_upstream_claim_rate: 0, mean_score: 1 },
      ai4i_physics: { status: "verified" },
      ai4i_contract: { status: "verified" },
      query_time_derived_measures: { power_w: "torque × rpm", temperature_gap_k: "process - ambient", overstrain_load: "torque × tool wear" },
      governance_artifacts: [],
      prediction_label_semantics: "generic_binary_risk_not_ai4i_failure_mode",
      release_evidence_is_prediction_label: false,
      maintenance_evidence_accuracy_is_instance_accuracy: false,
    },
    semantic_query: {
      dimensions: ["asset_id", "site_id", "cell_id"],
      canonical_measures: ["failure_probability", "torque_nm", "rotational_speed_rpm"],
      derived_measures: { power_w: "query_time", temperature_gap_k: "query_time", overstrain_load: "query_time" },
      latest_result_contract: "result_artifact",
      replay_prediction_contract: "precomputed_prediction_timeline",
      supported_grains: ["raw", "10m", "1h"],
      evaluation_truth_queryable: false,
      model_training_available: false,
    },
    graph: { status: "ready", record_count: 2160, provider_run_id: "projection-v3-1", last_error: null, attempt_count: 1, updated_at: "2026-08-05T00:00:00Z", required_for_runtime: false },
  };
}

function productResult(assetId: string, probability: number, status: string, action: string) {
  const artifactId = `artifact-${assetId}`;

  return {
    artifact_id: artifactId,
    source_contract: "result_artifact",
    asset_id: assetId,
    asset_type: assetId.startsWith("CNC") ? "cnc" : "compressor",
    site_id: "SEOUL-01",
    cell_id: assetId.startsWith("CNC") ? "CELL-CNC" : "CELL-COMP",
    observed_at: "2026-08-05T00:00:00Z",
    prediction_task: "binary_failure_within_horizon",
    failure_probability: probability,
    predicted_failure_type: probability >= 0.5 ? "failure_risk" : "no_significant_risk",
    status_grade: status,
    confidence: 0.81,
    top_factors: [
      { rank: 1, feature: "overstrain_load", feature_value: 162.3, signed_contribution: 0.38, direction: "risk_up", explanation_method: "linear_contribution" },
      { rank: 2, feature: "temperature_gap_k", feature_value: 14.8, signed_contribution: 0.17, direction: "risk_up", explanation_method: "linear_contribution" },
    ],
    recommended_action: { action, priority: probability > 0.8 ? "P1" : "P2", semantic_type: "policy_recommendation", approval_state: "not_requested", execution_state: "not_executed", creates_work_order_automatically: false },
    evidence_summary: {
      available: true,
      batch_lineage: {
        batch_id: `batch-${assetId}`,
        event_id: assetId,
        emitted_at: "2026-08-05T00:00:00Z",
        generated_at: "2026-08-05T00:00:00Z",
        source_kind: "maintenance_replay_overlay",
        producer_id: "gen-data-local",
        model_id: "independent-logreg-v3.1",
        source_reference: `prediction-result-batch:batch-${assetId}:event:${assetId}`,
      },
      evidence_payload_reference: {
        source: "product_result_artifact",
        reference: artifactId,
        generated_by: "systems.backend.diagnosis.generator_batch_promotion",
      },
      sensor_window_rows: 0,
      sensor_window: {},
      component_hypotheses: [],
      recommended_actions: [
        {
          action_id: action,
          label: action,
          kind: "backend_policy_recommendation",
          requires_human_approval: true,
          basis: ["prediction_batch.score", "backend_policy.decision_threshold"],
        },
      ],
      source_fields: [
        { field_id: "prediction_batch.score", label: "Generator failure score", source_path: `results[event_id=${assetId}].score`, description: "Raw prediction score emitted by Generator and consumed by Backend policy." },
        { field_id: "prediction_batch.payload_sha256", label: "Prediction payload checksum", source_path: `results[event_id=${assetId}].payload_sha256`, description: "Checksum captured for immutable batch payload evidence." },
        { field_id: "prediction_batch.model_artifact_manifest_sha256", label: "Model artifact manifest checksum", source_path: `results[event_id=${assetId}].model_artifact_manifest_sha256`, description: "Model artifact lineage checksum supplied by Generator." },
        { field_id: "backend_policy.decision_threshold", label: "Backend decision threshold", source_path: "threshold_policy.json", description: "Decision threshold owned by Backend promotion policy." },
      ],
      evidence_gaps: [
        { gap_id: "sensor-window-not-attached", field: "sensor_window", owner_domain: "diagnosis", display_policy: "show_limitation", reason: "Batch result does not include the raw observation window.", required_source: "time-windowed observation rows" },
        { gap_id: "component-hypothesis-not-inferred", field: "component_hypotheses", owner_domain: "diagnosis", display_policy: "show_limitation", reason: "Backend does not infer component causes from prediction score alone.", required_source: "diagnostic component mapping" },
        { gap_id: "maintenance-history-not-joined", field: "maintenance_context", owner_domain: "maintenance", display_policy: "show_limitation", reason: "Maintenance work history is not joined during batch promotion.", required_source: "closed-loop maintenance records" },
      ],
    },
    provenance: { dataset_id: "dataset-predictive-maintenance", dataset_version_id: "dsv-1914858a-cc17-57d8-819c-d8a2435fd805", source_version: "canonical-ai4i-physics-v3.1", bundle_checksum_sha256: checksum, model_version: "independent-logreg-v3.1", schema_version: "result-artifact-v1.0", prediction_task: "binary_failure_within_horizon" },
  };
}

export async function mockPredictiveMaintenanceApi(page: Page) {
  const context = runtimeContext();
  const results = [
    productResult("CNC-014", 0.91, "critical", "Inspect spindle and tool wear"),
    productResult("COMP-007", 0.76, "warning", "Review thermal load"),
    productResult("CNC-032", 0.64, "warning", "Schedule targeted inspection"),
    productResult("COMP-021", 0.42, "attention", "Monitor next shift"),
    productResult("CNC-004", 0.18, "normal", "Continue monitoring"),
  ];
  const base = `**/api/projects/${SHARE_PROJECT}/workspaces/${SHARE_WORKSPACE}/predictive-maintenance`;
  await page.route(`${base}/versions`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      organization_id: "org-ontology-demo",
      project_id: SHARE_PROJECT,
      workspace_id: SHARE_WORKSPACE,
      items: [
        { dataset_id: "dataset-predictive-maintenance", dataset_name: "Predictive Maintenance Canonical", dataset_version_id: context.dataset_version_id, version_number: 31, source_version: context.source_version, bundle_checksum_sha256: checksum, dataset_status: "published", record_count: context.record_count, row_counts: context.row_counts, result_artifact_count: 100, prediction_timeline_count: 68208, model_version: context.model_version, result_artifact_schema_version: context.result_artifact_schema_version, prediction_task: context.prediction_task, graph: context.graph, release_ready: true, is_latest: true, is_v3_1: true },
        { dataset_id: "dataset-predictive-maintenance", dataset_name: "Predictive Maintenance Canonical", dataset_version_id: "dsv-v2", version_number: 20, source_version: "canonical-ai4i-physics-v2", bundle_checksum_sha256: "e".repeat(64), dataset_status: "published", record_count: 540000, row_counts: { assets: 100 }, result_artifact_count: 0, prediction_timeline_count: 0, model_version: null, result_artifact_schema_version: null, prediction_task: null, graph: { ...context.graph, status: "ready", record_count: 1984 }, release_ready: true, is_latest: false, is_v3_1: false },
      ],
      default_dataset_version_id: context.dataset_version_id,
      immutable_versioning: true,
      rollback_supported: true,
    }) });
  });
  await page.route(`${base}/context**`, async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(context) }));
  await page.route(`${base}/results/latest**`, async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ context, items: results, total: results.length, latest_product_contract: "result_artifact" }) }));
  await page.route(`${base}/observations**`, async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ context, window_start: "2026-08-04T18:00:00Z", window_end: "2026-08-05T00:00:00Z", grain: "10m", source_rows_mutated: false, observations: [], returned_observation_count: 0, limit: 72, truncated: false }) }));
  await page.route(`${base}/replay/sessions`, async (route) => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({
    context,
    cursor: { session_id: "replay-share-1", state: "paused", sequence: 24, simulation_time: "2026-07-14T08:40:00Z", wall_clock_observed_at: "2026-08-05T00:20:00Z", source_freshness_at: "2026-07-14T08:40:00Z", speed_minutes_per_second: 60, progress: 0.42, model_retrained: false },
    canonical_sensor_time: "2026-07-14T08:40:00Z",
    nearest_prediction_time: "2026-07-14T08:40:00Z",
    compressor_observations: [],
    cnc_observations: [],
    predictions: results.slice(0, 2),
    graph: context.graph,
    replay_source: "postgresql_prediction_timeline",
    truth_exposed: false,
    sensor_values_generated: false,
  }) }));
  await page.route(`${base}/replay/sessions/replay-share-1/events`, async (route) => route.fulfill({ status: 204, body: "" }));
}
