# Palantir Contour/Foundry UI 접목 상세 분석 — mvp-프로젝트2

> 작성일: 2026-08-01
> 성격: **읽기·분석·설계 제안 문서**. 이 문서는 기존 코드/설정을 전혀 수정하지 않으며, `docs/40-ui-ux/reference/palantir-contour-ui-reference.md`(공식 문서 25개 기반 구현 노트)와 `docs/40-ui-ux/reference/palantir-contour-dashboard-benchmark.md`(첨부 화면 4개 + 공식 문서 벤치마크)를 전제로, **① 현재 코드와 정확히 대조한 gap 분석, ② 로컬 레퍼런스 7개의 파일 단위 실사, ③ 화면 구조·API 계약·로드맵의 실행 가능한 설계안**을 추가한다. 세 문서는 서로 대체하지 않고 아래처럼 역할이 나뉜다.

```text
palantir-contour-ui-reference.md        → "무엇을 왜 만드는가" (공식 문서 25개 → MVP 적용 원칙)
palantir-contour-dashboard-benchmark.md → "화면이 어떻게 동작해야 하는가" (첨부 화면 4개 → 인터랙션 벤치마크)
palantir-ui-integration-analysis.md(본 문서) → "지금 코드에서 무엇을 어떻게 바꾸는가" (gap 분석 + 레퍼런스 실사 + 계약/로드맵)
```

---

## 0. 분석 대상 요약

| 구분 | 경로 | 비고 |
|---|---|---|
| MVP 루트 | `mvp-프로젝트2/` | Backend 93% / Frontend 89% / Architecture 95% (`docs/30-implementation/implementation-status.md` 기준, 2026-08-01) |
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
| Board Catalog(카테고리 7종·검색·역할 필터) | `dashboard_catalog.py`(`BOARD_CATALOG` 45개 정의), `BoardCatalogPanel.tsx` | `category: suggested|observe|explore|explain|act|audit|build`, `allowed_roles` | Board toolbar category |
| 탭/보드에 추가(기존 탭 선택·새 탭 생성) | `utils.ts`(`addCatalogBoard`, `addCustomTab`) | `custom:${definitionId}:${uuid}` 신규 board id 채번 | "Add to dashboard" dropdown |
| 좌측 Parameter/Filter rail | `dashboard_catalog.py`(`PARAMETER_DEFINITIONS`), `ContextPanel.tsx` | `selected_event_id`, `status_filter`, `intent` 3+1종 typed parameter | Parameter panel |
| Cross-filter + "N boards affected" | `dashboard_service.py`(`_dependency_graph`), `ManufacturingApp.tsx`(`showAffected`) | `emits ∩ accepts` 교집합으로 `DependencyEdge[]` 계산, 1.8초 하이라이트 | Chart-to-chart filtering, "Affects N boards" |
| View/Edit 모드 분리 | `DashboardShell.tsx`(`mode` prop) | `view-edit-switch`, edit 모드에서만 Inspector/Catalog 노출 | Palantir viewer/editor 분리 |
| 역할 Template ↔ 개인 Preference 병합 | `dashboard_repository.py`(`dashboard_templates`, `dashboard_template_versions`, `dashboard_user_preferences` 3테이블), `dashboard_service.py`(`_resolve_template`, `_apply_preference_payload`) | `template_version`/`preference_revision`, override diff 저장(`_preference_payload_from_tabs`), `merge_notices` | 벤치마크 문서 11절의 "역할 default + 사용자 영구 override" — **MVP가 Palantir의 세션형 override보다 이미 한 단계 앞서 있음** |
| Saved View | `dashboard_repository.py`(`dashboard_saved_views`), `ContextPanel.tsx` | `SavedViewRecord{active_tab_id, tabs, parameter_state}` | Saved View |
| Share Link(만료·workspace 재검증) | `dashboard_repository.py`(`dashboard_shares`, `token_hash`, `expires_at`), `dashboard_service.py`(`create_share`/`resolve_share`) | 기본 72시간, 서버에서 workspace/이벤트 재검증 | Share Link |
| PDF/CSV/JSON export + 감사 checkpoint | `export_models.py`(`ExportCheckpoint{snapshot_hash, content_hash, requested_by}`) | 재현 가능한 export 감사 기록 | Export/Checkpoint |
| Board 전체화면 | `BoardCanvas.tsx`(`fullscreenBoardId`) | `is-fullscreen` 클래스 토글 | Board fullscreen |
| Text Board + 안전 검증 | `dashboard_catalog.py`("text-board"), `dashboard_service.py`(`UNSAFE_TEXT` 정규식) | HTML/script 삽입 차단(`<[^>]+>|javascript\s*:|on[a-z]+\s*=`) | Text Board |
| Object/Link/Action Ontology 코어 | `ontology.py`, `ontology_service.py`, `web/src/features/ontology/types.ts` | `query_objects`/`traverse`/`invoke`, `idempotency_key` 재생 방지 | Ontology Objects/Actions |
| Governed Action + 감사 | `ontology_service.py`(`invoke`, `reserve/succeed/fail`) | RBAC 권한 검사 → 실행 → `record_audit` | Action Types + permission(벤치마크 6절) — **MVP가 이미 이 모델을 상당히 구현하고 있음** |
| RBAC/tenant scope | `dashboard_service.py`(`_validate_board`), `project_context.py`(`ensure_scope_columns`) | 8개 `AppRole`, org/project/workspace 3단 scope | Object/Data/Action permission 분리(벤치마크 6절) |

