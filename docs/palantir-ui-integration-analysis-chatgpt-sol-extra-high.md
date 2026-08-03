# Palantir Contour/Foundry UI 접목 상세 분석 — mvp-프로젝트2

> 작성일: 2026-08-01
> 성격: **읽기·분석·설계 제안 문서**. 이 문서는 기존 코드/설정을 전혀 수정하지 않으며, `docs/palantir-contour-ui-reference.md`(공식 문서 25개 기반 구현 노트)와 `docs/palantir-contour-dashboard-benchmark.md`(첨부 화면 4개 + 공식 문서 벤치마크)를 전제로, **① 현재 코드와 정확히 대조한 gap 분석, ② 로컬 레퍼런스 7개의 파일 단위 실사, ③ 화면 구조·API 계약·로드맵의 실행 가능한 설계안**을 추가한다. 세 문서는 서로 대체하지 않고 아래처럼 역할이 나뉜다.

```text
palantir-contour-ui-reference.md        → "무엇을 왜 만드는가" (공식 문서 25개 → MVP 적용 원칙)
palantir-contour-dashboard-benchmark.md → "화면이 어떻게 동작해야 하는가" (첨부 화면 4개 → 인터랙션 벤치마크)
palantir-ui-integration-analysis.md(본 문서) → "지금 코드에서 무엇을 어떻게 바꾸는가" (gap 분석 + 레퍼런스 실사 + 계약/로드맵)
```

---

## 0. 분석 대상 요약

| 구분 | 경로 | 비고 |
|---|---|---|
| MVP 루트 | `mvp-프로젝트2/` | Backend 93% / Frontend 89% / Architecture 95% (`docs/07-implementation-status.md` 기준, 2026-08-01) |
| Dashboard 프론트 | `web/src/features/dashboard/*`, `web/src/features/manufacturing/*` | React + Vite, CSS는 `web/src/styles.css` 커스텀 디자인 시스템 |
| Dashboard 백엔드 | `api/factory_signal_board/dashboard_*.py`, `api/ontology_dashboard/routers/dashboards.py` | FastAPI + SQLite(로컬) / PostgreSQL(전환 70%) |
| Ontology 백엔드 | `api/factory_signal_board/ontology_service.py`, `ontology.py`, `ontology_adapter.py` | Object/Link/Action 모델이 이미 구현되어 있음 |
| 레퍼런스 루트 | `레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/` | 7개 프로젝트, 라이선스 3종(MIT/Apache-2.0/GPL-3.0/불명) 혼재 |

---

## 1. 현재 MVP에 이미 있는 기능 vs 실제로 부족한 기능

### 1-1. 이미 구현되어 있는 Palantir/Contour 유사 기능 (파일·코드 근거)

| 기능 | 근거 파일 | 코드 근거 | Contour/Palantir 대응 개념 |
|---|---|---|---|
| Board 단위 구성 + Tab | `dashboard_models.py`(`DashboardTab`, `DashboardBoard`), `DashboardShell.tsx` | `tabs[].boards[]`, `order` 기반 정렬(`utils.ts normalizeTabs`) | Boards + Dashboard tabs |
| Board Catalog(카테고리 7종·검색·역할 필터) | `dashboard_catalog.py`(`BOARD_CATALOG` 45개 정의), `BoardCatalogPanel.tsx` | category는 suggested / observe / explore / explain / act / audit / build, 별도 `allowed_roles` | Board toolbar category |
| 탭/보드에 추가(기존 탭 선택·새 탭 생성) | `utils.ts`(`addCatalogBoard`, `addCustomTab`) | `custom:${definitionId}:${uuid}` 신규 board id 채번 | "Add to dashboard" dropdown |
| 좌측 Parameter/Filter rail | `dashboard_catalog.py`(`PARAMETER_DEFINITIONS`), `ContextPanel.tsx` | `selected_event_id`, `status_filter`, `intent` 3+1종 typed parameter | Parameter panel |
| Cross-filter를 위한 dependency hint + "N boards affected" | `dashboard_service.py`(`_dependency_graph`), `ManufacturingApp.tsx`(`showAffected`) | `emits ∩ accepts` 교집합으로 `DependencyEdge[]` 계산, direct target를 1.8초 하이라이트 | Contour의 "Affects N boards"와 유사한 **시각적 affordance**. 실제 chart selection predicate 전파·하류 query 재실행은 아님 |
| View/Edit 모드 분리 | `DashboardShell.tsx`(`mode` prop) | `view-edit-switch`, edit 모드에서만 Inspector/Catalog 노출 | Palantir viewer/editor 분리 |
| 역할 Template ↔ 개인 Preference 병합 | `dashboard_repository.py`(`dashboard_templates`, `dashboard_template_versions`, `dashboard_user_preferences` 3테이블), `dashboard_service.py`(`_resolve_template`, `_apply_preference_payload`) | `template_version`/`preference_revision`, override diff 저장(`_preference_payload_from_tabs`), `merge_notices` | 역할 default + 사용자 영구 override를 위한 강한 기반 |
| Saved View | `dashboard_repository.py`(`dashboard_saved_views`), `ContextPanel.tsx` | `SavedViewRecord{active_tab_id, tabs, parameter_state}` | Saved View |
| Share Link(만료·workspace 재검증) | `dashboard_repository.py`(`dashboard_shares`, `token_hash`, `expires_at`), `dashboard_service.py`(`create_share`/`resolve_share`) | 기본 72시간, 서버에서 workspace/이벤트 재검증 | Share Link |
| PDF/CSV/JSON export + 감사 checkpoint | `export_models.py`(`ExportCheckpoint{snapshot_hash, content_hash, requested_by}`) | 재현 가능한 export 감사 기록 | Export/Checkpoint |
| Board 전체화면 | `BoardCanvas.tsx`(`fullscreenBoardId`) | `is-fullscreen` 클래스 토글 | Board fullscreen |
| Text Board + 안전 검증 | `dashboard_catalog.py`("text-board"), `dashboard_service.py`(`UNSAFE_TEXT` 정규식) | HTML tag, javascript scheme, event-handler 형태를 거부 | Text Board |
| Object/Link/Action Ontology 코어 | `ontology.py`, `ontology_service.py`, `web/src/features/ontology/types.ts` | `query_objects`/`traverse`/`invoke`, `idempotency_key` 재생 방지 | Ontology Objects/Actions |
| Governed Action + 감사 | `ontology_service.py`(`invoke`, `reserve/succeed/fail`) | RBAC 권한 검사 → 실행 → `record_audit` | Action Types + permission(벤치마크 6절) — **MVP가 이미 이 모델을 상당히 구현하고 있음** |
| RBAC/tenant scope | `dashboard_service.py`(`_validate_board`), `project_context.py`(`ensure_scope_columns`) | 8개 `AppRole`, org/project/workspace 3단 scope | Object/Data/Action permission 분리(벤치마크 6절) |

**결론**: Dashboard "소비 화면"의 뼈대(Tab, Board, Parameter, dependency hint, View/Edit, 개인화, Saved View, Share, Export, RBAC)는 이미 Contour의 Dashboard 레이어와 개념적으로 대응된다. 특히 역할 template·사용자 개인화, governed action, tenant 격리는 재사용할 가치가 높은 강점이다. 다만 현재 affected highlight를 실제 cross-filter로 과대평가해서는 안 된다.

### 1-2. 실제로 부족한 기능 (UI/분석 측면)

| 부족 기능 | 현재 상태 | 관련 파일 | 부족한 이유 / 필요성 |
|---|---|---|---|
| **Analysis 편집 화면(분석 경로)** | 없음. 모든 Board는 고정 렌더러이며 "행 집합을 변형해 다음 Board에 넘긴다"는 개념 자체가 없음 | `dashboard_catalog.py`(변환용 board 정의 0개) | Contour의 핵심인 `Filter → Group → Aggregate → Chart` 경로가 전혀 없음. `/app/analysis/:id` 라우트 자체가 없음(`web/src/routing.ts`) |
| **x/y/w/h 자유 배치 grid** | `width: Literal[4,6,12]` span만 존재, y좌표 없음, DOM 순서(`order`)로만 세로 배치 | `dashboard_models.py`(`DashboardBoard.width`), `BoardCanvas.tsx`(`style={{ gridColumn: \`span ${board.width}\` }}`) | 자유 드래그/리사이즈 불가. board 삭제·이동은 리스트 splice(`utils.ts moveBoard`)로만 가능 |
| **render_spec(선언적 렌더 계약)** | `renderer` 필드가 고정 문자열이고 `DashboardBoardRenderer.tsx`의 250줄짜리 switch 문으로 하드코딩 | `DashboardBoardRenderer.tsx`(`LEGACY_RENDERERS` Set + `switch(definition.renderer)`) | 새 board 타입 추가 시 FE·BE를 동시에 코드 수정해야 함. 데이터 기반으로 새 board를 확장할 수 없음 |
| **Table 결과 검증(Result Inspector)** | `EvidenceTable` 등은 고정 컬럼의 완성된 렌더러일 뿐, 행 수/스키마/null-rate/중복 key/샘플을 보여주는 중간 검증 단계가 없음 | `DashboardBoardRenderer.tsx` | Contour "결과 확인"(레퍼런스 문서 C-14) 단계 부재 |
| **Group/Aggregate 서버 API** | `query_objects()`는 `object_type/search/offset/limit`만 지원 | `ontology_service.py`(`query_objects`) | `group_by`/`metrics` 파라미터가 없어 집계 board를 만들 수 없음 |
| **Join(허용 관계)** | 없음. `traverse()`로 관계 탐색은 가능하나 board화되어 있지 않음 | `ontology_service.py`(`traverse`) | `RiskEvent↔Equipment↔Evidence` 관계를 분석 경로 안에서 조합할 수단이 없음 |
| **Object/Lineage 그래프 UI** | 백엔드 `traverse()`는 있지만 이를 그리는 프론트 컴포넌트가 전혀 없음 | 프론트 대응 파일 없음(`web/src/features/ontology/`에는 `types.ts`만 존재) | React Flow 등 그래프 렌더러 부재 |
| **데이터 버전/시간대/비결정성 표시** | 없음 | — | 벤치마크 문서가 요구하는 `DatasetRef`, workspace timezone 렌더링, non-determinism warning badge 없음 |
| **Analysis 결과 스냅샷/재현성** | `ExportCheckpoint`는 dashboard/event/role_workspace 운영 snapshot과 hash를 지원하지만 Analysis run 이력은 없음 | `export_models.py`, `export_service.py` | `AnalysisRun`/`DatasetRef`/board result hash를 export manifest와 연결하는 계약이 없음 |
| **이중 렌더링 체계 미정리** | `UIBlock`(사건별 LLM/결정론적 `Layout` 생성) vs `DashboardBoard`(영구 저장 grid)가 한 컴포넌트(`DashboardBoardRenderer.tsx`) 안에서 공존 | `LEGACY_RENDERERS` 분기 | 장기적으로 두 체계를 하나의 `render_spec` 계약으로 수렴시켜야 함(4절 참고) |

