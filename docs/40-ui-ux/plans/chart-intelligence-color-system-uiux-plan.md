# Ontology Dashboard — Color System and Chart Intelligence UI/UX Plan

- 작성일: 2026-08-03
- 목표: 사용자 제공 팔레트를 제품 전역에 적용하고, 동일한 데이터에 대해 `Auto` 추천과 수동 chart 전환이 가능한 Foundry형 visualization UX를 구현한다.
- 우선순위: UI/UX 구현 최우선
- 이번 계획의 검증 원칙: 전체 release gate, 전체 pytest, 전체 Playwright, 기존 48장 visual baseline 재생성은 기본 작업 범위에서 제외한다. 구현 중에는 TypeScript와 기능별 짧은 browser smoke만 사용하고, 전체 gate는 사용자가 별도로 요청할 때만 실행한다.
- 사용자 제공 색상 reference: conversation attachment `file_000000002a848209bd25f125d9ae580e`

---

## 1. 현재 구현에 대한 판정

### 결론

현재 구현은 **chart runtime의 기초는 존재하지만, 사용자가 기대하는 chart intelligence UI/UX는 아직 완성되지 않았다.**

이미 구현된 부분:

1. `RenderKind`에 다음 표현이 등록돼 있다.

   ```text
   metric
   bar
   line
   pie
   histogram
   table
   ontology
   activity
   ```

2. `EChartsRenderer`는 `bar`, `line`, `pie`, `histogram`을 하나의 generic renderer에서 그릴 수 있다.
3. `CatalogDataBoard`와 `AnalysisReferenceBoard`는 API가 반환한 `render_spec`에 따라 chart/table/metric renderer를 선택한다.
4. server query contract에는 `x_field`, `y_field`, `value_field`, `group_field`, `aggregation`, `selectable`, `brushable`이 존재한다.
5. Analysis runtime 일부는 결과 node에 `render_spec`을 생성한다.
6. cross-filter click/brush가 generic chart에 연결돼 있다.
7. Planner는 역할, 목표, 현재 배치, 숨김 여부, width signal을 사용해 Catalog Board를 추천한다.

아직 구현되지 않은 부분:

1. 데이터 profile을 분석해 chart 종류를 점수화하는 visualization recommendation engine이 없다.
2. Planner/LLM은 Board definition을 추천할 뿐 chart 종류와 field mapping을 추천하지 않는다.
3. `Auto` visualization mode가 없다.
4. 같은 데이터에서 chart 종류만 즉시 바꾸는 Board header UI가 없다.
5. Board Inspector에 Visualization section이 없다.
6. chart 변경을 user/workspace/tab/board scope로 저장하는 override contract가 없다.
7. 자동 추천 근거와 대안 chart 목록이 없다.
8. 호환되지 않는 chart를 비활성화하고 이유를 설명하는 UX가 없다.
9. scatter, area, stacked/grouped bar, heatmap 등 실무적인 chart pool이 충분하지 않다.
10. ECharts option 내부에 기존 파란색·주황색 값이 직접 하드코딩돼 있어 새 palette가 chart와 product chrome에 일관되게 적용되지 않는다.

따라서 현재 상태를 다음처럼 보는 것이 정확하다.

```text
Chart renderer foundation             있음
Server-driven render_spec             있음
Cross-filter chart interaction        있음
AI Board recommendation               있음
AI visualization recommendation       없음
User chart switcher                   없음
Visualization override persistence    없음
Recommended alternatives/rationale    없음
```

---

## 2. 새 색상 시스템

### 2.1 Canonical palette

#### Brand and accent

| Token role | Value | Usage |
|---|---|---|
| Navy / primary | `#0C1C74` | primary action, active navigation, selected series, links, focus |
| Slate / ink | `#3A4950` | primary ink, dark surface, subdued navigation |
| Orange / accent | `#E64D2B` | highlight, active comparison, selected alternative, attention |
| Red / reserved | `#DB0714` | destructive action, danger, critical state only |

