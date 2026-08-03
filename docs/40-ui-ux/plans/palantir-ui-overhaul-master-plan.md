# Palantir/Foundry 스타일 UI 전면 개편 마스터 플랜

- 작성일: 2026-08-02
- 대상 프로젝트: `mvp-프로젝트2` — Ontology Dashboard
- 임시 최우선 목표: **backend 기능 확장보다 사용자에게 보이는 Foundry형 제품 경험을 먼저 완성한다.**
- 실행 진입점: `docs/60-development-prompts/next-session-palantir-ui-overhaul-prompt.md`
- 기존 검증 문서:
  - `docs/40-ui-ux/reference/palantir-contour-ui-reference.md`
  - `docs/40-ui-ux/plans/palantir-ui-gap-verification-and-plan-v2.md`
  - `docs/ui/screenshots/palantir-gap-v2/README.md`

---

## 0. 이번 방향 전환의 결론

현재 제품은 기능적으로는 Dashboard, Analysis, Agent, Ontology, Datasets, Governance, Admin까지 연결되어 있다. 그러나 화면을 처음 본 사용자가 느끼는 제품 인상은 아직 **“Foundry형 통합 업무 플랫폼”보다 “기능이 많은 커스텀 React 대시보드”에 가깝다.**

따라서 다음 개발 사이클에서는 새로운 backend vertical, connector, SSO, managed infrastructure, namespace relocation을 우선하지 않는다. 기존 API와 데이터 계약을 최대한 고정하고 다음 순서로 UI를 전면 개편한다.

```text
1. 공통 Foundry형 디자인 시스템과 App Shell
2. Operations Dashboard
3. Contour형 Analysis 편집 공간
4. Object Explorer형 Ontology Workbench
5. Dataset Catalog
6. Agent Evidence / Governance
7. Admin / Auth
8. micro-interaction, keyboard, responsive, visual regression
```

목표는 Palantir 제품의 상표·코드·자산을 복제하는 것이 아니다. 목표는 다음 제품 언어를 우리 도메인에 맞게 구현하는 것이다.

- 고밀도 정보 구조
- 앱 전체에서 동일한 탐색 체계
- object/data/action 중심의 명확한 문맥
- 좌측 rail + 중앙 work area + 우측 inspector
- 작은 radius, 얇은 border, 절제된 elevation
- toolbar와 command 중심 조작
- 표와 그래프를 우선하는 업무형 화면
- 상태, 권한, lineage, freshness를 화면 안에서 설명
- 화면마다 같은 spacing, typography, control height 사용

---

## 1. 반드시 지킬 우선순위 동결 규칙

UI 전면 개편이 끝날 때까지 다음 작업은 기본적으로 후순위다.

### 동결 대상

- 신규 backend 도메인 기능
- 신규 repository 또는 migration
- production connector 구현
- OIDC/SSO/invitation/reset
- managed PostgreSQL/Redis/Neo4j 운영 작업
- `factory_signal_board` physical namespace 이전
- 새로운 역할 Dashboard 추가
- 새로운 ML 모델·metric
- 새로운 Agent orchestration 단계
- 현재 API contract를 바꾸는 대형 리팩터링

### 예외적으로 허용되는 backend 변경

다음 조건을 모두 만족할 때만 허용한다.

1. UI를 실제로 렌더링하기 위해 꼭 필요한 값이 현재 API에 없다.
2. 기존 contract를 깨지 않는 additive field 또는 작은 read endpoint다.
3. 해당 UI stage와 동일한 commit에서 사용된다.
4. 새 field의 E2E 또는 contract test가 추가된다.

### 금지되는 방식

- “UI를 바꾸는 김에” 서비스 계층을 전면 재작성
- UI stage 도중 unrelated TODO 처리
- 화면이 나오기 전에 architecture-only commit을 여러 개 생성
- 실제 화면 없이 component library만 장기간 구축
- mock 화면만 만들고 기존 runtime과 연결하지 않기

모든 stage는 **실제 route에서 동작하는 시각적 결과**로 끝나야 한다.

---

## 2. Palantir 사이트 HTML 복사에 대한 결정

### 결론

**Palantir 공식 사이트 또는 Foundry 제품 화면의 HTML/CSS/JavaScript를 통째로 복사하지 않는다.**

이유:

- 공개 문서의 HTML은 제품 runtime source가 아니며, 복사해도 Foundry의 실제 component behavior가 따라오지 않는다.
- class name, generated CSS, assets, tracking code와 documentation chrome이 섞여 있어 유지보수 가치가 낮다.
- 상표, proprietary asset, 문서 사이트 코드의 이용 조건이 open-source reference와 다르다.
- authenticated Foundry instance의 DOM/source를 복제하는 것은 제품 보안·라이선스 경계를 불명확하게 만든다.
- pixel-level 복사는 우리 데이터·권한·업무 흐름에 맞지 않는다.

### 허용되는 공식 사이트 활용법

공식 문서와 공개 이미지는 다음 용도로만 사용한다.

- pane 비율 측정
- header, toolbar, rail, inspector의 정보 계층 분석
- control 높이, gap, border, typography의 시각적 추정
- interaction 흐름 기록
- screenshot side-by-side 비교
- chart-to-chart filtering, fullscreen, parameter rail, object search 등 동작 명세 확인

