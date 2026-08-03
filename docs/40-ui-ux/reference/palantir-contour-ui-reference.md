# Palantir Contour UI 구현 레퍼런스

> 작성일: 2026-08-01  
> 범위: 사용자가 지정한 Palantir 공식 문서 25개를 바탕으로 만든 **구현용 요약**이다. 원문을 복제하지 않으며, 모든 기능 설명은 MVP 설계로 재해석했다. 이미지·GIF는 Palantir 공식 문서의 원본 URL을 참조하고, 동영상은 공식 YouTube 링크로 연결한다.

## 1. 만들려는 제품의 경계

MVP는 Palantir Foundry 전체를 복제하지 않는다. 대신 제조 예지보전 영역에서 다음 두 화면을 한 제품으로 구현한다.

```text
Contour Analysis (분석가 화면)
데이터셋 → Filter / Join / Expression / Group / Aggregate / Chart 보드의 경로
                 ↓
Contour Dashboard (운영자 화면)
좌측 파라미터 · 여러 차트의 교차 필터링 · Evidence/Action drill-down
                 ↓
Operational Action (현재 MVP 강점)
점검 생성 · 담당자 배정 · 결과 기록 · 감사 로그
```

현재 MVP의 Dashboard Shell, RBAC, Workspace 범위, Evidence, Action, 저장 View와 감사 기능은 유지한다. 새로 구현할 것은 분석 경로와 고밀도 Contour UI다.

## 2. UI 원칙

1. **Analysis와 Dashboard를 분리한다.** Analysis는 데이터를 만드는 편집 공간이고, Dashboard는 읽기·탐색·공유 중심 화면이다.
2. **보드는 순차적 데이터 경로다.** 각 보드는 앞 보드의 결과를 입력으로 삼는다. 단순한 독립 위젯 모음이 아니다.
3. **파라미터와 선택은 명시적 의존성 그래프를 가진다.** 한 차트의 선택이 어느 보드에 영향을 주는지 보드 헤더에서 보여 준다.
4. **운영 행동은 별도 승인 경계를 통과한다.** `Run action`은 대시보드에서 보이되 현재 MVP의 권한·Evidence·감사 계약을 우회하지 않는다.
5. **정확성은 화면 기능이다.** 데이터 버전, 시간대, 비결정성, 결과 검증과 비용을 UI에 노출한다.

## 3. 공식 문서별 구현 노트

### A. 결과 전달 방식

#### 01. 분석 결과 · 대시보드

