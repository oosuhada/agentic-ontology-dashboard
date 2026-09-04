import { expect, type Page, test } from "@playwright/test";

const PROJECT = "manufacturing-demo-project";
const OPERATIONS_PATH = `/app/projects/${PROJECT}/operations`;
const API_URL = process.env.PLAYWRIGHT_API_URL ?? `http://127.0.0.1:${process.env.PLAYWRIGHT_API_PORT ?? "8200"}`;
const CLASSIC_OVERVIEW_PATH = `${OPERATIONS_PATH}?view=overview&dashboard=classic`;
const WORKFLOW_FIELD_OVERVIEW_PATH = `${OPERATIONS_PATH}?view=overview&dashboard=workflow&role=field_operator&workspace_id=manufacturing-demo&asset_id=CNC-S04-L02-03&event_id=EVT-GS-004`;
const WORKFLOW_PROCESS_OVERVIEW_PATH = `${OPERATIONS_PATH}?view=overview&dashboard=workflow&role=process_manager&workspace_id=manufacturing-demo&asset_id=CNC-S04-L02-03&event_id=EVT-GS-004`;
const ACCOUNTS = {
  admin: ["admin@ontology.local", "OntologyAdmin!2026"],
  manager: ["manager@ontology.local", "Manager!2026"],
  engineer: ["engineer@ontology.local", "Engineer!2026"],
  executive: ["executive@ontology.local", "Executive!2026"],
} as const;
let loginAttempt = 0;

