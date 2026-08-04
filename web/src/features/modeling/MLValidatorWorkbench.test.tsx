import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MLValidatorWorkbench } from "./MLValidatorWorkbench";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: {
      permissions: ["ml.console.read", "ml.release.request", "ml.release.approve"],
    },
  }),
}));

const payload = {
  schema_version: "ml-validator-workbench-v1",
  scope: { organization_id: "org", project_id: "project", workspace_id: "workspace" },
  capabilities: { artifact_store: { status: "ready", reason: null }, experiment_execution: "queued_worker_or_cli", worker_health: { status: "idle", reason: null, running_count: 0, queued_count: 0 }, synchronous_training_endpoint: false },
  readiness: { status: "ready", steps: [{ step: "mapping_set", status: "approved", identity: "map" }], missing_prerequisites: [] },
  experiments: [{ experiment_id: "experiment-1", status: "succeeded", progress: 1, dataset_version_id: "dsv", mapping_set_id: "map", recipe_set_id: "recipe", feature_dataset_version_id: "feature", label_policy_id: "label", selected_candidate_id: "rf", threshold_policy_id: "threshold", split_policy: {}, candidates: [], created_at: "2026-01-01", updated_at: "2026-01-01" }],
  selected_experiment_id: "experiment-1",
  leaderboard: [{ candidate_id: "rf", algorithm: "random_forest", status: "succeeded", selected: true, dependency_version: "1", error_reason: null, validation_metrics: { average_precision: .8, roc_auc: .9, precision: .7, recall: .8, f1: .75, brier_score: .1, positive_prediction_rate: .2, confusion_matrix: [[10, 2], [1, 4]], sample_count: 17, positive_count: 5, positive_rate: .29, unavailable_reason: null }, held_out_test_metrics: null }],
  report: { status: "available", reason: null, split: {}, threshold_policy: {}, threshold_curve: [{ threshold: .2, precision: .7, recall: .8 }], precision_recall_curve: [{ recall: .8, precision: .7, threshold: .2 }], roc_curve: [{ false_positive_rate: .1, true_positive_rate: .8, threshold: .2 }], calibration: [{ mean_predicted_probability: .2, observed_positive_rate: .25 }], slice_metrics: [], runtime_versions: {}, lineage: { dataset_version_id: "dsv" }, limitations: [], validation_used_for_selection: true, test_used_for_selection: false },
  models: [], active_models: [], release_requests: [], lineage_detail: { mapping_set: {}, feature_recipe_set: {}, feature_dataset_version: {} }, global_feature_importance: { status: "unavailable", reason: "not produced", items: [] }, operational_monitoring: { status: "unavailable", reason: "not connected" }, audit_events: [], rollback_history: [], empty: false,
};

let container: HTMLDivElement;
let root: Root;

async function renderWorkbench(nextPayload: unknown = payload) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(nextPayload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  await act(async () => {
    root.render(<MLValidatorWorkbench projectId="project" workspaceId="workspace" />);
  });
  await act(async () => { await Promise.resolve(); });
}

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
    .IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

describe("MLValidatorWorkbench", () => {
  it("renders real leaderboard and evaluation artifacts", async () => {
    await renderWorkbench();
    expect(container.textContent).toContain("Validation leaderboard");
    expect(container.textContent).toContain("random_forest");
    expect(container.querySelector('[aria-label="Validation precision recall curve"]')).not.toBeNull();
    expect(container.querySelector('[aria-label="Validation ROC curve"]')).not.toBeNull();
    const thresholdTab = Array.from(container.querySelectorAll('button[role="tab"]'))
      .find((element) => element.textContent === "threshold");
    expect(thresholdTab).toBeDefined();
    await act(async () => thresholdTab?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(container.querySelector('[aria-label="Threshold precision recall curve"]')).not.toBeNull();
    expect(container.querySelector('[aria-label="Calibration curve"]')).not.toBeNull();
  });

  it("shows explicit empty state without inventing fixture metrics", async () => {
    await renderWorkbench({
      ...payload,
      experiments: [],
      leaderboard: [],
      models: [],
      empty: true,
      selected_experiment_id: null,
    });
    expect(container.textContent).toContain("아직 실행된 Experiment가 없습니다.");
    expect(container.textContent).not.toContain("Gold fixtures");
  });

  it("renders API errors instead of fallback samples", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "artifact store blocked" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await act(async () => {
      root.render(<MLValidatorWorkbench projectId="project" workspaceId="workspace" />);
    });
    await act(async () => { await Promise.resolve(); });
    expect(container.textContent).toContain("artifact store blocked");
  });
});