> 부연: `dashboard_catalog.py`의 `_definition()` 헬퍼는 `binding_schema`를 `{parameter_id: "string" for parameter_id in accepts}`로 **항상 string으로 고정**한다. 즉 이미 존재하는 풍부한 Ontology `ObjectType/LinkType/ActionType` 모델(`ontology.py`)이 Dashboard board의 바인딩 계약에는 전혀 연결되어 있지 않다 — 두 시스템이 나란히 존재하지만 결합되어 있지 않다는 것이 가장 근본적인 gap이다.

---

## 2. 레퍼런스 7개 실사 비교표

| 레퍼런스 | 핵심 파일 | UI takeaway | 데이터/상태 모델 takeaway | MVP 적용할 정확한 위치 | 직접 재사용 가능 여부 | 라이선스/주의점 |
|---|---|---|---|---|---|---|
| **1. mini_foundry_public** | `frontend/components/dashboards/DashboardCanvas.tsx`, `DataBindingPanel.tsx`, `FilterBar.tsx`, `ComponentPalette.tsx`, `PropertiesPanel.tsx`; `frontend/components/ontology/OntologyGraph.tsx`; backend `app/dashboards/{models,service,validation,permissions,registry,cache}.py` | `react-grid-layout` 기반 x/y/w/h 드래그·리사이즈 canvas(`<GridLayout layout={...} cols={12} isDraggable isResizable onLayoutChange=.../>`); 컴포넌트 타입별 `PropertiesPanel`; `sql_query/dataset/static` 3-tab 데이터 바인딩(Monaco SQL 에디터 포함); `date_range/select/multi_select/search` FilterBar | `DashboardComponent{id, component_type, config, data_binding, position:{x,y,w,h}}`; `Binding = sql_query \| dataset \| static` union type; board 실행을 감싸는 별도 backend `validation.py`/`permissions.py`/`cache.py` 모듈 분리 | `web/src/features/dashboard/DashboardGridCanvas.tsx`(신규, P0)의 `react-grid-layout` 통합 패턴; `DashboardBoard.x/y/w/h`(`dashboard_models.py`, P0) 스키마 설계 근거; `BoardInspector.tsx` 바인딩 편집기 고도화(P1) | 코드 그대로 복붙은 불가(Next.js App Router + Tailwind 의존, 우리는 Vite+커스텀 CSS) — **패턴·스키마 설계만 채택**, `react-grid-layout` 통합 코드는 구조적으로 거의 그대로 이식 가능 | **MIT**(Abdullrahman Bahar, 2026) — 재사용 자유. 원문 주석/구조를 그대로 옮기지 말고 우리 타입 체계로 재작성 |
| **2. openfoundry-emulator** | `apps/app-console/src/pages/Contour.tsx`; `apps/app-workshop/src/components/Canvas.tsx`; `apps/app-workshop/src/widgets/widget-registry.ts`; `apps/app-workshop/src/store/page-store.ts`; `apps/app-console/src/components/DataTable.tsx` | `Contour.tsx`는 세로 파이프라인 UI — Board 카드 사이 "+" connector로 `table/filter/groupby/aggregate/chart` 삽입, 각 단계가 이전 단계 결과를 변형(문서 4-1절 Analysis 화면과 정확히 대응); `Canvas.tsx`는 `react-grid-layout` 없이 순수 CSS grid + mouse handler로 만든 경량 12열 드래그/리사이즈(대안 구현 확인용) | `Board{id, type, config}`의 **클라이언트 사이드** 파이프라인 평가(`useMemo`로 단계별 snapshot 계산, 서버 없이 프로토타이핑 가능); `WidgetInstance{id,type,config,position}` + `widget-registry.ts`의 선언적 `configSchema` | `web/src/features/analysis/AnalysisPathCanvas.tsx`(신규, P1) — `Contour.tsx`의 파이프라인 UI/평가 구조를 **서버사이드 실행**으로 옮겨 재구현; `BoardCatalogDefinition`을 `widget-registry.ts`의 `configSchema` 패턴으로 확장(P1/P2) | UI 패턴·상태 모델은 강하게 참고할 가치가 있으나 Blueprint 의존이 깊고 client-only 평가 방식이라 부분 재작성 필요 | **Apache-2.0** — 재사용 가능(수정 파일에 변경 고지, NOTICE 유지 권장) |
| **3. contour-translation** | `contour-translator/contour_render_specs.py`(전체), `contour_translator.py` | UI 코드 아님(순수 백엔드 변환 로직) | `build_render_spec(board_type, board_state, board_view_state, title) -> dict`가 반환하는 `{specVersion, kind, title, isRenderable, ...}` 정규화 스펙; `kind` enum 15종(`histogram/timeseries/chart/table/filter/expression/aggregate/pivot_table/join/join_rows/sort/calculation/markdown/input_dataset/input_ref/unsupported/error`); **"번역이 실패해도 절대 예외를 던지지 않고 `kind="error"`로 감싼다"**는 방어적 설계 원칙 | `api/factory_signal_board/analysis_render_specs.py`(신규, P1) — 우리 board kind에 맞춘 `render_spec` 빌더로 직접 이식; `DashboardBoard.render_spec` 필드 설계의 직접 근거 | 우리 board 모델은 Contour의 Latitude 내부 클래스가 아니라 자체 정의이므로 `_normalize_column` 등 세부 구현은 새로 작성해야 하지만, **디스패치 테이블 구조와 "절대 예외를 던지지 않는다"는 원칙은 그대로 채택** | **MIT**(Sibyl Advisory, 2026) — 재사용 자유 |
| **4. palantir-blueprint** | `packages/core`, `packages/select`, `packages/datetime`, `packages/icons` | `Button`/`Tag`/`Card`/`Spinner`/`NonIdealState`/`FormGroup`/`Drawer` 등 고밀도 업무용 UI primitive — `openfoundry-emulator`의 `Contour.tsx`에서 시각 톤이 검증됨 | 해당 없음(순수 UI 컴포넌트 라이브러리, 상태 모델 없음) | `web/src/app/WorkbenchShell.tsx`와 `web/src/features/analysis/*`에 `@blueprintjs/core`를 선택 적용. Result table은 TanStack Table을 유지 | **소스 복사가 아니라 npm package로 정식 설치** — 재사용 가능. 기존 `styles.css`와 충돌하지 않도록 namespace/token과 visual regression 적용 | **Apache-2.0**, Palantir 공식 오픈소스. NOTICE 관리, Palantir 브랜드·로고·visual trade dress 복제 금지 |
| **5. OpenFoundry** | `apps/web/src/lib/components/dashboard/{DashboardGrid.svelte, WidgetFactory.svelte, ChartWidget/TableWidget/KPIWidget.svelte}`; `apps/web/src/lib/components/ontology/GraphView.svelte`; `README.md`(제품 정보구조) | `DashboardGrid.svelte`는 x/y 좌표 없이 순수 12-col CSS grid + `colSpan/rowSpan` + "W-/W+/H-/H+" 버튼 리사이즈(`react-grid-layout` 없이도 가능한 접근성 대안 확인); `WidgetFactory.svelte`는 위젯 타입 dispatch + SQL 템플릿에 필터 주입(`applyDashboardQueryTemplate`) + 로딩/에러/새로고침 UX | `DashboardWidget{id, type, layout:{colSpan,rowSpan}, query:{sql,limit}}`, `DashboardFilterState` 템플릿 치환 | `BoardInspector.tsx`의 버튼식 리사이즈(모바일 접근성 보완, P0 병행 고려); `GraphView.svelte`는 React Flow 도입 시 상태 관리 패턴 참고(P2) | **Svelte 프레임워크**라 코드 이식 불가(우리는 React) — 패턴/스키마만 참고 | README는 **Apache-2.0**을 명시하지만 **로컬 `LICENSE` 파일 내용이 비어 있음** — 실제 사용 전 GitHub 원본에서 라이선스 재확인 필수 |
| **6. palantir-demo** | `src/App.jsx`; `src/components/{Dashboard, GlobeComponent, MarketTickers, NewsFeed, EventDetailModal}.jsx` | 다크 테마 실시간 "situation room" 스타일(3D Globe, 시세 티커, 뉴스 피드, 이벤트 상세 모달) — Executive Overview 탭의 시각적 무드(다크/고대비/실시간감) 참고 가치는 있으나 제조 도메인과 직접 매칭되지 않음 | 해당 없음(정적 mock 데이터 기반 데모, 재사용 가능한 상태 모델 없음) | **적용하지 않음** — 디자인 무드보드 참고 수준으로만 열람, 코드/구조 이식 없음 | 불가 | **LICENSE 파일 없음**(리포지토리에 라이선스 명시 없음) — 코드 복사 금지, 시각적 아이디어만 참고 |
| **7. Gods_Eye** | `src/layers/{aircraft, ships, satellites, cameras, buildings, gpsJamming}.js`; `src/store`; `src/services` | 지도 위 다중 레이어 on/off 패턴과 time/replay coverage UX를 참고할 수 있으나 현재 MVP의 지도 요구는 미확정 | 레이어별 독립 데이터 source, 공통 time state, replay provenance/coverage | 현재 직접 적용하지 않음. P2 이후 지도·시간 use case가 확정되면 UX 원칙만 자체 구현 | 현재 라이선스 전략에서는 직접 재사용하지 않음 | **GPL-3.0** — 배포 파생물을 GPL-3.0 조건과 양립시킬 의사가 있을 때만 코드 재사용 가능. 현재 제품에는 코드 복사 없이 아이디어만 참고 |

