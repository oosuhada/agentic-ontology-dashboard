# Next Session Prompt — Palantir/Foundry UI Overhaul

아래 전체 내용을 새 ChatGPT 세션에 그대로 붙여넣는다.

---

@devspace.mcp

다음 로컬 프로젝트를 실제 checkout 모드로 열어줘.

## 작업 프로젝트

```text
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2
```

## Palantir/Foundry UI 레퍼런스 프로젝트

```text
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI
```

이번 세션의 최우선 목표는 backend, 인프라, connector, SSO, namespace migration이 아니라 **Ontology Dashboard의 사용자 화면을 Palantir Foundry/Contour/Object Explorer 계열 제품처럼 대폭 업그레이드하는 것**이다.

가장 먼저 다음 파일을 순서대로 읽어라.

```text
docs/palantir-ui-overhaul-master-plan.md
docs/palantir-contour-ui-reference.md
docs/palantir-ui-gap-verification-and-plan-v2.md
docs/ui/screenshots/palantir-gap-v2/README.md
docs/07-implementation-status.md
docs/09-architecture-decisions.md
docs/next-session-master-prompt.md
```

그 다음 현재 코드와 스크린샷을 확인하라.

```text
web/src/App.tsx
web/src/styles.css
web/src/workbench.css
web/src/features/dashboard/DashboardShell.tsx
web/src/features/dashboard/DashboardGridCanvas.tsx
web/src/features/dashboard/DashboardBoardRenderer.tsx
web/src/features/dashboard/BoardRuntimeSurface.tsx
web/src/features/dashboard/ContextPanel.tsx
web/src/features/dashboard/BoardCatalogPanel.tsx
web/src/features/dashboard/BoardInspector.tsx
web/src/features/analysis/
web/src/features/ontology/
web/src/features/datasets/
web/src/features/agent/
web/src/features/governance/
docs/ui/screenshots/palantir-gap-v2/
```

레퍼런스 프로젝트에서는 다음 파일과 license를 먼저 확인하라.

```text
palantir-blueprint/LICENSE
mini_foundry_public/LICENSE
mini_foundry_public/frontend/components/dashboards/DashboardCanvas.tsx
mini_foundry_public/frontend/components/dashboards/ComponentPalette.tsx
mini_foundry_public/frontend/components/dashboards/components/DataTable.tsx
mini_foundry_public/frontend/components/ontology/OntologyGraph.tsx
mini_foundry_public/frontend/lib/theme.ts
mini_foundry_public/frontend/app/globals.css
openfoundry-emulator/LICENSE
openfoundry-emulator/apps/app-console/src/pages/Contour.tsx
openfoundry-emulator/apps/app-console/src/components/DataTable.tsx
openfoundry-emulator/apps/app-console/src/styles/app.css
openfoundry-emulator/apps/app-workshop/src/widgets/widget-registry.ts
openfoundry-emulator/packages/ui/tokens/src/tokens.css
contour-translation/LICENSE
```

## 절대 우선순위

이번 세션에서는 다음 UI stage를 순서대로 실제 구현한다.

```text
UI-00 baseline, screenshot, license/reuse register
UI-01 Foundry design tokens와 공통 primitive
UI-02 global App Shell
UI-03 Dashboard shell과 parameter rail
UI-04 Board chrome, KPI, chart, dense table
```

UI-00 문서만 만들고 멈추지 말고, 같은 세션에서 최소 UI-01~UI-04까지 실제 route에 반영하라. 작업 여력이 남으면 UI-05 Analysis Workbench를 이어서 진행한다.

## 동결할 작업

다음 작업은 UI를 직접 막지 않는 한 수행하지 마라.

```text
신규 backend 도메인 기능
신규 repository/migration
connector
OIDC/SSO
managed infrastructure
factory_signal_board physical namespace 이전
새 ML 모델
새 Agent orchestration
새 역할 Dashboard
unrelated TODO 정리
```

