import { expect, type Page, test } from "@playwright/test";

const PROJECT = "manufacturing-demo-project";
const PATH = `/app/projects/${PROJECT}/operations?view=overview&dashboard=workflow&role=field_operator&workspace_id=manufacturing-demo&workspace_shell=reliability`;

async function login(page: Page) {
  await page.goto(`/login?returnTo=${encodeURIComponent(PATH)}`);
  await page.getByLabel(/이메일|Email/).fill("engineer@ontology.local");
  await page.getByLabel(/비밀번호|Password/).fill("Engineer!2026");
  await page.getByRole("button", { name: /로그인|Sign in/, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/app/projects/${PROJECT}/operations`), {
    timeout: 10_000,
  });
}

test("integrates monitoring risk, section minimap, and assistant execution activity without duplicating factory status", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.route("**/predictive-maintenance/risk-index?**", async (route) => {
    const url = new URL(route.request().url());
    const assetId = url.searchParams.get("asset_id");
    const window = url.searchParams.get("window") ?? "24h";
    const base = Date.parse("2026-09-05T08:00:00Z");
    const values = assetId
      ? [0.42, 0.47, 0.55, 0.63, 0.72, 0.81]
      : [0.58, 0.61, 0.67, 0.7, 0.76, 0.79];
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        project_id: PROJECT,
        workspace_id: "manufacturing-demo",
        asset_id: assetId,
        scope: assetId ? "asset" : "plant",
        aggregation: assetId ? "asset_bucket_mean" : "plant_failure_probability_p95",
        window,
        bucket_interval: window === "6h" ? "10 minutes" : "30 minutes",
        source_mode: "live",
        dataset_id: "dataset-live",
        dataset_version_id: "dsv-live",
        dataset_name: "Live Generator",
        source_version: "gen-data-wall-clock-live-v2",
        is_live_dataset: true,
        live_dataset_version_id: "dsv-live",
        workspace_dataset_version_id: "dsv-pinned",
        workspace_selection_mode: "explicit",
        workspace_selection_reason: "explicit_user_selection",
        workspace_is_pinned: true,
        latest_observed_at: "2026-09-05T08:00:00+00:00",
        data_age_seconds: 30,
        threshold: 0.75,
        threshold_kind: "operational_critical_boundary",
        points: values.map((value, index) => ({
          observed_at: new Date(base - (values.length - index - 1) * 30 * 60 * 1000).toISOString(),
          value,
          mean_risk: value * 0.72,
          max_risk: Math.min(0.99, value + 0.08),
          sample_count: 88,
          asset_count: assetId ? 1 : 88,
          critical_count: value >= 0.75 ? 4 : 0,
          status: value >= 0.75 ? "critical" : value >= 0.45 ? "warning" : "attention",
        })),
        point_count: values.length,
        empty_reason: null,
      }),
    });
  });
  await page.addInitScript(() => {
    window.localStorage.setItem("ontology-dashboard:reliability-locale", "ko-KR");
    window.localStorage.setItem("ontology-dashboard:reliability-theme", "dark");
  });
  await login(page);

  const shell = page.locator(".rw-preview-shell:not(.rw-preview-loading-placeholder)");
  await expect(shell).toBeVisible({ timeout: 15_000 });
  const factoryStatus = shell
    .locator(".rw-preview-left nav button")
    .filter({ hasText: "설비 현황" })
    .first();
  await expect(factoryStatus).toBeVisible();
  await factoryStatus.click();
  await expect(shell).toHaveAttribute("data-active-surface", "factory-status");
  await expect(shell.locator(".rw-market-workbench")).toHaveCount(0);

  const monitoring = shell
    .locator(".rw-preview-left nav button")
    .filter({ hasText: "모니터링" })
    .first();
  await expect(monitoring).toBeVisible();
  await monitoring.click();
  await expect(shell).toHaveAttribute("data-active-surface", "monitoring");

  const workbench = shell.locator(".rw-market-workbench");
  await expect(workbench).toBeVisible({ timeout: 15_000 });
  await expect(workbench.getByText("실시간 위험 지수", { exact: false })).toBeVisible();
  const bklitChart = workbench.locator('[data-chart-library="bklit-registry-derived"]');
  await expect(bklitChart).toHaveAttribute("data-bklit-source", "live-line-chart");
  await expect(workbench).toContainText("공장 위험 P95");

  const sectionRail = shell.locator(".rw-section-index");
  await expect(sectionRail).toBeVisible();
  await expect(sectionRail.locator("button")).toHaveCount(3);
  await sectionRail.locator("button").nth(1).hover();
  await expect(sectionRail.locator(".rw-section-index__preview")).toContainText("실시간 위험");
  const thirdSection = sectionRail.locator("button").nth(2);
  await thirdSection.click();
  await expect(thirdSection).toHaveClass(/is-active/);
  await expect(thirdSection).toHaveAttribute("aria-current", "location");
  await page.waitForTimeout(1_000);
  await expect(thirdSection).toHaveClass(/is-active/);
  await expect(sectionRail.locator("button").nth(1)).not.toHaveClass(/is-active/);

  await expect(workbench.locator(".rw-market-signal-row")).not.toHaveCount(0);
  await workbench.locator(".rw-market-signal-row").first().click();
  await expect(shell.locator(".rw-preview-selection-anchor")).toBeVisible();
  await expect(bklitChart.locator(".rw-bklit-risk-chart__svg")).toBeVisible({ timeout: 15_000 });
  await expect(bklitChart.locator(".rw-bklit-risk-chart__empty")).toHaveCount(0);
  const detailDrawer = shell.getByRole("dialog", { name: "선택 설비 상세" });
  if (await detailDrawer.isVisible()) {
    await detailDrawer.getByRole("button", { name: "선택 설비 상세 닫기" }).click();
    await expect(detailDrawer).toBeHidden();
  }

  await workbench.getByRole("button", { name: "6H", exact: true }).click();
  await expect(workbench.getByRole("button", { name: "6H", exact: true })).toHaveClass(/is-active/);
  await expect(workbench.locator(".rw-bklit-risk-chart__svg")).toBeVisible({ timeout: 15_000 });

  await shell.getByRole("button", { name: /Assistant/ }).click();
  const assistant = page.getByRole("dialog", { name: "Reliability Assistant" });
  await expect(assistant).toBeVisible();
  await assistant
    .getByRole("button", { name: "왜 이 설비가 이상으로 판단됐나요?", exact: true })
    .click();
  const completedMessage = assistant.locator(
    ".rw-context-assistant__message.is-assistant:not(.is-loading)",
  );
  await expect(completedMessage).toHaveCount(1, { timeout: 15_000 });
  await expect(completedMessage).not.toContainText("Team DB");
  await expect(completedMessage).not.toContainText("deterministic fallback");
  const activity = completedMessage.locator(".rw-assistant-trace");
  await expect(activity).toBeVisible();
  await expect(activity).toContainText("작업 기록");
  await expect(activity).toContainText("기록 저장됨");
  await expect(activity).toContainText("모델 내부 사고 과정은 포함하지 않습니다");

  await page.reload();
  const restoredShell = page.locator(".rw-preview-shell:not(.rw-preview-loading-placeholder)");
  await expect(restoredShell).toBeVisible({ timeout: 15_000 });
  await restoredShell.getByRole("button", { name: /Assistant/ }).click();
  const restoredAssistant = page.getByRole("dialog", { name: "Reliability Assistant" });
  await expect(restoredAssistant).toBeVisible();
  await expect(
    restoredAssistant.locator(".rw-context-assistant__message.is-user").getByText(
      "왜 이 설비가 이상으로 판단됐나요?",
      { exact: true },
    ),
  ).toBeVisible({ timeout: 15_000 });
  await expect(restoredAssistant.locator(".rw-assistant-trace")).toContainText("기록 저장됨");
});
