import { expect, test, type Page } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill("manager@ontology.local");
  await page.getByLabel("비밀번호").fill("Manager!2026");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/app\/projects\//);
  await expect(page.locator(".dashboard-board-frame").first()).toBeVisible({ timeout: 20_000 });
}

async function ensureEditMode(page: Page) {
  const undo = page.getByRole("button", { name: "Undo dashboard edit" });
  if (!(await undo.isVisible().catch(() => false))) {
    await page.getByRole("button", { name: "편집", exact: true }).click();
    await expect(undo).toBeVisible();
  }
}

async function savePreferences(page: Page) {
  const save = page.getByRole("button", { name: "개인 레이아웃 저장", exact: true });
  if (await save.isVisible().catch(() => false)) {
    await save.click();
    await expect(page.getByRole("button", { name: "개인 레이아웃 저장됨", exact: true })).toBeDisabled({ timeout: 20_000 });
  }
}

test("chart switcher follows density, keyboard and responsive contracts", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const runtimeErrors: string[] = [];
  page.on("pageerror", (error) => runtimeErrors.push(`page:${error.message}`));
  page.on("console", (message) => {
    const text = message.text();
    if (message.type() === "error" && !text.includes("401") && !text.includes("404 (Not Found)")) runtimeErrors.push(`console:${text}`);
  });

  let boardId = "";
  try {
    await login(page);
    await ensureEditMode(page);
    await page.getByRole("button", { name: "Board Catalog" }).click();
    const dialog = page.getByRole("dialog", { name: "Board Catalog" });
    await dialog.getByLabel("Board catalog search").fill("Risk by Status (RenderSpec)");
    await dialog.getByRole("button", { name: /Risk by Status \(RenderSpec\)/ }).click();
    await dialog.locator(".catalog-add-selected").click();
    await dialog.getByRole("button", { name: "닫기" }).click();

    const board = page.locator(".dashboard-board-frame").filter({ hasText: "Risk by Status (RenderSpec)" }).last();
    await expect(board).toBeVisible();
    boardId = await board.getAttribute("data-board-id") ?? "";
    expect(boardId).not.toBe("");

    const initialSlot = board.locator(".visualization-switcher, .visualization-switcher-skeleton");
    await expect(initialSlot).toBeVisible();
    const initialSlotWidth = await initialSlot.evaluate((element) => element.getBoundingClientRect().width);
    expect(initialSlotWidth).toBeGreaterThanOrEqual(59);
    expect(initialSlotWidth).toBeLessThanOrEqual(79);

    await savePreferences(page);
    const trigger = board.locator(".visualization-switcher-trigger");
    await expect(trigger).toBeVisible({ timeout: 20_000 });
    const dimensions = await trigger.evaluate((element) => ({
      height: element.getBoundingClientRect().height,
      token: getComputedStyle(document.documentElement).getPropertyValue("--fd-control-h").trim(),
      width: element.getBoundingClientRect().width,
      label: element.getAttribute("aria-label") ?? "",
    }));
    expect(`${dimensions.height}px`).toBe(dimensions.token);
    expect(dimensions.width).toBeGreaterThanOrEqual(55);
    expect(dimensions.width).toBeLessThanOrEqual(74.5);
    expect(dimensions.label).toMatch(/Auto|Manual/);

    await trigger.focus();
    await trigger.press("ArrowDown");
    const menu = page.getByRole("menu", { name: "Visualize as" });
    await expect(menu).toBeVisible();
    const firstItem = menu.locator("[data-visualization-menu-item]").first();
    await expect(firstItem).toBeFocused();
    const firstText = (await firstItem.textContent())?.trim();
    await page.keyboard.press("ArrowDown");
    expect(await menu.evaluate(() => document.activeElement?.textContent?.trim() ?? "")).not.toBe(firstText);
    await page.keyboard.press("End");
    expect(await menu.evaluate(() => document.activeElement?.textContent?.trim() ?? "")).not.toBe("");
    await page.keyboard.press("Tab");
    expect(await menu.evaluate((element) => element.contains(document.activeElement))).toBe(true);
    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    await expect(trigger).toBeFocused();

    await trigger.click();
    await expect(menu).toBeVisible();
    const kinds = await menu.locator(".visualization-kind-mark.is-preview").evaluateAll((elements) => (
      Array.from(new Set(elements.map((element) => element.getAttribute("data-kind")))).filter(Boolean)
    ));
    expect(kinds.length).toBeGreaterThanOrEqual(8);
    const firstAlternative = menu.locator(".visualization-menu-section").filter({ hasText: "Alternatives" }).locator("button").first();
    await firstAlternative.click();
    await expect(trigger).toHaveAttribute("aria-label", /Manual/);

    await board.locator(".dashboard-board-title").click();
    const inspector = page.locator(".dashboard-inspector");
    await expect(inspector.locator("#board-visualization")).toBeVisible();
    await expect(inspector.locator(".visualization-inspector-chart-grid > button")).toHaveCount(10);
    await expect(inspector.locator(".visualization-inspector-chart-grid .visualization-kind-mark.is-preview")).toHaveCount(10);

    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    await page.setViewportSize({ width: 720, height: 500 });
    await trigger.scrollIntoViewIfNeeded();
    await trigger.click();
    await expect(menu).toBeVisible();
    const mobileBounds = await menu.boundingBox();
    expect(mobileBounds).not.toBeNull();
    expect(mobileBounds!.x).toBeGreaterThanOrEqual(0);
    expect(mobileBounds!.x + mobileBounds!.width).toBeLessThanOrEqual(720.5);
    expect(mobileBounds!.y).toBeGreaterThanOrEqual(0);
    expect(mobileBounds!.y + mobileBounds!.height).toBeLessThanOrEqual(500.5);
    await page.keyboard.press("Escape");

    expect(runtimeErrors).toEqual([]);
  } finally {
    if (boardId) {
      await page.setViewportSize({ width: 1440, height: 1000 });
      await ensureEditMode(page);
      const board = page.locator(`.dashboard-board-frame[data-board-id="${boardId}"]`);
      if (await board.count()) {
        await board.locator(".dashboard-board-more > summary").click();
        await board.getByRole("menuitem", { name: "삭제" }).dispatchEvent("click");
        await expect(board).toHaveCount(0);
        await savePreferences(page);
      }
    }
  }
});