UI가 꼭 필요로 하는 additive API field만 예외로 허용하며, 그 경우에도 기존 contract를 깨지 말고 같은 stage에서 실제 UI가 사용하도록 해라.

## Palantir 공식 사이트 사용 규칙

공식 공개 문서와 screenshot은 layout, pane ratio, toolbar, information hierarchy와 interaction behavior를 분석하는 reference로 사용해라.

다음은 금지한다.

```text
Palantir 공식 사이트 HTML 전체 복사
Palantir generated CSS/JS bundle 복사
Palantir logo, proprietary icon, font, image를 제품 asset으로 포함
authenticated Foundry tenant source/data 복사
브랜드를 Palantir/Foundry로 변경
```

Chrome DevTools를 사용할 경우 panel width, control height, spacing, typography, DOM landmark와 focus behavior만 측정해라.

## 코드 재사용 규칙

- `@blueprintjs/core`는 현재 설치된 package를 직접 사용한다.
- `mini_foundry_public` MIT 코드는 필요한 algorithm/component composition만 adaptation할 수 있다.
- `openfoundry-emulator` Apache-2.0 코드는 필요한 structure만 adaptation할 수 있다.
- `contour-translation` MIT 코드는 render-spec 아이디어를 참고할 수 있다.
- `Gods_Eye` GPL 코드는 복사하지 않는다.
- license가 명확하지 않은 `palantir-demo`, `OpenFoundry` 코드는 복사하지 않는다.
- adaptation한 경우 원본 path와 license를 주석과 `THIRD_PARTY_NOTICES.md`에 기록한다.
- reference project의 mock API, mock data, token auth, inline style block 전체를 그대로 가져오지 않는다.

## 구현 원칙

1. 현재 business logic과 API contract는 유지한다.
2. mock 화면을 새로 만들지 말고 현재 실제 runtime 데이터를 렌더링한다.
3. 공통 primitive를 먼저 만들고 Dashboard에서 실제 사용한 뒤 다른 route로 확장한다.
4. 큰 둥근 SaaS card, 과도한 shadow, 긴 설명문을 줄인다.
5. 28~32px control/table density, 얇은 border, 작은 radius, toolbar 중심 조작을 적용한다.
6. global top bar + navigation rail + workbench header + local toolbar + content 구조를 고정한다.
7. Dashboard는 parameter rail + dense canvas + optional inspector 구조로 만든다.
8. Board는 공통 32px header, status metadata, action menu, runtime footer를 사용한다.
9. KPI는 card grid보다 compact metric strip을 우선한다.
10. table은 sticky header, 28~30px row, type-aware cell, selected row와 virtualization을 제공한다.
11. chart는 selection, affected filter, source/version/timezone과 empty/loading/error 상태를 명확히 한다.
12. light/dark, keyboard, focus, 720px viewport를 항상 유지한다.

## 권장 신규 구조

```text
web/src/ui/foundry/
  tokens.css
  FoundryAppShell.tsx
  FoundrySidebar.tsx
  FoundryTopBar.tsx
  ScopeBreadcrumbs.tsx
  WorkbenchHeader.tsx
  WorkbenchToolbar.tsx
  ThreePaneLayout.tsx
  ResourceRail.tsx
  InspectorPanel.tsx
  DenseDataTable.tsx
  MetricStrip.tsx
  BoardFrame.tsx
  FilterRail.tsx
  StatusPill.tsx
  EntityTitle.tsx
  EmptyState.tsx
  LoadingState.tsx
  ErrorState.tsx
  SectionHeader.tsx
  index.ts
```

과도하게 추상화하지 말고 UI-04까지 실제로 사용하는 component만 만들어라.

## UI-00 수행 사항

- 현재 Git status와 `origin/main` divergence 확인
- 현재 commit SHA 기록
- 기존 server가 실행 중이면 재사용하거나 안전하게 재시작
- Dashboard, Analysis, Project Home, Agent, Ontology, Datasets, Governance, Admin을 다음 viewport로 캡처

