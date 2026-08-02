import { expect, type Page, test } from "@playwright/test";

const projectId = "manufacturing-demo-project";
const workspaceId = "manufacturing-demo";
const approvedCapture = process.env.CAPTURE_PALANTIR_FINAL === "1";
const captureRoot = approvedCapture
  ? "../docs/ui/palantir-overhaul/final"
  : "test-results/palantir-overhaul-candidate";

async function login(page: Page, email = "fde@ontology.local", password = "FDE!2026") {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/(app\/projects|admin)/);
  await page.evaluate(() => {
    localStorage.setItem("ontology-dashboard-theme", "light");
    document.documentElement.dataset.theme = "light";
  });
}

async function stabilizeVisualSurface(page: Page) {
  await page.addStyleTag({
    content: `
      *, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; caret-color: transparent !important; }
      time { visibility: hidden !important; }
    `,
  });
  await page.evaluate(() => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const patterns = [
      /\d{1,2}\/\d{1,2}\/\d{4},?\s+\d{1,2}:\d{2}:\d{2}\s*(AM|PM)?/gi,
      /\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*(오전|오후)?\s*\d{1,2}:\d{2}:\d{2}/g,
      /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z/g,
    ];
    while (walker.nextNode()) {
      const node = walker.currentNode;
      let value = node.textContent ?? "";
      for (const pattern of patterns) value = value.replace(pattern, "[timestamp]");
      if (value !== node.textContent) node.textContent = value;
    }
  });
  await page.waitForTimeout(150);
}

async function capture(page: Page, viewportName: string, name: string, route: string, readySelector: string) {
  await page.goto(route);
  await expect(page.locator(readySelector).first()).toBeVisible({ timeout: 45_000 });
  if (name === "dashboard") {
    await expect(page.locator(".dashboard-board-frame .fd-metric-strip").first()).toBeVisible({ timeout: 45_000 });
    await expect(page.getByText("Board module을 불러오고 있습니다.")).toHaveCount(0);
  }
  if (name === "ontology") {
    const objectSearch = page.getByLabel("Ontology object property search");
    await objectSearch.fill("M-014");
    await expect(page.locator(".ontology-object-table .fd-resource-table__row").filter({ hasText: "M-014" }).first()).toBeVisible({ timeout: 45_000 });
  }
  if (name === "governance") {
    await page.getByRole("button", { name: "Access & Policy", exact: true }).click();
    await expect(page.getByText("ACTIVE SCOPE", { exact: true })).toBeVisible();
  }
  if (name === "datasets") {
    const datasetSearch = page.getByLabel("Dataset catalog search");
    await datasetSearch.fill("final-dataset-materialization");
    await expect(page.locator(".dataset-resource-table .fd-resource-table__row").first()).toBeVisible({ timeout: 45_000 });
  }
  await stabilizeVisualSurface(page);
  await page.screenshot({
    path: `${captureRoot}/${viewportName}/${name}.png`,
    fullPage: false,
    animations: "disabled",
    caret: "hide",
  });
}

async function overflowDiagnostics(page: Page) {
  return page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const offenders = Array.from(document.querySelectorAll<HTMLElement>("body *"))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          selector: `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}${element.className && typeof element.className === "string" ? `.${element.className.trim().replace(/\s+/g, ".")}` : ""}`,
          right: Math.round(rect.right),
          left: Math.round(rect.left),
          width: Math.round(rect.width),
          scrollWidth: element.scrollWidth,
          clientWidth: element.clientWidth,
        };
      })
      .filter((item) => item.right > viewport + 2 || (item.left < -2 && item.selector !== "span.sr-only"))
      .sort((a, b) => Math.max(b.right - viewport, b.scrollWidth - b.clientWidth) - Math.max(a.right - viewport, a.scrollWidth - a.clientWidth))
      .slice(0, 10);
    return { documentOverflow: document.documentElement.scrollWidth - viewport, offenders };
  });
}

