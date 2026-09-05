import { expect, type Page, test } from "@playwright/test";

const PROJECT = "manufacturing-demo-project";
const PATH = `/app/projects/${PROJECT}/operations?view=overview&dashboard=workflow&role=process_manager&workspace_id=manufacturing-demo&workspace_shell=reliability`;
const REPORT_PATH = `/app/projects/${PROJECT}/operations/report-draft?view=reports&dashboard=workflow&role=process_manager&workspace_id=manufacturing-demo&workspace_shell=reliability`;

const authCookies = new Map<
  string,
  Awaited<ReturnType<Page["context"]>["cookies"]>
>();

function hexContrast(foreground: string, background: string) {
  const luminance = (value: string) => {
    const hex = value.trim().replace(/^#/, "");
    const channels = [0, 2, 4].map(
      (offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255,
    );
    const linear = channels.map((channel) =>
      channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
    );
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
  };
  const a = luminance(foreground);
  const b = luminance(background);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

async function login(page: Page) {
  await loginAs(page, "manager@ontology.local", "Manager!2026", PATH);
}

async function loginAs(
  page: Page,
  email: string,
  password: string,
  returnTo = PATH,
) {
  const cached = authCookies.get(email);
  if (cached?.length) {
    await page.context().addCookies(cached);
    await page.goto(returnTo);
    await expect(page).toHaveURL(
      new RegExp(`/app/projects/${PROJECT}/operations`),
      { timeout: 10_000 },
    );
    return;
  }
  await page.goto(`/login?returnTo=${encodeURIComponent(returnTo)}`);
  await page.getByLabel(/이메일|Email/).fill(email);
  await page.getByLabel(/비밀번호|Password/).fill(password);
  await page
    .getByRole("button", { name: /로그인|Sign in/, exact: true })
    .click();
  await expect(page).toHaveURL(
    new RegExp(`/app/projects/${PROJECT}/operations`),
    { timeout: 10_000 },
  );
  authCookies.set(email, await page.context().cookies());
}

async function closeDetailDrawer(shell: ReturnType<Page["locator"]>) {
  const dialog = shell.getByRole("dialog", { name: "선택 설비 상세" });
  if (await dialog.isVisible()) {
    await dialog.getByRole("button", { name: "선택 설비 상세 닫기" }).click();
    await expect(dialog).toBeHidden();
  }
}

async function openFactoryStatus(shell: ReturnType<Page["locator"]>) {
  await closeDetailDrawer(shell);
  await shell
    .locator(".rw-preview-left nav button")
    .filter({ hasText: "설비 현황" })
    .click();
  await expect(shell).toHaveAttribute("data-active-surface", "factory-status");
}

test("uses a light Korean placeholder before the reliability workspace is ready", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("ontology-dashboard-theme", "dark");
    window.localStorage.setItem("ontology-dashboard:locale", "en-US");
    window.localStorage.removeItem("ontology-dashboard:reliability-theme");
    window.localStorage.removeItem("ontology-dashboard:reliability-locale");
  });

  await page.route(`**/api/projects/${PROJECT}`, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 800));
    await route.continue();
  });

  await login(page);

  const routePlaceholder = page.locator(".reliability-route-placeholder");
  await expect(routePlaceholder).toBeVisible();
  await expect(
    page.getByText("Validating Project scope", { exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".route-loading")).toHaveCount(0);

  const placeholder = page.locator(".rw-preview-loading-placeholder");
  await expect(placeholder).toBeVisible();
  await expect(
    placeholder.getByRole("heading", {
      name: "운영 워크스페이스를 준비하고 있습니다",
    }),
  ).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "ko-KR");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

  await expect(
    page.locator(".rw-preview-shell:not(.rw-preview-loading-placeholder)"),
  ).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("html")).toHaveAttribute("lang", "ko-KR");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");

  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell.locator(".operational-focus")).toHaveCount(0);
  const liveKpis = shell.locator(".operations-live-kpi-grid");
  const factoryMap = shell.locator(".operations-factory-map-panel").first();
  const decisionQueue = shell.getByText("DECISION QUEUE", { exact: true });
  await expect(liveKpis.or(decisionQueue).first()).toBeVisible();
  if (await liveKpis.isVisible()) {
    await expect(factoryMap).toBeVisible();
    const [kpiBox, mapBox] = await Promise.all([
      liveKpis.boundingBox(),
      factoryMap.boundingBox(),
    ]);
    expect(kpiBox?.y ?? Number.POSITIVE_INFINITY).toBeLessThan(
      mapBox?.y ?? Number.NEGATIVE_INFINITY,
    );
  } else {
    // Production telemetry can legitimately route managers to the adaptive
    // 판단 대기 surface when pending decisions are the top priority. The
    // placeholder/theme contract should not force the overview KPI grid in that
    // state, but it must still land in a concrete manager decision workspace.
    await expect(decisionQueue).toBeVisible();
    await expect(
      shell.getByRole("heading", { name: "지금 판단해야 할 항목" }),
    ).toBeVisible();
  }
  const lightSurfaces = await shell.evaluate((element) => {
    const sample = (selector: string) => {
      const target = element.querySelector<HTMLElement>(selector);
      if (!target) return null;
      const style = getComputedStyle(target);
      return {
        backgroundColor: style.backgroundColor,
        backgroundImage: style.backgroundImage,
      };
    };
    const shellStyle = getComputedStyle(element);
    return {
      themeBackground: shellStyle.getPropertyValue("--rw-bg").trim(),
      rail: sample(".rw-preview-left"),
      main: sample(".rw-preview-main"),
      bottom: sample(".rw-preview-bottom"),
    };
  });
  expect(lightSurfaces.themeBackground).toBe("#f3f6f9");
  expect(lightSurfaces.rail?.backgroundImage).toContain("rgb(251, 252, 253)");
  expect(lightSurfaces.main?.backgroundImage).toContain("rgb(247, 249, 251)");
  expect(lightSurfaces.bottom?.backgroundColor).toBe(
    "rgba(255, 255, 255, 0.98)",
  );
});

test("keeps the login lifecycle loader available as a persistent preview route", async ({
  page,
}) => {
  await page.goto("/loader");
  await expect(page.locator(".route-loading")).toBeVisible();
  await expect(page.locator(".od-lifecycle-loader")).toBeVisible();
  await expect(
    page.getByText("Checking session", { exact: true }),
  ).toBeVisible();
  await page.waitForTimeout(1200);
  await expect(page.locator(".od-lifecycle-loader")).toBeVisible();
  await expect(page).toHaveURL(/\/loader$/);
});

