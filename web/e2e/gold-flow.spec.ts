import { expect, type Page, test } from "@playwright/test";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
}

test("manager and engineer accounts see different governed views for the same event", async ({ page }) => {
  await login(page, "manager@ontology.local", "Manager!2026");
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByText("Ontology Dashboard", { exact: true })).toBeVisible();
  await expect(page.getByText("Manufacturing Predictive Maintenance Pack", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /GS-002/ }).click();
  await expect(page.getByText("MANAGER DECISION VIEW")).toBeVisible();
  await expect(page.getByText("현장 점검 요청", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("예상 운영 영향")).toBeVisible();

  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await expect(page).toHaveURL(/\/app$/);
  await page.getByRole("button", { name: /GS-002/ }).click();
  await expect(page.getByText("ENGINEER EVIDENCE VIEW")).toBeVisible();
  await expect(page.getByText("센서 변화", { exact: true })).toBeVisible();
  await expect(page.getByText("주요 위험 근거", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "왜 위험한가?" }).click();
  await expect(page.getByText(/가장 큰 근거는 공구 마모/)).toBeVisible();
});

test("data-quality and provider fallback states remain usable after authentication", async ({ page }) => {
  await login(page, "manager@ontology.local", "Manager!2026");
  await page.getByRole("button", { name: /GS-007/ }).click();
  await expect(page.getByText("데이터 품질 경고", { exact: true })).toBeVisible();
  await expect(page.getByText(/정상 또는 고장으로 단정하지 않습니다/)).toBeVisible();

  await page.getByRole("button", { name: /GS-008/ }).click();
  await expect(page.locator(".mode-badge", { hasText: "deterministic_fallback" })).toBeVisible();
  await expect(page.getByText("공구 마모 위험", { exact: false }).first()).toBeVisible();
});

test("FDE is denied admin access while tenant admin can manage users", async ({ page }) => {
  await login(page, "fde@ontology.local", "FDE!2026");
  await expect(page.getByText("FDE WORKBENCH PREVIEW")).toBeVisible();
  await page.goto("/admin");
  await expect(page.getByText("관리자 권한이 없습니다")).toBeVisible();
  await expect(page.getByText(/FDE와 일반 사용자 역할/)).toBeVisible();

  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await login(page, "admin@ontology.local", "OntologyAdmin!2026");
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByText("관리자 Overview")).toBeVisible();
  await page.getByRole("button", { name: "Users", exact: true }).click();
  await expect(page.getByText("가입 승인·역할·Workspace scope")).toBeVisible();
  await expect(page.getByText("fde@ontology.local", { exact: true })).toBeVisible();
});

test("registration creates a pending approval account", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel("이름").fill("Playwright User");
  await page.getByLabel("업무 이메일").fill("playwright.user@example.com");
  await page.getByLabel("조직명 또는 초대 조직").fill("Playwright Factory");
  await page.getByLabel("비밀번호").fill("Playwright!2026");
  await page.getByLabel(/서비스 이용과 계정 승인 절차/).check();
  await page.getByRole("button", { name: "가입 승인 요청" }).click();
  await expect(page).toHaveURL(/\/pending/);
  await expect(page.getByText("가입 요청이 접수되었습니다")).toBeVisible();
  await expect(page.getByText("playwright.user@example.com")).toBeVisible();
});