### 요약: 레퍼런스별 한 줄 결론

1. **mini_foundry_public** — `react-grid-layout` 통합과 `x/y/w/h` 스키마의 1차 이식 대상(MIT).
2. **openfoundry-emulator** — Analysis 파이프라인 UI/평가 구조의 1차 이식 대상(Apache-2.0).
3. **contour-translation** — `render_spec` 계약 설계의 직접 근거(MIT, 코드량이 작아 가장 순수하게 재사용 가능).
4. **palantir-blueprint** — 컴포넌트가 아니라 **의존성**으로 선택 채택(Apache-2.0, 공식).
5. **OpenFoundry** — 대안적 grid 구현·위젯 팩토리 패턴 참고(라이선스 재확인 필요).
6. **palantir-demo** — 코드 재사용 불가, 시각 자료만(라이선스 없음).
7. **Gods_Eye** — 현재 제품 라이선스 전략에서는 직접 재사용하지 않음(GPL-3.0), time/replay UX 원칙만 참고.

---

## 3. Palantir Contour UI에 최대한 근접한 화면 구조 제안

이 절은 `palantir-contour-dashboard-benchmark.md` 10절("권장 Target UI")을 전제로, 문서가 요구한 10개 항목을 현재 코드와 대조해 구체화한다.

### 3-1. Analysis 편집 화면

현재 존재하지 않는 신규 화면(`/app/analysis/:analysisId`, 5절에 wireframe/component tree). `Contour.tsx`의 세로 파이프라인 + `mini_foundry_public`의 `PropertiesPanel` 패턴을 결합한다.

### 3-2. Dashboard 소비 화면

기존 `ManufacturingApp.tsx`의 governed workflow는 보존하되, 화면 controller와 shell은 분해한다. `BoardCanvas.tsx`는 `DashboardGridCanvas.tsx`(React Grid Layout)로 교체하고, `DashboardShell.tsx`의 global chrome·3-pane만 `WorkbenchShell`로 추출한다. dashboard command와 analysis command를 한 prop-heavy shell에 조건문으로 합치지 않는다(4절 상세).

### 3-3. 좌측 rail / 중앙 canvas / 우측 inspector

Dashboard 쪽은 이미 `ContextPanel`(좌) / `BoardCanvas`(중) / `BoardInspector`(우) 3분할이 구현되어 있다. 이를 공통 `WorkbenchShell`의 slot으로 옮기고 Dashboard에서는 좌측을 Parameter/Saved View rail, 우측을 object/evidence/action drawer(편집 시 board inspector)로 사용한다. Analysis 쪽은 좌측 **Board rail**, 중앙 세로 path, 우측 **Data/Interaction/Access + Result inspector**로 구성한다.

### 3-4. Board Catalog

`BoardCatalogPanel.tsx`는 이미 카테고리·검색·대상 탭 선택을 지원한다. 부족한 것은 **호환성 필터**(레퍼런스 문서 C-11 "input_kind가 rows면 Filter/Join/Expression/Group, aggregate면 Chart/Metric만 활성화")이며, 이는 Analysis 쪽 신규 `AnalysisBoardRail`에서만 필요하다(Dashboard의 Board Catalog는 지금처럼 호환성 필터 없이 유지해도 무방 — Dashboard board는 서로 데이터 파이프라인으로 연결되지 않기 때문).

### 3-5. Parameter / Filter

`ContextPanel.tsx` + `DashboardParameterDefinition`(현재 4종: `selected_event_id`, `selected_equipment_id`, `status_filter`, `intent`)이 이미 구현되어 있다. Analysis 화면에서는 `line`, `failure_type`, `severity`, `period`, `risk_threshold` 같은 분석용 typed parameter가 추가로 필요하다(`palantir-contour-ui-reference.md` C-06 절이 이미 제안한 목록).

### 3-6. Chart-to-chart filtering

Dashboard 쪽에 구현된 것은 `_dependency_graph()`(`dashboard_service.py`)가 만든 metadata와 `showAffected()`의 하이라이트뿐이다. frontend의 `affectedBoardIds()`도 direct outgoing edge만 찾으며, transitive closure·cycle 검사·query invalidation은 수행하지 않는다. 따라서 실제 chart-to-chart filtering은 신규 기능으로 설계해야 한다.

`ECharts click/brush` → raw event adapter → typed `SelectionFilter` → 서버 validation → 명시적 dependency graph의 transitive downstream 계산 → 해당 board만 batch query → 결과·row count·result hash 교체의 순서로 동작한다. parameter/selection chip에는 source board와 target 수를 표시하고, stale response가 최신 선택을 덮지 않도록 request id 또는 `AbortController`를 사용한다.

### 3-7. Table result verification

현재 없음(1-2절 gap). `EvidenceTable`류 고정 렌더러와 별개로, Analysis 경로의 모든 변형 board에 접이식 `AnalysisResultInspector`(행 수/컬럼/null rate/중복 key/샘플 50행/`elapsed_ms`/`cache_hit`)를 붙인다. `openfoundry-emulator`의 `DataTable.tsx`(`ColumnDef<T>{key,header,render,sortable}` 패턴)를 얇게 재구현하되, 실제 테이블 렌더는 로드맵에서 채택한 **TanStack Table**로 한다(6절).

### 3-8. Evidence / Action drill-down

이미 MVP의 강점이다(`DashboardBoardRenderer.tsx`의 Evidence/Report/UIBlock 렌더러 + `record_decision`/`add_note`/`invoke_ontology_action`). Analysis 경로에는 이 렌더러를 그대로 감싸는 `evidence`/`action` kind의 board 2종만 추가하면 된다(P2, 7절).

### 3-9. Saved view / Share / PDF snapshot

이미 강점(1-1절)이다. 다만 Saved View에 tab·parameter뿐 아니라 normalized selections, layout preference, `analysis_version_policy`를 포함한다. 공유 token에는 결과 데이터를 넣지 않고 view state reference만 넣으며, 열 때 서버가 권한을 다시 평가한다. `AnalysisResultSnapshot`에는 analysis version, dataset versions, timezone, parameter/selection state, board result hashes, render spec version을 포함하고 기존 `ExportCheckpoint{snapshot_hash, content_hash}` 패턴을 확장한다. PDF는 브라우저 화면 캡처만이 아니라 이 manifest와 연결된 서버 artifact여야 한다.

### 3-10. Object / lineage graph

완전 신규(1-2절 gap). `mini_foundry_public`의 `OntologyGraph.tsx`(`@xyflow/react` 기반, 커스텀 `ObjectNode`, 디바운스 레이아웃 저장)를 이식하고, 데이터 소스는 이미 존재하는 `ontology_service.py`의 `traverse()`를 React Flow 노드/엣지 포맷으로 변환하는 신규 얇은 엔드포인트로 연결한다(P2, 7절).

---

## 4. DashboardShell / BoardCanvas 구조 변경 분석

### 4-1. 현재 구조의 한계

```text
DashboardBoard {
  id, definition_id, title,
  width: 4 | 6 | 12,      # ← 가로 span만. 세로 좌표 없음
  order: int,               # ← 세로 배치는 이 정수 하나로 암묵 결정
  hidden, mandatory, custom,
  bindings: dict, settings: dict
}
```