#### Semantic states

| Token role | Value |
|---|---|
| Info / action | `#0C1C74` |
| Success | `#29A634` |
| Warning | `#D1970C` |
| Danger | `#DB0714` |

#### Categorical chart series

```text
01 #0C1C74
02 #E64D2B
03 #00A396
04 #D1970C
05 #7861DB
06 #29A634
07 #DA2D6F
08 #5F6B7B
```

#### Neutral scale

```text
White       #FFFFFF
Canvas      #F7F8F9
Border      #DCDCDD
Muted ink   #5F6B7B
Strong ink  #3A4950
```

### 2.2 Token design

`web/src/ui/foundry/tokens.css`에서 색상값을 semantic token으로 정의한다.

권장 구조:

```css
--od-brand-primary: #0c1c74;
--od-brand-ink: #3a4950;
--od-brand-accent: #e64d2b;
--od-brand-reserved: #db0714;

--od-state-info: #0c1c74;
--od-state-success: #29a634;
--od-state-warning: #d1970c;
--od-state-danger: #db0714;

--od-series-1: #0c1c74;
--od-series-2: #e64d2b;
--od-series-3: #00a396;
--od-series-4: #d1970c;
--od-series-5: #7861db;
--od-series-6: #29a634;
--od-series-7: #da2d6f;
--od-series-8: #5f6b7b;

--od-neutral-0: #ffffff;
--od-neutral-50: #f7f8f9;
--od-neutral-300: #dcdcdd;
--od-neutral-600: #5f6b7b;
--od-neutral-800: #3a4950;
```

기존 `--fd-*` token은 새 canonical token을 참조하도록 바꾸고 feature CSS가 직접 hex를 추가하지 않게 한다.

### 2.3 Usage rules

1. Navy는 primary action과 selected state의 기본값이다.
2. Orange는 보조 accent와 비교 강조에만 사용한다.
3. Red는 delete, deny, failed, critical에만 사용한다.
4. Warning과 Orange accent를 같은 의미로 혼용하지 않는다.
5. chart series는 category 순서가 바뀌어도 동일 category가 같은 color를 유지하도록 stable hashing을 사용한다.
6. selected point는 단순히 색만 바꾸지 말고 outline, opacity, marker 크기 중 하나를 함께 사용한다.
7. dark theme에서는 categorical hue는 유지하고 canvas/surface/text만 별도 semantic token으로 조정한다.
8. chart option 안의 직접 hex를 제거하고 TypeScript palette helper가 CSS token과 동일한 canonical 값에서 생성되게 한다.

### 2.4 Primary migration targets

```text
web/src/ui/foundry/tokens.css
web/src/ui/foundry/convergence.css
web/src/ui/foundry/interaction-polish.css
web/src/features/auth/auth-control-plane.css
web/src/features/admin/admin-control-plane.css
web/src/features/dashboard/dashboard-runtime.css
web/src/features/dashboard/dashboard-editor.css
web/src/features/analysis/analysis-detail.css
web/src/features/ontology/object-explorer-detail.css
web/src/ui/foundry/chartPalette.ts
web/src/features/dashboard/renderers/EChartsRenderer.tsx
web/src/features/dashboard/EChartRuntime.tsx
web/src/features/dashboard/EChartCartesianCanvas.tsx
web/src/features/dashboard/EChartPieCanvas.tsx
```

---

## 3. Target visualization experience

### 3.1 User flow

Board가 처음 로드되면:

1. 데이터 schema와 profile을 분석한다.
2. `Auto` mode가 적합한 chart와 field mapping을 선택한다.
3. Board header에 다음을 보여준다.

   ```text
   Auto · Line
   ```

