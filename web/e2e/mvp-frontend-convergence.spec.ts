import { expect, type Page, test } from "@playwright/test";

const PROJECT = "manufacturing-demo-project";
const MVP_PATH = `/app/projects/${PROJECT}/mvp`;
const ACCOUNTS = {
  manager: ["manager@ontology.local", "Manager!2026"],
  engineer: ["engineer@ontology.local", "Engineer!2026"],
} as const;

async function login(page: Page, returnTo = MVP_PATH, account: keyof typeof ACCOUNTS = "manager") {
  const [email, password] = ACCOUNTS[account];
  await page.goto(`/login?returnTo=${encodeURIComponent(returnTo)}`);
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/app/projects/${PROJECT}`));
}

test("login exposes only the two mentoring MVP roles", async ({ page }) => {
  await page.goto(`/login?returnTo=${encodeURIComponent(MVP_PATH)}`);

  const demoAccounts = page.getByRole("group", { name: "MVP 데모 계정" }).getByRole("button");
  await expect(demoAccounts).toHaveCount(2);
  await expect(page.getByRole("button", { name: /관리자·임원/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /실무 엔지니어/ })).toBeVisible();
  await expect(page.getByText("데이터 사이언티스트", { exact: true })).toHaveCount(0);
  await expect(page.getByText("FDE", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: /관리자·임원/ }).click();
  await expect(page.getByLabel("이메일")).toHaveValue("manager@ontology.local");
  await expect(page.getByLabel("비밀번호")).toHaveValue("Manager!2026");

  await page.getByRole("button", { name: /실무 엔지니어/ }).click();
  await expect(page.getByLabel("이메일")).toHaveValue("engineer@ontology.local");
  await expect(page.getByLabel("비밀번호")).toHaveValue("Engineer!2026");
});

test("completes Overview to Objects to Operations to Executive Report without Analysis", async ({ page }) => {
  await login(page);
  await expect(page.locator(".mvp-app")).toBeVisible();
  await expect(page.locator(".mvp-navigation nav button")).toHaveCount(4);
  await expect(page.getByText("Analysis", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("mvp-overview")).toBeVisible();
  await expect(page.locator(".mvp-kpi")).toHaveCount(6);
  await expect(page.locator(".mvp-priority-list button").first()).toBeVisible();

  await page.locator(".mvp-priority-list button").first().click();
  await expect(page).toHaveURL(/view=objects/);
  await expect(page.getByTestId("mvp-objects")).toBeVisible();
  await expect(page.locator(".mvp-object-row").first()).toBeVisible();
  await expect(page.locator(".mvp-object-inspector")).toBeVisible();

  await page.getByRole("button", { name: /Operations에서 조치 검토/ }).click();
  await expect(page).toHaveURL(/view=operations/);
  await expect(page.getByTestId("mvp-operations")).toBeVisible();
  await expect(page.locator(".mvp-operation-hero")).toBeVisible();
  await expect(page.getByText("자동 정지 아님", { exact: true })).toBeVisible();
  await expect(page.getByText(/설비 제어 명령을 실행하지 않습니다/)).toBeVisible();
  await page.getByLabel("판단 메모").fill("E2E 검증: 현장 점검 전 정지 여부를 검토합니다.");
  await page.getByRole("button", { name: "판단 기록", exact: true }).click();
  await expect(page.getByText("저장 완료", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Executive Report 반영/ }).click();
  await expect(page).toHaveURL(/view=executive-report/);
  await expect(page.getByTestId("mvp-executive-report")).toBeVisible();
  await expect(page.locator(".mvp-report-document")).toBeVisible();
  await expect(page.getByRole("button", { name: /A4 PDF/ })).toBeVisible();
  await expect(page.locator(".mvp-report-kpis article")).toHaveCount(5);
  await page.emulateMedia({ media: "print" });
  await expect.poll(() => page.locator(".mvp-global-header").evaluate((element) => getComputedStyle(element).display)).toBe("none");
  await expect(page.locator(".mvp-report-document")).toBeVisible();

  const query = new URL(page.url()).searchParams;
  expect(query.get("asset_id")).toBeTruthy();
  expect(query.get("event_id")).toBeTruthy();
});

test("separates manager decisions from field-operator notes using real permissions", async ({ page }) => {
  await login(page, `${MVP_PATH}?view=operations`, "engineer");
  await expect(page.getByTestId("mvp-operations")).toBeVisible();
  await expect(page.getByText("현재 역할에는 events.decision 권한이 없습니다.", { exact: true })).toBeVisible();
  await expect(page.getByText("POST /api/events/{event_id}/notes", { exact: true })).toBeVisible();
  await page.getByLabel("점검 결과 또는 전달 사항").fill("E2E 현장 메모: 공구 마모와 센서 연결 상태를 확인했습니다.");
  await page.getByRole("button", { name: "메모 저장", exact: true }).click();
  await expect(page.getByText("저장 완료", { exact: true })).toBeVisible();
  await expect(page.getByText(/현장 메모가 실제 Event API에 저장됐습니다/)).toBeVisible();
});

test("keeps direct links reproducible and renders invalid IDs as safe empty states", async ({ page }) => {
  const invalid = `${MVP_PATH}?view=objects&asset_id=missing-asset&event_id=missing-event&role=process_manager`;
  await login(page, invalid);
  await expect(page).toHaveURL(/asset_id=missing-asset/);
  await expect(page.getByTestId("mvp-objects")).toBeVisible();
  await expect(page.getByText(/요청한 설비 missing-asset/)).toBeVisible();

  await page.reload();
  await expect(page).toHaveURL(/asset_id=missing-asset/);
  await expect(page.getByText(/요청한 설비 missing-asset/)).toBeVisible();
});

test("isolates Canonical API failures and preserves the four-screen fallback flow", async ({ page }) => {
  await page.route("**/api/projects/*/workspaces/*/predictive-maintenance/**", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "runtime_unavailable", message: "runtime unavailable in test" } }) });
  });
  await login(page);
  await expect(page.getByTestId("mvp-overview")).toBeVisible();
  await expect(page.getByText("계약형 Fallback", { exact: true })).toBeVisible();
  await expect(page.getByText(/부분 연결 경고/)).toBeVisible();
  await expect(page.locator(".mvp-priority-list button").first()).toBeVisible();
});

test("uses the verified report template when both LLM and deterministic report APIs fail", async ({ page }) => {
  await page.route("**/api/events/*/report", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "report_unavailable", message: "report unavailable in test" } }) });
  });
  await page.route("**/api/projects/*/workspaces/*/predictive-maintenance/dashboard**", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "runtime_unavailable", message: "runtime unavailable in test" } }) });
  });
  await login(page, `${MVP_PATH}?view=executive-report`);
  await expect(page.getByTestId("mvp-executive-report")).toBeVisible();
  await expect(page.getByText("Verified template fallback", { exact: true })).toBeVisible();
  await expect(page.locator(".mvp-report-document")).toBeVisible();
  await expect(page.getByText(/모델 확률은 실제 고장 발생을 확정하지 않습니다/)).toBeVisible();
});

test("keeps all MVP views inside a 390px mobile viewport and exposes compact navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await expect(page.locator(".mvp-app")).toBeVisible();

  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await expect(page.locator(".mvp-navigation")).toHaveClass(/is-open/);
  for (const label of ["Overview", "Objects", "Operations", "Executive Report"]) {
    await page.getByRole("button", { name: new RegExp(label) }).last().click();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    if (label !== "Executive Report") await page.getByRole("button", { name: "메뉴 열기" }).click();
  }
});

test("preserves V1, V2, V3, V4, and comparison routes beside the new MVP", async ({ page }) => {
  await login(page);
  await page.goto(`/app/projects/${PROJECT}`);
  await expect(page.locator(".mvp-app")).toHaveCount(0);
  await page.goto(`/app/projects/${PROJECT}/blueprint`);
  await expect(page.locator(".blueprint-preview")).toBeVisible();
  await page.goto(`/app/projects/${PROJECT}/blueprint-v2`);
  await expect(page.locator(".blueprint-v2")).toBeVisible();
  await page.goto(`/app/projects/${PROJECT}/blueprint-v4`);
  await expect(page.locator('[data-application-id="ontology-commercial-v4"]')).toBeVisible();
  await page.goto(`/app/projects/${PROJECT}/blueprint-compare`);
  await expect(page.locator(".blueprint-comparison-page")).toBeVisible();
  await page.goto(MVP_PATH);
  await expect(page.locator(".mvp-app")).toBeVisible();
});
