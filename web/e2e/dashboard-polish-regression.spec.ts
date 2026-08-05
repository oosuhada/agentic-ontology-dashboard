import { expect, type Page, test } from "@playwright/test";

const projectRoute = "/app/projects/manufacturing-demo-project";

async function login(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("ontology-dashboard-theme", "dark");
    localStorage.setItem("ontology-dashboard:locale", "ko-KR");
  });
  await page.goto("/login");
  await page.getByLabel("이메일").fill("engineer@ontology.local");
  await page.getByLabel("비밀번호").fill("Engineer!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  await expect(page).toHaveURL(/\/app(?:\/|$)/);
  await page.goto(projectRoute);
  await expect(page.locator(".react-grid-item.dashboard-board-frame").first()).toBeVisible({ timeout: 60_000 });
}

async function boardPositions(page: Page) {
  return page.locator(".react-grid-item.dashboard-board-frame").evaluateAll((elements) => elements.map((element) => {
    const style = getComputedStyle(element);
    return {
      id: element.getAttribute("data-board-id"),
      transform: style.transform,
    };
  }));
}

test.use({ viewport: { width: 1440, height: 1000 }, colorScheme: "dark" });

test("dashboard source disclosure, selected priority row, and grid selection remain visually stable", async ({ page }) => {
  test.setTimeout(90_000);
  await login(page);

  const disclosure = page.locator(".dashboard-source-disclosure");
  await expect(disclosure).toBeVisible();
  const disclosureMetrics = await disclosure.evaluate((element) => {
    const small = element.querySelector("small");
    if (!small) throw new Error("Missing source disclosure summary");
    const style = getComputedStyle(small);
    return {
      height: element.getBoundingClientRect().height,
      lineClamp: style.getPropertyValue("-webkit-line-clamp"),
      titleLength: small.getAttribute("title")?.length ?? 0,
    };
  });
  expect(disclosureMetrics.height).toBeLessThanOrEqual(44);
  expect(disclosureMetrics.lineClamp).toBe("2");
  expect(disclosureMetrics.titleLength).toBeGreaterThan(0);

  const beforeCrossFilter = await boardPositions(page);
  const priorityRow = page.locator(".priority-row").first();
  const tabs = page.locator(".dashboard-tabs button");
  for (let index = 0; index < await tabs.count(); index += 1) {
    if (await priorityRow.isVisible()) break;
    await tabs.nth(index).click();
    await page.waitForTimeout(250);
  }
  await expect(priorityRow).toBeVisible({ timeout: 30_000 });
  await priorityRow.click();
  await expect(priorityRow).toHaveClass(/selected/);
  const priorityTheme = await priorityRow.evaluate((element) => {
    const style = getComputedStyle(element);
    return { background: style.backgroundColor, color: style.color, border: style.borderColor };
  });
  expect(priorityTheme.background).not.toBe("rgb(255, 255, 255)");
  expect(priorityTheme.color).not.toBe("rgb(52, 64, 84)");
  expect(priorityTheme.border).not.toBe("rgb(234, 236, 240)");

  await expect(page.locator(".dashboard-board-frame.is-affected").first()).toBeVisible();
  const affectedAnimationNames = await page.locator(".dashboard-board-frame.is-affected").evaluateAll(
    (elements) => elements.map((element) => getComputedStyle(element).animationName),
  );
  expect(affectedAnimationNames.every((name) => name === "none")).toBe(true);
  const firstAffectedFrame = await boardPositions(page);
  await page.waitForTimeout(250);
  const secondAffectedFrame = await boardPositions(page);
  await page.waitForTimeout(500);
  const thirdAffectedFrame = await boardPositions(page);
  expect(firstAffectedFrame).toEqual(beforeCrossFilter);
  expect(secondAffectedFrame).toEqual(firstAffectedFrame);
  expect(thirdAffectedFrame).toEqual(firstAffectedFrame);

  await page.locator(".dashboard-board-title").first().click();
  await page.waitForTimeout(450);
  expect(await boardPositions(page)).toEqual(firstAffectedFrame);
});
