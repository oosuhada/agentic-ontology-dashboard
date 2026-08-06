import { expect, type Page, test } from "@playwright/test";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/(projects\/|$)|\/admin$/);
  if (!page.url().endsWith("/admin")) {
    await expect(page.getByLabel("Project", { exact: true })).toBeVisible();
    if (await page.getByLabel("Project", { exact: true }).inputValue() !== "manufacturing-demo-project") {
      await page.getByLabel("Project", { exact: true }).selectOption("manufacturing-demo-project");
      await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
    }
  }
}

const ontologyRoute = "/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/ontology";
const agentRoute = "/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/agent";
const governanceRoute = "/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/governance";

test("ontology deep link restores through reload and browser history with a visual baseline artifact", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page, "manager@ontology.local", "Manager!2026");

  await page.goto(ontologyRoute);
  await expect(page).toHaveURL(new RegExp(`${ontologyRoute}$`));
  await expect(page.getByText("ONTOLOGY WORKBENCH", { exact: true })).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".ontology-workbench-grid")).toBeVisible();
  await expect(page.locator(".ontology-object-rail")).toBeVisible();
  await expect(page.locator(".ontology-graph-pane")).toBeVisible();
  await expect(page.locator(".ontology-inspector-pane")).toBeVisible();

  const gridColumns = await page.locator(".ontology-workbench-grid").evaluate((element) =>
    getComputedStyle(element).gridTemplateColumns.split(" ").map((value) => Math.round(Number.parseFloat(value))),
  );
  expect(gridColumns).toHaveLength(3);
  expect(gridColumns[0]).toBe(255);
  expect(gridColumns[2]).toBe(300);
  expect(gridColumns[1]).toBeGreaterThanOrEqual(650);

  const screenshot = await page.screenshot({
    fullPage: true,
    animations: "disabled",
    caret: "hide",
  });
  expect(screenshot.byteLength).toBeGreaterThan(60_000);
  await testInfo.attach("stage48-ontology-workbench-1440x1000", {
    body: screenshot,
    contentType: "image/png",
  });

  await page.reload();
  await expect(page).toHaveURL(new RegExp(`${ontologyRoute}$`));
  await expect(page.getByText("ONTOLOGY WORKBENCH", { exact: true })).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  await page.goForward();
  await expect(page).toHaveURL(new RegExp(`${ontologyRoute}$`));
  await expect(page.locator(".ontology-workbench-grid")).toBeVisible();
});

test("ontology workbench rejects unauthorized project and mismatched project-workspace routes", async ({ page }) => {
  test.setTimeout(90_000);
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await page.goto("/app/projects/not-accessible/workspaces/azure-fleet-maintenance/ontology");
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  await expect(page.locator(".od-product-shell .react-grid-layout")).toBeVisible();

  await page.goto("/app/projects/azure-fleet-maintenance-project/workspaces/manufacturing-demo/ontology");
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  await expect(page.getByText("ONTOLOGY WORKBENCH", { exact: true })).toHaveCount(0);
});

test("Agent Evidence Workbench runs a scoped query, links claims to evidence and restores a persisted run", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page, "quality@ontology.local", "Quality!2026");
  await page.goto(`${agentRoute}?question=M-014+위험+상태+목록을+보여줘&objectType=equipment&objectId=M-014`);

  await expect(page.getByText("AGENT EVIDENCE WORKBENCH", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Question", { exact: true })).toHaveValue("M-014 위험 상태 목록을 보여줘");
  await page.getByLabel("Route", { exact: true }).selectOption("relational");
  await page.getByRole("button", { name: "Run governed query", exact: true }).click();

  await expect(page.getByText("VALIDATED CLAIMS", { exact: true })).toBeVisible();
  await expect(page.getByText("EVIDENCE TRACE", { exact: true })).toBeVisible();
  await expect(page.getByText("ORCHESTRATION LINEAGE", { exact: true })).toBeVisible();
  await expect(page.getByText("PERSISTED RUNS", { exact: true })).toBeVisible();
  await expect(page.locator(".agent-server-runs button").filter({ hasText: "M-014 위험 상태 목록을 보여줘" }).first()).toBeVisible();
  await page.getByPlaceholder("Question filter").fill("M-014 위험");
  await expect(page.locator(".agent-server-runs button").filter({ hasText: "M-014 위험 상태 목록을 보여줘" }).first()).toBeVisible();
  await page.getByPlaceholder("Question filter").fill("not-present-query");
  await expect(page.getByText("조건에 맞는 persisted run이 없습니다.", { exact: true })).toBeVisible();
  await page.getByPlaceholder("Question filter").fill("");
  await expect(page.locator(".agent-claim-list .bp6-card").first()).toBeVisible();
  await expect(page.locator(".agent-evidence-list .bp6-card").first()).toBeVisible();

  const evidenceId = await page.locator(".agent-claim-evidence-links button").first().innerText();
  await page.locator(".agent-claim-evidence-links button").first().click();
  await expect(page.locator(".agent-evidence-list .bp6-card.selected")).toContainText(evidenceId.trim());

  const runId = await page.locator(".agent-pane-heading strong").first().innerText();
  await expect(page).toHaveURL(new RegExp(`run=${encodeURIComponent(runId)}$`));
  const screenshot = await page.screenshot({ fullPage: true, animations: "disabled", caret: "hide" });
  expect(screenshot.byteLength).toBeGreaterThan(60_000);
  await testInfo.attach("agent-evidence-workbench-1440x1000", { body: screenshot, contentType: "image/png" });

  await page.reload();
  await expect(page.getByText("AGENT EVIDENCE WORKBENCH", { exact: true })).toBeVisible();
  await expect(page.locator(".agent-pane-heading strong").first()).toHaveText(runId);
  await expect(page.getByText("PERSISTED TRACE", { exact: true })).toBeVisible();
});

