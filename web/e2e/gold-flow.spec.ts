import { expect, test } from "@playwright/test";

test("manager and engineer see different governed views for the same event", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Factory Signal Board", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /GS-002/ }).click();
  await expect(page.getByText("MANAGER DECISION VIEW")).toBeVisible();
  await expect(page.getByText("현장 점검 요청", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("예상 운영 영향")).toBeVisible();

  await page.getByRole("button", { name: "엔지니어", exact: true }).click();
  await expect(page.getByText("ENGINEER EVIDENCE VIEW")).toBeVisible();
  await expect(page.getByText("센서 변화", { exact: true })).toBeVisible();
  await expect(page.getByText("주요 위험 근거", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "왜 위험한가?" }).click();
  await expect(page.getByText(/가장 큰 근거는 공구 마모/)).toBeVisible();
});

test("data-quality and provider fallback states remain usable", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /GS-007/ }).click();
  await expect(page.getByText("데이터 품질 경고", { exact: true })).toBeVisible();
  await expect(page.getByText(/정상 또는 고장으로 단정하지 않습니다/)).toBeVisible();

  await page.getByRole("button", { name: /GS-008/ }).click();
  await expect(page.locator(".mode-badge", { hasText: "deterministic_fallback" })).toBeVisible();
  await expect(page.getByText("공구 마모 위험", { exact: false }).first()).toBeVisible();
});