**결론**: Dashboard "소비 화면"의 뼈대(Tab, Board, Parameter, Cross-filter, View/Edit, 개인화, Saved View, Share, Export, RBAC)는 이미 Contour의 Dashboard 레이어와 개념적으로 대응된다. 오히려 역할 template과 사용자 개인화의 결합, governed action, tenant 격리는 Palantir 문서가 설명하는 것보다 더 엄격하게 구현되어 있다.

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
| **Analysis 결과 스냅샷/재현성** | `ExportCheckpoint`는 Dashboard 스냅샷만 지원, Analysis run 이력 없음 | `export_models.py` | `AnalysisRun`/`DatasetRef` 개념 자체가 없음 |
| **이중 렌더링 체계 미정리** | `UIBlock`(사건별 LLM/결정론적 `Layout` 생성) vs `DashboardBoard`(영구 저장 grid)가 한 컴포넌트(`DashboardBoardRenderer.tsx`) 안에서 공존 | `LEGACY_RENDERERS` 분기 | 장기적으로 두 체계를 하나의 `render_spec` 계약으로 수렴시켜야 함(4절 참고) |

> 부연: `dashboard_catalog.py`의 `_definition()` 헬퍼는 `binding_schema`를 `{parameter_id: "string" for parameter_id in accepts}`로 **항상 string으로 고정**한다. 즉 이미 존재하는 풍부한 Ontology `ObjectType/LinkType/ActionType` 모델(`ontology.py`)이 Dashboard board의 바인딩 계약에는 전혀 연결되어 있지 않다 — 두 시스템이 나란히 존재하지만 결합되어 있지 않다는 것이 가장 근본적인 gap이다.

---

## 2. 레퍼런스 7개 실사 비교표