test("keeps login role choices compact and prioritizes the auth panel on mobile", async ({
  page,
}) => {
  await page.goto("/login");
  await expect(
    page.getByRole("button", { name: "엔지니어", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "운영 관리", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "경영진", exact: true }),
  ).toBeVisible();
  const roleOrder = await page
    .locator(".demo-account-card strong")
    .allTextContents();
  expect(roleOrder).toEqual(["엔지니어", "운영 관리", "경영진"]);
  await expect(
    page.getByText("판단 대기 · 생산 영향 · 정비 승인 · 보고 초안", {
      exact: true,
    }),
  ).toBeHidden();

  const managerInfo = page.getByLabel("운영 관리 상세 정보");
  await managerInfo.hover();
  await expect(
    page.getByText("판단 대기 · 생산 영향 · 정비 승인 · 보고 초안", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("manager@ontology.local", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "운영 관리", exact: true }).click();
  await expect(page.getByLabel(/이메일|Email/)).toHaveValue(
    "manager@ontology.local",
  );

  for (const viewport of [
    { width: 1120, height: 700 },
    { width: 1024, height: 700 },
    { width: 900, height: 700 },
    { width: 820, height: 700 },
    { width: 768, height: 700 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/login");
    await expect(page.locator(".auth-resource-context")).toBeHidden();
    await expect(page.locator(".auth-panel")).toBeVisible();
    const panelBox = await page.locator(".auth-panel").boundingBox();
    const emailBox = await page.getByLabel(/이메일|Email/).boundingBox();
    expect(
      panelBox?.y ?? Number.POSITIVE_INFINITY,
      `${viewport.width}x${viewport.height} auth panel top`,
    ).toBeLessThanOrEqual(80);
    expect(
      emailBox?.y ?? Number.POSITIVE_INFINITY,
      `${viewport.width}x${viewport.height} email visible`,
    ).toBeLessThan(viewport.height);
  }

  await page.setViewportSize({ width: 1280, height: 700 });
  await page.goto("/login");
  await expect(page.locator(".auth-resource-context")).toBeVisible();
  const stripGap = await page
    .locator(".auth-resource-context")
    .evaluate((element) => {
      const story = element.querySelector<HTMLElement>(".auth-product-story");
      const strip = element.querySelector<HTMLElement>(".auth-value-strip");
      return strip && story
        ? strip.getBoundingClientRect().top -
            story.getBoundingClientRect().bottom
        : 0;
    });
  expect(stripGap).toBeLessThanOrEqual(48);
});

test("keeps login controls aligned and display popover stable across presets", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 760 });
  await page.goto("/login");
  const inputHeights = await page
    .locator(".auth-card .auth-form input")
    .evaluateAll((nodes) =>
      nodes.map((node) => node.getBoundingClientRect().height),
    );
  const submitHeight = await page
    .locator(".auth-submit")
    .evaluate((node) => node.getBoundingClientRect().height);
  for (const height of inputHeights)
    expect(Math.abs(height - submitHeight)).toBeLessThanOrEqual(2);
  expect(submitHeight).toBeGreaterThanOrEqual(44);

  const display = page.locator(".od-display-menu");
  await display.locator(":scope > summary").click();
  const popover = page.locator(".od-display-popover");
  await expect(popover).toBeVisible();
  const desktopPreset = page.getByRole("button", { name: /데스크톱/ });
  const before = await desktopPreset.evaluate((node) => ({
    height: node.getBoundingClientRect().height,
    font: parseFloat(getComputedStyle(node).fontSize),
    rects: (() => {
      const range = document.createRange();
      range.selectNodeContents(node.querySelector("strong")!);
      const value = range.getClientRects().length;
      range.detach();
      return value;
    })(),
    overflow: node.scrollWidth - node.clientWidth,
  }));
  await page.getByRole("button", { name: /발표\/프로젝터/ }).click();
  if (!(await popover.isVisible())) {
    await display.locator(":scope > summary").click();
  }
  await expect(popover).toBeVisible();
  const after = await desktopPreset.evaluate((node) => ({
    height: node.getBoundingClientRect().height,
    font: parseFloat(getComputedStyle(node).fontSize),
    rects: (() => {
      const range = document.createRange();
      range.selectNodeContents(node.querySelector("strong")!);
      const value = range.getClientRects().length;
      range.detach();
      return value;
    })(),
    overflow: node.scrollWidth - node.clientWidth,
  }));
  expect(Math.abs(after.height - before.height)).toBeLessThanOrEqual(1);
  expect(Math.abs(after.font - before.font)).toBeLessThanOrEqual(1);
  expect(after.rects).toBe(1);
  expect(after.overflow).toBeLessThanOrEqual(1);
});

test("keeps navigation expanded on laptop widths and wraps Korean copy by word boundary", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 800 });
  await login(page);

  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  await closeDetailDrawer(shell);
  const rail = shell.locator(".rw-preview-left");
  const firstNavCopy = rail.locator("nav button").first().locator("div");
  await expect(firstNavCopy).toBeVisible();

  const desktopGeometry = await rail.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      width: element.getBoundingClientRect().width,
      display: style.display,
    };
  });
  expect(desktopGeometry.width).toBeGreaterThanOrEqual(220);
  expect(desktopGeometry.display).not.toBe("none");

  const detailWrap = await shell
    .locator(".rw-preview-page-heading p")
    .evaluate((element) => {
      const style = getComputedStyle(element);
      return { wordBreak: style.wordBreak, overflowWrap: style.overflowWrap };
    });
  expect(detailWrap.wordBreak).toBe("keep-all");
  expect(detailWrap.overflowWrap).toBe("break-word");

  await page.setViewportSize({ width: 900, height: 800 });
  await expect(firstNavCopy).toBeVisible();
  expect((await rail.boundingBox())?.width ?? 0).toBeGreaterThanOrEqual(220);

  await shell.getByRole("button", { name: "환경설정" }).click();
  await shell
    .getByRole("button", { name: "발표/프로젝터", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute(
    "data-density",
    "comfortable",
  );
  await shell
    .locator(".rw-preview-page-heading")
    .click({ position: { x: 12, y: 12 } });
  await shell.getByRole("button", { name: "Collapse navigation" }).click();
  await expect(firstNavCopy).toBeHidden();
  expect(
    (await rail.boundingBox())?.width ?? Number.POSITIVE_INFINITY,
  ).toBeLessThanOrEqual(60);
  await shell.getByRole("button", { name: "Open navigation" }).click();
  await shell.getByRole("button", { name: "환경설정" }).click();
  await shell.getByRole("button", { name: "데스크톱", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute(
    "data-density",
    "standard",
  );
});

test("keeps login and reliability workspace inside a phone viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/login?returnTo=${encodeURIComponent(PATH)}`);

  const loginGeometry = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    documentWidth: document.documentElement.scrollWidth,
  }));
  expect(loginGeometry.documentWidth).toBeLessThanOrEqual(
    loginGeometry.viewport + 1,
  );

  await page.getByLabel(/이메일|Email/).fill("manager@ontology.local");
  await page.getByLabel(/비밀번호|Password/).fill("Manager!2026");
  await page
    .getByRole("button", { name: /로그인|Sign in/, exact: true })
    .click();
  await expect(page).toHaveURL(
    new RegExp(`/app/projects/${PROJECT}/operations`),
    { timeout: 10_000 },
  );

  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  const geometry = await shell.evaluate((element) => {
    const main = element.querySelector<HTMLElement>(".rw-preview-main");
    return {
      viewport: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
      mainClientWidth: main?.clientWidth ?? 0,
      mainScrollWidth: main?.scrollWidth ?? 0,
    };
  });
  expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewport + 1);
  expect(geometry.mainScrollWidth).toBeLessThanOrEqual(
    geometry.mainClientWidth + 1,
  );

  const openNav = shell.getByRole("button", { name: "Open navigation" });
  await openNav.click();
  const rail = shell.locator(".rw-preview-left");
  await expect(rail.locator("nav button").first().locator("div")).toBeVisible();
  const railBox = await rail.boundingBox();
  expect(railBox?.width ?? 0).toBeGreaterThan(220);
  expect(railBox?.width ?? Number.POSITIVE_INFINITY).toBeLessThan(390);
});