Chrome DevTools를 사용할 경우 다음만 기록한다.

- viewport와 panel width
- computed spacing과 typography 범위
- DOM landmark 구조
- keyboard/focus behavior
- loading/empty/error state

복사하지 않는 항목:

- Palantir HTML 전체
- generated CSS bundle
- Palantir logo·brand asset
- proprietary icon/image/font
- minified JavaScript
- 인증된 Foundry tenant의 source 또는 데이터

제품에는 `Ontology Dashboard` 명칭과 자체 brand mark를 유지한다.

---

## 3. 코드 재사용 및 라이선스 정책

### Tier A — 직접 사용 권장

#### `palantir-blueprint`

- 라이선스: Apache-2.0
- 현재 앱은 이미 `@blueprintjs/core`를 사용한다.
- source를 vendoring하기보다 npm package component를 직접 사용한다.
- 우선 적용 대상:
  - Button / ButtonGroup
  - Navbar / Tabs
  - InputGroup / FormGroup / ControlGroup
  - HTMLSelect / Menu / Popover / Tooltip
  - Card / Section / Callout / NonIdealState
  - Dialog / Drawer / Overlay
  - Tag / CompoundTag / EntityTitle
  - Spinner / Skeleton / ProgressBar

#### `mini_foundry_public`

- 라이선스: MIT
- 직접 adaptation 가능하나 copyright notice를 유지한다.
- 우선 참고 파일:
  - `frontend/components/dashboards/DashboardCanvas.tsx`
  - `frontend/components/dashboards/ComponentPalette.tsx`
  - `frontend/components/dashboards/components/DataTable.tsx`
  - `frontend/components/ontology/OntologyGraph.tsx`
  - `frontend/components/pipelines/PipelineCanvas.tsx`
  - `frontend/app/globals.css`
  - `frontend/lib/theme.ts`

#### `openfoundry-emulator`

- 라이선스: Apache-2.0
- 직접 adaptation 가능하나 NOTICE/저작권 조건을 확인한다.
- 우선 참고 파일:
  - `apps/app-console/src/pages/Contour.tsx`
  - `apps/app-console/src/components/DataTable.tsx`
  - `apps/app-console/src/styles/app.css`
  - `apps/app-workshop/src/widgets/widget-registry.ts`
  - `apps/app-workshop/src/styles/workshop.css`
  - `packages/ui/tokens/src/tokens.css`

#### `contour-translation`

- 라이선스: MIT
- render spec과 board translation 아이디어를 참고한다.

### Tier B — 직접 복사 금지, 구조만 참고

#### `Gods_Eye`

- GPL-3.0
- 현재 프로젝트에 코드를 복사하거나 import하지 않는다.
- map, layer, timeline interaction 아이디어만 참고한다.

#### `palantir-demo`

- 명시적 license 파일이 확인되지 않았다.
- code copy 금지.
- screenshot, layout idea만 참고한다.

#### `OpenFoundry`

- 로컬 license 파일이 비어 있어 사용 조건을 확정할 수 없다.
- code copy 금지.
- information architecture와 service boundary만 참고한다.

### 재사용 기록 규칙

직접 adaptation한 파일에는 상단 주석을 남긴다.

```ts
/**
 * Adapted from mini_foundry_public DashboardCanvas.tsx (MIT).
 * Original copyright and license are listed in THIRD_PARTY_NOTICES.md.
 * Adaptation: Ontology Dashboard grid contracts and Foundry-style chrome.
 */
```

프로젝트 루트에 다음 파일을 추가한다.

```text
THIRD_PARTY_NOTICES.md
```

내용:

- 프로젝트명
- 원본 repository/path
- license
- adaptation한 파일
- 원본 copyright notice
- 변경 요약

코드를 거의 그대로 복사하기보다 **layout algorithm, component composition, interaction pattern을 현재 type/API에 맞게 다시 작성**하는 방식을 우선한다.

---

## 4. 공식 Palantir UI 레퍼런스 맵

다음 공식 공개 문서를 기준 화면으로 사용한다.

### Dashboard / Contour

- Contour Dashboard overview
  - `https://www.palantir.com/docs/foundry/contour/dashboards-overview`
- Dashboard getting started
  - `https://www.palantir.com/docs/foundry/contour/dashboards-getting-started/index.html`
- Contour overview
  - `https://www.palantir.com/docs/foundry/contour/overview`
- Contour core concepts
  - `https://www.palantir.com/docs/foundry/contour/core-concepts/`

확인할 요소:

- application header와 analysis/dashboard mode 전환
- 좌측 parameter panel
- board title/action chrome
- chart-to-chart filtering
- dashboard preview와 add-to-dashboard flow
- fullscreen presentation
- export menu

### Object Explorer / Ontology

- Object Explorer overview
  - `https://www.palantir.com/docs/foundry/object-explorer/overview`
- Object Explorer getting started
  - `https://www.palantir.com/docs/foundry/object-explorer/getting-started`
- Ontology Manager overview
  - `https://www.palantir.com/docs/foundry/ontology-manager/overview/index.html`