4. 사용자가 해당 chip을 누르면 `Visualize as` menu가 열린다.
5. menu 상단에는 추천 chart와 이유를 표시한다.
6. 그 아래에는 호환 가능한 alternative chart를 mini preview와 함께 보여준다.
7. chart를 바꾸면 동일한 rows와 filter state를 유지한 채 renderer만 즉시 전환한다.
8. manual 선택 이후에는 다음처럼 표시한다.

   ```text
   Manual · Bar
   Reset to Auto
   ```

9. 변경은 현재 user/project/workspace/dashboard/tab/board scope로 저장된다.
10. reload와 재로그인 후 복원된다.

### 3.2 Board header quick switcher

Chart-capable Board의 header action 영역에 visualization button을 둔다.

예시:

```text
[ Auto · Line ▾ ]
```

menu 구성:

```text
Recommended
  Line chart
  Time field와 연속 numeric value가 감지됨

Alternatives
  Area
  Bar
  Table

Unavailable
  Pie — category cardinality가 너무 높음
  Scatter — 두 번째 numeric field가 없음
```

규칙:

- view mode에서도 chart 전환 가능
- arrange mode와 독립적으로 동작
- chart 전환이 board click/drag/long-press를 방해하지 않음
- keyboard로 열고 arrow/enter/escape 사용 가능
- mobile에서는 bottom sheet 형태 허용

### 3.3 Visualization Inspector

Board Inspector에 `Visualization` section을 추가한다.

필드:

```text
Mode                 Auto / Manual
Chart type           Line / Area / Bar / Stacked bar / Pie / ...
X axis               field selector
Y axis / Value       field selector
Series / Color       optional field selector
Aggregation          count / sum / avg / min / max
Sort                 auto / ascending / descending
Orientation          vertical / horizontal
Stack                off / normal / percent
Legend               auto / show / hide
Labels               auto / show / hide
Curve                 straight / smooth / step
Color strategy       categorical / semantic / single accent
```

Auto mode에서는 현재 추천 결과를 읽기 전용으로 보여주고 `Edit manually` 버튼을 제공한다.

### 3.4 Recommendation explanation

사용자가 추천 근거를 확인할 수 있어야 한다.

예시:

```text
Why Line?
- timestamp cardinality 96
- numeric value field: average_risk
- ordered temporal sequence detected
- 3 categories, suitable for color series
```

AI가 사용된 경우에도 결과는 typed rule 결과와 함께 표시한다.

```text
Recommended by: deterministic profile + AI intent hint
Validated against: chart registry v1
```

---

## 4. Chart pool

### 4.1 Phase-1 supported pool

처음부터 수십 개를 얕게 만들지 말고, 실제 사용성이 높은 10개를 완성도 있게 구현한다.

```text
auto
metric
table
bar
stacked_bar
line
area
pie / donut
histogram
scatter
heatmap
```

`pie`는 renderer 내부 option으로 donut style을 기본값으로 두고 `pie_style`로 full pie를 허용한다.

### 4.2 Later pool

다음은 phase-1 이후의 선택적 확장이다.

```text
treemap
waterfall
funnel
box_plot
radar
gauge
sankey
calendar_heatmap
```

### 4.3 Chart registry

frontend와 backend가 동일한 registry contract를 공유해야 한다.

권장 타입:

```ts
interface VisualizationDefinition {
  kind: VisualizationKind;
  displayName: string;
  icon: LucideIcon;
  intent: "comparison" | "trend" | "composition" | "distribution" | "relationship" | "detail" | "summary";
  requiredChannels: ChannelRequirement[];
  optionalChannels: ChannelRequirement[];
  constraints: VisualizationConstraint[];
  supportsSelection: boolean;
  supportsBrush: boolean;
  supportsSeries: boolean;
  supportsStack: boolean;
}
```

backend는 icon을 제외한 동일 schema를 Pydantic model로 가진다.

Registry 밖의 chart kind는 API와 LLM 모두 거부한다.

---

## 5. Data profiling and recommendation engine

### 5.1 Field profile

