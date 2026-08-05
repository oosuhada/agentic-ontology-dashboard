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

test.use({ viewport: { width: 1664, height: 960 }, colorScheme: "dark" });

test("expanded navigation, compact workspace chrome, full-height canvas, and board size controls stay usable", async ({ page }) => {
  test.setTimeout(90_000);
  await login(page);

  await expect(page.locator(".fd-platform-shortcuts svg").first()).toBeVisible();
  await expect(page.locator(".fd-resource-navigation .od-primary-nav button svg")).toHaveCount(0);

  const compactContext = page.locator(".dashboard-context-compact");
  await expect(compactContext).toBeVisible();
  await expect(page.locator(".adaptive-profile-strip")).toHaveCount(0);
  await page.getByRole("button", { name: "업무 정보 펼치기", exact: true }).click();
  await expect(page.locator(".od-context-header")).toBeVisible();
  await expect(page.locator(".adaptive-profile-strip")).toBeVisible();
  await page.getByRole("button", { name: "업무 정보 접기", exact: true }).click();
  await expect(compactContext).toBeVisible();

  const viewportSurfaces = await page.evaluate(() => {
    const shell = document.querySelector<HTMLElement>(".od-product-shell");
    const bodyStyle = getComputedStyle(document.body);
    const rootStyle = getComputedStyle(document.documentElement);
    return {
      viewportHeight: window.innerHeight,
      shellHeight: shell?.getBoundingClientRect().height ?? 0,
      bodyBackground: bodyStyle.backgroundColor,
      rootBackground: rootStyle.backgroundColor,
    };
  });
  expect(viewportSurfaces.shellHeight).toBeGreaterThanOrEqual(viewportSurfaces.viewportHeight);
  expect(viewportSurfaces.bodyBackground).not.toBe("rgb(255, 255, 255)");
  expect(viewportSurfaces.rootBackground).not.toBe("rgb(255, 255, 255)");

  await page.getByRole("button", { name: "편집", exact: true }).click();
  const board = page.locator(".react-grid-item.dashboard-board-frame").first();
  const boardId = await board.getAttribute("data-board-id");
  expect(boardId).toBeTruthy();
  const initialWidth = Number(await board.getAttribute("data-grid-w"));
  const initialHeight = Number(await board.getAttribute("data-grid-h"));

  await board.locator(".dashboard-board-more > summary").click();
  await board.getByRole("menuitem", { name: "Board 크기 키우기", exact: true }).click();
  await expect.poll(async () => Number(await page.locator(`[data-board-id="${boardId}"]`).getAttribute("data-grid-w"))).toBeGreaterThanOrEqual(initialWidth);
  await expect.poll(async () => Number(await page.locator(`[data-board-id="${boardId}"]`).getAttribute("data-grid-h"))).toBeGreaterThanOrEqual(initialHeight);

  const activeBoard = page.locator(`[data-board-id="${boardId}"]`).first();
  await activeBoard.getByTitle("Board 접기").click();
  const collapsedBoard = page.locator(`.dashboard-collapsed-board-tray [data-board-id="${boardId}"]`);
  await expect(collapsedBoard).toBeVisible();
  await collapsedBoard.getByTitle("Board 펼치기").click();
  await expect(page.locator(`.react-grid-item[data-board-id="${boardId}"]`)).toBeVisible();

  const expandedBoard = page.locator(`.react-grid-item[data-board-id="${boardId}"]`);
  await expandedBoard.getByTitle("전체 화면").click();
  await expect(expandedBoard).toHaveClass(/is-fullscreen/);
  await expandedBoard.getByTitle("전체 화면 닫기").click();
  await expect(expandedBoard).not.toHaveClass(/is-fullscreen/);
});
