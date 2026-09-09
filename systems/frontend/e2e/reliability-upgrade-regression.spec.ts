import { expect, type Page, test } from "@playwright/test";

const PROJECT = "manufacturing-demo-project";
const ENGINEERING_PATH = `/app/projects/${PROJECT}/operations/monitoring?view=overview&dashboard=workflow&role=field_operator&workspace_id=manufacturing-demo&workspace_shell=reliability`;

async function loginEngineer(page: Page, returnTo = ENGINEERING_PATH) {
  await page.goto(`/login?returnTo=${encodeURIComponent(returnTo)}`);
  await page.getByLabel(/이메일|Email/).fill("engineer@ontology.local");
  await page.getByLabel(/비밀번호|Password/).fill("Engineer!2026");
  await page.getByRole("button", { name: /로그인|Sign in/, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/app/projects/${PROJECT}/operations`), {
    timeout: 10_000,
  });
}

function reliabilityShell(page: Page) {
  return page.locator(".rw-preview-shell:not(.rw-preview-loading-placeholder)");
}

async function openFactoryStatus(page: Page) {
  const shell = reliabilityShell(page);
  await expect(shell).toBeVisible({ timeout: 15_000 });
  await shell
    .locator(".rw-preview-left nav button")
    .filter({ hasText: "설비 현황" })
    .click();
  await expect(shell).toHaveAttribute("data-active-surface", "factory-status");
  return shell;
}

test("acknowledges a factory alert and only auto-opens the drawer for an explicit deep link", async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("ontology-dashboard:reliability-locale", "ko-KR");
    window.localStorage.setItem("ontology-dashboard:reliability-theme", "light");
  });
  await loginEngineer(page);
  const shell = await openFactoryStatus(page);
  const factoryMap = shell.locator(".operations-factory-map-panel").first();
  const freshAlert = factoryMap.locator(".operations-factory-asset-node.has-alert").first();
  await expect(freshAlert).toBeVisible({ timeout: 15_000 });
  await expect(freshAlert.locator(".operations-asset-alert-badge")).toBeVisible();

  await freshAlert.click();
  const assetId = new URL(page.url()).searchParams.get("asset_id");
  const eventId = new URL(page.url()).searchParams.get("event_id");
  expect(assetId).toBeTruthy();

  const drawer = shell.getByRole("dialog", { name: "선택 설비 상세" });
  await expect(drawer).toBeVisible();
  await drawer.getByRole("button", { name: "선택 설비 상세 닫기" }).click();
  await expect(drawer).toBeHidden();

  const acknowledgedNode = factoryMap.locator(
    `.operations-factory-asset-node[aria-label*="${assetId}"]`,
  );
  await expect(acknowledgedNode).toHaveClass(/is-acknowledged/);
  await expect(acknowledgedNode.locator(".operations-asset-alert-badge")).toHaveCount(0);

  await page.reload();
  await expect(shell).toBeVisible({ timeout: 15_000 });
  await expect(shell.getByRole("dialog", { name: "선택 설비 상세" })).toBeHidden();
  const persistedNode = shell.locator(
    `.operations-factory-asset-node[aria-label*="${assetId}"]`,
  );
  await expect(persistedNode).toHaveClass(/is-acknowledged/);

  const deepLink = new URL(page.url());
  deepLink.searchParams.set("detail", "drawer");
  deepLink.searchParams.set("asset_id", assetId!);
  if (eventId) deepLink.searchParams.set("event_id", eventId);
  else deepLink.searchParams.delete("event_id");
  await page.goto(deepLink.toString());
  await expect(shell).toBeVisible({ timeout: 15_000 });
  const deepLinkedDrawer = shell.getByRole("dialog", { name: "선택 설비 상세" });
  await expect(deepLinkedDrawer).toBeVisible({ timeout: 15_000 });
  await deepLinkedDrawer.getByRole("button", { name: "선택 설비 상세 닫기" }).click();
  await expect(deepLinkedDrawer).toBeHidden();

  await shell
    .locator(".rw-preview-left nav button")
    .filter({ hasText: "설비 현황" })
    .click();
  await expect(shell).toHaveAttribute("data-active-surface", "factory-status");
  await expect(deepLinkedDrawer).toBeHidden();
});

test("distinguishes a live risk connection outage from an empty prediction range", async ({ page }) => {
  await page.route("**/predictive-maintenance/risk-index?**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "observation_dependency_unavailable",
          message: "observation store unavailable",
        },
      }),
    });
  });
  await page.addInitScript(() => {
    window.localStorage.setItem("ontology-dashboard:reliability-locale", "ko-KR");
    window.localStorage.setItem("ontology-dashboard:reliability-theme", "dark");
  });
  await loginEngineer(page);
  const shell = reliabilityShell(page);
  await expect(shell).toBeVisible({ timeout: 15_000 });
  await expect(shell).toHaveAttribute("data-active-surface", "monitoring");
  await expect(shell.getByText("위험 데이터 연결을 확인할 수 없음", { exact: true })).toBeVisible({
    timeout: 15_000,
  });
  await expect(shell.getByText("선택 범위에 위험 관측 없음", { exact: true })).toHaveCount(0);
  await expect(shell.getByText(/backend 또는 관측 저장소에 연결할 수 없습니다/)).toBeVisible();
});
