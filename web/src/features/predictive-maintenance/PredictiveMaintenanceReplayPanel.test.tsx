import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import {
  graphStatusLabel,
  PredictiveMaintenanceReplayPanel,
} from "./PredictiveMaintenanceReplayPanel";

describe("PredictiveMaintenanceReplayPanel", () => {
  it("renders a small replay vertical without confusing graph readiness", () => {
    const html = renderToString(
      <PredictiveMaintenanceReplayPanel projectId="project-test" workspaceId="workspace-test" />,
    );
    expect(html).toContain("Result Artifact · Replay");
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
      record_count: 1,
      row_counts: {},
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
        required_for_runtime: false,
      },
    })).toContain("PostgreSQL replay available");
  });
});
