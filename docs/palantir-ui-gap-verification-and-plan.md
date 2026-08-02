# Palantir UI 격차 검증 및 구현 후속 기록

- 최초 검증일: 2026-08-02
- 후속 구현 반영일: 2026-08-02
- 기준 문서: `palantir-contour-ui-reference.md`, `palantir-contour-dashboard-benchmark.md`, Palantir UI integration 분석 4종, `07-implementation-status.md`, `09-architecture-decisions.md`, `project3-adapter-contract.md`
- 검증 원칙: 파일 존재가 아니라 route, permission, persistence, 화면, E2E가 함께 연결됐는지를 기준으로 판단한다.

---

## 0. 결론

지난 검증에서 제시한 방향은 유지한다.

- Project 2는 scope, routing, evidence merge, claim validation, checkpoint, audit를 소유한다.
- Text-to-Cypher, graph ETL, graph RAG는 Project 3 안에 유지한다.
- Project 2는 `Project3Client` typed HTTP 경계만 사용하며 임의 Cypher 제출 API를 노출하지 않는다.
- 현재 직접 구현한 checkpoint state machine은 이 제품 범위에서 LangGraph의 핵심 효용을 충족한다. 별도 라이브러리 도입은 release requirement가 아니다.

이번 후속 구현으로 문서의 P0와 P1은 완료됐고 P2 시각 디자인 트랙은 첫 번째 실제 화면과 token 문서까지 시작됐다.

```text
P0 verification and safety closure      VERIFIED
P1 dedicated Agent Evidence UI          VERIFIED
P2 visual token and density first slice IMPLEMENTED_TESTED
Stage 54 initial bundle budget          VERIFIED
```

---

## 1. Multi-store Agent Orchestration 경계

### 유지해야 하는 구현

| 영역 | 구현 | 판단 |
|---|---|---|
| state contract | `api/ontology_dashboard/orchestration/models.py` | `extra="forbid"`, evidence 없는 claim 차단 유지 |
| relational port | `RelationalOntologyPort` | approved Ontology API만 호출하므로 유지 |
| graph port | `Project3GraphPort` | `Project3Client.query()` typed boundary 유지 |
| vector port | `Project3VectorPort` | `Project3Client.rag_search()` typed boundary 유지 |
| orchestrator | `MultiStoreOrchestrator` | route → collect → merge → validate → finish 순서 유지 |
| persistence | `AgentRunRepository` | run, checkpoint, trace 저장 유지 |
| Project 3 client | `integrations/project3/client.py` | arbitrary Cypher method 비노출 유지 |

### 직접 Neo4j driver 재검증

Project 2의 `neo4j.GraphDatabase` 직접 사용은 `polyglot/health.py`의 connectivity probe에만 존재한다. 업무 graph query는 Project 3 client를 통한다.

따라서 현재 경계는 다음과 같다.

```text
Project 2 Neo4j driver → health probe only
Project 2 graph query  → Project3Client typed HTTP
Project 2 direct Cypher submission → not exposed
```

---

## 2. P0 검증 마무리 결과

## 2.1 Analysis Join whitelist

`api/factory_signal_board/analysis_service.py`에 이미 다음 서버 whitelist가 있었다.

```text
risk_event_equipment
risk_event_evidence
equipment_work_order
```

후속 개선으로 run 시점뿐 아니라 Analysis create/update 저장 전에 `_validate_definition()`이 관계를 검사한다. 허용되지 않은 관계는 persistence 전에 `422 contract_validation_failed`로 거부한다.

검증:

```text
tests/test_analysis_path.py
- unknown join relationship rejection
- error code and message assertion
```

## 2.2 DAG cycle validation

기존 `_topological_order()`는 cycle을 탐지했지만 run 시점에만 실행됐다.

후속 개선:

- create 전에 DAG 검증
- update 전에 DAG 검증
- duplicate node ID 검증
- unknown edge node 검증
- cycle이 있으면 저장 전에 `422` 반환

검증:

```text
tests/test_analysis_path.py
- input → filter → input cycle rejection
- "analysis graph must be acyclic" assertion
```

## 2.3 pgvector 실제 소비처

검색 결과 Project 2 자체 `vector_document_chunks`에 대해 embedding insert 또는 similarity search를 실행하는 runtime repository는 아직 없다.

현재 의미는 다음과 같다.

```text
PostgreSQL pgvector
- extension health probe: implemented
- schema and index: implemented when the extension is installed
- plain PostgreSQL migration fallback: embedding_json column, no vector index
- Dataset projection target contract: implemented
- live local embedding writer: not implemented
- live local semantic search consumer: not implemented

Current semantic retrieval
- Project3Client.rag_search() via typed HTTP
```

기능 착시를 막기 위해 `PolyglotHealthService.snapshot()`에 다음 boundary를 명시했다.

```json
{
  "local_pgvector": "infrastructure_and_projection_schema_only",
  "semantic_retrieval": "project3_rag_via_typed_http",
  "graph_queries": "project3_via_typed_http",
  "direct_sql_or_cypher_submission": false
}
```