- `BoardCanvas.tsx`는 `style={{ gridColumn: \`span ${board.width}\` }}`만 지정한다. 세로 위치는 브라우저의 CSS grid **auto-placement**가 결정하므로, 사용자가 board를 원하는 좌표에 자유 배치하거나 리사이즈할 수 없다.
- board 이동은 `utils.ts`의 `moveBoard()`가 배열 `splice`로 처리하는 **리스트 재정렬**이지 좌표 이동이 아니다. 드래그 시 "어느 board 앞/뒤"만 결정되고 "어디에 놓였는지"는 결정되지 않는다.
- `width`가 `4 | 6 | 12`(1/3, 1/2, 1) 3단계로 고정되어 있어 세밀한 폭 조정이 불가능하다.
- `DashboardBoardRenderer.tsx`는 `definition.renderer` 문자열을 250줄 `switch`로 분기한다. 새 board를 추가하려면 (a) `dashboard_catalog.py`에 정의 추가 (b) `DashboardBoardRenderer.tsx`에 분기 추가 (c) 필요시 신규 컴포넌트 작성까지 **3중 코드 변경**이 필요하다.
- `_dependency_graph()`는 board의 `emits`/`accepts` **전역 교집합**으로 엣지를 만든다. Contour처럼 "이 board는 저 board의 실제 상류(upstream)"라는 방향성 있는 데이터 파이프라인이 아니라, 파라미터 이름이 같으면 무조건 연결되는 얕은 매칭이다. Analysis 경로가 생기기 전까지는 이 방식으로 충분하지만, row-set을 실제로 변형하는 board가 생기면 진짜 DAG가 필요하다.

### 4-2. `width` 중심 board를 `x/y/w/h` 12열 grid로 바꾸는 방법

**1단계 — 모델 확장(하위호환 유지)**

```python
# api/factory_signal_board/dashboard_models.py (변경)
class DashboardBoard(StrictModel):
    id: str = Field(min_length=3, max_length=160)
    definition_id: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=1, max_length=120)
    width: BoardWidth = 6            # 유지: 구버전 클라이언트/직렬화 호환용 alias
    x: int = Field(default=0, ge=0, le=11)     # 신규
    y: int = Field(default=0, ge=0)            # 신규
    w: int = Field(default=6, ge=1, le=12)     # 신규: width의 자유도 확장판
    h: int = Field(default=4, ge=1, le=12)     # 신규
    order: int = Field(ge=0)          # 유지: tab 내부 tab-order/z-index 용도로만 축소
    hidden: bool = False
    mandatory: bool = False
    custom: bool = False
    bindings: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    source: Literal["catalog_board", "analysis_board"] = "catalog_board"   # 신규(P1 대비)
    analysis_board_ref: str | None = None                                    # 신규(P1 대비)
```

위 예시는 전환기의 board 필드다. 실제 payload 최상위에는 `layout_schema_version: 2`를 추가하고 `width`는 dual-read 기간에만 허용한다. 새 저장은 `x/y/w/h`를 source of truth로 사용한다. P0에는 `lg` layout만 사용자가 편집하고 `md/sm`은 `order`를 접근성·모바일 stacking 순서로 삼아 deterministic하게 파생한다. breakpoint별 자유 편집은 실제 요구가 생긴 뒤 추가한다.

**2단계 — 자동 마이그레이션 함수**: 기존 저장된 `dashboard_template_versions.payload_json`/`dashboard_user_preferences.payload_json`에는 `x/y/w/h`가 없다. `_resolve_template()`이 이를 읽을 때 **row-fill 알고리즘**으로 최초 1회 자동 계산한다(DB 컬럼 변경 없이 payload 내부 값만 채움 — SQLite/PostgreSQL 마이그레이션 파일 불필요, 애플리케이션 레벨 마이그레이션).

```python
def _backfill_grid_position(boards: list[DashboardBoard]) -> list[DashboardBoard]:
    """기존 width만 있는 보드에 x/y/w/h를 12열 row-fill로 채운다."""
    cursor_x, cursor_y, row_height = 0, 0, 4
    out = []
    for board in sorted(boards, key=lambda b: b.order):
        w = board.width  # 4|6|12 그대로 사용(1차 마이그레이션은 폭 보존)
        if cursor_x + w > 12:
            cursor_x, cursor_y = 0, cursor_y + row_height
        out.append(board.model_copy(update={"x": cursor_x, "y": cursor_y, "w": w, "h": row_height}))
        cursor_x += w
    return out
```

**3단계 — 프론트 교체**: `BoardCanvas.tsx` → `DashboardGridCanvas.tsx`(신규, `react-grid-layout` 사용). `mini_foundry_public`의 `DashboardCanvas.tsx`에서 layout 변환·edit mode·drag cancel 패턴을 가져오되, 아래는 1.x 레퍼런스를 설명하는 개념 코드다. 실제 구현은 React Grid Layout 2.x API와 React 19 호환 spike를 거쳐 작성한다.

```tsx
// web/src/features/dashboard/DashboardGridCanvas.tsx (신규, mini_foundry_public 패턴 이식)
import GridLayout from "react-grid-layout";

const layout = tab.boards.map((b) => ({ i: b.id, x: b.x, y: b.y, w: b.w, h: b.h }));

<GridLayout
  className="dashboard-grid-layout"
  layout={layout}
  cols={12}
  rowHeight={56}
  isDraggable={mode === "edit"}
  isResizable={mode === "edit"}
  draggableCancel="input,textarea,button,select,.no-drag"
  onLayoutChange={(next) => onLayoutChange(gridLayoutToBoards(next))}
>
  {tab.boards.map((board) => (
    <div key={board.id}>{renderBoard(board)}</div>
  ))}
</GridLayout>
```

`gridLayoutToBoards()`/`boardsToGridLayout()` 왕복 변환 유틸은 `web/src/features/dashboard/gridLayout.ts`(신규)에 둔다.

### 4-3. Dashboard와 Analysis Path를 분리하는 방법

`DashboardShell.tsx`에 Analysis props를 계속 추가하지 않는다. 현재 `ManufacturingApp.tsx`가 담당하는 load/draft/share/export/event/action orchestration도 route controller별로 나눈다.

```text
AppRouter
├── AnalysisRoute
│   └── AnalysisWorkspaceProvider
│       └── WorkbenchShell(headerSlot, railSlot, canvasSlot, inspectorSlot)
│           ├── AnalysisBoardRail
│           ├── AnalysisPathCanvas
│           └── AnalysisBoardInspector
└── DashboardRoute
    └── DashboardWorkspaceProvider
        └── WorkbenchShell(headerSlot, railSlot, canvasSlot, inspectorSlot)
            ├── DashboardParameterRail
            ├── DashboardGridCanvas
            └── ObjectEvidenceDrawer / BoardInspector(edit mode)
```

권장 신규 경계는 `web/src/app/WorkbenchShell.tsx`, `web/src/features/analysis/AnalysisWorkspace.tsx`, `web/src/features/dashboard/DashboardWorkspace.tsx`다. 기존 `DashboardShell.tsx`와 `ManufacturingApp.tsx`는 P0 동안 compatibility wrapper로 남겨 회귀를 막고 점진적으로 축소한다.

```text
Analysis(신규)                              Dashboard(기존 유지)
────────────────────────────                ────────────────────────────
AnalysisBoard(row-set 변형/생성)      →      DashboardBoard(source="analysis_board")
    │ Filter/Group/Aggregate/Join                  │ 는 AnalysisBoard의 render_spec을
    │ Chart/Table/Metric/Text/Evidence/Action       │ "참조"만 한다(값을 복제하지 않음)
    ▼                                               ▼
AnalysisRun(실행 이력·검증)                    DashboardBoard(source="catalog_board")
                                                    │ 는 지금처럼 BoardCatalogDefinition을
                                                    │ 직접 사용(운영 board, 변경 없음)
```

- **분리 원칙**: `Analysis`는 편집 전용(분석가·FDE·데이터 사이언티스트), `Dashboard`는 소비 전용(전 역할)이라는 `palantir-contour-ui-reference.md` UI 원칙 1을 그대로 따른다.
- **연결 지점**: Analysis 화면의 각 board 카드에 `[+ Add to dashboard]` 버튼을 두고, 클릭 시 `DashboardBoard{source:"analysis_board", analysis_board_ref, version_policy}`를 생성한다. query spec 값은 복제하지 않되, 기본 `version_policy`는 `pinned`로 하여 게시된 `analysis_version`을 명시적으로 참조한다. `latest_published`는 사용자가 선택한 경우에만 허용하고 Dashboard에 version 변경 badge를 표시한다. draft 변경이 소비 화면을 즉시 바꾸게 해서는 안 된다.
- **기존 45개 catalog board는 전혀 건드리지 않는다** — `source="catalog_board"`가 기본값이므로 `dashboard_catalog.py`의 운영/거버넌스 board(Evidence/Action/Audit 계열)는 지금 그대로 유지된다.

### 4-4. 보드 정의·데이터 바인딩·render spec·dependency graph·parameter binding 계약

현재 `BoardCatalogDefinition.accepts/emits/binding_schema`를 다음 registry contract로 확장한다. Analysis와 Dashboard catalog는 같은 registry primitive를 쓰되, Analysis catalog는 compiler가 있는 source/transform/visualize board이고 Dashboard catalog는 published output/object/evidence/action presentation board다.