- Ontology Manager navigation
  - `https://www.palantir.com/docs/foundry/ontology-manager/navigation`

확인할 요소:

- global ontology search
- object type grouping과 preview
- object set / table / exploration mode
- object inspector와 relation navigation
- left navigation, resource list, central table/graph, right detail pane

### Governance / Checkpoints

- Checkpoints overview
  - `https://www.palantir.com/docs/foundry/checkpoints/overview`
- Review checkpoint records
  - `https://www.palantir.com/docs/foundry/checkpoints/review-checkpoint-records`

확인할 요소:

- dense filter toolbar
- records table
- selected record detail
- permission redaction 상태
- justification와 audit metadata

### Agent

- Agents overview
  - `https://www.palantir.com/docs/foundry/agents/overview`
- AIP Chatbot Studio overview
  - `https://www.palantir.com/docs/foundry/chatbot-studio/overview`

확인할 요소:

- conversational work area
- attached context/evidence
- run/activity trace
- publish/status metadata
- right-side configuration or evidence detail

---

## 5. 현재 UI의 핵심 격차

### 5.1 전체 App Shell

현재 강점:

- Product Navigation 존재
- Project/Workspace/Role selector 존재
- theme와 command palette 존재
- route별 workbench 연결 완료

남은 격차:

- sidebar, top bar, page header, status strip가 하나의 제품 hierarchy로 보이지 않는다.
- 각 feature가 서로 다른 card, button, typography 규칙을 사용한다.
- page title과 current object/resource context가 약하다.
- toolbar가 페이지마다 위치와 높이가 다르다.
- whitespace와 card radius가 업무형 Foundry UI보다 크다.
- 화면에 긴 설명 문장이 많고 데이터가 뒤로 밀린다.

### 5.2 Dashboard

현재 강점:

- 12-column grid
- drag/resize
- server-first cross-filter
- tabs, parameter, saved view, share, export
- ECharts, virtual table, Evidence/Action

남은 격차:

- board chrome가 Foundry board처럼 조밀하지 않다.
- KPI card가 일반 SaaS dashboard 형태에 가깝다.
- parameter rail이 filter workbench보다 form list처럼 보인다.
- edit/view mode의 차이가 tool behavior보다 button 표시 차이에 가깝다.
- selection filter와 affected board 상태가 시각적으로 약하다.
- table header, row density, sorting/filter affordance가 더 고도화되어야 한다.
- board loading, stale, error, empty 상태가 통일되어 있지 않다.

### 5.3 Analysis

현재 강점:

- board rail
- React Flow path
- inspector
- server run lifecycle
- lineage mini graph
- add to Dashboard / save Dataset

남은 격차:

- Contour의 “연속적인 분석 경로”보다 일반 node editor처럼 보인다.
- board type identity, connector, output preview가 약하다.
- selected board의 config와 result inspector가 충분히 밀도 높지 않다.
- input dataset/version, current run, unsaved state와 publish 상태가 header에 통합되지 않았다.
- board add interaction이 visual workflow 중심이 아니다.

### 5.4 Ontology

현재 강점:

- object list, graph, inspector
- multi-store Ask
- Project/Workspace scope

남은 격차:

- Object Explorer의 ontology-wide search와 object type orientation이 부족하다.
- object rail과 property panel이 일반 custom pane처럼 보인다.
- object set table/exploration mode 전환이 없다.
- selected object identity, status, links와 actions가 하나의 object view로 정리되지 않았다.
- graph chrome와 legend가 제품 전체 스타일과 다르다.

### 5.5 Dataset Catalog

현재 강점:

- server pagination/search
- schema/profile/files/lineage/materialization

남은 격차:

- dataset list가 resource browser보다 card/list 조합에 가깝다.
- dataset identity, version, freshness, owner, quality가 한 줄에 조밀하게 보이지 않는다.
- detail pane의 tabs와 metadata hierarchy가 약하다.
- schema table와 profile visualization이 Foundry data catalog 수준으로 보이지 않는다.

### 5.6 Agent / Governance

현재 강점:

- claims/evidence/trace/checkpoint 연결
- persisted run
- Governance records와 projection retry

남은 격차:

- Agent 화면이 chat workbench보다 form + 결과 card 형태다.
- run history와 current conversation의 hierarchy가 약하다.
- claims, evidence와 trace가 별도 list이지만 동일 run context로 느껴지지 않는다.
- Governance는 dense audit application보다 여러 section card의 조합처럼 보인다.

### 5.7 Admin / Auth

- Admin은 control plane의 hierarchy, table density, drawer/dialog 흐름을 통일해야 한다.
- Login/Register는 제품 brand와 security context를 더 명확히 보여야 하지만, Dashboard/Analysis보다 후순위다.

---

## 6. 목표 디자인 시스템

### 6.1 새 폴더 구조

```text
web/src/ui/foundry/
  tokens.css
  reset.css
  FoundryAppShell.tsx
  FoundrySidebar.tsx
  FoundryTopBar.tsx
  ScopeBreadcrumbs.tsx
  WorkbenchHeader.tsx
  WorkbenchToolbar.tsx
  ThreePaneLayout.tsx
  ResourceRail.tsx
  InspectorPanel.tsx
  SplitPane.tsx
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
  CommandMenu.tsx
  index.ts
```