따라서 발표나 상태 문서에서 현재 Project 2 기능을 “자체 pgvector RAG 완료”로 표현하면 안 된다.

## 2.4 Analysis Result Inspector profile

null count, null rate, distinct count는 이미 서버 `AnalysisService._profile()`이 전체 실행 row에서 계산하고 있었다.

문제가 남아 있던 항목은 duplicate key였다. 프론트엔드가 sample/result rows로 다시 계산하고 있었다.

후속 개선:

- 서버 node result에 `quality` 추가
- `row_count`
- `column_count`
- `null_cell_count`
- 전체 cell 기준 `null_rate`
- `duplicate_key_count`
- `computed_by: "server"`
- 프론트 Result Inspector가 server quality를 우선 사용
- client preview일 때만 fallback 계산

---

## 3. P1 Agent Evidence UI 구현 결과

지난 검증 시점에는 Ontology Ask panel과 Governance trace가 있었지만 독립적인 Agent feature route가 없었다. 이번 후속 구현에서 dedicated workbench를 추가했다.

### Route

```text
/app/projects/:projectId/workspaces/:workspaceId/agent
```

### 신규 파일

```text
web/src/features/agent/
├── AgentWorkbenchPage.tsx
├── AgentQueryBoard.tsx
├── EvidenceTraceList.tsx
├── GroundedClaimList.tsx
├── OrchestrationStepper.tsx
└── types.ts
```

### 연결된 API

```text
POST /api/agent/query
GET  /api/agent/runs/:runId?project_id=:projectId
```

### 화면 기능

- 자연어 질문 입력
- auto/relational/graph/vector/hybrid route 선택
- optional Object Type/Object ID scope
- top-k 상한 입력
- persisted run ID 직접 조회
- 최근 run local history
- URL `?run=` 기반 reload 복원
- answer와 caveat
- claim validation/confidence
- claim의 evidence ID 클릭 → Evidence item으로 scroll
- store별 evidence icon과 label
- source reference
- Dataset Version
- Object ID
- score
- metadata
- route → collect → merge → validate lineage stepper
- store latency와 성공/실패 상태
- persisted trace metadata

### Dashboard drill-down

Dashboard의 `AuditTrace` renderer에 `Agent Evidence에서 추적` 버튼을 연결했다.

이 버튼은 현재 Project, Workspace, Risk Event ID와 질문을 Agent route에 전달한다. 따라서 사용자는 다음 흐름을 가진다.

```text
Dashboard claim
→ AuditTrace board
→ Agent Evidence Workbench
→ claim
→ evidence ID
→ source store / Dataset Version / Object ID / trace
→ Governance persisted run inspection
```

### Permission and isolation

Agent route는 다음을 모두 검증한다.

- `planner.object_query` permission
- principal project scope
- active Project
- workspace scope
- Project에 실제로 속한 Workspace인지 API 조회
- persisted run의 workspace 일치

---

## 4. P2 시각 디자인 트랙 시작 결과

기능 문서와 분리된 visual language 문서를 추가했다.

```text
docs/ui/palantir-visual-language.md
```

### CSS token 추가

`web/src/styles.css`에 다음 semantic token을 추가했다.

```text
surface/canvas/border/text/accent/success/warning/danger
panel and control radius
panel shadow
compact row density
light/dark counterparts
```

### 첫 적용 화면

Agent Evidence Workbench는 다음 원칙을 실제 적용한다.

- 12px 수준의 compact outer padding
- 300px query rail
- flexible evidence center
- 310px lineage inspector
- 40~44px pane headers
- 4~6px radius
- 낮은 elevation
- gray surface hierarchy
- semantic color를 selection/status에만 사용
- metadata 7~9px compact hierarchy
- panel 간 넓은 whitespace 대신 border 구분

이 slice는 전역 CSS를 한 번에 위험하게 재작성하지 않고, 신규 workbench부터 token을 검증한 뒤 Ontology/Dataset/Governance로 확장하는 방식이다.

---

## 5. 현재 프론트엔드 구조·동작·시각 상태

| 항목 | 구조 | 실제 동작 | 현재 상태 |
|---|---:|---:|---|
| 12열 Dashboard grid | ✅ | ✅ | 유지 |
| ECharts renderer | ✅ | ✅ | 유지 |
| TanStack Table/virtualization | ✅ | ✅ | 유지 |
| server Analysis run | ✅ | ✅ | 유지 |
| server Join whitelist | ✅ | ✅ | save-time rejection까지 보강 |
| Analysis DAG cycle validation | ✅ | ✅ | save-time rejection까지 보강 |
| server Result profile | ✅ | ✅ | duplicate/null summary까지 보강 |
| Ontology Workbench | ✅ | ✅ | route restore/isolation/screenshot E2E |
| Governance Workbench | ✅ | ✅ | trace/evidence/lineage/projection retry |
| Agent Evidence Workbench | ✅ | ✅ | dedicated route와 reload/audit flow |
| Project 2 local pgvector RAG | projection schema only | 의도적 비사용 | runtime semantic retrieval은 `project3_rag` typed HTTP로 확정 |
| visual token system | ✅ | ✅ | Agent/Ontology/Governance/Dataset/Project Home 공유 token 적용 |
| Dataset materialization | ✅ | ✅ | Analysis result → immutable Dataset Version → reusable Analysis input |
| Analysis lifecycle | ✅ | ✅ | queued/running/progress/cancel/cache/cursor |
| canonical WorkOrder | ✅ | ✅ | `work_order` primary, `inspection` deprecated alias |

