import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  countStatusGrades,
  graphStatusLabel,
  PredictiveMaintenanceReplayPanel,
  replayTimestamp,
  roleRuntimeMode,
} from "./PredictiveMaintenanceReplayPanel";

describe("PredictiveMaintenanceReplayPanel", () => {
  it("renders a small replay vertical without confusing graph readiness", () => {
    const html = renderToString(
      <PredictiveMaintenanceReplayPanel projectId="project-test" workspaceId="workspace-test" />,
    );
    expect(html).toContain("Dataset Version · Result Artifact · Replay");
    expect(html).toContain("Simulation time");
    expect(html).toContain("Source freshness");
  });

  it("treats graph failure as supplemental to PostgreSQL replay", () => {
    expect(graphStatusLabel({
      organization_id: "org",
      project_id: "project",
      workspace_id: "workspace",
      dataset_id: "dataset",
      dataset_version_id: "version",
      source_version: "canonical-ai4i-physics-v3.1",
      bundle_checksum_sha256: "a".repeat(64),
      version_number: 2,
      record_count: 1,
      dataset_status: "ready",
      row_counts: {},
      source_contract: {},
      model_version: "independent-logreg-v3.1",
      result_artifact_schema_version: "result-artifact-v1.0",
      prediction_task: "binary_failure_within_horizon",
      relational_status: "ready",
      relational_record_count: 15,
      semantic_catalog_version: "predictive-maintenance-semantic-v3.1",
      governance: {
        release_identity: {},
        tool_wear_continuity: { pass: true },
        agent_example_evaluation: { pass: true },
        ai4i_physics: { pass: true },
        ai4i_contract: {},
        query_time_derived_measures: {},
        governance_artifacts: [],
        prediction_label_semantics: "generic_binary_risk_not_ai4i_failure_mode",
        release_evidence_is_prediction_label: false,
        maintenance_evidence_accuracy_is_instance_accuracy: false,
      },
      semantic_query: {
        dimensions: [],
        canonical_measures: [],
        derived_measures: {},
        latest_result_contract: "result_artifact",
        replay_prediction_contract: "precomputed_prediction_timeline",
        supported_grains: ["raw", "10m", "1h"],
        evaluation_truth_queryable: false,
        model_training_available: false,
      },
      graph: {
        status: "failed",
        record_count: 0,
        provider_run_id: null,
        last_error: "offline",
        attempt_count: 1,
        updated_at: null,
        required_for_runtime: false,
      },
    })).toContain("PostgreSQL runtime available");
  });

  it("keeps role views and status aggregation deterministic", () => {
    expect(roleRuntimeMode("process_manager")).toBe("manager");
    expect(roleRuntimeMode("process_engineer")).toBe("engineer");
    expect(roleRuntimeMode("ml_validator")).toBe("model");
    expect(roleRuntimeMode("fde")).toBe("governance");
    expect(countStatusGrades([
      { status_grade: "critical" },
      { status_grade: "warning" },
      { status_grade: "critical" },
    ] as never)).toEqual({ critical: 2, warning: 1, attention: 0, normal: 0 });
  });

  it("normalizes datetime-local replay controls to a timezone-aware contract", () => {
    const timestamp = replayTimestamp("2026-08-15T12:00");
    expect(timestamp).toMatch(/Z$/);
    expect(Date.parse(timestamp ?? "")).toBe(Date.parse("2026-08-15T12:00"));
    expect(replayTimestamp("")).toBeUndefined();
    expect(replayTimestamp("not-a-time")).toBeUndefined();
  });
});
