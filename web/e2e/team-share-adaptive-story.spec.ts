import { expect, test } from "@playwright/test";

const captureRoot = "public/team-share-adaptive-assets";

async function waitForStoryReady(page: import("@playwright/test").Page) {
  await expect(page.getByRole("heading", { name: /가입과 역할별 업무부터/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".adaptive-share-integrity strong")).toHaveText("team-share-adaptive-complete-integrity-20260805");
  await expect(page.locator(".adaptive-share-capture-card")).toHaveCount(17);
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

test("legacy team share remains unchanged and complete adaptive story is independently accessible", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/team-share");
  await expect(page.getByText("team-share-capture-integrity-20260804", { exact: true })).toBeVisible();
  await expect(page.getByText("team-share-adaptive-complete-integrity-20260805", { exact: true })).toHaveCount(0);

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/team-share-adaptive");
  await waitForStoryReady(page);
  await expect(page.getByRole("link", { name: "2026-08-04 기록", exact: true })).toHaveAttribute("href", "/team-share");
  await expect(page.locator(".adaptive-share-actions a.primary")).toHaveAttribute(
    "href",
    "/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/modeling",
  );
  await expect(page.getByRole("link", { name: /독립 HTML 열기/ })).toHaveAttribute("href", "/team-share-adaptive.html");
  await expect(page.getByText("Manufacturing Gold Fixture Demo — Equipment Registry + Risk Events", { exact: true })).toBeVisible();
  await expect(page.getByText("UCI AI4I 2020 Manufacturing Predictive Maintenance — Physics & Maintenance Canonical V3.1", { exact: true }).first()).toBeVisible();
  const sectionHeaderLayout = await page.locator("#foundation > header").evaluate((header) => {
    const heading = header.querySelector("h2");
    const description = header.querySelector("p");
    if (!heading || !description) return null;
    const headingRect = heading.getBoundingClientRect();
    const descriptionRect = description.getBoundingClientRect();
    return {
      display: getComputedStyle(header).display,
      headingBottom: headingRect.bottom,
      descriptionTop: descriptionRect.top,
      leftDelta: Math.abs(headingRect.left - descriptionRect.left),
    };
  });
  expect(sectionHeaderLayout).not.toBeNull();
  expect(sectionHeaderLayout?.display).toBe("block");
  expect(sectionHeaderLayout?.descriptionTop ?? 0).toBeGreaterThanOrEqual(sectionHeaderLayout?.headingBottom ?? 0);
  expect(sectionHeaderLayout?.leftDelta ?? 999).toBeLessThanOrEqual(1);
  await page.screenshot({ path: `${captureRoot}/00-team-share-adaptive-story.png`, fullPage: true, animations: "disabled", caret: "hide" });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await waitForStoryReady(page);
  const geometry = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(geometry.width).toBeLessThanOrEqual(geometry.viewport + 1);
  await page.screenshot({ path: `${captureRoot}/00-team-share-adaptive-story-mobile.png`, fullPage: true, animations: "disabled", caret: "hide" });

  await page.goto("/team-share-adaptive.html");
  await expect(page.getByRole("heading", { name: /가입과 역할별 업무부터/ })).toBeVisible();
  await expect(page.locator("main img")).toHaveCount(7);
  await page.waitForFunction(() => Array.from(document.querySelectorAll<HTMLImageElement>('img[data-local="true"]')).every((image) => image.complete && image.naturalWidth > 0));
  await expect(page.getByRole("link", { name: "2026-08-04 기록 보기" })).toHaveAttribute("href", "/team-share");
});