Board query response에 visualization 추천에 필요한 profile을 추가한다.

```text
field id
inferred semantic type
physical type
null ratio
distinct count
cardinality ratio
min / max
numeric distribution summary
temporal ordering
sample values
identifier likelihood
latitude/longitude likelihood
```

Semantic type 예시:

```text
identifier
categorical
ordinal
quantitative
temporal
boolean
text
geo
```

### 5.2 Deterministic ranking

AI 호출 전 deterministic scoring을 먼저 구현한다.

예시 규칙:

```text
temporal + quantitative                       → line / area
categorical low-cardinality + quantitative    → bar / donut
categorical high-cardinality                  → bar / table
one quantitative field                        → histogram / metric
two quantitative fields                       → scatter
two categorical dimensions + quantitative     → heatmap
small summary record                          → metric
wide record detail                            → table
```

각 후보는 다음을 반환한다.

```json
{
  "kind": "line",
  "score": 0.94,
  "field_mapping": {
    "x": "timestamp",
    "y": "average_risk",
    "series": "line"
  },
  "reason_codes": [
    "temporal_sequence",
    "continuous_numeric_measure",
    "low_series_cardinality"
  ]
}
```

### 5.3 AI-assisted intent

기존 Planner에 chart recommendation을 추가하되 LLM은 다음 역할만 한다.

- 사용자 goal을 visualization intent로 분류
- deterministic 후보의 순서를 조정
- 사람이 읽을 수 있는 짧은 rationale 작성

LLM이 할 수 없는 것:

- registry에 없는 chart 생성
- 존재하지 않는 field 선택
- unsupported aggregation 생성
- permission이나 project scope 우회
- query 결과를 변경하거나 arbitrary code 생성

권장 API:

```text
POST /api/planner/visualizations/recommend
```

Request:

```json
{
  "workspace_id": "...",
  "dashboard_id": "...",
  "board_id": "...",
  "goal": "시간에 따른 위험도 변화와 라인별 차이를 보고 싶다",
  "use_llm": true
}
```

Response:

```json
{
  "mode": "deterministic | llm | deterministic_fallback",
  "recommended": {},
  "alternatives": [],
  "profile": {},
  "validation": {
    "registry_whitelist": true,
    "fields_exist": true,
    "scope_enforced": true
  }
}
```

---

## 6. Persistence contract

### 6.1 Board settings

기존 additive `board.settings`를 활용해 병렬 preference system을 만들지 않는다.

권장 shape:

```json
{
  "visualization": {
    "version": 1,
    "mode": "auto",
    "kind": "line",
    "field_mapping": {
      "x": "timestamp",
      "y": "average_risk",
      "series": "line"
    },
    "aggregation": "avg",
    "sort": "auto",
    "orientation": "vertical",
    "stack": "off",
    "legend": "auto",
    "labels": "auto",
    "curve": "smooth",
    "color_strategy": "categorical",
    "recommendation_revision": "profile-hash"
  }
}
```

### 6.2 Resolution order

```text
manual board override
→ auto recommendation from current profile
→ API render_spec
→ catalog default_render_spec
→ safe table fallback
```

### 6.3 Invalidation

Auto recommendation은 data profile hash가 바뀌면 재계산한다.

Manual override는 schema field가 사라진 경우에만 invalid 상태로 표시하고 자동으로 파괴하지 않는다.

사용자에게 다음 선택을 제공한다.

```text
Repair mapping
Reset to Auto
Keep table fallback
```

---

## 7. Implementation phases

## Phase 0 — Current-state inventory and palette foundation

목표:

- 기존 renderer, hardcoded colors, render_spec, board settings 흐름을 정확히 inventory
- canonical palette token과 TypeScript chart palette helper 구현

작업:

1. `tokens.css`에 사용자 palette 추가
2. 기존 semantic token mapping 교체
3. `chartPalette.ts` 추가
4. ECharts hardcoded colors 제거
5. light/dark surface contrast 조정
6. Dashboard, Auth, Admin, Analysis, Object Explorer 핵심 화면에 palette 적용