test("Agent Workbench rejects an unauthorized project deep link", async ({ page }) => {
  await login(page, "quality@ontology.local", "Quality!2026");
  await page.goto("/app/projects/not-accessible/workspaces/manufacturing-demo/agent");
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  await expect(page.getByText("AGENT EVIDENCE WORKBENCH", { exact: true })).toHaveCount(0);
});

test("quality auditor restores the Governance Workbench and captures its reference artifact", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page, "quality@ontology.local", "Quality!2026");
  await page.goto(ontologyRoute);
  await expect(page.getByText("ONTOLOGY WORKBENCH", { exact: true })).toBeVisible();
  await page.getByPlaceholder(/M-014와 연결된 최근 위험 사건/).fill("선택 설비의 위험 사건과 관계, 근거 문서를 보여줘");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.locator(".ontology-agent-result")).toBeVisible();

  await page.goto(governanceRoute);
  await expect(page).toHaveURL(new RegExp(`${governanceRoute}$`));
  await expect(page.getByText("GOVERNANCE WORKBENCH", { exact: true })).toBeVisible();
  await expect(page.getByText("Project governance boundary", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Agent Runs", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Projection Health", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Access & Policy", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Agent Runs", exact: true }).click();
  await expect(page.getByRole("heading", { name: "선택 설비의 위험 사건과 관계, 근거 문서를 보여줘", exact: true })).toBeVisible();
  await expect(page.getByText("VALIDATED CLAIMS", { exact: true })).toBeVisible();
  await expect(page.getByText("EVIDENCE SOURCES", { exact: true })).toBeVisible();
  const governanceRunId = await page.locator(".governance-panel-heading strong").filter({ hasText: /^agent-/ }).innerText();
  await page.getByRole("button", { name: "Open Agent Evidence", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/agent\\?run=${encodeURIComponent(governanceRunId)}$`));
  await expect(page.locator(".agent-pane-heading strong").first()).toHaveText(governanceRunId);
  await page.getByRole("button", { name: "Governance", exact: true }).click();
  await page.getByRole("button", { name: "Overview", exact: true }).click();

  const screenshot = await page.screenshot({
    fullPage: true,
    animations: "disabled",
    caret: "hide",
  });
  expect(screenshot.byteLength).toBeGreaterThan(50_000);
  await testInfo.attach("stage51-governance-workbench-1440x1000", {
    body: screenshot,
    contentType: "image/png",
  });

  await page.reload();
  await expect(page).toHaveURL(new RegExp(`${governanceRoute}$`));
  await expect(page.getByText("GOVERNANCE WORKBENCH", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Access & Policy", exact: true }).click();
  await expect(page.getByLabel("Access and policy").getByText("ACTIVE SCOPE", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Users", exact: true })).toHaveCount(0);
});

test("Governance Workbench remains project scoped and is hidden from roles without governance permission", async ({ page }) => {
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await page.goto(governanceRoute);
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  await expect(page.getByText("GOVERNANCE WORKBENCH", { exact: true })).toHaveCount(0);

  await page.goto("/app/projects/azure-fleet-maintenance-project/workspaces/azure-fleet-maintenance/governance");
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
});
