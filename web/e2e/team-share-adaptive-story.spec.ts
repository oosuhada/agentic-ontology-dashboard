import { expect, test } from "@playwright/test";

const captureRoot = "public/team-share-adaptive-assets";

async function waitForStoryReady(page: import("@playwright/test").Page) {
  await expect(page.getByRole("heading", { name: /Canonical V3.1의 데이터 계약에서/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".adaptive-share-integrity strong")).toHaveText("team-share-adaptive-capture-integrity-20260805");
  await expect(page.locator(".adaptive-share-capture-card")).toHaveCount(5);
  await page.waitForFunction(() => Array.from(document.images).every((image) => image.complete && image.naturalWidth > 0));
  await page.waitForFunction(() => {
    const visible = (element: Element) => {
      const node = element as HTMLElement;
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    };
    return !Array.from(document.querySelectorAll(".route-loading,.fd-state.state-loading,.mlv-loading")).some(visible);
  });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  });
  await page.addStyleTag({ content: "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}" });
}

test("legacy team share remains unchanged and adaptive release story is independently accessible", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/team-share");
  await expect(page.getByText("team-share-capture-integrity-20260804", { exact: true })).toBeVisible();
  await expect(page.getByText("team-share-adaptive-capture-integrity-20260805", { exact: true })).toHaveCount(0);

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/team-share-adaptive");
  await waitForStoryReady(page);
  await expect(page.getByRole("link", { name: "이전 Team Share" })).toHaveAttribute("href", "/team-share");
  await expect(page.getByRole("link", { name: /독립 HTML 열기/ })).toHaveAttribute("href", "/team-share-adaptive.html");
  await page.screenshot({ path: `${captureRoot}/00-team-share-adaptive-story.png`, fullPage: true, animations: "disabled", caret: "hide" });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await waitForStoryReady(page);
  const geometry = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(geometry.width).toBeLessThanOrEqual(geometry.viewport + 1);
  await page.screenshot({ path: `${captureRoot}/00-team-share-adaptive-story-mobile.png`, fullPage: true, animations: "disabled", caret: "hide" });

  await page.goto("/team-share-adaptive.html");
  await expect(page.getByRole("heading", { name: /Canonical V3.1의 데이터 계약에서/ })).toBeVisible();
  await expect(page.locator("main img")).toHaveCount(5);
  await page.waitForFunction(() => Array.from(document.images).every((image) => image.complete && image.naturalWidth > 0));
  await expect(page.getByRole("link", { name: "기존 자료와 비교" })).toHaveAttribute("href", "/team-share");
});
