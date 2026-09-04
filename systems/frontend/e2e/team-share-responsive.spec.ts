import { expect, test } from "@playwright/test";

const viewports = [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "tablet-landscape", width: 1024, height: 768 },
  { name: "tablet-portrait", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
] as const;

for (const viewport of viewports) {
  test(`team share story remains usable at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/team-share");

    await expect(page.getByRole("heading", { name: /데이터를 보여주는 Dashboard가 아니라/ })).toBeVisible();
    await expect(page.locator(".team-share-story-header")).toBeVisible();
    await expect(page.locator(".team-share-flow-switcher button")).toHaveCount(6);
    await expect(page.locator(".team-share-role-tabs button")).toHaveCount(3);
    await expect(page.locator(".team-share-dataset-tabs button")).toHaveCount(3);

    const geometry = await page.evaluate(() => ({
      viewportWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      headerBottom: document.querySelector<HTMLElement>(".team-share-story-header")?.getBoundingClientRect().bottom ?? 0,
    }));
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
    expect(geometry.bodyScrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
    expect(geometry.headerBottom).toBeGreaterThan(0);

    await page.getByRole("tab", { name: /06 각 사용자의 화면 설정/ }).click();
    await expect(page.getByText("동일 역할 사용자 격리", { exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "엔지니어·실무자" }).click();
    await expect(page.getByText("Adaptive Dashboard", { exact: true })).toBeVisible();
    await page.getByRole("tab", { name: /Fleet Maintenance/ }).click();
    await expect(page.getByText("Fleet Event Grid", { exact: true })).toBeVisible();

    const firstScreenshot = page.locator(".team-share-screenshot img").first();
    await expect(firstScreenshot).toBeVisible();
    const imageBox = await firstScreenshot.boundingBox();
    expect(imageBox).not.toBeNull();
    expect(imageBox!.width).toBeGreaterThan(viewport.width <= 390 ? 320 : 480);

    if (process.env.CAPTURE_TEAM_SHARE === "1" && viewport.name === "mobile") {
      await page.screenshot({
        path: "../docs/00-team-onboarding/assets/screenshots/00-team-share-story-mobile.png",
        fullPage: true,
        animations: "disabled",
      });
    }
  });
}
