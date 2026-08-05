import { expect, type Browser, type Page, test } from "@playwright/test";

const projectId = "manufacturing-demo-project";
const workspaceId = "manufacturing-demo";
const datasetVersionId = "dsv-9fc144c7-d3f8-5b37-8465-04248165b7ce";
const datasetName = "UCI AI4I 2020 Manufacturing Predictive Maintenance — Physics & Maintenance Canonical V3.1";
const projectRoute = `/app/projects/${projectId}`;
const modelingRoute = `${projectRoute}/workspaces/${workspaceId}/modeling`;
const runtimeBase = `/api/projects/${projectId}/workspaces/${workspaceId}/predictive-maintenance`;

test.skip(
  process.env.PLAYWRIGHT_PUBLIC_VERIFY !== "1",
  "Set PLAYWRIGHT_PUBLIC_VERIFY=1 and PLAYWRIGHT_BASE_URL to verify a deployed environment.",
);

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/(?:app|admin)(?:\/|$)/);
}

function collectServerErrors(page: Page): string[] {
  const failures: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 500) {
      failures.push(`${response.status()} ${response.request().method()} ${response.url()}`);
    }
  });
  return failures;
}

async function expectCanonicalRuntime(page: Page) {
  await expect(page.getByText(datasetName, { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByLabel("Predictive maintenance Dataset Version")).toHaveValue(datasetVersionId);
  await expect(page.locator(".pm-replay-summary")).toContainText("canonical-ai4i-physics-v3.1");
  await expect(page.getByText(/Graph pending/).first()).toBeVisible();
}

async function newAuthenticatedPage(
  browser: Browser,
  email: string,
  password: string,
): Promise<{ page: Page; close: () => Promise<void> }> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await login(page, email, password);
  return { page, close: () => context.close() };
}

test("public Dashboard serves the canonical PostgreSQL contract and complete replay controls", async ({ page }) => {
  test.setTimeout(180_000);
  const serverErrors = collectServerErrors(page);
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await page.goto(projectRoute);
  await expectCanonicalRuntime(page);

  const endpointResponses = await Promise.all(
    ["context", "versions", "dashboard"].map((endpoint) =>
      page.request.get(`${runtimeBase}/${endpoint}`),
    ),
  );
  for (const response of endpointResponses) expect(response.status()).toBe(200);

  const context = await endpointResponses[0].json();
  expect(context).toMatchObject({
    dataset_version_id: datasetVersionId,
    source_version: "canonical-ai4i-physics-v3.1",
    model_version: "independent-logreg-v3.1",
    result_artifact_schema_version: "result-artifact-v1.0",
    prediction_task: "binary_failure_within_horizon",
    relational_status: "ready",
    graph: { status: "pending", required_for_runtime: false },
  });
  expect(context.row_counts.result_artifact).toBe(100);
  expect(context.row_counts.prediction_timeline).toBe(68_208);

  const versions = await endpointResponses[1].json();
  expect(versions.default_dataset_version_id).toBe(datasetVersionId);
  expect(versions.selection_reason).toBe("canonical_v3_1_release_ready");

  const seek = page.getByLabel("Seek time");
  await seek.fill("2026-08-15T12:00");
  await page.getByRole("button", { name: "Start replay", exact: true }).click();
  await expect(page.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(page.locator(".pm-replay-cursor")).toContainText("paused");
  await page.getByRole("button", { name: "Resume", exact: true }).click();
  await expect(page.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
  await seek.fill("2026-08-20T12:00");
  await page.getByRole("button", { name: "Seek", exact: true }).click();
  await expect(page.getByRole("button", { name: "Reset", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(page.locator(".pm-replay-cursor")).toContainText("stopped");

  await page.reload();
  await expectCanonicalRuntime(page);
  expect(serverErrors).toEqual([]);
});

test("public role sessions preserve the V3.1 default and ML Validator permissions", async ({ browser }) => {
  test.setTimeout(180_000);

  const fde = await newAuthenticatedPage(browser, "fde@ontology.local", "FDE!2026");
  await fde.page.goto(projectRoute);
  await expectCanonicalRuntime(fde.page);
  expect((await fde.page.request.get(`${runtimeBase}/release`)).status()).toBe(200);
  const catalog = await fde.page.request.get(
    `/api/projects/${projectId}/dataset-catalog?workspace_id=${workspaceId}&offset=0&limit=200`,
  );
  expect(catalog.status()).toBe(200);
  const catalogPayload = await catalog.json();
  expect(catalogPayload.items.map((item: { display_name: string }) => item.display_name)).toEqual(
    expect.arrayContaining([
      datasetName,
      "Manufacturing Equipment Registry",
      "Manufacturing Risk Events",
    ]),
  );
  for (const datasetId of [
    "ds-a4e4e4dc-a0c7-5bde-8a19-43332f77b399",
    "ds-manufacturing-equipment",
    "ds-manufacturing-risk-events",
  ]) {
    expect(
      (
        await fde.page.request.get(
          `/api/projects/${projectId}/dataset-catalog/${datasetId}`,
        )
      ).status(),
    ).toBe(200);
  }
  await fde.close();

  const dataScientist = await newAuthenticatedPage(
    browser,
    "datascientist@ontology.local",
    "DataScience!2026",
  );
  await dataScientist.page.goto(modelingRoute);
  await expect(dataScientist.page.locator(".mlv-shell")).toBeVisible({ timeout: 60_000 });
  await expect(dataScientist.page.getByText("아직 실행된 Experiment가 없습니다.", { exact: true })).toBeVisible();
  await dataScientist.page.getByRole("tab", { name: "models", exact: true }).click();
  await expect(dataScientist.page.getByRole("button", { name: "승인", exact: true })).toHaveCount(0);
  await expect(dataScientist.page.getByRole("button", { name: "활성화", exact: true })).toHaveCount(0);
  await dataScientist.close();

  const engineer = await newAuthenticatedPage(browser, "engineer@ontology.local", "Engineer!2026");
  await engineer.page.goto(modelingRoute);
  await expect(engineer.page).toHaveURL(new RegExp(`${projectRoute}$`));
  await expect(engineer.page.locator(".mlv-shell")).toHaveCount(0);
  await engineer.close();

  const admin = await newAuthenticatedPage(browser, "admin@ontology.local", "OntologyAdmin!2026");
  await admin.page.goto(modelingRoute);
  await expect(admin.page.locator(".mlv-shell")).toBeVisible({ timeout: 60_000 });
  await expect(admin.page.getByRole("tab", { name: "models", exact: true })).toBeVisible();
  await admin.close();
});

test("public Team Share routes and API docs are distinct and complete", async ({ page }) => {
  test.setTimeout(120_000);
  const serverErrors = collectServerErrors(page);

  await page.goto("/team-share");
  await expect(page.getByText("team-share-capture-integrity-20260804", { exact: true })).toBeVisible();

  await page.goto("/team-share-adaptive");
  await expect(page.locator(".adaptive-share-page")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".adaptive-share-integrity strong")).toHaveText(
    "team-share-adaptive-v3.1-postgresql-20260805",
  );
  await expect(page.getByText(datasetVersionId, { exact: false })).toBeVisible();

  await page.goto("/team-share-adaptive.html");
  await expect(page.locator("main#top")).toBeVisible();
  await expect(page.locator(".integrity")).toHaveText("team-share-adaptive-v3.1-postgresql-20260805");
  await expect(page.locator(".adaptive-share-page")).toHaveCount(0);

  await page.goto("/docs");
  await expect(page.locator("#swagger-ui")).toBeVisible({ timeout: 60_000 });
  expect(serverErrors).toEqual([]);
});

test("public mobile surfaces do not overflow horizontally", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/team-share-adaptive");
  await expect(page.locator(".adaptive-share-page")).toBeVisible({ timeout: 60_000 });
  const storyGeometry = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));
  expect(storyGeometry.documentWidth).toBeLessThanOrEqual(storyGeometry.viewportWidth + 1);

  await login(page, "datascientist@ontology.local", "DataScience!2026");
  await page.goto(modelingRoute);
  await expect(page.locator(".mlv-shell")).toBeVisible({ timeout: 60_000 });
  const modelingGeometry = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));
  expect(modelingGeometry.documentWidth).toBeLessThanOrEqual(modelingGeometry.viewportWidth + 1);
});
