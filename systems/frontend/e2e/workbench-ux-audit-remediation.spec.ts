import { expect, type Page, test } from "@playwright/test";

const project = "/app/projects/manufacturing-demo-project";
const workspace = `${project}/workspaces/manufacturing-demo`;

async function login(page: Page, email: string, password: string) {
  await page.addInitScript(() => {
    localStorage.setItem("ontology-dashboard-theme", "dark");
    localStorage.setItem("ontology-dashboard:locale", "ko-KR");
  });
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app(?:\/|$)|\/admin$/);
}

test("dashboard, report, analysis, and agent surfaces preserve the audited UX fixes", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await page.goto(project);
  await expect(page.locator(".dashboard-board-canvas")).toBeVisible({ timeout: 60_000 });

  await expect(page.locator(".od-display-menu")).not.toHaveAttribute("open", "");
  await expect(page.locator(".od-display-popover")).toBeHidden();
  await expect(page.locator(".dashboard-context-tabs button")).toHaveCount(3);
  await page.locator(".dashboard-context-tabs button").filter({ hasText: "필터" }).click();
  await expect(page.getByText("상태 필터", { exact: true })).toBeVisible();
  await page.locator(".dashboard-context-tabs button").filter({ hasText: "Event" }).click();
  await expect(page.locator(".context-event-nav button").first()).toBeVisible();

  const fallbackBadge = page.locator(".mode-badge.fallback");
  if (await fallbackBadge.count()) await expect(page.locator(".dashboard-runtime-warning")).toBeVisible();

  await page.getByRole("button", { name: "리포트", exact: true }).click();
  await expect(page.getByRole("button", { name: "리포트 편집", exact: true })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "리포트 편집", exact: true }).click();
  await expect(page.getByRole("button", { name: "편집 취소", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "변경 되돌리기", exact: true })).toBeVisible();
  const headline = page.locator(".role-report-headline-input");
  await headline.fill(`${await headline.inputValue()} 변경`);
  await expect(page.getByText("저장되지 않은 변경", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "편집 취소", exact: true }).click();
  await expect(headline).toHaveCount(0);

  await page.goto("/app/analysis/risk-event-portfolio");
  await expect(page.locator(".analysis-board-rail")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".analysis-board-group button:disabled")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "사용할 수 없는 Board도 보기", exact: true })).toBeVisible();
  await expect(page.getByLabel("More analysis inspector sections")).toBeVisible();

  await page.goto(`${workspace}/agent`);
  await expect(page.locator(".agent-workbench-page")).toBeVisible({ timeout: 60_000 });
  const project3Warning = page.getByText(/Project 3.*Connection refused|Project 3.*unavailable/i);
  if (await project3Warning.count()) {
    await expect(page.locator('#agent-route option[value="graph"]')).toBeDisabled();
    await expect(page.locator('#agent-route option[value="hybrid"]')).toBeDisabled();
  }
});

test("dataset, governance, and project home expose safe and actionable information", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page, "admin@ontology.local", "OntologyAdmin!2026");

  await page.goto(`${project}/datasets`);
  await expect(page.locator(".dataset-catalog-page")).toBeVisible({ timeout: 60_000 });
  await page.getByLabel("More Dataset inspector sections").selectOption("files");
  await expect(page.locator("code.dataset-safe-uri").first()).toContainText("artifact://datasets/");
  await expect(page.locator("body")).not.toContainText("file:///Users/");
  await page.getByRole("button", { name: /Schema/ }).click();
  await expect(page.locator(".dataset-schema-table__row").first()).toBeVisible();

  await page.goto(`${workspace}/governance`);
  await expect(page.locator(".governance-workbench-page")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".governance-tabs")).toContainText("Projection 상태");
  await page.getByRole("button", { name: "접근 및 정책", exact: true }).click();
  await expect(page.locator(".governance-permission-groups details").first()).toBeVisible();

  await page.goto(`${project}/home`);
  await expect(page.locator(".project-home-attention-panel")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".project-workspace-actions > button")).toHaveCount(1);
  await expect(page.locator(".project-workspace-more")).toBeVisible();
});

test.describe("mobile touch targets", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("dataset controls meet the 44px target after responsive conversion", async ({ page }) => {
    await login(page, "admin@ontology.local", "OntologyAdmin!2026");
    await page.goto(`${project}/datasets`);
    await expect(page.locator(".dataset-catalog-page")).toBeVisible({ timeout: 60_000 });
    const undersized = await page.locator("button:visible,summary:visible,select:visible,input:visible").evaluateAll((nodes) => nodes.filter((element) => {
      const rect = element.getBoundingClientRect();
      return rect.width < 44 || rect.height < 44;
    }).map((element) => ({ text: element.textContent, rect: element.getBoundingClientRect().toJSON() })));
    expect(undersized).toEqual([]);
  });
});
