import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "../../ui/i18n/I18nProvider";
import type { PredictiveMaintenanceRuntimeContext } from "./types";
import {
  countStatusGrades,
  graphStatusLabel,
  PredictiveMaintenanceReplayPanel,
  productResultContractLabel,
  productResultEvidencePreview,
  replayTimestamp,
  roleRuntimeMode,
} from "./PredictiveMaintenanceReplayPanel";

describe("PredictiveMaintenanceReplayPanel", () => {
  it("renders a small replay vertical without confusing graph readiness", () => {
    const html = renderToString(
      <I18nProvider>
        <PredictiveMaintenanceReplayPanel projectId="project-test" workspaceId="workspace-test" />
      </I18nProvider>,
    );
    expect(html).toContain("Dataset Version · Result Artifact · Replay");
    expect(html).toContain("Simulation 시각");
    expect(html).toContain("Source 최신 시각");
  });

  it("treats graph failure as supplemental to PostgreSQL replay", () => {
    const context: PredictiveMaintenanceRuntimeContext = {
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
    };
    expect(graphStatusLabel(context)).toContain("PostgreSQL runtime available");
    expect(graphStatusLabel(context, "ko-KR")).toContain("PostgreSQL Runtime 사용 가능");
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

  it("surfaces promoted Product Result evidence without parsing raw payload in the view", () => {
    const result = {
      source_contract: "result_artifact",
      evidence_summary: {
        available: true,
        batch_lineage: {
          batch_id: "batch-001",
          event_id: "GEN-EVT-001",
          emitted_at: "2026-08-05T00:00:00Z",
          generated_at: "2026-08-05T00:00:00Z",
          source_kind: "maintenance_replay_overlay",
          producer_id: "gen-data-local",
          model_id: "independent-logreg",
          source_reference: "prediction-result-batch:batch-001:event:GEN-EVT-001",
        },
        evidence_payload_reference: {
          source: "product_result_artifact",
          reference: "GEN-001",
        },
        sensor_window_rows: 0,
        sensor_window: {},
        component_hypotheses: [],
        recommended_actions: [],
        source_fields: [
          { field_id: "prediction_batch.score", label: "Generator failure score", source_path: "results[0].score", description: null },
          { field_id: "prediction_batch.payload_sha256", label: "Prediction payload checksum", source_path: "results[0].payload_sha256", description: null },
          { field_id: "prediction_batch.model_artifact_manifest_sha256", label: "Model artifact manifest checksum", source_path: "results[0].model_artifact_manifest_sha256", description: null },
          { field_id: "backend_policy.decision_threshold", label: "Backend decision threshold", source_path: "threshold_policy.json", description: null },
          { field_id: "extra.hidden", label: "Extra field", source_path: "extra", description: null },
        ],
        evidence_gaps: [
          { gap_id: "gap-1", field: "sensor", owner_domain: "diagnosis", display_policy: "show_limitation", reason: "missing_source", required_source: "observation window" },
          { gap_id: "gap-2", field: "component", owner_domain: "diagnosis", display_policy: "show_limitation", reason: "missing_source", required_source: "component mapping" },
          { gap_id: "gap-3", field: "maintenance", owner_domain: "maintenance", display_policy: "show_limitation", reason: "missing_source", required_source: "maintenance context" },
          { gap_id: "gap-4", field: "extra", owner_domain: "diagnosis", display_policy: "show_limitation", reason: "missing_source", required_source: "extra" },
        ],
      },
    } as never;

    expect(productResultContractLabel(result, (key) => key)).toBe("pm.promotedResultArtifact");
    expect(productResultEvidencePreview(result).inspectionReasons.map((field) => field.field_id)).toEqual([
      "prediction_batch.score",
      "prediction_batch.payload_sha256",
      "prediction_batch.model_artifact_manifest_sha256",
      "backend_policy.decision_threshold",
    ]);
    expect(productResultEvidencePreview(result).evidenceGaps.map((gap) => gap.gap_id)).toEqual([
      "gap-1",
      "gap-2",
      "gap-3",
    ]);
  });

  it("normalizes datetime-local replay controls to a timezone-aware contract", () => {
    const timestamp = replayTimestamp("2026-08-15T12:00");
    expect(timestamp).toMatch(/Z$/);
    expect(Date.parse(timestamp ?? "")).toBe(Date.parse("2026-08-15T12:00"));
    expect(replayTimestamp("")).toBeUndefined();
    expect(replayTimestamp("not-a-time")).toBeUndefined();
  });
});