test("keeps grounded report surfaces light and derives assistant copy from live context", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "ontology-dashboard:reliability-theme",
      "light",
    );
    window.localStorage.setItem(
      "ontology-dashboard:reliability-locale",
      "ko-KR",
    );
  });
  await login(page);
  await page.goto(REPORT_PATH);

  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  const reportSurface = shell.locator('[data-surface="report-draft"]');
  await expect(reportSurface).toBeVisible({ timeout: 15_000 });
  await expect(
    reportSurface.getByText("역할별 보고 요약", { exact: true }),
  ).toBeVisible();
  const reportBlockBackground = await reportSurface
    .locator(".rw-composed-block")
    .filter({ hasText: "역할별 보고 요약" })
    .first()
    .evaluate((element) => getComputedStyle(element).backgroundColor);
  expect(reportBlockBackground).toBe("rgb(255, 255, 255)");

  await shell.getByRole("button", { name: /Assistant/ }).click();
  const assistant = page.getByRole("dialog", { name: "Reliability Assistant" });
  await expect(assistant).toBeVisible();
  await expect(assistant).not.toContainText("local_sop_metadata_retriever");
  await expect(
    assistant.getByRole("button", {
      name: "지금 승인해야 하는 조치는 무엇인가요?",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    assistant.getByRole("button", {
      name: "이 조치로 어떤 생산·비용 가치를 보호할 수 있나요?",
      exact: true,
    }),
  ).toBeVisible();
  await assistant
    .getByRole("button", {
      name: "이 조치로 어떤 생산·비용 가치를 보호할 수 있나요?",
      exact: true,
    })
    .click();
  const valueAnswer = assistant.locator(
    ".rw-context-assistant__message.is-assistant:not(.is-loading)",
  ).last();
  await expect(valueAnswer).toBeVisible({ timeout: 15_000 });
  await expect(valueAnswer).toContainText(/보호|생산 연속성/);
  await expect(valueAnswer).toContainText(/실제.*절감|절감.*확정|보호 대상/);
  await expect(valueAnswer).not.toContainText("비용을 절감했습니다");
  await expect(
    assistant.getByRole("button", {
      name: "경영진 보고 초안을 만들어줘",
      exact: true,
    }),
  ).toBeVisible();
});

test("uses wall-clock assets and resolves observation-history states", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "ontology-dashboard:reliability-theme",
      "light",
    );
    window.localStorage.setItem(
      "ontology-dashboard:reliability-locale",
      "ko-KR",
    );
  });
  await login(page);

  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  await openFactoryStatus(shell);
  const factoryMap = shell.locator(".operations-factory-map-panel").first();
  await expect(factoryMap).toBeVisible();
  await expect(
    factoryMap.locator(".operations-factory-asset-node"),
  ).toHaveCount(100, { timeout: 15_000 });
  await expect(factoryMap).not.toContainText("설비 정보 준비 중");
  await expect(shell).not.toContainText("2026. 09. 12");

  const connectedAsset = factoryMap
    .locator(".operations-factory-asset-node:not(.slot)")
    .first();
  await expect(connectedAsset).toBeVisible();
  await connectedAsset.click();

  const drawer = shell.getByRole("dialog", { name: "선택 설비 상세" });
  await expect(drawer).toBeVisible();
  const featureMonitor = drawer.locator(".operations-live-feature-monitor");
  await expect(featureMonitor).not.toContainText("관측 이력 로딩 중", {
    timeout: 15_000,
  });
  const featureSeriesCount = await featureMonitor
    .locator(".asset-series-line")
    .count();
  if (featureSeriesCount === 0)
    await expect(featureMonitor).toContainText("관측 이력 없음");
  else expect(featureSeriesCount).toBeGreaterThan(0);
  await expect(drawer).not.toContainText("pressure_raw_6h_max_abs");
  await expect(drawer).not.toContainText("vibration_raw_6h_max_abs");
  await expect(drawer).not.toContainText("relative_vibration_z_6h_max_abs");
  await expect(drawer).not.toContainText("SSE 수신 대기");
  await expect(drawer).not.toContainText("재생성 권한 없음");
});

test("requires report type review before opening the browser print flow", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "ontology-dashboard:reliability-theme",
      "light",
    );
    window.localStorage.setItem(
      "ontology-dashboard:reliability-locale",
      "ko-KR",
    );
  });
  await login(page);

  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  await openFactoryStatus(shell);
  const chartAsset = shell
    .locator(
      ".operations-factory-asset-node.critical, .operations-factory-asset-node.warning, .operations-factory-asset-node.attention, .operations-factory-asset-node.hold",
    )
    .first();
  await expect(chartAsset).toBeVisible({ timeout: 15_000 });
  await chartAsset.click();

  const detailDrawer = page.getByRole("dialog", { name: "선택 설비 상세" });
  await expect(detailDrawer).toBeVisible({ timeout: 15_000 });
  await detailDrawer.getByRole("button", { name: "보고서 출력" }).click();

  const outputDialog = page.getByRole("dialog", {
    name: "보고서 출력 유형 선택",
  });
  await expect(outputDialog).toBeVisible();
  for (const label of [
    "상태 요약",
    "점검 요청",
    "요약 보고서",
    "Executive Brief",
  ]) {
    await expect(
      outputDialog.getByRole("button", { name: new RegExp(label) }),
    ).toBeVisible();
  }
  await expect(outputDialog.getByLabel("선택한 출력 내용 확인")).toBeVisible();
  await page.evaluate(() => {
    (window as typeof window & { __printCalled?: number }).__printCalled = 0;
    window.print = () => {
      (window as typeof window & { __printCalled?: number }).__printCalled =
        ((window as typeof window & { __printCalled?: number }).__printCalled ??
          0) + 1;
    };
  });
  await outputDialog.getByRole("button", { name: "확인 후 출력" }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as typeof window & { __printCalled?: number })
            .__printCalled ?? 0,
      ),
    )
    .toBe(1);
});

