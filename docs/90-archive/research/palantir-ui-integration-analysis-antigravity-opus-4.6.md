# Palantir Contour/Foundry UI 통합 분석서

> 작성일: 2026-08-01  
> 범위: `mvp-프로젝트2`에 Palantir Contour 스타일 분석·대시보드 UI를 접목하기 위한 상세 분석  
> 근거: MVP 소스 코드 + Palantir Contour UI 레퍼런스 문서 + 7개 오픈소스 레퍼런스 프로젝트

---

## 목차

1. [현재 MVP의 Palantir 유사 기능 vs 부족한 기능](#1-현재-mvp의-palantir-유사-기능-vs-부족한-기능)
2. [레퍼런스 7개 비교 분석표](#2-레퍼런스-7개-비교-분석표)
3. [Palantir Contour 스타일 화면 구조 제안](#3-palantir-contour-스타일-화면-구조-제안)
4. [DashboardShell·BoardCanvas 구조 전환 분석](#4-dashboardshellboardcanvas-구조-전환-분석)
5. [ASCII Wireframe과 컴포넌트 트리](#5-ascii-wireframe과-컴포넌트-트리)
6. [기술 선택 판단](#6-기술-선택-판단)
7. [P0/P1/P2 구현 로드맵](#7-p0p1p2-구현-로드맵)
8. [현실적 범위 정의](#8-현실적-범위-정의)

---

## 1. 현재 MVP의 Palantir 유사 기능 vs 부족한 기능

### 1-A. 이미 있는 Palantir/Contour 유사 기능

| 기능 | MVP 파일 | Contour 대응 | 구현 수준 |
|------|----------|-------------|----------|
| 스키마 기반 Board Catalog | `types.ts` L17-34 `BoardCatalogDefinition` | Contour Board 카탈로그 | ✅ `category`, `renderer`, `allowed_roles`, `binding_schema`, `emits`/`accepts` 정의 완비 |
| 탭 기반 Dashboard | `DashboardShell.tsx` L162-186 | Contour Dashboard 탭 | ✅ 탭 렌더링, 드래그 재정렬, 추가/숨김 |
| 좌측 Context/Parameter Rail | `ContextPanel.tsx` | Contour 좌측 파라미터 패널 | ✅ Object Context, Parameter 드롭다운, Saved View, 이벤트 리스트 |
| 우측 Inspector | `BoardInspector.tsx` | Contour 보드 설정 패널 | ✅ 제목, 폭, 탭 이동, 숨김, Bindings, Cross-filter Contract |
| View/Edit 모드 분리 | `DashboardShell.tsx` L189-192 | Contour View/Edit 토글 | ✅ 뷰 모드에서 소비, 에디트 모드에서 구성 |
| Cross-filter 의존성 그래프 | `types.ts` L59-63 `DependencyEdge` | Contour 차트 간 필터 전파 | ⚠️ 데이터 모델은 있으나 실제 query 재실행 미연결 |
| Export (PDF/CSV/JSON) | `DashboardShell.tsx` L196-203 | Contour PDF/CSV export | ✅ 포맷 선택 + export 버튼 |
| Share / Saved View | `types.ts` L82-110 | Contour 공유 / 북마크 | ✅ `SavedView`, `DashboardShareCreated`, token 기반 |
| RBAC + Template 게시 | `DashboardShell.tsx` L209-217 | Foundry 역할별 앱 | ✅ 8개 역할, FDE/Admin template 게시 |
| Ontology (Object·Link·Action) | `api/ontology_dashboard/routers/ontology.py` | Foundry Ontology | ✅ Object 조회, Link 탐색, Action invoke, audit log |
| Evidence / Lineage 추적 | `DashboardBoardRenderer.tsx` L195-206 `AuditTrace` | Foundry audit trail | ✅ Object → Evidence → Model·Policy → Human Action 추적 |
| 보드 드래그 앤 드롭 재정렬 | `BoardCanvas.tsx` L72-86 | Contour 보드 위치 이동 | ✅ 동일 탭 내 + 탭 간 이동 |
| 전체화면 보드 | `BoardCanvas.tsx` L96-105 | Contour 보드 전체화면 | ✅ 개별 보드 확대/축소 |

### 1-B. 부족한 기능 (Contour 대비 갭)

| 부족한 기능 | Contour에서의 역할 | 현재 상태 | 갭 설명 |
|------------|-------------------|----------|--------|
| **Analysis Path (순차적 데이터 경로)** | 핵심 — Filter → Join → Group → Aggregate → Chart를 위→아래 보드 경로로 연결 | ❌ 없음 | MVP는 독립 위젯 모음이며 `input_board_id`/`output_schema` 개념 없음. 라우트 `/app/analysis/:id` 미존재 |
| **데이터 변형 보드** | Table, Filter, Join, Expression, Group/Aggregate 보드가 실제 row-level 변형 수행 | ❌ 없음 | `DashboardBoardRenderer`의 보드들은 결과 표시용이며 데이터를 변형하지 않음 |
| **실제 차트/메트릭 렌더러** | ECharts/Vega 기반 차트, KPI 카드, 히스토그램 | ❌ 없음 | 현재 renderer는 `BlockRenderer`(텍스트 기반) 또는 하드코딩된 카드. 차트 라이브러리 미사용 |
| **12열 x/y/w/h Grid** | 자유 배치 2D 그리드 (x,y 좌표 + w,h 크기) | ⚠️ 부분 | `BoardWidth`가 4·6·12만 허용, `gridColumn: span N`으로 1차원 배치. y 좌표·자유 배치 없음 |
| **Chart-to-chart 교차 필터 실행** | 차트 선택(brush/click)이 하류 보드의 query를 실제 재실행 | ⚠️ 시각만 | `affectedBoardIds` CSS 하이라이트는 있으나 실제 데이터 재조회 미구현 |
| **Result Inspector (결과 검증)** | 각 보드의 행 수, 스키마, null rate, 중복 key, sample 50행 표시 | ❌ 없음 | `BoardInspector`는 메타데이터(제목, 폭, bindings)만 다룸. 데이터 검증 UI 없음 |
| **고밀도 테이블 (TanStack/AG Grid)** | 컬럼 정렬, 필터, 페이지네이션, 가상 스크롤 | ❌ 없음 | 기본 `<table>` 또는 `<dl>` 사용 |
| **데이터셋 저장/버전 관리** | 분석 결과를 이름 있는 데이터셋으로 저장, 입력 버전 변경 시 영향 추적 | ❌ 없음 | `DatasetRef {id, version}` 개념 미존재 |
| **Ontology/Lineage 시각 그래프** | React Flow 기반 object 관계, 분석 경로 DAG 시각화 | ❌ 없음 | `AuditTrace`는 텍스트 리스트이며 그래프 시각화 아님 |
| **비결정성/시간대 경고** | 정렬 없는 집계, `now()` 의존, timezone 차이에 대한 warning badge | ❌ 없음 | timestamp는 UTC 저장되나 UI 경고 없음 |
| **Analysis Run Audit** | `user_id`, `input_rows`, `output_rows`, `elapsed_ms`, `cache_hit` 기록 | ❌ 없음 | 쿼리 실행 메타데이터 미추적 |
| **지도/공간 UI** | 설비 위치, 공장 레이아웃 시각화 | ❌ 없음 | MapLibre 등 미사용 |

---

## 2. 레퍼런스 7개 비교 분석표

### 2-1. 종합 비교표

| # | 레퍼런스 | 핵심 파일 | UI Takeaway | 데이터/상태 모델 Takeaway | MVP 적용 위치 | 직접 재사용 | 라이선스/주의점 |
|---|---------|----------|-------------|------------------------|-------------|-----------|--------------|
| 1 | **mini_foundry_public** | `DashboardCanvas.tsx`, `DataBindingPanel.tsx`, `FilterBar.tsx`, `OntologyGraph.tsx` | `react-grid-layout` 12열 x/y/w/h 드래그 그리드; 필터 바 (date_range, select, multi_select, search); React Flow 온톨로지 그래프 | `DashboardComponent {x,y,w,h}` 레이아웃; `Binding` discriminated union (sql_query, dataset, static); `DashboardFilter` 타입 | `BoardCanvas.tsx` → react-grid-layout 교체; 새 `DataBindingPanel`; 새 `OntologyGraph` | ✅ 구조 참고 + 일부 코드 재사용 가능 | **MIT** — 복사 가능, 저작권 표시 필수 |
| 2 | **openfoundry-emulator** | `Contour.tsx`, `Canvas.tsx`, `widget-registry.ts`, `page-store.ts` | 위→아래 순차 파이프라인(Contour); CSS Grid 커스텀 드래그 캔버스(Workshop); Blueprint.js UI primitive | 파이프라인 `Board {id, type, config}`, `BoardType` enum; `snapshots[]` 배열에 단계별 결과 캐싱; `WidgetInstance {position}` | 새 `AnalysisPath.tsx` → Contour 파이프라인 패턴; `widget-registry` → Board Catalog 확장 | ✅ 구조·패턴 재사용 가능 | **Apache 2.0** — 복사 가능, NOTICE 파일 유지 |
| 3 | **contour-translation** | `contour_translator.py`, `contour_render_specs.py` | UI 없음 (Python 스크립트) | Contour 내부 `boardState` → 정규화된 render spec 변환; `RENDER_KINDS` (input_dataset, histogram, timeseries, pivot_table 등); 컬럼/필터 정규화 로직 | `AnalysisBoardSpec` 타입 설계; render spec JSON 스키마; 필터 정규화 규칙 | ⚠️ Python 로직만 참고 | **MIT** — 변환 로직 참고 가능 |
| 4 | **palantir-blueprint** | `packages/core/src/components/` (button, dialog, forms, panel-stack, tabs, tree, popover) | Palantir 공식 디자인 시스템; data-dense UI에 최적화된 컴포넌트; SCSS 기반 디자인 토큰; 가상화 테이블 | controlled component 패턴; SCSS 변수·색상 체계; 접근성(a11y) 패턴 | `styles.css` 디자인 토큰 확장; 선택적 컴포넌트 사용 (Tree, PanelStack, Select, Table) | ✅ npm 패키지 직접 사용 | **Apache 2.0** — npm 의존성으로 정상 사용 |
| 5 | **OpenFoundry** | `apps/web/src/lib/components/{dashboard,ontology,pipeline,map}`, `lib/stores/` | Ontology/Pipeline/Dashboard 3계층 분리; 지도 레이어; 앱 빌더 패턴; Svelte 반응형 UI | Svelte stores 기반 상태; Rust 백엔드; 데이터셋→온톨로지→파이프라인 흐름 | **아키텍처 참고만**: 3계층 분리 개념을 React로 재해석; 지도 UI 아이디어 | ❌ 기술 스택 불일치 (Svelte/Rust) | **Apache 2.0** — 코드 복사 비실용적 |
| 6 | **palantir-demo** | `src/components/Dashboard.jsx`, `GlobeComponent.jsx`, `EventDetailModal.jsx` | 3D 지구본; glassmorphism 스타일; 실시간 고빈도 업데이트; 슬라이딩 패널 | React hooks 기반; 고빈도 상태 업데이트 최적화; 시뮬레이션 데이터 | **시각 영감만**: dark mode 스타일, 실시간 업데이트 패턴 | ❌ 코드 복사 금지 | **라이선스 미명시** — 아이디어 참고만 |
| 7 | **Gods_Eye** | `src/components/Globe.jsx`, `LayerControls.jsx`, `Timeline.jsx`; `src/store/`, `src/layers/` | Cesium 3D 맵; 레이어 on/off; 타임라인 컨트롤; zustand 상태; 떠다니는 투명 위젯 | zustand 전역 상태; `layers/` 도메인 분리 (aircraft, satellite, gpsJamming); 백엔드 CORS 프록시 | **시각 영감만**: 레이어 토글 패턴, 타임라인 UI; zustand 상태 관리 참고 | ❌ 코드 복사 금지 | **GPL-3.0 가능성** — 코드 절대 복사 금지, 아이디어만 |

### 2-2. 핵심 재사용 우선순위

```
높음 (구조+코드 참고): mini_foundry_public → openfoundry-emulator → palantir-blueprint
중간 (설계 참고):      contour-translation → OpenFoundry
낮음 (시각 영감만):    palantir-demo → Gods_Eye
```

---

## 3. Palantir Contour 스타일 화면 구조 제안

### 3-A. Analysis 편집 화면 (`/app/analysis/:analysisId`)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Global Header                                                          │
│  [Logo] Project ▼ | Workspace ▼ | Analysis: "리스크 이벤트 분석" | ▶ Run | Save | Share │
├──────────────┬──────────────────────────────────────┬───────────────────┤
│  Board Rail  │  Analysis Path (세로 흐름)             │  Inspector       │
│  ────────── │  ┌──────────────────────────────────┐ │  ──────────────  │
│  📊 Table    │  │ ① Input: risk_events              │ │  Board Type     │
│  🔍 Filter   │  │    schema: 12 cols, 1,847 rows    │ │  Input Kind     │
│  🔗 Join     │  └──────────────┬───────────────────┘ │  Output Kind    │
│  📐 Expression│               [+ Add Board]           │  Config Schema  │
│  📈 Group    │  ┌──────────────────────────────────┐ │  ──────────────  │
│  Σ  Aggregate│  │ ② Filter: status="critical"      │ │  Result Preview │
│  ────────── │  │    → 423 rows                     │ │  rows: 423      │
│  📉 Chart    │  └──────────────┬───────────────────┘ │  null%: 2.1%    │
│  🔢 Metric   │               [+ Add Board]           │  elapsed: 45ms  │
│  📝 Text     │  ┌──────────────────────────────────┐ │  cache: HIT     │
│  🔬 Evidence │  │ ③ Group: equipment_id             │ │  ──────────────  │
│  ⚡ Action   │  │    p95(risk_score), count(*)      │ │  Lineage        │
│              │  │    → 87 groups                    │ │  [mini graph]   │
│  ────────── │  └──────────────┬───────────────────┘ │                  │
│  비활성:     │               [+ Add Board]           │  ──────────────  │
│  (현재 보드  │  ┌──────────────────────────────────┐ │  Parameters     │
│   output과   │  │ ④ Chart: bar (equipment × risk)   │ │  period: 30d    │
│   호환 안됨) │  │    [▓▓▓▓▓░░ ▓▓▓░░░ ▓▓▓▓░░]      │ │  line: L3       │
│              │  └──────────────────────────────────┘ │                  │
│              │                                       │  [Add to        │
│              │  [+ Add Board]   [Save as Dataset]    │   Dashboard]    │
├──────────────┴──────────────────────────────────────┴───────────────────┤
│  Footer: workspace scope · timezone: Asia/Seoul · data version: v42     │
└─────────────────────────────────────────────────────────────────────────┘
```

**핵심 동작:**
- **Board Rail**: 현재 마지막 보드의 `output_kind` (rows/aggregate)에 따라 호환 보드만 활성화
- **Analysis Path**: 위→아래 순차 흐름. 각 보드는 앞 보드의 출력을 입력으로 사용
- **Inspector**: 선택된 보드의 설정 + Result Preview (행 수, null rate, elapsed, cache) + 간이 lineage 그래프
- **[+ Add Board]**: 호환 보드 카탈로그 팝업. "추천"과 "호환 안됨" 구분 표시
- **[Save as Dataset]**: 최종 결과를 이름 있는 materialized view로 저장

### 3-B. Dashboard 소비 화면 (`/app/dashboard/:dashboardId`)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Global Header                                                          │
│  [Logo] Project ▼ | Workspace ▼ | [Tab1][Tab2][Tab3][+] | View|Edit | Share | PDF │
├──────────────┬──────────────────────────────────────────────────────────┤
│  Parameter   │  12-column Responsive Grid Canvas                        │
│  Rail        │  ┌────────┐ ┌────────┐ ┌────────┐                       │
│  ──────────  │  │Risk KPI│ │Overdue │ │Alert   │   ← w=4 each          │
│  기간: 30d ▼ │  │  87    │ │  12    │ │  423   │                       │
│  라인: All ▼ │  └────────┘ └────────┘ └────────┘                       │
│  고장유형: ▼ │  ┌──────────────────────┐ ┌──────────┐                  │
│  위험도: ▼   │  │Risk Trend Chart      │ │Failure   │  ← w=8, w=4      │
│              │  │  (ECharts line)      │ │Type Mix  │                   │
│  ──────────  │  │ 🖱 brush select →    │ │(ECharts  │                   │
│  적용 보드:  │  │  3 boards affected   │ │ pie)     │                   │
│  5 boards    │  └──────────────────────┘ └──────────┘                  │
│  ──────────  │  ┌────────────────────────────────────┐                  │
│  Object      │  │Equipment Risk Table (TanStack)     │  ← w=12         │
│  Context:    │  │ ID | Name | Risk | Status | Action │                  │
│  [Pump-A03]  │  │ click row → update context         │                  │
│  ──────────  │  └────────────────────────────────────┘                  │
│  Saved Views │  ┌──────────────────┐ ┌──────────────────┐              │
│  · 이번주    │  │Evidence Board    │ │Recommended Action│  ← w=6 each  │
│  · 긴급 필터 │  │ (source refs)    │ │ (governed)       │              │
│              │  └──────────────────┘ └──────────────────┘              │
├──────────────┴──────────────────────────────────────────────────────────┤
│  Footer: scope · timezone · template v3 · revision 7                    │
└─────────────────────────────────────────────────────────────────────────┘
```

**핵심 동작:**
- **Parameter Rail**: 기간, 라인, 고장유형, 위험도 드롭다운. 변경 시 `N boards affected` 표시 + 해당 보드만 query 재실행
- **Grid Canvas**: `react-grid-layout`으로 x/y/w/h 자유 배치. Edit 모드에서 드래그/리사이즈
- **Chart-to-chart filtering**: 차트 brush/click 선택 → `SelectionFilter` 생성 → `dependency_graph`를 따라 하류 보드 재실행
- **Table drill-down**: 행 클릭 → ContextPanel의 Object Context 업데이트 → Evidence/Action 보드 갱신
- **Board Catalog**: Edit 모드에서 분석 경로의 Chart/Metric/Table 보드를 Dashboard에 추가
- **Saved View**: 현재 파라미터 + 탭 상태를 북마크

### 3-C. 화면 간 관계

```
Analysis (만드는 곳)                    Dashboard (소비하는 곳)
┌──────────────────┐                   ┌──────────────────┐
│ Filter → Group   │ ──"Add to"───→   │ Grid에 배치된     │
│ → Aggregate      │   Dashboard      │ Chart/Table/KPI  │
│ → Chart          │                   │ 보드들            │
│ → Verify Table   │                   │                   │
└──────────────────┘                   └──────────────────┘
         │                                      │
         ↓                                      ↓
  AnalysisBoard.render_spec           DashboardBoard.data_binding
  (어떤 변형을 거쳤는지)               (어떤 render_spec을 참조하는지)
```

---

## 4. DashboardShell·BoardCanvas 구조 전환 분석

### 4-A. 현재 구조의 한계

#### BoardCanvas 한계 (`BoardCanvas.tsx`)

| 항목 | 현재 | 한계 |
|------|------|------|
| 레이아웃 모델 | `BoardWidth = 4 \| 6 \| 12`, `gridColumn: span N` (L71) | **1차원 배치만 가능**. 보드가 왼→오른→다음행으로 자동 흐름. 특정 위치에 보드를 놓거나, 보드 높이를 조절할 수 없음 |
| 드래그 앤 드롭 | HTML5 DnD로 보드 순서 변경 (L72-86) | **재정렬만 가능**. 다른 행/열 위치로 자유 이동 불가. 리사이즈 핸들 없음 |
| 보드 크기 | Inspector에서 4/6/12 중 선택 (L34-36) | **3단계 폭만 허용**. 실제 Contour는 임의 w(1~12), h(1~∞) 지원 |
| 반응형 | CSS Grid `repeat(12, minmax(0,1fr))` | **기본 반응형은 있으나** 브레이크포인트별 재배치 없음 |

#### DashboardShell 한계 (`DashboardShell.tsx`)

| 항목 | 현재 | 한계 |
|------|------|------|
| 라우트 구조 | 단일 라우트. `ManufacturingApp.tsx`가 모든 것을 관리 | **Analysis 화면 없음**. Dashboard 소비와 분석 편집이 분리되지 않음 |
| 데이터 연결 | `renderBoard` callback으로 보드 렌더링 위임 (L10) | **보드가 실제 데이터를 변형하지 않음**. 렌더러는 정적 Evidence/Report를 표시만 함 |
| 파라미터 반응 | `affectedBoardIds`로 CSS 하이라이트 (L9) | **시각적 표시만**. 실제 query 재실행 미구현 |
| 보드 간 의존 | `DependencyEdge` 타입 정의됨 (L59-63) | **모델만 존재**. 런타임에 의존성을 따라 데이터를 전파하는 엔진 없음 |

### 4-B. `width` 중심 → `x/y/w/h` 12열 Grid 전환

#### 현재 데이터 모델

```typescript
// types.ts L36-47
interface DashboardBoard {
  id: string;
  definition_id: string;
  title: string;
  width: BoardWidth;    // 4 | 6 | 12
  order: number;        // 순서만
  hidden: boolean;
  // ...
}
```

#### 제안 데이터 모델

```typescript
interface DashboardBoard {
  id: string;
  definition_id: string;
  title: string;
  // --- Layout: width → x/y/w/h ---
  layout: {
    x: number;    // 0~11, 12열 그리드의 시작 열
    y: number;    // 행 위치 (Infinity = 자동 배치)
    w: number;    // 1~12, 폭 (열 수)
    h: number;    // 1~∞, 높이 (행 수, 기본값은 보드 타입별)
    minW?: number;
    minH?: number;
    maxW?: number;
    maxH?: number;
  };
  hidden: boolean;
  mandatory: boolean;
  custom: boolean;
  // --- 새 필드 ---
  data_binding: DataBinding | null;           // 데이터 소스 바인딩
  parameter_bindings: Record<string, string>; // 파라미터 → 보드 config 매핑
  render_spec: RenderSpec | null;             // 차트/테이블 렌더링 사양
  depends_on: string[];                       // 선행 보드 ID 목록
  // --- 기존 유지 ---
  bindings: Record<string, unknown>;
  settings: Record<string, unknown>;
}
```

#### react-grid-layout 전환 방법

```
1단계: 마이그레이션 함수 작성
       기존 {width, order} → {x, y, w, h} 자동 변환
       - width=4 → w=4, width=6 → w=6, width=12 → w=12
       - order 순서대로 x=0,4,8 / y=0,1,2... 자동 배치

2단계: BoardCanvas.tsx 교체
       - HTML5 DnD + CSS Grid → react-grid-layout의 <ResponsiveGridLayout>
       - 기존 드래그 로직 제거, RGL의 onLayoutChange로 대체

3단계: BoardInspector.tsx 확장
       - "Layout 폭" select → w/h 숫자 입력 또는 프리셋 (1/3, 1/2, full)
       - 위치는 드래그로, 크기는 리사이즈 핸들로

4단계: API 계약 업데이트
       - DashboardBoard의 width/order → layout 필드로 변경
       - 기존 API 호환을 위한 마이그레이션 엔드포인트
```

### 4-C. Dashboard와 Analysis Path 분리

```
현재:
  /app → ManufacturingApp → DashboardShell → BoardCanvas → DashboardBoardRenderer
  (모든 것이 하나의 화면)

제안:
  /app/dashboard/:dashboardId → DashboardPage
    └→ DashboardShell → GridCanvas → DashboardBoardRenderer
       (소비: 차트, KPI, 테이블, 교차 필터, 전체화면, 공유)

  /app/analysis/:analysisId → AnalysisPage
    └→ AnalysisShell → AnalysisPath → AnalysisBoardRenderer
       (편집: 순차 데이터 변형 경로, 결과 검증, 데이터셋 저장)
```

### 4-D. 계약 설계

#### Board 정의 계약

```typescript
// Board Catalog 확장
interface BoardCatalogDefinition {
  // ... 기존 필드 유지 ...
  
  // 새 필드
  input_kind: "rows" | "aggregate" | "any" | "none";    // 입력 데이터 유형
  output_kind: "rows" | "aggregate" | "chart" | "none"; // 출력 데이터 유형
  config_schema: JSONSchema;                             // 설정 UI 자동 생성용
  query_compiler: string | null;                         // 서버사이드 쿼리 컴파일러 ID
  default_height: number;                                // 기본 grid 높이
}
```

#### 데이터 바인딩 계약

```typescript
type DataBinding =
  | { kind: "analysis_ref"; analysis_id: string; board_id: string }  // Analysis 결과 참조
  | { kind: "dataset"; dataset_id: string; version?: string }       // 데이터셋 직접 참조
  | { kind: "query"; query_spec: QuerySpec }                        // 인라인 쿼리
  | { kind: "static"; rows: Record<string, unknown>[] };            // 정적 데이터
```

#### Render Spec 계약

```typescript
interface RenderSpec {
  kind: "table" | "bar" | "line" | "pie" | "histogram" | "metric" | "text" | "map";
  x_field?: string;
  y_fields?: string[];
  group_field?: string;
  color_scheme?: string;
  sort?: { field: string; direction: "asc" | "desc" };
  limit?: number;
  format?: Record<string, string>;  // 필드별 포맷 (%, 소수점, 날짜 등)
}
```

#### Dependency Graph 계약

```typescript
interface DependencyEdge {
  source_board_id: string;
  target_board_id: string;
  parameter_ids: string[];
  // 새 필드
  propagation: "filter" | "selection" | "parameter"; // 전파 유형
  transform?: SelectionFilter;                        // 변환 규칙
}

interface SelectionFilter {
  field: string;
  operator: "in" | "range" | "eq";
  values: unknown[];
}
```

#### FastAPI API 계약 (새 엔드포인트)

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/analyses` | GET | 현재 workspace의 분석 목록 |
| `/api/analyses` | POST | 새 분석 생성 (입력 데이터셋 지정) |
| `/api/analyses/{id}` | GET | 분석 상세 (보드 경로 + 파라미터) |
| `/api/analyses/{id}/boards` | POST | 보드 추가 |
| `/api/analyses/{id}/boards/{boardId}` | PUT | 보드 설정 변경 |
| `/api/analyses/{id}/boards/{boardId}` | DELETE | 보드 삭제 (하류 영향 경고) |
| `/api/analyses/{id}/boards/{boardId}/execute` | POST | 보드 실행 (입력 → 변형 → 결과) |
| `/api/analyses/{id}/boards/{boardId}/preview` | GET | 결과 미리보기 (50행 + 스키마 + 통계) |
| `/api/analyses/{id}/save-dataset` | POST | 결과를 materialized view로 저장 |
| `/api/analyses/{id}/run` | POST | 전체 분석 실행 |
| `/api/analyses/{id}/share` | POST | 분석 공유 링크 생성 |
| `/api/dashboards/{id}/boards/{boardId}/query` | POST | 대시보드 보드 데이터 조회 |
| `/api/dashboards/{id}/boards/{boardId}/selection-filter` | POST | 차트 선택 → 하류 보드 필터 전파 |
| `/api/datasets` | GET | 저장된 데이터셋 목록 |
| `/api/datasets/{id}/versions` | GET | 데이터셋 버전 목록 |

---

## 5. ASCII Wireframe과 컴포넌트 트리

### 5-A. `/app/analysis/:analysisId` 컴포넌트 트리

```
<App>
  <AnalysisPage>                          // 라우트 컴포넌트
    <AnalysisShell>                        // 레이아웃 쉘
      ├── <GlobalHeader />                // 프로젝트/워크스페이스 선택, 분석 이름
      ├── <AnalysisToolbar />             // Run, Save, Share, Export Spec 버튼
      │
      ├── <AnalysisBoardRail>             // 좌측: 추가 가능한 보드 카탈로그
      │   ├── <BoardRailSection category="transform">
      │   │   ├── <RailItem kind="table" enabled />
      │   │   ├── <RailItem kind="filter" enabled />
      │   │   ├── <RailItem kind="join" enabled />
      │   │   ├── <RailItem kind="expression" enabled />
      │   │   ├── <RailItem kind="group" enabled />
      │   │   └── <RailItem kind="aggregate" disabled />  // output_kind 불일치 시
      │   └── <BoardRailSection category="visualize">
      │       ├── <RailItem kind="chart" />
      │       ├── <RailItem kind="metric" />
      │       ├── <RailItem kind="text" />
      │       ├── <RailItem kind="evidence" />
      │       └── <RailItem kind="action" />
      │
      ├── <AnalysisPath>                  // 중앙: 순차 보드 경로
      │   ├── <AnalysisBoardCard boardId="input-1">
      │   │   ├── <BoardHeader title="Input: risk_events" />
      │   │   ├── <BoardBody renderer="InputTableBoard" />
      │   │   └── <BoardFooter rows={1847} schema="12 cols" />
      │   ├── <AddBoardConnector />       // [+] 버튼
      │   ├── <AnalysisBoardCard boardId="filter-1">
      │   │   ├── <BoardHeader title="Filter: status=critical" />
      │   │   ├── <BoardBody renderer="FilterBoard" />
      │   │   └── <BoardFooter rows={423} />
      │   ├── <AddBoardConnector />
      │   ├── <AnalysisBoardCard boardId="group-1">
      │   │   ├── <BoardHeader title="Group: equipment_id" />
      │   │   ├── <BoardBody renderer="GroupBoard" />
      │   │   └── <BoardFooter groups={87} />
      │   ├── <AddBoardConnector />
      │   └── <AnalysisBoardCard boardId="chart-1">
      │       ├── <BoardHeader title="Bar: equipment × risk" />
      │       ├── <BoardBody renderer="ChartBoard" />
      │       └── <BoardFooter />
      │
      └── <AnalysisInspector>             // 우측: 선택된 보드 상세
          ├── <InspectorHeader boardType="filter" />
          ├── <BoardConfigPanel>          // 보드 타입별 설정 UI
          │   └── (동적: FilterConfig / GroupConfig / ChartConfig / ...)
          ├── <ResultPreview>             // 결과 검증
          │   ├── <StatRow label="rows" value={423} />
          │   ├── <StatRow label="null%" value="2.1%" />
          │   ├── <StatRow label="elapsed" value="45ms" />
          │   ├── <StatRow label="cache" value="HIT" />
          │   └── <SampleTable rows={50} />
          ├── <ParameterBindings />       // 파라미터 연결
          └── <LineageMiniGraph />        // 간이 의존 그래프
  </AnalysisPage>
</App>
```

### 5-B. `/app/dashboard/:dashboardId` 컴포넌트 트리

```
<App>
  <DashboardPage>                         // 라우트 컴포넌트
    <DashboardShell>                      // 기존 쉘 확장
      ├── <GlobalHeader />               // 프로젝트/워크스페이스 선택
      ├── <DashboardTabBar>              // 탭 + View/Edit 토글 + 액션
      │   ├── <TabButton /> × N
      │   ├── <AddTabButton />
      │   ├── <ViewEditToggle />
      │   ├── <BoardCatalogButton />
      │   ├── <SaveViewButton />
      │   ├── <ShareButton />
      │   └── <ExportControl />
      ├── <TemplatePublishBar />          // FDE/Admin 전용
      │
      ├── <ContextPanel>                  // 좌측 (기존 유지 + 확장)
      │   ├── <ObjectContextCard />
      │   ├── <ParameterRail>
      │   │   ├── <ParamControl id="period" type="date_range" />
      │   │   ├── <ParamControl id="line" type="select" />
      │   │   ├── <ParamControl id="failure_type" type="multi_select" />
      │   │   ├── <ParamControl id="risk_threshold" type="number" />
      │   │   └── <AffectedBoardCount count={5} />
      │   ├── <EventObjectList />
      │   └── <SavedViewList />
      │
      ├── <GridCanvas>                    // 중앙 (BoardCanvas 대체)
      │   └── <ResponsiveGridLayout cols={12}>
      │       ├── <GridBoardFrame boardId="kpi-1" layout={x:0,y:0,w:4,h:2}>
      │       │   ├── <BoardHeader title="Risk KPI" affected={false} />
      │       │   └── <MetricRenderer value={87} />
      │       ├── <GridBoardFrame boardId="chart-1" layout={x:0,y:2,w:8,h:4}>
      │       │   ├── <BoardHeader title="Risk Trend" affected={true} />
      │       │   └── <EChartsRenderer spec={lineSpec} onBrush={handleFilter} />
      │       ├── <GridBoardFrame boardId="table-1" layout={x:0,y:6,w:12,h:5}>
      │       │   ├── <BoardHeader title="Equipment Risk Table" />
      │       │   └── <TanStackTableRenderer data={rows} onRowClick={handleDrill} />
      │       └── ...
      │
      └── <BoardInspector>               // 우측 (기존 + 확장)
          ├── <InspectorHeader />
          ├── <LayoutControl w/h />       // 기존 width → w/h 확장
          ├── <DataBindingSection />       // 새: 데이터 소스 설정
          ├── <RenderSpecSection />        // 새: 차트/테이블 렌더링 설정
          ├── <CrossFilterContract />      // 기존: accepts/emits
          └── <ParameterBindings />        // 새: 파라미터 매핑
  </DashboardPage>
</App>
```

### 5-C. `/app/analysis/:analysisId` ASCII Wireframe (상세)

```
┌─────────────────────────────────────────────────────────────────┐
│ [OD] Ontology Dashboard                                         │
│ Project: [Manufacturing Alpha ▼]  Workspace: [Line-3 ▼]        │
│ Analysis: "2026-07 리스크 이벤트 분석"                            │
│ [▶ Run All] [💾 Save] [🔗 Share] [📥 Export Spec]                │
├──────────┬─────────────────────────────────────┬────────────────┤
│ Board    │                                     │ Inspector      │
│ Catalog  │  ┌────── INPUT ─────────────────┐   │                │
│          │  │ 📊 risk_events               │   │ Type: Input    │
│ ── Data ─│  │ 12 columns · 1,847 rows      │   │ Dataset:       │
│ [Table]  │  │ version: v42 · 2026-07-31    │   │  risk_events   │
│ [Filter] │  └─────────────┬────────────────┘   │ Version: v42   │
│ [Join]   │                │                     │                │
│ [Expr]   │          [+ Add Board]               │ ─── Result ─── │
│ [Group]  │                │                     │ Rows: 1,847    │
│ [Aggr]   │  ┌────── FILTER ───────────────┐   │ Null%: 0.3%    │
│          │  │ 🔍 status = "critical"       │   │ Elapsed: 12ms  │
│ ── Viz ──│  │ AND severity >= "high"       │   │ Cache: MISS    │
│ [Chart]  │  │ → 423 rows remaining        │   │                │
│ [Metric] │  └─────────────┬────────────────┘   │ ─── Schema ─── │
│ [Text]   │                │                     │ event_id: str  │
│          │          [+ Add Board]               │ equipment: obj │
│ ── Act ──│                │                     │ status: str    │
│ [Evid]   │  ┌────── GROUP ────────────────┐   │ risk_score: f64│
│ [Action] │  │ 📈 BY: equipment_id          │   │ ...8 more      │
│          │  │ p95(risk_score): 0.87        │   │                │
│          │  │ count(*): 423                │   │ ─── Lineage ── │
│          │  │ → 87 groups                  │   │ Input → Filter │
│          │  └─────────────┬────────────────┘   │   → [Group] ●  │
│          │                │                     │                │
│          │          [+ Add Board]               │ ─── Params ─── │
│          │                │                     │ period: 30d    │
│          │  ┌────── CHART ─────────────────┐   │ line: L3       │
│          │  │ 📉 Bar: equipment × risk_p95  │   │                │
│          │  │ ┌──┐┌─┐┌───┐┌──┐┌─┐          │   │ [Add to       │
│          │  │ │  ││ ││   ││  ││ │          │   │  Dashboard ▶] │
│          │  │ └──┘└─┘└───┘└──┘└─┘          │   │                │
│          │  │ [🔍 Verify Result Table ▼]    │   │                │
│          │  └──────────────────────────────┘   │                │
│          │                                     │                │
│          │  [+ Add Board]  [Save as Dataset]   │                │
├──────────┴─────────────────────────────────────┴────────────────┤
│ Asia/Seoul · Workspace scope: Line-3 · Data v42 · Non-det: ⚠   │
└─────────────────────────────────────────────────────────────────┘
```

### 5-D. `/app/dashboard/:dashboardId` ASCII Wireframe (상세)

```
┌─────────────────────────────────────────────────────────────────┐
│ [OD] Ontology Dashboard     Manufacturing Predictive Maint Pack │
│ Project: [Mfg Alpha ▼]  WS: [Line-3 ▼]  Template v3 · Rev 7   │
│ User: 김지훈 (Process Engineer)                     [관리자][로그아웃]│
├─────────────────────────────────────────────────────────────────┤
│ Process Engineer Dashboard                                       │
│ 설비 위험 예측과 예방 점검 관리를 위한 운영 대시보드                   │
│ [Risk Analysis] [Maintenance] [Model Health] [Overview] [+]      │
│                                    [View|Edit] [Catalog] [Save View] [Share] [PDF▼ Export]│
├──────────┬──────────────────────────────────────────────────────┤
│Parameter │ ┌──── w=4 ────┐┌──── w=4 ────┐┌──── w=4 ────┐      │
│Rail      │ │ Risk KPI    ││ Overdue KPI ││ Alert Count │      │
│──────────│ │    ⚠ 87     ││    ⛔ 12    ││    🔔 423   │      │
│기간      │ └─────────────┘└─────────────┘└─────────────┘      │
│[30일 ▼]  │ ┌──────────── w=8 ────────────┐┌──── w=4 ────┐    │
│──────────│ │ Risk Trend (Line Chart)      ││ Failure Mix │    │
│라인      │ │  ╭─╮    ╭──╮                 ││ (Pie Chart) │    │
│[All ▼]   │ │ ─╯ ╰──╯  ╰─╮ 🖱 brush      ││   ◐ TWF     │    │
│──────────│ │              ╰──             ││   ◑ HDF     │    │
│고장유형  │ │ "3 boards affected"          ││   ◓ PWF     │    │
│[All ▼]   │ └─────────────────────────────┘└─────────────┘    │
│──────────│ ┌────────────────── w=12 ──────────────────────┐    │
│위험도    │ │ Equipment Risk Table (TanStack)               │    │
│[≥0.5 ▼] │ │ ┌──────┬────────┬──────┬────────┬──────────┐│    │
│──────────│ │ │ ID   │ Name   │ Risk │ Status │ Action   ││    │
│적용보드  │ │ ├──────┼────────┼──────┼────────┼──────────┤│    │
│5 boards  │ │ │P-A03 │Pump A03│ 0.92 │critical│[점검 생성]││    │
│──────────│ │ │M-B07 │Motor B7│ 0.78 │warning │[점검 생성]││    │
│Object    │ │ │C-D12 │Conv D12│ 0.65 │warning │[상세 보기]││    │
│Context:  │ │ └──────┴────────┴──────┴────────┴──────────┘│    │
│──────────│ │ [1/47 pages] [< Prev] [Next >] [Sort ▼]     │    │
│[Pump-A03]│ └─────────────────────────────────────────────┘    │
│Risk: 0.92│ ┌──── w=6 ──────────┐┌──── w=6 ──────────────┐    │
│Status:   │ │ Evidence Board    ││ Recommended Action     │    │
│ critical │ │ ─────────────     ││ ─────────────────      │    │
│Engineer: │ │ • Temp: 312K ↑    ││ ✅ 점검 생성 (governed)│    │
│ 김지훈   │ │ • Torque: 48Nm ↑  ││ 📋 체크리스트 확인     │    │
│──────────│ │ • Wear: 215min ↑  ││ 📸 사진 첨부           │    │
│Saved View│ │ confidence: 0.92  ││ [▶ Run Action]         │    │
│──────────│ │ model: v3.2       ││ requires: human_review │    │
│· 이번주  │ └───────────────────┘└────────────────────────┘    │
│· 긴급    │                                                     │
├──────────┴──────────────────────────────────────────────────────┤
│ Manufacturing Predictive Maintenance Pack · 공유 링크도 현재     │
│ 사용자의 object permission과 workspace scope를 우회하지 않습니다. │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. 기술 선택 판단

### 6-A. "지금 도입" / "나중에 검토" / "도입하지 않음" 분류

| 기술 | 판단 | 근거 |
|------|------|------|
| **React Grid Layout** | 🟢 **지금 도입** | `mini_foundry_public`이 동일 패턴으로 12열 드래그/리사이즈 사용. `BoardCanvas`의 `gridColumn: span N`을 `x/y/w/h` 레이아웃으로 대체하는 데 필수. MIT 라이선스, 번들 크기 ~50KB, React 생태계 표준 |
| **Apache ECharts** | 🟢 **지금 도입** | Chart/Metric/Histogram 보드의 실제 렌더러에 필수. `mini_foundry_public`이 `echarts-for-react` 사용. brush/click selection으로 교차 필터링 구현 가능. Apache 2.0, 성숙한 라이브러리 |
| **TanStack Table** | 🟢 **지금 도입** | 결과 검증 테이블, Equipment Risk Table, Verify Result 등 고밀도 데이터 표시에 필수. `mini_foundry_public`이 `@tanstack/react-table` 사용. 정렬/필터/페이지네이션/가상화 지원. MIT, 번들 최적 |
| **React Flow (@xyflow/react)** | 🟟 **나중에 검토** (P1~P2) | Ontology 그래프, 분석 경로 DAG, Lineage 시각화에 유용하나 P0에서는 불필요. `mini_foundry_public`이 사용. P1의 Analysis Path lineage, P2의 Object Graph에 도입 |
| **Blueprint.js** | 🟟 **나중에 검토** (선택적) | Palantir 공식 디자인 시스템이지만 현재 MVP는 커스텀 CSS로 잘 동작. Tree, PanelStack, Select 등 특정 컴포넌트만 선택적으로 사용할 가치 있음. 전체 교체는 비용 대비 효과 낮음 |
| **Vega-Lite** | 🟟 **나중에 검토** | 선언형 chart spec 후보. ECharts로 충분히 커버 가능하며 두 라이브러리 병행은 비효율적. Analysis Path의 render spec 스키마 설계에 Vega-Lite grammar 참고 가능 |
| **MapLibre GL JS** | 🟟 **나중에 검토** (P2+) | 공장 레이아웃/설비 위치 지도가 필요해지면 도입. 현재 제조 예지보전 vertical에서는 지도보다 차트/테이블이 우선 |
| **AG Grid Enterprise** | 🔴 **도입하지 않음** | 연간 라이선스 비용 $1,495+/developer. TanStack Table로 필요한 기능(정렬, 필터, 페이지네이션, 가상화) 충분히 구현 가능. Enterprise 전용 기능(피벗, 차트 연동, 서버사이드 모델) 현재 불필요 |
| **Apache Superset** | 🔴 **도입하지 않음** (별도 BI로만) | 별도 BI 도구로 사용하려면 별도 서버 운영 필요. embed 시 인증 연동, 스타일 커스텀, 워크스페이스 범위 제어가 복잡. MVP의 통합된 Ontology Dashboard 경험과 충돌 |
| **Cube** | 🔴 **도입하지 않음** (현재) | Semantic layer로 유용하나, 현재 MVP 규모(수천~수만 행)에서는 FastAPI + SQLite/PostgreSQL 직접 쿼리로 충분. Cube 서버 추가는 인프라 복잡도 증가. 데이터가 수백만 행 이상이 되면 재검토 |

### 6-B. 추천 조합

```
P0 핵심 스택:
  react-grid-layout + ECharts + TanStack Table

P1 확장:
  + React Flow (Lineage/Ontology 그래프)
  + Blueprint.js 선택 컴포넌트 (Tree, Select, PanelStack)

P2 선택:
  + MapLibre GL JS (공장 지도 필요 시)
  + Vega-Lite (선언형 spec 전환 필요 시)
```

### 6-C. AG Grid Enterprise / Superset / Cube 상세 비용 분석

| 기술 | 라이선스 비용 | 인프라 비용 | 구조적 단점 |
|------|-------------|-----------|-----------|
| **AG Grid Enterprise** | $1,495+/dev/yr | 없음 (클라이언트) | 번들 크기 ~500KB+; TanStack Table 대비 기능 과잉; 라이선스 관리 부담; OSS 전환 시 lock-in |
| **Apache Superset** | 무료 (Apache 2.0) | 별도 Python 서버 + Redis + PostgreSQL | 인증/RBAC 이중 관리; iframe embed 시 UX 단절; 워크스페이스 scope 연동 커스텀 필요; CSS 오버라이드 어려움 |
| **Cube** | Community 무료, Cloud $0.10/1K queries | 별도 Node.js 서버 + Redis | pre-aggregation 설정 복잡; 스키마 DSL 학습 곡선; 현재 데이터 규모에서 직접 쿼리 대비 이점 미미; 서버 1대 추가 운영 |

---

## 7. P0/P1/P2 구현 로드맵

### P0 — Dashboard를 Contour형 소비 화면으로 완성

> 목표: 현재 Dashboard를 12열 Grid + 실제 차트 + 교차 필터가 작동하는 Contour Dashboard로 업그레이드

#### P0-1. Board 타입 확장 + x/y/w/h Grid 전환

| 항목 | 내용 |
|------|------|
| **변경 파일** | `web/src/features/dashboard/types.ts` (DashboardBoard에 `layout` 필드 추가), `web/src/features/dashboard/BoardCanvas.tsx` → `GridCanvas.tsx`로 교체 |
| **새 파일** | `web/src/features/dashboard/GridCanvas.tsx`, `web/src/features/dashboard/layout-migration.ts` |
| **새 타입** | `BoardLayout {x,y,w,h,minW,minH}`, `DataBinding` 유니온, `RenderSpec`, `SelectionFilter` |
| **새 API** | `PUT /api/dashboards/{id}/preferences` 에 layout 필드 추가 |
| **UI 기능** | 드래그로 보드 위치 이동, 모서리 핸들로 리사이즈, 기존 width→layout 자동 마이그레이션 |
| **테스트 전략** | 마이그레이션 함수 단위 테스트 (width=4 → {x,y,w:4,h:3}); E2E: 드래그 후 위치 유지 |
| **완료 조건** | 기존 대시보드가 새 Grid로 렌더링되고, Edit 모드에서 드래그/리사이즈 작동 |
| **예상 리스크** | 기존 `width`/`order` 데이터 마이그레이션 시 레이아웃 깨짐 가능 → 마이그레이션 함수에 `order` 기반 자동 배치 로직 필수 |

#### P0-2. ECharts 차트 렌더러 연결

| 항목 | 내용 |
|------|------|
| **변경 파일** | `web/src/features/dashboard/DashboardBoardRenderer.tsx` (차트 렌더러 분기 추가) |
| **새 파일** | `web/src/features/dashboard/renderers/EChartsRenderer.tsx`, `web/src/features/dashboard/renderers/MetricRenderer.tsx`, `web/src/features/dashboard/renderers/types.ts` |
| **새 타입** | `ChartRenderSpec`, `MetricRenderSpec`, `ChartSelectionEvent` |
| **새 API** | `POST /api/dashboards/{id}/boards/{boardId}/query` (보드별 데이터 조회) |
| **새 DB** | `analysis_board_cache` 테이블 (board_id, query_hash, result_json, created_at, ttl) |
| **UI 기능** | Bar/Line/Pie/Histogram 차트 렌더링, brush selection, click selection, tooltip |
| **테스트 전략** | ECharts 렌더링 스냅샷 테스트; brush event → SelectionFilter 변환 단위 테스트 |
| **완료 조건** | Dashboard에 실제 차트가 표시되고, 차트 영역을 brush/click하면 SelectionFilter 객체 생성 |
| **예상 리스크** | ECharts SSR 미지원 → CSR only 확인; 대량 데이터 시 렌더링 성능 → `sampling` 옵션 활용 |

#### P0-3. TanStack Table 결과 테이블

| 항목 | 내용 |
|------|------|
| **변경 파일** | `web/src/features/dashboard/DashboardBoardRenderer.tsx` |
| **새 파일** | `web/src/features/dashboard/renderers/DataTableRenderer.tsx` |
| **새 타입** | `TableRenderSpec`, `ColumnDef[]` 자동 생성 |
| **UI 기능** | 컬럼 정렬, 필터, 페이지네이션 (서버사이드), 행 클릭 → Object Context 업데이트, 가상 스크롤 |
| **테스트 전략** | 100행/1000행 데이터 렌더링 테스트; 정렬·필터 동작 테스트 |
| **완료 조건** | Equipment Risk Table이 TanStack으로 렌더링되고, 행 클릭 시 ContextPanel 업데이트 |
| **예상 리스크** | 서버사이드 페이지네이션 API 추가 필요 → FastAPI에 `offset`/`limit`/`sort`/`filter` 파라미터 |

#### P0-4. Chart-to-chart 교차 필터 실행

| 항목 | 내용 |
|------|------|
| **변경 파일** | `web/src/features/manufacturing/ManufacturingApp.tsx` (handleParameterChange 확장), `web/src/features/dashboard/DashboardBoardRenderer.tsx` |
| **새 파일** | `web/src/features/dashboard/cross-filter-engine.ts` |
| **새 타입** | `CrossFilterState`, `BoardQueryResult` |
| **새 API** | `POST /api/dashboards/{id}/boards/{boardId}/selection-filter` |
| **UI 기능** | 차트 brush/click → SelectionFilter → dependency_graph 탐색 → 영향받는 보드 query 재실행 → 결과 업데이트 |
| **테스트 전략** | dependency_graph 탐색 단위 테스트; E2E: 차트 선택 후 하류 보드 데이터 변경 확인 |
| **완료 조건** | Risk Trend 차트에서 기간 brush → Equipment Table 필터링 + Evidence 보드 업데이트 |
| **예상 리스크** | 순환 의존 방지 필요 → DAG 검증; 동시 필터 충돌 → 마지막 선택 우선 |

#### P0-5. Parameter Rail 실제 query 연결

| 항목 | 내용 |
|------|------|
| **변경 파일** | `web/src/features/dashboard/ContextPanel.tsx` (파라미터 타입별 UI 확장) |
| **새 파일** | `web/src/features/dashboard/ParamControl.tsx` (date_range, select, multi_select, number 지원) |
| **UI 기능** | 날짜 범위 피커, 다중 선택, 슬라이더; 변경 시 영향 보드 하이라이트 + 실제 재실행 |
| **테스트 전략** | 각 파라미터 타입 렌더링 테스트; 값 변경 → API 호출 확인 |
| **완료 조건** | 기간·라인·고장유형·위험도 변경 시 관련 보드만 데이터 재조회 |
| **예상 리스크** | debounce 필요 (슬라이더 연속 변경 시 과다 API 호출) |

### P1 — Analysis Path + 결과 검증

> 목표: 순차적 데이터 변형 경로를 만들고 결과를 검증할 수 있는 Analysis 화면 구현

#### P1-1. Analysis 라우트 + Shell

| 항목 | 내용 |
|------|------|
| **새 파일** | `web/src/features/analysis/AnalysisPage.tsx`, `AnalysisShell.tsx`, `AnalysisPath.tsx`, `AnalysisBoardCard.tsx`, `AnalysisBoardRail.tsx`, `AnalysisInspector.tsx`, `types.ts` |
| **새 타입** | `Analysis`, `AnalysisBoard`, `AnalysisBoardSpec`, `BoardOutputSnapshot`, `AnalysisRun` |
| **새 API** | `POST /api/analyses`, `GET /api/analyses/{id}`, `POST /api/analyses/{id}/boards`, `PUT /api/analyses/{id}/boards/{boardId}`, `DELETE /api/analyses/{id}/boards/{boardId}` |
| **새 DB 테이블** | `analyses`, `analysis_boards`, `analysis_runs` |
| **UI 기능** | `/app/analysis/:id` 라우트, Board Rail, 세로 Analysis Path, Inspector, Run/Save/Share |
| **테스트 전략** | 분석 생성 → 보드 추가 → 순서 확인 E2E; 라우팅 단위 테스트 |
| **완료 조건** | `/app/analysis/new`에서 빈 분석 생성, 입력 데이터셋 선택, 세로 캔버스에 카드 표시 |
| **예상 리스크** | 기존 경량 라우터(`routing.ts`)가 path parameter를 지원하는지 확인 필요 → 패턴 매칭 추가 |

#### P1-2. 데이터 변형 보드 5종

| 항목 | 내용 |
|------|------|
| **새 파일** | `web/src/features/analysis/boards/FilterBoard.tsx`, `GroupBoard.tsx`, `AggregateBoard.tsx`, `InputTableBoard.tsx`, `VerifyTableBoard.tsx` |
| **새 API** | `POST /api/analyses/{id}/boards/{boardId}/execute` (보드 단위 실행), `GET /api/analyses/{id}/boards/{boardId}/preview` |
| **UI 기능** | Filter: 컬럼 선택 + 연산자 + 값; Group: group by 컬럼 선택; Aggregate: 집계 함수 선택; Verify: 행수/스키마/null/중복/sample 표시 |
| **테스트 전략** | 각 보드의 config → SQL/쿼리 변환 단위 테스트; 빈 입력/대량 입력 엣지 케이스 |
| **완료 조건** | Input → Filter → Group → Aggregate → Chart 경로를 만들고 각 단계의 결과를 확인 가능 |
| **예상 리스크** | 서버사이드 쿼리 컴파일러 복잡도; SQL 인젝션 방지 → parameterized query 필수 |

#### P1-3. Result Inspector (결과 검증 패널)

| 항목 | 내용 |
|------|------|
| **새 파일** | `web/src/features/analysis/ResultPreview.tsx`, `SampleTable.tsx` |
| **UI 기능** | 행 수, 컬럼 목록, null 비율, 중복 key 수, sample 50행, upstream 데이터 버전, 실행 시간, 캐시 상태 |
| **테스트 전략** | 통계 계산 정확성 단위 테스트 |
| **완료 조건** | 모든 변형 보드에 접을 수 있는 Result Inspector가 표시됨 |
| **예상 리스크** | null rate/중복 계산 비용 → server에서 계산하여 결과와 함께 반환 |

#### P1-4. 데이터셋 저장 + 버전 관리

| 항목 | 내용 |
|------|------|
| **새 파일** | `web/src/features/analysis/SaveDatasetDialog.tsx` |
| **새 타입** | `DatasetRef {id, version}`, `SavedDataset` |
| **새 API** | `POST /api/analyses/{id}/save-dataset`, `GET /api/datasets`, `GET /api/datasets/{id}/versions` |
| **새 DB 테이블** | `datasets`, `dataset_versions` |
| **UI 기능** | "Save as Dataset" 대화상자 (이름, 설명), 저장된 데이터셋 목록, 버전 변경 시 영향 보드 안내 |
| **테스트 전략** | 저장 → 불러오기 E2E; 버전 변경 → 영향 분석 표시 |
| **완료 조건** | 분석 결과를 이름 있는 데이터셋으로 저장하고 다른 분석/대시보드에서 참조 가능 |
| **예상 리스크** | SQLite에서 materialized view 크기 제한 → row 수 상한 설정 |

#### P1-5. Analysis Share + Snapshot

| 항목 | 내용 |
|------|------|
| **새 파일** | `web/src/features/analysis/ShareDialog.tsx` |
| **새 타입** | `AnalysisSharePayload`, `AnalysisResultSnapshot` |
| **새 API** | `POST /api/analyses/{id}/share`, `GET /api/analyses/{id}/snapshots` |
| **UI 기능** | 분석 공유 링크 (파라미터 포함), 결과 스냅샷 (input versions + params + result hash + timestamp) |
| **테스트 전략** | 공유 링크 생성 → 복원 E2E; 스냅샷 재현성 검증 |
| **완료 조건** | 공유 링크 수신자가 같은 분석 상태를 볼 수 있음 (RBAC 재평가 적용) |
| **예상 리스크** | 공유 시 데이터 권한 누출 → server-side workspace/RBAC 재검증 필수 |

### P2 — 운영화 + 온톨로지 결합

> 목표: 관계 기반 Join, Ontology 그래프, Evidence drill-down, Action 실행, 배치 파이프라인 변환

#### P2-1. 관계 기반 Join 보드 + React Flow Lineage

| 항목 | 내용 |
|------|------|
| **새 파일** | `web/src/features/analysis/boards/JoinBoard.tsx`, `web/src/features/analysis/LineageGraph.tsx` |
| **새 라이브러리** | `@xyflow/react` |
| **UI 기능** | 허용 관계만 Join (RiskEvent→Equipment, Equipment→WorkOrder 등), cardinality 표시, 미매칭 행 수 경고; React Flow 기반 analysis path DAG + ontology object 관계 그래프 |
| **완료 조건** | Join 보드에서 관계 선택 → 결과 테이블 생성 + 미매칭 행 경고; Lineage 그래프에서 보드 간 흐름 시각화 |
| **예상 리스크** | 허용되지 않은 관계로의 Join 시도 → 서버 검증 필수 |

#### P2-2. Evidence Board drill-down + Action Board 실행

| 항목 | 내용 |
|------|------|
| **변경 파일** | `web/src/features/dashboard/DashboardBoardRenderer.tsx` (Evidence/Action 렌더러 확장) |
| **새 파일** | `web/src/features/dashboard/renderers/EvidenceDrilldown.tsx`, `web/src/features/dashboard/renderers/ActionExecutor.tsx` |
| **UI 기능** | Evidence: source reference 링크, factor contribution 시각화, report trace; Action: 점검 생성/배정/승인 UI (기존 `onFieldAction` 연결) |
| **완료 조건** | 테이블 행 클릭 → Evidence 출처 확인 → Action 실행 → audit log 기록 |
| **예상 리스크** | Action 실행 시 권한 확인 + Evidence 경계 우회 방지 |

#### P2-3. Analysis Spec → Batch Job Export

| 항목 | 내용 |
|------|------|
| **새 파일** | `web/src/features/analysis/ExportSpecDialog.tsx`, `api/ontology_dashboard/routers/batch_jobs.py` |
| **새 API** | `POST /api/analyses/{id}/export-spec`, `POST /api/batch-jobs` |
| **UI 기능** | "Export Analysis Spec" JSON 다운로드; 다음 단계에서 JSON → FastAPI batch job 정의로 컴파일 |
| **완료 조건** | 분석 경로를 JSON spec으로 내보내고, 해당 spec으로 배치 실행 가능 |
| **예상 리스크** | spec 포맷 호환성 유지 → 버전 관리 필요 |

#### P2-4. 비결정성/시간대 경고 + Analysis Run Audit

| 항목 | 내용 |
|------|------|
| **새 파일** | `web/src/features/analysis/NonDetWarning.tsx`, `web/src/features/analysis/TimezoneIndicator.tsx` |
| **새 DB 테이블** | `analysis_run_audit` (user_id, workspace_id, input_rows, output_rows, elapsed_ms, cache_hit, exported) |
| **UI 기능** | 정렬 없는 first/last, random sampling, now() 사용 시 ⚠ badge; 모든 보드에 timezone 표시; 관리자 화면에 실행 통계 |
| **완료 조건** | 비결정적 계산에 경고 표시; 모든 실행에 audit 기록 |
| **예상 리스크** | 비결정성 자동 감지 로직 복잡도 |

---

## 8. 현실적 범위 정의

### 8-A. "Palantir 전체 복제" vs "제조 예지보전 vertical Palantir급 경험"

```
❌ 복제 대상이 아닌 것:
  · Foundry 전체 데이터 인프라 (Object Storage, Spark, Data Connection)
  · Quiver (오브젝트 중심 로우코드 앱 빌더)
  · Pipeline Builder (코드 기반 데이터 파이프라인)
  · Code Workbook (Jupyter 대안)
  · AIP (대규모 LLM 통합 플랫폼)
  · 범용 BI 도구 기능 (Superset 수준의 SQL 탐색)
  · 실시간 3D 지구본 (palantir-demo 스타일)
  · 위성/항공기 추적 (Gods_Eye 스타일)

✅ 구현 범위: "제조 예지보전 vertical에서 Palantir급 경험"
  · Contour Analysis Path: 제조 도메인 데이터(RiskEvent, Equipment, MaintenanceRecord)에
    대해 Filter → Group → Aggregate → Chart 경로를 만들고 검증하는 분석 환경
  · Contour Dashboard: 12열 Grid에 차트·KPI·테이블·Evidence·Action을 배치하고,
    파라미터·차트 선택으로 교차 필터링하는 운영 대시보드
  · Ontology Integration: Object·Link·Action 기반 도메인 모델과 결합된 분석
  · Governed Action: 점검 생성·배정·승인·감사를 대시보드에서 직접 실행
  · Evidence Traceability: 모델 예측 → 근거 → 판단 → 행동의 전체 추적
```

### 8-B. 핵심 차별화 포인트 (Palantir도 하지 않는 것)

| 포인트 | 설명 |
|--------|------|
| **도메인 특화 온톨로지** | RiskEvent, Equipment, WorkOrder, MaintenanceRecord가 미리 정의된 관계와 함께 제공. 범용 Foundry와 달리 학습 곡선 최소화 |
| **Evidence 기반 의사결정** | 모든 Action에 Evidence hash, model version, policy version, confidence가 첨부. "왜 이 판단을 했는가"를 항상 추적 가능 |
| **RBAC 통합 대시보드** | 8개 역할별 맞춤 대시보드 템플릿. 동일 데이터에 대해 관리자/엔지니어/현장 기술자가 각자의 관점으로 소비 |
| **LLM Planner 연동** | `PlannerAssistantBoard`를 통해 AI가 대시보드 구성을 제안하는 기능 (현재 MVP 고유 강점) |

### 8-C. 현실적 마일스톤

```
Week 1-2 (P0-1, P0-2):
  → Dashboard에 react-grid-layout + ECharts 적용
  → 기존 대시보드가 드래그/리사이즈 가능한 12열 그리드로 전환
  → 최소 2종 차트(Bar, Line) 실제 데이터 렌더링

Week 3-4 (P0-3, P0-4, P0-5):
  → TanStack Table 결과 테이블
  → Chart-to-chart 교차 필터 실행
  → Parameter Rail 실제 query 연결
  → "Contour Dashboard 소비 화면" 완성

Week 5-7 (P1-1, P1-2, P1-3):
  → Analysis 라우트 + Shell
  → 데이터 변형 보드 5종 (Filter, Group, Aggregate, Input, Verify)
  → Result Inspector
  → "Analysis Path 편집 화면" MVP 완성

Week 8-9 (P1-4, P1-5):
  → 데이터셋 저장/버전
  → 분석 공유/스냅샷

Week 10+ (P2):
  → Join 보드 + React Flow
  → Evidence drill-down + Action 실행
  → 배치 export
  → 비결정성/시간대 경고 + Audit
```

### 8-D. 성공 기준 (Palantir급 경험의 판단 지표)

| # | 기준 | 측정 |
|---|------|------|
| 1 | 분석가가 Risk Event 입력에서 Filter → Group → Aggregate → Chart 경로를 5분 내에 만들 수 있다 | 첫 사용 테스트 시간 |
| 2 | 운영자가 기간·라인·고장유형을 바꾸면 관련 보드만 1초 내에 다시 계산된다 | query 재실행 시간 |
| 3 | 막대/점/테이블 행 선택이 Evidence와 Action 보드까지 전파된다 | 교차 필터 체인 길이 |
| 4 | 보드마다 입력 데이터 버전·시간대·행 수·실행 시간·Evidence 출처를 확인할 수 있다 | Result Inspector 필드 수 |
| 5 | 공유 링크와 PDF snapshot은 권한을 우회하지 않고, 재현 가능한 metadata를 남긴다 | 공유 → 복원 정확도 |
| 6 | 8개 역할 중 최소 3개(process_engineer, process_manager, maintenance_technician)에서 대시보드가 즉시 유용하다 | 역할별 사용성 테스트 |

---

## 부록: 파일 경로 요약

### 현재 MVP 핵심 파일

| 파일 | 역할 |
|------|------|
| `web/src/features/dashboard/types.ts` | 대시보드 타입 시스템 (Board, Tab, Parameter, Dependency) |
| `web/src/features/dashboard/DashboardShell.tsx` | 대시보드 레이아웃 쉘 (헤더, 탭, 툴바, 슬롯) |
| `web/src/features/dashboard/BoardCanvas.tsx` | 보드 그리드 캔버스 (현재 `gridColumn: span N`) |
| `web/src/features/dashboard/ContextPanel.tsx` | 좌측 파라미터/Object Context 패널 |
| `web/src/features/dashboard/BoardInspector.tsx` | 우측 보드 Inspector (제목, 폭, 바인딩) |
| `web/src/features/dashboard/DashboardBoardRenderer.tsx` | 보드 렌더러 팩토리 (14개 legacy + 5개 platform) |
| `web/src/features/manufacturing/ManufacturingApp.tsx` | 제조 도메인 오케스트레이터 |
| `web/src/types.ts` | 전역 타입 (AppRole, Evidence, Report, Layout, UIBlock) |
| `web/src/styles.css` | 전체 CSS (57KB, 디자인 토큰, 12열 grid, 애니메이션) |
| `web/src/routing.ts` | 경량 라우터 (pushState + popstate) |
| `web/src/api.ts` | API 클라이언트 (17KB) |
| `api/ontology_dashboard/routers/` | FastAPI 라우터 12개 (ontology, dashboards, auth 등) |

### 레퍼런스 프로젝트 핵심 파일

| 레퍼런스 | 핵심 참고 파일 |
|---------|-------------|
| mini_foundry_public | `frontend/components/dashboards/DashboardCanvas.tsx` (react-grid-layout), `DataBindingPanel.tsx`, `FilterBar.tsx`, `OntologyGraph.tsx` (React Flow) |
| openfoundry-emulator | `apps/app-console/src/pages/Contour.tsx` (순차 파이프라인), `apps/app-workshop/src/components/Canvas.tsx`, `src/widgets/widget-registry.ts` |
| contour-translation | `contour_translator.py`, `contour_render_specs.py` (render spec 정규화) |
| palantir-blueprint | `packages/core/src/components/` (UI primitives) |
| OpenFoundry | `apps/web/src/lib/components/` (아키텍처 참고) |
| palantir-demo | `src/components/Dashboard.jsx` (시각 영감) |
| Gods_Eye | `src/components/Globe.jsx`, `src/store/` (zustand, 시각 영감) |

---

> **문서 끝.** 이 문서는 읽기·분석·설계 제안만 포함하며, 기존 코드를 수정하지 않았습니다.