| 레퍼런스 | 핵심 파일 | UI takeaway | 데이터/상태 모델 takeaway | MVP 적용할 정확한 위치 | 직접 재사용 가능 여부 | 라이선스/주의점 |
|---|---|---|---|---|---|---|
| **1. mini_foundry_public** | `frontend/components/dashboards/DashboardCanvas.tsx`, `DataBindingPanel.tsx`, `FilterBar.tsx`, `ComponentPalette.tsx`, `PropertiesPanel.tsx`; `frontend/components/ontology/OntologyGraph.tsx`; backend `app/dashboards/{models,service,validation,permissions,registry,cache}.py` | `react-grid-layout` 기반 x/y/w/h 드래그·리사이즈 canvas(`<GridLayout layout={...} cols={12} isDraggable isResizable onLayoutChange=.../>`); 컴포넌트 타입별 `PropertiesPanel`; `sql_query/dataset/static` 3-tab 데이터 바인딩(Monaco SQL 에디터 포함); `date_range/select/multi_select/search` FilterBar | `DashboardComponent{id, component_type, config, data_binding, position:{x,y,w,h}}`; `Binding = sql_query \| dataset \| static` union type; board 실행을 감싸는 별도 backend `validation.py`/`permissions.py`/`cache.py` 모듈 분리 | `web/src/features/dashboard/DashboardGridCanvas.tsx`(신규, P0)의 `react-grid-layout` 통합 패턴; `DashboardBoard.x/y/w/h`(`dashboard_models.py`, P0) 스키마 설계 근거; `BoardInspector.tsx` 바인딩 편집기 고도화(P1) | 코드 그대로 복붙은 불가(Next.js App Router + Tailwind 의존, 우리는 Vite+커스텀 CSS) — **패턴·스키마 설계만 채택**, `react-grid-layout` 통합 코드는 구조적으로 거의 그대로 이식 가능 | **MIT**(Abdullrahman Bahar, 2026) — 재사용 자유. 원문 주석/구조를 그대로 옮기지 말고 우리 타입 체계로 재작성 |
| **2. openfoundry-emulator** | `apps/app-console/src/pages/Contour.tsx`; `apps/app-workshop/src/components/Canvas.tsx`; `apps/app-workshop/src/widgets/widget-registry.ts`; `apps/app-workshop/src/store/page-store.ts`; `apps/app-console/src/components/DataTable.tsx` | `Contour.tsx`는 세로 파이프라인 UI — Board 카드 사이 "+" connector로 `table/filter/groupby/aggregate/chart` 삽입, 각 단계가 이전 단계 결과를 변형(문서 4-1절 Analysis 화면과 정확히 대응); `Canvas.tsx`는 `react-grid-layout` 없이 순수 CSS grid + mouse handler로 만든 경량 12열 드래그/리사이즈(대안 구현 확인용) | `Board{id, type, config}`의 **클라이언트 사이드** 파이프라인 평가(`useMemo`로 단계별 snapshot 계산, 서버 없이 프로토타이핑 가능); `WidgetInstance{id,type,config,position}` + `widget-registry.ts`의 선언적 `configSchema` | `web/src/features/analysis/AnalysisPathCanvas.tsx`(신규, P1) — `Contour.tsx`의 파이프라인 UI/평가 구조를 **서버사이드 실행**으로 옮겨 재구현; `BoardCatalogDefinition`을 `widget-registry.ts`의 `configSchema` 패턴으로 확장(P1/P2) | UI 패턴·상태 모델은 강하게 참고할 가치가 있으나 Blueprint 의존이 깊고 client-only 평가 방식이라 부분 재작성 필요 | **Apache-2.0** — 재사용 가능(수정 파일에 변경 고지, NOTICE 유지 권장) |
| **3. contour-translation** | `contour-translator/contour_render_specs.py`(전체), `contour_translator.py` | UI 코드 아님(순수 백엔드 변환 로직) | `build_render_spec(board_type, board_state, board_view_state, title) -> dict`가 반환하는 `{specVersion, kind, title, isRenderable, ...}` 정규화 스펙; `kind` enum 15종(`histogram/timeseries/chart/table/filter/expression/aggregate/pivot_table/join/join_rows/sort/calculation/markdown/input_dataset/input_ref/unsupported/error`); **"번역이 실패해도 절대 예외를 던지지 않고 `kind="error"`로 감싼다"**는 방어적 설계 원칙 | `api/factory_signal_board/analysis_render_specs.py`(신규, P1) — 우리 board kind에 맞춘 `render_spec` 빌더로 직접 이식; `DashboardBoard.render_spec` 필드 설계의 직접 근거 | 우리 board 모델은 Contour의 Latitude 내부 클래스가 아니라 자체 정의이므로 `_normalize_column` 등 세부 구현은 새로 작성해야 하지만, **디스패치 테이블 구조와 "절대 예외를 던지지 않는다"는 원칙은 그대로 채택** | **MIT**(Sibyl Advisory, 2026) — 재사용 자유 |
| **4. palantir-blueprint** | `packages/core`, `packages/table`, `packages/select`, `packages/datetime`, `packages/icons`(공식 Blueprint.js 모노레포 원본 그대로) | `HTMLTable`/`HTMLSelect`/`Tag`/`Card`/`Spinner`/`NonIdealState` 등 고밀도 업무용 UI primitive — `openfoundry-emulator`의 `Contour.tsx`가 실제 이 라이브러리로 구현되어 톤이 이미 검증됨 | 해당 없음(순수 UI 컴포넌트 라이브러리, 상태 모델 없음) | `web/src/features/analysis/*`의 Result Inspector·필터 드롭다운 등 고밀도 표 UI에 `@blueprintjs/core`의 `HTMLTable`/`NonIdealState`/`Tag`만 **선택적으로 npm 설치**해 사용(P1) | **소스 복사가 아니라 npm 패키지로 정식 설치**(`@blueprintjs/core`) — 재사용 가능하나 `Navbar`/`Drawer` 등 우리 `styles.css` 디자인 시스템과 충돌하는 컴포넌트는 도입하지 않음 | **Apache-2.0**, Palantir 공식 오픈소스 — 안전 |
| **5. OpenFoundry** | `apps/web/src/lib/components/dashboard/{DashboardGrid.svelte, WidgetFactory.svelte, ChartWidget/TableWidget/KPIWidget.svelte}`; `apps/web/src/lib/components/ontology/GraphView.svelte`; `README.md`(제품 정보구조) | `DashboardGrid.svelte`는 x/y 좌표 없이 순수 12-col CSS grid + `colSpan/rowSpan` + "W-/W+/H-/H+" 버튼 리사이즈(`react-grid-layout` 없이도 가능한 접근성 대안 확인); `WidgetFactory.svelte`는 위젯 타입 dispatch + SQL 템플릿에 필터 주입(`applyDashboardQueryTemplate`) + 로딩/에러/새로고침 UX | `DashboardWidget{id, type, layout:{colSpan,rowSpan}, query:{sql,limit}}`, `DashboardFilterState` 템플릿 치환 | `BoardInspector.tsx`의 버튼식 리사이즈(모바일 접근성 보완, P0 병행 고려); `GraphView.svelte`는 React Flow 도입 시 상태 관리 패턴 참고(P2) | **Svelte 프레임워크**라 코드 이식 불가(우리는 React) — 패턴/스키마만 참고 | README는 **Apache-2.0**을 명시하지만 **로컬 `LICENSE` 파일 내용이 비어 있음** — 실제 사용 전 GitHub 원본에서 라이선스 재확인 필수 |
| **6. palantir-demo** | `src/App.jsx`; `src/components/{Dashboard, GlobeComponent, MarketTickers, NewsFeed, EventDetailModal}.jsx` | 다크 테마 실시간 "situation room" 스타일(3D Globe, 시세 티커, 뉴스 피드, 이벤트 상세 모달) — Executive Overview 탭의 시각적 무드(다크/고대비/실시간감) 참고 가치는 있으나 제조 도메인과 직접 매칭되지 않음 | 해당 없음(정적 mock 데이터 기반 데모, 재사용 가능한 상태 모델 없음) | **적용하지 않음** — 디자인 무드보드 참고 수준으로만 열람, 코드/구조 이식 없음 | 불가 | **LICENSE 파일 없음**(리포지토리에 라이선스 명시 없음) — 코드 복사 금지, 시각적 아이디어만 참고 |
| **7. Gods_Eye** | `src/layers/{aircraft, ships, satellites, cameras, buildings, gpsJamming}.js`; `src/store`; `src/services` | 지도 위 다중 레이어 on/off(항공기/선박/위성/카메라/건물/GPS 교란) 패턴 — 향후 "설비/공장 지도" 요구가 생기면 레이어 패널 UX만 참고 가능, 현재 MVP 로드맵에는 지도 요구사항이 없음 | 레이어별 독립 데이터 소스 + 실시간 갱신 스토어, MapLibre/Cesium류 지도 SDK와 강결합 | **적용하지 않음**(로드맵 외 범위, P2 이후 지도 요구가 확정되면 레이어 패널 UX만 재참고) | 불가 | **GPL-3.0** — copyleft 강제 조항으로 파생물 전체를 GPL로 공개해야 하므로 폐쇄형 MVP 코드베이스에 **단 한 줄도 복사 불가**. 아이디어 수준 참고만 허용 |