test("connects search, settings dismissal, locale, theme, presets, and assistant prompts", async ({
  page,
}) => {
  await page.goto(`/login?returnTo=${encodeURIComponent(PATH)}`);
  const display = page.locator(".od-display-menu");
  await display.locator(":scope > summary").click();
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en-US");
  await expect(
    page.getByRole("heading", {
      name: "Find abnormal equipment by location and alert first.",
    }),
  ).toBeVisible();
  await expect(page.getByLabel("Email")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await page.mouse.click(12, 180);
  await expect(display).not.toHaveAttribute("open", "");

  await display.locator(":scope > summary").click();
  await page.getByRole("button", { name: "Dark", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "한국어", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ko-KR");
  await expect(
    page.getByRole("heading", {
      name: "이상 설비를 위치와 알림으로 먼저 찾습니다.",
    }),
  ).toBeVisible();
  await page.mouse.click(12, 180);

  await page.getByLabel("이메일").fill("manager@ontology.local");
  await page.getByLabel("비밀번호").fill("Manager!2026");
  await page.getByRole("button", { name: "로그인", exact: true }).click();
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });

  await shell
    .getByRole("button", { name: "Reliability Operations 검색" })
    .click();
  const palette = page.getByRole("dialog", {
    name: "Reliability Operations 검색",
  });
  await expect(palette).toBeVisible();
  await palette.getByLabel("메뉴, 설비 또는 Event 검색").fill("Decision Case");
  await palette
    .getByRole("button", { name: /Decision Case/ })
    .first()
    .click();
  await expect(page).toHaveURL(/\/operations\/decision-case/);
  await expect(
    shell.getByRole("heading", { name: "하나의 사건을 끝까지 추적" }),
  ).toBeVisible();

  await shell.getByRole("button", { name: "환경설정" }).click();
  await expect(shell.locator(".rw-preview-settings-panel")).toBeVisible();
  await shell
    .locator(".rw-preview-page-heading")
    .click({ position: { x: 12, y: 12 } });
  await expect(shell.locator(".rw-preview-settings-panel")).toBeHidden();

  await shell.getByRole("button", { name: "환경설정" }).click();
  await shell
    .getByRole("button", { name: "발표/프로젝터", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute(
    "data-density",
    "comfortable",
  );
  const presentationCopySize = await shell
    .locator(".rw-composed-list small")
    .first()
    .evaluate((element) => parseFloat(getComputedStyle(element).fontSize));
  expect(presentationCopySize).toBeGreaterThanOrEqual(12);
  await shell.getByRole("button", { name: "데스크톱", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute(
    "data-density",
    "standard",
  );
  await shell
    .locator(".rw-preview-page-heading")
    .click({ position: { x: 12, y: 12 } });

  await shell.getByRole("button", { name: /Assistant/ }).click();
  const assistant = page.getByRole("dialog", { name: "Reliability Assistant" });
  await expect(assistant).toBeVisible();
  await assistant
    .getByRole("button", { name: "이 조치로 어떤 생산·비용 가치를 보호할 수 있나요?", exact: true })
    .click();
  await expect(
    assistant.locator(".rw-context-assistant__message.is-user"),
  ).toHaveCount(1);
  await expect(
    assistant.locator(
      ".rw-context-assistant__message.is-assistant:not(.is-loading)",
    ),
  ).toHaveCount(1, { timeout: 12_000 });
  await expect(
    assistant.locator(".rw-context-assistant__message.is-loading"),
  ).toHaveCount(0, { timeout: 12_000 });
});

test("keeps factory status focused and avoids repeating the full map on operations status", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  await openFactoryStatus(shell);
  await expect(shell.locator(".operations-live-kpi-grid")).toBeVisible();
  await expect(shell.locator(".operations-factory-map-panel")).toBeVisible();
  await expect(shell.locator(".operations-monitoring-summary")).toBeHidden();
  await expect(shell.locator(".operations-work-queue-board")).toBeHidden();
  const zoneColumns = await shell
    .locator(".operations-factory-line-map")
    .evaluate(
      (element) =>
        getComputedStyle(element).gridTemplateColumns.split(" ").length,
    );
  expect(zoneColumns).toBe(2);

  const mainGeometry = await shell
    .locator(".rw-preview-main")
    .evaluate((element) => ({
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
    }));
  expect(
    mainGeometry.scrollHeight / Math.max(1, mainGeometry.clientHeight),
  ).toBeLessThan(2.2);

  await shell
    .locator(".rw-preview-left nav button")
    .filter({ hasText: "운영 현황" })
    .click();
  await expect(page).toHaveURL(/\/operations\/operations-status/);
  const composed = shell.locator('[data-surface="operations-status"]');
  await expect(composed).toBeVisible();
  await expect(composed).not.toHaveAttribute("data-composition", /factory-map/);
  await expect(composed.locator(".rw-factory-map")).toHaveCount(0);
});

test("uses grouped manager IA, exception-first factory map, persistent case anchor, and adaptive lifecycle", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });

  const rail = shell.locator(".rw-preview-left");
  for (const group of ["OBSERVE · 감지", "DECIDE · 판단", "FOLLOW-UP · 후속"]) {
    await expect(rail.getByText(group, { exact: true })).toBeVisible();
  }
  await expect(rail.locator("nav")).not.toContainText("01");
  await expect(
    rail
      .locator(".rw-preview-nav-group")
      .filter({ hasText: "FOLLOW-UP · 후속" }),
  ).toContainText("보고");
  await expect(
    rail
      .locator(".rw-preview-nav-group")
      .filter({ hasText: "FOLLOW-UP · 후속" }),
  ).toContainText("Archive");

  await openFactoryStatus(shell);
  const lifecycle = shell.locator(".lifecycle-instrument");
  const initialAnchor = shell.locator(".rw-preview-selection-anchor");
  if ((await initialAnchor.count()) === 0) {
    await expect(lifecycle).toHaveClass(/is-idle/);
  } else {
    await expect(initialAnchor).toBeVisible();
    await expect(initialAnchor).toContainText("선택 Case");
    await expect(lifecycle).toHaveClass(/is-compact|is-full/);
  }

  const factoryMap = shell.locator(".operations-factory-map-panel");
  await expect(
    factoryMap.getByRole("button", { name: "이상만 강조", exact: true }),
  ).toHaveClass(/is-active/);
  expect(
    await factoryMap
      .locator(".operations-factory-asset-node.normal.is-deemphasized")
      .count(),
  ).toBeGreaterThan(0);
  await factoryMap
    .getByRole("button", { name: "전체 설비", exact: true })
    .click();
  await expect(factoryMap.locator(".operations-factory-map")).toHaveClass(
    /focus-all/,
  );
  await factoryMap
    .getByRole("button", { name: "이상만 강조", exact: true })
    .click();

  const abnormal = factoryMap
    .locator(".operations-factory-asset-node:not(.normal):not(.slot)")
    .first();
  await abnormal.click();
  await expect(
    shell.getByRole("dialog", { name: "선택 설비 상세" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  const anchor = shell.locator(".rw-preview-selection-anchor");
  await expect(anchor).toBeVisible();
  await expect(anchor).toContainText("선택 Case");
  await expect(anchor).toContainText("위험");
  await expect(lifecycle).toHaveClass(/is-compact/);

  await rail.locator("nav button").filter({ hasText: "Decision Case" }).click();
  await expect(shell).toHaveAttribute("data-active-surface", "decision-case");
  await expect(anchor).toBeVisible();
  await expect(lifecycle).toHaveClass(/is-full/);
  await expect(
    shell.getByRole("button", { name: "보고 초안 이어보기", exact: true }),
  ).toBeVisible();

  await rail.locator("nav button").filter({ hasText: "운영 현황" }).click();
  const operationsStatus = shell.locator('[data-surface="operations-status"]');
  await expect(operationsStatus).toHaveAttribute(
    "data-composition",
    /^risk-metrics,operational-kpis,line-risk/,
  );
  const promotionReason = shell.locator(".rw-composition-reason");
  if (await promotionReason.count()) {
    await expect(promotionReason).toContainText(/우선순위 상승/);
    await expect(promotionReason).toContainText(
      /현재 운영 상태에 따라 중요한 블록/,
    );
  }
});

test("keeps an explicitly selected Decision Case stable across reload", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await login(page);
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  await openFactoryStatus(shell);
  const factoryMap = shell.locator(".operations-factory-map-panel");
  const abnormal = factoryMap
    .locator(".operations-factory-asset-node:not(.normal):not(.slot)")
    .first();
  await abnormal.click();
  await expect(
    page.getByRole("dialog", { name: "선택 설비 상세" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  const anchor = shell.locator(".rw-preview-selection-anchor");
  await expect(anchor).toBeVisible();
  const before = new URL(page.url()).searchParams.get("event_id");
  expect(before).toBeTruthy();
  await expect(anchor).toContainText(before!);

  await shell
    .locator(".rw-preview-left nav button")
    .filter({ hasText: "Decision Case" })
    .click();
  const caseSurface = shell.locator('[data-surface="decision-case"]');
  await expect(caseSurface).toHaveAttribute("data-selected-event-id", before!);
  await expect(
    caseSurface
      .locator(".rw-composed-list.static[data-event-id]")
      .filter({ has: caseSurface.getByText("모델", { exact: false }) })
      .first(),
  )
    .toHaveAttribute("data-event-id", before!)
    .catch(() => undefined);
  const actionPanel = caseSurface.locator(
    ".operations-maintenance-workflow-panel[data-event-id]",
  );
  if (await actionPanel.count())
    await expect(actionPanel).toHaveAttribute("data-event-id", before!);

  await page.reload();
  await expect(shell).toBeVisible({ timeout: 15_000 });
  await expect(page).toHaveURL(
    new RegExp(`event_id=${encodeURIComponent(before!)}`),
  );
  await expect(shell.locator(".rw-preview-selection-anchor")).toContainText(
    before!,
  );
  await page.waitForTimeout(22_000);
  await expect(page).toHaveURL(
    new RegExp(`event_id=${encodeURIComponent(before!)}`),
  );
  await expect(shell.locator(".rw-preview-selection-anchor")).toContainText(
    before!,
  );
  const blocked = await shell
    .getByText("선택 Case를 다시 확인해 주세요", { exact: true })
    .count();
  if (before!.startsWith("RESULT#")) {
    expect(
      blocked,
      "immutable live RESULT# Case must remain restorable across refresh ticks",
    ).toBe(0);
  }
  if (blocked) {
    await expect(shell).toContainText(/최신 Event로 자동 대체하지/);
    await expect(shell.locator('[data-surface="decision-case"]')).toHaveCount(
      0,
    );
  } else {
    await expect(
      shell.locator('[data-surface="decision-case"]'),
    ).toHaveAttribute("data-selected-event-id", before!);
    const refreshedEvidence = shell
      .locator(
        '[data-surface="decision-case"] .rw-composed-list.static[data-event-id]',
      )
      .first();
    if (await refreshedEvidence.count())
      await expect(refreshedEvidence).toHaveAttribute("data-event-id", before!);
    const refreshedAction = shell.locator(
      '[data-surface="decision-case"] .operations-maintenance-workflow-panel[data-event-id]',
    );
    if (await refreshedAction.count())
      await expect(refreshedAction).toHaveAttribute("data-event-id", before!);

    await shell
      .locator(".rw-preview-left nav button")
      .filter({ hasText: "보고" })
      .click();
    const reportSurface = shell.locator('[data-surface="report-draft"]');
    await expect(reportSurface).toHaveAttribute(
      "data-selected-event-id",
      before!,
    );
    await expect(
      reportSurface.locator(".rw-report-artifact-meta"),
    ).toContainText(`Case ${before!}`, { timeout: 15_000 });
  }
});

test("blocks an explicit Decision Case that cannot be restored instead of falling forward", async ({
  page,
}) => {
  await login(page);
  const missing = "RESULT#MISSING-FROZEN-SNAPSHOT";
  const url = new URL(
    `/app/projects/${PROJECT}/operations/decision-case`,
    page.url(),
  );
  url.searchParams.set("view", "operations");
  url.searchParams.set("dashboard", "workflow");
  url.searchParams.set("role", "process_manager");
  url.searchParams.set("workspace_id", "manufacturing-demo");
  url.searchParams.set("asset_id", "CNC-S03-L02-01");
  url.searchParams.set("event_id", missing);
  url.searchParams.set("workspace_shell", "reliability");
  await page.goto(url.toString());
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  await expect(page).toHaveURL(
    new RegExp(`event_id=${encodeURIComponent(missing)}`),
  );
  await expect(
    shell.getByText("선택 Case를 다시 확인해 주세요", { exact: true }),
  ).toBeVisible();
  await expect(shell).toContainText(/최신 Event로 자동 대체하지/);
  await expect(
    shell.locator('[data-selected-event-id]:not([data-selected-event-id=""])'),
  ).toHaveCount(0);
});

test("separates executive primary decisions from evidence and detail", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 800 });
  await loginAs(page, "executive@ontology.local", "Executive!2026");
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  const groups = shell.locator(".rw-preview-nav-group");
  const primary = groups.filter({ hasText: "PRIMARY · 경영 판단" });
  const evidence = groups.filter({ hasText: "EVIDENCE · 근거/상세" });
  await expect(primary).toBeVisible();
  await expect(evidence).toBeVisible();
  await expect(primary.locator("button")).toHaveCount(5);
  await expect(evidence.locator("button")).toHaveCount(3);
  for (const label of [
    "Executive Brief",
    "운영 리스크",
    "운영 KPI",
    "의사결정 병목",
    "보고 산출물",
  ]) {
    await expect(primary).toContainText(label);
  }
  for (const label of ["정비 효과", "개선 과제", "설비 상태 근거"]) {
    await expect(evidence).toContainText(label);
  }

  const executiveBrief = shell.locator('[data-surface="executive-brief"]');
  await expect(executiveBrief).toHaveAttribute(
    "data-composition",
    /^risk-metrics,production-exposure,decision-bottleneck,report-summary/,
  );
  for (const heading of [
    "전체 운영 리스크",
    "생산 · 재무 가치",
    "의사결정 병목",
    "보고 준비 상태",
  ]) {
    const box = await executiveBrief
      .getByText(heading, { exact: true })
      .boundingBox();
    expect(
      box?.y ?? Number.POSITIVE_INFINITY,
      `${heading} should be in the executive first viewport`,
    ).toBeLessThan(790);
  }
  await expect(executiveBrief).not.toContainText(
    "immediate_inspection_and_stop_review",
  );
  await expect(executiveBrief).not.toContainText(/설비 중요도 high/);

  await primary.locator("button").filter({ hasText: "의사결정 병목" }).click();
  const bottleneck = shell.locator('[data-surface="decision-bottleneck"]');
  await expect(bottleneck).toBeVisible();
  await expect(bottleneck).toHaveAttribute(
    "data-composition",
    /^decision-bottleneck,workflow-lifecycle,production-exposure/,
  );
  await expect(
    bottleneck.getByText("대기시간 기준", { exact: true }),
  ).toBeVisible();
  await expect(bottleneck).toContainText(
    "승인된 Decision SLA 계약이 없어 SLA 초과 여부를 임의 계산하지 않습니다",
  );
});

test("organizes engineering navigation by work intent instead of duplicated data types", async ({
  page,
}) => {
  await loginAs(page, "engineer@ontology.local", "Engineer!2026");
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  const rail = shell.locator(".rw-preview-left");
  for (const label of [
    "설비 현황",
    "모니터링",
    "원인 분석",
    "점검",
    "정비 효과",
    "정비 이력",
    "현장 기록",
  ]) {
    await expect(
      rail.locator("nav button").filter({ hasText: label }),
    ).toHaveCount(1);
  }
  await expect(
    rail.locator("nav button").filter({ hasText: "센서 피쳐" }),
  ).toHaveCount(0);
  await expect(
    rail.locator("nav button").filter({ hasText: "점검 · 정비 이력" }),
  ).toHaveCount(0);
  for (const group of ["OBSERVE · 감지", "DIAGNOSE · 진단", "LEARN · 이력"]) {
    await expect(rail.getByText(group, { exact: true })).toBeVisible();
  }

  await closeDetailDrawer(shell);
  await rail.locator("nav button").filter({ hasText: "원인 분석" }).click();
  const diagnosis = shell.locator('[data-surface="assets"]');
  await expect(diagnosis).toHaveAttribute(
    "data-layout-engine",
    "semantic-content-masonry",
  );
  await expect(diagnosis).toHaveAttribute(
    "data-composition",
    /^evidence-factors,inspection-targets,sensor-signals,/,
  );
  await expect
    .poll(() => diagnosis.locator(".rw-composed-block[data-adaptive-row-span]").count())
    .toBeGreaterThanOrEqual(3);
  const diagnosisLayout = await diagnosis.evaluate((element) => {
    const style = window.getComputedStyle(element);
    return { flow: style.gridAutoFlow, rows: style.gridAutoRows };
  });
  expect(diagnosisLayout.flow).toContain("dense");
  expect(diagnosisLayout.rows).toBe("8px");
  const diagnosisEmpty = diagnosis.locator(".rw-composed-block.is-empty-block").first();
  if (await diagnosisEmpty.count()) {
    await expect(diagnosisEmpty).toHaveAttribute("data-adaptive-column-span", "6");
    const cards = diagnosis.locator(".rw-composed-block");
    if (await cards.count() >= 3) {
      const firstBox = await cards.nth(0).boundingBox();
      const emptyBox = await diagnosisEmpty.boundingBox();
      const thirdBox = await cards.nth(2).boundingBox();
      if (firstBox && emptyBox && thirdBox && emptyBox.height + 20 < firstBox.height) {
        expect(thirdBox.y).toBeLessThan(firstBox.y + firstBox.height);
      }
    }
  }
  const main = shell.locator(".rw-preview-main");
  const sectionIndex = main.locator(".rw-section-index");
  if (await sectionIndex.count()) {
    const geometry = await main.evaluate((element) => ({
      paddingLeft: Number.parseFloat(window.getComputedStyle(element).paddingLeft),
    }));
    expect(geometry.paddingLeft).toBeGreaterThanOrEqual(40);
    const railBox = await sectionIndex.boundingBox();
    const contentBox = await diagnosis.boundingBox();
    expect(railBox).not.toBeNull();
    expect(contentBox).not.toBeNull();
    expect((railBox?.x ?? 0) + (railBox?.width ?? 0)).toBeLessThanOrEqual((contentBox?.x ?? 0) + 1);
  }
  expect(
    (await diagnosis.getAttribute("data-composition"))?.indexOf(
      "feature-trend",
    ),
  ).toBeGreaterThan(0);
  await expect(diagnosis).not.toContainText(
    /rotational_speed_rpm_(?:current|6h_mean|6h_abs_mean)/,
  );
  await expect(diagnosis).not.toContainText("inspection_candidate");
  const factorLabels = diagnosis.locator(".rw-composed-list.static strong");
  const factorText = (await factorLabels.allTextContents()).join(" | ");
  if (factorText.includes("주축 회전수")) {
    expect(factorText).toMatch(
      /주축 회전수 · (현재값|6시간 평균|6시간 절대평균|6시간 최대 절대값)/,
    );
  }
  const chartSvgs = diagnosis.locator(".rw-feature-trends svg[tabindex='0']");
  if (await chartSvgs.count()) {
    await expect(
      diagnosis.locator(".rw-feature-hit[tabindex='0']"),
    ).toHaveCount(0);
    const chart = chartSvgs.first();
    await chart.focus();
    const keyboardValue = diagnosis.locator(".rw-chart-keyboard-value").first();
    const beforeKeyboard = await keyboardValue.textContent();
    await chart.press("ArrowRight");
    await expect
      .poll(() => keyboardValue.textContent())
      .not.toBe(beforeKeyboard);
  }

  await rail.locator("nav button").filter({ hasText: "점검" }).click();
  const inspection = shell.locator('[data-surface="inspection"]');
  await expect(inspection).toBeVisible();
  await expect(inspection).toHaveAttribute(
    "data-composition",
    /^workflow-actions,inspection-targets,/,
  );
  await expect(inspection).not.toHaveAttribute("data-composition", /workflow-lifecycle/);
  await expect(shell.locator(".rw-preview-operational-focus")).toHaveCount(0);
  const inspectionBlocks = inspection.locator(".rw-composed-block");
  await expect(inspectionBlocks.first()).toHaveClass(/is-action-hero/);
  const selectedCaseBar = shell.locator(".rw-preview-selection-anchor");
  if (await selectedCaseBar.count()) {
    const selectedCaseHeight = await selectedCaseBar.evaluate((element) => element.getBoundingClientRect().height);
    expect(selectedCaseHeight).toBeLessThan(64);
  }
  const lifecycleFooter = shell.locator(".rw-preview-bottom .lifecycle-instrument.is-compact");
  await expect(lifecycleFooter).toBeVisible();
  const lifecycleHeight = await lifecycleFooter.evaluate((element) => element.getBoundingClientRect().height);
  expect(lifecycleHeight).toBeLessThan(60);
  await expect(
    inspection
      .getByText(/점검 요청 대기|점검 시작|점검 결과 기록·완료/)
      .first(),
  ).toBeVisible();
  const pendingState = inspection.locator(".operations-workflow-state");
  if (await pendingState.count()) {
    await expect(pendingState).toBeVisible();
    await expect(pendingState).toContainText("현재 상태");
    await expect(inspection.locator(".operations-workflow-summary")).toContainText("다음 Owner");
    await expect(
      inspection.getByRole("button", { name: "점검 요청 대기", exact: true }),
    ).toHaveCount(0);
    await expect(pendingState).toContainText(/다음 Owner|현재 상태/);
  }
  const compactEmpty = inspection.locator(".rw-composed-block.is-compact-empty");
  if (await compactEmpty.count()) {
    await expect(compactEmpty).toContainText("현재 근거에서 특정된 점검 대상이 없습니다.");
    await expect(compactEmpty).toHaveAttribute("data-adaptive-column-span", "6");
    const widthRatio = await compactEmpty.evaluate((element) => {
      const grid = element.parentElement;
      if (!grid) return 0;
      return element.getBoundingClientRect().width / grid.getBoundingClientRect().width;
    });
    expect(widthRatio).toBeGreaterThan(0.42);
    expect(widthRatio).toBeLessThan(0.62);
  }
});

test("changes executive report artifacts when the report type changes", async ({
  page,
}) => {
  await loginAs(page, "executive@ontology.local", "Executive!2026");
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  await expect(shell).toHaveAttribute("data-active-view", "reports");
  await expect(page).toHaveURL(/event_id=/, { timeout: 15_000 });
  const report = shell.locator('[data-surface="executive-brief"]');
  await expect(report).toBeVisible({ timeout: 15_000 });
  const select = report.getByLabel("보고 유형");
  await expect(select).toBeVisible();
  const meta = report.locator(".rw-report-artifact-meta");
  await expect(meta).toContainText("executive-brief", { timeout: 15_000 });
  const initialArtifact = await meta
    .locator("small")
    .filter({ hasText: "artifact" })
    .textContent();

  await select.selectOption("operations-decision");
  await expect(meta).toContainText("operations-decision", { timeout: 15_000 });
  const decisionArtifact = await meta
    .locator("small")
    .filter({ hasText: "artifact" })
    .textContent();
  expect(decisionArtifact).not.toBe(initialArtifact);

  await select.selectOption("inspection-summary");
  await expect(meta).toContainText("inspection-summary", { timeout: 15_000 });
  const inspectionArtifact = await meta
    .locator("small")
    .filter({ hasText: "artifact" })
    .textContent();
  expect(inspectionArtifact).not.toBe(decisionArtifact);
});

test("keeps standard workspace copy readable and exposes active-navigation semantics", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "ontology-dashboard:reliability-theme",
      "light",
    );
    window.localStorage.setItem(
      "ontology-dashboard:reliability-density",
      "standard",
    );
  });
  await login(page);
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  const activeNav = shell.locator(".rw-preview-left nav button.is-active");
  await expect(activeNav).toHaveAttribute("aria-current", "page");

  await closeDetailDrawer(shell);
  await shell
    .locator(".operations-factory-asset-node:not(.normal):not(.slot)")
    .first()
    .click();
  await expect(
    page.getByRole("dialog", { name: "선택 설비 상세" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await shell
    .locator(".rw-preview-left nav button")
    .filter({ hasText: "Decision Case" })
    .click();
  const composed = shell.locator('[data-surface="decision-case"]');
  await expect(composed).toBeVisible();
  const typography = await composed.evaluate((element) => {
    const visibleText = [
      ...element.querySelectorAll<HTMLElement>(
        "p,li,button,small,span,strong,time,summary,code",
      ),
    ].filter((node) => {
      const style = getComputedStyle(node);
      const box = node.getBoundingClientRect();
      return (
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        box.width > 0 &&
        box.height > 0 &&
        Boolean(node.textContent?.trim())
      );
    });
    const fontSizes = visibleText
      .map((node) => parseFloat(getComputedStyle(node).fontSize))
      .filter(Number.isFinite);
    const buttons = [...element.querySelectorAll<HTMLElement>("button")].filter(
      (node) => node.getBoundingClientRect().height > 0,
    );
    const smallest = visibleText
      .map((node) => ({
        size: parseFloat(getComputedStyle(node).fontSize),
        tag: node.tagName,
        className: node.className,
        text: node.textContent?.trim().slice(0, 80) ?? "",
      }))
      .filter((item) => Number.isFinite(item.size))
      .sort((left, right) => left.size - right.size)
      .slice(0, 8);
    return {
      minFont: fontSizes.length ? Math.min(...fontSizes) : 0,
      minButtonHeight: buttons.length
        ? Math.min(
            ...buttons.map((node) => node.getBoundingClientRect().height),
          )
        : 0,
      smallest,
    };
  });
  expect(
    typography.minFont,
    JSON.stringify(typography.smallest),
  ).toBeGreaterThanOrEqual(12);
  expect(typography.minButtonHeight).toBeGreaterThanOrEqual(40);
  const palette = await shell.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      muted: style.getPropertyValue("--rw-muted").trim(),
      background: style.getPropertyValue("--rw-bg").trim(),
    };
  });
  expect(palette.muted).toMatch(/^#[0-9a-f]{6}$/i);
  expect(palette.background).toMatch(/^#[0-9a-f]{6}$/i);
  expect(
    hexContrast(palette.muted, palette.background),
    `${palette.muted} on ${palette.background}`,
  ).toBeGreaterThanOrEqual(4.5);

  const main = shell.locator(".rw-preview-main");
  await main.evaluate((element) => {
    element.scrollTop = Math.min(800, element.scrollHeight);
  });
  expect(await main.evaluate((element) => element.scrollTop)).toBeGreaterThan(
    0,
  );
  await shell
    .locator(".rw-preview-left nav button")
    .filter({ hasText: "생산 영향" })
    .click();
  await expect
    .poll(() => main.evaluate((element) => element.scrollTop))
    .toBe(0);
});

test("gives the mobile assistant an opaque conversation-first layout", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  await shell.getByRole("button", { name: /Assistant/ }).click();
  const assistant = page.getByRole("dialog", { name: "Reliability Assistant" });
  await expect(assistant).toBeVisible();
  await expect(
    assistant.locator(".rw-context-assistant__prompts"),
  ).toBeHidden();
  const metrics = await assistant.evaluate((element) => {
    const thread = element.querySelector<HTMLElement>(
      ".rw-context-assistant__thread",
    );
    const composer = element.querySelector<HTMLElement>(
      ".rw-context-assistant__composer",
    );
    const close = element.querySelector<HTMLElement>(
      ".rw-context-assistant__close",
    );
    const background = getComputedStyle(element).backgroundColor;
    return {
      threadHeight: thread?.getBoundingClientRect().height ?? 0,
      threadFont: thread ? parseFloat(getComputedStyle(thread).fontSize) : 0,
      composerHeight: composer?.getBoundingClientRect().height ?? 0,
      closeHeight: close?.getBoundingClientRect().height ?? 0,
      background,
    };
  });
  expect(metrics.threadHeight).toBeGreaterThanOrEqual(844 * 0.45 - 2);
  expect(metrics.composerHeight).toBeGreaterThanOrEqual(44);
  expect(metrics.closeHeight).toBeGreaterThanOrEqual(44);
  expect(metrics.background).not.toContain("rgba(0, 0, 0, 0)");
});