- 원문: [대시보드](https://www.palantir.com/docs/kr/foundry/analytics/dashboards/)
- 공식 이미지: ![Contour dashboard](https://www.palantir.com/docs/resources/foundry/analytics/dashboards-contour.png)
- 동영상: [Contour 공식 튜토리얼](https://www.youtube.com/watch?v=W5_rSPG3A84&t=3s)
- 요지: Contour는 분석 결과를 대화식으로 탐색하는 대시보드, Quiver는 오브젝트 중심의 읽기 전용 대시보드, Notepad는 정적 보고서에 적합하다.
- MVP 적용: `Analysis`와 `Operations Dashboard`를 별 라우트로 둔다. 전자는 엔지니어/FDE, 후자는 관리자·현장 역할에 우선 노출한다. 현장 Action까지 필요한 화면은 Dashboard 내부의 governed Action을 사용한다.

#### 02. 분석 결과 · 보고서

- 원문: [보고서](https://www.palantir.com/docs/kr/foundry/analytics/reporting/)
- 공식 이미지: ![Notepad reporting](https://www.palantir.com/docs/resources/foundry/analytics/reporting-notepad.png)
- 동영상: [Foundry 분석 소개](https://www.youtube.com/watch?v=W5_rSPG3A84&t=3s)
- 요지: 상호작용 탐색은 대시보드, 시점 고정·주석·PDF 결과물은 Notepad식 보고서가 담당한다.
- MVP 적용: 현재 PDF export를 유지하되, `ReportSnapshot`에 보드 스냅샷·파라미터·Evidence hash·생성 시각을 저장한다. 라이브 Dashboard를 PDF처럼 다루지 않는다.

### B. Contour 분석 공간

#### 03. Contour 개요

- 원문: [개요](https://www.palantir.com/docs/kr/foundry/contour/overview/)
- 공식 이미지: ![Contour overview](https://www.palantir.com/docs/resources/foundry/contour/overview.png)
- 동영상: [Contour 공식 튜토리얼](https://www.youtube.com/watch?v=W5_rSPG3A84&t=3s)
- 요지: 테이블 데이터를 보드로 변형하고, 탐색 중 만든 결과를 대시보드·데이터셋·파이프라인으로 이어가는 시각적 분석 환경이다.
- MVP 적용: `/app/analysis/:id`를 추가하고, 첫 입력은 `RiskEvent`, `Equipment`, `MaintenanceRecord` 중 하나를 선택한다.

#### 04. Contour 시작하기

- 원문: [시작하기](https://www.palantir.com/docs/kr/foundry/contour/getting-started/)
- 공식 이미지: ![Contour chart tutorial](https://www.palantir.com/docs/resources/foundry/contour/getting-started-chart-tutorial-pt-1.png)
- 동영상: [Contour 튜토리얼](https://www.youtube.com/watch?v=W5_rSPG3A84&t=3s)
- 요지: 데이터셋 선택 → 보드 추가 → 속성 설정 → 결과 확인 → Dashboard 추가의 짧은 학습 경로가 중요하다.
- MVP 적용: 새 분석 화면에 빈 캔버스 대신 **"위험 이벤트 분석 시작"** 템플릿을 제공한다. 첫 보드는 Table, 그 다음 권장 보드는 Filter와 Group by로 제시한다.

#### 05. 분석 경로 생성

- 원문: [경로 생성](https://www.palantir.com/docs/kr/foundry/contour/analysis-create-path/)
- 공식 GIF: ![Create analysis path](https://www.palantir.com/docs/resources/foundry/contour/analysis-create-path.gif)
- 동영상: [Contour 튜토리얼](https://www.youtube.com/watch?v=W5_rSPG3A84&t=3s)
- 요지: 분석은 노드 그래프가 아니라 위에서 아래로 이어지는 보드 경로로 읽힌다. 각 단계는 그 시점의 테이블 결과를 바꾼다.
- MVP 적용: 중앙 캔버스에 `+ Add board` 연결점을 둔다. 보드에는 `input_board_id`와 `output_schema`를 저장하고, 삭제 시 하류 영향 경고를 표시한다.

#### 06. 분석 파라미터화

- 원문: [분석에 파라미터 사용하기](https://www.palantir.com/docs/kr/foundry/contour/analysis-parameterize/)
- 공식 이미지: ![Create parameter](https://www.palantir.com/docs/resources/foundry/contour/analysis-create-parameter.png)
- 동영상: [Contour 튜토리얼](https://www.youtube.com/watch?v=W5_rSPG3A84&t=3s)
- 요지: 날짜·범주·숫자 파라미터를 하나의 정의로 만들고 여러 보드의 구성에 바인딩한다.
- MVP 적용: 기존 `DashboardParameterDefinition`을 Analysis에도 재사용한다. `line`, `failure_type`, `severity`, `period`, `risk_threshold`를 typed parameter로 만들고 어떤 보드가 소비하는지 기록한다.

#### 07. 집계 데이터로 전환

- 원문: [집계된 데이터로 전환](https://www.palantir.com/docs/kr/foundry/contour/analysis-switch-aggregated/)
- 공식 이미지: ![Switch to pivot](https://www.palantir.com/docs/resources/foundry/contour/analysis-switch-to-pivot.png)
- 동영상: [Contour 튜토리얼](https://www.youtube.com/watch?v=W5_rSPG3A84&t=3s)
- 요지: 행 단위 탐색과 `group by + aggregate` 결과는 서로 다른 분석 상태이며, 집계로 전환하면 사용할 수 있는 후속 보드가 달라진다.
- MVP 적용: `RowSet`과 `AggregateSet`을 구분한다. Aggregate 보드는 `count`, `sum`, `avg`, `min`, `max`, `p50/p95`만 허용하고, 원행 drill-down 링크를 보존한다.

#### 08. 분석 공유 및 협업

- 원문: [분석 공유 및 협업하기](https://www.palantir.com/docs/kr/foundry/contour/analysis-share-collaborate/)
- 공식 GIF: ![Share analysis](https://www.palantir.com/docs/resources/foundry/contour/analysis-share.gif)
- 동영상: [Contour 튜토리얼](https://www.youtube.com/watch?v=W5_rSPG3A84&t=3s)
- 요지: 분석 자체는 편집 협업 대상이며, 공유자가 원본 데이터 권한을 우회시키지 않는다.
- MVP 적용: Dashboard template publish와 별도로 `analysis_owner`, `editor`, `viewer`를 둔다. 공유 링크는 선택 파라미터만 전달하고 server-side workspace/RBAC를 재평가한다.

#### 09. 결과 공유

- 원문: [결과 공유](https://www.palantir.com/docs/kr/foundry/contour/analysis-share-results/)
- Git 레퍼런스: [`contour-translation`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/contour-translation/)
- 요지: 편집 가능한 분석 공유와 특정 결과·시점 공유를 구분해야 재현성과 권한 경계가 유지된다.
- MVP 적용: `LiveAnalysisLink`와 `AnalysisResultSnapshot`을 분리한다. 후자는 실행 input·파라미터·데이터 버전·결과 해시를 담는다.

### C. Board 카탈로그와 데이터 변형

#### 10. Boards 개요

- 원문: [Boards 개요](https://www.palantir.com/docs/kr/foundry/contour/boards-overview/)
- 공식 이미지: ![Board toolbar](https://www.palantir.com/docs/resources/foundry/contour/boards-toolbar-overview.png)
- Git 레퍼런스: [`Contour.tsx`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/openfoundry-emulator/apps/app-console/src/pages/Contour.tsx)
- 요지: 보드는 데이터 조작 보드와 시각화 보드로 나뉘며, 보드 타입에 따라 입력·출력과 UI 구성 패널이 달라진다.
- MVP 적용: 초기 Board Catalog는 `Table`, `Filter`, `Join`, `Expression`, `Group`, `Aggregate`, `Chart`, `Metric`, `Text`, `Evidence`, `Action` 10종으로 제한한다.

#### 11. 보드 추가

- 원문: [보드 추가](https://www.palantir.com/docs/kr/foundry/contour/boards-add/)
- 공식 이미지: ![Board toolbar](https://www.palantir.com/docs/resources/foundry/contour/boards-toolbar-overview.png)
- Git 레퍼런스: [`ComponentPalette.tsx`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/frontend/components/dashboards/ComponentPalette.tsx)
- 요지: 컨텍스트에 맞는 보드만 추가 가능해야 한다. 모든 보드를 항상 보여 주면 분석 실수가 늘어난다.
- MVP 적용: `input_kind`가 `rows`면 Filter/Join/Expression/Group, `aggregate`면 Chart/Metric을 활성화한다. Catalog에 "추천"과 "호환 안 됨"을 같이 표시한다.

#### 12. 데이터 필터링

- 원문: [데이터 필터링](https://www.palantir.com/docs/kr/foundry/contour/boards-filter/)
- 공식 GIF: ![Histogram filtering](https://www.palantir.com/docs/resources/foundry/contour/boards-histogram-filter.gif)
- 동영상: [Contour 튜토리얼](https://www.youtube.com/watch?v=W5_rSPG3A84&t=3s)
- 요지: 히스토그램·차트 선택은 단순 강조가 아니라 하류 row set을 제한하는 필터다.
- MVP 적용: ECharts `dataZoom`/`brush`/bar click을 `SelectionFilter`로 변환한다. 선택 보드에는 `N boards affected`와 적용된 filter chip을 보인다.

#### 13. 데이터셋 결합

- 원문: [데이터셋 결합](https://www.palantir.com/docs/kr/foundry/contour/boards-join/)
- 공식 GIF: ![Join board](https://www.palantir.com/docs/resources/foundry/contour/boards-join.gif)
- Git 레퍼런스: [`OntologyGraph.tsx`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/frontend/components/ontology/OntologyGraph.tsx)
- 요지: Join은 키·join type·중복·결측을 명시적으로 선택·확인하게 하는 고위험 변형이다.
- MVP 적용: 첫 버전에서는 허용된 관계만 사용한다: `RiskEvent → Equipment`, `RiskEvent → Evidence`, `Equipment → WorkOrder`. 임의 SQL join은 허용하지 않는다. UI에 cardinality와 매칭되지 않은 행 수를 표시한다.

#### 14. 결과 확인

- 원문: [결과 확인](https://www.palantir.com/docs/kr/foundry/contour/boards-verify-results/)
- 공식 GIF: ![Verify table result](https://www.palantir.com/docs/resources/foundry/contour/boards-verify-table.gif)
- Git 레퍼런스: [`DataTable.tsx`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/openfoundry-emulator/apps/app-console/src/components/DataTable.tsx)
- 요지: 시각화 전에 표·스키마·행 수·null/중복을 보며 단계별 결과를 확인한다.
- MVP 적용: 모든 변형 보드에 접을 수 있는 `Result inspector`를 둔다: 행 수, 컬럼, null rate, 중복 key, sample 50행, upstream version. 차트만 보고 판단하지 않게 한다.

#### 15. 보드 설명

- 원문: [보드 설명](https://www.palantir.com/docs/kr/foundry/contour/boards-descriptions/)
- 공식 이미지: ![Filter configuration](https://www.palantir.com/docs/resources/foundry/contour/board-descriptions-filter-config.png)
- Git 레퍼런스: [`widget-registry.ts`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/openfoundry-emulator/apps/app-workshop/src/widgets/widget-registry.ts)
- 요지: 각 보드는 용도·설정·제약을 갖는다. Table, Filter, Histogram, Chart, Expression, Join 등은 같은 카드가 아니다.
- MVP 적용: `BoardDefinition`에 `input_kind`, `output_kind`, `config_schema`, `allowed_roles`, `renderer`, `query_compiler`를 명시한다. LLM은 이 카탈로그에 있는 board만 제안하도록 한다.

### D. Dashboard 화면

#### 16. Contour Dashboard 개요

- 원문: [대시보드 전체보기](https://www.palantir.com/docs/kr/foundry/contour/dashboards-overview/)
- 공식 이미지: ![Dashboard overview](https://www.palantir.com/docs/resources/foundry/contour/dashboard-overview.png)
- Git 레퍼런스: [`DashboardCanvas.tsx`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/frontend/components/dashboards/DashboardCanvas.tsx)
- 요지: Dashboard는 analysis board의 소비용 배치다. 분석 경로 전체를 편집하는 장소가 아니다.
- MVP 적용: 현재 `/app` Dashboard를 소비 모드로 두고 `/app/analysis`에서 보드를 만든 뒤 `Add to dashboard`로 복사 참조한다. 동일 보드의 query spec을 중복 저장하지 않는다.

#### 17. Contour Dashboard 시작하기

- 원문: [대시보드 시작하기](https://www.palantir.com/docs/kr/foundry/contour/dashboards-getting-started/)
- 공식 이미지: ![Create dashboard](https://www.palantir.com/docs/resources/foundry/contour/dashboard-creating-a-dashboard.png)
- 공식 GIF: ![Chart-to-chart filtering](https://www.palantir.com/docs/resources/foundry/contour/dashboard-chart-to-chart-filtering.gif)
- 동영상: [Dashboard 생성 영상](https://www.youtube.com/watch?v=0A3sGymV6kY)
- 요지: 탭, 드래그 재배열, 보드 크기, 텍스트, 좌측 파라미터, 전체화면, PDF export, 차트 간 필터링이 완성된 Dashboard 경험을 만든다.
- MVP 적용: 현재 Shell에 이미 탭·좌측 context·fullscreen·export가 있다. 다음 변경은 `width`만 있는 레이아웃을 `x/y/w/h` 12열 grid로 바꾸고, Text board와 차트 선택 전파를 실제 실행기로 연결하는 것이다.

### E. 데이터셋·재현성·운영화

#### 18. 데이터셋으로 저장하기

- 원문: [데이터셋으로 저장하기](https://www.palantir.com/docs/kr/foundry/contour/datasets-save/)
- Git 레퍼런스: [`openfoundry-emulator`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/openfoundry-emulator/)
- 요지: 탐색 결과를 이름 있는 데이터셋으로 저장하면 이후 분석과 파이프라인에서 재사용할 수 있다.
- MVP 적용: `Save result as dataset`은 우선 SQLite/Parquet materialized view로 시작한다. 저장물에는 source versions, transform spec, owner, created_at을 포함한다.

#### 19. 입력 데이터셋 버전 변경

- 원문: [입력 데이터셋 버전 변경](https://www.palantir.com/docs/kr/foundry/contour/change-dataset-version/)
- Git 레퍼런스: [`contour-translation`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/contour-translation/)
- 요지: 데이터 업데이트와 과거 결과의 재현은 다른 요구다. 입력 버전을 바꿀 때 영향을 검토해야 한다.
- MVP 적용: `DatasetRef {id, version}`을 모든 AnalysisRun과 ReportSnapshot에 저장한다. 최신 데이터로 refresh할 때 변경된 행 수와 영향을 받는 보드를 안내한다.

#### 20. 프로젝트 출처

- 원문: [프로젝트 출처](https://www.palantir.com/docs/kr/foundry/contour/project-references/)
- Git 레퍼런스: [`OpenFoundry`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/OpenFoundry/)
- 요지: 분석은 프로젝트·폴더·참조 구조 안에서 발견되고 재사용된다.
- MVP 적용: Project/Workspace 외에 `AnalysisFolder`와 `Reference`를 둔다. 다른 프로젝트 분석을 바로 복제하지 않고 reference로 연결해 원본·권한·버전을 추적한다.

#### 21. Pipeline Builder로 변환

- 원문: [Contour 로직을 Pipeline Builder로 내보내기](https://www.palantir.com/docs/kr/foundry/contour/convert-to-pipeline-builder/)
- Git 레퍼런스: [`mini_foundry_public PipelineCanvas`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/frontend/components/pipelines/PipelineCanvas.tsx)
- 요지: 탐색에서 검증된 변형을 반복 실행 가능한 파이프라인으로 승격한다.
- MVP 적용: 초기에는 `Export Analysis Spec` JSON만 제공한다. 다음 단계에 해당 JSON을 FastAPI batch job 정의로 컴파일하고, 수동 탐색과 운영 배치를 구분한다.

#### 22. 분석 최적화

- 원문: [분석 최적화](https://www.palantir.com/docs/kr/foundry/contour/performance-optimize/)
- Git 레퍼런스: [`mini_foundry_public`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/)
- 요지: 큰 데이터를 다룰 때는 초기에 행·열을 줄이고, 값비싼 join/집계는 필요한 시점까지 미루며, 보드별 비용을 의식해야 한다.
- MVP 적용: server-side pagination, 열 projection, `LIMIT` preview, query timeout, 5분 캐시를 기본으로 둔다. Board Inspector에 `rows scanned`, `elapsed_ms`, `cache hit`을 노출한다.

#### 23. 비결정성

- 원문: [Contour에서의 비결정성](https://www.palantir.com/docs/kr/foundry/contour/correctness-non-determinism/)
- Git 레퍼런스: [`mvp-프로젝트2 Evidence/Export 계약`](../../../schemas)
- 요지: 순서가 보장되지 않은 데이터, 임의 샘플, 현재 시각 의존 계산은 같은 분석이라도 다른 결과를 만들 수 있다.
- MVP 적용: 정렬 없는 first/last, random sampling, `now()` 기반 결과에는 warning badge를 붙인다. Report/Export에는 run timestamp와 deterministic seed, data version을 고정한다.

#### 24. 시간대

- 원문: [Contour에서의 시간대](https://www.palantir.com/docs/kr/foundry/contour/correctness-timezones/)
- Git 레퍼런스: [`mvp-프로젝트2 API`](../../../api)
- 요지: 날짜 필터·일별 집계·상대 시간은 시간대 설정에 따라 결과가 달라질 수 있다.
- MVP 적용: 모든 event timestamp는 UTC 저장, 화면은 Workspace timezone 렌더링, 보드마다 timezone 표시를 기본으로 한다. 교대조 기준 날짜는 별도 `operational_date`로 계산한다.

#### 25. 컴퓨트 사용량

- 원문: [Contour를 사용한 컴퓨트 사용량 계산](https://www.palantir.com/docs/kr/foundry/contour/compute-usage/)
- Git 레퍼런스: [`OpenFoundry`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/OpenFoundry/)
- 요지: 탐색용 분석도 조직 비용·자원 사용량을 만들므로 실행 주체·데이터 크기·계산 비용을 관리해야 한다.
- MVP 적용: 현재는 비용 청구 대신 `AnalysisRunAudit`로 시작한다. `user_id`, `workspace_id`, `input_rows`, `output_rows`, `elapsed_ms`, `cache_hit`, `exported`를 남기고, 관리자 화면에서 집계한다.

## 4. MVP의 실제 UI 설계

### 4-1. Analysis 편집 화면

```text
┌ Global header: Project | Workspace | Analysis name | Save | Run | Share ┐
├ Board rail ───────┬ Analysis path ────────────────────┬ Inspector ─┤
│ Table             │ [Input table]                      │ Board type │
│ Filter            │       │                             │ Input      │
│ Join              │      [+]                            │ Fields     │
│ Expression        │ [Filter: line, severity]           │ Config     │
│ Group/Aggregate   │       │                             │ Preview    │
│ Chart             │      [+]                            │ Lineage    │
│ Metric/Text       │ [Group: equipment → p95 risk]      │            │
│ Evidence/Action   │       │                             │            │
│                   │ [Bar chart / Verify result table]  │            │
└───────────────────┴───────────────────────────────────┴────────────┘
```

- Board rail은 호환 가능한 보드만 활성화한다.
- 중앙 path는 세로 흐름, inspector는 선택된 보드의 data binding·format·result 검증을 담당한다.
- Table/Filter/Join/Expression은 분석용, Chart/Metric/Text/Evidence/Action은 결과 전달용이다.

### 4-2. Operations Dashboard 소비 화면

```text
┌ Header: workspace | dashboard tabs | View/Edit | Share | PDF export ┐
├ Parameter rail ───┬ 12-column responsive dashboard canvas ──────────┤
│ 기간              │ [Risk KPI] [Overdue KPI] [Alert count]            │
│ 라인              │ [Risk trend ─────────────────] [Failure mix]     │
│ 고장 유형         │ [Equipment risk table ───────────────]           │
│ 위험도            │ [Evidence] [Recommended action]                  │
│ 적용 보드 수      │                                                   │
└───────────────────┴─────────────────────────────────────────────────┘
```

- View mode: 필터·차트 선택·전체화면·공유·내보내기.
- Edit mode: grid 배치·크기·탭·텍스트·보드 추가. 분석 변형 자체는 Analysis 화면에서만 수정.
- 차트 선택은 URL에 파라미터로 직렬화하여 share link에도 동일한 탐색 상태를 복원한다.

## 5. 구현 우선순위

### P0 — 현재 Dashboard를 Contour형 화면으로 완성

1. `DashboardBoard`에 `x/y/w/h`, `data_binding`, `parameter_bindings`, `depends_on`, `render_spec` 추가.
2. 현재 단순 `gridColumn span` 캔버스를 12-column draggable/resizable grid로 교체.
3. Chart/Metric/Table/Text board renderer와 좌측 parameter rail을 실제 query 결과에 연결.
4. 선택한 차트의 `SelectionFilter`가 하류 board 재실행을 유발하게 한다.

### P1 — Analysis Path와 검증

1. `Analysis`, `AnalysisBoard`, `AnalysisRun`, `DatasetRef` API/SQLite 계약 추가.
2. Filter, Group, Aggregate, Chart, Verify Table 5개 보드부터 구현.
3. 각 보드에 rows/schema/null/duplicate/elapsed preview를 넣는다.
4. 결과 snapshot, share link, data version, timezone을 저장한다.

### P2 — 운영화와 온톨로지 결합

1. 허용 관계 기반 Join과 React Flow lineage/object graph.
2. Evidence board에서 source reference와 report trace를 표시.
3. Action board에서 작업 생성·배정·승인·audit을 호출.
4. Analysis spec → scheduled batch job export를 제공.

## 6. 기술 선택과 라이선스 경계

| 목적 | 권장 선택 | 근거 |
|---|---|---|
| Grid 편집 | `react-grid-layout` | `mini_foundry_public`이 12열 구성·드래그·리사이즈에 사용 |
| 차트 | ECharts | 같은 레퍼런스의 Dashboard renderer와 잘 맞음 |
| 온톨로지/계보 그래프 | `@xyflow/react` | object/link 및 pipeline graph에 적합 |
| 고밀도 업무 UI | Blueprint를 선택적으로 사용 | 공식 Palantir React UI toolkit, Apache-2.0 |
| Contour 동작 명세 | `openfoundry-emulator`의 `Contour.tsx` | React/TypeScript 기반이며 Filter/Group/Aggregate/Chart 흐름 참고에 적합 |

`palantir-demo`는 라이선스가 명시되지 않았고 `Gods_Eye`는 GPL-3.0이다. 두 프로젝트는 화면 아이디어만 참고하고 코드를 복사하지 않는다. `mini_foundry_public`은 MIT, `openfoundry-emulator`와 Blueprint는 Apache-2.0 조건을 확인한 뒤 필요한 부분만 재사용한다.

## 7. 로컬 Git 레퍼런스 색인

- [`mini_foundry_public`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/): DashboardCanvas, data binding, filter, ontology graph.
- [`openfoundry-emulator`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/openfoundry-emulator/): Contour, Workshop Builder, widget registry, object/action console.
- [`contour-translation`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/contour-translation/): Contour board를 structured render spec으로 옮기는 방식.
- [`palantir-blueprint`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/palantir-blueprint/): 공식 UI component system.
- [`OpenFoundry`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/OpenFoundry/): 제품 정보구조와 service boundaries.
- [`palantir-demo`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/palantir-demo/): dark real-time situation dashboard inspiration only.
- [`Gods_Eye`](../../../../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/Gods_Eye/): map/layer/timeline interaction inspiration only.

## 8. 구현 완료 기준

- 분석가가 Risk Event 입력에서 Filter → Group → Aggregate → Chart 경로를 만들고 저장할 수 있다.
- 운영자가 Dashboard에서 기간·라인·고장 유형을 바꾸면 관련 보드만 다시 계산된다.
- 막대/점/테이블 행 선택이 Evidence와 Action 보드까지 전파된다.
- 보드마다 입력 데이터 버전·시간대·행 수·실행 시간·Evidence 출처를 확인할 수 있다.
- 공유 링크와 PDF snapshot은 권한을 우회하지 않고, 재현 가능한 parameters/version/run metadata를 남긴다.