기존 feature는 새 primitive를 사용하되 business component 자체는 유지한다.

### 6.2 CSS 분리

현재:

```text
web/src/styles.css       1500+ lines
web/src/workbench.css     500+ lines
```

목표:

```text
web/src/ui/foundry/tokens.css
web/src/ui/foundry/shell.css
web/src/ui/foundry/components.css
web/src/features/dashboard/dashboard.css
web/src/features/analysis/analysis.css
web/src/features/ontology/ontology.css
web/src/features/datasets/datasets.css
web/src/features/agent/agent.css
web/src/features/governance/governance.css
web/src/features/admin/admin.css
```

한 번에 전부 이동하지 않는다. stage별로 새 stylesheet로 옮기고 기존 selector를 제거한다.

### 6.3 권장 token baseline

다음 값은 Palantir proprietary CSS 복사가 아니라 Blueprint와 공개 screenshot을 참고한 자체 baseline이다.

```css
:root {
  --fd-canvas: #f5f7f9;
  --fd-surface: #ffffff;
  --fd-surface-subtle: #eef1f4;
  --fd-surface-selected: #e8f1fb;
  --fd-text: #182026;
  --fd-text-secondary: #5f6b7c;
  --fd-text-muted: #738091;
  --fd-border: #d3d8de;
  --fd-border-strong: #a7b0ba;
  --fd-accent: #2d72d2;
  --fd-accent-hover: #215db0;
  --fd-success: #238551;
  --fd-warning: #c87619;
  --fd-danger: #c23030;

  --fd-radius-xs: 2px;
  --fd-radius-sm: 4px;
  --fd-radius-md: 6px;

  --fd-control-h: 28px;
  --fd-toolbar-h: 34px;
  --fd-topbar-h: 40px;
  --fd-table-row-h: 28px;
  --fd-sidebar-icon-w: 48px;
  --fd-sidebar-expanded-w: 220px;
  --fd-inspector-w: 320px;

  --fd-space-1: 4px;
  --fd-space-2: 8px;
  --fd-space-3: 12px;
  --fd-space-4: 16px;
  --fd-space-5: 20px;

  --fd-font-ui: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --fd-font-mono: "SFMono-Regular", Consolas, monospace;
  --fd-font-xs: 11px;
  --fd-font-sm: 12px;
  --fd-font-md: 13px;
  --fd-font-lg: 16px;
  --fd-font-title: 20px;

  --fd-shadow-popover: 0 4px 16px rgba(17, 20, 24, .16);
}
```

### 6.4 시각 규칙

- 일반 업무 panel에는 큰 drop shadow를 사용하지 않는다.
- card는 기본적으로 border 기반이다.
- radius 12px 이상의 “둥근 SaaS card”를 제거한다.
- 데이터 영역 안의 설명 문장은 1~2줄로 제한한다.
- section title보다 resource identity와 current selection을 우선한다.
- icon button은 tooltip과 aria-label을 항상 가진다.
- table row는 28~32px를 기본으로 한다.
- top-level action만 solid accent button을 사용한다.
- 위험도 색은 배경 전체가 아니라 pill, icon, small marker 중심으로 사용한다.
- chart는 decoration보다 axis, tooltip, selection, reference line 가독성을 우선한다.
- loading, stale, degraded, offline, read-only 상태를 동일한 StatusPill 체계로 표현한다.

---

## 7. 단계별 구현 계획

## Stage UI-00 — UI 작업선 고정과 baseline

### 목표

기능 회귀 없이 UI만 바꿀 수 있는 출발점을 고정한다.

### 작업

1. Git clean/sync 확인.
2. 현재 `main` SHA 기록.
3. 다음 route를 1440×1000, 1728×1117, 720×500으로 캡처.
   - Dashboard
   - Analysis
   - Project Home
   - Agent
   - Ontology
   - Datasets
   - Governance
   - Admin
4. `docs/ui/palantir-overhaul/baseline/`에 저장.
5. 각 화면의 문제를 annotation 없이 Markdown scorecard로 기록.
6. `THIRD_PARTY_NOTICES.md` 생성.
7. UI worktree 또는 별도 branch를 사용할지 결정하되 실제 checkout을 요청받으면 현재 checkout에서 작업.

### 완료 기준

- baseline screenshot manifest 존재
- route별 visual gap score 존재
- backend test baseline과 Playwright baseline 기록
- license/reuse register 존재

---

## Stage UI-01 — Foundry design tokens와 공통 primitive

### 목표

모든 feature가 같은 시각 언어를 쓰도록 foundation을 만든다.

### 대상 파일

- 신규 `web/src/ui/foundry/*`
- `web/src/styles.css`
- `web/src/workbench.css`
- `web/src/App.tsx`

### 구현

- token CSS
- Blueprint theme class 정리
- dense Button/Input/Select/Table override
- StatusPill
- EntityTitle
- WorkbenchHeader
- WorkbenchToolbar
- SectionHeader
- Empty/Loading/Error state
- ThreePaneLayout
- ResourceRail / InspectorPanel

### 레퍼런스

- Blueprint design token과 core component
- `openfoundry-emulator/packages/ui/tokens/src/tokens.css`
- `mini_foundry_public/frontend/lib/theme.ts`