### 요약: 레퍼런스별 한 줄 결론

1. **mini_foundry_public** — `react-grid-layout` 통합과 `x/y/w/h` 스키마의 1차 이식 대상(MIT).
2. **openfoundry-emulator** — Analysis 파이프라인 UI/평가 구조의 1차 이식 대상(Apache-2.0).
3. **contour-translation** — `render_spec` 계약 설계의 직접 근거(MIT, 코드량이 작아 가장 순수하게 재사용 가능).
4. **palantir-blueprint** — 컴포넌트가 아니라 **의존성**으로 선택 채택(Apache-2.0, 공식).
5. **OpenFoundry** — 대안적 grid 구현·위젯 팩토리 패턴 참고(라이선스 재확인 필요).
6. **palantir-demo** — 코드 재사용 불가, 시각 자료만(라이선스 없음).
7. **Gods_Eye** — 코드 재사용 절대 불가(GPL-3.0), 아이디어만.

---

## 3. Palantir Contour UI에 최대한 근접한 화면 구조 제안

이 절은 `palantir-contour-dashboard-benchmark.md` 10절("권장 Target UI")을 전제로, 문서가 요구한 10개 항목을 현재 코드와 대조해 구체화한다.

### 3-1. Analysis 편집 화면

현재 존재하지 않는 신규 화면(`/app/analysis/:analysisId`, 5절에 wireframe/component tree). `Contour.tsx`의 세로 파이프라인 + `mini_foundry_public`의 `PropertiesPanel` 패턴을 결합한다.

### 3-2. Dashboard 소비 화면

기존 `ManufacturingApp.tsx` + `DashboardShell.tsx`를 그대로 유지하되, `BoardCanvas.tsx`만 `DashboardGridCanvas.tsx`(react-grid-layout)로 교체한다(4절 상세).

### 3-3. 좌측 rail / 중앙 canvas / 우측 inspector

Dashboard 쪽은 이미 `ContextPanel`(좌) / `BoardCanvas`(중) / `BoardInspector`(우) 3분할이 구현되어 있다. Analysis 쪽은 동일한 3분할 패턴을 새로 만들되 좌측은 **Board rail**(Contour의 category+검색 toolbar, `BoardCatalogPanel.tsx`를 확장), 우측은 **Data/Interaction/Access 3탭 Inspector**(`palantir-contour-dashboard-benchmark.md` 2.1절 구조를 그대로 채택)로 구성한다.

### 3-4. Board Catalog

`BoardCatalogPanel.tsx`는 이미 카테고리·검색·대상 탭 선택을 지원한다. 부족한 것은 **호환성 필터**(레퍼런스 문서 C-11 "input_kind가 rows면 Filter/Join/Expression/Group, aggregate면 Chart/Metric만 활성화")이며, 이는 Analysis 쪽 신규 `AnalysisBoardRail`에서만 필요하다(Dashboard의 Board Catalog는 지금처럼 호환성 필터 없이 유지해도 무방 — Dashboard board는 서로 데이터 파이프라인으로 연결되지 않기 때문).

### 3-5. Parameter / Filter

`ContextPanel.tsx` + `DashboardParameterDefinition`(현재 4종: `selected_event_id`, `selected_equipment_id`, `status_filter`, `intent`)이 이미 구현되어 있다. Analysis 화면에서는 `line`, `failure_type`, `severity`, `period`, `risk_threshold` 같은 분석용 typed parameter가 추가로 필요하다(`palantir-contour-ui-reference.md` C-06 절이 이미 제안한 목록).

