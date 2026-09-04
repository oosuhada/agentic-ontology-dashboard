import { expect, type Page, test } from "@playwright/test";

const captureRoot = "../docs/ui/palantir-integration/final";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill("fde@ontology.local");
  await page.getByLabel("비밀번호").fill("FDE!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/projects\//, { timeout: 45_000 });
}

async function capture(page: Page, name: string) {
  await page.screenshot({ path: `${captureRoot}/${name}.png`, fullPage: false, animations: "disabled" });
}

test.use({ viewport: { width: 1440, height: 1000 }, colorScheme: "light" });

test("Analysis projections, compatible actions, canvases, hidden computation, and forecast", async ({ page }) => {
  test.setTimeout(150_000);
  await login(page);
  await page.goto("/app/analysis/palantir-integration-analysis");
  await expect(page.locator(".analysis-flow-canvas .react-flow")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".fd-data-pill").first()).toBeVisible();
  await capture(page, "analysis-path");

  await page.getByRole("button", { name: "Canvas", exact: true }).click();
  await expect(page.locator(".analysis-freeform-canvas")).toBeVisible();
  await expect(page.locator(".analysis-canvas-card")).toHaveCount(4);
  await page.getByRole("button", { name: "Add canvas" }).click();
  await expect(page.locator(".analysis-canvas-row")).toHaveCount(2);
  await capture(page, "analysis-canvas");

  await page.getByRole("button", { name: "Graph", exact: true }).click();
  await expect(page.locator(".analysis-dependency-graph .react-flow")).toBeVisible();
  await page.getByRole("button", { name: "Collapse computation" }).click();
  await expect(page.getByRole("button", { name: "Show computation" })).toBeVisible();
  await capture(page, "analysis-graph");

  await page.getByRole("button", { name: /Inspector|Dependencies/ }).last().click();
  await expect(page.locator(".analysis-dependency-panel")).toBeVisible();
  await page.getByRole("button", { name: /Dependencies/ }).last().click();
  await expect(page.locator(".analysis-result-inspector")).toBeVisible();
  await page.getByRole("button", { name: "Forecast", exact: true }).click();
  await expect(page.locator(".analysis-timeseries-forecast")).toBeVisible();
  await page.getByRole("button", { name: /Forecast settings/ }).click();
  await expect(page.locator(".analysis-forecast-editor")).toBeVisible();
  await capture(page, "analysis-forecast");
});

test("ObjectSet selection merge and linked traversal actions", async ({ page }) => {
  test.setTimeout(150_000);
  await login(page);
  await page.getByRole("button", { name: "Ontology", exact: true }).click();
  await expect(page.locator(".ontology-object-table .fd-resource-table__row").first()).toBeVisible({ timeout: 45_000 });
  const rowChecks = page.locator('.ontology-object-table input[type="checkbox"][aria-label^="Select "]:not([aria-label="Select all visible objects"])');
  await expect(rowChecks).toHaveCount(7);
  await rowChecks.nth(0).check();
  await rowChecks.nth(1).check();
  await page.getByLabel("Selection merge mode").selectOption("union");
  await page.getByRole("button", { name: /Apply selection/ }).click();
  await expect(page.locator(".ontology-selection-banner")).toContainText("2 objects selected");
  await capture(page, "ontology-selection");
  await page.getByRole("button", { name: /Traverse selected/ }).click();
  await expect(page.locator(".ontology-exploration-view")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".ontology-exploration-root")).toBeVisible();
  await capture(page, "ontology-traversal");
});

test("public reference gallery renders before and after captures", async ({ page }) => {
  await page.goto("/reference");
  await expect(page.getByRole("heading", { name: /Before \/ After Reference/ })).toBeVisible();
  await expect(page.locator(".reference-comparison-card")).toHaveCount(6);
  await expect(page.locator(".reference-comparison-images img")).toHaveCount(12);
  await page.waitForFunction(() => [...document.querySelectorAll<HTMLImageElement>(".reference-comparison-images img")].every((image) => image.complete && image.naturalWidth > 0));
  await page.screenshot({ path: `${captureRoot}/reference-gallery.png`, fullPage: true, animations: "disabled" });
});
