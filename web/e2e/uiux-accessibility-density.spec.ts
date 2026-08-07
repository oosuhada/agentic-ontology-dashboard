import { expect, test, type Locator, type Page } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill("manager@ontology.local");
  await page.getByLabel("비밀번호").fill("Manager!2026");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/app\/projects\//);
  await expect(page.locator(".dashboard-board-frame").first()).toBeVisible({ timeout: 20_000 });
}

async function expectFocusInside(page: Page, container: Locator) {
  expect(await container.evaluate((element) => element.contains(document.activeElement))).toBe(true);
}

test("density, responsive grid and modal focus contracts", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);

  const displaySummary = page.locator(".od-display-menu > summary");
  await displaySummary.click();
  const displayDialog = page.getByRole("dialog", { name: "Display settings" });
  await expect(displayDialog).toBeVisible();

  await displayDialog.getByRole("button", { name: /Compact/ }).click();
  const compact = await page.evaluate(() => ({
    control: getComputedStyle(document.documentElement).getPropertyValue("--fd-control-h").trim(),
    toolbar: getComputedStyle(document.documentElement).getPropertyValue("--fd-toolbar-h").trim(),
  }));
  await displayDialog.getByRole("button", { name: /Standard/ }).click();
  const standard = await page.evaluate(() => ({
    control: getComputedStyle(document.documentElement).getPropertyValue("--fd-control-h").trim(),
    toolbar: getComputedStyle(document.documentElement).getPropertyValue("--fd-toolbar-h").trim(),
  }));
  await displayDialog.getByRole("button", { name: /Accessible/ }).click();
  const accessible = await page.evaluate(() => ({
    control: getComputedStyle(document.documentElement).getPropertyValue("--fd-control-h").trim(),
    toolbar: getComputedStyle(document.documentElement).getPropertyValue("--fd-toolbar-h").trim(),
  }));
  expect(Number.parseFloat(compact.control)).toBeLessThan(Number.parseFloat(standard.control));
  expect(Number.parseFloat(standard.control)).toBeLessThan(Number.parseFloat(accessible.control));
  expect(Number.parseFloat(compact.toolbar)).toBeLessThan(Number.parseFloat(standard.toolbar));
  expect(Number.parseFloat(standard.toolbar)).toBeLessThan(Number.parseFloat(accessible.toolbar));
  await displayDialog.getByRole("button", { name: /Standard/ }).click();
  await displaySummary.click();

  await expect(page.locator(".board-runtime-technical:visible")).toHaveCount(0);

  const commandTrigger = page.locator(".od-global-search");
  await commandTrigger.click();
  const commandDialog = page.getByRole("dialog", { name: "Command palette" });
  await expect(commandDialog).toBeVisible();
  await expect(commandDialog.locator("input")).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expectFocusInside(page, commandDialog);
  await page.keyboard.press("Escape");
  await expect(commandDialog).toBeHidden();
  await expect(commandTrigger).toBeFocused();

  await page.getByRole("button", { name: "편집", exact: true }).click();
  const catalogTrigger = page.getByRole("button", { name: "Board Catalog" });
  await catalogTrigger.click();
  const catalogDialog = page.getByRole("dialog", { name: "Board Catalog" });
  await expect(catalogDialog).toBeVisible();
  await expect(catalogDialog.getByLabel("Board catalog search")).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expectFocusInside(page, catalogDialog);
  await page.keyboard.press("Escape");
  await expect(catalogDialog).toBeHidden();
  await expect(catalogTrigger).toBeFocused();

  const firstBoard = page.locator(".dashboard-board-frame").first();
  await expect(firstBoard.locator(".dashboard-board-more")).toBeVisible();
  expect(await firstBoard.locator(".dashboard-board-actions > button").count()).toBeLessThanOrEqual(1);

  await page.setViewportSize({ width: 390, height: 844 });
  const layout = page.locator(".dashboard-workspace-layout");
  await expect(layout).toBeVisible();
  const mobileGeometry = await page.evaluate(() => {
    const layoutElement = document.querySelector<HTMLElement>(".dashboard-workspace-layout");
    const canvas = document.querySelector<HTMLElement>(".dashboard-canvas-region");
    const context = document.querySelector<HTMLElement>(".dashboard-context-rail");
    const first = document.querySelector<HTMLElement>(".dashboard-board-frame");
    return {
      columns: layoutElement ? getComputedStyle(layoutElement).gridTemplateColumns : "",
      layoutWidth: layoutElement?.getBoundingClientRect().width ?? 0,
      canvasWidth: canvas?.getBoundingClientRect().width ?? 0,
      contextWidth: context?.getBoundingClientRect().width ?? 0,
      firstBoardTop: first?.getBoundingClientRect().top ?? 9999,
    };
  });
  expect(mobileGeometry.columns.trim().split(/\s+/)).toHaveLength(1);
  expect(mobileGeometry.canvasWidth).toBeGreaterThan(370);
  expect(mobileGeometry.contextWidth).toBeGreaterThan(370);
  expect(mobileGeometry.firstBoardTop).toBeLessThan(260);

  const contextTrigger = page.getByRole("button", { name: "Context & filters" });
  await contextTrigger.click();
  const contextSheet = page.locator(".dashboard-context-sheet");
  await expect(contextSheet).toBeVisible();
  const contextBounds = await contextSheet.boundingBox();
  expect(contextBounds).not.toBeNull();
  expect(contextBounds!.x).toBeGreaterThanOrEqual(0);
  expect(contextBounds!.x + contextBounds!.width).toBeLessThanOrEqual(390.5);
  await contextSheet.getByRole("button", { name: "Context 닫기" }).click();
  await expect(contextSheet).toBeHidden();

  await page.goto("/app/analysis/risk-event-portfolio");
  await expect(page.locator(".analysis-edge-label > button").first()).toBeVisible({ timeout: 20_000 });
  const connector = page.locator(".analysis-edge-label > button").first();
  await expect.poll(async () => connector.evaluate((element) => element.getBoundingClientRect().width)).toBeGreaterThanOrEqual(39.5);
  await expect.poll(async () => connector.evaluate((element) => element.getBoundingClientRect().height)).toBeGreaterThanOrEqual(39.5);
});