async function login(page: Page, returnTo = OPERATIONS_PATH, account: keyof typeof ACCOUNTS = "manager") {
  const [email, password] = ACCOUNTS[account];
  const forwardedFor = `127.0.0.${++loginAttempt}`;
  await page.route("**/api/auth/login", async (route) => {
    await route.continue({
      headers: {
        ...route.request().headers(),
        "X-Forwarded-For": forwardedFor,
      },
    });
  }, { times: 1 });
  await page.goto(`/login?returnTo=${encodeURIComponent(returnTo)}`);
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/app/projects/${PROJECT}`));
}

async function materializeAgentSummary(page: Page, assetId: string) {
  await page.evaluate(
    async ({ apiUrl, assetId, project }) => {
      const csrfToken = document.cookie
        .split(";")
        .map((item) => item.trim())
        .find((item) => item.startsWith("ontology_csrf="))
        ?.slice("ontology_csrf=".length);
      const response = await fetch(
        `${apiUrl}/api/objects/${encodeURIComponent(assetId)}/agent-review-summary?project_id=${encodeURIComponent(project)}&history_window=24h`,
        {
          method: "POST",
          headers: csrfToken ? { "X-CSRF-Token": decodeURIComponent(csrfToken) } : {},
          credentials: "include",
        },
      );
      if (!response.ok) {
        const body = await response.text();
        throw new Error(`agent summary materialization failed: ${response.status} ${body}`);
      }
    },
    { apiUrl: API_URL, assetId, project: PROJECT },
  );
}

test("login exposes the three decision-workspace personas", async ({ page }) => {
  await page.goto(`/login?returnTo=${encodeURIComponent(OPERATIONS_PATH)}`);

  await expect(page.getByText("Predictive Maintenance Decision Workspace", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "실시간 설비 현황에서 운영 판단과 경영 보고까지" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /설비 이상 발견 뒤/ })).toBeVisible();
  await expect(page.getByText("Monitoring", { exact: true })).toBeVisible();
  await expect(page.getByText("Decision Case", { exact: true })).toBeVisible();
  await expect(page.getByText("Executive Brief", { exact: true })).toBeVisible();
  for (const legacyCopy of [
    "Foundry-style operational platform",
    "PLATFORM RESOURCES",
    "Dataset Catalog",
    "Object Explorer",
    "Local governed runtime",
    "Project 3 boundary",
    "업무 공간에 로그인",
    "운영 데모 역할 선택",
    "Credentials are validated inside the configured tenant boundary.",
  ]) {
    await expect(page.getByText(legacyCopy, { exact: true })).toHaveCount(0);
  }

  const demoAccounts = page.getByRole("group", { name: "역할별 계정" }).getByRole("button");
  await expect(demoAccounts).toHaveCount(3);
  await expect(page.getByRole("button", { name: /운영 관리자/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /설비\/공정 엔지니어/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /경영진/ })).toBeVisible();
  await expect(page.getByText("데이터 사이언티스트", { exact: true })).toHaveCount(0);
  await expect(page.getByText("FDE", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: /운영 관리자/ }).click();
  await expect(page.getByLabel("이메일")).toHaveValue("manager@ontology.local");
  await expect(page.getByLabel("비밀번호")).toHaveValue("Manager!2026");

  await page.getByRole("button", { name: /설비\/공정 엔지니어/ }).click();
  await expect(page.getByLabel("이메일")).toHaveValue("engineer@ontology.local");
  await expect(page.getByLabel("비밀번호")).toHaveValue("Engineer!2026");

  await page.getByRole("button", { name: /경영진/ }).click();
  await expect(page.getByLabel("이메일")).toHaveValue("executive@ontology.local");
  await expect(page.getByLabel("비밀번호")).toHaveValue("Executive!2026");
});

test("role-aware entry keeps manager, engineer, and executive experiences distinct", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();

  async function signIn(email: string, password: string) {
    await page.goto("/login");
    await page.getByLabel("이메일").fill(email);
    await page.getByLabel("비밀번호").fill(password);
    await page.getByRole("button", { name: "로그인", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/app/projects/${PROJECT}/operations`));
  }

  async function switchAccount() {
    await page.getByRole("button", { name: "환경설정" }).click();
    await page.getByRole("button", { name: /계정 전환/ }).click();
    await expect(page).toHaveURL(/\/login/);
  }

  await signIn(...ACCOUNTS.manager);
  await expect(page).toHaveURL(/\/operations\/factory-status/);
  await expect(page).toHaveURL(/view=overview/);
  await expect(page.getByText("공장 설비 상태맵", { exact: true })).toBeVisible();
  await expect(page.locator(".operations-factory-asset-node")).toHaveCount(100);
  const managerNav = page.locator(".rw-preview-left nav button");
  await expect(managerNav).toHaveCount(5);
  await expect(managerNav.nth(0)).toContainText("설비 현황");
  await expect(managerNav.nth(1)).toContainText("판단 대기");
  await expect(managerNav.nth(2)).toContainText("운영 현황");
  await expect(managerNav.nth(3)).toContainText("생산 영향");
  await expect(managerNav.nth(4)).toContainText("보고 초안");
  await managerNav.nth(3).click();
  await expect(page).toHaveURL(/\/operations\/production-impact/);
  await expect(page).toHaveURL(/view=objects/);
  await expect(page.getByText("생산 · 재무 영향", { exact: true })).toBeVisible();

  await switchAccount();
  await signIn(...ACCOUNTS.executive);
  await expect(page).toHaveURL(/\/operations\/executive-brief/);
  await expect(page).toHaveURL(/view=reports/);
  await expect(page.getByTestId("role-composed-executive")).toBeVisible();
  const executiveNav = page.locator(".rw-preview-left nav button");
  await expect(executiveNav).toHaveCount(5);
  await expect(executiveNav.nth(0)).toContainText("Executive Brief");
  await expect(executiveNav.nth(1)).toContainText("의사결정 병목");
  await expect(executiveNav.nth(2)).toContainText("운영 리스크");
  await expect(executiveNav.nth(3)).toContainText("정비 효과");
  await expect(executiveNav.nth(4)).toContainText("설비 상태 근거");
  await expect(page.getByText("경영 KPI 기준", { exact: true })).toBeVisible();
  await executiveNav.nth(4).click();
  await expect(page).toHaveURL(/\/operations\/factory-status/);
  await expect(page.getByText("공장 설비 상태맵", { exact: true })).toBeVisible();

  await switchAccount();
  await signIn(...ACCOUNTS.engineer);
  await expect(page).toHaveURL(/\/operations\/factory-status/);
  await expect(page).toHaveURL(/view=overview/);
  const engineerNav = page.locator(".rw-preview-left nav button");
  await expect(engineerNav).toHaveCount(5);
  await expect(engineerNav.nth(0)).toContainText("설비 현황");
  await expect(engineerNav.nth(1)).toContainText("모니터링");
  await expect(engineerNav.nth(2)).toContainText("설비");
  await expect(engineerNav.nth(3)).toContainText("점검");
  await expect(engineerNav.nth(4)).toContainText("현장 메모");
  await expect(page.getByText("공장 설비 상태맵", { exact: true })).toBeVisible();
  await engineerNav.nth(1).click();
  await expect(page).toHaveURL(/\/operations\/monitoring/);
  await expect(page.getByText("실시간 피쳐 그래프", { exact: true })).toBeVisible();
  await expect(page).not.toHaveURL(/view=objects/);

  await context.close();
});

