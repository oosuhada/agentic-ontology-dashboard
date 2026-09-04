import { expect, type Page, test } from "@playwright/test";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const captureRoot = "../docs/ui/screenshots/palantir-gap-v2";

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("이메일").fill("fde@ontology.local");
  await page.getByLabel("비밀번호").fill("FDE!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/projects\//);
}

async function capture(page: Page, name: string, readySelector: string) {
  await expect(page.locator(readySelector).first()).toBeVisible({ timeout: 45_000 });
  await page.screenshot({
    path: `${captureRoot}/${name}.png`,
    fullPage: false,
    animations: "disabled",
  });
}

test.use({
  viewport: { width: 1440, height: 1000 },
  colorScheme: "light",
});

test("capture Palantir gap review surfaces", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page);

  await capture(page, "dashboard", ".od-product-shell .react-grid-layout");

  await page.goto("/app/analysis/palantir-visual-audit-analysis");
  await expect(page.locator(".analysis-flow-canvas .react-flow")).toBeVisible();
  await page.locator(".analysis-flow-node").filter({ hasText: "Risk by production line" }).click();
  await expect(page.locator(".analysis-lineage-mini-canvas .analysis-lineage-node").first()).toBeVisible();
  await capture(page, "analysis", ".analysis-lineage-mini-canvas .react-flow");

  await page.getByRole("button", { name: "Agent", exact: true }).click();
  await capture(page, "agent", ".agent-workbench-page");

  await page.getByRole("button", { name: "Governance", exact: true }).click();
  await capture(page, "governance", ".governance-workbench-page");

  await page.goto("/app/projects/manufacturing-demo-project/datasets");
  await capture(page, "datasets", ".dataset-catalog-page");
});

test("render local and official references side by side", async ({ page }) => {
  test.setTimeout(120_000);
  const comparisonPath = resolve(process.cwd(), captureRoot, "comparison.html");
  await page.goto(pathToFileURL(comparisonPath).href, { waitUntil: "networkidle" });
  await expect(page.locator("article")).toHaveCount(5);
  await expect(page.locator("img.local")).toHaveCount(5);
  await expect(page.locator("img.official")).toHaveCount(5);
  await page.waitForFunction(() => (
    [...document.querySelectorAll<HTMLImageElement>("img")]
      .every((image) => image.complete && image.naturalWidth > 0)
  ));
  await page.screenshot({
    path: `${captureRoot}/comparison-sheet.png`,
    fullPage: true,
    animations: "disabled",
  });
});
