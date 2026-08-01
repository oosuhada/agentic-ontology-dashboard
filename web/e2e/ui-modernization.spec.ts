import { expect, type Page, test } from "@playwright/test";

async function login(page: Page, email = "manager@ontology.local", password = "Manager!2026") {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/projects\//);
}

test("modern dashboard runtime exposes chart, virtual grid, ontology graph, analysis flow and persistent theme", async ({ page }) => {
  test.setTimeout(60_000);
  await login(page);

  await expect(page.locator(".react-grid-layout")).toBeVisible();
  await expect(page.locator(".generic-echarts-renderer canvas")).toBeVisible();
  await expect(page.locator(".generic-data-table")).toBeVisible();
  await expect(page.locator(".generic-data-table-body > button").first()).toBeVisible();

  await page.getByRole("button", { name: "근거와 후속", exact: true }).click();
  await expect(page.locator(".ontology-react-flow .react-flow")).toBeVisible();
  await expect(page.locator(".ontology-react-flow .react-flow__node").first()).toBeVisible();

  await page.keyboard.press("Control+K");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
  await page.getByRole("dialog", { name: "Command palette" }).getByRole("button", { name: /Open Analysis Path/ }).click();

  await expect(page.locator(".analysis-flow-canvas .react-flow")).toBeVisible();
  await expect(page.locator(".analysis-flow-node")).toHaveCount(4);
  await expect(page.locator(".analysis-result-echart canvas")).toBeVisible();
  await page.getByRole("button", { name: /Run path/ }).click();
  await expect(page.getByText(/Run analysis-run:.* succeeded/)).toBeVisible();
  await expect(page.getByText("server run", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "테마 전환" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("analysis save publishes a server snapshot and dashboard table uses server pagination", async ({ page }) => {
  test.setTimeout(90_000);
  await login(page);
  await page.goto("/app/analysis/playwright-server-analysis");
  await expect(page.getByText(/Server Analysis v1|서버에 생성했습니다/)).toBeVisible();

  await page.getByRole("button", { name: /Run path/ }).click();
  await expect(page.getByText(/Run analysis-run:.* succeeded/)).toBeVisible();
  await expect(page.getByText("server run", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Save dataset/ }).click();
  await expect(page.getByText(/published · server dataset snapshot/)).toBeVisible();
  await expect(page.getByText(/freshness ·/)).toBeVisible();

  await page.getByRole("button", { name: "Dashboards", exact: true }).click();
  await expect(page.locator(".generic-pagination-controls")).toBeVisible();
  await expect(page.locator(".data-grid-footer").filter({ hasText: "Server pagination" })).toBeVisible();
});

test("cross-filter selection updates downstream boards", async ({ page }) => {
  await login(page);
  await page.locator(".generic-data-table-body > button").nth(1).click();
  await expect(page.locator(".cross-filter-summary")).toContainText("active cross-filter");
  await expect(page.locator(".dashboard-board-frame.is-affected").first()).toBeVisible();
  await page.locator(".cross-filter-summary").getByRole("button", { name: "Clear" }).click();
  await expect(page.locator(".cross-filter-summary")).toHaveCount(0);
});

test("analysis route adds a pinned board reference to dashboard", async ({ page }) => {
  await login(page);
  await page.goto("/app/analysis/maintenance-risk-analysis");
  await expect(page).toHaveURL(/\/app\/analysis\/maintenance-risk-analysis$/);
  await expect(page.getByText(/maintenance-risk-analysis/).first()).toBeVisible();
  await page.locator(".analysis-flow-node").filter({ hasText: "Risk by production line" }).click();
  await page.getByRole("button", { name: /Add to Dashboard/ }).click();
  await expect(page.getByText(/pinned reference/)).toBeVisible();
  await page.getByRole("button", { name: "Dashboards", exact: true }).click();
  await expect(page.locator(".analysis-reference-runtime")).toContainText("maintenance-risk-analysis");
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByRole("button", { name: "개인 설정 저장" }).click();
  await expect(page.getByText(/다음 로그인에서도 복원됩니다/)).toBeVisible();
  await page.reload();
  await expect(page.locator(".analysis-reference-runtime")).toContainText("maintenance-risk-analysis");
});

test("react-grid-layout width persists through dashboard preferences", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Edit", exact: true }).click();

  const item = page.locator(".dashboard-board-title strong", { hasText: /^권장 조치$/ })
    .locator("xpath=ancestor::article[contains(@class,'dashboard-board-frame')]");
  await item.click();
  await expect(page.getByText("Board Inspector", { exact: true })).toBeVisible();
  await page.getByLabel("Layout 폭").selectOption("6");
  await expect(item).toHaveAttribute("data-grid-w", "6");

  const saveButton = page.getByRole("button", { name: "개인 설정 저장" });
  await expect(saveButton).toBeVisible();
  await saveButton.click();
  await expect(page.getByText(/다음 로그인에서도 복원됩니다/)).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Edit", exact: true }).click();

  const restoredFrame = page.locator(".dashboard-board-title strong", { hasText: /^권장 조치$/ })
    .locator("xpath=ancestor::article[contains(@class,'dashboard-board-frame')]");
  await expect(restoredFrame).toHaveAttribute("data-grid-w", "6");
});
