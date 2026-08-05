import { expect, test } from "@playwright/test";

const captureRoot = "public/team-share-adaptive-assets";

async function waitForStoryReady(page: import("@playwright/test").Page) {
  await expect(page.getByRole("heading", { name: /가입과 역할별 업무부터/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".adaptive-share-integrity strong")).toHaveText("team-share-adaptive-v3.1-postgresql-20260805");
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

async function expectVerticalSectionHeaders(page: import("@playwright/test").Page) {
  const layouts = await page.locator(".adaptive-share-section > header").evaluateAll((headers) =>
    headers.map((header) => {
      const label = header.querySelector(":scope > span");
      const heading = header.querySelector(":scope > h2");
      const description = header.querySelector(":scope > p");
      if (!label || !heading || !description) return null;
      const labelRect = label.getBoundingClientRect();
      const headingRect = heading.getBoundingClientRect();
      const descriptionRect = description.getBoundingClientRect();
      return {
        display: getComputedStyle(header).display,
        labelBottom: labelRect.bottom,
        headingTop: headingRect.top,
        headingBottom: headingRect.bottom,
        descriptionTop: descriptionRect.top,
        leftDelta: Math.max(
          Math.abs(labelRect.left - headingRect.left),
          Math.abs(headingRect.left - descriptionRect.left),
        ),
      };
    }),
  );
  expect(layouts.length).toBeGreaterThan(0);
  for (const layout of layouts) {
    expect(layout).not.toBeNull();
    expect(layout?.display).toBe("block");
    expect(layout?.headingTop ?? 0).toBeGreaterThanOrEqual(layout?.labelBottom ?? 0);
    expect(layout?.descriptionTop ?? 0).toBeGreaterThanOrEqual(layout?.headingBottom ?? 0);
    expect(layout?.leftDelta ?? 999).toBeLessThanOrEqual(1);
  }
}

test("legacy team share remains unchanged and complete adaptive story is independently accessible", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/team-share");
  await expect(page.getByText("team-share-capture-integrity-20260804", { exact: true })).toBeVisible();
  await expect(page.getByText("team-share-adaptive-v3.1-postgresql-20260805", { exact: true })).toHaveCount(0);

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
  await expect(page.getByText("dsv-9fc144c7-d3f8-5b37-8465-04248165b7ce", { exact: false })).toBeVisible();
  await expect(page.getByText("68,208 timeline rows", { exact: false }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Quality", exact: true })).toHaveAttribute("href", "#quality");
  const modelingSection = page.locator("#modeling");
  const qualitySection = page.locator("#quality");
  await expect(modelingSection.getByRole("heading", { name: "운영 Dataset과 모델링 파이프라인의 준비 상태를 구분해 표시합니다" })).toBeVisible();
  await expect(modelingSection.locator(".adaptive-share-capture-card")).toHaveCount(2);
  await expect(modelingSection.getByText("DARK MODE USABILITY REGRESSION", { exact: true })).toHaveCount(0);
  await expect(qualitySection.getByRole("heading", { name: "화면 크기와 테마가 바뀌어도 정보와 가독성을 유지합니다" })).toBeVisible();
  await expect(qualitySection.locator(".adaptive-share-capture-card")).toHaveCount(2);
  await expect(qualitySection.getByText("DARK MODE USABILITY REGRESSION", { exact: true })).toBeVisible();
  await expectVerticalSectionHeaders(page);
  await page.screenshot({ path: `${captureRoot}/00-team-share-adaptive-story.png`, fullPage: true, animations: "disabled", caret: "hide" });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await waitForStoryReady(page);
  await expectVerticalSectionHeaders(page);
  const geometry = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(geometry.width).toBeLessThanOrEqual(geometry.viewport + 1);
  await page.screenshot({ path: `${captureRoot}/00-team-share-adaptive-story-mobile.png`, fullPage: true, animations: "disabled", caret: "hide" });

  await page.goto("/team-share-adaptive.html");
  await expect(page.getByRole("heading", { name: /가입과 역할별 업무부터/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "운영 Dataset과 모델링 파이프라인의 준비 상태를 구분해 표시합니다" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "화면 크기와 테마가 바뀌어도 정보와 가독성을 유지합니다" })).toBeVisible();
  await expect(page.locator("main img")).toHaveCount(7);
  await page.waitForFunction(() => Array.from(document.querySelectorAll<HTMLImageElement>('img[data-local="true"]')).every((image) => image.complete && image.naturalWidth > 0));
  await expect(page.getByRole("link", { name: "2026-08-04 기록 보기" })).toHaveAttribute("href", "/team-share");
});