test.use({ colorScheme: "light" });

test("UI-06 Analysis uses a vertical path, insert controls, and tabbed result inspector", async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);
  await page.goto("/app/analysis/final-analysis-overhaul");
  await expect(page.getByText("BOARD PALETTE", { exact: true })).toBeVisible();
  const nodes = page.locator(".analysis-flow-node");
  await expect(nodes.first()).toBeVisible({ timeout: 45_000 });
  const positions = await nodes.evaluateAll((items) => items.map((item) => Math.round(item.getBoundingClientRect().left)));
  expect(new Set(positions).size).toBeLessThanOrEqual(2);
  const beforeCount = await nodes.count();
  await page.getByRole("button", { name: "Add output board", exact: true }).click();
  await expect(nodes).toHaveCount(beforeCount + 1);
  await nodes.filter({ hasText: "Risk by production line" }).click();
  await expect(page.getByRole("navigation", { name: "Analysis inspector sections" })).toBeVisible();
  await page.getByRole("button", { name: /Quality/ }).click();
  await expect(page.getByText("Null rate", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Lineage/ }).click();
  await expect(page.locator(".analysis-lineage-mini-canvas")).toBeVisible();
});

test("UI-05 Object Explorer switches Table, Explore, and Graph while preserving inspector tabs", async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);
  await page.goto(`/app/projects/${projectId}/workspaces/${workspaceId}/ontology`);
  await expect(page.locator(".ontology-object-table .fd-resource-table__row").first()).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("navigation", { name: "Object inspector sections" })).toBeVisible();
  await page.getByRole("button", { name: /Links/ }).click();
  await expect(page.locator(".ontology-link-list")).toBeVisible();
  await page.getByRole("button", { name: "Explore", exact: true }).click();
  await expect(page.locator(".ontology-exploration-root")).toBeVisible();
  await page.getByRole("button", { name: "Graph", exact: true }).click();
  await expect(page.locator(".ontology-flow-canvas")).toBeVisible();
  await page.getByRole("button", { name: /Actions/ }).click();
  await expect(page.locator(".ontology-action-list")).toBeVisible();
});

test("UI-07 Agent terminal links the composer, claims, evidence, checkpoints, and persisted trace", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page, "quality@ontology.local", "Quality!2026");
  await page.goto(`/app/projects/${projectId}/workspaces/${workspaceId}/agent?question=M-014+위험+상태+목록을+보여줘&objectType=equipment&objectId=M-014`);
  await page.getByLabel("Route", { exact: true }).selectOption("relational");
  await page.getByRole("button", { name: "Run governed query", exact: true }).click();
  await expect(page.getByText("VALIDATED CLAIMS", { exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Agent run inspector" })).toBeVisible();
  await expect(page.locator(".agent-evidence-list .bp6-card").first()).toBeVisible();
  await page.getByRole("button", { name: /CLAIMS/ }).click();
  await expect(page.locator(".agent-claim-list .bp6-card").first()).toBeVisible();
  await page.getByRole("button", { name: /CHECKPOINTS/ }).click();
  await expect(page.locator(".agent-orchestration-stepper")).toBeVisible();
  await page.getByRole("button", { name: /PERSISTED TRACE/ }).click();
  await expect(page.locator(".fd-activity-timeline")).toBeVisible();
  await expect(page.locator(".agent-composer")).toBeVisible();
});

test("UI-08 Dataset and Governance use dense record tables with persistent entity inspectors", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);
  await page.goto("/app/analysis/final-dataset-materialization");
  await page.getByRole("button", { name: /Run path/ }).click();
  await expect(page.getByText(/Run .* succeeded/)).toBeVisible({ timeout: 45_000 });
  await page.getByRole("button", { name: /Save dataset/ }).click();
  await expect(page.getByText(/생성 · .* rows/)).toBeVisible({ timeout: 30_000 });
  await page.goto(`/app/projects/${projectId}/datasets`);
  await expect(page.locator(".dataset-resource-table .fd-resource-table__row").first()).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("navigation", { name: "Dataset inspector sections" })).toBeVisible();
  await page.getByRole("button", { name: /Schema/ }).click();
  await expect(page.locator(".dataset-catalog-detail-pane .fd-property-table")).toBeVisible();
  await page.getByRole("button", { name: /Projections/ }).click();
  await expect(page.locator(".dataset-projection-inspector")).toBeVisible();

  await page.context().clearCookies();
  await login(page, "quality@ontology.local", "Quality!2026");
  await page.goto(`/app/projects/${projectId}/workspaces/${workspaceId}/governance`);
  await page.getByRole("button", { name: "Projection Health", exact: true }).click();
  await expect(page.locator(".governance-record-table .fd-resource-table__row").first()).toBeVisible();
  await expect(page.locator(".governance-record-inspector")).toBeVisible();
  await page.getByRole("button", { name: "Approvals", exact: true }).click();
  await expect(page.locator(".governance-record-layout")).toBeVisible();
});

