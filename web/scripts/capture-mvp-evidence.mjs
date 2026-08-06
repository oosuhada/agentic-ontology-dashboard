import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "playwright";

const baseUrl = (process.env.MVP_CAPTURE_BASE_URL ?? "http://127.0.0.1:3100").replace(/\/$/, "");
const email = process.env.MVP_CAPTURE_EMAIL ?? "manager@ontology.local";
const password = process.env.MVP_CAPTURE_PASSWORD ?? "Manager!2026";
const projectId = process.env.MVP_CAPTURE_PROJECT_ID ?? "manufacturing-demo-project";
const outputDir = resolve(
  process.env.MVP_CAPTURE_OUTPUT_DIR
    ?? resolve(process.cwd(), "../docs/10-product/mentoring-mvp-2026-08/assets/week2-mvp-frontend-convergence"),
);
const mvpPath = `/app/projects/${projectId}/mvp`;

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  ignoreHTTPSErrors: true,
});
const page = await context.newPage();

async function login(returnTo = mvpPath) {
  await page.goto(`${baseUrl}/login?returnTo=${encodeURIComponent(returnTo)}`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("이메일").fill(email);
  await page.getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await page.waitForURL(new RegExp(`/app/projects/${projectId}`));
}

async function capture(name, locator = page.locator(".mvp-app")) {
  await locator.waitFor({ state: "visible" });
  await locator.screenshot({ path: resolve(outputDir, name) });
}

try {
  await login();
  await page.getByTestId("mvp-overview").waitFor();
  await capture("01-overview-desktop.png");

  await page.locator(".mvp-priority-list button").first().click();
  await page.getByTestId("mvp-objects").waitFor();
  await capture("02-objects-inspector-desktop.png");

  await page.getByRole("button", { name: /Operations에서 조치 검토/ }).click();
  await page.getByTestId("mvp-operations").waitFor();
  await capture("03-operations-desktop.png");

  await page.getByRole("button", { name: /Executive Report 반영/ }).click();
  await page.locator(".mvp-report-document").waitFor();
  await capture("04-executive-report-a4.png", page.locator(".mvp-report-document"));

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}${mvpPath}?view=overview`, { waitUntil: "domcontentloaded" });
  await page.getByTestId("mvp-overview").waitFor();
  await capture("05-overview-mobile.png");
} finally {
  await browser.close();
}

console.log(`MVP evidence captured from ${baseUrl} to ${outputDir}`);
