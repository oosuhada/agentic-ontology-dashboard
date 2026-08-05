import { expect, type Page, test } from "@playwright/test";

const projectRoute = "/app/projects/manufacturing-demo-project";

async function login(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("ontology-dashboard:locale", "ko-KR");
    localStorage.setItem("ontology-dashboard-theme", "dark");
  });
  await page.goto("/login");
  await page.getByLabel("이메일").fill("engineer@ontology.local");
  await page.getByLabel("비밀번호").fill("Engineer!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app(?:\/|$)/, { timeout: 30_000 });
  await page.goto(projectRoute);
  await expect(page.locator(".dashboard-board-frame").first()).toBeVisible({ timeout: 60_000 });
}

test.use({ viewport: { width: 1440, height: 1000 }, colorScheme: "dark" });

test("locale switch updates the dashboard chrome and content-aware AI layout can be applied", async ({ page }) => {
  test.setTimeout(120_000);
  await page.route("**/api/planner/board-recommendations", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        mode: "llm",
        provider: "playwright-layout-planner",
        fallback_reason: null,
        role_code: "process_engineer",
        goal: "prioritize evidence and maintenance boards",
        recommendations: [
          { definition_id: "risk-trend-workbench", display_name: "Risk trend", category: "observe", score: 0.98, reason: "Primary temporal evidence", already_present: true, preference_signals: [] },
          { definition_id: "event-data-grid", display_name: "Event data", category: "explore", score: 0.94, reason: "Detailed evidence", already_present: true, preference_signals: [] },
          { definition_id: "ontology-relationship", display_name: "Ontology", category: "explain", score: 0.88, reason: "Relationship context", already_present: true, preference_signals: [] },
        ],
        current_board_ids: [],
        requires_approval: true,
        persisted: false,
      }),
    });
  });

  await login(page);

  await expect(page.getByText("설비 신뢰성 운영", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "신뢰성 운영", exact: true })).toBeVisible();
  await expect(page.locator(".dashboard-board-title strong", { hasText: "운영 KPI 요약" }).first()).toBeVisible();
  await expect(page.getByText("표시 중인 Object", { exact: true })).toBeVisible();

  await page.locator(".od-display-menu > summary").click();
  await page.getByRole("button", { name: "English", exact: true }).click();
  await page.locator(".od-display-menu > summary").click();
  await expect(page.getByRole("button", { name: "Project home", exact: true })).toBeVisible();
  await expect(page.getByText("Connected resources", { exact: true })).toBeVisible();
  await expect(page.getByText("Parameters and filters", { exact: true })).toBeVisible();
  await expect(page.getByText("Automatically compose the workspace around equipment risk, production-line impact, failure type, and inspection decisions.", { exact: true })).toBeVisible();
  await expect(page.getByText("Risk trend + contributing factors + equipment relationships + inspection actions", { exact: true })).toBeVisible();
  await expect(page.locator(".dashboard-board-title strong", { hasText: "Operations KPI Strip" }).first()).toBeVisible();
  await expect(page.getByText("Visible objects", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const autoFit = page.getByRole("button", { name: "Auto-fit current tab", exact: true });
  await expect(autoFit).toBeVisible();
  await autoFit.click();
  await expect(page.getByText("Board heights and spacing were fitted to the current content.", { exact: true })).toBeVisible();
  await expect(page.locator('.dashboard-board-frame[data-layout-mode="auto"]').first()).toBeVisible();

  const aiLayout = page.getByRole("button", { name: "Recommend AI layout", exact: true });
  await aiLayout.click();
  await expect(page.getByText(/llm · playwright-layout-planner Planner recommendations/)).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('.dashboard-board-frame[data-layout-mode="ai"]').first()).toBeVisible();

  const overlapCount = await page.locator('.dashboard-board-frame[data-layout-mode="ai"]').evaluateAll((frames) => {
    const rects = frames.map((frame) => frame.getBoundingClientRect());
    let overlaps = 0;
    for (let left = 0; left < rects.length; left += 1) {
      for (let right = left + 1; right < rects.length; right += 1) {
        const a = rects[left];
        const b = rects[right];
        if (a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top) overlaps += 1;
      }
    }
    return overlaps;
  });
  expect(overlapCount).toBe(0);

  page.once("dialog", (dialog) => dialog.accept());
  const restoreResponse = page.waitForResponse((response) => (
    response.url().includes("/api/dashboards/preferences/restore")
    && response.request().method() === "POST"
  ));
  await page.getByTitle("Restore role defaults").evaluate((button: HTMLButtonElement) => button.click());
  expect((await restoreResponse).status()).toBe(200);
});