test("UI-05 to UI-08 workbenches stay inside the 720px document viewport", async ({ page }) => {
  test.setTimeout(150_000);
  await page.setViewportSize({ width: 720, height: 500 });
  await login(page);
  const routes = [
    [`/app/analysis/final-overhaul-mobile`, ".analysis-flow-canvas"],
    [`/app/projects/${projectId}/workspaces/${workspaceId}/ontology`, ".ontology-workbench-page"],
    [`/app/projects/${projectId}/workspaces/${workspaceId}/agent`, ".agent-workbench-page"],
    [`/app/projects/${projectId}/datasets`, ".dataset-catalog-page"],
    [`/app/projects/${projectId}/workspaces/${workspaceId}/governance`, ".governance-workbench-page"],
  ] as const;

  for (const [route, selector] of routes) {
    await page.goto(route);
    await expect(page.locator(selector).first()).toBeVisible({ timeout: 45_000 });
    const diagnostics = await overflowDiagnostics(page);
    expect(diagnostics.documentOverflow, `${route}\n${JSON.stringify(diagnostics.offenders, null, 2)}`).toBeLessThanOrEqual(2);
  }
});

for (const viewport of [
  { name: "1440x1000", width: 1440, height: 1000 },
  { name: "1728x1117", width: 1728, height: 1117 },
  { name: "720x500", width: 720, height: 500 },
]) {
  test(`capture final overhaul surfaces at ${viewport.name}`, async ({ page }) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await login(page);
    await capture(page, viewport.name, "dashboard", "/app/projects/azure-pdm-demo-project", ".od-product-shell .react-grid-layout");

    await capture(page, viewport.name, "analysis", "/app/analysis/final-overhaul-capture", ".analysis-flow-canvas .react-flow");
    await capture(page, viewport.name, "project-home", `/app/projects/${projectId}/home`, ".project-home-page");
    await capture(page, viewport.name, "agent", `/app/projects/${projectId}/workspaces/${workspaceId}/agent`, ".agent-workbench-page");
    await capture(page, viewport.name, "ontology", `/app/projects/${projectId}/workspaces/${workspaceId}/ontology`, ".ontology-workbench-page");
    await capture(page, viewport.name, "datasets", `/app/projects/${projectId}/datasets`, ".dataset-catalog-page");
    await capture(page, viewport.name, "governance", `/app/projects/${projectId}/workspaces/${workspaceId}/governance`, ".governance-workbench-page");

    await page.context().clearCookies();
    await login(page, "admin@ontology.local", "OntologyAdmin!2026");
    await expect(page.locator(".admin-shell")).toBeVisible({ timeout: 45_000 });
    await expect(page.locator(".admin-metrics")).toBeVisible({ timeout: 45_000 });
    await stabilizeVisualSurface(page);
    await page.screenshot({ path: `${captureRoot}/${viewport.name}/admin.png`, fullPage: false, animations: "disabled", caret: "hide" });
  });
}
