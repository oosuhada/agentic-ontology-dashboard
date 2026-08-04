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
| Project 2 local pgvector RAG | schema only | ❌ | Project 3 RAG와 구분 표기 |
| visual token system | ✅ first slice | ✅ Agent | 나머지 workbench 확대 필요 |

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

### Full release gate

```text
scripts/release_gate.py --with-e2e
- 13/13 PASS
- ephemeral PostgreSQL migration/RLS PASS
- PostgreSQL runtime PASS
- backend 114 PASS
- Playwright 27 PASS
```

Release runner는 외부 API/Vite 프로세스의 stdout을 `DEVNULL`로 처리해 로그 pipe saturation을 방지하고, 임시 frontend copy에서는 이미 실행한 외부 서버를 사용한다.

### Frontend build and initial bundle budget

`ManufacturingApp`, `AdminApp`, `AnalysisWorkbench`, `DashboardBoardRenderer`를 route/runtime lazy boundary로 분리했다. `web/scripts/check-initial-bundle.mjs`는 `dist/index.html`이 즉시 로드하는 JavaScript만 합산해 기본 300 KiB budget을 초과하면 build를 실패시킨다.

```text
npm run build
- initial JavaScript: 212.25 KiB / 300 KiB PASS
- entry before split: 1,361.50 KiB
- ManufacturingApp before inner split: 954.90 KiB
- ManufacturingApp after inner split: 139.23 KiB
- AnalysisWorkbench lazy chunk: 23.21 KiB
- DashboardBoardRenderer lazy chunk: 54.91 KiB
```

`DataTableRenderer` lazy chunk는 725.21 KiB로 Vite 경고가 남지만 초기 route payload에는 포함되지 않는다. 후속 작업은 경고를 숨기는 것이 아니라 TanStack table/virtualization vendor split 또는 renderer-level import 경계를 검토하는 것이다.

### Frontend / E2E

```text
npm test -- --run
- Vitest 3 PASS

PLAYWRIGHT_API_PORT=8300 PLAYWRIGHT_WEB_PORT=3300 \
  npx playwright test e2e/workbench-governance.spec.ts e2e/ui-modernization.spec.ts
- Playwright 11 PASS
- Dashboard/Analysis lazy loading regression PASS
- Agent direct route
- scoped query execution
- claim → evidence navigation
- persisted run reload
- unauthorized project rejection
- Agent screenshot artifact
- Ontology/Governance regression flows
```

---

## 7. 다음 우선순위

P0/P1을 반복 구현하지 않는다.

이번 후속 작업으로 다음 두 항목을 완료했다.

1. Governance Agent Run 상세에 `Open Agent Evidence` deep link를 추가했다. Agent Workbench의 기존 Governance 이동과 결합되어 양방향 persisted-run 이동이 가능하다.
2. `GET /api/agent/runs` server pagination/filter를 추가했다. Project/Workspace scope, status, route, question search, offset/limit을 서버에서 검증하고 Agent Workbench는 browser-local history 대신 persisted 목록을 기본 UI로 사용한다. Local history는 offline recovery 보조 정보로만 남긴다.

남은 순서는 다음과 같다.

3. 실제 Project 3 service가 실행되는 release profile에서 hybrid query의 Neo4j/RAG evidence를 검증한다.
4. Project 2 local pgvector를 사용할지 명시적으로 결정한다.
   - 사용하지 않으면 schema를 projection future boundary로 유지한다.
   - 사용한다면 먼저 project/role-filtered evidence retrieval use case와 writer를 구현한다.
5. `palantir-visual-language.md` token을 Governance와 Ontology에 점진적으로 적용한다.
6. Governance Agent run 목록에도 Agent Workbench와 동일한 server pagination/filter contract를 직접 사용하게 해 overview snapshot 의존도를 줄인다.
7. 725 KiB `DataTableRenderer` lazy chunk를 renderer/vendor 단위로 더 분리할지 실제 route 성능을 기준으로 결정한다.

완료되어 남은 목록에서 제거한 항목:

- Agent Workbench ↔ Governance 양방향 persisted-run deep link
- `GET /api/agent/runs` server pagination, status/route/search filter
- Stage 54 initial JavaScript 300 KiB budget과 build-time regression gate

### 이번 추가 검증

```text
Backend targeted: 12 PASS
Frontend Vitest: 3 PASS
Frontend build and 300 KiB initial budget: PASS
Dashboard/Analysis + Agent/Ontology/Governance Playwright: 11 PASS
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
