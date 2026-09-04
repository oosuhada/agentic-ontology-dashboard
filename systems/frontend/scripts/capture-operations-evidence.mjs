import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const baseUrl = (process.env.Operations_CAPTURE_BASE_URL ?? "http://127.0.0.1:3100").replace(/\/$/, "");
const email = process.env.Operations_CAPTURE_EMAIL ?? "manager@ontology.local";
const password = process.env.Operations_CAPTURE_PASSWORD ?? "Manager!2026";
const projectId = process.env.Operations_CAPTURE_PROJECT_ID ?? "manufacturing-demo-project";
const scriptDir = dirname(fileURLToPath(import.meta.url));
const outputDir = resolve(
  process.env.Operations_CAPTURE_OUTPUT_DIR
    ?? resolve(scriptDir, "../../../docs/operations/history/2026-08-week2/assets/week2-operations-frontend-convergence"),
);
const operationsPath = `/app/projects/${projectId}/operations`;

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  ignoreHTTPSErrors: true,
});
const page = await context.newPage();

async function login(returnTo = operationsPath) {
  await page.goto(`${baseUrl}/login?returnTo=${encodeURIComponent(returnTo)}`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.waitForURL(new RegExp(`/app/projects/${projectId}`));
}

async function capture(name, locator = page.locator(".operations-app")) {
  await locator.waitFor({ state: "visible" });
  await locator.screenshot({ path: resolve(outputDir, name) });
}

try {
  await login();
  await page.getByTestId("operations-overview").waitFor();
  await capture("01-overview-desktop.png");

  await page.locator(".operations-priority-list button").first().click();
  await page.getByTestId("operations-objects").waitFor();
  await capture("02-objects-inspector-desktop.png");

  await page.getByRole("button", { name: /Operations에서 조치 검토/ }).click();
  await page.getByTestId("operations-operations").waitFor();
  await capture("03-operations-desktop.png");

  await page.getByRole("button", { name: /Executive Report 반영/ }).click();
  await page.locator(".operations-report-document").waitFor();
  await capture("04-executive-report-a4.png", page.locator(".operations-report-document"));

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}${operationsPath}?view=overview`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("operations-overview").waitFor();
  await capture("05-overview-mobile.png");
} finally {
  await browser.close();
}

console.log(`Operations evidence captured from ${baseUrl} to ${outputDir}`);