### 완료 기준

- Storybook을 새로 도입하지 않는다. 대신 `/app` 실제 shell에서 primitive를 사용한다.
- Dashboard 한 화면에서 token 변경이 실제로 보인다.
- light/dark 모두 contrast와 focus ring이 유지된다.
- 신규 raw color literal은 lint 또는 grep으로 제한한다.

---

## Stage UI-02 — Global App Shell 전면 교체

### 목표

어떤 Workbench로 이동해도 동일한 Foundry 제품 안에 있다는 인상을 만든다.

### 대상 파일

- `DashboardShell.tsx`
- `App.tsx`
- `ProjectHomePage.tsx`
- 신규 `FoundryAppShell.tsx`, `FoundrySidebar.tsx`, `FoundryTopBar.tsx`

### 구현 구조

```text
40px global top bar
├ product identity
├ breadcrumbs: Organization / Project / Workspace / Resource
├ global search / command
├ environment and store health
└ user menu

48px icon rail + optional 220px expanded navigation
├ Home
├ Dashboards
├ Analysis
├ Agent
├ Ontology
├ Datasets
├ Governance
└ Admin when allowed

main workbench
├ resource header
├ local toolbar
└ route content
```

### 세부 작업

- 현재 sidebar brand/header/scope section 재구성
- Project/Workspace/Role selector를 top context bar 또는 scope popover로 통합
- page별 중복 title 제거
- global health를 작은 status 영역으로 축소
- command palette를 resource-aware로 재구성
- active route indicator와 hover/focus 통일
- sidebar collapse behavior와 mobile drawer 유지

### 완료 기준

- 모든 주요 route가 동일 shell을 사용
- route 이동 시 header 높이와 content origin이 바뀌지 않음
- top bar, local toolbar, content scroll 영역이 분리됨
- 720px에서 navigation drawer가 동작

---

## Stage UI-03 — Dashboard shell과 parameter rail

### 목표

현재 Dashboard를 일반 SaaS dashboard가 아니라 Contour Dashboard 소비 화면으로 보이게 한다.

### 대상 파일

- `DashboardShell.tsx`
- `ContextPanel.tsx`
- `BoardCanvas.tsx`
- `DashboardGridCanvas.tsx`
- `BoardCatalogPanel.tsx`
- `BoardInspector.tsx`
- `dashboard.css`

### 구현

- resource header에 Dashboard name, source Analysis, version, freshness 표시
- View/Edit mode를 segmented control로 변경
- tabs를 compact tab bar로 변경
- Share/Export/Save를 toolbar action group으로 정리
- parameter rail을 sectioned filter panel로 재설계
- active filters를 compact chip과 clear-all action으로 표시
- affected board count를 parameter 옆에 표시
- saved view를 select/popover 형태로 통합
- Board Catalog를 modal이 아니라 left drawer 또는 overlay palette로 재구성
- Inspector를 persistent right pane로 정리

### 레퍼런스

- 공식 Contour Dashboard overview/getting started
- `mini_foundry_public/DashboardCanvas.tsx`
- `mini_foundry_public/ComponentPalette.tsx`

### 완료 기준

- Dashboard 화면에서 가장 먼저 데이터와 parameter가 보이고 설명 card가 전면에 나오지 않음
- view mode에서는 edit affordance가 숨겨짐
- edit mode에서는 drag handle, resize handle, selected board outline, inspector가 명확함
- parameter rail width와 inspector width가 고정 token을 사용

---

## Stage UI-04 — Board chrome, KPI, chart, table

### 목표

모든 Board renderer의 외곽과 상태 표현을 통일한다.

### 대상 파일

- `DashboardBoardRenderer.tsx`
- `BoardRuntimeSurface.tsx`
- `AdvancedBoards.tsx`
- `CatalogDataBoard.tsx`
- `AnalysisReferenceBoard.tsx`
- `RoleBoardRenderer.tsx`
- `EChart*.tsx`
- 신규 `BoardFrame.tsx`, `MetricStrip.tsx`, `DenseDataTable.tsx`

### BoardFrame 표준

```text
header 32px
├ drag handle/edit mode only
├ icon + title
├ runtime/status metadata
└ actions: filter state / fullscreen / menu
body
footer optional
├ rows, freshness, timezone, cache, server/client state
```

### KPI 변경

- 큰 둥근 card 여러 개 대신 compact metric strip
- value, label, delta, basis를 한 hierarchy로 표시
- warning/critical은 얇은 marker와 pill 사용
- 숫자의 근거가 없는 decorative trend 제거

### Chart 변경

- axis/legend font token 통일
- chart background 투명
- selection dimming과 active mark 강화
- hover tooltip에 source/version/timezone 표시
- empty/loading/error를 공통 state로 교체

### Table 변경

- TanStack table 기반 공통 DenseDataTable
- sticky header
- 28~30px row
- property type icon
- sort/filter affordance
- selected row state
- right-aligned numeric cells
- null, stale, warning 표시
- virtualization 유지

### 완료 기준

