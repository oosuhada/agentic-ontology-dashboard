import { expect, type Page, test } from "@playwright/test";

const projectId = "manufacturing-demo-project";
const workspaceId = "manufacturing-demo";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill("fde@ontology.local");
  await page.getByLabel("비밀번호").fill("FDE!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/projects\//);
}

async function expectSingleColumn(page: Page, selector: string) {
  const columns = await page.locator(selector).evaluate((element) => getComputedStyle(element).gridTemplateColumns);
  expect(columns.trim().split(/\s+/)).toHaveLength(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
}

test("mobile workbenches use drawers and single-column resource flows", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);

  const menuTrigger = page.getByRole("button", { name: /Product navigation 열기|Open product navigation/ });
  await menuTrigger.click();
  const navigation = page.getByRole("dialog", { name: "Product navigation" });
  await expect(navigation).toBeVisible();
  await page.keyboard.press("Shift+Tab");
  expect(await navigation.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(navigation).toBeHidden();
  await expect(menuTrigger).toBeFocused();

  await page.goto(`/app/projects/${projectId}/datasets`);
  await expect(page.locator(".dataset-resource-table .fd-resource-table__row").first()).toBeVisible({ timeout: 30_000 });
  await expectSingleColumn(page, ".dataset-catalog-grid");
  await page.locator(".dataset-resource-table .fd-resource-table__row").first().click();
  const datasetDrawer = page.locator(".dataset-detail-drawer");
  await expect(datasetDrawer).toBeVisible();
  await datasetDrawer.getByRole("button", { name: /닫기$/ }).click();

  await page.goto(`/app/projects/${projectId}/workspaces/${workspaceId}/ontology`);
  await expect(page.locator(".ontology-object-table .fd-resource-table__row").first()).toBeVisible({ timeout: 30_000 });
  await expectSingleColumn(page, ".ontology-workbench-grid");
  await page.locator(".ontology-object-table .fd-resource-table__row").first().click();
  const objectDrawer = page.getByRole("dialog", { name: /Object를 선택하세요|Select an object/ });
  await expect(objectDrawer).toBeVisible();
  await objectDrawer.getByRole("button", { name: /닫기$/ }).click();

  await page.goto(`/app/projects/${projectId}/workspaces/${workspaceId}/governance`);
  await page.getByRole("button", { name: "Projection Health" }).click();
  await expect(page.locator(".governance-record-table .fd-resource-table__row").first()).toBeVisible({ timeout: 30_000 });
  await expectSingleColumn(page, ".governance-record-layout");
  await page.locator(".governance-record-table .fd-resource-table__row").first().click();
  const governanceDrawer = page.getByRole("dialog", { name: "Projection inspector" });
  await expect(governanceDrawer).toBeVisible();
  await governanceDrawer.getByRole("button", { name: /닫기$/ }).click();

  await page.goto("/app/analysis/mobile-workbench-contract");
  await expect(page.locator(".analysis-workbench")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("dialog", { name: "Analysis inspector" })).toHaveCount(0);
  await page.getByRole("button", { name: "Show inspector" }).click();
  await expect(page.getByRole("dialog", { name: "Analysis inspector" })).toBeVisible();
  await page.getByRole("dialog", { name: "Analysis inspector" }).getByRole("button", { name: /닫기$/ }).click();

  await page.goto(`/app/projects/${projectId}/workspaces/${workspaceId}/agent`);
  await expect(page.locator(".agent-workbench-grid")).toBeVisible({ timeout: 30_000 });
  await expectSingleColumn(page, ".agent-workbench-grid");
});
