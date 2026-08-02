import { expect, type Locator, type Page, test } from "@playwright/test";

const projectId = "manufacturing-demo-project";
const workspaceId = "manufacturing-demo";
const captureRoot = "../docs/ui/palantir-overhaul/stage-04";

async function login(page: Page, email = "fde@ontology.local", password = "FDE!2026") {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/(app\/projects|admin)/);
}

async function roundedBox(locator: Locator) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return {
    width: Math.round(box?.width ?? 0),
    height: Math.round(box?.height ?? 0),
  };
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

test.use({ colorScheme: "light" });

test("Foundry shell and dashboard primitives use the compact geometry", async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);
  await expect(page.locator(".od-product-shell .react-grid-layout")).toBeVisible({ timeout: 45_000 });

  expect(await roundedBox(page.locator(".od-global-topbar"))).toEqual({ width: 1232, height: 40 });
  expect((await roundedBox(page.locator(".od-primary-sidebar"))).width).toBe(208);

  const toolbar = await roundedBox(page.locator(".dashboard-tab-toolbar"));
  expect(toolbar.height).toBeGreaterThanOrEqual(34);
  expect(toolbar.height).toBeLessThanOrEqual(38);
  expect((await roundedBox(page.locator(".dashboard-board-header").first())).height).toBe(32);
  expect((await roundedBox(page.locator(".generic-data-table-body > button").first())).height).toBe(30);

  await expect(page.locator(".fd-filter-chips")).toBeVisible();
  await expect(page.locator(".fd-status-pill.runtime-state").first()).toContainText(/ready|querying/);
  await expect(page.locator(".board-runtime-footer").first()).toContainText(/template|latest_published|pinned/);

  await page.getByTitle("사이드바 접기").click();
  await expect.poll(async () => (await roundedBox(page.locator(".od-primary-sidebar"))).width).toBe(48);
  await page.getByTitle("사이드바 펼치기").click();
  await expect.poll(async () => (await roundedBox(page.locator(".od-primary-sidebar"))).width).toBe(208);
});

test("shared route shell keeps workbench navigation and theme behavior", async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);

  await page.getByRole("button", { name: "Project Home", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/app/projects/${projectId}/home$`));
  await expect(page.locator(".fd-route-shell.route-home")).toBeVisible();
  expect((await roundedBox(page.locator(".od-global-topbar"))).height).toBe(40);
  await expect(page.getByRole("navigation", { name: "Product navigation", exact: true })).toBeVisible();
  await expect(page.getByRole("main")).toHaveCount(1);

  await page.getByRole("button", { name: "Datasets", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/app/projects/${projectId}/datasets$`));
  await expect(page.locator(".fd-route-shell.route-datasets")).toBeVisible();
  await expect(page.getByText("DATASET CATALOG", { exact: true })).toBeVisible();

  await page.getByTitle("테마 전환").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

  await page.keyboard.press("Control+K");
  const palette = page.getByRole("dialog", { name: "Command palette" });
  await expect(palette).toBeVisible();
  await palette.getByRole("button", { name: /Ontology/ }).click();
  await expect(page).toHaveURL(new RegExp(`/app/projects/${projectId}/workspaces/${workspaceId}/ontology$`));
  await expect(page.locator(".fd-route-shell.route-ontology")).toBeVisible();
});

test("dashboard filter rail and board interactions remain functional", async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page, "manager@ontology.local", "Manager!2026");

  const chips = page.getByRole("group", { name: "상태 필터 바로가기" });
  await expect(chips).toBeVisible();
  const chipButtons = chips.getByRole("button");
  expect(await chipButtons.count()).toBeGreaterThan(1);
  await chipButtons.nth(1).click();
  await expect(page.locator(".parameter-state-list")).not.toContainText("all");

  await page.locator(".generic-data-table-body > button").first().click();
  await expect(page.locator(".cross-filter-summary")).toContainText("active cross-filter");
  await expect(page.locator(".dashboard-board-frame.is-affected").first()).toBeVisible();

  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(page.getByText("Board Inspector", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Undo dashboard edit" })).toBeVisible();
});

test("720px viewport has one main landmark and no document overflow across workbenches", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 720, height: 500 });
  await login(page);

  const routes = [
    [`/app/projects/${projectId}`, ".od-product-shell"],
    [`/app/analysis/foundry-overhaul-mobile`, ".analysis-flow-canvas"],
    [`/app/projects/${projectId}/home`, ".project-home-page"],
    [`/app/projects/${projectId}/workspaces/${workspaceId}/agent`, ".agent-workbench-page"],
    [`/app/projects/${projectId}/workspaces/${workspaceId}/ontology`, ".ontology-workbench-page"],
    [`/app/projects/${projectId}/datasets`, ".dataset-catalog-page"],
    [`/app/projects/${projectId}/workspaces/${workspaceId}/governance`, ".governance-workbench-page"],
  ] as const;

  for (const [route, readySelector] of routes) {
    await page.goto(route);
    await expect(page.locator(readySelector).first()).toBeVisible({ timeout: 45_000 });
    await expect(page.getByRole("main")).toHaveCount(1);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(2);
  }
});

for (const viewport of [
  { name: "1440x1000", width: 1440, height: 1000 },
  { name: "1728x1117", width: 1728, height: 1117 },
  { name: "720x500", width: 720, height: 500 },
]) {
  test(`capture UI-04 after surfaces at ${viewport.name}`, async ({ page }) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await login(page);

    await capture(page, viewport.name, "dashboard", `/app/projects/${projectId}`, ".od-product-shell .react-grid-layout");
    await capture(page, viewport.name, "analysis", "/app/analysis/foundry-overhaul-capture", ".analysis-flow-canvas .react-flow");
    await capture(page, viewport.name, "project-home", `/app/projects/${projectId}/home`, ".project-home-page");
    await capture(page, viewport.name, "agent", `/app/projects/${projectId}/workspaces/${workspaceId}/agent`, ".agent-workbench-page");
    await capture(page, viewport.name, "ontology", `/app/projects/${projectId}/workspaces/${workspaceId}/ontology`, ".ontology-workbench-page");
    await capture(page, viewport.name, "datasets", `/app/projects/${projectId}/datasets`, ".dataset-catalog-page");
    await capture(page, viewport.name, "governance", `/app/projects/${projectId}/workspaces/${workspaceId}/governance`, ".governance-workbench-page");

    await page.context().clearCookies();
    await login(page, "admin@ontology.local", "OntologyAdmin!2026");
    await expect(page.locator(".admin-shell")).toBeVisible({ timeout: 45_000 });
    await page.screenshot({
      path: `${captureRoot}/${viewport.name}/admin.png`,
      fullPage: false,
      animations: "disabled",
    });
  });
}