- Dashboard의 모든 board가 동일 header 높이와 menu 위치를 가짐
- table, chart, KPI가 같은 surface/border/token 사용
- server-first cross-filter badge가 footer/status 체계에 통합
- screenshot에서 “서로 다른 라이브러리 component 조합” 느낌이 사라짐

---

## Stage UI-05 — Contour형 Analysis Workbench

### 목표

Analysis를 일반 React Flow node editor가 아니라 “데이터를 단계별로 변환하고 검증하는 Contour 작업 공간”으로 바꾼다.

### 대상 파일

- `AnalysisShell.tsx`
- `AnalysisPage.tsx`
- `AnalysisBoardRail.tsx`
- `AnalysisPathCanvas.tsx`
- `AnalysisBoardCard.tsx`
- `AnalysisInspector.tsx`
- `AnalysisResultInspector.tsx`
- `AnalysisLineageMiniGraph.tsx`
- `analysis.css`

### 화면 구조

```text
Header
├ Analysis name / owner / revision
├ Dataset version / UTC
├ unsaved / saved / running state
└ Run / Save / Share / Add to Dashboard / Save Dataset

Left board rail 200~220px
├ Inputs
├ Transform
├ Aggregate
├ Visualize
└ Output

Center path
├ vertically ordered board cards
├ connector and + insertion control
├ selected output preview
└ run progress overlay

Right inspector 320~360px
├ Configuration
├ Result
├ Quality
├ Lineage
└ Runtime
```

### 핵심 변경

- React Flow 자유 배치보다 vertical flow가 우선되도록 node positions 고정
- board type별 color는 header 전체가 아니라 icon/left stripe로 제한
- 각 board card에 input rows → output rows 표시
- connector에 add-board control
- selected board output sample을 card 하단 또는 inspector에서 즉시 확인
- run progress를 node별 status로 표시
- error node는 해당 위치에서 원인과 retry 제공
- lineage mini graph는 inspector tab 안에 배치
- Analysis와 Dashboard 간 mode 전환을 top header에서 명확히 표시

### 레퍼런스

- 공식 Contour overview/create path/board toolbar
- `openfoundry-emulator/Contour.tsx`
- `contour-translation`

### 가져오지 않을 것

- openfoundry mock object data
- localStorage bearer token helper
- inline style object 전체
- mock aggregation logic

### 완료 기준

- 첫 화면에서 Input → Filter/Group → Chart 흐름을 시각적으로 읽을 수 있음
- board 추가 지점이 명확함
- config와 result가 선택 board 기준으로 즉시 바뀜
- server run lifecycle가 화면 위계에 자연스럽게 통합됨

---

## Stage UI-06 — Object Explorer형 Ontology Workbench

### 목표

Ontology 화면을 graph demo가 아니라 object discovery와 operational action을 수행하는 Object Explorer로 바꾼다.

### 대상 파일

- `OntologyPreviewPage.tsx`
- `ontology.css`
- 필요 시 신규:
  - `OntologyHome.tsx`
  - `ObjectTypeRail.tsx`
  - `ObjectSetTable.tsx`
  - `ObjectViewInspector.tsx`
  - `OntologyGraphView.tsx`

### 구현

- top global object search
- object type group/filter
- Table / Exploration / Graph mode switch
- left object type/resource rail
- central object set table 또는 graph
- right object view inspector
- selected object header에 type icon, primary key, status, source 표시
- Properties / Links / Actions / Lineage tabs
- Action buttons는 permission과 read-only 상태 반영
- graph legend, depth, direction, layout control을 toolbar로 이동
- Ask Ontology는 중앙 화면을 밀어내는 큰 form이 아니라 command/chat drawer로 제공

### 레퍼런스

- 공식 Object Explorer overview/getting started
- 공식 Ontology Manager navigation
- `mini_foundry_public/OntologyGraph.tsx`

### 완료 기준

- 사용자가 search → object set → selected object → relation/action 흐름을 한 화면에서 이해
- graph를 열지 않아도 object 탐색 가능
- object view가 Dataset/Agent/Governance와 같은 EntityTitle/Inspector primitive 사용

---

## Stage UI-07 — Dataset Catalog resource browser

### 목표

Dataset Catalog를 Foundry형 데이터 resource browser로 바꾼다.

### 대상 파일

- `DatasetCatalogPage.tsx`
- `datasets.css`
- 공통 DenseDataTable/EntityTitle/InspectorPanel

### 구조

```text
Header: Datasets / current Project / create or ingest when permitted
Toolbar: search, owner, type, quality, freshness, sort
Left/main: dense dataset table
Right: selected dataset inspector
  Overview
  Schema
  Profile
  Files
  Versions
  Lineage
  Projections
```

### 구현

- card 중심 list 제거
- dataset row에 name, version, owner, rows, updated, quality, status 표시
- selected row 유지
- schema를 dense property table로 변경
- profile metric을 compact strip과 distribution preview로 표시
- lineage source/target를 mini graph 또는 structured list로 표시
- materialization/projection status를 공통 StatusPill 사용

### 완료 기준

- 20개 이상 dataset에서도 정보 밀도가 유지되는 구조
- detail pane를 닫아도 list가 충분한 정보를 제공
- Dataset Version identity가 항상 보임

---

## Stage UI-08 — Agent Evidence와 Governance

### Agent 목표

