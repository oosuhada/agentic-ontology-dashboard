import { expect, test } from "@playwright/test";

test("display language switches common workbench actions and persists", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("이메일").fill("manager@ontology.local");
  await page.getByLabel("비밀번호").fill("Manager!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page.locator(".dashboard-board-canvas")).toBeVisible({ timeout: 30_000 });

  await page.locator(".od-display-menu > summary").click();
  const display = page.getByRole("dialog", { name: "화면 설정" });
  await display.getByRole("button", { name: "English", exact: true }).click();
  await expect(page.getByRole("button", { name: "View", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save view", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "View", exact: true })).toBeVisible({ timeout: 30_000 });

  await page.locator(".od-display-menu > summary").click();
  await page.getByRole("dialog", { name: "Display settings" }).getByRole("button", { name: "한국어", exact: true }).click();
  await expect(page.getByRole("button", { name: "보기", exact: true })).toBeVisible();
});
