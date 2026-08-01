# Stage 43 — Sprint 0~5 Frontend Acceleration Summary

## 목적

네 개 UI 통합 분석 문서의 공통 결론을 바탕으로, 백엔드 분석 실행 엔진과 신규 영속 테이블을 기다리지 않고 Ontology Dashboard의 프론트엔드 분석·대시보드 기능을 빠르게 확장했다.

참고 문서:

- `palantir-ui-integration-analysis-antigravity-opus-4.6.md`
- `palantir-ui-integration-analysis-chatgpt-sol-high.md`
- `palantir-ui-integration-analysis-claude-sonnet5-extra.md`
- `palantir-ui-integration-analysis-chatgpt-sol-extra-high.md`

Canonical product/namespace는 계속 `Ontology Dashboard` / `ontology_dashboard`를 사용한다.

## Sprint 0 — 의존성과 계약

추가된 프론트엔드 의존성:

- `react-grid-layout`
- `echarts`
- `echarts-for-react`
- `@tanstack/react-table`
- `@tanstack/react-virtual`
- `@xyflow/react`
- `@blueprintjs/core`
- `lucide-react`

Blueprint 전체 CSS는 번들 증가가 커서 로드하지 않는다. 패키지는 선택 도입 상태로 유지하며 현재 화면은 동일한 design token 기반 경량 상태 컴포넌트를 사용한다.

프론트 계약:

- `DashboardBoardLayout`
- `RenderSpec`
- `DataBinding`
- `SelectionFilter`
- `BoardSourceReference`
- `VersionPolicy: pinned | latest_published`

백엔드 및 JSON Schema에도 nullable Analysis board source reference를 추가했다.

## Sprint 1 — Dashboard Grid Canvas

신규 구조:

- `web/src/features/dashboard/DashboardGridCanvas.tsx`
- `web/src/features/dashboard/gridLayout.ts`
- 기존 `BoardCanvas.tsx`는 호환 wrapper로 유지

구현 기능:

- 12열 자유 배치
- drag/resize
- x/y/w/h 저장과 재접속 복원
- legacy width/order 자동 backfill
- hidden, mandatory, duplicate, fullscreen 유지
- responsive View와 고정 12열 Edit canvas 분리

## Sprint 2 — 공통 렌더러

신규 렌더러:

- `renderers/EChartsRenderer.tsx`
  - bar, line, pie, histogram
  - click selection
  - rectangle brush selection
- `renderers/DataTableRenderer.tsx`
  - TanStack sorting, global filtering, column visibility
  - virtual scrolling
  - row selection
- `renderers/MetricRenderer.tsx`
  - KPI metric strip

제조 도메인 전용 `AdvancedBoards.tsx`는 위 공통 렌더러를 소비하도록 변경했다.

## Sprint 3 — Cross-filter Engine

신규 파일:

- `web/src/features/dashboard/cross-filter-engine.ts`

구현 기능:

- 표준 `SelectionFilter` 저장
- dependency graph 기반 transitive downstream 계산
- chart click/brush 및 table row selection의 실제 downstream filtering
- Context Panel active filter 표시 및 clear
- 기존 selected event/equipment parameter 계약과 병행

DAG cycle 차단과 서버 동시성 제어는 후속 서버 단계에서 수행한다.

## Sprint 4 — 모듈형 Analysis Path

신규 경로:

- `/app/analysis/:analysisId`

신규 모듈:

- `AnalysisPage.tsx`
- `AnalysisShell.tsx`
- `AnalysisBoardRail.tsx`
- `AnalysisPathCanvas.tsx`
- `AnalysisBoardCard.tsx`
- `AnalysisInspector.tsx`
- `AnalysisResultInspector.tsx`
- `boards/InputObjectSetBoard.tsx`
- `boards/FilterBoard.tsx`
- `boards/GroupBoard.tsx`
- `boards/AggregateBoard.tsx`
- `boards/ChartBoard.tsx`
- `boards/VerifyTableBoard.tsx`

구현 기능:

- React Flow graph 편집
- Input → Filter → Group/Aggregate → Chart/Table 경로
- client-side path evaluation
- 실행 상태와 revision
- result preview, rows/schema/null/duplicate/sample/lineage inspector
- dataset snapshot JSON 저장
- 자유 SQL 대신 field/operator 선택
- Join relationship은 UI에서 `event_id`, `equipment_id`, `model_version`으로 제한

## Sprint 5 — Analysis Reference와 Ontology

- Analysis node를 Dashboard에 값 복제 없이 참조로 추가
- `source.kind = analysis_board`
- `analysis_id`, `analysis_node_id`, `version_policy`, `version` 저장
- Inspector에서 pinned/latest published 정책 편집
- Dashboard reference에서 원본 Analysis URL로 이동
- React Flow Ontology relationship graph 유지
- Result Preview와 Flow canvas가 겹치지 않도록 독립 grid 영역으로 분리

## 안정성 개선

기능 확장 과정에서 함께 수정한 항목:

- Dashboard template seed의 SQLite 동시 삽입 경쟁을 `INSERT OR IGNORE` 방식으로 제거
- active project 변경 시 중복 Workspace/Event 요청 제거
- stale dashboard request가 최신 scope를 덮어쓰지 않도록 request sequence 적용
- resolved dashboard가 도착하면 catalog/saved-view보다 먼저 shell을 렌더링
- Layout V2와 Analysis source가 preference override에 포함되도록 merge 계약 확장

## 검증 결과

- Frontend production build: 성공
- Vitest: 1 passed
- 전체 Pytest: 84 passed
- 기존 Gold Flow + 신규 UI Playwright: 20 passed
- 신규 E2E 검증 범위:
  - ECharts, virtual table, Ontology graph
  - direct Analysis route
  - client cross-filter
  - Analysis node → Dashboard pinned reference
  - reference 저장 및 reload 복원
  - RGL resize 저장 및 reload 복원
  - dark theme persistence

현재 production JS는 약 1.33 MB, gzip 약 424 KB이다. ECharts brush/toolbox와 React Flow가 초기 번들에 포함되어 있어 route-level lazy loading은 다음 성능 단계의 우선 과제다.

## 의도적으로 남긴 후속 작업

이번 단계는 프론트엔드 vertical slice를 우선했다. 다음 항목은 아직 완료하지 않았다.

- 서버 영속 `Analysis`, `AnalysisBoard`, `AnalysisRun`, `DatasetRef` 모델과 API
- PostgreSQL/SQLite 신규 Analysis migration
- 서버 실행 엔진과 materialized result cache
- 서버사이드 Join relationship whitelist 강제
- Analysis RBAC와 object-level permission의 세밀한 검증
- DAG cycle validation 및 concurrent run conflict 처리
- 서버 계산 기반 null-rate/duplicate/schema profiling
- published analysis version과 immutable run 재현성
- route-level lazy loading 및 vendor chunk 분리

후속 구현 시 네 분석 문서의 P1-4, P1-5, P2-3, P2-4와 테스트·migration 섹션을 기준으로 이어간다.