### 3-6. Chart-to-chart filtering

Dashboard 쪽은 `_dependency_graph()`(`dashboard_service.py`)로 이미 구현되어 있다. 다만 현재는 **파라미터 선택 전파**(예: `selected_event_id`)만 가능하고, Contour처럼 **차트 브러시/클릭 선택이 하류 row-set을 실제로 제한**하는 것은 Analysis 경로가 생겨야 가능하다(4-4절 dependency graph 설계 참고).

### 3-7. Table result verification

현재 없음(1-2절 gap). `EvidenceTable`류 고정 렌더러와 별개로, Analysis 경로의 모든 변형 board에 접이식 `AnalysisResultInspector`(행 수/컬럼/null rate/중복 key/샘플 50행/`elapsed_ms`/`cache_hit`)를 붙인다. `openfoundry-emulator`의 `DataTable.tsx`(`ColumnDef<T>{key,header,render,sortable}` 패턴)를 얇게 재구현하되, 실제 테이블 렌더는 로드맵에서 채택한 **TanStack Table**로 한다(6절).

### 3-8. Evidence / Action drill-down

이미 MVP의 강점이다(`DashboardBoardRenderer.tsx`의 Evidence/Report/UIBlock 렌더러 + `record_decision`/`add_note`/`invoke_ontology_action`). Analysis 경로에는 이 렌더러를 그대로 감싸는 `evidence`/`action` kind의 board 2종만 추가하면 된다(P2, 7절).

### 3-9. Saved view / Share / PDF snapshot

이미 강점(1-1절). Analysis 쪽에는 `AnalysisResultSnapshot`(실행 input·파라미터·데이터 버전·결과 해시)만 신규로 필요하며, 이는 기존 `ExportCheckpoint{snapshot_hash, content_hash}` 패턴을 그대로 확장하면 된다(4-4절).

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

**3단계 — 프론트 교체**: `BoardCanvas.tsx` → `DashboardGridCanvas.tsx`(신규, `react-grid-layout` 사용). `mini_foundry_public`의 `DashboardCanvas.tsx` 통합 패턴을 그대로 채택한다.

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
- **연결 지점**: Analysis 화면의 각 board 카드에 `[+ Add to dashboard]` 버튼을 두고, 클릭 시 `DashboardBoard{source:"analysis_board", analysis_board_ref: <AnalysisBoard.id>}`를 생성한다. **값을 복제하지 않고 참조만 저장**하므로 Analysis 쪽에서 쿼리 정의를 바꾸면 Dashboard 쪽 렌더링도 최신 결과를 반영한다(`palantir-contour-ui-reference.md` C-16의 "동일 board의 query spec을 중복 저장하지 않는다" 원칙).
- **기존 45개 catalog board는 전혀 건드리지 않는다** — `source="catalog_board"`가 기본값이므로 `dashboard_catalog.py`의 운영/거버넌스 board(Evidence/Action/Audit 계열)는 지금 그대로 유지된다.

### 4-4. 보드 정의·데이터 바인딩·render spec·dependency graph·parameter binding 계약

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
    input_board_id: str | None       # 상류 board id — 진짜 DAG의 근간
    object_type: str | None          # kind == input_object_set일 때만
    config: dict[str, Any]           # kind별 설정(필터 조건 / group_by 컬럼 / join 관계 등)
    render_spec: dict[str, Any]      # contour_render_specs.py 스타일 정규화 스펙(아래)
    output_schema: list[dict] | None # [{name, field_type}], Result Inspector용
    order: int
    created_by: str
    created_at: str

class Analysis(StrictModel):
    id: str
    workspace_id: str
    display_name: str
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
    board_id: str
    parameter_state: dict[str, Any]
    row_count: int
    elapsed_ms: int
    cache_hit: bool
    executed_by: str
    executed_at: str
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

**Dependency graph(진짜 DAG)**: Analysis 경로는 `input_board_id`로 명시적 방향성을 갖는다(Contour의 "위→아래 순차 경로"). Dashboard의 기존 `_dependency_graph()`(파라미터 이름 교집합 기반)는 그대로 두되, `source="analysis_board"`인 board가 섞여 있으면 **파라미터 전파 + 상류 재계산 트리거**를 함께 수행하도록 확장한다.