chat, run history, claims/evidence/trace를 하나의 run context로 통합한다.

### Agent 구조

```text
Left 240px: run history / filters
Center: conversation and answer
Right 340px: Evidence / Claims / Trace / Checkpoints
Bottom composer: question + context attachment + run
```

### Agent 대상 파일

- `AgentWorkbenchPage.tsx`
- `AgentQueryBoard.tsx`
- `GroundedClaimList.tsx`
- `EvidenceTraceList.tsx`
- `OrchestrationStepper.tsx`
- `agent.css`

### Governance 목표

Checkpoints형 dense audit application으로 변경한다.

### Governance 구조

```text
Header and tabs: Review / Approvals / Projections
Filter toolbar
Records table
Selected record inspector
```

### Governance 대상 파일

- `GovernanceWorkbenchPage.tsx`
- `governance.css`

### 완료 기준

- Agent 답변의 claim 클릭 시 right inspector evidence가 선택됨
- trace와 checkpoint가 card 나열이 아니라 ordered activity로 보임
- Governance filter/table/detail이 한 화면에서 동작
- permission redaction과 degraded 상태가 명확함

---

## Stage UI-09 — Admin, Auth, Project Home

### Admin

- Users, Membership, Roles, Approvals, Audit를 shared control-plane shell로 통합
- table + detail drawer 패턴
- destructive action은 Blueprint Alert/Dialog
- status/role pill 통일

### Auth

- 과도한 marketing card 제거
- product identity, environment, security notice, login form hierarchy 정리
- demo account는 development mode에서만 별도 expandable panel

### Project Home

- 큰 소개 card보다 resource launchpad와 current health를 우선
- recent resources, active analyses, dashboard, dataset, governance queue를 compact table/list로 구성

### 완료 기준

- Admin도 다른 Workbench와 같은 token/control 사용
- Login은 독립 페이지지만 같은 brand/type/button 체계 사용

---

## Stage UI-10 — Interaction, keyboard, responsive

### 구현

- keyboard shortcut registry
- command palette resource action
- focus visible와 focus return
- resize handle, splitter keyboard support
- context menu
- hover/selected/active/disabled 상태 통일
- Skeleton loading
- optimistic save indicator
- unsaved/recovery UI를 top status에 통합
- reduced motion 지원
- 200% zoom equivalent 유지

### 권장 shortcut

```text
Cmd/Ctrl+K        command palette
Cmd/Ctrl+S        save
Cmd/Ctrl+Enter    run current Analysis/Agent
Cmd/Ctrl+Z        undo
Cmd/Ctrl+Shift+Z  redo
/                 focus current search
Escape            close overlay / clear selection
F                 fullscreen selected board
```

### 완료 기준

- mouse 없이 주요 탐색 가능
- mobile은 Dashboard 소비/Field flow 중심으로 유지
- Analysis 편집은 작은 화면에서 unsupported 안내와 read-only preview 제공 가능

---

## Stage UI-11 — 시각 회귀와 수용 기준

### 캡처 matrix

각 route를 다음 viewport에서 캡처한다.

```text
1440 × 1000  기본 비교
1728 × 1117  넓은 desktop
1280 × 800   작은 laptop
720 × 500    200% zoom-equivalent
390 × 844    mobile consumption/field only
```

### 상태 matrix

- populated
- empty
- loading
- error
- degraded
- read-only
- permission denied
- selected row/object/board
- active cross-filter
- edit mode
- dark theme

### 비교 artifact

```text
docs/ui/palantir-overhaul/
  baseline/
  stage-01-shell/
  stage-03-dashboard/
  stage-05-analysis/
  stage-06-ontology/
  stage-07-datasets/
  stage-08-agent-governance/
  final/
  scorecard.md
  comparison.html
  baseline-manifest.json
```

### 시각 점수표

| 항목 | 배점 |
|---|---:|
| Global hierarchy와 navigation | 15 |
| Information density | 15 |
| Typography와 spacing consistency | 10 |
| Table/resource browser quality | 10 |
| Board/chart chrome | 10 |
| Three-pane workbench composition | 10 |
| Selection/filter/action feedback | 10 |
| Loading/empty/error/degraded states | 5 |
| Keyboard/accessibility | 5 |
| Responsive behavior | 5 |
| Official reference와의 structural similarity | 5 |
| 합계 | 100 |

최종 목표:

```text
전체 85점 이상
Dashboard 90점 이상
Analysis 90점 이상
어느 화면도 75점 미만 금지
```

“동작한다”만으로 stage를 완료하지 않는다. screenshot을 열어 side-by-side로 판단한다.

---

## 8. 파일별 재사용 후보 맵

