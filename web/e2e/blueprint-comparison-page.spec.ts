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
  await expect(page.locator(".comparison-preview-card")).toHaveCount(3);
  await expect(page.locator("iframe")).toHaveCount(3);

  const titles = await page.locator("iframe").evaluateAll((frames) => frames.map((frame) => frame.getAttribute("title")));
  expect(titles).toEqual([
    "기존 Dashboard live preview",
    "Blueprint V1 live preview",
    "Blueprint V2 live preview",
  ]);

  await expect(page.frameLocator('iframe[title="기존 Dashboard live preview"]').locator("body")).toBeVisible();
  await expect(page.frameLocator('iframe[title="Blueprint V1 live preview"]').locator(".blueprint-preview")).toBeVisible();
  await expect(page.frameLocator('iframe[title="Blueprint V2 live preview"]').locator(".blueprint-v2")).toBeVisible();

  await page.getByRole("button", { name: "Original ↔ V2" }).click();
  await expect(page.locator(".comparison-preview-card")).toHaveCount(2);
  await expect(page.locator('iframe[title="Blueprint V1 live preview"]')).toHaveCount(0);

  await page.getByRole("button", { name: "Blueprint V2", exact: true }).last().click();
  await expect(page.getByText("Blueprint V2 선택됨")).toBeVisible();
  await page.getByLabel("비교 판단 메모").fill("V2의 Object 중심 구조가 가장 명확하다.");
  await expect(page.getByLabel("비교 판단 메모")).toHaveValue("V2의 Object 중심 구조가 가장 명확하다.");
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