---

## 6. 테스트 근거

### Backend

```text
tests/test_analysis_path.py
- whitelist rejection
- cycle rejection
- server quality summary

tests/test_polyglot_infra_stage46.py
- capability boundary assertion

tests/test_multistore_orchestrator_stage49.py
- routing, evidence grounding, degraded mode, isolation
```

### Full release and live integration evidence

```text
Backend full suite: 118 PASS
Frontend Vitest: 3 PASS
Playwright full suite: 28 PASS
Ephemeral PostgreSQL migration/RLS/runtime: PASS
SQLite backup/restore + tamper detection: PASS

scripts/verify_live_project3_hybrid.py
- Project 3 status: ready
- PostgreSQL evidence: 1
- Neo4j evidence: 3
- Project 3 RAG evidence: 1
- grounded claims: 5
- checkpoint sequence: 4
```

`release_gate.py`는 `--with-live-project3` 옵션을 지원해 이미 실행 중인 Project 2/3 서비스에 같은 public HTTP gate를 적용한다. 외부 API/Vite 프로세스 stdout은 `DEVNULL`로 처리해 pipe saturation을 방지한다.

### Frontend build and initial bundle budget

`ManufacturingApp`, `AdminApp`, `AnalysisWorkbench`, `DashboardBoardRenderer`를 route/runtime lazy boundary로 분리했다. `web/scripts/check-initial-bundle.mjs`는 `dist/index.html`이 즉시 로드하는 JavaScript만 합산해 기본 300 KiB budget을 초과하면 build를 실패시킨다.

```text
npm run build
- initial JavaScript: 213.87 KiB / 300 KiB PASS
- entry before split: 1,361.50 KiB
- DataTableRenderer: 6.42 KiB
- DashboardBoardRenderer: 10.25 KiB
- ECharts Cartesian runtime: 168.53 KiB
- ECharts Pie runtime: 34.05 KiB
- largest deferred common runtime: 443.24 KiB
```

TanStack/virtualizer 의존을 제거한 lightweight virtual table과 Pie/Cartesian ECharts runtime split으로 모든 deferred JavaScript chunk가 500 KiB 아래에 있다.

### Frontend / E2E

```text
npm test -- --run
- Vitest 3 PASS

PLAYWRIGHT_API_PORT=8800 PLAYWRIGHT_WEB_PORT=3800 npx playwright test
- Playwright 28 PASS
- Project switch/resource isolation
- Project Home and active role context
- Dataset Catalog and Analysis materialization
- queued Analysis lifecycle
- Dashboard/Analysis lazy loading regression
- Agent direct route and persisted run reload
- claim → evidence navigation
- unauthorized project/workspace rejection
- Ontology/Governance visual artifacts and regression flows
```

---

## 7. 후속 운영 과제

이 문서에서 정의한 Palantir UI gap 구현 항목은 완료됐다. 다음 항목은 기능 미구현이 아니라 배포 환경·장기 운영 과제다.

1. Docker CLI가 있는 host에서 PostgreSQL+pgvector+Redis+Neo4j compose cold-start/rollback drill을 반복한다.
2. managed PostgreSQL과 Redis에서 pool, rate limiter, outbox worker 장기 부하를 측정한다.
3. production REST/Kafka/MQTT/OPC-UA connector credential·retry·backpressure 정책을 도메인별로 구성한다.
4. Dashboard editor undo/redo와 unsaved draft recovery를 제품 편집성 개선 트랙으로 진행한다.
5. Project Home/Dataset Workbench screenshot baseline을 정기 visual regression 대상으로 추가한다.

### 이번 최종 검증

```text
Backend: 118 PASS
Frontend Vitest: 3 PASS
TypeScript/build: PASS
Initial JS: 213.87 KiB / 300 KiB
All deferred JS chunks: < 500 KiB
Playwright: 28 PASS
Live Project 2 → Project 3 three-store gate: PASS
```

---

## 8. 요약 문서 규칙

향후 Stage/Sprint 완료 문서는 기능 목록보다 먼저 다음을 포함한다.

1. 실제 route
2. 사용자 역할과 permission
3. Playwright flow 이름
4. screenshot artifact 이름
5. degraded/error 상태
6. 남은 live integration gap

이 규칙을 적용하면 “백엔드 구조는 늘었지만 화면은 없는 상태”를 완료 문서 단계에서 바로 발견할 수 있다.