test("live exact-event grounding returns SOP inspection targets and RAG evidence", async ({ page }) => {
  test.setTimeout(60_000);
  await login(page, OPERATIONS_PATH, "manager");

  const verification = await page.evaluate(async ({ apiUrl, project }) => {
    const workspace = "manufacturing-demo";
    const latestResponse = await fetch(
      `${apiUrl}/api/projects/${encodeURIComponent(project)}/workspaces/${encodeURIComponent(workspace)}/predictive-maintenance/results/latest?limit=500`,
      { credentials: "include" },
    );
    if (!latestResponse.ok) throw new Error(`latest results failed: ${latestResponse.status}`);
    const latest = await latestResponse.json();
    const datasetVersionId = latest.context?.dataset_version_id ?? null;

    const candidates = (latest.items ?? []).filter((item: {
      asset_type?: string;
    }) => (
      String(item.asset_type ?? "").toLowerCase() === "cnc"
    )).sort((left: { failure_probability?: number }, right: { failure_probability?: number }) => (
      Number(right.failure_probability ?? 0) - Number(left.failure_probability ?? 0)
    )).slice(0, 12);

    const diagnostics: Array<Record<string, unknown>> = [];
    for (const item of candidates) {
      const assetId = item.asset_id;
      const eventId = item.artifact_id ?? item.provenance?.prediction_id ?? null;
      if (!assetId || !eventId) continue;

      const packetParams = new URLSearchParams({
        project_id: project,
        history_window: "24h",
        event_id: eventId,
      });
      if (datasetVersionId) packetParams.set("dataset_version_id", datasetVersionId);
      const packetResponse = await fetch(
        `${apiUrl}/api/objects/${encodeURIComponent(assetId)}/agent-review-packet?${packetParams.toString()}`,
        { credentials: "include" },
      );
      if (!packetResponse.ok) {
        diagnostics.push({ assetId, eventId, packetStatus: packetResponse.status });
        continue;
      }
      const packet = await packetResponse.json();
      diagnostics.push({
        assetId,
        eventId,
        failureProbability: item.failure_probability ?? null,
        predictedFailureType: item.predicted_failure_type ?? null,
        topFactors: (item.top_factors ?? []).slice(0, 4).map((factor: { feature?: string }) => factor.feature ?? null),
        sopCount: packet.sop_retrieval?.returned_count ?? 0,
        packetInspectionTargets: packet.inspection_targets?.length ?? 0,
      });
      if ((packet.sop_retrieval?.returned_count ?? 0) < 1) continue;

      const detailParams = new URLSearchParams({
        project_id: project,
        workspace_id: workspace,
        history_window: "24h",
        event_id: eventId,
      });
      if (datasetVersionId) detailParams.set("dataset_version_id", datasetVersionId);
      const detailResponse = await fetch(
        `${apiUrl}/api/objects/${encodeURIComponent(assetId)}/detail-view?${detailParams.toString()}`,
        { credentials: "include" },
      );
      diagnostics[diagnostics.length - 1].detailStatus = detailResponse.status;
      if (!detailResponse.ok) continue;
      const detail = await detailResponse.json();
      diagnostics[diagnostics.length - 1].detailInspectionTargets = detail.inspection_targets?.length ?? 0;

      const csrfToken = document.cookie
        .split(";")
        .map((value) => value.trim())
        .find((value) => value.startsWith("ontology_csrf="))
        ?.slice("ontology_csrf=".length);
      const queryResponse = await fetch(`${apiUrl}/api/agent/query`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(csrfToken ? { "X-CSRF-Token": decodeURIComponent(csrfToken) } : {}),
        },
        body: JSON.stringify({
          project_id: project,
          workspace_id: workspace,
          question: "이 설비에서 우선 확인할 기술 근거와 SOP를 알려줘",
          route: "auto",
          audience: "engineering",
          object_type: "equipment",
          object_id: assetId,
          event_id: eventId,
          top_k: 8,
        }),
      });
      diagnostics[diagnostics.length - 1].queryStatus = queryResponse.status;
      if (!queryResponse.ok) continue;
      const query = await queryResponse.json();
      const ragEvidence = (query.state?.evidence ?? []).filter((e: { store?: string }) => e.store === "project3_rag");
      diagnostics[diagnostics.length - 1].ragEvidenceCount = ragEvidence.length;
      if (ragEvidence.length < 1) continue;

      return {
        match: {
          assetId,
          eventId,
          sopCount: packet.sop_retrieval.returned_count,
          packetInspectionTargets: packet.inspection_targets?.length ?? 0,
          detailInspectionTargets: detail.inspection_targets?.length ?? 0,
          ragEvidenceCount: ragEvidence.length,
          sopSource: packet.sop_guidance?.[0]?.source_ref ?? null,
        },
        diagnostics,
      };
    }
    return { match: null, diagnostics };
  }, { apiUrl: API_URL, project: PROJECT });

  console.log("live grounding diagnostics", JSON.stringify(verification.diagnostics));
  expect(verification.match).not.toBeNull();
  expect(verification.match?.sopCount).toBeGreaterThanOrEqual(1);
  expect(verification.match?.packetInspectionTargets).toBeGreaterThanOrEqual(1);
  expect(verification.match?.detailInspectionTargets).toBeGreaterThanOrEqual(1);
  expect(verification.match?.ragEvidenceCount).toBeGreaterThanOrEqual(1);
  expect(verification.match?.sopSource).toContain("SOP-DEMO-CNC-ROTATING-ASSEMBLY-001");
});