```ts
type DataKind =
  | "dataset"
  | "object_set"
  | "tabular"
  | "aggregate"
  | "scalar"
  | "selection"
  | "evidence"
  | "action";

type BoardDefinition = {
  id: string;
  category: "source" | "transform" | "visualize" | "operational";
  inputPorts: Array<{ id: string; accepts: DataKind[]; required: boolean }>;
  outputPorts: Array<{ id: string; kind: DataKind }>;
  configSchema: JsonSchema;
  rendererKey: string;
  compilerKey?: string;
  capabilities: Array<"click" | "brush" | "page" | "sort" | "export">;
  allowedRoles: string[];
  defaultGridSize?: { w: number; h: number; minW?: number; minH?: number };
};

type DashboardBinding =
  | {
      kind: "analysis_output";
      analysisId: string;
      boardId: string;
      outputPort: string;
      versionPolicy: "pinned" | "latest_published";
      analysisVersion?: number;
    }
  | { kind: "object_set"; objectType: string; governedQueryId: string }
  | { kind: "static_text"; markdown: string };
```

P0/P1에는 arbitrary SQL binding을 열지 않는다. 임의 SQL은 query 권한·비용 제한·schema drift·dataset version·lineage를 별도로 해결해야 하므로, 필요 시 P2 이후 server-stored governed query id로만 추가한다.

```python
# api/factory_signal_board/analysis_models.py (신규, P1)

AnalysisBoardKind = Literal[
    "input_object_set",  # 시작 board: ObjectType 하나를 선택
    "filter", "join", "expression",           # row 변형
    "group_by", "aggregate",                  # 집계 전환
    "chart", "metric", "table", "text",       # 결과 전달
    "evidence", "action",                     # 운영 결합(P2)
]

class DatasetRef(StrictModel):
    object_type: str
    workspace_id: str
    as_of_version: int | None = None

class AnalysisBoard(StrictModel):
    id: str
    analysis_id: str
    kind: AnalysisBoardKind
    title: str
    input_board_ids: list[str] = Field(default_factory=list)  # 보통 1개, Join은 정확히 2개
    object_type: str | None          # kind == input_object_set일 때만
    config: dict[str, Any]           # kind별 설정(필터 조건 / group_by 컬럼 / join 관계 등)
    render_spec: dict[str, Any]      # contour_render_specs.py 스타일 정규화 스펙(아래)
    output_schema: list[dict] | None # [{name, field_type}], Result Inspector용
    order: int
    created_by: str
    created_at: str

class Analysis(StrictModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    display_name: str
    revision: int
    owner_user_id: str
    editors: list[str] = Field(default_factory=list)
    viewers: list[str] = Field(default_factory=list)
    status: Literal["draft", "published"] = "draft"
    boards: list[AnalysisBoard]
    parameter_definitions: list[DashboardParameterDefinition] = Field(default_factory=list)
    created_at: str
    updated_at: str

class AnalysisRun(StrictModel):
    id: str
    analysis_id: str
    analysis_version: int
    parameter_state: dict[str, Any]
    dataset_versions: list[dict[str, str]]
    timezone: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    board_statuses: dict[str, str]
    executed_by: str
    started_at: str
    finished_at: str | None
```

`render_spec`은 `contour-translation/contour_render_specs.py`의 설계를 그대로 이식한다.

```python
# api/factory_signal_board/analysis_render_specs.py (신규, P1)
# contour_render_specs.py의 build_render_spec() 디스패치 구조를 우리 kind에 맞게 재구현

SPEC_VERSION = "1"
RENDER_KINDS = (  # 우리 8종 + input
    "input_object_set", "filter", "join", "expression",
    "group_by", "aggregate", "chart", "metric", "table", "text",
    "unsupported", "error",
)

def build_render_spec(kind: str, config: dict, title: str | None) -> dict:
    """번역이 실패해도 절대 예외를 던지지 않는다(contour_render_specs.py 원칙 그대로 채택)."""
    try:
        payload = _BUILDERS.get(kind, _unsupported)(config)
    except Exception as e:
        payload = {"kind": "error", "error": f"{type(e).__name__}: {e}"}
    return {"specVersion": SPEC_VERSION, "title": title, "isRenderable": payload["kind"] not in {"error", "unsupported"}, **payload}
```

영구 `render_spec`은 ECharts의 raw `option`이나 React component props를 저장하지 않는다. 다음처럼 domain-neutral하고 versioned된 union을 저장하며, frontend adapter가 이를 ECharts option/TanStack column으로 compile한다.

```ts
type RenderSpecV1 =
  | {
      version: 1;
      kind: "chart";
      chartType: "bar" | "line" | "scatter" | "histogram";
      encodings: { x: FieldRef; y: FieldRef; series?: FieldRef; tooltip?: FieldRef[] };
      interactions: Array<"click" | "brush" | "zoom">;
    }
  | { version: 1; kind: "table"; columns: TableColumnSpec[]; defaultSort?: SortSpec[] }
  | { version: 1; kind: "metric"; field: FieldRef; format?: string }
  | { version: 1; kind: "evidence"; objectIdField: FieldRef }
  | { version: 1; kind: "action"; actionType: string; objectIdField: FieldRef }
  | { version: 1; kind: "object_graph"; nodeType: string; edgeTypes: string[] };

type BoardResult = {
  runId: string;
  boardId: string;
  schema: ResultField[];
  rows?: unknown[];
  page?: { nextCursor?: string; totalRows?: number };
  metrics: {
    inputRows?: number;
    outputRows?: number;
    elapsedMs: number;
    cacheHit: boolean;
    resultHash: string;
  };
  warnings: Array<{ code: string; message: string }>;
  lineage: Array<{ kind: string; id: string; version?: string }>;
};
```

**Dependency graph(진짜 DAG)**: Analysis 경로는 `input_board_ids`와 typed port edge로 명시적 방향성을 갖는다. 기본 board는 상류 1개, source는 0개, Join은 정확히 2개를 요구한다. 별도 `DependencyEdge{source_board_id, source_port, target_board_id, target_port, kind:data|parameter|selection}`를 version payload에 저장해 port compatibility와 cycle을 publish 전에 검증한다. Dashboard의 기존 `_dependency_graph()`는 v1 migration hint로만 쓰고, v2 dashboard query는 서버가 검증해 반환한 명시적 graph를 사용한다.

**Parameter binding 계약**: 기존 `DashboardParameterDefinition`의 id/type/default/options/scope는 migration source로 재사용하되 target을 암묵 추정하지 않는다. `ParameterBinding{parameter_id, target_board_id, target_path, operator:eq|in|between|gte|lte|contains}`를 명시적으로 저장한다. chart event는 `SelectionFilter{source_board_id, field, operator, values, mode:replace|add|toggle}`로 정규화하고, server가 field type과 권한을 재검증한다. 초기 도메인 parameter는 `line`, `failure_type`, `severity`, `period`, `risk_threshold`로 제한한다.

### 4-5. 프론트엔드-FastAPI API 계약

| Method | Path | 설명 | 상태 |
|---|---|---|---|
| GET | `/api/dashboards/resolved` | 기존 그대로(응답 payload에 `x/y/w/h` 필드만 추가) | 변경(P0) |
| PUT | `/api/dashboards/preferences` | 기존 그대로(요청 payload에 `x/y/w/h` 포함) | 변경(P0) |
| GET | `/api/object-types/{id}/aggregate` | `group_by` + `metrics`(count/sum/avg/min/max) 신규 집계 쿼리 | 신규(P1) |
| POST | `/api/analyses` | Analysis 생성 | 신규(P1) |
| GET / PUT | `/api/analyses/{id}` | Analysis 조회/수정(owner/editor만) | 신규(P1) |
| POST | `/api/analyses/{id}/boards` | AnalysisBoard 추가(경로에 삽입) | 신규(P1) |
| PUT / DELETE | `/api/analyses/{id}/boards/{board_id}` | 설정 변경/삭제(하류 영향 경고 포함) | 신규(P1) |
| POST | `/api/analyses/{id}/validate` | port/type/field/cycle/action permission 검증 | 신규(P1) |
| POST | `/api/analyses/{id}/publish` | immutable AnalysisVersion 생성 | 신규(P1) |
| POST | `/api/analyses/{id}/runs` | pinned version·parameter로 전체 경로 실행 → `AnalysisRun` | 신규(P1) |
| GET | `/api/analysis-runs/{run_id}` | run/board status, dataset versions, timezone 조회 | 신규(P1) |
| GET | `/api/analysis-runs/{run_id}/boards/{board_id}/result` | cursor 기반 preview/result, sort/filter, schema·metrics·lineage | 신규(P1) |
| POST | `/api/analyses/{id}/boards/{board_id}/add-to-dashboard` | `DashboardBoard{source:"analysis_board"}` 생성 | 신규(P1) |
| POST | `/api/dashboards/{id}/query` | parameter·selection·대상 board를 받아 하류 결과 batch resolve | 신규(P1) |
| POST | `/api/dashboards/{id}/snapshots` | 기존 export service로 versioned manifest + PDF/JSON snapshot 생성 | 신규(P1) |
| GET | `/api/ontology/graph` | 기존 `traverse()`를 React Flow 노드/엣지 포맷으로 변환해 반환 | 신규(P2) |

