import { expect, type Locator, type Page, test } from "@playwright/test";

const projectId = "manufacturing-demo-project";

async function login(page: Page, email = "fde@ontology.local", password = "FDE!2026") {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page.locator(".od-product-shell .react-grid-layout")).toBeVisible({ timeout: 45_000 });
}

async function openDisplay(page: Page) {
  await page.locator('summary[aria-label="Display settings"]').click();
  return page.locator(".od-display-popover:visible");
}

async function gridValue(board: Locator, attribute: "x" | "y" | "w" | "h") {
  return Number(await board.getAttribute(`data-grid-${attribute}`));
}

async function dragBy(page: Page, handle: Locator, dx: number, dy: number) {
  await handle.scrollIntoViewIfNeeded();
  await page.waitForTimeout(120);
  const box = await handle.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move((box?.x ?? 0) + (box?.width ?? 0) / 2, (box?.y ?? 0) + (box?.height ?? 0) / 2);
  await page.mouse.down();
  await page.mouse.move((box?.x ?? 0) + (box?.width ?? 0) / 2 + dx, (box?.y ?? 0) + (box?.height ?? 0) / 2 + dy, { steps: 8 });
  await page.mouse.up();
}

test("Display settings are independent and persist for guest and authenticated user", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator("html")).toHaveAttribute("data-text-size", "default");
  await expect(page.locator("html")).toHaveAttribute("data-density", "compact");

  let display = await openDisplay(page);
  await display.getByRole("button", { name: "Large", exact: true }).click();
  await display.getByRole("button", { name: "Comfortable", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-text-size", "large");
  await expect(page.locator("html")).toHaveAttribute("data-density", "comfortable");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-text-size", "large");
  await expect(page.locator("html")).toHaveAttribute("data-density", "comfortable");

  await page.getByLabel("이메일").fill("fde@ontology.local");
  await page.getByLabel("비밀번호").fill("FDE!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page.locator(".react-grid-layout")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator("html")).toHaveAttribute("data-text-size", "default");
  await expect(page.locator("html")).toHaveAttribute("data-density", "compact");

  display = await openDisplay(page);
  await display.getByRole("button", { name: "Extra large", exact: true }).click();
  await display.getByRole("button", { name: "Standard", exact: true }).click();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-text-size", "extra-large");
  await expect(page.locator("html")).toHaveAttribute("data-density", "standard");

  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("이메일").fill("fde@ontology.local");
  await page.getByLabel("비밀번호").fill("FDE!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page.locator(".react-grid-layout")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator("html")).toHaveAttribute("data-text-size", "extra-large");
  await expect(page.locator("html")).toHaveAttribute("data-density", "standard");
});

test("long press enters one arrange state and board layout plus favorite persist", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page, "manager@ontology.local", "Manager!2026");
  const canvas = page.locator(".dashboard-board-canvas");
  const initialBoard = page.locator(".dashboard-board-frame").first();

  const interactive = initialBoard.locator(".dashboard-board-favorite");
  await interactive.dispatchEvent("pointerdown", { pointerId: 31, pointerType: "mouse", button: 0 });
  await page.waitForTimeout(560);
  await interactive.dispatchEvent("pointercancel", { pointerId: 31, pointerType: "mouse", button: 0 });
  await expect(canvas).toHaveAttribute("data-arrange-state", "view");

  const title = initialBoard.locator(".dashboard-board-title");
  const titleBox = await title.boundingBox();
  expect(titleBox).not.toBeNull();
  await page.mouse.move((titleBox?.x ?? 0) + 20, (titleBox?.y ?? 0) + 10);
  await page.mouse.down();
  await page.waitForTimeout(540);
  await page.mouse.up();
  await expect(canvas).toHaveAttribute("data-arrange-state", "arranging");
  await expect(page.locator(".ontology-dashboard-shell")).toHaveClass(/mode-edit/);

  const boardIndex = await page.locator(".dashboard-board-frame").evaluateAll((elements) => {
    const index = elements.findIndex((element) => {
      const x = Number(element.getAttribute("data-grid-x"));
      const w = Number(element.getAttribute("data-grid-w"));
      const h = Number(element.getAttribute("data-grid-h"));
      const maxW = Number(element.getAttribute("data-grid-max-w"));
      const maxH = Number(element.getAttribute("data-grid-max-h"));
      return x + w < 12 && w < maxW && h < maxH;
    });
    return index >= 0 ? index : 0;
  });
  let board = page.locator(".dashboard-board-frame").nth(boardIndex);
  const boardId = await board.getAttribute("data-board-id");
  expect(boardId).toBeTruthy();
  await expect(board.locator(".react-resizable-handle")).toHaveCount(8);
  expect(await board.evaluate((element) => getComputedStyle(element).animationName)).toBe("none");
  expect(await board.evaluate((element) => getComputedStyle(element, "::after").animationName)).toBe("od-board-jiggle");

  const before = {
    x: await gridValue(board, "x"),
    y: await gridValue(board, "y"),
    w: await gridValue(board, "w"),
    h: await gridValue(board, "h"),
  };

  await board.locator(".dashboard-board-favorite").click();
  await expect(board.locator(".dashboard-board-favorite")).toHaveAttribute("aria-pressed", "true");

  if (before.w < 12) {
    await dragBy(page, board.locator(".react-resizable-handle-e"), 70, 0);
    board = page.locator(`[data-board-id="${boardId}"]`);
    await expect.poll(() => gridValue(board, "w")).toBeGreaterThan(before.w);
  }
  if (before.h < 12) {
    await dragBy(page, board.locator(".react-resizable-handle-s"), 0, 150);
    board = page.locator(`[data-board-id="${boardId}"]`);
    await expect.poll(() => gridValue(board, "h")).toBeGreaterThan(before.h);
  }
  await dragBy(page, board.locator(".dashboard-board-drag-handle"), 55, 95);
  board = page.locator(`[data-board-id="${boardId}"]`);
  await expect.poll(async () => {
    const x = await gridValue(board, "x");
    const y = await gridValue(board, "y");
    return x !== before.x || y !== before.y;
  }).toBe(true);
  const finalLayout = {
    x: await gridValue(board, "x"),
    y: await gridValue(board, "y"),
    w: await gridValue(board, "w"),
    h: await gridValue(board, "h"),
  };

  await page.getByRole("button", { name: "개인 레이아웃 저장", exact: true }).click();
  await expect(page.getByRole("button", { name: "개인 레이아웃 저장됨", exact: true })).toBeDisabled({ timeout: 20_000 });
  await page.reload();
  await expect(page.locator(".react-grid-layout")).toBeVisible({ timeout: 45_000 });
  board = page.locator(`[data-board-id="${boardId}"]`);
  await expect(board.locator(".dashboard-board-favorite")).toHaveAttribute("aria-pressed", "true");
  expect(await gridValue(board, "w")).toBe(finalLayout.w);
  expect(await gridValue(board, "h")).toBe(finalLayout.h);
  expect(await gridValue(board, "x")).toBe(finalLayout.x);
  expect(await gridValue(board, "y")).toBe(finalLayout.y);

  await page.getByRole("button", { name: /Edit|Arrange/ }).click();
  await expect(canvas).toHaveAttribute("data-arrange-state", "arranging");
  await page.keyboard.press("Escape");
  await expect(canvas).toHaveAttribute("data-arrange-state", "view");
});