test("shows normal assets in the current-state overview", async ({ page }) => {
  await login(page, CLASSIC_OVERVIEW_PATH);
  await expect(page.getByTestId("operations-overview")).toBeVisible();
  await expect(page.getByText("라인별 설비 상태", { exact: true })).toBeVisible();
  const lineStatuses = page.locator(".operations-line-risk-list footer");
  await expect(lineStatuses.first()).toBeVisible();
  await expect(lineStatuses.first()).toContainText(/정상 \d+/);
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("button", { name: "로그인", exact: true })).toBeVisible();
});

test("keeps workflow role dashboards ordered around each role's first task", async ({ page }) => {
  await login(page, WORKFLOW_FIELD_OVERVIEW_PATH);
  await expect(page.getByTestId("operations-overview")).toBeVisible();
  await expect(page.getByRole("heading", { name: "우선순위", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "작업 상태 큐" })).toBeVisible();
  const fieldPriority = await page.getByRole("heading", { name: "우선순위", exact: true }).boundingBox();
  const fieldQueue = await page.getByRole("region", { name: "작업 상태 큐" }).boundingBox();
  expect(fieldPriority?.y ?? 0).toBeLessThan(fieldQueue?.y ?? 0);

  await page.goto(WORKFLOW_PROCESS_OVERVIEW_PATH);
  await expect(page.getByTestId("operations-overview")).toBeVisible();
  await expect(page.getByRole("heading", { name: "라인별 설비 영향 맵", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "작업 상태 큐" })).toBeVisible();
  const processMap = await page.getByRole("heading", { name: "라인별 설비 영향 맵", exact: true }).boundingBox();
  const processQueue = await page.getByRole("region", { name: "작업 상태 큐" }).boundingBox();
  expect(processMap?.y ?? 0).toBeLessThan(processQueue?.y ?? 0);
});

