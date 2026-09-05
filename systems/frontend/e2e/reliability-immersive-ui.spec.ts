import { expect, type Page, test } from "@playwright/test";

const PROJECT = "manufacturing-demo-project";
const PATH = `/app/projects/${PROJECT}/operations?view=overview&dashboard=workflow&role=process_manager&workspace_id=manufacturing-demo&workspace_shell=reliability`;

async function login(page: Page) {
  await page.goto(`/login?returnTo=${encodeURIComponent(PATH)}`);
  await page.getByLabel(/이메일|Email/).fill("manager@ontology.local");
  await page.getByLabel(/비밀번호|Password/).fill("Manager!2026");
  await page.getByRole("button", { name: /로그인|Sign in/, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/app/projects/${PROJECT}/operations`), {
    timeout: 10_000,
  });
}

test("connects the immersive risk index, hover context, and assistant execution activity", async ({ page }) => {
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

  const workbench = shell.locator(".rw-market-workbench");
  await expect(workbench).toBeVisible({ timeout: 15_000 });
  await expect(workbench.getByText("실시간 위험 지수", { exact: false })).toBeVisible();
  const bklitChart = workbench.locator('[data-chart-library="bklit-registry-derived"]');
  await expect(bklitChart).toHaveAttribute("data-bklit-source", "live-line-chart");
  await expect(workbench.locator(".rw-market-signal-row")).not.toHaveCount(0);
  await workbench.locator(".rw-market-signal-row").first().click();
  await expect(shell.locator(".rw-preview-selection-anchor")).toBeVisible();
  const detailDrawer = shell.getByRole("dialog", { name: "선택 설비 상세" });
  if (await detailDrawer.isVisible()) {
    await detailDrawer.getByRole("button", { name: "선택 설비 상세 닫기" }).click();
    await expect(detailDrawer).toBeHidden();
  }

  await workbench.getByRole("button", { name: "6H", exact: true }).click();
  await expect(workbench.getByRole("button", { name: "6H", exact: true })).toHaveClass(/is-active/);

  await factoryStatus.hover();
  const navPreview = page.locator(".rw-nav-context-popover");
  await expect(navPreview).toBeVisible();
  await expect(navPreview).toContainText("설비 현황");
  await expect(navPreview).toContainText("현재 화면");

  await shell.getByRole("button", { name: /Assistant/ }).click();
  const assistant = page.getByRole("dialog", { name: "Reliability Assistant" });
  await expect(assistant).toBeVisible();
  await assistant
    .getByRole("button", { name: "생산 영향은 어느 정도인가요?", exact: true })
    .click();
  const completedMessage = assistant.locator(
    ".rw-context-assistant__message.is-assistant:not(.is-loading)",
  );
  await expect(completedMessage).toHaveCount(1, { timeout: 15_000 });
  const activity = completedMessage.locator(".rw-assistant-trace");
  await expect(activity).toBeVisible();
  await expect(activity).toContainText("작업 기록");
  await expect(activity).toContainText("모델 내부 사고 과정은 포함하지 않습니다");
});
