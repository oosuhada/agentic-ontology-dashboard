import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 1440, height: 1000 }, colorScheme: "light" });

test("team share story presents the verified user flow and interactive product tour", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/team-share");

  await expect(page.getByRole("heading", { name: /데이터를 보여주는 Dashboard가 아니라/ })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Team handoff sections" })).toBeVisible();
  await expect(page.locator(".team-share-flow-switcher button")).toHaveCount(6);
  await expect(page.locator(".team-share-workbench-grid article")).toHaveCount(3);
  await expect(page.locator(".team-share-capability-grid article")).toHaveCount(6);
  await expect(page.getByText("team-share-audit-ready-20260804", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: /02 관리자가 알림을 받고/ }).click();
  await expect(page.getByRole("heading", { name: "관리자가 알림을 받고 역할·범위·권한을 확정합니다" })).toBeVisible();
  await expect(page.getByText("permission override", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "엔지니어·실무자" }).click();
  await expect(page.getByText("Adaptive Dashboard", { exact: true })).toBeVisible();
  await expect(page.getByText("Dashboard 분석 · Ontology 탐색 · Analysis 작성 · 보고서 편집", { exact: true })).toBeVisible();

  await page.getByRole("tab", { name: /Compressor Monitoring/ }).click();
  await expect(page.getByText("Sensor Line Chart", { exact: true })).toBeVisible();
  await expect(page.getByText("8:4 대형 시계열 + 이상 탐지 구성", { exact: true })).toBeVisible();

  await page.locator(".team-share-screenshot button").first().click();
  await expect(page.getByRole("dialog", { name: /확대 보기/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: /확대 보기/ })).toHaveCount(0);

  await page.goto("/team-share#adaptive");
  await expect(page).toHaveURL(/#adaptive$/);
  await expect(page.locator('.team-share-story-header nav a[href="#adaptive"]')).toHaveAttribute("aria-current", "location");

  const images = page.locator(".team-share-story-page img");
  await expect(images).toHaveCount(6);
  await page.waitForFunction(() => [...document.images].every((image) => image.complete && image.naturalWidth > 0));

  await page.screenshot({
    path: "../docs/00-team-onboarding/assets/screenshots/00-team-share-story.png",
    fullPage: true,
    animations: "disabled",
  });
});
