import { expect, test } from "@playwright/test";

test("role Dashboard supports focus, favorites, jump navigation and collapsed tray", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("이메일").fill("manager@ontology.local");
  await page.getByLabel("비밀번호").fill("Manager!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page.locator(".dashboard-focus-toolbar")).toBeVisible({ timeout: 30_000 });

  const allGridBoards = page.locator(".react-grid-item.dashboard-board-frame");
  const initialGridCount = await allGridBoards.count();
  expect(initialGridCount).toBeGreaterThan(2);

  const collapsedTray = page.locator(".dashboard-collapsed-board-tray");
  await expect(collapsedTray).toBeVisible();
  const collapsedBoard = collapsedTray.locator(".dashboard-board-frame").first();
  const collapsedTitle = (await collapsedBoard.locator(".dashboard-board-title strong").textContent())?.trim() ?? "";
  expect(collapsedTitle).not.toBe("");
  await collapsedBoard.getByRole("button", { name: new RegExp(`${collapsedTitle} 펼치기`) }).click();
  await expect(page.locator(".react-grid-item.dashboard-board-frame", { hasText: collapsedTitle })).toBeVisible();

  await page.getByRole("button", { name: "Focus", exact: true }).click();
  const focusCount = await allGridBoards.count();
  expect(focusCount).toBeLessThan(initialGridCount + 1);

  await page.getByRole("button", { name: "전체", exact: true }).click();
  const firstBoard = allGridBoards.first();
  const firstTitle = (await firstBoard.locator(".dashboard-board-title strong").textContent())?.trim() ?? "";
  await firstBoard.getByRole("button", { name: new RegExp(`${firstTitle} 즐겨찾기`) }).click();
  await page.getByRole("button", { name: "즐겨찾기", exact: true }).click();
  await expect(page.locator(".react-grid-item.dashboard-board-frame")).toHaveCount(1);
  await expect(page.locator(".react-grid-item.dashboard-board-frame").first()).toHaveAttribute("data-favorite", "true");

  await page.getByRole("button", { name: "전체", exact: true }).click();
  const jump = page.locator(".dashboard-focus-toolbar select");
  const options = await jump.locator("option").count();
  expect(options).toBeGreaterThan(2);
  await jump.selectOption({ index: 2 });
  await expect(jump).toHaveValue("");
});
