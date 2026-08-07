import { expect, type Page, test } from "@playwright/test";

const apiURL = process.env.PLAYWRIGHT_API_URL ?? "http://127.0.0.1:8200";

async function login(page: Page, email = "manager@ontology.local", password = "Manager!2026") {
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/projects\//);
  await expect(page.getByLabel("Project", { exact: true })).toBeVisible();
  if (await page.getByLabel("Project", { exact: true }).inputValue() !== "manufacturing-demo-project") {
    await page.getByLabel("Project", { exact: true }).selectOption("manufacturing-demo-project");
    await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project$/);
  }
}

async function expectAccessibleSurface(page: Page) {
  await expect(page.getByRole("main")).toBeVisible({ timeout: 45_000 });
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
      const explicitLabel = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
      if (!accessibleName(element) && !explicitLabel && !element.closest("label")) {
        const detail = [
          element.tagName.toLowerCase(),
          element.getAttribute("class") ?? "",
          element.getAttribute("placeholder") ?? "",
          element.getAttribute("type") ?? "",
        ].filter(Boolean).join(" · ");
        issues.push(`missing accessible name: ${detail}`);
      }
    });
    document.querySelectorAll("img").forEach((image) => {
      if (!image.hasAttribute("alt")) issues.push("image missing alt");
    });
    const ids = Array.from(document.querySelectorAll("[id]"), (element) => element.id).filter(Boolean);
    ids.filter((id, index) => ids.indexOf(id) !== index).forEach((id) => issues.push(`duplicate id: ${id}`));
    if (document.querySelectorAll("main").length !== 1) issues.push("page must contain exactly one main landmark");
    return [...new Set(issues)];
  });
  expect(violations).toEqual([]);
}

test("modern dashboard runtime exposes chart, virtual grid, ontology graph, analysis flow and persistent theme", async ({ page }) => {
  test.setTimeout(60_000);
  await login(page);

  await expect(page.locator(".react-grid-layout")).toBeVisible();
  await expect(page.locator(".generic-echarts-renderer canvas")).toBeVisible();
  await expect(page.locator(".generic-data-table")).toBeVisible();
  await expect(page.locator(".generic-data-table-body > button").first()).toBeVisible();

  await page.getByRole("button", { name: "근거와 후속", exact: true }).click();
  await expect(page.locator(".ontology-react-flow .react-flow")).toBeVisible();
  await expect(page.locator(".ontology-react-flow .react-flow__node").first()).toBeVisible();

  await page.keyboard.press("Control+K");
  await expect(page.getByRole("dialog", { name: "Command palette" })).toBeVisible();
  await page.getByRole("dialog", { name: "Command palette" }).getByRole("button", { name: /Open Analysis Path/ }).click();

  await expect(page.locator(".analysis-flow-canvas .react-flow")).toBeVisible();
  await expect(page.locator(".analysis-flow-node")).toHaveCount(4);
  await expect(page.locator(".analysis-result-echart canvas")).toBeVisible();
  await page.getByRole("button", { name: /Run path/ }).click();
  await expect(page.getByText(/Run .* succeeded/)).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("server run", { exact: true })).toBeVisible();
  await expect(page.locator(".analysis-lineage-mini-canvas .react-flow")).toBeVisible();
  await expect(page.locator(".analysis-lineage-mini-canvas .analysis-lineage-node").first()).toBeVisible();

  await page.getByRole("button", { name: "테마 전환" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
});

test("analysis save publishes a server snapshot and dashboard table uses server pagination", async ({ page }) => {
  test.setTimeout(90_000);
  await login(page, "fde@ontology.local", "FDE!2026");
  await page.goto("/app/analysis/playwright-server-analysis");
  await expect(page.getByText(/Server Analysis v1|서버에 생성했습니다/)).toBeVisible();

  await page.getByRole("button", { name: /Run path/ }).click();
  await expect(page.getByText(/Run .* succeeded/)).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText("server run", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Save dataset/ }).click();
  await expect(page.getByText(/생성 · .* rows/)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/freshness ·/)).toBeVisible();

  await page.getByRole("button", { name: "Dashboards", exact: true }).click();
  await expect(page.locator(".generic-pagination-controls")).toBeVisible();
  await expect(page.locator(".data-grid-footer").filter({ hasText: "Server pagination" })).toBeVisible();
});