**Parameter binding 계약**: 기존 `DashboardParameterDefinition`(scope: `dashboard|tab|board`)을 Analysis에도 그대로 재사용한다(`palantir-contour-ui-reference.md` C-06 원칙). 추가로 `line`, `failure_type`, `severity`, `period`, `risk_threshold` 5종을 신규 정의한다.

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
| POST | `/api/analyses/{id}/boards/{board_id}/run` | 실행 → `AnalysisRun` + 미리보기 행(paginated) + `output_schema` 반환 | 신규(P1) |
| POST | `/api/analyses/{id}/boards/{board_id}/add-to-dashboard` | `DashboardBoard{source:"analysis_board"}` 생성 | 신규(P1) |
| GET | `/api/ontology/graph` | 기존 `traverse()`를 React Flow 노드/엣지 포맷으로 변환해 반환 | 신규(P2) |

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
DashboardPage  (route: /app/dashboard/:dashboardId, 기존 ManufacturingApp.tsx가 이 라우트로 확장)
└── DashboardShell                (기존 유지, 변경 없음)
    ├── header                    (project/workspace picker, view/edit switch, catalog, save view, share, export)
    ├── ContextPanel               (좌측 parameter rail — 기존 유지)
    ├── DashboardGridCanvas        (신규: BoardCanvas.tsx 대체, react-grid-layout 기반)
    │   └── GridLayout
    │       └── DashboardBoardFrame × N   (draggable/resizable)
    │           ├── DashboardBoardHeader  (affected chip, fullscreen, hidden/duplicate/remove — 기존 유지)
    │           └── DashboardBoardRenderer
    │               ├── (source="catalog_board") 기존 switch 그대로
    │               └── (source="analysis_board") render_spec 렌더러 신규 분기(P1)
    ├── BoardInspector             (우측, 기존 확장: bindings를 object_set picker로 고도화)
    └── BoardCatalogPanel          (기존 + "내 Analysis에서 가져오기" 탭 신규 추가)
