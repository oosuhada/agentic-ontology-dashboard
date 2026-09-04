import { expect, type Page, test } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill("manager@ontology.local");
  await page.getByLabel("비밀번호").fill("Manager!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/projects\//);
}

test("keeps the original dashboard route and exposes the Blueprint comparison workbench", async ({ page }) => {
  await login(page);

  await page.goto("/app/projects/manufacturing-demo-project");
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  await expect(page.locator(".blueprint-preview")).toHaveCount(0);

  await page.goto("/app/projects/manufacturing-demo-project/blueprint");
  await expect(page.locator(".blueprint-preview")).toBeVisible();
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project\/blueprint$/);
  await expect(page.getByText("기존 Dashboard는 변경하지 않았습니다")).toBeVisible();
  await expect(page.locator(".bp-kpi-card")).toHaveCount(4);
  await expect(page.locator(".bp-event-list button")).toHaveCount(8);

  await page.getByRole("button", { name: /Objects/ }).click();
  await expect(page.getByText("Ontology Object Explorer", { exact: true })).toBeVisible();
  await expect(page.locator(".bp-virtual-table-row").first()).toBeVisible();

  await page.getByRole("button", { name: /Analysis/ }).click();
  await expect(page.getByText("Typed Analysis Workbench", { exact: true })).toBeVisible();
  await expect(page.locator(".react-flow__node")).toHaveCount(5);
  await page.getByRole("button", { name: "Canvas", exact: true }).click();
  await expect(page.locator(".bp-analysis-canvas canvas")).toBeVisible();

  await page.getByRole("button", { name: /Operations/ }).click();
  await expect(page.getByText("Operational Workflow", { exact: true })).toBeVisible();
  await expect(page.locator(".bp-operations-grid .bp-panel")).toHaveCount(3);
});

test("Blueprint workbench remains within the mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto("/app/projects/manufacturing-demo-project/blueprint");
  await expect(page.locator(".blueprint-preview")).toBeVisible();
  await expect(page.locator(".bp-inspector")).toHaveCount(0);

  for (const label of ["Overview", "Objects", "Analysis", "Operations"]) {
    await page.getByRole("button", { name: new RegExp(label) }).click();
    const widths = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(widths.scroll).toBe(widths.client);
  }
});