test("Project Home, active role context and Dataset Catalog are navigable", async ({ page }) => {
  test.setTimeout(60_000);
  await login(page, "fde@ontology.local", "FDE!2026");
  await expect(page.getByLabel("Role")).toHaveValue("fde");
  const datasetNavigation = page.getByLabel("Product navigation").getByRole("button", { name: "Datasets", exact: true });
  await expect(datasetNavigation).toBeEnabled();
  await expect(datasetNavigation).not.toContainText("SOON");
  await page.getByRole("button", { name: "Project Home", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/projects\/manufacturing-demo-project\/home$/);
  await expect(page.getByText("PROJECT HOME", { exact: true })).toBeVisible();
  await expect(page.getByText("Typed Project 3 boundary", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Datasets", exact: true }).first().click();
  await expect(page).toHaveURL(/\/datasets$/);
  await expect(page.getByText("DATASET CATALOG", { exact: true })).toBeVisible();
  await expect(page.getByPlaceholder("Search name, slug, description")).toBeVisible();
  await expect(page.locator(".dataset-catalog-pagination")).toBeVisible();
});

test("all primary Workbench routes pass accessibility and 200-percent-equivalent viewport checks", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 720, height: 500 });
  await login(page, "fde@ontology.local", "FDE!2026");

  const routes = [
    ["/app/projects/manufacturing-demo-project", ".od-product-shell"],
    ["/app/analysis/accessibility-route", ".analysis-flow-canvas"],
    ["/app/projects/manufacturing-demo-project/home", ".project-home-page"],
    ["/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/agent", ".agent-workbench-page"],
    ["/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/ontology", ".ontology-workbench-page"],
    ["/app/projects/manufacturing-demo-project/datasets", ".dataset-catalog-page"],
    ["/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/governance", ".governance-workbench-page"],
  ] as const;

  for (const [route, readySelector] of routes) {
    await page.goto(route);
    await expect(page.locator(readySelector).first()).toBeVisible({ timeout: 45_000 });
    await expectAccessibleSurface(page);
    const documentOverflow = await page.evaluate(() => (
      document.documentElement.scrollWidth - document.documentElement.clientWidth
    ));
    expect(documentOverflow).toBeLessThanOrEqual(2);
  }
});

test("archived Project deep links render a tombstone instead of silently switching scope", async ({ page, request }) => {
  await page.goto("/login");
  await page.getByLabel("이메일").fill("admin@ontology.local");
  await page.getByLabel("비밀번호").fill("OntologyAdmin!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  const cookies = await page.context().cookies();
  const csrf = cookies.find((cookie) => cookie.name === "ontology_csrf")?.value;
  expect(csrf).toBeTruthy();
  const headers = {
    Cookie: cookies.map((cookie) => `${cookie.name}=${cookie.value}`).join("; "),
    "X-CSRF-Token": csrf ?? "",
  };
  const created = await request.post(`${apiURL}/api/admin/projects`, {
    headers,
    data: {
      slug: "playwright-archived-project",
      display_name: "Playwright Archived Project",
      description: "Tombstone route fixture",
      domain_pack_code: "generic",
      status: "draft",
    },
  });
  expect(created.ok()).toBe(true);
  const project = await created.json() as { id: string };
  const archived = await request.patch(`${apiURL}/api/admin/projects/${encodeURIComponent(project.id)}`, {
    headers,
    data: { status: "archived" },
  });
  expect(archived.ok()).toBe(true);

  await page.goto(`/app/projects/${encodeURIComponent(project.id)}/home`);
  await expect(page.getByText("PROJECT UNAVAILABLE", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "이 Project는 보관되었거나 삭제되었습니다" })).toBeVisible();
  await expect(page.getByText(project.id, { exact: true })).toBeVisible();
});

