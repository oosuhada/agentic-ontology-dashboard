import { expect, type Page, test } from "@playwright/test";

const captureRoot = "../docs/ui/core-experience/final";

async function capture(page: Page, name: string) {
  await page.screenshot({ path: `${captureRoot}/${name}.png`, fullPage: false, animations: "disabled" });
}

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app(\/projects\/[^/]+)?$/);
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

test.use({ viewport: { width: 1440, height: 1000 }, colorScheme: "light" });

test("manager and executive-level roles land on a report and drill down to the dashboard", async ({ page }) => {
  await login(page, "manager@ontology.local", "Manager!2026");
  await expect(page.locator(".role-report-workbench")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator('.od-primary-nav button.active')).toContainText("Reports");
  await expect(page.getByRole("button", { name: /Open detailed dashboard/ })).toBeVisible();
  await capture(page, "manager-report-landing");

  const railBox = await page.locator(".fd-platform-shortcuts > span.active").boundingBox();
  const navBox = await page.locator(".od-primary-nav button.active").boundingBox();
  expect(railBox).not.toBeNull();
  expect(navBox).not.toBeNull();
  expect(Math.abs((railBox!.y + railBox!.height / 2) - (navBox!.y + navBox!.height / 2))).toBeLessThanOrEqual(3);

  await page.getByRole("button", { name: /Open detailed dashboard/ }).click();
  await expect(page.locator(".dashboard-board-canvas")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator('.od-primary-nav button.active')).toContainText("Dashboards");
  await capture(page, "manager-dashboard-drilldown");
  await logout(page);
  await login(page, "manager@ontology.local", "Manager!2026");
  await expect(page.locator(".role-report-workbench")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator('.od-primary-nav button.active')).toContainText("Reports");
});

test("practitioner edits a shared report revision that a manager reads", async ({ page }) => {
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await expect(page.locator(".dashboard-board-canvas")).toBeVisible({ timeout: 45_000 });
  await page.getByRole("button", { name: "Reports", exact: true }).click();
  await expect(page.locator(".role-report-workbench")).toBeVisible();
  await page.getByRole("button", { name: "Edit report" }).click();
  await capture(page, "engineer-report-editor");
  const headline = `Engineer-reviewed report ${Date.now()}`;
  await page.locator(".role-report-headline-input").fill(headline);
  await page.locator(".role-report-summary-input").fill("공정 엔지니어가 근거와 점검 결과를 검토한 공유 보고서입니다.");
  await page.getByRole("button", { name: "Save report" }).click();
  await expect(page.getByText(/공용 보고서 revision 1/)).toBeVisible();
  await capture(page, "engineer-report-saved");

  await logout(page);
  await login(page, "manager@ontology.local", "Manager!2026");
  await expect(page.locator(".role-report-workbench h1")).toHaveText(headline, { timeout: 45_000 });
  await expect(page.getByRole("button", { name: "Edit report" })).toHaveCount(0);

  await logout(page);
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await expect(page.locator(".dashboard-board-canvas")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator('.od-primary-nav button.active')).toContainText("Dashboards");
});

test("project and dataset profile changes the workspace composition", async ({ page }) => {
  await login(page, "fde@ontology.local", "FDE!2026");
  await expect(page.locator('.ontology-dashboard-shell[data-adaptive-profile="factory-reliability"]')).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".dashboard-board-frame").first()).toBeVisible({ timeout: 45_000 });
  const factoryDefinitions = await page.locator(".dashboard-board-frame").evaluateAll((items) => items.map((item) => item.getAttribute("data-definition-id")));

  await page.getByLabel("Project", { exact: true }).selectOption("azure-fleet-maintenance-project");
  await expect(page.locator('.ontology-dashboard-shell[data-adaptive-profile="fleet-maintenance"]')).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".adaptive-profile-strip")).toContainText("Fleet Maintenance Briefing");
  const fleetHero = page.locator(".dashboard-board-frame").first();
  await expect(fleetHero).toHaveAttribute("data-grid-w", "12");
  const fleetDefinitions = await page.locator(".dashboard-board-frame").evaluateAll((items) => items.map((item) => item.getAttribute("data-definition-id")));
  expect(fleetDefinitions).not.toEqual(factoryDefinitions);
  expect(fleetDefinitions).toContain("impact-summary");
  await capture(page, "fleet-adaptive-dashboard");

  await page.getByLabel("Project", { exact: true }).selectOption("metropt-compressor-project");
  await expect(page.locator('.ontology-dashboard-shell[data-adaptive-profile="compressor-monitoring"]')).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".adaptive-profile-strip")).toContainText("Compressor Condition Monitor");
  const compressorHero = page.locator(".dashboard-board-frame").first();
  await expect(compressorHero).toHaveAttribute("data-grid-w", "8");
  const compressorDefinitions = await page.locator(".dashboard-board-frame").evaluateAll((items) => items.map((item) => item.getAttribute("data-definition-id")));
  expect(compressorDefinitions).not.toEqual(fleetDefinitions);
  expect(compressorDefinitions).toContain("sensor-line-chart");
  expect(compressorDefinitions).toContain("anomaly-timeline");
  await capture(page, "compressor-adaptive-dashboard");
});

test("personal dashboard preference autosaves, restores, and does not leak between users", async ({ page }) => {
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await expect(page.locator(".dashboard-board-favorite").first()).toBeVisible({ timeout: 45_000 });
  const favorite = page.locator(".dashboard-board-favorite").first();
  if (await favorite.getAttribute("aria-pressed") === "true") await favorite.click();
  await favorite.click();
  await expect(favorite).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".od-runtime-meta .personalized")).toContainText("Personalized for this user", { timeout: 15_000 });

  await page.reload();
  await expect(page.locator(".dashboard-board-favorite").first()).toHaveAttribute("aria-pressed", "true", { timeout: 45_000 });
  await page.getByRole("button", { name: "Reports", exact: true }).click();
  await logout(page);

  await login(page, "technician@ontology.local", "Technician!2026");
  await expect(page.locator(".dashboard-board-canvas")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator('.od-primary-nav button.active')).toContainText("Dashboards");
  await expect(page.locator(".od-runtime-meta .role-default")).toContainText("Role default");
});

test("display preferences restore from the user account after local storage is cleared", async ({ page }) => {
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await page.locator(".od-display-menu > summary").first().click();
  await page.getByRole("button", { name: /Accessible/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-text-size", "large");
  await expect(page.locator("html")).toHaveAttribute("data-density", "comfortable");
  await page.waitForTimeout(700);

  await logout(page);
  await page.evaluate(() => window.localStorage.clear());
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await expect(page.locator("html")).toHaveAttribute("data-text-size", "large", { timeout: 15_000 });
  await expect(page.locator("html")).toHaveAttribute("data-density", "comfortable");

  await logout(page);
  await page.evaluate(() => window.localStorage.clear());
  await login(page, "technician@ontology.local", "Technician!2026");
  await expect(page.locator("html")).toHaveAttribute("data-text-size", "default", { timeout: 15_000 });
  await expect(page.locator("html")).toHaveAttribute("data-density", "standard");
});
