import { expect, type Page, test } from "@playwright/test";

const ACCOUNTS = {
  admin: ["admin@ontology.local", "OntologyAdmin!2026"],
  executive: ["executive@ontology.local", "Executive!2026"],
  manager: ["manager@ontology.local", "Manager!2026"],
  engineer: ["engineer@ontology.local", "Engineer!2026"],
  technician: ["technician@ontology.local", "Technician!2026"],
  quality: ["quality@ontology.local", "Quality!2026"],
  datascientist: ["datascientist@ontology.local", "DataScience!2026"],
  fde: ["fde@ontology.local", "FDE!2026"],
} as const;

type Account = keyof typeof ACCOUNTS;

async function login(page: Page, returnPath?: string, account: Account = "manager") {
  const [email, password] = ACCOUNTS[account];
  await page.goto(returnPath ? `/login?returnTo=${encodeURIComponent(returnPath)}` : "/login");
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
}

test("preserves V1 through V3 and exposes an independent Commercial V4 composition", async ({ page }) => {
  const v4 = "/app/projects/manufacturing-demo-project/blueprint-v4";
  await login(page, v4, "admin");
  await expect(page).toHaveURL(new RegExp(`${v4}$`));
  await expect(page.locator('[data-application-id="ontology-commercial-v4"]')).toBeVisible();
  await expect(page.getByText("Commercial V4", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("V1–V3 preserved", { exact: true })).toBeVisible();
  await expect(page.getByText("Not the default route", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Identity & access/ }).click();
  await expect(page.getByText("Provider status", { exact: true })).toBeVisible();
  await expect(page.getByText("Enterprise OIDC", { exact: true })).toBeVisible();
  await expect(page.getByText("not configured", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Deployment/ }).click();
  await expect(page.getByText("Production topology", { exact: true })).toBeVisible();
  await expect(page.getByText("/health/ready", { exact: true })).toBeVisible();
  await expect(page.getByText("/app/projects/manufacturing-demo-project/blueprint-v4", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Distributed runtime/ }).click();
  await expect(page.getByText("Queue & coordination", { exact: true })).toBeVisible();
  await expect(page.getByText("not configured", { exact: true })).toBeVisible();
  await expect(page.getByText("Distributed rate-limit policy", { exact: true })).toBeVisible();
  await expect(page.getByText("Recent durable jobs", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Artifacts/ }).click();
  await expect(page.getByText("Object-storage readiness", { exact: true })).toBeVisible();
  await expect(page.getByText("Governed artifact catalog", { exact: true })).toBeVisible();
  await expect(page.getByText("No governed artifact has been registered for this Project.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Run reconciliation preview", exact: true }).click();
  await expect(page.getByText(/Reconciliation preview:/)).toBeVisible();

  await page.getByRole("button", { name: /Operations & SLO/ }).click();
  await expect(page.getByText("Telemetry readiness", { exact: true })).toBeVisible();
  await expect(page.getByText("Service level objectives", { exact: true })).toBeVisible();
  await expect(page.getByText("Alert policy", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /Ingestion/ }).click();
  await expect(page.getByText("Connector readiness", { exact: true })).toBeVisible();
  await expect(page.getByText("Canonical fixture ingestion", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Run ingestion", exact: true }).click();
  await expect(page.getByText(/Connector ingestion queued as job-/)).toBeVisible();

  await page.getByRole("button", { name: /Actions & functions/ }).click();
  await expect(page.getByText("Ontology Interfaces", { exact: true })).toBeVisible();
  await expect(page.getByText("Request asset inspection", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Preview action", exact: true }).click();
  await expect(page.getByText(/Action preview valid for 2 assets/)).toBeVisible();
  await page.getByRole("button", { name: "Run function", exact: true }).click();
  await expect(page.getByText(/Function succeeded: risk/)).toBeVisible();

  await page.getByRole("button", { name: /Lineage & evidence/ }).click();
  await expect(page.getByText("Global branches", { exact: true })).toBeVisible();
  await expect(page.getByText("End-to-end lineage", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Create review branch", exact: true }).click();
  await expect(page.getByText(/Branch v4-review-/)).toBeVisible();
  await page.getByRole("button", { name: "Check export policy", exact: true }).click();
  await expect(page.getByText(/Policy deny:/)).toBeVisible();

  await page.getByRole("button", { name: /^Objects/ }).click();
  await expect(page.getByText("Standard Object Views", { exact: true })).toBeVisible();
  await expect(page.getByText("Metadata application runtime", { exact: true })).toBeVisible();
  await page.getByLabel("Search Objects, Datasets, Actions and Functions").fill("CNC");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("CNC Machine M-001", { exact: true })).toBeVisible();

  await page.goto("/app/projects/manufacturing-demo-project");
  await expect(page.locator('[data-application-version="v4"]')).toHaveCount(0);

  for (const [path, selector] of [
    ["/app/projects/manufacturing-demo-project/blueprint", ".blueprint-preview"],
    ["/app/projects/manufacturing-demo-project/blueprint-v2", ".blueprint-v2"],
  ] as const) {
    await page.goto(path);
    await expect(page.locator(selector)).toBeVisible();
    await expect(page.locator('[data-application-version="v4"]')).toHaveCount(0);
  }
});

test("loads the manager overview without requesting permission-gated V4 snapshots", async ({ page }) => {
  const failures: Array<{ status: number; url: string }> = [];
  page.on("response", (response) => {
    if (response.status() >= 400 && !response.url().endsWith("/api/auth/me")) {
      failures.push({ status: response.status(), url: response.url() });
    }
  });
  await login(page, "/app/projects/manufacturing-demo-project/blueprint-v4");
  await expect(page.locator('[data-application-id="ontology-commercial-v4"]')).toBeVisible();
  await expect(page.getByText("Project context is unavailable", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: /Artifacts/ }).click();
  await expect(page.getByText("PERMISSION DENIED", { exact: true })).toBeVisible();
  expect(failures).toEqual([]);
});

test("loads the V4 overview for every demo role without a permission-denied application failure", async ({ browser }) => {
  for (const account of Object.keys(ACCOUNTS) as Account[]) {
    const page = await browser.newPage();
    const failures: Array<{ status: number; url: string }> = [];
    page.on("response", (response) => {
      if (response.status() >= 400 && !response.url().endsWith("/api/auth/me")) {
        failures.push({ status: response.status(), url: response.url() });
      }
    });
    await login(page, "/app/projects/manufacturing-demo-project/blueprint-v4", account);
    await expect(page.locator('[data-application-id="ontology-commercial-v4"]')).toBeVisible();
    await expect(page.getByText("Project context is unavailable", { exact: true })).toHaveCount(0);
    await expect(page.getByText("permission_denied", { exact: false })).toHaveCount(0);
    expect(failures, account).toEqual([]);
    await page.close();
  }
});

test("keeps the V4 manifest usable on a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "/app/projects/manufacturing-demo-project/blueprint-v4?surface=settings");
  await expect(page.locator('[data-application-version="v4"]')).toBeVisible();
  await expect(page.getByText("Version-scoped runtime", { exact: true })).toBeVisible();
  await expect(page.getByText("Tenant persistence readiness", { exact: true })).toBeVisible();
  await expect(page.getByText(/Production (PostgreSQL required|ready)/, { exact: true })).toBeVisible();
  const widths = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  }));
  expect(widths.scroll).toBe(widths.client);
});