test("dashboard editor supports undo redo and reload draft recovery", async ({ page }) => {
  test.setTimeout(60_000);
  await login(page);
  await page.getByRole("button", { name: "편집", exact: true }).click();

  page.once("dialog", async (dialog) => dialog.accept("Recovered Operations"));
  await page.locator(".add-tab-button").click();
  await expect(page.getByRole("button", { name: /Recovered Operations/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Undo dashboard edit" })).toBeEnabled();

  await page.getByRole("button", { name: "Undo dashboard edit" }).click();
  await expect(page.getByRole("button", { name: /Recovered Operations/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Redo dashboard edit" })).toBeEnabled();

  await page.getByRole("button", { name: "Redo dashboard edit" }).click();
  await expect(page.getByRole("button", { name: /Recovered Operations/ })).toBeVisible();
  await expect.poll(() => page.evaluate(() => (
    Object.keys(window.localStorage).some((key) => key.startsWith("ontology-dashboard:dashboard-draft:"))
  ))).toBe(true);

  page.on("dialog", async (dialog) => dialog.accept());
  await page.reload();
  await expect(page.getByText("저장되지 않은 Dashboard 초안이 있습니다", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "초안 복구", exact: true }).click();
  await expect(page.getByRole("button", { name: /Recovered Operations/ })).toBeVisible();
  await expect(page.getByText("Unsaved changes", { exact: true })).toBeVisible();
});

test("cross-filter selection updates downstream boards", async ({ page }) => {
  await login(page);
  await page.locator(".generic-data-table-body > button").nth(1).click();
  await expect(page.locator(".cross-filter-summary")).toContainText("active cross-filter");
  await expect(page.locator(".dashboard-board-frame.is-affected").first()).toBeVisible();
  await expect(page.locator(".dashboard-cross-filter-runtime.server").first()).toContainText("Server filtered");
  await page.locator(".cross-filter-summary").getByRole("button", { name: "Clear" }).click();
  await expect(page.locator(".cross-filter-summary")).toHaveCount(0);
});

test("analysis route adds a pinned board reference to dashboard", async ({ page }) => {
  await login(page);
  await page.goto("/app/analysis/maintenance-risk-analysis");
  await expect(page).toHaveURL(/\/app\/analysis\/maintenance-risk-analysis$/);
  await expect(page.getByText(/maintenance-risk-analysis/).first()).toBeVisible();
  await page.locator(".analysis-flow-node").filter({ hasText: "Risk by production line" }).click();
  await page.getByRole("button", { name: /Add to Dashboard/ }).click();
  await expect(page.getByText(/pinned reference/)).toBeVisible();
  await page.getByRole("button", { name: "Dashboards", exact: true }).click();
  await expect(page.locator(".analysis-reference-runtime")).toContainText("maintenance-risk-analysis");
  await page.getByRole("button", { name: "편집", exact: true }).click();
  await page.getByRole("button", { name: "개인 레이아웃 저장" }).click();
  await expect(page.getByText(/다음 로그인에서도 복원됩니다/)).toBeVisible();
  await page.reload();
  await expect(page.locator(".analysis-reference-runtime")).toContainText("maintenance-risk-analysis");
});

test("react-grid-layout width persists through dashboard preferences", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "편집", exact: true }).click();

  const item = page.locator(".dashboard-board-title strong", { hasText: /^권장 조치$/ })
    .locator("xpath=ancestor::article[contains(@class,'dashboard-board-frame')]");
  await item.click();
  await expect(page.getByRole("navigation", { name: "Board inspector sections" })).toBeVisible();
  await page.getByLabel("Layout 폭").selectOption("6");
  await expect(item).toHaveAttribute("data-grid-w", "6");

  const saveButton = page.getByRole("button", { name: "개인 레이아웃 저장" });
  await expect(saveButton).toBeVisible();
  await saveButton.click();
  await expect(page.getByText(/다음 로그인에서도 복원됩니다/)).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "편집", exact: true }).click();

  const restoredFrame = page.locator(".dashboard-board-title strong", { hasText: /^권장 조치$/ })
    .locator("xpath=ancestor::article[contains(@class,'dashboard-board-frame')]");
  await expect(restoredFrame).toHaveAttribute("data-grid-w", "6");
});
