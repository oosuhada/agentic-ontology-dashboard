import { expect, type Page, test } from "@playwright/test";
import {
  MODELING_ROUTE,
  SHARE_PROJECT,
  mockAdaptiveModelingApi,
  mockPredictiveMaintenanceApi,
} from "./fixtures/team-share-adaptive.fixture";

const captureRoot = "public/team-share-adaptive-assets";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app(?:\/|$)|\/admin$/);
}

async function waitForCaptureReady(page: Page, selector: string) {
  await expect(page.locator(selector).first()).toBeVisible({ timeout: 60_000 });
  await page.waitForFunction(() => {
    const transient = [
      ".route-loading",
      ".role-report-loading",
      ".role-report-refresh",
      ".loading-panel",
      ".fd-state.state-loading",
      ".fd-state.state-refreshing",
      ".visualization-switcher-skeleton",
      ".mlv-loading",
    ];
    const visible = (element: Element) => {
      const node = element as HTMLElement;
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    };
    const noTransient = transient.every((item) => !Array.from(document.querySelectorAll(item)).some(visible));
    const noBusy = !Array.from(document.querySelectorAll('[aria-busy="true"]')).some(visible);
    return noTransient && noBusy;
  }, { timeout: 60_000 });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(Array.from(document.images).map((image) => image.complete ? Promise.resolve() : new Promise<void>((resolve) => {
      image.addEventListener("load", () => resolve(), { once: true });
      image.addEventListener("error", () => resolve(), { once: true });
    })));
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  });
  await page.addStyleTag({ content: "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important} time{visibility:hidden!important}" });
}

async function capture(page: Page, filename: string, fullPage = false) {
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `${captureRoot}/${filename}`, fullPage, animations: "disabled", caret: "hide" });
}

test.use({ viewport: { width: 1440, height: 1000 }, colorScheme: "light" });

test("capture V3.1 runtime and replay without transient loaders", async ({ page }) => {
  test.skip(process.env.CAPTURE_TEAM_SHARE_ADAPTIVE !== "1", "Set CAPTURE_TEAM_SHARE_ADAPTIVE=1 to refresh captures.");
  test.setTimeout(180_000);
  await mockPredictiveMaintenanceApi(page);
  await login(page, "fde@ontology.local", "FDE!2026");
  await page.goto(`/app/projects/${SHARE_PROJECT}`);
  await waitForCaptureReady(page, ".pm-replay-panel");
  await expect(page.getByText("Predictive maintenance V3.1 runtime", { exact: true })).toBeVisible();
  await expect(page.getByText("Graph ready · 2,160 records", { exact: true })).toBeVisible();
  await capture(page, "01-v3-runtime-dashboard.png");

  await page.getByRole("button", { name: "Start replay", exact: true }).click();
  await expect(page.getByRole("button", { name: "Resume", exact: true })).toBeVisible();
  await expect(page.locator(".pm-replay-cursor")).toContainText("paused");
  await waitForCaptureReady(page, ".pm-replay-workbench");
  await page.locator(".pm-replay-panel").screenshot({ path: `${captureRoot}/02-v3-result-replay.png`, animations: "disabled", caret: "hide" });
});

test("capture ML Validator evaluation and release governance", async ({ page }) => {
  test.skip(process.env.CAPTURE_TEAM_SHARE_ADAPTIVE !== "1", "Set CAPTURE_TEAM_SHARE_ADAPTIVE=1 to refresh captures.");
  test.setTimeout(180_000);
  await mockAdaptiveModelingApi(page);
  await login(page, "datascientist@ontology.local", "DataScience!2026");
  await page.goto(MODELING_ROUTE);
  await waitForCaptureReady(page, ".mlv-shell");
  await expect(page.getByText("Validation leaderboard", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Validation precision recall curve")).toBeVisible();
  await capture(page, "03-ml-validator-desktop.png", true);

  await page.getByRole("tab", { name: "models", exact: true }).click();
  await expect(page.getByText("Model Registry", { exact: true })).toBeVisible();
  await waitForCaptureReady(page, ".mlv-model-list");
  await capture(page, "04-model-release-governance.png", true);
});

test("capture ML Validator mobile layout", async ({ page }) => {
  test.skip(process.env.CAPTURE_TEAM_SHARE_ADAPTIVE !== "1", "Set CAPTURE_TEAM_SHARE_ADAPTIVE=1 to refresh captures.");
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAdaptiveModelingApi(page);
  await login(page, "datascientist@ontology.local", "DataScience!2026");
  await page.goto(MODELING_ROUTE);
  await waitForCaptureReady(page, ".mlv-shell");
  await expect(page.getByText("Validation leaderboard", { exact: true })).toBeVisible();
  const geometry = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(geometry.width).toBeLessThanOrEqual(geometry.viewport + 1);
  await capture(page, "05-ml-validator-mobile.png", true);
});