완료 조건:

- primary navy, orange accent, reserved red 규칙이 실제 UI에서 구분됨
- categorical 8색이 chart에 순서대로 반영됨
- chart option에 기존 `#2d72d2`, `#d9822b` 직접값이 남지 않음

## Phase 1 — Visualization registry and generic renderer expansion

목표:

- chart pool을 typed registry로 만들고 generic ECharts renderer가 10개 핵심 kind를 지원

작업:

1. `VisualizationKind`와 registry 정의
2. `RenderSpec`를 backward-compatible하게 확장
3. bar/stacked bar/line/area/pie-donut/histogram/scatter/heatmap 구현
4. table/metric은 동일 switcher에서 선택 가능하게 통합
5. stable category color mapping
6. selection/brush contract 보존

완료 조건:

- 동일 rows로 지원 chart를 즉시 교체 가능
- unsupported mapping은 error 대신 disabled option과 설명 제공

## Phase 2 — Data profile and deterministic recommendation

목표:

- 데이터에 맞는 chart와 field mapping을 자동 추천

작업:

1. server query response에 field profile 추가
2. visualization compatibility scoring 구현
3. primary + alternatives + reason code 반환
4. profile hash와 recommendation revision 생성
5. `Auto` resolution을 CatalogDataBoard와 AnalysisReferenceBoard에 연결

완료 조건:

- time series, category comparison, distribution, relationship fixture에서 기대한 추천이 나옴
- AI 없이도 항상 deterministic recommendation 가능

## Phase 3 — Board header `Visualize as` UX

목표:

- 주식 앱처럼 같은 데이터의 표현을 즉시 변경

작업:

1. Board header chart chip 추가
2. recommended/alternative/unavailable menu 구현
3. mini chart preview 또는 icon preview
4. `Auto`와 `Manual` 상태 표시
5. `Reset to Auto`
6. keyboard/mobile interaction
7. chart change 시 query/filter/selection state 유지

완료 조건:

- view mode에서 chart 변경 가능
- arrange drag와 충돌하지 않음
- reload 전에도 즉시 반영

## Phase 4 — Visualization Inspector and persistence

목표:

- 세부 field mapping과 style을 사용자가 편집하고 저장

작업:

1. Inspector `Visualization` section
2. field selectors와 aggregation controls
3. orientation, stack, legend, labels, curve, color strategy
4. `board.settings.visualization` serialization
5. 기존 Dashboard preference save/reload/login restoration 사용
6. schema drift repair state
7. undo/redo와 draft recovery에 포함

완료 조건:

- manual chart override가 reload와 재로그인 후 복원됨
- undo/redo가 chart 변경도 되돌림
- saved view와 share가 명시된 범위에서 visualization state를 유지

## Phase 5 — AI visualization recommendation

목표:

- 기존 Planner가 Board 추천뿐 아니라 chart recommendation도 수행

작업:

1. typed request/response model
2. deterministic candidate를 LLM 입력으로 제공
3. registry whitelist와 field validation
4. natural-language intent 입력 UI
5. recommendation rationale 표시
6. provider unavailable fallback

완료 조건:

- LLM이 registry 밖 chart를 만들 수 없음
- AI 실패 시 deterministic recommendation 유지
- 사용자가 추천을 preview 후 적용

## Phase 6 — UI polish

목표:

- Foundry형 고밀도 authoring 경험 완성

작업:

1. chart switch menu hierarchy와 spacing polish
2. hover/focus/selected states
3. empty/insufficient-data state
4. chart transition animation과 reduced-motion
5. 720px bottom sheet
6. chart palette legend와 semantic state legend 구분
7. Board Catalog preview를 실제 renderer preview로 개선

완료 조건:

- chart 전환이 빠르고 설명 가능하며 모바일에서도 사용 가능
- 색상과 hierarchy가 전체 workbench에 일관됨