```text
1440x1000
1728x1117
720x500
```

- `docs/ui/palantir-overhaul/baseline/`에 저장
- `docs/ui/palantir-overhaul/scorecard.md` 생성
- `THIRD_PARTY_NOTICES.md` 생성

## UI-01 수행 사항

- Foundry token CSS 생성
- Blueprint component density override
- common StatusPill, EntityTitle, WorkbenchHeader, Toolbar, Empty/Loading/Error state 구현
- raw color/spacing을 token으로 이동
- 기존 Dashboard 한 화면에서 실제 적용

## UI-02 수행 사항

- App 전체에 40px top bar 적용
- 48px navigation rail과 확장 sidebar 정리
- Organization/Project/Workspace/resource breadcrumbs
- Project/Workspace/Role selector를 scope control로 정리
- global command/search와 health/user area 정리
- route별 content origin과 header height 통일
- mobile navigation drawer 유지

## UI-03 수행 사항

- Dashboard resource header
- View/Edit segmented control
- compact tabs
- parameter rail 재설계
- filter chips, affected board count, clear-all
- Saved View, Share, Export action group
- Board Catalog drawer/palette
- persistent board inspector

## UI-04 수행 사항

- 모든 Dashboard renderer를 공통 BoardFrame으로 감싼다.
- KPI를 MetricStrip으로 변경한다.
- dense shared table을 도입한다.
- chart tooltip/legend/selection/state를 통일한다.
- server-first cross-filter와 client fallback 상태를 새 chrome 안에 유지한다.
- loading/empty/error/degraded/read-only 상태를 통일한다.

## 검증 방식

작업 도중 화면을 보지 않고 CSS만 작성하지 마라. 각 stage 후 실제 브라우저 screenshot을 생성해 기존 baseline과 비교한다.

최소 명령:

```bash
cd web
npm run test
npm run build
npm run test:e2e -- <관련 spec>
```

UI-04 완료 후:

```bash
.venv/bin/python -m pytest
cd web && npm run test && npm run build && npm run test:e2e
cd ..
.venv/bin/python scripts/check_visual_baselines.py
.venv/bin/python scripts/release_gate.py
```

필요하면 다음 E2E 파일을 추가한다.

```text
web/e2e/foundry-shell.spec.ts
web/e2e/foundry-dashboard.spec.ts
```

다음을 자동 검증한다.

- shell/panel dimensions
- toolbar height
- selected/hover/focus state
- keyboard shortcut
- one main landmark
- accessible names
- duplicate ID 없음
- document horizontal overflow 없음
- light/dark
- 720px viewport
- screenshot artifact

## 완료 기준

이번 세션 완료 시 최소 다음이 보여야 한다.

1. Dashboard screenshot이 이전 screenshot과 명백히 다른 제품 수준으로 개선되어 있다.
2. global shell이 Home, Dashboard, Analysis, Agent, Ontology, Datasets, Governance에 공통으로 적용된다.
3. Dashboard parameter rail, toolbar, tabs, board chrome, KPI, table, chart가 동일 디자인 시스템을 사용한다.
4. 기존 server-first cross-filter, Saved View, Share, Export, fullscreen, undo/redo, recovery가 유지된다.
5. baseline과 updated screenshot comparison이 저장된다.
6. 관련 Vitest/build/Playwright가 통과한다.
7. adaptation한 코드의 license와 원본 경로가 기록된다.
8. Palantir proprietary HTML/CSS/assets는 포함되지 않는다.

작업이 길어져도 계획만 작성하거나 사용자에게 다시 확인을 요청하지 말고, 실제 구현과 검증을 가능한 범위까지 계속 진행해라. 기능적으로 이미 완료된 backend 항목을 다시 구현하지 마라.

작업 종료 시 다음을 보고해라.

```text
변경한 UI 구조
새 공통 component
화면별 before/after 차이
재사용한 reference와 license
검증 결과
생성한 screenshot 경로
남은 UI stage
Git status와 commit/push 상태
```

---
