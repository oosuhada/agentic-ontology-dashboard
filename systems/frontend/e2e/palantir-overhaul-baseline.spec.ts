import { expect, type Page, test } from "@playwright/test";

const captureRoot = "../docs/ui/palantir-overhaul/baseline";
const captureEnabled = process.env.CAPTURE_PALANTIR_BASELINE === "1";

test.skip(!captureEnabled, "Set CAPTURE_PALANTIR_BASELINE=1 to intentionally refresh the pre-overhaul evidence set.");
const projectId = "manufacturing-demo-project";
const workspaceId = "manufacturing-demo";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
}

async function capture(page: Page, viewportName: string, name: string, route: string, readySelector: string) {
  await page.goto(route);
  await expect(page.locator(readySelector).first()).toBeVisible({ timeout: 45_000 });
  await page.screenshot({
    path: `${captureRoot}/${viewportName}/${name}.png`,
    fullPage: false,
    animations: "disabled",
  });
}

for (const viewport of [
  { name: "1440x1000", width: 1440, height: 1000 },
  { name: "1728x1117", width: 1728, height: 1117 },
  { name: "720x500", width: 720, height: 500 },
]) {
  test(`capture pre-overhaul baseline at ${viewport.name}`, async ({ page }) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await login(page, "fde@ontology.local", "FDE!2026");
    await expect(page).toHaveURL(/\/app\/projects\//);

    await capture(page, viewport.name, "dashboard", `/app/projects/${projectId}`, ".od-product-shell .react-grid-layout");
    await capture(page, viewport.name, "analysis", "/app/analysis/palantir-overhaul-baseline", ".analysis-flow-canvas .react-flow");
    await capture(page, viewport.name, "project-home", `/app/projects/${projectId}/home`, ".project-home-page");
    await capture(page, viewport.name, "agent", `/app/projects/${projectId}/workspaces/${workspaceId}/agent`, ".agent-workbench-page");
    await capture(page, viewport.name, "ontology", `/app/projects/${projectId}/workspaces/${workspaceId}/ontology`, ".ontology-workbench-page");
    await capture(page, viewport.name, "datasets", `/app/projects/${projectId}/datasets`, ".dataset-catalog-page");
    await capture(page, viewport.name, "governance", `/app/projects/${projectId}/workspaces/${workspaceId}/governance`, ".governance-workbench-page");

    await page.context().clearCookies();
    await login(page, "admin@ontology.local", "OntologyAdmin!2026");
    await expect(page).toHaveURL(/\/admin$/);
    await expect(page.locator(".admin-shell")).toBeVisible({ timeout: 45_000 });
    await page.screenshot({
      path: `${captureRoot}/${viewport.name}/admin.png`,
      fullPage: false,
      animations: "disabled",
    });
  });
}
