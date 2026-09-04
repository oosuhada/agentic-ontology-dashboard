import { expect, type Page, test } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill("manager@ontology.local");
  await page.getByLabel("비밀번호").fill("Manager!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/projects\//);
}

test("keeps Original and Blueprint V1 while exposing the denser Blueprint V2 route", async ({ page }) => {
  await login(page);

  await page.goto("/app/projects/manufacturing-demo-project/blueprint");
  await expect(page.locator(".blueprint-preview")).toBeVisible();
  await expect(page.locator(".blueprint-v2")).toHaveCount(0);

  await page.goto("/app/projects/manufacturing-demo-project/blueprint-v2");
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project\/blueprint-v2$/);
  await expect(page.locator(".blueprint-v2")).toBeVisible();
  await expect(page.locator(".bpv2-navbar")).toBeVisible();
  await expect(page.locator(".bpv2-left-panel")).toBeVisible();
  await expect(page.locator(".bpv2-inspector")).toBeVisible();
  await expect(page.locator(".bpv2-object-table tbody tr").first()).toBeVisible();

  await page.getByRole("tab", { name: "Analysis" }).click();
  await expect(page.getByText("Transformation graph", { exact: true })).toBeVisible();
  await expect(page.locator(".bpv2-pipeline-step")).toHaveCount(5);

  await page.getByRole("tab", { name: "Operations" }).click();
  await expect(page.getByText("Decision inbox", { exact: true })).toBeVisible();
  await expect(page.locator(".bpv2-queue button")).toHaveCount(8);
});

test("Blueprint V2 keeps its workspaces inside a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto("/app/projects/manufacturing-demo-project/blueprint-v2");
  await expect(page.locator(".blueprint-v2")).toBeVisible();
  await expect(page.locator(".bpv2-left-panel")).toHaveCount(0);
  await expect(page.locator(".bpv2-inspector")).toHaveCount(0);

  for (const tab of ["Objects", "Analysis", "Operations"]) {
    await page.getByRole("tab", { name: tab }).click();
    const widths = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(widths.scroll).toBe(widths.client);
  }

  await page.getByRole("button", { name: "Object navigation" }).click();
  await expect(page.locator(".bpv2-left-panel")).toBeVisible();
  await page.getByRole("button", { name: "Close navigation" }).click();
  await page.getByRole("button", { name: "Inspector", exact: true }).last().click();
  await expect(page.locator(".bpv2-inspector")).toBeVisible();
});
