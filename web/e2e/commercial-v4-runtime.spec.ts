import { expect, type Page, test } from "@playwright/test";

async function login(page: Page, returnPath?: string) {
  await page.goto(returnPath ? `/login?returnTo=${encodeURIComponent(returnPath)}` : "/login");
  await page.getByLabel("이메일").fill("manager@ontology.local");
  await page.getByLabel("비밀번호").fill("Manager!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
}

test("preserves V1 through V3 and exposes an independent Commercial V4 composition", async ({ page }) => {
  const v4 = "/app/projects/manufacturing-demo-project/blueprint-v4";
  await login(page, v4);
  await expect(page).toHaveURL(new RegExp(`${v4}$`));
  await expect(page.locator('[data-application-id="ontology-commercial-v4"]')).toBeVisible();
  await expect(page.getByText("Commercial V4", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("V1–V3 preserved", { exact: true })).toBeVisible();
  await expect(page.getByText("Not the default route", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Actions & functions/ }).click();
  await expect(page.getByText("Planned · Phase 27", { exact: true })).toBeVisible();
  await expect(page.getByText(/does not present a simulated success state/)).toBeVisible();

  await page.getByRole("button", { name: /Identity & access/ }).click();
  await expect(page.getByText("Provider status", { exact: true })).toBeVisible();
  await expect(page.getByText("Enterprise OIDC", { exact: true })).toBeVisible();
  await expect(page.getByText("not configured", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Deployment/ }).click();
  await expect(page.getByText("Production topology", { exact: true })).toBeVisible();
  await expect(page.getByText("/health/ready", { exact: true })).toBeVisible();
  await expect(page.getByText("/app/projects/manufacturing-demo-project/blueprint-v4", { exact: true })).toBeVisible();

  await page.goto("/app/projects/manufacturing-demo-project");
  await expect(page.getByRole("heading", { name: "운영 매니저 운영 브리핑" })).toBeVisible();
  await expect(page.locator('[data-application-version="v4"]')).toHaveCount(0);

  for (const [path, selector] of [
    ["/app/projects/manufacturing-demo-project/blueprint", ".blueprint-preview"],
    ["/app/projects/manufacturing-demo-project/blueprint-v2", ".blueprint-v2"],
  ] as const) {
    await page.goto(path);
    await expect(page.locator(selector)).toBeVisible();
    await expect(page.locator('[data-application-version="v4"]')).toHaveCount(0);
  }
});

test("keeps the V4 manifest usable on a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "/app/projects/manufacturing-demo-project/blueprint-v4?surface=settings");
  await expect(page.locator('[data-application-version="v4"]')).toBeVisible();
  await expect(page.getByText("Version-scoped runtime", { exact: true })).toBeVisible();
  await expect(page.getByText("Tenant persistence readiness", { exact: true })).toBeVisible();
  await expect(page.getByText("Production PostgreSQL required", { exact: true })).toBeVisible();
  const widths = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(widths.scroll).toBe(widths.client);
});