test("stays within the viewport across the nine reliability QA sizes", async ({
  page,
}) => {
  await login(page);
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  const viewports = [
    { width: 390, height: 667 },
    { width: 390, height: 844 },
    { width: 768, height: 700 },
    { width: 900, height: 700 },
    { width: 1024, height: 700 },
    { width: 1280, height: 800 },
    { width: 1440, height: 800 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
  ];

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.waitForTimeout(80);
    const geometry = await shell.evaluate((element) => {
      const main = element.querySelector<HTMLElement>(".rw-preview-main");
      const heading = element.querySelector<HTMLElement>(
        ".rw-preview-page-heading",
      );
      const content = element.querySelector<HTMLElement>(".rw-preview-content");
      return {
        viewportWidth: document.documentElement.clientWidth,
        viewportHeight: document.documentElement.clientHeight,
        documentWidth: document.documentElement.scrollWidth,
        shellWidth: element.getBoundingClientRect().width,
        mainWidth: main?.clientWidth ?? 0,
        mainScrollWidth: main?.scrollWidth ?? 0,
        headingTop: heading?.getBoundingClientRect().top ?? -1,
        headingBottom: heading?.getBoundingClientRect().bottom ?? -1,
        contentTop: content?.getBoundingClientRect().top ?? -1,
      };
    });
    expect(
      geometry.documentWidth,
      `${viewport.width}x${viewport.height} document overflow`,
    ).toBeLessThanOrEqual(geometry.viewportWidth + 1);
    expect(
      geometry.shellWidth,
      `${viewport.width}x${viewport.height} shell width`,
    ).toBeLessThanOrEqual(geometry.viewportWidth + 1);
    expect(
      geometry.mainWidth,
      `${viewport.width}x${viewport.height} main width`,
    ).toBeGreaterThan(0);
    expect(
      geometry.mainScrollWidth,
      `${viewport.width}x${viewport.height} main overflow`,
    ).toBeLessThanOrEqual(geometry.mainWidth + 1);
    expect(
      geometry.headingTop,
      `${viewport.width}x${viewport.height} heading clipped`,
    ).toBeGreaterThanOrEqual(48);
    expect(
      geometry.headingBottom,
      `${viewport.width}x${viewport.height} heading should fit`,
    ).toBeLessThan(geometry.viewportHeight);
    expect(
      geometry.contentTop,
      `${viewport.width}x${viewport.height} content order`,
    ).toBeGreaterThanOrEqual(geometry.headingTop);
  }

  await page.setViewportSize({ width: 390, height: 667 });
  await page.waitForTimeout(100);
  await page.setViewportSize({ width: 1024, height: 700 });
  await page.waitForTimeout(150);
  const rail = shell.locator(".rw-preview-left");
  expect((await rail.boundingBox())?.width ?? 0).toBeGreaterThanOrEqual(220);
  await expect(rail.locator("nav button").first().locator("div")).toBeVisible();
});

