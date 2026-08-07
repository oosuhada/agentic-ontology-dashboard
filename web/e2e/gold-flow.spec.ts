import { expect, type Page, test } from "@playwright/test";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/projects\/|\/admin$/);
  if (!page.url().endsWith("/admin")) {
    await expect(page.getByLabel("Project", { exact: true })).toBeVisible();
    if (await page.getByLabel("Project", { exact: true }).inputValue() !== "manufacturing-demo-project") {
      await page.getByLabel("Project", { exact: true }).selectOption("manufacturing-demo-project");
      await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
    }
  }
}

test("manager and engineer accounts see different governed views for the same event", async ({ page }) => {
  test.setTimeout(90_000);
  await login(page, "manager@ontology.local", "Manager!2026");
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  await expect(page.locator(".od-product-shell .react-grid-layout")).toBeVisible();
  await expect(page.getByText("Manufacturing Predictive Maintenance Pack", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /GS-002/ }).click();
  await expect(page.getByText("MANAGER DECISION VIEW")).toBeVisible();
  await expect(page.getByText("현장 점검 요청", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("예상 운영 영향", { exact: true }).first()).toBeVisible();

  const loggedOut = page.waitForResponse((response) => (
    response.request().method() === "POST"
    && response.url().includes("/api/auth/logout")
    && response.ok()
  ));
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await loggedOut;
  await expect(page).toHaveURL(/\/login$/, { timeout: 15_000 });
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  await page.getByRole("button", { name: /GS-002/ }).click();
  await expect(page.getByText("ENGINEER EVIDENCE VIEW")).toBeVisible();
  await expect(page.getByText("센서 변화", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("주요 위험 근거", { exact: true }).first()).toBeVisible();

  const followUpCompleted = page.waitForResponse((response) => (
    response.request().method() === "POST"
    && response.url().includes("/follow-up")
    && response.ok()
  ));
  await page.getByRole("button", { name: "왜 위험한가?" }).click();
  const followUpResponse = await followUpCompleted;
  const followUpPayload = await followUpResponse.json() as { answer: string; supported: boolean };
  expect(followUpPayload.supported).toBe(true);
  await expect(page.locator(".conversation-answer")).toContainText(followUpPayload.answer, { timeout: 15_000 });
});

test("project context restores the migrated demo route and scopes its workspace", async ({ page }) => {
  await login(page, "manager@ontology.local", "Manager!2026");
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  await expect(page.getByLabel("Project", { exact: true })).toHaveValue("manufacturing-demo-project");
  await expect(page.getByLabel("Workspace")).toHaveValue("manufacturing-demo");

  await page.goto("/app/projects/not-accessible");
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  await expect(page.getByLabel("Project", { exact: true })).toHaveValue("manufacturing-demo-project");
  await expect(page.getByLabel("Workspace")).toHaveValue("manufacturing-demo");
});

test("project switch persists active context and isolates project resources", async ({ page }) => {
  test.setTimeout(60_000);
  await login(page, "manager@ontology.local", "Manager!2026");
  await page.getByLabel("Project", { exact: true }).selectOption("azure-fleet-maintenance-project");
  await expect(page).toHaveURL(/\/app\/projects\/azure-fleet-maintenance-project$/);
  await expect(page.getByLabel("Workspace")).toHaveValue("azure-fleet-maintenance");
  await expect(page.getByRole("button", { name: /GS-002/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /AZ-002/ })).toBeVisible();
  await expect(page.getByText("Fleet Machine 042", { exact: true }).first()).toBeVisible();

  await page.reload();
  await expect(page).toHaveURL(/\/app\/projects\/azure-fleet-maintenance-project$/);
  await expect(page.getByLabel("Project", { exact: true })).toHaveValue("azure-fleet-maintenance-project");
  await expect(page.getByLabel("Workspace")).toHaveValue("azure-fleet-maintenance");

  await page.goto("/app/projects/deleted-project");
  await expect(page).not.toHaveURL(/deleted-project/);
  await expect(page).toHaveURL(/\/app\/projects\/(azure-fleet-maintenance-project|manufacturing-demo-project)$/);

  await page.goto("/app/projects/manufacturing-demo-project");
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  await expect(page.getByLabel("Workspace")).toHaveValue("manufacturing-demo");
  await expect(page.getByRole("button", { name: /GS-002/ })).toBeVisible();
});

test("MetroPT project renders a scoped compressor evidence dashboard", async ({ page }) => {
  await login(page, "manager@ontology.local", "Manager!2026");
  await page.getByLabel("Project", { exact: true }).selectOption("metropt-compressor-project");
  await expect(page).toHaveURL(/\/app\/projects\/metropt-compressor-project$/);
  await expect(page.getByLabel("Workspace")).toHaveValue("metropt-compressor-monitoring");
  await expect(page.getByRole("button", { name: /MPT-001/ })).toBeVisible();
  await expect(page.getByText("MetroPT Air Production Unit", { exact: true }).first()).toBeVisible();
  await expect(page.locator(".generic-data-table-body")).toContainText("EVT-MPT-001");
  await expect(page.locator(".data-grid-footer")).toContainText("Server pagination");
  await expect(page.getByText("조회 전용", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/새 판단을 기록할 수 없습니다/).first()).toBeVisible();
});

test("data-quality and provider fallback states remain usable after authentication", async ({ page }) => {
  await login(page, "manager@ontology.local", "Manager!2026");
  const gs007Details = Promise.all([
    page.waitForResponse((response) => response.url().includes("/api/events/EVT-GS-007/evidence") && response.ok()),
    page.waitForResponse((response) => response.url().includes("/api/events/EVT-GS-007/report") && response.ok()),
    page.waitForResponse((response) => response.url().includes("/api/events/EVT-GS-007/layout") && response.ok()),
  ]);
  await page.getByRole("button", { name: /GS-007/ }).click();
  await gs007Details;
  await expect(page.getByText("데이터 품질 경고", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/정상 또는 고장으로 단정하지 않습니다/)).toBeVisible({ timeout: 15_000 });

  const gs008Details = Promise.all([
    page.waitForResponse((response) => response.url().includes("/api/events/EVT-GS-008/evidence") && response.ok()),
    page.waitForResponse((response) => response.url().includes("/api/events/EVT-GS-008/report") && response.ok()),
    page.waitForResponse((response) => response.url().includes("/api/events/EVT-GS-008/layout") && response.ok()),
  ]);
  await page.getByRole("button", { name: /GS-008/ }).click();
  await gs008Details;
  await expect(page.locator(".mode-badge", { hasText: "deterministic_fallback" })).toBeVisible();
  await expect(page.getByText("공구 마모 위험", { exact: false }).first()).toBeVisible({ timeout: 15_000 });
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

test("dashboard edit mode persists a catalog text board and protects mandatory boards", async ({ page }) => {
  test.setTimeout(60_000);
  await login(page, "manager@ontology.local", "Manager!2026");
  await expect(page.getByRole("button", { name: "운영 판단", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "근거와 후속", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "편집", exact: true }).click();
  const mandatoryFrame = page.locator(".dashboard-board-frame").filter({ hasText: "현재 사건 요약" });
  await mandatoryFrame.click();
  await mandatoryFrame.locator(".dashboard-board-more > summary").click();
  await expect(mandatoryFrame.getByRole("menuitem", { name: "삭제", exact: true })).toBeDisabled();

  await page.getByRole("button", { name: "Board Catalog", exact: true }).click();
  const catalog = page.getByRole("dialog", { name: "Board Catalog" });
  await catalog.locator(".catalog-resource-row").filter({ hasText: "Text Board" }).click();
  await catalog.locator(".catalog-add-selected").click();
  await catalog.getByRole("button", { name: "닫기" }).click();
  const addedTextFrame = page.locator(".dashboard-board-frame").filter({ hasText: "Text Board" }).last();
  await expect(addedTextFrame).toBeVisible({ timeout: 20_000 });
  await addedTextFrame.click();
  const plainText = page.getByLabel("Plain text");
  await expect(plainText).toBeVisible({ timeout: 20_000 });
  await plainText.fill("Playwright 개인 운영 메모");

  await page.getByRole("button", { name: "개인 레이아웃 저장" }).click();
  await expect(page.getByText(/다음 로그인에서도 복원됩니다/)).toBeVisible();
  await page.reload();
  await expect(page.getByText("Playwright 개인 운영 메모", { exact: true })).toBeVisible();

  const textFrame = page.locator(".dashboard-board-frame").filter({ hasText: "Playwright 개인 운영 메모" });
  await textFrame.getByRole("button", { name: /전체 화면/ }).click();
  await expect(textFrame).toHaveClass(/is-fullscreen/);
  await textFrame.getByRole("button", { name: "전체 화면 닫기" }).click();
});

test("cross-filter selection saved view and share preserve governed parameter state", async ({ page }) => {
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await page.getByRole("button", { name: /GS-002/ }).click();
  await expect(page.locator(".dashboard-board-frame.is-affected").first()).toBeVisible();
  await expect(page.getByText(/boards affected/)).toBeVisible();

  const savedViewCreated = page.waitForResponse((response) => (
    response.request().method() === "POST"
    && response.url().includes("/api/dashboards/saved-views")
    && response.ok()
  ));
  page.once("dialog", async (dialog) => dialog.accept("Playwright 공구 마모 View"));
  await page.getByRole("button", { name: "이름 있는 뷰 저장", exact: true }).click();
  await savedViewCreated;
  await expect(page.getByRole("option", { name: "Playwright 공구 마모 View" })).toBeAttached({ timeout: 15_000 });
  await expect(page.getByText(/Saved View 'Playwright 공구 마모 View'/)).toBeVisible({ timeout: 15_000 });

  const shareCreated = page.waitForResponse((response) => (
    response.request().method() === "POST"
    && response.url().includes("/api/dashboards/shares")
    && response.ok()
  ));
  await page.getByRole("button", { name: "공유", exact: true }).click();
  await shareCreated;
  await expect(page.getByText(/공유 링크를 생성했습니다:.*share=/)).toBeVisible({ timeout: 15_000 });
});

test("executive viewer understands aggregate risk and drills into an unresolved event", async ({ page }) => {
  await login(page, "executive@ontology.local", "Executive!2026");
  await expect(page.getByText("EXECUTIVE RISK OVERVIEW")).toBeVisible();
  await expect(page.getByRole("button", { name: "Executive Overview", exact: true })).toBeVisible();
  await expect(page.getByText("조직 위험 Portfolio", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("추정 정지 영향", { exact: true })).toBeVisible();
  const unresolved = page.locator(".executive-unresolved-list button").first();
  await expect(unresolved).toBeVisible();
  await unresolved.click();
  await expect(page.locator(".context-object-card")).toBeVisible();
  await expect(page.getByText("추정 가정", { exact: true })).toBeVisible();
});

test("quality auditor reconstructs evidence and records an export checkpoint", async ({ page }) => {
  await login(page, "quality@ontology.local", "Quality!2026");
  await expect(page.getByText("QUALITY & AUDIT VIEW")).toBeVisible();
  await expect(page.getByRole("button", { name: "Event Reconstruction", exact: true })).toBeVisible();
  await expect(page.getByText("사건 재구성", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/fixture-heuristic-v1/).first()).toBeVisible();
  await page.getByRole("button", { name: "Action & Export", exact: true }).click();
  await page.getByLabel("감사 목적").fill("Playwright 감사 checkpoint");
  await page.getByRole("button", { name: "Export checkpoint 기록" }).click();
  await expect(page.getByText(/감사 hash를 기록했습니다/)).toBeVisible();
  await expect(page.getByText("Playwright 감사 checkpoint", { exact: false })).toBeVisible();
});

test("field technician completes a task from a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "technician@ontology.local", "Technician!2026");
  await expect(page.getByText("FIELD TASK VIEW")).toBeVisible();
  await expect(page.getByRole("button", { name: "Mobile Task", exact: true })).toBeVisible();
  await expect(page.getByText("배정 현장 작업", { exact: true }).first()).toBeVisible();
  await expect(page.locator(".dashboard-context-panel")).toBeHidden();
  await page.locator(".mobile-checklist input").first().check();
  await page.getByPlaceholder("완료 handoff 또는 문제·작업 불가 사유").fill("Playwright 모바일 작업 완료 handoff");
  await page.getByRole("button", { name: "작업 완료", exact: true }).click();
  await expect(page.getByText(/현장 작업 완료와 엔지니어 handoff/)).toBeVisible();
  await expect(page.getByText("completed", { exact: true }).first()).toBeVisible();
});

test("FDE sees customer diagnostics and submits template changes for approval", async ({ page }) => {
  await login(page, "fde@ontology.local", "FDE!2026");
  await expect(page.getByText("FDE WORKBENCH PREVIEW")).toBeVisible();
  await expect(page.getByRole("button", { name: "Customer Workspace", exact: true })).toBeVisible();
  await expect(page.getByText("Customer Workspace Overview", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Deployment Checklist", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Diagnostic Events", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "편집", exact: true }).click();
  await expect(page.getByRole("button", { name: "Template 승인 요청", exact: true })).toBeVisible();
  await expect(page.getByText(/Credential·secret 비노출/)).toBeVisible();
});

test("FDE planner validates natural language and applies a non-persisted dashboard draft", async ({ page }) => {
  await login(page, "fde@ontology.local", "FDE!2026");
  await page.getByRole("button", { name: "Template Builder", exact: true }).click();
  const planner = page.locator(".planner-assistant-card");
  await expect(planner.getByText("Governed planning", { exact: true })).toBeVisible();
  await planner.getByRole("button", { name: "Draft 생성", exact: true }).click();
  await expect(planner.locator("strong").filter({ hasText: /^risk_event$/ }).first()).toBeVisible();
  await expect(planner.getByText(/deterministic_fallback/)).toBeVisible();

  await planner.getByRole("button", { name: "Dashboard Draft", exact: true }).click();
  await planner.getByLabel("자연어 요청").fill("운영 판단과 감사 근거를 함께 보는 고객 dashboard");
  await planner.getByRole("button", { name: "Draft 생성", exact: true }).click();
  await expect(planner.getByText("process_manager Dashboard Draft", { exact: true })).toBeVisible();
  await planner.getByRole("button", { name: "검토를 위해 Canvas에 적용", exact: true }).click();
  await expect(page.getByText(/아직 저장·게시되지 않았습니다/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Template 승인 요청", exact: true })).toBeVisible();
});

test("dashboard export creates a downloadable JSON artifact and checkpoint", async ({ page }) => {
  await login(page, "manager@ontology.local", "Manager!2026");
  await page.getByLabel("내보내기 형식").selectOption("json");
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Export", exact: true }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/manufacturing-demo-dashboard-.*\.json$/);
  await expect(page.getByText(/JSON export와 checkpoint/)).toBeVisible();
});

test("authenticated project shell passes the baseline accessibility gate", async ({ page }) => {
  await login(page, "manager@ontology.local", "Manager!2026");
  await expect(page.getByRole("main")).toBeVisible();

  const violations = await page.evaluate(() => {
    const issues: string[] = [];
    const accessibleName = (element: Element) => (
      element.getAttribute("aria-label")
      || element.getAttribute("aria-labelledby")
      || element.getAttribute("title")
      || element.textContent?.trim()
      || ""
    );
    document.querySelectorAll("button,a,input,select,textarea").forEach((element) => {
      const input = element as HTMLInputElement;
      if (input.type === "hidden") return;
      const id = element.getAttribute("id");
      const labelled = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
      const wrappingLabel = element.closest("label");
      if (!accessibleName(element) && !labelled && !wrappingLabel) {
        issues.push(`missing accessible name: ${element.tagName.toLowerCase()}`);
      }
    });
    document.querySelectorAll("img").forEach((image) => {
      if (!image.hasAttribute("alt")) issues.push("image missing alt");
    });
    const ids = Array.from(document.querySelectorAll("[id]"))
      .map((element) => element.id)
      .filter(Boolean);
    const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
    duplicates.forEach((id) => issues.push(`duplicate id: ${id}`));
    if (document.querySelectorAll("main").length !== 1) {
      issues.push("page must contain exactly one main landmark");
    }
    return [...new Set(issues)];
  });

  expect(violations).toEqual([]);
});

test("data scientist requests a model release and admin sees the approval queue", async ({ page }) => {
  await login(page, "datascientist@ontology.local", "DataScience!2026");
  await expect(page.getByText("MODEL VALIDATION VIEW")).toBeVisible();
  await expect(page.getByRole("button", { name: "Model Console", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Drift & Regression", exact: true }).click();
  await expect(page.getByText("8/8 PASS", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Release Candidate", exact: true }).click();
  await page.getByLabel("승인 요청 근거").fill("Playwright Gold 8건 통과 승인 요청");
  await page.getByRole("button", { name: "Release 승인 요청", exact: true }).click();
  await expect(page.getByText(/관리자 승인 요청으로 제출했습니다/)).toBeVisible();

  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await login(page, "admin@ontology.local", "OntologyAdmin!2026");
  await page.getByRole("button", { name: "Workflow Approvals", exact: true }).click();
  await expect(page.getByText("Playwright Gold 8건 통과 승인 요청", { exact: false })).toBeVisible();
  await expect(page.getByText("MODEL RELEASE", { exact: true })).toBeVisible();
});