test("lets a permitted manager explicitly regenerate the AI review summary", async ({ page }) => {
  await login(page, `${Operations_PATH}?view=overview&dashboard=workflow&role=field_operator&workspace_id=manufacturing-demo&asset_id=CNC-S04-L04-01&event_id=EVT-GS-002`, "manager");
  await materializeAgentSummary(page, "CNC-S04-L04-01");
  await expect(page.getByTestId("operations-overview")).toBeVisible();
  await page.getByRole("button", { name: /공구\/금형 마모 의심 제안 #02/ }).click();
  const preview = page.getByRole("dialog", { name: "선택 설비 상세" });
  await expect(preview).toBeVisible();
  const agentReview = preview.getByRole("region", { name: "AI 검토 요약" });
  await expect(agentReview).toContainText("저장 요약");
  await expect(agentReview).toContainText("최근 정비 이력");
  await expect(agentReview).toContainText("현장 담당자");
  await expect(agentReview).not.toContainText("공정 관리자");
  await expect(agentReview).toContainText("이 초안은 담당자 검토를 돕기 위한 read-only 문서");
  await expect(agentReview).toContainText("자동 승인을 수행하지 않습니다");
  await expect(agentReview.getByRole("button", { name: "AI 요약 재생성" })).toBeEnabled();
  await agentReview.getByRole("button", { name: "AI 요약 재생성" }).click();
  await expect(agentReview).toContainText("수동 갱신");
  await expect(agentReview).toContainText("완료");
});

test("shows stored AI review summaries to engineers as read-only", async ({ page }) => {
  const returnTo = `${Operations_PATH}?view=overview&dashboard=workflow&role=field_operator&workspace_id=manufacturing-demo&asset_id=CNC-S04-L04-01&event_id=EVT-GS-002`;
  await login(page, returnTo, "engineer");
  await expect(page.getByTestId("operations-overview")).toBeVisible();
  await page.getByRole("button", { name: /공구\/금형 마모 의심 제안 #02/ }).click();
  const preview = page.getByRole("dialog", { name: "선택 설비 상세" });
  await expect(preview).toBeVisible();
  const agentReview = preview.getByRole("region", { name: "AI 검토 요약" });
  await expect(agentReview).toContainText("저장 요약");
  await expect(agentReview).toContainText("최근 정비 이력");
  await expect(agentReview).toContainText("현재 역할은 저장된 AI 요약만 조회할 수 있습니다.");
  await expect(agentReview.getByRole("button", { name: "AI 요약 재생성" })).toBeDisabled();
  await preview.getByRole("tab", { name: "처리", exact: true }).click();
  await expect(preview.getByText("점검 요청 후보이며 작업요청이나 정비 조치는 실제 생성하지 않습니다.")).toBeVisible();
});

test("keeps system administrator logs behind the admin persona", async ({ page }) => {
  await login(page, `${Operations_PATH}?view=system&dashboard=workflow`, "admin");
  await expect(page.locator(".operations-page-heading").getByRole("heading", { name: "AI 요약 처리 로그", exact: true })).toBeVisible();
  await expect(page.locator(".operations-navigation nav").getByRole("button", { name: /시스템 관리자/ })).toBeVisible();
});

test("completes Overview to Objects to Operations to Reports Executive Brief without Analysis", async ({ page }) => {
  await login(page, CLASSIC_OVERVIEW_PATH);
  await expect(page.locator(".operations-app")).toBeVisible();
  await expect(page.locator(".operations-navigation nav button")).toHaveCount(4);
  await expect(page.getByText("Analysis", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("operations-overview")).toBeVisible();
  await expect(page.locator(".operations-kpi")).toHaveCount(6);
  await expect(page.locator(".operations-priority-list button").first()).toBeVisible();

  await page.locator(".operations-priority-list button").first().click();
  await expect(page).toHaveURL(/view=objects/);
  await expect(page.getByTestId("operations-objects")).toBeVisible();
  await expect(page.locator(".operations-object-row").first()).toBeVisible();
  await expect(page.locator(".operations-object-inspector")).toBeVisible();

  await page.getByRole("button", { name: /작업요청 후보 열기/ }).click();
  await expect(page).toHaveURL(/view=operations/);
  await expect(page.getByTestId("operations-operations")).toBeVisible();
  await expect(page.locator(".operations-operation-hero")).toBeVisible();
  await expect(page.getByText("자동 정지 아님", { exact: true })).toBeVisible();
  await expect(page.getByText(/설비 제어 명령을 실행하지 않습니다/)).toBeVisible();
  await page.getByLabel("추가 메모 선택 입력").fill("E2E 검증: 현장 점검 전 정지 여부를 검토합니다.");
  await page.getByLabel("현재 허용된 작업").getByRole("button", { name: "작업요청 생성", exact: true }).click();
  const saveFailure = page.getByRole("status").filter({ hasText: "저장 실패" });
  await expect(saveFailure).toBeVisible();
  await expect(saveFailure).toContainText("API request failed: 503");

  await page.locator(".operations-report-bridge").click();
  await expect(page).toHaveURL(/view=reports/);
  await expect(page).toHaveURL(/report=executive-brief/);
  await expect(page.getByTestId("operations-reports")).toBeVisible();
  await expect(page.getByTestId("operations-executive-report")).toBeVisible();
  await expect(page.locator(".operations-report-document")).toBeVisible();
  await expect(page.getByRole("button", { name: /A4 PDF/ })).toBeVisible();
  await expect(page.locator(".operations-report-kpis article")).toHaveCount(5);
  await page.emulateMedia({ media: "print" });
  await expect.poll(() => page.locator(".operations-global-header").evaluate((element) => getComputedStyle(element).display)).toBe("none");
  await expect(page.locator(".operations-report-document")).toBeVisible();

  const query = new URL(page.url()).searchParams;
  expect(query.get("asset_id")).toBeTruthy();
  expect(query.get("event_id")).toBeTruthy();
});

test("covers Reports side-tab flow with summary graphs and report types", async ({ page }) => {
  await login(page, `${Operations_PATH}?view=reports&dashboard=classic&report=inspection-request`);
  await expect(page.getByTestId("operations-reports")).toBeVisible();
  await expect(page.getByRole("tab", { name: /상태 요약/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /점검 요청/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /요약 보고서/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Executive Brief/ })).toBeVisible();
  await expect(page.getByTestId("operations-static-report")).toBeVisible();
  await expect(page.getByRole("heading", { name: "예지보전 점검 요청 보고서", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "관리자 판단", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "점검 항목", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "센서 참고값", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "근거 추적", exact: true })).toBeVisible();
  await expect(page.getByText("공기압축기 설비 참고도")).toBeVisible();

  const query = new URL(page.url()).searchParams;
  expect(query.get("view")).toBe("reports");
  expect(query.get("report")).toBe("inspection-request");
  expect(query.get("asset_id")).toBeTruthy();
  expect(query.get("event_id")).toBeTruthy();

  await page.locator(".operations-navigation nav").getByRole("button", { name: /Overview/ }).click();
  await expect(page).toHaveURL(/view=overview/);
  await expect(page.getByTestId("operations-overview")).toBeVisible();

  await page.getByRole("button", { name: /Reports/ }).click();
  await expect(page.getByTestId("operations-reports")).toBeVisible();
  await page.getByRole("tab", { name: /상태 요약/ }).click();
  await expect(page.getByTestId("operations-status-map-report")).toBeVisible();
  const statusMapNodes = page.locator(".operations-reports-page .line-map .asset-node");
  const statusMapNodeCount = await statusMapNodes.count();
  expect(statusMapNodeCount).toBeGreaterThan(0);
  await expect(page.locator(".operations-reports-page .line-map .asset-node.warning").first()).toBeVisible();
  await expect(page.locator(".operations-reports-page .line-map .asset-node.attention").first()).toBeVisible();
  await expect(page.locator(".operations-reports-page .line-map .asset-node:disabled")).toHaveCount(0);
  await statusMapNodes.nth(1).click();
  await expect(statusMapNodes.nth(1)).toHaveAttribute("aria-pressed", "true");
  await expect(statusMapNodes.nth(1)).toHaveClass(/selected/);
  await expect(page.locator(".operations-reports-page .report-panel").getByText("선택 설비 상세")).toBeVisible();
  await page.getByRole("tab", { name: /요약 보고서/ }).click();
  await expect(page.getByTestId("operations-summary-report")).toBeVisible();
  await expect(page.getByTestId("operations-summary-map-report-graphs")).toBeVisible();
  await expect(page.getByText("상태 맵 · 라인 위험 · 선택 설비를 한 장으로 압축")).toBeVisible();
  await expect(page.getByText("상태 분포")).toBeVisible();
  await expect(page.getByText("라인별 평균 위험")).toBeVisible();
  await expect(page.getByText("위험 예측 확률")).toBeVisible();
  await expect(page.getByTestId("operations-summary-graphs")).toBeVisible();
  await expect(page.getByRole("img", { name: /관측 흐름/ }).first()).toBeVisible();
  expect(await page.locator(".asset-series-chart").count()).toBeGreaterThanOrEqual(3);
  await expect(page.locator(".asset-crossing-marker").first()).toBeVisible();
  await expect(page.locator(".asset-history-section").first()).toBeVisible();
  await expect(page.getByText("설비 이력").first()).toBeVisible();
  await page.getByRole("tab", { name: /점검 요청/ }).click();
  await expect(page.getByTestId("operations-static-report")).toBeVisible();
});

test("loads the Objects inspector through the AssetDetailViewModel API", async ({ page }) => {
  const detailViewResponses: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/objects/CNC-S04-L04-01/detail-view") && response.ok()) {
      detailViewResponses.push(response.url());
    }
  });

  await login(page, `${Operations_PATH}?view=objects&dashboard=classic&asset_id=CNC-S04-L04-01&event_id=EVT-GS-002`);
  await expect(page.getByTestId("operations-objects")).toBeVisible();
  await expect.poll(() => detailViewResponses.length).toBeGreaterThan(0);
  await expect(page.locator(".operations-object-inspector")).toContainText("4구역 · 4셀 · CNC 가공기 1");
  await expect(page.locator(".operations-object-inspector")).toContainText("공구 마모");
  expect(detailViewResponses[0]).toContain("dataset_version_id=");
});

test("separates manager decisions from field-operator notes using real permissions", async ({ page }) => {
  await login(page, `${Operations_PATH}?view=operations&dashboard=classic`, "engineer");
  await expect(page.getByTestId("operations-operations")).toBeVisible();
  await expect(page.getByText("현재 역할에는 결정 기록 권한이 없습니다.", { exact: true })).toBeVisible();
  await expect(page.getByText("메모 기록 가능", { exact: true })).toBeVisible();
  await page.getByLabel("점검 결과 또는 전달 사항").fill("E2E 현장 메모: 공구 마모와 센서 연결 상태를 확인했습니다.");
  await page.getByRole("button", { name: "메모 저장", exact: true }).click();
  await expect(page.getByText("저장 완료", { exact: true })).toBeVisible();
  await expect(page.getByText(/현장 메모가 저장됐습니다/)).toBeVisible();
});

test("keeps direct links reproducible and renders invalid IDs as safe empty states", async ({ page }) => {
  const invalid = `${Operations_PATH}?view=objects&dashboard=classic&asset_id=missing-asset&event_id=missing-event&role=process_manager`;
  await login(page, invalid);
  await expect(page).toHaveURL(/asset_id=missing-asset/);
  await expect(page.getByTestId("operations-objects")).toBeVisible();
  await expect(page.getByText(/요청한 설비 missing-asset/)).toBeVisible();

  await page.reload();
  await expect(page).toHaveURL(/asset_id=missing-asset/);
  await expect(page.getByText(/요청한 설비 missing-asset/)).toBeVisible();
});

test("isolates Canonical API failures and preserves the four-screen fallback flow", async ({ page }) => {
  await page.route("**/api/projects/*/workspaces/*/predictive-maintenance/**", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "runtime_unavailable", message: "runtime unavailable in test" } }) });
  });
  await login(page, CLASSIC_OVERVIEW_PATH);
  await expect(page.getByTestId("operations-overview")).toBeVisible();
  await expect(page.getByText("보조 데이터 표시", { exact: true })).toBeVisible();
  await expect(page.getByText(/부분 연결 경고/)).toBeVisible();
  await expect(page.locator(".operations-priority-list button").first()).toBeVisible();
});