모든 endpoint는 client가 보낸 role/project를 신뢰하지 않고 현재 `Principal`과 `ProjectContext`에서 organization/project/workspace를 파생한다. `PUT`은 `base_revision` 또는 `If-Match`로 optimistic concurrency를 적용한다. dashboard query는 board별 success/error를 분리하고 `request_id`, `effective_filters`, `result_hash`를 반환해 부분 실패와 stale response를 안전하게 처리한다.

---

## 5. 화면 ASCII wireframe + 컴포넌트 트리

### 5-1. `/app/analysis/:analysisId`

```text
┌ Header: Project ▾ | Workspace ▾ | Analysis "위험 이벤트 원인 분석" | Save | Run | Share | [Dashboard 미리보기] ┐
├ Board rail ─────────┬ Analysis path(세로 스크롤) ─────────────────────────────┬ Inspector ────────────┤
│ 추천                 │ ┌ Input: RiskEvent object set ─────────────────────┐   │ Board: Group by        │
│  Table               │ │ workspace=$workspace, status ∈ [warning,critical]│   │                        │
│                      │ └────────────────────────────────────────────────┘   │ Data                   │
│ Row 변환              │                   │ (+ Filter / Join / Group)          │  group_by: line         │
│  Filter              │ ┌ Filter ───────────────────────────────────────┐   │  aggregate: p95(risk)   │
│  Join(허용 관계만)      │ │ line = $line AND severity >= warning           │   │                        │
│  Expression          │ │ 812 rows → 214 rows                             │   │ Interaction             │
│                      │ └────────────────────────────────────────────────┘   │  emits: selection       │
│ 집계                  │                   │                                    │  affects: 2 boards      │
│  Group / Aggregate   │ ┌ Group by: line → p95(failure_probability) ─────┐   │                        │
│  (호환 안 됨: Join)     │ │ [Result Inspector ▾] rows=6 cols=2 null=0%      │   │ Access                 │
│                      │ └────────────────────────────────────────────────┘   │  visible: engineer,     │
│ 결과 전달              │                   │ (+ Chart / Table / Metric)         │   fde, quality_auditor  │
│  Chart / Metric      │ ┌ Chart: bar(line, p95_risk) ─────────────────────┐   │  export: allowed        │
│  Text                │ │ [막대 차트 렌더]                                  │   │                        │
│  Evidence / Action    │ └────────────────────────────────────────────────┘   │                        │
│                      │                   │ [+ Add to dashboard]               │                        │
└──────────────────────┴────────────────────────────────────────────────────┴────────────────────────┘
```

```text
AnalysisPage  (route: /app/analysis/:analysisId)
└── AnalysisShell
    ├── AnalysisHeader            (breadcrumb, name, Save, Run, Share, "Dashboard 미리보기")
    └── AnalysisWorkspaceLayout
        ├── AnalysisBoardRail     (좌; BoardCatalogPanel.tsx를 input_kind 호환성 필터로 확장)
        ├── AnalysisPathCanvas    (중)
        │   ├── AnalysisPathConnector       ("+" 추가 메뉴, Contour.tsx 패턴)
        │   ├── AnalysisBoardCard × N
        │   │   ├── AnalysisBoardHeader     (kind, title, 삭제/복제)
        │   │   ├── AnalysisBoardConfigForm (kind별 동적 폼: Filter/GroupBy/Aggregate/Chart/Join)
        │   │   └── AnalysisResultInspector (접이식: rows/columns/null-rate/dup-key/sample 50행)
        │   └── AnalysisEmptyState          ("위험 이벤트 분석 시작" 템플릿, C-04 원칙)
        ├── AnalysisInspector      (우; Data/Interaction/Access 3탭, benchmark 2.1절 구조)
        └── AddToDashboardDialog   (기존 tab 선택 / 새 tab 생성, benchmark 2.2절 구조)
```

### 5-2. `/app/dashboard/:dashboardId`

```text
┌ Header: Project ▾ | Workspace ▾ | Tabs[운영 Overview|Governance|+] | View●/Edit | Board Catalog | Save View | Share | Export ▾ ┐
├ Parameter rail ───────┬ 12-column grid canvas(react-grid-layout) ──────────────────────────────────────────────┤
│ 기간: 최근 7일           │ ┌ x0 y0 w12 h2 ── Status Summary ────────────────────────────────────────────────┐    │
│ 라인: 전체 ▾             │ └─────────────────────────────────────────────────────────────────────────────────┘    │
│ 고장유형: 전체 ▾          │ ┌ x0 y2 w6 h4 ─ Risk Trend ──────────────┐ ┌ x6 y2 w6 h4 ─ Failure Mix ───────────┐    │
│ 위험도: warning+          │ │ 선택 시 하류 3개 board 갱신                │ │ pie/bar chart                          │    │
│ 적용 보드: 3개             │ └───────────────────────────────────────┘ └───────────────────────────────────────┘    │
│                        │ ┌ x0 y6 w12 h5 ─ Equipment Risk Table(TanStack Table, 정렬/필터/페이지) ────────────┐    │
│ Saved Views ▾           │ └─────────────────────────────────────────────────────────────────────────────────┘    │
│  [Board Meeting]        │ ┌ x0 y11 w6 h4 ─ Evidence ────────────────┐ ┌ x6 y11 w6 h4 ─ Recommended Action ────┐    │
│                        │ └───────────────────────────────────────┘ └───────────────────────────────────────┘    │
└────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────┘
```

```text
DashboardRoute  (route: /app/dashboard/:dashboardId)
└── DashboardWorkspaceProvider
    └── WorkbenchShell
        ├── DashboardCommandBar
        │   ├── ViewSelector / FreshnessIndicator
        │   ├── ShareDialog / SnapshotExportDialog
        │   └── EditModeToggle
        └── DashboardLayout
            ├── DashboardParameterRail
            │   ├── TypedParameterForm
            │   ├── ActiveSelectionList
            │   ├── SavedViewList
            │   └── DataVersionSummary
            ├── DashboardGridCanvas
            │   └── ResponsiveGridLayout
            │       └── DashboardBoardFrame × N
            │           ├── DashboardBoardHeader
            │           └── DashboardBoardRenderer
            │               ├── (source="catalog_board") 기존 renderer adapter
            │               └── (source="analysis_board") RenderSpecV1 adapter
            └── ObjectEvidenceDrawer
                ├── ObjectSummary / ObjectRelations
                ├── EvidenceTimeline / AuditTimeline
                └── GovernedActionPanel

Edit mode에서만 `ObjectEvidenceDrawer` 대신 `BoardInspector`와 `BoardCatalogPanel`을 열 수 있다. 소비 모드의 우측 panel은 board 설정 form이 아니라 선택 object의 evidence/action drill-down이다.
```

---

## 6. 기술 선택: 지금 도입 / 나중에 검토 / 도입하지 않음

| 기술 | 결정 | 근거 |
|---|---|---|
| **React Grid Layout** | **지금 도입(P0)** | `mini_foundry_public`이 정확히 이 조합(12열, `isDraggable`/`isResizable`, `onLayoutChange`)으로 검증. `BoardCanvas.tsx` 교체에 필요한 x/y/w/h·collision·resize를 제공한다. 레퍼런스의 1.x 코드를 복사하지 말고 최신 2.x TypeScript API를 React 19에서 검증한다. |
| **Apache ECharts** | **지금 도입(P0~P1)** | `SensorLineChart`/`ExecutiveRiskTrend` 등 기존 차트 board를 대체·확장하며, `dataZoom`/`brush`/클릭 이벤트를 `SelectionFilter`로 변환하는 데 적합(`palantir-contour-ui-reference.md` C-12 원칙). Apache-2.0 |
| **TanStack Table** | **지금 도입(P1)** | Result Inspector·Equipment Risk Table 등 고밀도 검증용 표에 적합. Headless라 `web/src/styles.css` 커스텀 디자인 시스템과 충돌 없음. MIT |
| **Blueprint(선택 컴포넌트만)** | **지금 도입(P1, 부분)** | `NonIdealState`/`Tag`/`Spinner`/`Button`/`FormGroup`/`Drawer` 등 core primitive만 `@blueprintjs/core` npm 의존성으로 추가. 결과 table은 TanStack Table 한 종류로 통일하고 Blueprint Table과 역할을 중복시키지 않는다. |
| **React Flow(`@xyflow/react`)** | **나중에 검토(P2)** | Object/lineage graph는 P2 스코프. `mini_foundry_public`의 `OntologyGraph.tsx`가 정확한 패턴(커스텀 노드, 디바운스 레이아웃 저장)을 제공한다. 라이선스는 MIT다. Analysis 기본 경로와 Dashboard grid에는 사용하지 않는다. |
| **Vega-Lite** | **나중에 검토(도입 보류)** | ECharts로 커버 가능한 영역과 중복. `render_spec`을 완전 선언형으로 만들 때 후보로만 남겨둠. 지금 도입하면 차트 렌더러가 2종(ECharts+Vega-Lite)이 되어 유지보수 비용만 늘어남 |
| **MapLibre GL JS** | **나중에 검토(로드맵 미확정)** | 현재 MVP 요구사항에 "설비/공장 지도"가 없음. `Gods_Eye`는 GPL이라 코드 재사용 불가, 패턴만 참고 가능. 지도 요구가 확정되면 그때 재검토 |
| **AG Grid Enterprise** | **도입하지 않음** | 상용 라이선스 비용 발생. TanStack Table(무료)로 정렬/필터/페이지네이션/가상화 요구를 충분히 충족 가능. Enterprise 전용 기능(클라이언트 pivot, row grouping UI)은 우리 설계상 **서버사이드 Group/Aggregate board**가 담당해야 하므로(4-4절) 클라이언트 그리드 라이선스에 의존할 이유가 약함 |
| **Apache Superset(임베드)** | **도입하지 않음** | 별도 서비스 배포·인증 연동 비용 발생. Superset 자체 권한 모델과 MVP의 세밀한 object/property/action 권한(`ontology_service.py`)을 이중 관리해야 함. 임베드된 대시보드가 Evidence/Action drilldown과 통합되지 않아 "운영 행동은 승인 경계를 통과한다"는 UI 원칙(레퍼런스 문서 2절 원칙 4)을 satisfy할 수 없음 |
| **Cube(semantic layer)** | **나중에 검토** | 현재 Ontology/FastAPI 옆에 별도 metric schema·cache·service를 두면 source of truth가 둘이 된다. 여러 제품이 동일 metric을 공유하고 warehouse query 규모가 실제 병목이 될 때에만 검토한다. |