test("keeps short-height rails and assistant content scrollable and dismisses the mobile rail after navigation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 900, height: 700 });
  await login(page);
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });

  const rail = shell.locator(".rw-preview-left");
  const nav = rail.locator(":scope > nav");
  const railMetrics = await nav.evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
    overflowY: getComputedStyle(element).overflowY,
  }));
  expect(railMetrics.scrollHeight).toBeGreaterThan(railMetrics.clientHeight);
  expect(railMetrics.overflowY).toBe("auto");
  await nav.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  expect(await nav.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);

  await shell.getByRole("button", { name: /Assistant/ }).click();
  const assistant = page.getByRole("dialog", { name: "Reliability Assistant" });
  await expect(assistant).toBeVisible();
  const thread = assistant.locator(".rw-context-assistant__thread");
  const threadMetrics = await thread.evaluate((element) => ({
    clientHeight: element.clientHeight,
    overflowY: getComputedStyle(element).overflowY,
  }));
  expect(threadMetrics.clientHeight).toBeGreaterThanOrEqual(96);
  expect(threadMetrics.overflowY).toBe("auto");
  await assistant
    .getByRole("button", { name: /닫기|Close Reliability Assistant/ })
    .click();

  await page.setViewportSize({ width: 390, height: 844 });
  await shell.getByRole("button", { name: "Open navigation" }).click();
  await expect(rail).toBeVisible();
  await rail.getByRole("button", { name: /운영 현황/ }).click();
  await expect(shell).toHaveClass(/left-collapsed/);
});

