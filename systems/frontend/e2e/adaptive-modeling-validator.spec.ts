import { expect, type Page, test } from "@playwright/test";
import {
  ADAPTIVE_MODELING_PROJECT,
  ADAPTIVE_MODELING_VIEWPORTS,
  ADAPTIVE_MODELING_WORKSPACE,
} from "./adaptive-modeling-validator.manifest";

const routePath = `/app/projects/${ADAPTIVE_MODELING_PROJECT}/workspaces/${ADAPTIVE_MODELING_WORKSPACE}/modeling`;

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app(?:\/|$)|\/admin$/);
}

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

function workbenchPayload() {
  return {
    schema_version: "ml-validator-workbench-v1",
    scope: {
      organization_id: "org-ontology-demo",
      project_id: ADAPTIVE_MODELING_PROJECT,
      workspace_id: ADAPTIVE_MODELING_WORKSPACE,
    },
    capabilities: {
      artifact_store: { status: "ready", reason: null },
      experiment_execution: "queued_worker_or_cli",
      worker_health: {
        status: "idle",
        reason: null,
        running_count: 0,
        queued_count: 0,
      },
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
    experiments: [
      {
        experiment_id: "experiment-1",
        status: "succeeded",
        progress: 1,
        dataset_version_id: "dataset-version-1",
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
      },
    ],
    selected_experiment_id: "experiment-1",
    leaderboard: [
      {
        candidate_id: "candidate-dummy",
        algorithm: "dummy_prior",
        status: "succeeded",
        selected: false,
        dependency_version: "1.9.0",
        error_reason: null,
        validation_metrics: metric(0.29, 0.5),
        held_out_test_metrics: null,
      },
      {
        candidate_id: "candidate-logistic",
        algorithm: "logistic_regression",
        status: "succeeded",
        selected: true,
        dependency_version: "1.9.0",
        error_reason: null,
        validation_metrics: metric(0.59, 0.88),
        held_out_test_metrics: metric(0.5, 0.82),
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
      split: { train: 210, validation: 72, test: 72 },
      threshold_policy: {
        selected_operational_threshold: 0.33,
        recall_target: 0.5,
        false_negative_cost: 10,
        false_positive_cost: 1,
      },
      threshold_curve: [
        { threshold: 0.2, precision: 0.5, recall: 1 },
        { threshold: 0.33, precision: 0.63, recall: 0.95 },
        { threshold: 0.5, precision: 0.72, recall: 0.86 },
      ],
      precision_recall_curve: [
        { recall: 1, precision: 0.29, threshold: 0 },
        { recall: 0.95, precision: 0.63, threshold: 0.33 },
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
        dataset_version_id: "dataset-version-1",
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
        artifact: { uri: "artifact://model-candidate.joblib", checksum_sha256: "a".repeat(64), media_type: "application/octet-stream", size_bytes: 3000, created_at: "2026-08-05T00:12:00Z", store_capability: "ready" },
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
    release_requests: [
      {
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
      },
    ],
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

async function mockModelingApi(page: Page) {
  await page.route("**/api/modeling/workbench**", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(workbenchPayload()) });
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

for (const viewport of ADAPTIVE_MODELING_VIEWPORTS) {
  test(`ML Validator visual contract at ${viewport.name}`, async ({ page }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.addInitScript(() => {
      localStorage.setItem("ontology-dashboard:locale", "ko-KR");
      localStorage.setItem("ontology-dashboard-theme", "light");
    });
    await mockModelingApi(page);
    await login(page, "datascientist@ontology.local", "DataScience!2026");
    await page.goto(routePath);
    await expect(page.getByRole("heading", { name: "예지보전 모델 검증 Workbench" })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Validation leaderboard", { exact: true })).toBeVisible();
    await expect(page.getByLabel("Validation precision recall curve")).toBeVisible();
    await expect(page.getByLabel("Validation ROC curve")).toBeVisible();
    const geometry = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      headingVisible: Boolean(document.querySelector(".mlv-header h1")),
    }));
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
    expect(geometry.headingVisible).toBe(true);
    await expect(page).toHaveScreenshot(`adaptive-modeling-${viewport.name}.png`, {
      animations: "disabled",
      caret: "hide",
      maxDiffPixelRatio: 0.015,
      fullPage: true,
    });
  });
}

test("ML Validator can request release but cannot self-approve or activate", async ({ page }) => {
  await mockModelingApi(page);
  await login(page, "datascientist@ontology.local", "DataScience!2026");
  await page.goto(routePath);
  await page.getByRole("tab", { name: "models", exact: true }).click();
  await expect(page.getByRole("button", { name: "승인 요청", exact: true })).toBeVisible();
  await expect(page.locator(".mlv-release-list").getByRole("button", { name: "승인", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "활성화", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "승인 요청", exact: true }).click();
  await expect(page.getByText("승인 요청을 생성했습니다.", { exact: true })).toBeVisible();
});

test("tenant admin can approve and activate governed models", async ({ page }) => {
  await mockModelingApi(page);
  await login(page, "admin@ontology.local", "OntologyAdmin!2026");
  await page.goto(routePath);
  await page.getByRole("tab", { name: "models", exact: true }).click();
  await expect(page.locator(".mlv-release-list").getByRole("button", { name: "승인", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "활성화", exact: true })).toBeVisible();
  await page.locator(".mlv-release-list").getByRole("button", { name: "승인", exact: true }).click();
  await expect(page.getByText("모델을 승인했습니다.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "활성화", exact: true }).click();
  await expect(page.getByText("모델을 active로 전환했습니다.", { exact: true })).toBeVisible();
});

test("role without ml console permission cannot open the workbench", async ({ page }) => {
  await mockModelingApi(page);
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await page.goto(routePath);
  await expect(page).toHaveURL(new RegExp(`/app/projects/${ADAPTIVE_MODELING_PROJECT}$`));
  await expect(page.getByRole("heading", { name: "예지보전 모델 검증 Workbench" })).toHaveCount(0);
});