test("route loading exposes an accessible lifecycle operation", async ({ page }) => {
  await page.route("**/api/auth/me", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 650));
    await route.continue();
  });
  await page.goto("/login");
  await expect(page.getByRole("status", { name: "Checking session" })).toBeVisible();
  await expect(page.locator(".auth-card")).toBeVisible({ timeout: 10_000 });
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("arrange mode keeps boards static", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await login(page);
    expect(await page.evaluate(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);
    await page.getByRole("button", { name: /Edit|Arrange/ }).click();
    const board = page.locator(".dashboard-board-frame").first();
    expect(await board.evaluate((element) => getComputedStyle(element, "::after").animationName)).toBe("none");
  });
});

test("720px extra-large comfortable display has no document overflow", async ({ page }) => {
  await page.setViewportSize({ width: 720, height: 500 });
  await login(page);
  const display = await openDisplay(page);
  await display.getByRole("button", { name: "Extra large", exact: true }).click();
  await display.getByRole("button", { name: "Comfortable", exact: true }).click();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(await page.evaluate(() => window.innerWidth)).toBe(720);
  await expect(page.locator(".od-product-shell")).toBeVisible();
  await page.goto(`/app/projects/${projectId}`);
  await expect(page.locator(".react-grid-layout")).toBeVisible({ timeout: 45_000 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