test("uses the verified report template when both LLM and deterministic report APIs fail", async ({ page }) => {
  await page.route("**/api/events/*/report", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "report_unavailable", message: "report unavailable in test" } }) });
  });
  await page.route("**/api/projects/*/workspaces/*/predictive-maintenance/dashboard**", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "runtime_unavailable", message: "runtime unavailable in test" } }) });
  });
  await login(page, `${Operations_PATH}?view=reports&dashboard=classic&report=executive-brief`);
  await expect(page.getByTestId("operations-executive-report")).toBeVisible();
  await expect(page.getByText("근거 기반 보고서", { exact: true })).toBeVisible();
  await expect(page.locator(".operations-report-document")).toBeVisible();
  await expect(page.getByText(/모델 확률은 실제 고장 발생을 확정하지 않습니다/)).toBeVisible();
});

test("keeps Reports inspection request available when predictive or report APIs fail", async ({ page }) => {
  await page.route("**/api/projects/*/workspaces/*/predictive-maintenance/dashboard**", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "runtime_unavailable", message: "runtime unavailable in test" } }) });
  });
  await page.route("**/api/events/*/evidence", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "evidence_unavailable", message: "evidence unavailable in test" } }) });
  });
  await page.route("**/api/events/*/report", async (route) => {
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "report_unavailable", message: "report unavailable in test" } }) });
  });
  await login(page, `${Operations_PATH}?view=reports&dashboard=classic&report=inspection-request`);
  await expect(page.getByTestId("operations-reports")).toBeVisible();
  await expect(page.getByTestId("operations-static-report")).toBeVisible();
  await expect(page.getByRole("heading", { name: "예지보전 점검 요청 보고서", exact: true })).toBeVisible();
  await expect(page.getByText("이 리포트는 점검 요청 산출물입니다.")).toBeVisible();
});

test("keeps all Operations views inside a 390px mobile viewport and exposes compact navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, CLASSIC_OVERVIEW_PATH);
  await expect(page.locator(".operations-app")).toBeVisible();

  await page.getByRole("button", { name: "메뉴 열기" }).click();
  await expect(page.locator(".operations-navigation")).toHaveClass(/is-open/);
  for (const label of ["Overview", "Assets", "작업요청", "Reports"]) {
    await page.locator(".operations-navigation nav").getByRole("button", { name: new RegExp(label) }).first().click();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    if (label !== "Reports") await page.getByRole("button", { name: "메뉴 열기" }).click();
  }
});

test("redirects a legacy project surface to the official Week 2 Operations", async ({ page }) => {
  await login(page, CLASSIC_OVERVIEW_PATH);
  await page.goto(`/app/projects/${PROJECT}/blueprint-v2`);
  await expect(page).toHaveURL(new RegExp(`${Operations_PATH}$`));
  await expect(page.getByTestId("operations-overview")).toBeVisible({ timeout: 15_000 });
});