| 현재 파일 | 참고 코드 | 적용할 것 | 적용하지 않을 것 |
|---|---|---|---|
| `DashboardGridCanvas.tsx` | `mini_foundry_public/DashboardCanvas.tsx` | container width 측정, 12열 layout mapping, drag cancel | reference project의 data model과 renderer |
| `BoardCatalogPanel.tsx` | `mini_foundry_public/ComponentPalette.tsx` | categorized palette, search, compatible item state | Tailwind class 그대로 복사 |
| 공통 table | 두 reference의 `DataTable.tsx` | compact header, type-aware cell, sticky structure | mock API/data |
| `AnalysisPathCanvas.tsx` | `openfoundry-emulator/Contour.tsx` | vertical board pipeline, connector, add control, board identity | inline style block, mock ontology, local token auth |
| `OntologyPreviewPage.tsx` | `mini_foundry_public/OntologyGraph.tsx` | graph toolbar와 selected node flow | backend contract |
| `AnalysisReferenceBoard.tsx` | `contour-translation` | structured render spec translation | project-specific pipeline code |
| global tokens | Blueprint + openfoundry tokens | naming, density, intent hierarchy | proprietary Palantir site CSS |

---

## 9. 구현 중 유지해야 할 현재 기능

다음 기능은 UI 교체 후에도 반드시 유지한다.

### Dashboard

- server-first cross-filter
- matching object ID scope
- explicit client fallback
- saved view
- share state
- export checkpoint
- fullscreen
- undo/redo
- draft recovery
- mandatory board policy
- role-specific templates

### Analysis

- server run lifecycle
- cancel/cache/cursor
- result quality
- lineage
- save Dataset
- add to Dashboard

### Ontology

- Project/Workspace permission
- object query
- relation traversal
- Action boundary
- Project 3 degraded fallback

### Agent/Governance

- persisted runs
- claim/evidence trace
- checkpoints
- approvals
- projection retry
- redaction and permission

UI 구현 때문에 이 기능들을 mock으로 대체하지 않는다.

---

## 10. 테스트와 검증 명령

각 stage 최소 검증:

```bash
cd web
npm run test
npm run build
npm run test:e2e -- <관련 spec>
```

주요 stage 종료:

```bash
.venv/bin/python -m pytest
cd web && npm run test && npm run build && npm run test:e2e
cd ..
.venv/bin/python scripts/check_visual_baselines.py
.venv/bin/python scripts/release_gate.py
```

UI-specific E2E를 별도 spec으로 분리한다.

```text
web/e2e/foundry-shell.spec.ts
web/e2e/foundry-dashboard.spec.ts
web/e2e/foundry-analysis.spec.ts
web/e2e/foundry-object-explorer.spec.ts
web/e2e/foundry-resource-browser.spec.ts
```

검사 항목:

- panel width와 toolbar height
- route별 shell consistency
- selected/hover/focus state
- keyboard
- screenshot artifact
- no horizontal document overflow
- one main landmark
- accessible name
- duplicate ID 없음

---

## 11. Git 운영 방식

한 stage를 여러 unrelated commit으로 쪼개지 않는다. 다음 단위를 권장한다.

```text
feat(ui): establish Foundry design system and shell
feat(ui): overhaul Contour-style dashboard experience
feat(ui): rebuild analysis as a Contour workbench
feat(ui): add Object Explorer-style ontology workspace
feat(ui): redesign dataset resource browser
feat(ui): unify agent evidence and governance workbenches
test(ui): add Foundry visual regression matrix
```

각 commit 전:

- relevant Vitest
- build
- relevant Playwright
- screenshot review
- `git diff --check`

각 major stage 후 원격 push 가능. 사용자가 별도 지시하지 않으면 final full gate 후 한 번에 push해도 된다.

---

## 12. 완료 정의

다음 조건을 모두 만족해야 “Palantir UI overhaul 완료”로 본다.

1. 모든 주요 route가 동일 FoundryAppShell을 사용한다.
2. Dashboard가 parameter rail + dense board canvas + inspector 구조를 가진다.
3. Analysis가 vertical Contour path와 config/result inspector를 가진다.
4. Ontology가 search/object set/object view 중심으로 동작한다.
5. Dataset Catalog가 dense resource table + detail inspector 구조다.
6. Agent는 run history + conversation + evidence inspector 구조다.
7. Governance는 filters + records table + detail inspector 구조다.
8. Blueprint control height와 typography가 전 화면에서 통일된다.
9. 큰 rounded SaaS card와 화면별 임의 style이 대부분 제거된다.
10. 기존 backend contract와 business functionality가 유지된다.
11. full Python/Vitest/build/Playwright/release gate가 통과한다.
12. 최종 visual score 85점 이상이며 Dashboard와 Analysis는 90점 이상이다.
13. 재사용한 open-source code가 `THIRD_PARTY_NOTICES.md`에 기록된다.
14. Palantir proprietary HTML/CSS/assets를 제품 코드에 포함하지 않는다.

---

## 13. 다음 세션에서 가장 먼저 할 작업

다음 세션은 기능 분석을 다시 하지 말고 아래 작업부터 시작한다.

```text
UI-00 baseline 및 reuse/license register
→ UI-01 tokens/primitives
→ UI-02 global shell
→ UI-03 Dashboard shell/parameter rail
→ UI-04 board/table/chart chrome
```

첫 세션의 실질적 목표는 **Dashboard 화면 하나를 현재 screenshot과 비교했을 때 명백히 다른 제품처럼 보일 정도로 바꾸는 것**이다.

Analysis, Ontology, Dataset, Agent를 조금씩 동시에 건드리지 않는다. 공통 shell과 Dashboard를 먼저 완결한 뒤 동일 primitive를 다른 Workbench로 전파한다.
