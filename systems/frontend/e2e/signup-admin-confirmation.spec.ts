import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 1440, height: 1000 }, colorScheme: "light" });

test("signup role request notifies admin and can be confirmed with role and permission changes", async ({ page }) => {
  const nonce = Date.now();
  const email = `flow.user.${nonce}@example.com`;
  const password = "FlowUserApproval!2026";

  await page.goto("/register");
  await page.getByLabel("이름").fill("사용자 흐름 검증");
  await page.getByLabel("업무 이메일").fill(email);
  await page.getByLabel("조직명 또는 초대 조직").fill("Ontology Demo Organization");
  await page.getByLabel("희망 역할").selectOption("process_engineer");
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "가입 승인 요청" }).click();
  await expect(page).toHaveURL(/\/pending/);
  await expect(page.getByText("희망 역할 · process_engineer")).toBeVisible();

  await page.goto("/login");
  await page.getByLabel("이메일").fill("admin@ontology.local");
  await page.getByLabel("비밀번호").fill("OntologyAdmin!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await page.getByRole("button", { name: /Notifications/ }).click();
  const notification = page.locator(".admin-notification-list button", { hasText: email });
  await expect(notification).toBeVisible();
  await expect(notification).toContainText("process_engineer");
  await notification.click();

  const row = page.locator(".admin-user-table tbody tr", { hasText: email });
  await expect(row).toBeVisible();
  const roleSelect = row.getByLabel(`${email} 역할`);
  await expect(roleSelect).toHaveValue("process_engineer");
  await roleSelect.selectOption("process_manager");
  await row.getByLabel(`${email} workspace`).selectOption("manufacturing-demo");
  await row.locator(".permission-override-editor summary").click();
  await row.getByLabel(`${email} dashboards.share 권한`).selectOption("deny");
  await row.getByRole("button", { name: "승인", exact: true }).click();
  const refreshedRow = page.locator(".admin-user-table tbody tr", { hasText: email });
  await expect(refreshedRow.locator(".account-status")).toHaveText("active", { timeout: 15_000 });
  await expect(refreshedRow.getByLabel(`${email} 역할`)).toHaveValue("process_manager");

  await page.getByRole("button", { name: "로그아웃" }).click();
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page.locator(".role-report-workbench")).toBeVisible({ timeout: 45_000 });
  await expect(page.locator('.od-primary-nav button.active')).toContainText("Reports");
});