```

---

## 6. 기술 선택: 지금 도입 / 나중에 검토 / 도입하지 않음

| 기술 | 결정 | 근거 |
|---|---|---|
| **React Grid Layout** | **지금 도입(P0)** | `mini_foundry_public`이 정확히 이 조합(12열, `isDraggable`/`isResizable`, `onLayoutChange`)으로 검증. `BoardCanvas.tsx` 교체에 필요한 API가 이미 우리 요구(x/y/w/h, mandatory board 리사이즈만 허용 등)를 그대로 감쌀 수 있음. MIT, 번들 작음 |
| **Apache ECharts** | **지금 도입(P0~P1)** | `SensorLineChart`/`ExecutiveRiskTrend` 등 기존 차트 board를 대체·확장하며, `dataZoom`/`brush`/클릭 이벤트를 `SelectionFilter`로 변환하는 데 적합(`palantir-contour-ui-reference.md` C-12 원칙). Apache-2.0 |
| **TanStack Table** | **지금 도입(P1)** | Result Inspector·Equipment Risk Table 등 고밀도 검증용 표에 적합. Headless라 `web/src/styles.css` 커스텀 디자인 시스템과 충돌 없음. MIT |
| **Blueprint(선택 컴포넌트만)** | **지금 도입(P1, 부분)** | `HTMLTable`/`NonIdealState`/`Tag`/`Spinner` 등 소수 primitive만 `@blueprintjs/core` npm 의존성으로 추가. `openfoundry-emulator`의 `Contour.tsx`가 이미 검증한 조합. `Navbar`/전체 테마는 도입하지 않음(기존 디자인 시스템과 충돌) |
| **React Flow(`@xyflow/react`)** | **나중에 검토(P2)** | Object/lineage graph는 P2 스코프. `mini_foundry_public`의 `OntologyGraph.tsx`가 정확한 패턴(커스텀 노드, 디바운스 레이아웃 저장) 제공. Apache-2.0급 라이선스, 도입 자체엔 문제 없음 — 단지 우선순위가 P2 |
| **Vega-Lite** | **나중에 검토(도입 보류)** | ECharts로 커버 가능한 영역과 중복. `render_spec`을 완전 선언형으로 만들 때 후보로만 남겨둠. 지금 도입하면 차트 렌더러가 2종(ECharts+Vega-Lite)이 되어 유지보수 비용만 늘어남 |
| **MapLibre GL JS** | **나중에 검토(로드맵 미확정)** | 현재 MVP 요구사항에 "설비/공장 지도"가 없음. `Gods_Eye`는 GPL이라 코드 재사용 불가, 패턴만 참고 가능. 지도 요구가 확정되면 그때 재검토 |
| **AG Grid Enterprise** | **도입하지 않음** | 상용 라이선스 비용 발생. TanStack Table(무료)로 정렬/필터/페이지네이션/가상화 요구를 충분히 충족 가능. Enterprise 전용 기능(클라이언트 pivot, row grouping UI)은 우리 설계상 **서버사이드 Group/Aggregate board**가 담당해야 하므로(4-4절) 클라이언트 그리드 라이선스에 의존할 이유가 약함 |
| **Apache Superset(임베드)** | **도입하지 않음** | 별도 서비스 배포·인증 연동 비용 발생. Superset 자체 권한 모델과 MVP의 세밀한 object/property/action 권한(`ontology_service.py`)을 이중 관리해야 함. 임베드된 대시보드가 Evidence/Action drilldown과 통합되지 않아 "운영 행동은 승인 경계를 통과한다"는 UI 원칙(레퍼런스 문서 2절 원칙 4)을 satisfy할 수 없음 |
| **Cube(semantic layer)** | **도입하지 않음(PostgreSQL 전환 후 재검토)** | 현재 SQLite 기반 + Ontology adapter 계층(`ontology_adapter.py`)이 이미 semantic layer 역할을 부분적으로 수행 중이라 중복 계층이 됨. PostgreSQL 전환(현재 70%, `docs/30-implementation/implementation-status.md`)이 완료된 뒤, 대량 집계 쿼리 성능이 실제로 병목이 될 때 재검토 |

### AG Grid Enterprise / Superset / Cube 도입 시 구조상 단점 상세

- **AG Grid Enterprise**: 연간 라이선스 비용 + 팀 규모별 과금. `dashboard_service.py`의 `_validate_board`가 수행하는 세밀한 role-based binding 검증을 클라이언트 그리드 라이브러리 레벨에서 재현할 수 없어, 결국 서버 검증 로직은 그대로 유지한 채 프론트만 무거워짐.
- **Superset embed**: 자체 사용자/역할 시스템을 가지고 있어 우리 8종 `AppRole` + org/project/workspace 3단 scope(`project_context.py`)와 매핑 계층을 별도로 만들어야 함. 감사(`ExportCheckpoint`, `record_audit`)가 Superset 내부 export와 이원화되어 "공유 링크와 PDF snapshot은 권한을 우회하지 않는다"는 완료 기준(8절)을 두 시스템에서 각각 보장해야 하는 이중 부담 발생.
- **Cube**: 캐싱·집계 성능은 매력적이지만, `ontology_service.py`가 이미 `ObjectType`/`LinkType` 단위로 조회를 추상화하고 있어 Cube의 semantic model과 우리 Ontology 모델이 **같은 역할을 두 벌**로 갖게 됨. 스키마 동기화 비용(Ontology 변경 시 Cube 모델도 매번 갱신)이 실질 편익보다 클 가능성이 높음.

---

## 7. 구현 로드맵 (P0 / P1 / P2)

### P0 — Dashboard를 Contour형 12열 grid로 완성

| 항목 | 내용 |
|---|---|
| 변경 파일 | `api/factory_signal_board/dashboard_models.py`(`DashboardBoard.x/y/w/h/source/analysis_board_ref` 추가), `dashboard_catalog.py`(자동 배치 헬퍼), `dashboard_service.py`(`_backfill_grid_position`) |
| 신규 파일 | `web/src/features/dashboard/DashboardGridCanvas.tsx`, `web/src/features/dashboard/gridLayout.ts` |
| 삭제 대상 | `web/src/features/dashboard/BoardCanvas.tsx`(`DashboardGridCanvas.tsx`로 대체) |
| 신규 타입/API/DB | 신규 API 없음(`PUT /api/dashboards/preferences` payload 확장). DB 테이블 변경 없음(payload_json 내부 필드만 추가, 애플리케이션 레벨 backfill) |
| UI 기능 | 자유 드래그/리사이즈, 12열 grid, 겹침 방지, 기존 hidden/mandatory/fullscreen/catalog 기능 100% 유지 |
| 테스트 전략 | 프론트: `gridLayout.ts` 왕복 변환 단위 테스트(좌표 손실 없음), `DashboardGridCanvas.test.tsx`(react-grid-layout mock). 백엔드: `tests/test_dashboard_grid_migration.py`(신규) — 기존 8개 역할 템플릿(`width`만 있는 레코드)을 로드했을 때 자동으로 `x/y/w/h`가 채워지는지 검증. E2E: `web/e2e/gold-flow.spec.ts`에 드래그·리사이즈 시나리오 추가 |
| 완료 조건 | 기존 8개 역할 템플릿이 전부 오류 없이 자동 마이그레이션되어 렌더링됨; 드래그/리사이즈 후 저장 → 재로그인 시 위치 복원; `mandatory` board는 리사이즈는 가능하되 삭제/숨김은 여전히 불가 |
| 예상 리스크 | `react-grid-layout`은 SSR 미지원(비이슈, Vite CSR이므로 무관); row-fill 배치 알고리즘 버그로 board가 겹치거나 유실될 위험 → dry-run 검증 스크립트 필요; 기존 Saved View/공유 링크에 저장된 layout snapshot과의 하위호환 확인 필요 |

### P1 — Analysis Path와 검증

| 항목 | 내용 |
|---|---|
| 신규 파일(백엔드) | `api/factory_signal_board/analysis_models.py`, `analysis_repository.py`, `analysis_service.py`, `analysis_render_specs.py`; `api/ontology_dashboard/routers/analysis.py`(신규, `main.py`에 등록) |
| 신규 파일(프론트) | `web/src/features/analysis/{AnalysisShell.tsx, AnalysisPathCanvas.tsx, AnalysisBoardCard.tsx, AnalysisResultInspector.tsx, AnalysisInspector.tsx, AddToDashboardDialog.tsx, types.ts, api.ts}` |
| 변경 파일 | `web/src/routing.ts`(`/app/analysis/:analysisId` 추가), `web/src/App.tsx`(라우트 매핑), `api/factory_signal_board/ontology_service.py`(`aggregate_objects()` 신규 메서드), `api/ontology_dashboard/routers/ontology.py`(집계 엔드포인트 추가) |
| 신규 DB 테이블 | `analyses(id, workspace_id, display_name, owner_user_id, status, created_at, updated_at, organization_id, project_id)`; `analysis_boards(id, analysis_id, kind, title, input_board_id, config_json, render_spec_json, output_schema_json, order, created_by, created_at)`; `analysis_runs(id, analysis_id, board_id, parameter_state_json, row_count, elapsed_ms, cache_hit, executed_by, executed_at)`; `dataset_refs(id, analysis_id, object_type, workspace_id, as_of_version, created_at)` — SQLite `api/migrations/sqlite/0005_analysis_path.sql` + PostgreSQL `api/migrations/postgresql/0004_analysis_path.sql` 양쪽 작성 |
| UI 기능 | Filter/Join(허용 관계 3종)/Group by/Aggregate/Chart/Table/Text/Verify-Table 8종 board; `AnalysisResultInspector`(rows/columns/null-rate/dup-key/sample 50행/`elapsed_ms`); "Add to dashboard" 다이얼로그 |
| 테스트 전략 | 백엔드: `tests/test_analysis_path.py`(신규) — kind별 실행 결과 검증, owner/editor/viewer RBAC, workspace 격리, Join 화이트리스트 강제. 프론트: 컴포넌트 테스트 + Playwright E2E(시나리오: "분석가가 Filter→Group→Aggregate→Chart 경로를 만들고 저장한다") |
| 완료 조건 | `palantir-contour-ui-reference.md` 8절의 1번째 완료 기준 — "분석가가 Risk Event 입력에서 Filter → Group → Aggregate → Chart 경로를 만들고 저장할 수 있다" 충족 |
| 예상 리스크 | SQLite에서 대량 row group-by 성능 저하 → `LIMIT`/페이지네이션 강제, PostgreSQL 전환 전까지 워크로드 상한 명시 필요; Join을 허용 관계 화이트리스트(`RiskEvent→Equipment`, `RiskEvent→Evidence`, `Equipment→WorkOrder`)로 하드코딩해 임의 SQL 인젝션 위험 원천 차단 |

### P2 — 운영화와 온톨로지 결합

| 항목 | 내용 |
|---|---|
| 신규 파일 | `web/src/features/ontology/OntologyGraph.tsx`(React Flow, `mini_foundry_public` 패턴 이식); `web/src/features/analysis/boards/{EvidenceBoard.tsx, ActionBoard.tsx}`(기존 Evidence/Recommended Actions 렌더러 재사용); `scripts/export_analysis_spec.py` |
| 변경 파일 | `api/ontology_dashboard/routers/ontology.py`(`GET /api/ontology/graph` 신규 — 기존 `traverse()`를 React Flow 포맷으로 wrapping) |
| 신규 DB(선택) | `analysis_join_policies(id, source_object_type, link_type, target_object_type, approved_by, created_at)` — Join 화이트리스트를 하드코딩에서 관리 테이블로 승격할 경우에만 |
| UI 기능 | 허용 관계 기반 Join board; Evidence board의 source reference/lineage 표시; Action board(작업 생성/배정/승인 Ontology Action 호출); Analysis spec → scheduled batch job export(`Export Analysis Spec` JSON) |
| 테스트 전략 | E2E: "운영자가 Dashboard에서 파라미터를 바꾸면 관련 board만 재계산된다", "막대/점/테이블 행 선택이 Evidence/Action board까지 전파된다"(레퍼런스 문서 8절 완료 기준 2·3번과 동일 문구로 시나리오 작성) |
| 완료 조건 | `palantir-contour-ui-reference.md` 8절의 5개 완료 기준 전부 충족 |
| 예상 리스크 | Join 화이트리스트 확장 시 권한 우회 가능성 → 확장 자체에 승인 프로세스 필요; React Flow 도입으로 번들 크기 증가 → 코드 스플리팅(`React.lazy`) 필요 |

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
3. **12열 grid Dashboard + parameter rail + chart-to-chart filtering + saved view + share + PDF export**는 이미 상당 부분 구현되어 있으므로(1-1절) 마무리(P0)만 필요
4. **Evidence/Action drilldown과 감사**는 이미 MVP의 강점 — Palantir 공식 문서가 설명하는 permission 분리(벤치마크 6절)보다 오히려 더 엄격한 governed action 모델(`idempotency_key`, `record_audit`)을 이미 보유하고 있으므로 유지·확장만 하면 됨
5. **Object/lineage graph**는 RiskEvent 주변 1~2 hop까지만(전체 온톨로지 탐색기가 아님) — `traverse(depth=1|2)` 범위로 제한
6. **PostgreSQL 전환 완료(현재 70%) 전까지는 워크로드 상한**(row limit, query timeout, 5분 캐시)을 Analysis 실행 API에 명시적으로 건다

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
docs/40-ui-ux/reference/palantir-contour-ui-reference.md
docs/40-ui-ux/reference/palantir-contour-dashboard-benchmark.md
docs/30-implementation/implementation-status.md
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
