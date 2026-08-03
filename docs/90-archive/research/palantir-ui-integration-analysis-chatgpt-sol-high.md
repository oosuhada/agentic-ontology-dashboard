# Palantir Contour/Foundry UI 통합 상세 분석서 — ChatGPT SOL High

> **문서 상태:** 완성본  
> **작성일:** 2026-08-01  
> **대상 프로젝트:** `mvp-프로젝트2`  
> **목적:** 기존 Ontology Dashboard에 Palantir Contour/Foundry 스타일의 분석·대시보드 경험을 접목하기 위한 코드 기반 상세 분석 및 설계 제안  
> **작업 범위:** 읽기·분석·설계만 수행하며 기존 코드와 설정은 수정하지 않음  
> **근거:** 현재 MVP 소스 코드, `docs/40-ui-ux/reference/palantir-contour-ui-reference.md`, 로컬 레퍼런스 프로젝트 7개

---

## 목차

1. [Executive Summary](#0-executive-summary)
2. [현재 MVP의 구현 기능과 실제 부족 기능](#1-현재-mvp의-구현-기능과-실제-부족-기능)
3. [레퍼런스 7개 상세 비교](#2-레퍼런스-7개-상세-비교)
4. [Palantir Contour에 근접한 목표 화면 구조](#3-palantir-contour에-근접한-목표-화면-구조)
5. [DashboardShell과 BoardCanvas 구조 전환](#4-dashboardshell과-boardcanvas-구조-전환)
6. [보드·데이터·상태 계약 설계](#5-보드데이터상태-계약-설계)
7. [Frontend와 FastAPI API 계약](#6-frontend와-fastapi-api-계약)
8. [ASCII Wireframe과 컴포넌트 트리](#7-ascii-wireframe과-컴포넌트-트리)
9. [기술 선택 판단](#8-기술-선택-판단)
10. [P0/P1/P2 구현 로드맵](#9-p0p1p2-구현-로드맵)
11. [현실적인 제품 범위](#10-현실적인-제품-범위)
12. [최종 권고](#11-최종-권고)
13. [부록](#부록-a-검토-파일-경로)

---

# 0. Executive Summary

현재 `mvp-프로젝트2`는 단순한 카드형 Dashboard 수준을 이미 넘어섰다. 역할별 Dashboard Template, 개인 Preference, Saved View, 공유 링크, PDF/CSV/JSON Export, Board Catalog, 좌측 Context Panel, 우측 Inspector, Evidence/Action/Audit 흐름이 구현되어 있다.

즉, 현재 MVP의 강점은 다음과 같다.

```text
Object Context
  → Evidence
  → Recommendation
  → Governed Action
  → Audit
```

반대로 현재 MVP에서 Palantir Contour와 비교해 가장 부족한 것은 **분석 경로와 범용 데이터 실행 계층**이다.

현재 Dashboard Board는 대부분 다음 두 형태다.

1. 기존 `Layout/UIBlock`을 감싸서 표시하는 legacy renderer
2. 역할별 API 결과를 하드코딩된 React 컴포넌트로 표시하는 role renderer

따라서 현재 구조에는 아래 개념이 없다.

- 입력 데이터 또는 Object Set 선택
- Filter → Expression → Group → Aggregate → Chart 순차 경로
- 단계별 입력·출력 스키마
- 단계별 row count, null rate, duplicate, elapsed time 검증
- Analysis Run과 버전
- Chart click/brush가 실제 query를 다시 실행하는 교차 필터
- Dashboard Board가 versioned Analysis output을 참조하는 계약

가장 현실적인 목표는 Palantir 전체를 복제하는 것이 아니라 다음 경험을 구현하는 것이다.

```text
Prediction Result 또는 RiskEvent Object Set
  → Filter
  → Group/Aggregate
  → Chart
  → Result Table 검증
  → Equipment/RiskEvent 선택
  → Evidence 확인
  → Maintenance Action 실행
  → Audit 재구성
```

이를 위해 권장하는 기술 조합은 다음과 같다.

| 역할 | 기술 |
|---|---|
| Dashboard 배치 | React Grid Layout |
| Chart와 interaction | Apache ECharts |
| 검증용 고밀도 Table | TanStack Table |
| Object/Lineage Graph | React Flow |
| 편집 UI primitive | Blueprint 선택 도입 |

핵심 구조 결정은 다음과 같다.

1. `/app/analysis/:analysisId`와 `/app/dashboard/:dashboardId`를 분리한다.
2. Dashboard는 자유 배치 `x/y/w/h` 12열 Grid로 전환한다.
3. Analysis는 자유 배치 Grid가 아니라 세로 Path 또는 제한된 DAG로 구성한다.
4. Dashboard Board는 query를 중복 저장하지 않고 Analysis output 또는 Object Query를 참조한다.
5. ECharts의 library-specific option을 저장하지 않고, library-neutral `RenderSpec`을 저장한다.
6. 모든 Chart는 같은 `BoardResultContract`를 통해 Table 검증이 가능해야 한다.
7. Evidence와 Action은 일반 BI renderer가 아니라 현재 MVP의 governed workflow를 유지한다.
8. Superset, Cube, AG Grid Enterprise는 현재 핵심 구조에 도입하지 않는다.

---

# 1. 현재 MVP의 구현 기능과 실제 부족 기능

## 1.1 현재 MVP에 이미 있는 Palantir/Contour 유사 기능

| 기능 | 근거 파일 | 현재 구조 | 평가 |
|---|---|---|---|
| Project/Workspace Context | `web/src/features/dashboard/DashboardShell.tsx` | 상단 Project 및 Workspace selector | Foundry의 resource context와 유사한 기반이 이미 존재 |
| 역할별 Dashboard | `DashboardShell.tsx`, `ManufacturingApp.tsx` | 역할 banner, focus, role template | 현장·관리자·FDE 역할 분리에 적합 |
| Dashboard Tab | `DashboardShell.tsx`, `utils.ts` | tab 선택, drag reorder, 새 tab | Dashboard 소비 구조의 기본 기능 완성 |
| View/Edit 모드 | `DashboardShell.tsx` | View/Edit switch, edit에서 Inspector와 Catalog 표시 | 소비와 편집 분리 기반 존재 |
| 좌측 Context Rail | `ContextPanel.tsx` | Object Context, Parameter, Risk Event, Saved View | Palantir Dashboard parameter rail과 유사 |
| 중앙 Board Canvas | `BoardCanvas.tsx` | 12열 CSS Grid, width 4/6/12 | 형태는 있으나 자유 배치는 미완성 |
| 우측 Board Inspector | `BoardInspector.tsx` | 제목, 폭, 탭, 숨김, bindings, accepts/emits | 편집 UI 골격은 이미 적절 |
| Board Catalog | `BoardCatalogPanel.tsx` | 검색, category, 역할 필터, 대상 tab | Registry 기반 확장에 좋은 기반 |
| Board Definition | `web/src/features/dashboard/types.ts`, `dashboard_models.py` | renderer, allowed roles, object types, accepts, emits | 선언형 Registry로 발전 가능 |
| Parameter Definition | frontend/backend `DashboardParameterDefinition` | value type, scope, default, options | Analysis parameter에도 재사용 가능 |
| Dependency Graph 개념 | `dashboard_service.py::_dependency_graph()` | emits와 accepts 교집합으로 edge 생성 | 표시용 graph는 있으나 실행 graph는 아님 |
| Affected Board 표시 | `ManufacturingApp.tsx`, `utils.ts` | parameter 변경 시 affected board highlight | Cross-filter UX의 초기 형태 |
| Saved View | dashboard repository/API, `ContextPanel.tsx` | tabs와 parameter state 저장 | 개인화 기능 강점 |
| Share Link | `/api/dashboards/shares` | token, expiry, workspace 검증 | 권한 우회 없는 공유 방향이 적절 |
| PDF/CSV/JSON Export | `DashboardShell.tsx`, export API | export와 audit checkpoint | 보고와 감사 요구 기반 존재 |
| Role Template Version | dashboard repository/service | publish, preview, revision, request | FDE/Admin 운영 모델과 잘 맞음 |
| Evidence/Action/Audit | `DashboardBoardRenderer.tsx`, role workspace API | Evidence, action form, audit trace | 일반 BI와 구분되는 핵심 경쟁력 |
| Object/Link/Action Ontology | API ontology 모듈 | object query, link traverse, action invoke | Palantir급 운영 경험의 핵심 기반 |
| 반응형 화면 | `web/src/styles.css` | desktop/tablet/mobile layout | 현장용 화면 확장 가능 |

## 1.2 현재 MVP의 실제 부족 기능

| 부족 기능 | 현재 상태 | 관련 파일 | 필요한 변화 |
|---|---|---|---|
| Analysis 전용 route | 없음 | `web/src/App.tsx`, `web/src/routing.ts` | `/app/analysis/:analysisId` 추가 |
| Dashboard ID 중심 route | `/app/*`가 `ManufacturingApp`로 통합 | `App.tsx` | `/app/dashboard/:dashboardId`를 1급 route로 승격 |
| Analysis Path | 없음 | dashboard feature 전체 | Filter/Group/Aggregate/Chart 세로 경로 추가 |
| 실제 데이터 실행 | Board가 공통 query/result 계약을 사용하지 않음 | `DashboardBoardRenderer.tsx` | FastAPI Analysis Run 및 Dashboard Query Batch 필요 |
| 자유 Grid | `width`와 `order`만 존재 | `types.ts`, `dashboard_models.py` | `x/y/w/h` 및 responsive layout 추가 |
| Resize/Collision/Packing | 없음 | `BoardCanvas.tsx` | React Grid Layout 도입 |
| Typed Data Binding | 문자열 input | `BoardInspector.tsx` | source별 Binding Editor 필요 |
| Render Spec | renderer string + 임의 settings | `DashboardBoardRenderer.tsx` | versioned discriminated `RenderSpec` 필요 |
| 범용 Chart | 실제 chart library 없음 | `web/package.json` | ECharts renderer 필요 |
| Chart selection 실행 | highlight만 수행 | `showAffected()`, `affectedBoardIds()` | selection → query invalidation → batch rerun 필요 |
| 고밀도 Result Table | generic verification table 없음 | renderer 계층 | TanStack Table 추가 |
| Result Profile | row/schema/null/duplicate/runtime 미표시 | Inspector | `BoardResultContract.profile` 필요 |
| Data Version/Freshness | UI 노출 없음 | 전체 | source version, generated_at, freshness_at 표시 |
| Analysis Run Audit | 없음 | API/DB | `analysis_runs`, `analysis_board_runs` 필요 |
| Object/Lineage Graph | 텍스트 trace만 존재 | `AuditTrace` renderer | React Flow 기반 graph 필요 |
| Explicit Dependency Mapping | parameter 이름 교집합으로 자동 연결 | `_dependency_graph()` | source field → target field 명시 계약 필요 |
| Dependency Transitive Traversal | direct edge만 조회 | `utils.ts::affectedBoardIds()` | DAG traversal 및 cycle validation 필요 |
| Undo/Redo | 없음 | `useDashboardEditor.ts` | draft history 또는 command stack 필요 |
| Query Scope Governance | raw SQL 실행 contract 없음 | API 전체 | curated query plan 또는 Analysis compiler 필요 |

## 1.3 현재 구조의 핵심 진단

### Dashboard shell은 강하지만 분석 엔진은 없다

현재 화면은 역할별 운영 Dashboard로는 완성도가 높다. 이를 폐기하고 다른 BI를 embed하는 것은 손실이 크다.

권장 방향은 다음이다.

```text
기존 유지
- role template
- personal preference
- Evidence
- Action
- Audit
- Saved View
- Share
- Export

신규 추가
- Analysis Definition
- Analysis Run
- Board Result Contract
- Generic Chart/Table renderer
- Grid Layout V2
- Explicit dependency graph
```

### 현재 dependency graph는 실행 그래프가 아니다

현재 backend는 board definition의 `emits`와 `accepts`를 비교해 edge를 생성한다.

이 방식은 다음 질문에 답하지 못한다.

- source board의 어떤 field가 target의 어떤 parameter에 연결되는가
- selection은 `replace`, `add`, `toggle` 중 무엇인가
- tab 범위인가 dashboard 범위인가
- target board query를 재실행하는가, UI 선택만 바꾸는가
- cycle이 있는가
- selection을 Saved View에 저장할 것인가

따라서 현재 graph는 추천용 metadata로 유지하고, 실행용 graph는 명시적 contract로 별도 저장해야 한다.

---

# 2. 레퍼런스 7개 상세 비교

## 2.1 종합 비교표

| 레퍼런스 | 핵심 파일 | UI takeaway | 데이터/상태 모델 takeaway | MVP에 적용할 정확한 위치 | 직접 재사용 가능 여부 | 라이선스/코드 복사 주의점 |
|---|---|---|---|---|---|---|
| `mini_foundry_public` | `frontend/components/dashboards/DashboardCanvas.tsx`, `DataBindingPanel.tsx`, `FilterBar.tsx`, `ontology/OntologyGraph.tsx` | React Grid Layout 12열 drag/resize, binding panel, filter bar, React Flow graph | component position `x/y/w/h`, binding union, graph node/edge 및 position persistence | `BoardCanvas.tsx` 대체, `BoardInspector.tsx` Binding tab, 신규 graph feature | 부분 가능 | MIT. 저작권 고지 유지. Next.js/Tailwind/API 경로는 그대로 복사하지 않음 |
| `openfoundry-emulator` | `Contour.tsx`, `Canvas.tsx`, `widget-registry.ts`, `page-store.ts` | 세로 Analysis step, step 사이 add connector, Workshop canvas, preview mode | `WidgetTypeDef`, config schema, default size, `WidgetInstance.position` | 신규 `AnalysisCanvas.tsx`, board registry 확장 | 부분 가능 | Apache-2.0. client-side pipeline, `any`, localStorage, HTML widget은 그대로 사용 금지 |
| `contour-translation` | `contour_translator.py`, `contour_render_specs.py` | UI보다 normalized render spec 구조가 핵심 | `render_spec_kind`, `is_renderable`, raw state 보존, unsupported/error 안전 처리 | 신규 `render_specs.py`, frontend render-spec types | 개념과 일부 helper 가능 | MIT. Foundry 내부 state/PAT/RID 가정 제거 필요 |
| `palantir-blueprint` | `packages/core`, `icons`, `select`, `datetime`, `table` | 고밀도 업무 UI primitive와 iconography | controlled primitive, form/accessibility pattern | Analysis/Dashboard toolbar, inspector, dialog, menu | npm package 직접 사용 | Apache-2.0. source copy보다 package dependency 사용 |
| `OpenFoundry` | `DashboardGrid.svelte`, `WidgetFactory.svelte`, `WidgetConfig.svelte`, `lib/utils/dashboards.ts` | chart/table/KPI factory, 상세 widget config | widget discriminated union, query/layout 분리 | renderer host 분해, widget config 설계 | 설계 참고 | package/README는 Apache-2.0이나 로컬 LICENSE가 비어 있어 upstream 재확인 전 복사 금지 |
| `palantir-demo` | `Dashboard.jsx`, `GlobeComponent.jsx`, `EventDetailModal.jsx` | command center density, layer toggle, detail modal, responsive menu | selected event와 layer state orchestration | Evidence/Action drawer 및 alert feed의 시각 참고 | 직접 재사용 금지 | LICENSE 미명시. 코드·asset 복사 금지 |
| `Gods_Eye` | `useStore.js`, `timeStore.js`, `LayerControls.jsx`, `Timeline.jsx`, architecture docs | layer panel, selection, timeline/replay, freshness honesty | selection store와 time/snapshot store 분리 | P2 timeline/freshness/map layer state | 직접 재사용 금지 | GPL-3.0. clean-room 독립 구현만 허용 |

## 2.2 `mini_foundry_public`

### 가져올 내용

`DashboardCanvas.tsx`의 핵심 구조는 다음과 같다.

```text
DashboardComponent.position
  → React Grid Layout Layout[]
  → drag/resize
  → onLayoutChange
  → position map persistence
```

MVP 적용 위치:

```text
web/src/features/dashboard/BoardCanvas.tsx
  → web/src/features/dashboard/DashboardGridCanvas.tsx
```

보완 사항:

- `ResizeObserver` 또는 React Grid Layout container width hook 사용
- `onDragStop`과 `onResizeStop`에서만 draft 저장
- chart/table interaction 영역은 `draggableCancel` 지정
- responsive breakpoint layout 저장
- role template layout과 personal override 분리

`DataBindingPanel.tsx`에서 가져올 것은 SQL editor가 아니라 **binding kind를 구분하는 방식**이다.

권장 binding kind:

```text
analysis_output
object_set
prediction_result
role_workspace_query
dataset_manifest
static_text
```

`OntologyGraph.tsx`의 custom React Flow node, MiniMap, Controls, position persistence 패턴은 P2 graph에 적합하다.

## 2.3 `openfoundry-emulator`

`Contour.tsx`에서 가장 중요한 것은 세로 분석 흐름이다.

```text
Input
  ↓
Filter
  ↓
Group By
  ↓
Aggregate
  ↓
Chart 또는 Table
```

각 단계 사이에 Add connector를 두고, 각 Board가 설정과 결과를 함께 표시한다.

현재 레퍼런스는 브라우저 배열을 순회해 계산하지만 MVP에서는 다음으로 변경한다.

```text
AnalysisDefinition
  → POST /api/analyses/{id}/runs
  → server scope validation
  → board execution
  → board result/profile
  → UI preview
```

`widget-registry.ts`의 장점:

- type identity
- default config
- default size
- config schema
- instance config와 position 분리

그대로 사용하지 않을 부분:

- raw HTML Text Widget
- arbitrary URL button
- localStorage persistence
- 수동 pointer drag 구현
- client-only transform execution

## 2.4 `contour-translation`

가장 중요한 원칙은 Authoring Config와 Compiled Render Spec을 분리하는 것이다.

```text
Authoring Config
- 사용자가 편집하는 field, aggregation, chart 설정

Compiled Render Spec
- renderer가 소비하는 versioned normalized spec
```

또한 지원하지 않는 Board가 전체 Analysis를 깨뜨리지 않도록 한다.

```json
{
  "status": "unsupported",
  "board_id": "board-123",
  "renderer_id": "unknown",
  "message": "지원되지 않는 render spec version",
  "raw_config": {}
}
```

## 2.5 Blueprint

권장 도입 범위:

- Button, ButtonGroup
- Tabs
- Menu, Popover
- Dialog, Drawer
- Callout, Tag, Spinner, Tooltip
- FormGroup, InputGroup, NumericInput, Switch
- Select 및 date/time controls
- icons

초기 비권장:

- 전체 CSS theme 교체
- admin/login/mobile 화면 동시 migration
- 기존 모든 Table을 Blueprint Table로 교체

Blueprint는 **Palantir처럼 보이게 하는 장식**보다 고밀도 편집 UI의 접근성과 일관성을 위해 도입한다.

## 2.6 `OpenFoundry`

참고할 분리:

```text
DashboardWidget
  ├─ layout
  ├─ query/data binding
  └─ visualization config

WidgetFactory
  ├─ result request
  └─ renderer dispatch
```

채택하지 않을 부분:

- raw SQL string template
- client-side localStorage dashboard store
- Svelte-specific state model

현재 MVP에서는 서버가 registered query plan 또는 validated Analysis Definition을 compile해야 한다.

## 2.7 `palantir-demo`

적용할 것은 3D globe가 아니라 다음 interaction pattern이다.

- 중앙 primary visualization
- 주변 status/feed/detail panel
- selected event detail modal 또는 drawer
- mobile에서 controls를 접는 방식
- live/freshness 상태 강조

제조 vertical에서는 globe 대신 다음으로 치환한다.

- 공장 또는 라인 topology
- Equipment risk list
- RiskEvent feed
- Evidence/Action detail drawer

## 2.8 `Gods_Eye`

중요한 takeaway는 replay와 freshness를 정직하게 표시하는 것이다.

| 데이터 | replay capability |
|---|---|
| Sensor trend | full historical replay |
| Prediction result | versioned snapshot replay |
| Adapter health | current-only |
| Camera/photo | captured-at snapshot |
| Maintenance action | immutable event history |

UI는 모든 Board가 동일하게 실시간 또는 replay 가능하다고 표현하면 안 된다.

---

# 3. Palantir Contour에 근접한 목표 화면 구조

## 3.1 전체 정보 구조

```text
Ontology Dashboard
├─ /app/projects/:projectId
├─ /app/analysis/:analysisId
├─ /app/dashboard/:dashboardId
├─ /app/objects/:objectType/:objectId
├─ /app/lineage/:resourceId
└─ /admin
```

## 3.2 Analysis 편집 화면

### 목적

- 어떤 source에서 출발했는지 명확히 한다.
- 데이터 변환 단계와 시각화 단계를 분리한다.
- 각 단계 결과를 검증한다.
- Dashboard에 publish할 output을 명시한다.

### 좌측 Rail

```text
Data Sources
- Object Set
- Prediction Result Contract
- Dataset Manifest
- Saved Analysis Output

Transform Boards
- Filter
- Derive
- Group
- Aggregate
- Sort
- Join(P2)

Inspect Boards
- Table
- Profile
- Details

Visual Boards
- Chart
- Histogram
- Timeseries
- Metric

Parameters
- date range
- line
- failure type
- severity
- risk threshold
- model version
```

### 중앙 Canvas

- 세로 Analysis Path
- Input Board
- 각 단계 header
- row count 및 runtime
- 설정 요약
- result preview
- 단계 사이 Add connector
- blocked/failed/unsupported state
- Output Port

### 우측 Inspector

- Board Config
- Field Mapping
- Input Schema
- Output Schema
- Parameter Binding
- Result Profile
- Lineage
- Validation Error

## 3.3 Dashboard 소비 화면

### 좌측 Rail

View 모드:

- Object Context
- Parameters
- Active Selections
- Saved Views

Edit 모드:

- 위 항목 유지
- Board Catalog entry
- layout breakpoint switch

### 중앙 Canvas

- 12열 `x/y/w/h`
- Chart, Table, Metric
- Evidence, Action
- Text, Object Context
- Graph
- fullscreen/focus mode
- loading/error/stale/freshness

### 우측 Panel

```text
Edit mode → Board Inspector
View mode → Object/Evidence/Action Detail Drawer
```

두 panel을 동시에 노출하지 않고 `RightPanelHost`가 mode를 관리한다.

## 3.4 Board Catalog

Board Catalog item은 단순 renderer 목록이 아니라 다음 contract를 가진다.

```text
Board Definition
├─ identity/version
├─ surface: analysis/dashboard/both
├─ category
├─ allowed roles/permissions
├─ accepted input kinds
├─ output kind
├─ emitted selection kinds
├─ config schema
├─ default config
├─ default layout
├─ renderer id
├─ query compiler id
└─ capabilities
```

Catalog UX:

- Suggested
- Compatible
- Transform
- Visualize
- Operate
- Audit
- Incompatible with reason

## 3.5 Parameter와 Selection Filter 분리

| 구분 | 예 | 저장 | 공유 | 적용 범위 |
|---|---|---|---|---|
| Parameter | date range, threshold, model version | 가능 | 가능 | dashboard/tab/board |
| Selection Filter | chart bar click, brush range | 기본 transient | 선택적 | dependency graph |
| Object Context | selected equipment/risk event | 가능 | 권한 재평가 | dashboard 전역 |

지원 control:

- single select
- multi select
- date range
- datetime range
- numeric range
- boolean
- object selector
- enum/status
- model/policy version

## 3.6 Chart-to-chart Filtering

ECharts raw event를 직접 persistence하지 않는다.

```ts
interface SelectionFilter {
  id: string;
  source_board_id: string;
  field: string;
  operator: "eq" | "in" | "between";
  values: unknown[];
  combine: "replace" | "add" | "toggle";
  scope: "tab" | "dashboard";
  transient: boolean;
}
```

실행 흐름:

```text
ECharts click/brush
  → EChartsSelectionAdapter
  → SelectionFilter
  → dependency graph traversal
  → affected query key invalidation
  → POST dashboard query batch
  → chart/table/object context update
  → Active Selection chips 표시
```

규칙:

- source self-filter 여부는 Board Definition에서 결정
- Shift/Ctrl은 add/toggle로 정규화
- clear one / clear all 지원
- Saved View 포함 시 transient를 persistent로 승격
- PDF에 active selection summary 포함

## 3.7 Table Result Verification

모든 Chart Board가 제공해야 할 action:

- View Data
- Open Verification Table
- Show Lineage
- Show Profile
- Export Filtered Rows

TanStack Table 요구사항:

- server pagination/cursor
- sort/filter API 전달
- column pinning
- column resizing
- column visibility
- schema type badge
- null/invalid 표시
- selected row → Object Context
- current scope 재검증 후 CSV export
- 전체 대용량 dataset을 브라우저에 전달하지 않음

## 3.8 Evidence와 Action Drill-down

```text
Chart/Table Selection
  → RiskEvent Object
  → Prediction Result Contract
  → Evidence Bundle
  → Recommended Action
  → Permission Check
  → Action Form
  → Action Invocation ID
  → Audit Timeline
```

현재 role board와 action API를 재사용하되, generic chart renderer 안에 Action form을 넣지 않는다.

## 3.9 Saved View, Share, PDF Snapshot

### Saved View

```text
- dashboard version
- active tab
- parameter state
- persistent selections
- selected object reference
- panel state
- optional personal layout override
```

### Share

```text
- dashboard/analysis resource id
- version
- view state
- expiration
- scope context
- server-side permission re-evaluation
```

### PDF Snapshot

```text
- snapshot id
- generated_at
- dashboard/analysis version
- parameters
- selections
- data freshness
- evidence/action references
- audit hash/checkpoint
```

## 3.10 Object와 Lineage Graph

Graph mode를 분리한다.

1. Ontology Graph
2. Analysis Lineage
3. Decision Lineage

한 graph에 세 종류를 모두 섞지 않는다.

---

# 4. DashboardShell과 BoardCanvas 구조 전환

## 4.1 `DashboardShell.tsx`의 현재 한계

현재 한 컴포넌트가 다음 책임을 가진다.

- global header
- project/workspace selector
- role banner
- tabs
- view/edit controls
- export/share/save
- template publish
- panel layout
- footer

Analysis와 ID 기반 Dashboard route를 추가하면 props가 더 비대해진다.

### 권장 분해

```text
web/src/layout/
├─ ApplicationChrome.tsx
├─ ProjectWorkspaceSwitcher.tsx
├─ ResourceHeader.tsx
├─ ResourceToolbar.tsx
├─ LeftRail.tsx
└─ RightPanelHost.tsx

web/src/features/dashboard/
├─ DashboardRoute.tsx
├─ DashboardShell.tsx
├─ DashboardToolbar.tsx
├─ DashboardTabBar.tsx
├─ DashboardGridCanvas.tsx
├─ DashboardParameterRail.tsx
└─ DashboardBoardInspector.tsx

web/src/features/analysis/
├─ AnalysisRoute.tsx
├─ AnalysisShell.tsx
├─ AnalysisToolbar.tsx
├─ AnalysisSourceRail.tsx
├─ AnalysisCanvas.tsx
└─ AnalysisBoardInspector.tsx
```

`ApplicationChrome`는 Project/Workspace/User navigation만 담당한다.

## 4.2 `BoardCanvas.tsx`의 현재 한계

- `gridColumn: span width`
- DOM order 기반 auto placement
- 높이 없음
- resize 없음
- collision/packing 없음
- native drag/drop이 chart/table interaction과 충돌 가능
- mobile에서 전부 span 12로만 처리
- drag 중 persistence transaction 경계 없음

## 4.3 새 Layout Type

```ts
export interface GridPosition {
  x: number;
  y: number;
  w: number;
  h: number;
  min_w?: number;
  min_h?: number;
  max_w?: number;
  max_h?: number;
  static?: boolean;
}

export interface ResponsiveBoardLayout {
  lg: GridPosition;
  md?: GridPosition;
  sm?: GridPosition;
}
```

## 4.4 `width/order`에서 `x/y/w/h`로 전환

### 기존

```ts
interface DashboardBoard {
  width: 4 | 6 | 12;
  order: number;
}
```

### 변경

```ts
interface DashboardBoard {
  layout: ResponsiveBoardLayout;
  order: number;
}
```

`order`는 keyboard navigation, accessibility order, fallback layout에만 사용한다.

### Legacy Migration Algorithm

```text
boards = order 오름차순
cursorX = 0
cursorY = 0
rowHeight = definition.default_h 또는 4

for board:
  w = legacy width
  h = definition.default_h

  if cursorX + w > 12:
    cursorX = 0
    cursorY = 다음 빈 row

  layout.lg = {x: cursorX, y: cursorY, w, h}
  cursorX += w
```

Migration 규칙:

- `layout_schema_version: 2`
- old payload read 시 adapter가 v2 생성
- 최초 저장 시 v2 persistence
- transition 동안 `width/order` read compatibility 유지
- new authoring source of truth는 `layout`
- mandatory board는 minimum size를 registry가 제공
- role template layout과 personal override 병합

## 4.5 React Grid Layout 적용

- 12 columns
- fixed row unit
- edit에서만 drag/resize
- view에서 static
- `onDragStop`, `onResizeStop`에서 draft update
- chart/table control은 drag cancel
- breakpoint별 layout
- collision/compact 정책은 dashboard definition에 저장
- layout update에 base revision 포함

## 4.6 Dashboard와 Analysis 분리

| 항목 | Analysis | Dashboard |
|---|---|---|
| 목적 | 데이터 변환·검증 | 결과 소비·운영 행동 |
| 배치 | 세로 path/제한 DAG | 자유 12열 grid |
| Board | source/filter/derive/group/aggregate/sort/table/chart | chart/table/metric/evidence/action/text/graph |
| 실행 | Analysis Run | Query Batch |
| 저장 | Analysis Version | Dashboard Version/Saved View |
| 주요 역할 | FDE, Data Scientist, Engineer | 전체 역할 |
| 결과 | Output Port | Board Binding |

Dashboard에서는 Join/Expression/Aggregate 정의를 수정하지 않는다.

---

# 5. 보드·데이터·상태 계약 설계

## 5.1 Board Definition Registry

```ts
export interface BoardDefinition {
  id: string;
  version: number;
  display_name: string;
  description: string;
  surface: "analysis" | "dashboard" | "both";
  category: "source" | "transform" | "inspect" | "visualize" | "operate" | "audit";

  accepted_input_kinds: BoardDataKind[];
  output_kind: BoardDataKind | null;
  emitted_selection_kinds: string[];
  accepted_parameter_kinds: string[];

  config_schema: JsonSchema;
  default_config: Record<string, unknown>;
  default_layout?: GridPosition;

  renderer_id: string;
  query_compiler_id?: string;
  allowed_roles: AppRole[];
  required_permissions: string[];

  capabilities: {
    selectable: boolean;
    exportable: boolean;
    fullscreen: boolean;
    supports_verification_table: boolean;
    supports_snapshot: boolean;
  };
}
```

## 5.2 Data Binding Contract

```ts
export type DataBinding =
  | {
      kind: "analysis_output";
      analysis_id: string;
      analysis_version: number;
      output_port: string;
    }
  | {
      kind: "object_set";
      object_type: string;
      object_set_query_id: string;
      projection: string[];
    }
  | {
      kind: "prediction_result";
      contract_version: string;
      result_set_id: string;
      projection: string[];
    }
  | {
      kind: "dataset_manifest";
      dataset_manifest_id: string;
      version: string;
      projection: string[];
    }
  | {
      kind: "role_workspace_query";
      query_id: string;
      projection: string[];
    };
```

원칙:

- Project는 binding source가 아니다.
- Project는 scope boundary다.
- raw SQL은 기본 binding으로 제공하지 않는다.
- Dataset Manifest는 FDE/Data Scientist 제한
- Prediction 결과는 versioned Result Contract로만 노출
- request body의 scope를 신뢰하지 않고 principal scope를 재검증

## 5.3 Render Spec Contract

ECharts `option`을 그대로 저장하지 않는다.

```ts
export type RenderSpec =
  | ChartRenderSpec
  | TableRenderSpec
  | MetricRenderSpec
  | TextRenderSpec
  | EvidenceRenderSpec
  | ActionRenderSpec
  | GraphRenderSpec;

export interface ChartRenderSpec {
  schema_version: "1.0";
  kind: "chart";
  chart_type: "line" | "bar" | "area" | "scatter" | "pie" | "histogram";
  encodings: {
    x?: FieldEncoding;
    y?: FieldEncoding | FieldEncoding[];
    color?: FieldEncoding;
    size?: FieldEncoding;
    tooltip?: FieldEncoding[];
  };
  interactions: {
    click_select?: boolean;
    brush_x?: boolean;
    brush_y?: boolean;
    multi_select?: boolean;
  };
  display: {
    legend?: boolean;
    stacked?: boolean;
    smooth?: boolean;
    value_format?: string;
  };
}
```

장점:

- renderer 교체 가능
- supported option whitelist
- PDF/server renderer 재사용
- version migration 가능
- AI-generated spec 검증 가능

## 5.4 Board Result Contract

```ts
export interface BoardResultContract {
  board_id: string;
  run_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "blocked" | "stale";

  schema: ResultColumn[];
  rows: Record<string, unknown>[];

  row_page: {
    cursor: string | null;
    next_cursor: string | null;
    returned: number;
    total_estimate: number | null;
  };

  aggregates: Record<string, unknown>[];
  profile: Record<string, ColumnProfile>;

  stats: {
    duration_ms: number;
    scanned_rows?: number;
    output_rows?: number;
    cache_hit: boolean;
  };

  lineage: ResourceReference[];
  object_refs: ObjectReference[];
  evidence_refs: string[];

  generated_at: string;
  source_freshness_at: string | null;
  error: { code: string; message: string } | null;
}
```

## 5.5 Dependency Graph Contract

```ts
export interface DependencyEdge {
  id: string;
  source: {
    board_id: string;
    port: string;
  };
  target: {
    board_id: string;
    port: string;
  };
  kind: "data" | "parameter" | "selection" | "object_context";
  mapping: Array<{
    source_field: string;
    target_field: string;
    operator: "eq" | "in" | "between";
  }>;
  propagation: "immediate" | "manual";
  scope: "tab" | "dashboard";
}
```

규칙:

- Analysis data edge는 cycle 금지
- Dashboard selection edge도 cycle validation
- self-filter는 별도 policy
- Catalog accepts/emits는 edge 추천에만 사용
- 최종 edge는 persisted definition에 저장

## 5.6 Parameter Binding Contract

```ts
export interface ParameterBinding {
  parameter_id: string;
  target_board_id: string;
  target_field: string;
  operator: "eq" | "in" | "gte" | "lte" | "between";
  required: boolean;
  fallback: "default" | "ignore" | "error";
}
```

## 5.7 Analysis Definition

```ts
export interface AnalysisDefinition {
  id: string;
  workspace_id: string;
  display_name: string;
  version: number;
  source: DataBinding;
  boards: AnalysisBoard[];
  edges: DependencyEdge[];
  parameters: DashboardParameterDefinition[];
  outputs: AnalysisOutputPort[];
}
```

## 5.8 Analysis Board

```ts
export interface AnalysisBoard {
  id: string;
  definition_id: string;
  title: string;
  config: Record<string, unknown>;
  input_ports: string[];
  output_ports: string[];
  parameter_bindings: ParameterBinding[];
  render_spec: RenderSpec | null;
  order: number;
}
```

---

# 6. Frontend와 FastAPI API 계약

## 6.1 Dashboard API

기존 API를 유지하면서 ID 기반 runtime API를 추가한다.

```text
GET    /api/dashboards/{dashboard_id}
POST   /api/dashboards
POST   /api/dashboards/{dashboard_id}/versions
PATCH  /api/dashboards/{dashboard_id}/layout
POST   /api/dashboards/{dashboard_id}/query-batches
POST   /api/dashboards/{dashboard_id}/snapshots
GET    /api/dashboards/{dashboard_id}/snapshots/{snapshot_id}
```

### Layout Patch

```json
{
  "base_revision": 12,
  "tab_id": "overview",
  "layouts": {
    "lg": {
      "risk-trend": { "x": 0, "y": 0, "w": 8, "h": 5 },
      "risk-table": { "x": 8, "y": 0, "w": 4, "h": 5 }
    }
  }
}
```

Conflict 시:

```text
HTTP 409
- current_revision
- current_layout
- conflict reason
```

### Query Batch

```json
{
  "dashboard_version": 4,
  "board_ids": ["risk-trend", "risk-table"],
  "parameters": {
    "date_range": ["2026-07-01", "2026-08-01"],
    "risk_status": ["high", "critical"]
  },
  "selections": [
    {
      "source_board_id": "risk-by-line",
      "field": "line_id",
      "operator": "in",
      "values": ["LINE-03"]
    }
  ],
  "result_limit": 500
}
```

Backend 책임:

- principal scope 검증
- dashboard/version permission
- binding resource scope 검증
- parameter/selection type validation
- query plan compilation
- batch execution/cache
- board별 result/error
- audit telemetry

## 6.2 Analysis API

```text
GET    /api/analyses/{analysis_id}
POST   /api/analyses
PUT    /api/analyses/{analysis_id}/draft
POST   /api/analyses/{analysis_id}/versions
POST   /api/analyses/{analysis_id}/validate
POST   /api/analyses/{analysis_id}/runs
GET    /api/analysis-runs/{run_id}
GET    /api/analysis-runs/{run_id}/boards/{board_id}/result
GET    /api/analysis-runs/{run_id}/boards/{board_id}/profile
POST   /api/analyses/{analysis_id}/outputs/{port}/publish
```

### Analysis Run Request

```json
{
  "analysis_version": 3,
  "parameters": {
    "date_from": "2026-07-01T00:00:00Z",
    "date_to": "2026-08-01T00:00:00Z"
  },
  "preview": true,
  "preview_limit": 500
}
```

## 6.3 신규 Backend 모듈 위치

```text
api/ontology_dashboard/
├─ routers/
│  ├─ analyses.py
│  ├─ dashboard_runtime.py
│  ├─ lineage.py
│  └─ snapshots.py
├─ analysis_models.py
├─ analysis_service.py
├─ analysis_repository.py
├─ analysis_executor.py
├─ analysis_validation.py
├─ query_models.py
├─ query_service.py
├─ board_registry.py
├─ render_specs.py
├─ lineage_service.py
└─ snapshot_service.py
```

현재 `api/factory_signal_board/dashboard_*`는 즉시 이동하지 않는다.

신규 기능은 canonical namespace인 `ontology_dashboard`에 추가하고, 기존 service는 adapter/facade로 점진적으로 흡수한다.

## 6.4 DB 모델

### 기존 활용

- `dashboard_templates`
- `dashboard_template_versions`
- `dashboard_user_preferences`
- `dashboard_saved_views`
- `dashboard_shares`

P0에서는 Dashboard 본체 테이블을 중복 생성하지 않는다.

- payload에 `schema_version`
- responsive layout
- data binding
- render spec
- dependency graph
- personal layout override

### Analysis 신규 테이블

```text
analyses
- id
- organization_id
- project_id
- workspace_id
- display_name
- current_version
- created_by
- created_at
- updated_at

analysis_versions
- id
- analysis_id
- version
- status
- definition_json
- created_by
- created_at

analysis_runs
- id
- analysis_id
- analysis_version
- organization_id
- project_id
- workspace_id
- requested_by
- parameter_json
- status
- started_at
- finished_at
- error_json

analysis_board_runs
- id
- run_id
- board_id
- status
- input_snapshot_json
- result_schema_json
- result_location
- profile_json
- stats_json
- started_at
- finished_at

analysis_output_publications
- id
- analysis_id
- analysis_version
- output_port
- contract_json
- published_by
- published_at
```

대용량 row를 DB JSON에 직접 저장하지 않는다.

- preview sample만 제한 저장
- full result는 materialized table 또는 object storage location 기록

### P2

```text
dashboard_snapshots
resource_lineage_edges
resource_lineage_snapshots
```

Ontology domain link와 build/runtime lineage를 구분한다.

---

# 7. ASCII Wireframe과 컴포넌트 트리

## 7.1 `/app/analysis/:analysisId`

### ASCII Wireframe

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ OD  Project ▾  Workspace ▾   Analysis: Bearing Risk Root Cause   Draft v3   Run   Save   Publish │
├──────┬──────────────────────────────┬────────────────────────────────────────────────┬───────────────┤
│ NAV  │ SOURCE / BOARD CATALOG       │ ANALYSIS PATH                                  │ INSPECTOR     │
│      │                              │                                                │               │
│ ⌂    │ Data source                  │ ┌────────────────────────────────────────────┐ │ Step settings │
│ ◫    │ ● Prediction Result v2       │ │ INPUT  Prediction Result Contract v2      │ │               │
│ ◇    │ ○ Equipment Object Set       │ │ 12,480 rows · refreshed 18:41             │ │ Field mapping │
│ ⛓    │ ○ Dataset Manifest           │ └──────────────────────┬─────────────────────┘ │ Parameter bind│
│      │                              │                        │                       │               │
│      │ Transform                    │                  [+ Add step]                  │ Input schema  │
│      │ Filter                       │                        │                       │ Output schema │
│      │ Derive column                │ ┌──────────────────────▼─────────────────────┐ │               │
│      │ Group / Aggregate            │ │ 1  FILTER  status in high, critical       │ │ Result profile│
│      │ Sort                         │ │ 2,104 rows · 84 ms                        │ │ null/distinct │
│      │ Join (P2)                    │ │ [Preview table ▾]                          │ │               │
│      │                              │ └──────────────────────┬─────────────────────┘ │ Lineage       │
│      │ Inspect                      │                  [+ Add step]                  │ Validation    │
│      │ Table                        │                        │                       │               │
│      │ Profile                      │ ┌──────────────────────▼─────────────────────┐ │               │
│      │                              │ │ 2  AGGREGATE by equipment_id              │ │               │
│      │ Visualize                    │ │ max(risk_score), count(event_id)           │ │               │
│      │ Chart                        │ │ 318 rows · 63 ms                           │ │               │
│      │ Histogram                    │ └──────────────────────┬─────────────────────┘ │               │
│      │ Metric                       │                  [+ Add step]                  │               │
│      │                              │                        │                       │               │
│      │ Parameters                   │ ┌──────────────────────▼─────────────────────┐ │               │
│      │ date range                   │ │ 3  TABLE  Verification output             │ │               │
│      │ threshold                    │ │ [columns] [sort] [profile] [lineage]       │ │               │
│      │ model version                │ └────────────────────────────────────────────┘ │               │
├──────┴──────────────────────────────┴────────────────────────────────────────────────┴───────────────┤
│ Run 2026-08-01 18:44 · succeeded · 3 steps · input snapshot PR-2026-08-01-1841 · audit RUN-... │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Component Tree

```text
<AnalysisRoute>
└─ <ApplicationChrome>
   ├─ <ProjectWorkspaceSwitcher />
   ├─ <ResourceHeader resource="analysis" />
   └─ <AnalysisShell>
      ├─ <AnalysisToolbar>
      │  ├─ <VersionStatus />
      │  ├─ <RunAnalysisButton />
      │  ├─ <SaveDraftButton />
      │  └─ <PublishOutputMenu />
      ├─ <AnalysisWorkspace>
      │  ├─ <AnalysisSourceRail>
      │  │  ├─ <DataSourcePicker />
      │  │  ├─ <CompatibleBoardCatalog />
      │  │  ├─ <AnalysisOutline />
      │  │  └─ <ParameterEditor />
      │  ├─ <AnalysisCanvas>
      │  │  ├─ <AnalysisInputNode />
      │  │  ├─ <AnalysisBoardFrame>
      │  │  │  ├─ <BoardStatusHeader />
      │  │  │  ├─ <BoardConfigSummary />
      │  │  │  └─ <BoardResultPreview />
      │  │  ├─ <AddAnalysisBoardConnector />
      │  │  └─ <AnalysisOutputNode />
      │  └─ <AnalysisBoardInspector>
      │     ├─ <BoardConfigEditor />
      │     ├─ <FieldMappingEditor />
      │     ├─ <ParameterBindingEditor />
      │     ├─ <SchemaDiff />
      │     ├─ <ResultProfile />
      │     └─ <LineageSummary />
      └─ <AnalysisRunStatusBar />
```

## 7.2 `/app/dashboard/:dashboardId`

### ASCII Wireframe

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ OD  Project ▾ Workspace ▾  Predictive Maintenance Dashboard  Published v4  View/Edit  Share PDF │
├──────┬──────────────────────────────┬────────────────────────────────────────────────┬───────────────┤
│ NAV  │ CONTEXT / FILTERS            │  OVERVIEW   EVENTS   EVIDENCE                  │ DETAIL/DRAWER │
│      │                              │                                                │               │
│ ⌂    │ Object Context               │ ┌──────────────────────────────┬───────────────┐ │ Equipment     │
│ ◫    │ Pump P-104                   │ │ Critical Risk Trend          │ Critical Now  │ │ Pump P-104    │
│ ◇    │ Line 03                      │ │      ECharts line/brush      │ 18            │ │               │
│ ⛓    │ RiskEvent RE-882             │ │                              │ +4 today      │ │ Prediction    │
│      │                              │ └──────────────────────────────┴───────────────┘ │ Evidence      │
│      │ Parameters                   │                                                │               │
│      │ Date  Jul 1 — Aug 1          │ ┌──────────────────────┬───────────────────────┐ │ Recommended   │
│      │ Status high, critical        │ │ Risk by Line         │ Failure Mode Mix      │ │ Action        │
│      │ Model v12                    │ │ ECharts bar click    │ ECharts pie click     │ │               │
│      │                              │ └──────────────────────┴───────────────────────┘ │ [Create task] │
│      │ Active selections            │                                                │ [Acknowledge] │
│      │ × Line = 03                  │ ┌──────────────────────────────────────────────┐ │               │
│      │ × Mode = bearing             │ │ Result Verification Table                   │ │ Audit history │
│      │ [Clear all]                  │ │ Equipment | Score | Mode | Predicted At ... │ │               │
│      │                              │ │ pinned/sort/filter/paged                    │ │               │
│      │ Saved Views                  │ └──────────────────────────────────────────────┘ │               │
│      │ Shift Review                 │                                                │               │
├──────┴──────────────────────────────┴────────────────────────────────────────────────┴───────────────┤
│ Data freshness: sensor 18:46 · prediction 18:41 · maintenance 18:30 · active view: Shift Review │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Component Tree

```text
<DashboardRoute>
└─ <ApplicationChrome>
   ├─ <ProjectWorkspaceSwitcher />
   ├─ <ResourceHeader resource="dashboard" />
   └─ <DashboardShell>
      ├─ <DashboardToolbar>
      │  ├─ <ViewEditSwitch />
      │  ├─ <BoardCatalogButton />
      │  ├─ <SavedViewMenu />
      │  ├─ <ShareButton />
      │  ├─ <SnapshotExportMenu />
      │  └─ <TemplatePublishAction />
      ├─ <DashboardTabBar />
      ├─ <DashboardWorkspace>
      │  ├─ <DashboardParameterRail>
      │  │  ├─ <ObjectContextCard />
      │  │  ├─ <ParameterControls />
      │  │  ├─ <ActiveSelectionList />
      │  │  └─ <SavedViewList />
      │  ├─ <DashboardGridCanvas>
      │  │  └─ <DashboardBoardFrame>*
      │  │     ├─ <BoardFrameHeader />
      │  │     ├─ <BoardRuntimeState />
      │  │     └─ <BoardRendererHost>
      │  │        ├─ <EChartsBoard />
      │  │        ├─ <ResultTableBoard />
      │  │        ├─ <MetricBoard />
      │  │        ├─ <EvidenceBoard />
      │  │        ├─ <ActionBoard />
      │  │        └─ <GraphBoard />
      │  └─ <RightPanelHost>
      │     ├─ <DashboardBoardInspector />
      │     └─ <ObjectEvidenceActionDrawer />
      ├─ <BoardCatalogDrawer />
      └─ <DataFreshnessStatusBar />
```

---

# 8. 기술 선택 판단

## 8.1 분류

| 기술 | 결정 | 사용 범위 | 이유 |
|---|---|---|---|
| React Grid Layout | **지금 도입** | Dashboard layout | 현재 width/order 한계를 직접 해결 |
| Apache ECharts | **지금 도입** | Chart/Histogram/Timeseries | brush/click/selection과 산업용 chart 지원 |
| TanStack Table | **지금 도입** | Result Verification | headless, type-safe, 기존 CSS와 결합 용이 |
| Blueprint | **선택 도입** | Toolbar, Inspector, Dialog, Form | Palantir 계열 고밀도 UI primitive |
| React Flow | **P1 후반~P2** | Ontology/Lineage | graph interaction에 적합 |
| Vega-Lite | **나중에 검토** | declarative interchange | ECharts와 동시 운영할 필요가 아직 없음 |
| MapLibre GL JS | **나중에 검토** | 위치/공장 layer 요구 발생 시 | 현재 핵심 루프에는 필수 아님 |
| Superset | **별도 BI 대안만** | analyst BI/embed | 핵심 운영 화면과 상태/권한 중복 |
| Cube | **나중에 검토** | certified metric 확산 시 | 현재 ontology/query contract와 중복 가능 |
| AG Grid Enterprise | **도입하지 않음** | 없음 | 비용, license, 과도한 기능 |
| Cesium/react-globe.gl | **도입하지 않음** | 없음 | 제조 vertical 핵심 가치가 아님 |

## 8.2 권장 조합

```text
React Grid Layout = Dashboard 배치
ECharts           = Chart Rendering + Interaction
TanStack Table    = Result Verification
React Flow        = Graph/Lineage
Blueprint         = Editor Primitive
Product Contracts = Source of Truth
```

라이브러리 객체를 persistence contract로 저장하지 않는다.

- Grid Layout object → `GridPosition` adapter
- ECharts event → `SelectionFilter` adapter
- TanStack state → API page/sort/filter adapter
- React Flow state → domain graph adapter

## 8.3 AG Grid Enterprise를 도입하지 않는 이유

- 개발자 및 배포 범위에 따른 상용 비용
- license compliance 관리 필요
- 현재 필요한 sorting/filtering/pinning/resizing/pagination은 TanStack으로 가능
- integrated chart state가 ECharts/SelectionFilter와 중복
- 핵심 차별점은 spreadsheet가 아니라 Object/Evidence/Action 연결
- server-side row model이 실제 병목으로 확인되기 전 과도한 결합

## 8.4 Superset Embed를 핵심으로 쓰지 않는 이유

중복되는 것:

- auth/guest token
- row-level security
- filter state
- dashboard version
- saved view/share/export
- chart plugin
- Evidence/Action detail
- 별도 배포와 metadata DB

Superset은 향후 analyst self-service BI가 필요할 때 sidecar로 검토한다.

## 8.5 Cube를 지금 도입하지 않는 이유

현재 먼저 안정화할 것:

- Project/Workspace scope
- Dataset Manifest
- Object Set
- Prediction Result Contract
- Analysis Definition/Run
- Dashboard Data Binding
- Evidence/Action/Audit

Cube 재검토 조건:

- 동일 KPI가 여러 surface에서 반복
- warehouse query가 병목
- pre-aggregation 필요
- 외부 BI와 AI가 동일 certified metric 소비
- metric governance 팀과 CI workflow 존재

## 8.6 Vega-Lite와 MapLibre

### Vega-Lite

다음 요구가 생기면 검토:

- chart spec 외부 교환
- browser/PDF/server renderer 통일
- AI-generated chart spec

### MapLibre

다음 데이터가 실제 있을 때 검토:

- 여러 공장/사업장
- 설비 geometry
- line/area/route/heatmap
- 위치 기반 risk clustering

단일 공장 내부 관계 중심 topology는 React Flow 또는 SVG가 더 적합할 수 있다.

---

# 9. P0/P1/P2 구현 로드맵

## P0 — Dashboard Layout V2와 Generic Visualization Runtime

### 목표

기존 역할 Dashboard의 기능을 유지하면서 자유 Grid, generic Chart/Table, 실제 selection query를 도입한다.

### 변경 파일

```text
web/package.json
web/src/App.tsx
web/src/features/dashboard/types.ts
web/src/features/dashboard/DashboardShell.tsx
web/src/features/dashboard/BoardCanvas.tsx
web/src/features/dashboard/BoardInspector.tsx
web/src/features/dashboard/BoardCatalogPanel.tsx
web/src/features/dashboard/DashboardBoardRenderer.tsx
web/src/features/dashboard/utils.ts
web/src/features/manufacturing/ManufacturingApp.tsx
web/src/styles.css

api/factory_signal_board/dashboard_models.py
api/factory_signal_board/dashboard_service.py
schemas/dashboard-platform.schema.json
```

### 신규 파일

```text
web/src/layout/ApplicationChrome.tsx
web/src/features/dashboard/DashboardRoute.tsx
web/src/features/dashboard/DashboardGridCanvas.tsx
web/src/features/dashboard/board-registry.ts
web/src/features/dashboard/layout-migration.ts
web/src/features/dashboard/selection-model.ts
web/src/features/dashboard/render-spec.ts
web/src/features/dashboard/BindingEditor.tsx
web/src/features/dashboard/ParameterControl.tsx
web/src/features/dashboard/renderers/EChartsBoard.tsx
web/src/features/dashboard/renderers/ResultTableBoard.tsx

api/ontology_dashboard/routers/dashboard_runtime.py
api/ontology_dashboard/query_models.py
api/ontology_dashboard/query_service.py
api/ontology_dashboard/board_registry.py
api/ontology_dashboard/render_specs.py

api/migrations/sqlite/0005_dashboard_layout_v2.sql
api/migrations/postgresql/0004_dashboard_layout_v2.sql
```

### 새 타입/API/DB

- `GridPosition`
- `ResponsiveBoardLayout`
- `DataBinding`
- `RenderSpec`
- `BoardResultContract`
- `SelectionFilter`
- explicit `DependencyEdge`
- query batch API
- layout patch API
- 기존 payload schema v2

### UI 기능

- drag/resize 12열 Grid
- breakpoint layout
- Chart/Table/Metric board
- chart click/brush
- Active Selection chip
- verification table
- typed binding editor
- parameter control
- loading/error/stale/freshness
- 기존 Evidence/Action 유지

### 테스트 전략

```text
Vitest
- legacy layout migration
- grid adapter
- selection combine/clear
- dependency traversal
- render spec validation

Pytest
- scope mismatch 거부
- query batch permission
- invalid parameter
- invalid selection
- revision conflict
- legacy payload resolve

Playwright
- drag/resize/save/reload
- chart click → table update
- saved view/share restore
- mobile layout
- role/evidence/action regression
```

### 완료 조건

- 기존 role template 정상 렌더
- layout 저장/복원
- chart selection이 실제 target board 재조회
- verification table이 동일 filter를 반영
- share/PDF에 parameter/selection 포함
- scope 우회 테스트 통과

### 리스크

- Grid CSS와 fullscreen 충돌
- v1/v2 preference merge
- chart gesture와 drag 충돌
- query N+1
- Blueprint 전역 style 충돌
- legacy/generic renderer 이중화

---

## P1 — Analysis Path MVP

### 목표

재현 가능한 Analysis 편집·실행·검증 화면을 구축한다.

### 변경 파일

```text
web/src/App.tsx
web/src/routing.ts
web/src/api.ts
```

### 신규 파일

```text
web/src/features/analysis/types.ts
web/src/features/analysis/AnalysisRoute.tsx
web/src/features/analysis/AnalysisShell.tsx
web/src/features/analysis/AnalysisSourceRail.tsx
web/src/features/analysis/AnalysisCanvas.tsx
web/src/features/analysis/AnalysisBoardFrame.tsx
web/src/features/analysis/AnalysisBoardInspector.tsx
web/src/features/analysis/AnalysisResultPreview.tsx
web/src/features/analysis/AnalysisRunStatusBar.tsx
web/src/features/analysis/analysis-registry.ts
web/src/features/analysis/analysis-validation.ts

api/ontology_dashboard/routers/analyses.py
api/ontology_dashboard/analysis_models.py
api/ontology_dashboard/analysis_repository.py
api/ontology_dashboard/analysis_service.py
api/ontology_dashboard/analysis_executor.py
api/ontology_dashboard/analysis_validation.py

api/migrations/sqlite/0006_analysis_engine.sql
api/migrations/postgresql/0005_analysis_engine.sql
schemas/analysis-definition.schema.json
schemas/board-result.schema.json
```

### 새 타입/API/DB

- `AnalysisDefinition`
- `AnalysisVersion`
- `AnalysisBoard`
- `AnalysisEdge`
- `AnalysisOutputPort`
- `AnalysisRun`
- `AnalysisBoardRun`
- analyses API
- run/result/profile API
- analysis tables

### UI 기능

- source picker
- vertical path
- Add connector
- compatible board catalog
- per-step preview
- schema diff
- profile
- run/validate/save/version
- Dashboard publish

### P1 지원 Board

- Source
- Filter
- Derive
- Group
- Aggregate
- Sort
- Table
- Chart

### P2로 미룸

- arbitrary SQL
- multi-input join
- pivot
- custom Python
- notebook/kernel
- streaming continuous run

### 테스트 전략

```text
Unit
- board config schema
- field type inference
- DAG cycle rejection
- expression whitelist
- output contract compilation

Integration
- Prediction Result → Filter → Aggregate → Table
- cross-project source 거부
- failed board downstream blocked
- run version reproducibility
- cursor paging/profile

E2E
- Analysis 생성
- step 추가
- 실행
- table 검증
- version 저장
- Dashboard publish
```

### 완료 조건

- raw SQL 없이 핵심 분석 경로 구성
- version/parameter/input으로 결과 재현
- 단계별 schema/profile 확인
- published output을 Dashboard가 소비
- Dashboard에서 transform config 수정 불가

### 리스크

- mini data platform으로 범위 팽창
- expression security
- preview와 full result 차이
- source version 고정
- long-running run 상태
- SQLite/PostgreSQL 차이

---

## P2 — Lineage, Operational Drill-down, Snapshot

### 목표

분석 결과를 Object/Evidence/Action/Audit graph와 연결한다.

### 신규 파일

```text
web/src/features/graph/types.ts
web/src/features/graph/GraphBoard.tsx
web/src/features/graph/OntologyGraphView.tsx
web/src/features/graph/AnalysisLineageView.tsx
web/src/features/graph/DecisionLineageView.tsx
web/src/features/dashboard/ObjectEvidenceActionDrawer.tsx
web/src/features/dashboard/DataFreshnessStatusBar.tsx
web/src/features/dashboard/SnapshotDialog.tsx
web/src/features/timeline/TimelineParameter.tsx
web/src/features/map/*

api/ontology_dashboard/routers/lineage.py
api/ontology_dashboard/routers/snapshots.py
api/ontology_dashboard/lineage_service.py
api/ontology_dashboard/snapshot_service.py

api/migrations/sqlite/0007_lineage_snapshots.sql
api/migrations/postgresql/0006_lineage_snapshots.sql
```

### 새 타입/API/DB

- `ResourceNode`
- `ResourceLineageEdge`
- `ObjectReference`
- `EvidenceReference`
- `ActionReference`
- `DashboardSnapshotContract`
- graph API
- snapshot API
- lineage/snapshot tables

### UI 기능

- Ontology Graph
- Analysis Lineage
- Decision Lineage
- selected row → detail drawer
- Action 수행 후 audit 갱신
- freshness/replay badge
- immutable PDF snapshot
- 필요 시 MapLibre Board

### 테스트 전략

- graph permission filtering
- cross-project edge leakage 방지
- Action invocation lineage
- snapshot reproducibility
- PDF metadata
- 100~500 node 성능
- replay honesty label

### 완료 조건

- Prediction Result에서 Action까지 lineage 재구성
- snapshot이 version/parameter/selection/freshness/audit 보존
- 권한 없는 node/edge 비노출
- 현장 사용자가 허용된 Action 수행

### 리스크

- graph 과밀
- ontology link와 lineage 중복
- snapshot 민감 데이터
- replay/live 혼동
- Map 기능의 데모화

---

# 10. 현실적인 제품 범위

## 10.1 구현할 범위

### 제조 예지보전 Object

- Equipment
- Production Line
- Sensor/Signal Window
- Prediction Result
- Risk Event
- Evidence
- Maintenance Record
- Work Order/Field Task
- Model/Policy Version
- Human Decision/Action Invocation

### 사용자별 흐름

```text
Manager
- 위험 현황 확인
- 생산 영향 확인
- line/equipment drill-down
- 조치 상태 확인

Engineer
- trend/anomaly 선택
- Result Table 검증
- Evidence 확인
- maintenance action 수행

Data Scientist / ML Validator
- model/policy/dataset version 선택
- slice 검증
- quality 확인
- release request

FDE
- Analysis 구성
- Dashboard template 구성
- binding/permission 검증
- publish request

Auditor/Admin
- Prediction → Evidence → Decision → Action → Export 재구성
```

### 지원 분석 범위

- 1~3 curated source contract
- Filter, Derive, Group, Aggregate, Sort
- line/bar/area/scatter/pie/histogram/metric
- generic verification table
- 핵심 parameter 4~6개
- chart-to-chart/table/object filtering
- Analysis version/run
- Dashboard layout/version/view/share/snapshot
- Evidence/Action/Audit

## 10.2 명시적으로 구현하지 않을 것

- Foundry 전체 Dataset/Pipeline/Code Repository/Notebook
- arbitrary Python/SQL execution platform
- 실시간 협업 편집/멀티 커서
- 범용 low-code App Builder
- 범용 Ontology Modeling Studio 전체
- Marketplace/Plugin ecosystem
- 모든 산업 대상 generic semantic layer
- full BI authoring suite
- globe/위성 command center
- 대규모 geospatial engine
- Superset/Cube/AG Grid 동시 도입
- Project를 Dataset으로 취급
- Dashboard가 모델 내부 table을 직접 참조

## 10.3 성공 기준

다음 질문에 모두 답할 수 있어야 한다.

1. 이 차트는 어떤 source, Analysis, Model, Policy version에서 왔는가?
2. 차트 선택 대상이 Table과 Object Detail에서 동일하게 보이는가?
3. 원시 결과를 검증할 수 있는가?
4. Evidence를 보고 권한 있는 Action을 실행할 수 있는가?
5. 누가 어떤 근거와 parameter로 Action을 실행했는가?
6. Share/PDF가 scope와 freshness를 정직하게 표현하는가?
7. role template과 personal preference가 version 변경 후 안전하게 병합되는가?

## 10.4 가장 먼저 검증할 Vertical Slice

```text
Risk by Line ECharts
  → LINE-03 클릭
  → Critical Risk Trend 갱신
  → Verification Table 갱신
  → Equipment/RiskEvent Drawer 갱신
  → Evidence 확인
  → Maintenance Action 실행
  → Audit 기록 확인
```

이 흐름 하나가 다음을 동시에 검증한다.

- scope
- query result contract
- selection propagation
- Table verification
- Object context
- Evidence
- Action
- Audit

---

# 11. 최종 권고

현재 MVP에 Palantir Contour/Foundry 스타일을 접목하는 가장 좋은 방법은 기존 Dashboard를 폐기하거나 외부 BI를 embed하는 것이 아니다.

권장 방향:

1. 기존 역할·Evidence·Action·Audit 기능을 유지한다.
2. Dashboard Board Layout을 `x/y/w/h`로 승격한다.
3. ECharts와 TanStack Table을 동일 `BoardResultContract` 위에 올린다.
4. Analysis Path를 별도 route와 versioned server run으로 구현한다.
5. Dashboard는 Analysis output을 참조하고 transform logic을 중복 저장하지 않는다.
6. React Flow는 Object/Lineage에만 사용한다.
7. Blueprint는 편집 UI primitive에만 선택 도입한다.
8. Prediction Result Contract와 scope boundary를 모든 query의 전제로 둔다.
9. Superset, Cube, AG Grid Enterprise는 현재 도입하지 않는다.
10. 제조 예지보전의 탐지→분석→검증→근거→행동→감사 루프에 집중한다.

최종 목표는 “Palantir처럼 보이는 화면”이 아니다.

```text
데이터에서 위험을 발견하고,
분석 경로로 원인을 좁히고,
표로 결과를 검증하고,
Object와 Evidence를 확인하고,
권한 있는 Action을 실행하고,
전체 과정을 Audit으로 재구성할 수 있는 경험
```

이 경험이 구현되면 Palantir 전체를 복제하지 않아도 제조 예지보전 vertical에서 충분히 Palantir급 제품 경험을 제공할 수 있다.

---

# 부록 A. 검토 파일 경로

## MVP Frontend

```text
web/src/App.tsx
web/src/routing.ts
web/src/api.ts
web/src/features/dashboard/DashboardShell.tsx
web/src/features/dashboard/BoardCanvas.tsx
web/src/features/dashboard/ContextPanel.tsx
web/src/features/dashboard/DashboardBoardRenderer.tsx
web/src/features/dashboard/BoardInspector.tsx
web/src/features/dashboard/BoardCatalogPanel.tsx
web/src/features/dashboard/types.ts
web/src/features/dashboard/utils.ts
web/src/features/manufacturing/ManufacturingApp.tsx
web/src/features/manufacturing/useDashboardEditor.ts
web/src/features/ontology/types.ts
web/src/styles.css
web/package.json
```

## MVP Backend

```text
api/ontology_dashboard/routers/dashboards.py
api/factory_signal_board/dashboard_models.py
api/factory_signal_board/dashboard_service.py
api/factory_signal_board/dashboard_repository.py
api/factory_signal_board/ontology.py
api/factory_signal_board/ontology_service.py
api/factory_signal_board/ontology_adapter.py
schemas/dashboard-platform.schema.json
api/migrations/sqlite/*
api/migrations/postgresql/*
```

## Reference Documents

```text
docs/40-ui-ux/reference/palantir-contour-ui-reference.md
docs/40-ui-ux/reference/palantir-contour-dashboard-benchmark.md
docs/30-implementation/implementation-status.md
```

## Reference Projects

```text
mini_foundry_public/frontend/components/dashboards/DashboardCanvas.tsx
mini_foundry_public/frontend/components/dashboards/DataBindingPanel.tsx
mini_foundry_public/frontend/components/dashboards/FilterBar.tsx
mini_foundry_public/frontend/components/ontology/OntologyGraph.tsx

openfoundry-emulator/apps/app-console/src/pages/Contour.tsx
openfoundry-emulator/apps/app-workshop/src/components/Canvas.tsx
openfoundry-emulator/apps/app-workshop/src/widgets/widget-registry.ts
openfoundry-emulator/apps/app-workshop/src/store/page-store.ts

contour-translation/contour-translator/contour_translator.py
contour-translation/contour-translator/contour_render_specs.py

palantir-blueprint/packages/core
palantir-blueprint/packages/icons
palantir-blueprint/packages/select
palantir-blueprint/packages/table

OpenFoundry/apps/web/src/lib/components/dashboard/DashboardGrid.svelte
OpenFoundry/apps/web/src/lib/components/dashboard/WidgetFactory.svelte
OpenFoundry/apps/web/src/lib/components/dashboard/WidgetConfig.svelte
OpenFoundry/apps/web/src/lib/utils/dashboards.ts
OpenFoundry/apps/web/src/lib/stores/dashboards.ts

palantir-demo/src/components/Dashboard.jsx
palantir-demo/src/components/GlobeComponent.jsx
palantir-demo/src/components/EventDetailModal.jsx

Gods_Eye/docs/ARCHITECTURE.md
Gods_Eye/docs/REPLAY_MODEL.md
Gods_Eye/src/store/useStore.js
Gods_Eye/src/store/timeStore.js
Gods_Eye/src/components/LayerControls.jsx
Gods_Eye/src/components/Timeline.jsx
```

---

# 부록 B. 라이선스 체크리스트

| 대상 | 확인 상태 | 처리 |
|---|---|---|
| `mini_foundry_public` | MIT | notice 유지 후 adaptation 가능 |
| `openfoundry-emulator` | Apache-2.0 | NOTICE/저작권 확인 |
| `contour-translation` | MIT | helper 개념/일부 코드 가능 |
| `palantir-blueprint` | Apache-2.0 | npm dependency 사용 |
| `OpenFoundry` | README/package Apache-2.0, 로컬 LICENSE 비어 있음 | upstream 재확인 전 복사 금지 |
| `palantir-demo` | LICENSE 미명시 | 코드/asset 복사 금지 |
| `Gods_Eye` | GPL-3.0 | 독립 구현만 허용 |
| React Grid Layout | MIT | dependency notice 관리 |
| TanStack Table | MIT | dependency notice 관리 |
| Apache ECharts | Apache-2.0 | NOTICE 관리 |
| React Flow | MIT | dependency notice 관리 |
| Vega-Lite | BSD-3-Clause | 도입 시 notice 관리 |
| MapLibre GL JS | BSD-3-Clause 및 third-party notices | attribution 관리 |
| Superset | Apache-2.0 | 별도 서비스 license inventory |
| Cube Core | Apache-2.0 | 별도 서비스 license inventory |
| AG Grid Enterprise | 상용 | 구매·배포 조건 확인 전 도입 금지 |

> 이 라이선스 표는 기술 검토용이며 법률 자문이 아니다. 실제 코드 복사 또는 배포 전에 사용 commit 기준 LICENSE, NOTICE, third-party attribution을 다시 확인해야 한다.
