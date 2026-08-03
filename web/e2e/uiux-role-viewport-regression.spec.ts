import { expect, type Page, test } from "@playwright/test";
import { ROLE_VISUAL_CASES, VIEWPORT_VISUAL_CASES, VISUAL_PROJECT_ID } from "./uiux-role-viewport.manifest";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app(?:\/|$)|\/admin$/);
  await page.goto(`/app/projects/${VISUAL_PROJECT_ID}`);
  await expect(page.locator(".dashboard-board-canvas")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".dashboard-focus-toolbar")).toBeVisible();
}

for (const roleCase of ROLE_VISUAL_CASES) {
  for (const viewport of VIEWPORT_VISUAL_CASES) {
    test(`${roleCase.role} dashboard visual contract at ${viewport.name}`, async ({ page }) => {
      test.setTimeout(90_000);
      const runtimeErrors: string[] = [];
      page.on("pageerror", (error) => runtimeErrors.push(`page:${error.message}`));
      page.on("console", (message) => {
        if (
          message.type() === "error"
          && !message.text().includes("401")
          && !message.text().includes("403 (Forbidden)")
          && !message.text().includes("404 (Not Found)")
        ) runtimeErrors.push(`console:${message.text()}`);
      });
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.addInitScript(() => {
        localStorage.setItem("ontology-dashboard:locale", "ko-KR");
        localStorage.setItem("ontology-dashboard-theme", "light");
      });
      await login(page, roleCase.email, roleCase.password);

      const geometry = await page.evaluate(() => {
        const canvas = document.querySelector<HTMLElement>(".dashboard-canvas-region");
        const workspace = document.querySelector<HTMLElement>(".dashboard-workspace-layout");
        const meaningfulTinyText = Array.from(document.querySelectorAll<HTMLElement>("body *")).filter((element) => {
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          const text = (element.textContent ?? "").trim();
          if (!text || rect.width === 0 || rect.height === 0 || style.visibility === "hidden" || style.display === "none") return false;
          if (element.children.length > 0) return false;
          return Number.parseFloat(style.fontSize) < 9 && !element.classList.contains("fd-entity-title__eyebrow");
        }).length;
        return {
          scrollWidth: document.documentElement.scrollWidth,
          viewportWidth: window.innerWidth,
          canvasWidth: canvas?.getBoundingClientRect().width ?? 0,
          workspaceColumns: workspace ? getComputedStyle(workspace).gridTemplateColumns : "",
          meaningfulTinyText,
        };
      });

      expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
      expect(geometry.canvasWidth).toBeGreaterThan(viewport.name === "mobile" ? 360 : 500);
      expect(geometry.meaningfulTinyText).toBeLessThanOrEqual(viewport.name === "mobile" ? 14 : 8);
      if (viewport.name === "mobile") expect(geometry.workspaceColumns.trim().split(/\s+/)).toHaveLength(1);
      expect(runtimeErrors).toEqual([]);

      await expect(page).toHaveScreenshot(`${roleCase.role}-${viewport.name}.png`, {
        animations: "disabled",
        caret: "hide",
        maxDiffPixelRatio: 0.015,
        mask: [page.locator(".od-runtime-meta"), page.locator(".board-runtime-meta")],
      });
    });
  }
}