이 조합은 현재 프로젝트에 적합하되 책임 경계가 전제다: **Blueprint=workbench primitive, RGL=Dashboard layout, ECharts=chart/interaction, TanStack Table=결과 검증, React Flow=object/lineage graph**다. 다섯 라이브러리의 내부 상태를 영구 저장 계약으로 직접 쓰지 않고 adapter 뒤에 둔다.

공식 확인 자료:

- [React Grid Layout 저장소와 2.x 안내](https://github.com/react-grid-layout/react-grid-layout)
- [Apache ECharts 다운로드·Apache-2.0 안내](https://echarts.apache.org/en/download.html)
- [TanStack Table 개요와 headless/server-state 특성](https://tanstack.com/table/latest/docs/overview)
- [React Flow 공식 문서](https://reactflow.dev/)
- [Blueprint 저장소와 Apache-2.0 라이선스](https://github.com/palantir/blueprint)
- [Vega-Lite 선언형 grammar](https://vega.github.io/vega-lite/docs/)
- [MapLibre GL JS 문서](https://maplibre.org/maplibre-gl-js/docs/)
- [AG Grid 라이선스·가격](https://www.ag-grid.com/license-pricing/) 및 [Community/Enterprise 비교](https://www.ag-grid.com/javascript-data-grid/community-vs-enterprise/)
- [Superset Embedded SDK의 guest token/backend 흐름](https://github.com/apache/superset/blob/master/superset-embedded-sdk/README.md)
- [Cube Core 저장소·라이선스 구성](https://github.com/cube-js/cube) 및 [Cube Cloud 가격](https://cube.dev/pricing)

### AG Grid Enterprise / Superset / Cube 도입 시 구조상 단점 상세

- **AG Grid Enterprise**: Community는 MIT이지만 Enterprise feature는 상용 EULA 대상이다. 공식 가격 페이지의 현재 시작가는 USD 999/developer이며 deployment 조건도 별도로 확인해야 한다. 가격은 변할 수 있다. `dashboard_service.py`의 role-based binding 검증은 어차피 서버에 남으므로, 현재 요구에서 상용 client grid를 추가하면 비용과 lock-in만 늘어난다.
- **Superset embed**: Superset 자체는 Apache-2.0이지만 embedded SDK는 iframe, feature flag, guest token을 발급하는 backend, 별도 Superset auth/RLS·metadata 운영을 전제로 한다. 우리 8종 `AppRole` + org/project/workspace scope 및 `ExportCheckpoint`를 두 시스템에 맞춰야 한다. 별도 BI portal에는 적합할 수 있으나 현재 object/evidence/action UX에는 구조적 이중화라는 판단이다.
- **Cube**: Core backend는 Apache-2.0, client package는 MIT 계열이며 Cube Cloud는 별도 요금제다. 캐싱·집계 성능은 매력적이지만, `ontology_service.py`의 Object/Link model과 Cube semantic model이 **같은 지표 의미를 두 벌**로 갖게 된다. 여러 제품이 동일 metric을 공유하는 시점 전에는 schema 동기화·서비스 운영 비용이 편익보다 크다는 판단이다.

---

## 7. 구현 로드맵 (P0 / P1 / P2)

### P0 — Dashboard를 Contour형 12열 grid로 완성

| 항목 | 내용 |
|---|---|
| 변경 파일 | `web/src/App.tsx`, `web/src/features/dashboard/types.ts`, `api/factory_signal_board/dashboard_models.py`, `dashboard_service.py`, `schemas/dashboard-platform.schema.json` |
| 신규 파일 | `web/src/app/WorkbenchShell.tsx`, `web/src/features/dashboard/DashboardWorkspace.tsx`, `DashboardGridCanvas.tsx`, `gridLayout.ts`, `layoutMigration.ts` |
| compatibility | `BoardCanvas.tsx`와 `DashboardShell.tsx`는 P0 동안 adapter/wrapper로 유지하고 v2 회귀가 끝난 뒤 제거 여부를 결정 |
| 신규 타입/API/DB | `layout_schema_version=2`, `GridPosition`, `ResponsiveBoardLayout`, `version_policy`. 기존 `GET /api/dashboards/resolved`와 `PUT /api/dashboards/preferences` payload를 versioned 확장. 별도 table 추가 없이 version payload JSON과 schema를 갱신 |
| UI 기능 | 자유 드래그/리사이즈, 12열 grid, 겹침 방지, 기존 hidden/mandatory/fullscreen/catalog 기능 100% 유지 |
| 테스트 전략 | 프론트: `gridLayout.ts` 왕복 변환 단위 테스트(좌표 손실 없음), `DashboardGridCanvas.test.tsx`(react-grid-layout mock). 백엔드: `tests/test_dashboard_grid_migration.py`(신규) — 기존 8개 역할 템플릿(`width`만 있는 레코드)을 로드했을 때 자동으로 `x/y/w/h`가 채워지는지 검증. E2E: `web/e2e/gold-flow.spec.ts`에 드래그·리사이즈 시나리오 추가 |
| 완료 조건 | 기존 8개 역할 템플릿이 전부 오류 없이 자동 마이그레이션되어 렌더링됨; 드래그/리사이즈 후 저장 → 재로그인 시 위치 복원; `mandatory` board는 리사이즈는 가능하되 삭제/숨김은 여전히 불가; 기존 saved view/share/export/evidence/action E2E 전부 통과 |
| 예상 리스크 | `react-grid-layout`은 SSR 미지원(비이슈, Vite CSR이므로 무관); row-fill 배치 알고리즘 버그로 board가 겹치거나 유실될 위험 → dry-run 검증 스크립트 필요; 기존 Saved View/공유 링크에 저장된 layout snapshot과의 하위호환 확인 필요 |

### P1 — Analysis Path와 검증

| 항목 | 내용 |
|---|---|
| 신규 파일(백엔드) | `api/ontology_dashboard/{analysis_models.py,analysis_repository.py,analysis_service.py,analysis_executor.py,query_planner.py}`; `api/ontology_dashboard/routers/analyses.py` |
| 신규 파일(프론트) | `web/src/features/analysis/{AnalysisWorkspace.tsx,AnalysisPathCanvas.tsx,AnalysisBoardCard.tsx,AnalysisResultInspector.tsx,AnalysisBoardInspector.tsx,AddToDashboardDialog.tsx,types.ts,api.ts}`; `web/src/features/charts/{EChartsBoard.tsx,echartsAdapter.ts}`; `web/src/features/dashboard/{selectionStore.ts,DashboardParameterRail.tsx,ObjectEvidenceDrawer.tsx}`; `web/src/components/results/ResultTable.tsx` |
| 변경 파일 | `web/src/routing.ts`, `web/src/App.tsx`, `web/src/features/dashboard/DashboardWorkspace.tsx`, `api/ontology_dashboard/routers/dashboards.py`, `api/factory_signal_board/export_service.py`, `api/factory_signal_board/ontology_service.py` |
| 신규 DB 테이블 | `analysis_definitions`, `analysis_versions(definition_json, definition_hash)`, `analysis_runs(parameter_json, dataset_versions_json, timezone, status)`, `analysis_board_results(schema_json, storage_ref, result_hash, metrics_json)`, `dashboard_snapshots(view_state_json, analysis_run_refs_json, manifest_hash, artifact_ref)` — SQLite와 PostgreSQL migration을 같은 단계에서 작성 |
| UI 기능 | Source/Filter/Group/Aggregate/Chart/Table/Metric/Text 최소 board; TanStack Result Inspector; ECharts click/brush → typed selection → 하류 batch query; typed Parameter rail; object 선택 → 기존 Evidence/Action drawer; Add to Dashboard와 version pin |
| 테스트 전략 | backend: kind별 결과, owner/editor/viewer RBAC, tenant 격리, graph cycle/port 검증, timeout/cache policy isolation. frontend unit: ECharts event→SelectionFilter, transitive closure, stale response. Playwright: Analysis 작성·publish 및 Chart A brush 후 Chart B/Table의 row count·result hash 실제 변경, object→evidence/action 연결 |
| 완료 조건 | Analysis source→Filter→Group/Aggregate→Chart/Table을 만들고 immutable version으로 publish; Dashboard에서 selection 후 하류 board만 재질의; Result Table에 schema/row count/version/hash; snapshot에 analysis/dataset/timezone/filter/result hash 포함 |
| 예상 리스크 | SQLite 집계 성능, brush query 폭주, selection field와 object id 매핑, cache key에 권한·dataset version 누락. Join은 P2로 미루고 P1은 임의 SQL 없이 allowlisted operator만 지원 |

### P2 — 운영화와 온톨로지 결합

| 항목 | 내용 |
|---|---|
| 신규 파일 | `web/src/features/ontology/OntologyGraph.tsx`, `web/src/features/analysis/{VersionDiffView.tsx,boards/JoinBoardEditor.tsx,boards/ExpressionBoardEditor.tsx}`, 조건부 `web/src/features/map/AssetMapBoard.tsx`; `api/ontology_dashboard/{lineage_service.py,materialization_service.py,cost_guard.py,version_diff_service.py}` |
| 변경 파일 | `api/ontology_dashboard/routers/ontology.py`(`GET /api/ontology/graph` 신규 — 기존 `traverse()`를 React Flow 포맷으로 wrapping), analysis publish/run router |
| 신규 DB(선택) | `analysis_join_policies`, `analysis_materializations`, `analysis_run_events`. MapLibre용 공간 table은 유효한 geometry·권한 use case가 확인된 경우에만 추가 |
| UI 기능 | 허용 relation 기반 Join, safe Expression/Pivot, Object/Analysis/Result lineage graph, version diff/rollback, compute cost·row explosion·freshness 경고. Evidence/Action은 P1 연결을 확장한다. |
| 테스트 전략 | join cardinality/row explosion fixture, expression sandbox 보안, version rollback/replay, materialization invalidation, 대용량 query budget/load test. 지도 도입 시 geometry permission과 viewport query test |
| 완료 조건 | 고급 board가 lineage·version·권한·비용 지표 없이 실행되지 않음; 합의한 데이터 규모에서 P95 interaction/run SLA 충족; version diff/rollback과 snapshot retention이 감사 시나리오 통과 |
| 예상 리스크 | 범용 query builder로 팽창해 vertical focus 상실; Join/Expression이 비용·재현성을 훼손; React Flow 번들 증가; materialization/지도 인프라의 조기 도입 |

---

## 8. "Palantir 전체 복제"가 아닌 현실적 범위 정의

### 명시적으로 하지 않는 것

- Pipeline Builder 전체(스케줄 배치 파이프라인 편집기) — P1의 "Export Analysis Spec"까지만, 실제 배치 컴파일은 범위 밖
- Code Repository / Notebook(코드 실행 환경) — `mini_foundry_public`/`OpenFoundry`가 가진 개발자 도구 전체는 대상 아님
- 임의 SQL 콘솔 — Analysis Filter/Expression board는 화이트리스트 연산만 허용, 자유 SQL 입력 없음
- 범용 커넥터 카탈로그(Postgres/REST API/CSV 업로드 등) — 현재 도메인 어댑터(`ontology_adapter.py`) 체계로 충분
- 멀티테넌트 marketplace, 범용 App Builder(Workshop 전체), 데이터레이크/브랜칭/거버넌스 스택 전체, 자체 LLM 에이전트 플랫폼 — 전부 범위 밖

### "제조 예지보전 vertical에서 Palantir급 경험"의 현실적 범위

1. **4개 ObjectType**(`RiskEvent`, `Equipment`, `Evidence`, `MaintenanceAction`)에 한정된 Analysis 경로 — 8종 board(Filter/Join/Group/Aggregate/Chart/Table/Text/Verify-Table)만 제공, Contour의 전체 board 카탈로그(Pivot Table, Bulk Column Editor 등)는 이식하지 않음
2. **관계 3종 화이트리스트**만 Join 허용(`RiskEvent→Equipment`, `RiskEvent→Evidence`, `Equipment→WorkOrder`) — 임의 join 불가
3. **12열 grid Dashboard + parameter rail + saved view + share + PDF export**는 기존 기반을 확장한다. **실제 chart-to-chart filtering은 신규 실행 기능**이며 P1에서 result hash가 변하는 E2E로 완료를 증명한다.
4. **Evidence/Action drilldown과 감사**는 이미 MVP의 강점 — Palantir 공식 문서가 설명하는 permission 분리(벤치마크 6절)보다 오히려 더 엄격한 governed action 모델(`idempotency_key`, `record_audit`)을 이미 보유하고 있으므로 유지·확장만 하면 됨
5. **Object/lineage graph**는 RiskEvent 주변 1~2 hop까지만(전체 온톨로지 탐색기가 아님) — `traverse(depth=1|2)` 범위로 제한
6. **PostgreSQL 전환 완료(현재 70%) 전까지는 워크로드 상한**(row limit, query timeout, 5분 캐시)을 Analysis 실행 API에 명시적으로 건다

현실적인 대표 성공 시나리오는 다음 하나로 고정한다.

```text
위험 trend에서 7/18–7/24를 brush
  → ranking과 verification table이 92개 설비로 좁아짐
  → EQ-1042 선택
  → 관련 RiskEvent, 센서 이상, 최근 inspection, model version 확인
  → 권한과 reason을 거쳐 Create Inspection 실행
  → audit event와 work item 생성
  → 같은 analysis/data/filter/result hash를 가진 Shift Handover view와 PDF snapshot 공유
```

이 흐름이 빠르고 정확하고 재현 가능하면 “제조 예지보전 vertical에서 Palantir급 경험”이라고 판단한다. 반대로 범용 board 수가 많아도 근거 행·version·action·audit가 끊기면 목표를 달성한 것이 아니다.

### 하지 않을 안티패턴(벤치마크 문서 9절과 동일 원칙 재확인)

- 일반 사용자(임원·현장 작업자·감사 담당)에게 Analysis 편집 화면을 노출하지 않는다 — Analysis는 분석가·FDE·데이터 사이언티스트 역할에게만 `allowed_roles`로 제한
- 분석 경로(dependency graph)를 UI에 그대로 노출하지 않는다 — 사용자에게는 "N boards affected" 요약만 보여주고, DAG 자체는 내부 구조로 관리
- 개인화를 세션에만 머무르게 하지 않는다 — 이미 구현된 역할 template + 사용자 영구 개인화 결합(1-1절)이 MVP의 핵심 차별점이므로 Analysis 쪽에도 동일 원칙을 적용한다(Saved Analysis 소유권은 `owner_user_id` 기준으로 영구 저장)

---

## 부록 A. 파일 경로 색인(본 문서에서 언급한 MVP 파일)

```text
api/factory_signal_board/dashboard_models.py
api/factory_signal_board/dashboard_service.py
api/factory_signal_board/dashboard_catalog.py
api/factory_signal_board/dashboard_repository.py
api/factory_signal_board/export_models.py
api/factory_signal_board/ontology.py
api/factory_signal_board/ontology_service.py
api/factory_signal_board/ontology_adapter.py
api/ontology_dashboard/routers/dashboards.py
api/ontology_dashboard/routers/ontology.py
api/ontology_dashboard/project_context.py
schemas/dashboard-platform.schema.json
schemas/ui-block.schema.json
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
web/src/features/manufacturing/roleLanding.ts
web/src/features/ontology/types.ts
web/src/routing.ts
web/src/types.ts
web/src/styles.css
docs/palantir-contour-ui-reference.md
docs/palantir-contour-dashboard-benchmark.md
docs/07-implementation-status.md
```

## 부록 B. 레퍼런스 파일 경로 색인

```text
레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/
  frontend/components/dashboards/{DashboardCanvas,DataBindingPanel,FilterBar,ComponentPalette,PropertiesPanel}.tsx
  frontend/components/ontology/OntologyGraph.tsx
  backend/app/dashboards/{models,service,validation,permissions,registry,cache}.py
  LICENSE (MIT)

레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/openfoundry-emulator/
  apps/app-console/src/pages/Contour.tsx
  apps/app-console/src/components/DataTable.tsx
  apps/app-workshop/src/components/Canvas.tsx
  apps/app-workshop/src/widgets/widget-registry.ts
  apps/app-workshop/src/store/page-store.ts
  LICENSE (Apache-2.0)

레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/contour-translation/
  contour-translator/contour_render_specs.py
  contour-translator/contour_translator.py
  LICENSE (MIT)

레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/palantir-blueprint/
  packages/{core,table,select,datetime,icons}/
  LICENSE (Apache-2.0, 공식 Palantir 오픈소스)

레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/OpenFoundry/
  apps/web/src/lib/components/dashboard/{DashboardGrid,WidgetFactory,ChartWidget,TableWidget,KPIWidget}.svelte
  apps/web/src/lib/components/ontology/GraphView.svelte
  LICENSE (파일 비어 있음 — README는 Apache-2.0 주장, 재확인 필요)

레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/palantir-demo/
  src/components/{Dashboard,GlobeComponent,MarketTickers,NewsFeed,EventDetailModal}.jsx
  (LICENSE 파일 없음)

레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/Gods_Eye/
  src/layers/{aircraft,ships,satellites,cameras,buildings,gpsJamming}.js
  LICENSE (GPL-3.0 — 코드 재사용 불가)
```
