import { expect, type Page, test } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill("manager@ontology.local");
  await page.getByLabel("비밀번호").fill("Manager!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/projects\//);
}

test("renders three live project versions and supports pair comparison", async ({ page }) => {
  await login(page);
  await page.goto("/app/projects/manufacturing-demo-project/blueprint-compare");

  await expect(page.getByRole("heading", { name: "세 화면을 같은 조건에서 비교하세요" })).toBeVisible();
  const primaryGrid = page.locator(".blueprint-comparison-page > .comparison-live-grid");
  await expect(primaryGrid.locator(".comparison-preview-card")).toHaveCount(3);
  await expect(primaryGrid.locator("iframe")).toHaveCount(3);
  await expect(primaryGrid.locator('iframe[src*="comparison_embed=1"]')).toHaveCount(3);

  const titles = await primaryGrid.locator("iframe").evaluateAll((frames) => frames.map((frame) => frame.getAttribute("title")));
  expect(titles).toEqual([
    "V1 · 기존 Dashboard live preview",
    "V2 · Blueprint 1차 live preview",
    "V3 · Blueprint 2차 live preview",
  ]);

  await expect(page.frameLocator('iframe[title="V1 · 기존 Dashboard live preview"]').locator("body")).toBeVisible();
  await expect(page.frameLocator('iframe[title="V2 · Blueprint 1차 live preview"]').locator(".blueprint-preview")).toBeVisible();
  await expect(page.frameLocator('iframe[title="V3 · Blueprint 2차 live preview"]').locator(".blueprint-v2")).toBeVisible();
  await expect(page.frameLocator('iframe[title="V1 · 기존 Dashboard live preview"]').getByLabel("이메일")).toHaveCount(0);
  await expect(page.frameLocator('iframe[title="V2 · Blueprint 1차 live preview"]').getByLabel("이메일")).toHaveCount(0);
  await expect(page.frameLocator('iframe[title="V3 · Blueprint 2차 live preview"]').getByLabel("이메일")).toHaveCount(0);
  await expect(primaryGrid.locator("iframe.is-ready")).toHaveCount(3);

  await expect(page.getByRole("button", { name: "V1 · 기존 Dashboard 열기" })).toBeVisible();
  await expect(page.getByRole("button", { name: "V2 · Blueprint 1차 열기" })).toBeVisible();
  await expect(page.getByRole("button", { name: "V3 · Blueprint 2차 열기" })).toBeVisible();

  await expect(page.locator(".comparison-scenario-section")).toHaveCount(4);
  await expect(page.getByRole("heading", { name: "첫 화면과 운영 개요 비교" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Object Explorer 비교" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Analysis Workbench 비교" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "운영 판단과 Action 비교" })).toBeVisible();

  await page.getByRole("heading", { name: "Object Explorer 비교" }).scrollIntoViewIfNeeded();
  await expect(page.locator('iframe[title="Object Explorer 비교 · V1 · 기존 Dashboard live preview"]')).toBeVisible();
  await expect(page.locator('iframe[title="Object Explorer 비교 · V2 · Blueprint 1차 live preview"]')).toBeVisible();
  await expect(page.locator('iframe[title="Object Explorer 비교 · V3 · Blueprint 2차 live preview"]')).toBeVisible();

  await page.getByRole("button", { name: "V1 ↔ V3" }).click();
  await expect(primaryGrid.locator(".comparison-preview-card")).toHaveCount(2);
  await expect(primaryGrid.locator('iframe[title="V2 · Blueprint 1차 live preview"]')).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "최종 후보와 판단 메모" })).toHaveCount(0);
});

test("comparison page stays within the mobile document width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto("/app/projects/manufacturing-demo-project/blueprint-compare");
  await expect(page.locator(".blueprint-comparison-page")).toBeVisible();
  const width = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(width.scroll).toBe(width.client);
});