test("keeps light-mode report cards and charts light and exposes chart axes and point hover values", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem(
      "ontology-dashboard:reliability-theme",
      "light",
    );
    window.localStorage.setItem(
      "ontology-dashboard:reliability-locale",
      "ko-KR",
    );
  });
  await login(page);
  const shell = page.locator(
    ".rw-preview-shell:not(.rw-preview-loading-placeholder)",
  );
  await expect(shell).toBeVisible({ timeout: 15_000 });
  const drawer = page.getByRole("dialog", { name: "선택 설비 상세" });
  const candidates = shell.locator(".operations-factory-asset-node:not(.slot)");
  const chart = drawer.locator(".asset-series-chart").first();
  const candidateCount = Math.min(await candidates.count(), 16);
  for (let index = 0; index < candidateCount; index += 1) {
    await closeDetailDrawer(shell);
    await candidates.nth(index).click({ force: true });
    await expect(drawer).toBeVisible();
    const monitor = drawer.locator(".operations-live-feature-monitor");
    await expect(monitor)
      .not.toContainText("센서 이력 로딩 중", { timeout: 4_000 })
      .catch(() => undefined);
    if (await chart.count()) break;
    await drawer.getByRole("button", { name: "선택 설비 상세 닫기" }).click();
  }
  if (await chart.count()) {
    await expect(chart).toBeVisible();
    await expect(chart.locator(".asset-chart-axis-title")).toHaveCount(2);
    expect(
      await chart.locator(".asset-chart-hit-target").count(),
    ).toBeGreaterThan(0);
    const chartTheme = await chart.evaluate((element) => {
      const frame = element.querySelector<SVGElement>(".asset-chart-frame");
      return {
        background: getComputedStyle(element).backgroundColor,
        frameFill: frame ? getComputedStyle(frame).fill : "",
      };
    });
    expect(chartTheme.background).toBe("rgb(255, 255, 255)");
    expect(chartTheme.frameFill).toBe("rgb(248, 250, 252)");
    const hoverTarget = chart.locator(".asset-chart-hit-target").first();
    const tooltip = hoverTarget
      .locator("xpath=..")
      .locator(".asset-chart-tooltip");
    await hoverTarget.hover();
    await expect
      .poll(() =>
        tooltip.evaluate((element) =>
          Number.parseFloat(getComputedStyle(element).opacity),
        ),
      )
      .toBeGreaterThan(0.9);
    await expect(tooltip.locator("text.is-value")).toBeVisible();
  } else {
    await closeDetailDrawer(shell);
    await candidates.first().click({ force: true });
    await expect(drawer).toBeVisible();
    await expect(
      drawer.locator(".operations-live-feature-monitor"),
    ).toContainText(/관측 이력 없음|관측 이력 로딩 중/);
  }

  await drawer.getByRole("button", { name: "보고서 출력" }).click();
  const outputDialog = page.getByRole("dialog", {
    name: "보고서 출력 유형 선택",
  });
  const outputCard = outputDialog.locator(".operations-report-output-card");
  await expect(outputCard).toBeVisible();
  expect(
    await outputCard.evaluate(
      (element) => getComputedStyle(element).backgroundColor,
    ),
  ).toBe("rgb(255, 255, 255)");
});
