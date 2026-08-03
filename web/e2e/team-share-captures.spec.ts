import { expect, type Page, test } from "@playwright/test";

const captureRoot = "../docs/00-team-onboarding/assets/screenshots";

async function screenshot(page: Page, name: string) {
  await page.addStyleTag({
    content: `
      *, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; caret-color: transparent !important; }
      time { visibility: hidden !important; }
    `,
  });
  await page.screenshot({
    path: `${captureRoot}/${name}.png`,
    fullPage: false,
    animations: "disabled",
    caret: "hide",
  });
}

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/(app(\/projects\/[^/]+)?|admin)$/);
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "로그아웃" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

test.use({ viewport: { width: 1440, height: 1000 }, colorScheme: "light" });

test("capture governed onboarding, role homes, adaptive workspaces, and analysis surfaces", async ({ page }) => {
  test.skip(process.env.CAPTURE_TEAM_SHARE !== "1", "Set CAPTURE_TEAM_SHARE=1 to refresh committed team-share screenshots.");
  test.setTimeout(300_000);

  const email = "team.member@example.com";
  const password = "TeamMemberApproval!2026";

  await page.goto("/register");
  await page.getByLabel("이름").fill("팀 공유 사용자");
  await page.getByLabel("업무 이메일").fill(email);
  await page.getByLabel("조직명 또는 초대 조직").fill("Ontology Demo Organization");
  await page.getByLabel("희망 역할").selectOption("process_engineer");
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("checkbox").check();
  await screenshot(page, "01-signup-role-request");
  await page.getByRole("button", { name: "가입 승인 요청" }).click();
  await expect(page.getByText("희망 역할 · process_engineer")).toBeVisible();
  await screenshot(page, "02-pending-approval");

  await login(page, "admin@ontology.local", "OntologyAdmin!2026");
  await page.getByRole("button", { name: /Notifications/ }).click();
  const notification = page.locator(".admin-notification-list button", { hasText: email });
  await expect(notification).toBeVisible();
  await screenshot(page, "03-admin-signup-notification");
  await notification.click();
  const row = page.locator(".admin-user-table tbody tr", { hasText: email });
  await expect(row).toBeVisible();
  await row.getByLabel(`${email} 역할`).selectOption("process_manager");
  await row.getByLabel(`${email} workspace`).selectOption("manufacturing-demo");
  await row.locator(".permission-override-editor summary").click();
  await row.getByLabel(`${email} dashboards.share 권한`).selectOption("deny");
  await screenshot(page, "04-admin-role-permission-confirmation");
  await row.getByRole("button", { name: "승인", exact: true }).click();
  await expect(page.locator(".admin-user-table tbody tr", { hasText: email }).locator(".account-status")).toHaveText("active", { timeout: 15_000 });

  await logout(page);
  await login(page, email, password);
  await expect(page.locator(".role-report-workbench")).toBeVisible({ timeout: 45_000 });
  await screenshot(page, "05-manager-report-home");
  await page.getByRole("button", { name: /Open detailed dashboard/ }).click();
  await expect(page.locator(".dashboard-board-canvas")).toBeVisible({ timeout: 45_000 });
  await screenshot(page, "06-manager-dashboard-drilldown");

  await logout(page);
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await expect(page.locator(".dashboard-board-canvas")).toBeVisible({ timeout: 45_000 });
  await screenshot(page, "07-engineer-dashboard-home");
  await page.getByRole("button", { name: "Reports", exact: true }).click();
  await page.getByRole("button", { name: "Edit report" }).click();
  await screenshot(page, "08-engineer-report-editor");
  await page.getByRole("button", { name: "Dashboards", exact: true }).click();
  const favorite = page.locator(".dashboard-board-favorite").first();
  await expect(favorite).toBeVisible();
  if (await favorite.getAttribute("aria-pressed") !== "true") await favorite.click();
  await expect(page.locator(".od-runtime-meta .personalized")).toContainText("Personalized for this user", { timeout: 15_000 });
  await page.locator(".od-display-menu > summary").first().click();
  await screenshot(page, "09-personalized-dashboard-display-settings");

  await logout(page);
  await login(page, "fde@ontology.local", "FDE!2026");
  await expect(page.locator('.ontology-dashboard-shell[data-adaptive-profile="factory-reliability"]')).toBeVisible({ timeout: 45_000 });
  await screenshot(page, "10-factory-adaptive-dashboard");
  await page.getByLabel("Project", { exact: true }).selectOption("azure-fleet-maintenance-project");
  await expect(page.locator('.ontology-dashboard-shell[data-adaptive-profile="fleet-maintenance"]')).toBeVisible({ timeout: 45_000 });
  await screenshot(page, "11-fleet-adaptive-dashboard");
  await page.getByLabel("Project", { exact: true }).selectOption("metropt-compressor-project");
  await expect(page.locator('.ontology-dashboard-shell[data-adaptive-profile="compressor-monitoring"]')).toBeVisible({ timeout: 45_000 });
  await screenshot(page, "12-compressor-adaptive-dashboard");

  await page.goto("/app/analysis/team-share-analysis");
  await expect(page.locator(".analysis-flow-canvas .react-flow")).toBeVisible({ timeout: 45_000 });
  await page.getByRole("button", { name: "Canvas", exact: true }).click();
  await expect(page.locator(".analysis-freeform-canvas")).toBeVisible();
  await screenshot(page, "13-analysis-canvas");
  await page.getByRole("button", { name: "Graph", exact: true }).click();
  await expect(page.locator(".analysis-dependency-graph .react-flow")).toBeVisible();
  await screenshot(page, "14-analysis-dependency-graph");

  await page.goto("/app/projects/metropt-compressor-project");
  await page.getByLabel("Project", { exact: true }).selectOption("manufacturing-demo-project");
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  await page.getByRole("button", { name: "Ontology", exact: true }).click();
  await expect(page.locator(".ontology-object-table .fd-resource-table__row").first()).toBeVisible({ timeout: 45_000 });
  const rowChecks = page.locator('.ontology-object-table input[type="checkbox"][aria-label^="Select "]:not([aria-label="Select all visible objects"])');
  await rowChecks.nth(0).check();
  await rowChecks.nth(1).check();
  await page.getByLabel("Selection merge mode").selectOption("union");
  await page.getByRole("button", { name: /Apply selection/ }).click();
  await expect(page.locator(".ontology-selection-banner")).toContainText("2 objects selected");
  await screenshot(page, "15-ontology-objectset-selection");
});
