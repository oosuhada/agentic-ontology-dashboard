import { expect, type Page, test } from "@playwright/test";

const projectRoute = "/app/projects/manufacturing-demo-project";

async function login(page: Page, email: string, password: string) {
  await page.addInitScript(() => {
    localStorage.setItem("ontology-dashboard-theme", "dark");
    localStorage.setItem("ontology-dashboard:locale", "ko-KR");
  });
  await page.goto("/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app(?:\/|$)/);
}

interface SurfaceMetric {
  selector: string;
  background: [number, number, number];
  text: [number, number, number];
  backgroundLuminance: number;
  contrast: number;
}

async function surfaceMetrics(page: Page, selectors: string[]): Promise<SurfaceMetric[]> {
  return page.evaluate((targets) => {
    type Rgba = [number, number, number, number];
    const parse = (value: string): Rgba => {
      const match = value.match(/rgba?\((\d+(?:\.\d+)?)[, ]+(\d+(?:\.\d+)?)[, ]+(\d+(?:\.\d+)?)(?:[, /]+(\d+(?:\.\d+)?))?\)/);
      if (!match) return [0, 0, 0, 0];
      return [Number(match[1]), Number(match[2]), Number(match[3]), match[4] === undefined ? 1 : Number(match[4])];
    };
    const composite = (foreground: Rgba, background: Rgba): Rgba => {
      const alpha = foreground[3] + background[3] * (1 - foreground[3]);
      if (alpha === 0) return [0, 0, 0, 0];
      return [
        (foreground[0] * foreground[3] + background[0] * background[3] * (1 - foreground[3])) / alpha,
        (foreground[1] * foreground[3] + background[1] * background[3] * (1 - foreground[3])) / alpha,
        (foreground[2] * foreground[3] + background[2] * background[3] * (1 - foreground[3])) / alpha,
        alpha,
      ];
    };
    const effectiveBackground = (element: Element): Rgba => {
      const chain: Element[] = [];
      let current: Element | null = element;
      while (current) {
        chain.unshift(current);
        current = current.parentElement;
      }
      let result: Rgba = [17, 24, 32, 1];
      for (const node of chain) result = composite(parse(getComputedStyle(node).backgroundColor), result);
      return result;
    };
    const luminance = (rgb: [number, number, number]) => {
      const values = rgb.map((channel) => {
        const value = channel / 255;
        return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2];
    };
    const output = [];
    for (const selector of targets) {
      const element = document.querySelector(selector);
      if (!element) throw new Error(`Missing dark-mode target: ${selector}`);
      const rect = element.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) throw new Error(`Hidden dark-mode target: ${selector}`);
      const backgroundRgba = effectiveBackground(element);
      const textRgba = parse(getComputedStyle(element).color);
      const background: [number, number, number] = [backgroundRgba[0], backgroundRgba[1], backgroundRgba[2]];
      const text: [number, number, number] = [textRgba[0], textRgba[1], textRgba[2]];
      const backgroundLuminance = luminance(background);
      const textLuminance = luminance(text);
      output.push({
        selector,
        background,
        text,
        backgroundLuminance,
        contrast: (Math.max(backgroundLuminance, textLuminance) + 0.05) / (Math.min(backgroundLuminance, textLuminance) + 0.05),
      });
    }
    return output;
  }, selectors);
}

function expectDarkSurfaces(metrics: SurfaceMetric[]) {
  for (const metric of metrics) {
    expect(metric.backgroundLuminance, `${metric.selector} must use a dark effective background`).toBeLessThan(0.18);
    expect(metric.contrast, `${metric.selector} must keep readable foreground contrast`).toBeGreaterThanOrEqual(4.5);
  }
}

test.use({ viewport: { width: 1440, height: 1000 }, colorScheme: "dark" });

test("engineer server-filtered boards inherit the complete dark theme", async ({ page }) => {
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await page.goto(projectRoute);
  await expect(page.locator(".server-filtered-event-scope").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expectDarkSurfaces(await surfaceMetrics(page, [
    ".dashboard-board-frame",
    ".board-runtime-body",
    ".server-filtered-event-scope",
    ".server-filtered-event-scope > .advanced-board",
  ]));
});

test("Engineer Planner Assistant inputs, tabs, notices, and results stay dark", async ({ page }) => {
  test.setTimeout(90_000);
  await login(page, "engineer@ontology.local", "Engineer!2026");
  await page.goto(projectRoute);
  await expect(page.getByRole("combobox", { name: "Workspace" })).toHaveValue(
    "manufacturing-demo",
    { timeout: 60_000 },
  );
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1_000);
  await expect(page.getByRole("combobox", { name: "Workspace" })).toHaveValue("manufacturing-demo");
  const planner = page.locator(".planner-assistant-card:visible").first();
  const tabs = page.locator(".dashboard-tabs button");
  for (let index = 0; index < await tabs.count(); index += 1) {
    if (await planner.isVisible()) break;
    await tabs.nth(index).click();
    await page.waitForTimeout(250);
  }
  await expect(planner).toBeVisible({ timeout: 60_000 });
  await expect(planner).toHaveAttribute("data-workspace-id", "manufacturing-demo");
  await planner.getByRole("button", { name: "Draft 생성", exact: true }).click();
  await expect(planner.locator(".planner-result")).toBeVisible({ timeout: 30_000 });
  expectDarkSurfaces(await surfaceMetrics(page, [
    ".planner-assistant-card",
    ".planner-tool-tabs button.active",
    ".planner-prompt-row textarea",
    ".planner-safety-note",
    ".planner-result > code",
    ".planner-object-grid article",
  ]));

  if (process.env.CAPTURE_TEAM_SHARE_ADAPTIVE === "1") {
    await planner.scrollIntoViewIfNeeded();
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    await page.screenshot({
      path: "public/team-share-adaptive-assets/06-dashboard-dark-mode.png",
      animations: "disabled",
      caret: "hide",
    });
  }
});

test("ML Validator empty, table, tabs, and form controls stay dark", async ({ page }) => {
  test.setTimeout(90_000);
  await login(page, "datascientist@ontology.local", "DataScience!2026");
  await page.goto(
    "/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/modeling",
  );
  await expect(page.locator(".mlv-empty-state")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expectDarkSurfaces(await surfaceMetrics(page, [
    ".mlv-shell",
    ".mlv-header",
    ".mlv-empty-state",
    ".mlv-panel",
    ".mlv-toolbar",
    ".mlv-toolbar button[aria-selected='true']",
    ".mlv-toolbar select",
    ".mlv-metrics article",
    ".mlv-table thead",
    ".mlv-table th",
  ]));
  const disabled = page.locator(".mlv-panel button:disabled");
  if (await disabled.count()) {
    await expect(disabled.first()).toBeVisible();
    const opacity = await disabled.first().evaluate((element) => Number(getComputedStyle(element).opacity));
    expect(opacity).toBeGreaterThanOrEqual(0.4);
  }
});

test("Dataset, Ontology, Governance, and Analysis workbenches keep dark surfaces", async ({ page }) => {
  test.setTimeout(150_000);
  await login(page, "fde@ontology.local", "FDE!2026");

  const routes: Array<{ path: string; ready: string; surfaces: string[] }> = [
    {
      path: "/app/projects/manufacturing-demo-project/datasets",
      ready: ".dataset-catalog-page",
      surfaces: [
        ".dataset-catalog-page",
        ".dataset-catalog-list-pane",
        ".dataset-catalog-detail-pane",
        ".dataset-catalog-toolbar",
      ],
    },
    {
      path: "/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/ontology",
      ready: ".ontology-workbench-page",
      surfaces: [
        ".ontology-workbench-page",
        ".ontology-query-toolbar",
        ".ontology-object-rail",
        ".ontology-primary-view",
      ],
    },
    {
      path: "/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/governance",
      ready: ".governance-workbench-page",
      surfaces: [
        ".governance-workbench-page",
        ".governance-tabs",
        ".governance-overview",
        ".governance-panel",
      ],
    },
    {
      path: "/app/analysis/risk-event-portfolio",
      ready: ".analysis-workbench",
      surfaces: [
        ".analysis-workbench",
        ".analysis-notice",
        ".analysis-projection-toolbar",
        ".analysis-projection-layout",
      ],
    },
  ];

  for (const route of routes) {
    await page.goto(route.path);
    await expect(page.locator(route.ready)).toBeVisible({ timeout: 60_000 });
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    expectDarkSurfaces(await surfaceMetrics(page, route.surfaces));
    const geometry = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    }));
    expect(geometry.scrollWidth, `horizontal overflow at ${route.path}`).toBeLessThanOrEqual(
      geometry.viewportWidth + 1,
    );
  }
});