---

## 8. Primary files

```text
web/src/ui/foundry/tokens.css
web/src/ui/foundry/chartPalette.ts
web/src/ui/foundry/ChartPanel.tsx
web/src/ui/foundry/BoardFrame.tsx
web/src/features/dashboard/types.ts
web/src/features/dashboard/CatalogDataBoard.tsx
web/src/features/dashboard/AnalysisReferenceBoard.tsx
web/src/features/dashboard/renderers/EChartsRenderer.tsx
web/src/features/dashboard/renderers/DataTableRenderer.tsx
web/src/features/dashboard/renderers/MetricRenderer.tsx
web/src/features/dashboard/BoardInspector.tsx
web/src/features/dashboard/DashboardBoardRenderer.tsx
web/src/features/dashboard/DashboardGridCanvas.tsx
web/src/features/manufacturing/ManufacturingApp.tsx
web/src/features/manufacturing/useDashboardEditor.ts
api/ontology_dashboard/dashboard_models.py
api/ontology_dashboard/dashboard_service.py
api/ontology_dashboard/dashboard_catalog.py
api/ontology_dashboard/analysis_service.py
api/ontology_dashboard/planner/models.py
api/ontology_dashboard/planner/service.py
api/ontology_dashboard/routers/planner.py
```

새 파일 후보:

```text
web/src/features/dashboard/visualization/visualizationRegistry.ts
web/src/features/dashboard/visualization/visualizationProfile.ts
web/src/features/dashboard/visualization/VisualizationSwitcher.tsx
web/src/features/dashboard/visualization/VisualizationInspector.tsx
web/src/features/dashboard/visualization/visualization.css
api/ontology_dashboard/visualizations/models.py
api/ontology_dashboard/visualizations/profiler.py
api/ontology_dashboard/visualizations/recommender.py
```

---

## 9. UIUX-first execution rules

이번 작업은 다음 원칙을 지킨다.

1. 전체 release gate를 실행하지 않는다.
2. 전체 backend pytest를 실행하지 않는다.
3. 전체 Playwright를 실행하지 않는다.
4. 기존 48장 visual baseline을 자동 재생성하지 않는다.
5. threshold 조정이나 CI 보정에 시간을 사용하지 않는다.
6. 각 Phase 종료 후 필요한 경우 다음만 수행한다.

   ```text
   TypeScript noEmit
   production build 1회
   변경 기능 전용 browser smoke 1~3개
   실제 1440x1000 / 720x500 수동 확인
   ```

7. 작은 CSS 차이 때문에 기능 구현을 중단하지 않는다.
8. 사용자에게 보이는 chart switcher와 Inspector를 먼저 완성하고, broad regression은 뒤로 미룬다.
9. 테스트를 추가해야 한다면 chart recommendation과 persistence를 직접 보호하는 작은 테스트만 추가한다.
10. 사용자가 별도로 요청할 때만 release gate와 전체 visual regression을 수행한다.

---

## 10. Definition of done

1. 사용자 제공 palette가 global token과 chart palette에 적용됨
2. red가 destructive/danger 외 용도로 사용되지 않음
3. chart-capable Board에 `Auto / Manual` switcher가 표시됨
4. 같은 rows를 table, metric, bar, line, area, pie, histogram, scatter, heatmap으로 호환 범위 내에서 변경 가능
5. 데이터 profile 기반 primary recommendation과 alternatives가 표시됨
6. 추천 이유를 확인할 수 있음
7. manual visualization override가 Dashboard preference에 저장됨
8. reload와 재로그인 후 복원됨
9. cross-filter, brush, inspector selection이 chart 전환 후에도 유지됨
10. AI는 registry와 실제 field만 선택할 수 있음
11. AI unavailable 시 deterministic Auto mode가 정상 동작함
12. 720px에서 chart switcher가 사용할 수 있음

