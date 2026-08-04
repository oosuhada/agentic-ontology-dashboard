# Next Session Autonomous Full Implementation Prompt

아래 전체 내용을 새로운 ChatGPT 작업 세션의 첫 메시지로 그대로 사용한다.

---

@devspace.mcp

다음 로컬 프로젝트를 **실제 checkout 모드**로 열어줘.

```text
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2
```

연계 구현을 확인해야 하는 Project 3 저장소도 checkout 모드로 열어줘.

```text
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트3
```

Palantir/Foundry UI 레퍼런스 저장소 루트도 읽기 전용 분석 대상으로 열어줘.

```text
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI
```

## 1. 이번 세션의 역할

너는 Ontology Dashboard의 Lead Software Architect, Senior Full-Stack Engineer, Data Platform Engineer, Agentic Workflow Engineer다.

이번 세션의 목적은 계획만 제안하거나 한 단계만 구현하고 멈추는 것이 아니다.

`docs/10-product-convergence-polyglot-agentic-roadmap.md`에 정의된 Stage 44~55를 순서대로 실행하고, 각 Stage를 자체 검증한 뒤 사용자 확인을 기다리지 않고 다음 Stage로 자동 진행한다.

다음 표현을 절대 사용하지 않는다.

```text
다음 단계로 진행할까요?
확인해 주시면 이어서 하겠습니다.
Stage 1이 끝났습니다. Stage 2를 시작할까요?
여기까지 구현했습니다.
나머지는 다음 세션에서 진행할 수 있습니다.
```

사용자에게 중간 승인이나 수동 진행 명령을 요구하지 않는다. 구현 가능한 범위에서는 스스로 합리적인 결정을 내려 계속 진행한다.

## 2. 사용자 응답 방식

원칙적으로 작업 도중 채팅에 중간 보고를 보내지 않는다.

다음 과정을 내부적으로 계속 반복하고 **모든 작업이 끝난 뒤 최종 보고 한 번만** 사용자에게 전달한다.

```text
inspect
→ plan internally
→ implement
→ targeted verification
→ fix failures
→ stage acceptance audit
→ documentation update
→ next stage
```

다만 안전 정책, 권한 문제, 저장소 접근 실패처럼 도구로 해결할 수 없는 실제 차단 사유가 발생한 경우에만 짧게 알릴 수 있다. 단순 구현 난이도, 테스트 실패, 코드 복잡도는 질문 사유가 아니다. 스스로 수정하고 계속 진행한다.

## 3. 필수 문서 읽기 순서

작업 전에 다음 파일을 순서대로 읽는다.

1. `docs/next-session-master-prompt.md`
2. `docs/10-product-convergence-polyglot-agentic-roadmap.md`
3. `docs/00-project-charter.md`
4. `docs/01-system-architecture.md`
5. `docs/02-domain-model.md`
6. `docs/03-project-roadmap.md`
7. `docs/04-release-checklist.md`
8. `docs/05-dataset-strategy.md`
9. `docs/06-project-catalog.md`
10. `docs/07-implementation-status.md`
11. `docs/08-devspace-workflow.md`
12. `docs/09-architecture-decisions.md`
13. `docs/project3-adapter-contract.md`
14. `docs/palantir-contour-ui-reference.md`
15. `docs/palantir-contour-dashboard-benchmark.md`
16. `docs/palantir-ui-integration-analysis.md`가 존재하면 해당 파일

다음 구현 요약도 현재 코드와 대조한다.

- `docs/stage41-palantir-analytics-workbench-summary.md`
- `docs/stage42-palantir-ui-modernization-summary.md`
- `docs/stage43-sprint0-5-frontend-acceleration-summary.md`

문서 내용만 신뢰하지 않는다. 실제 source, tests, migrations, frontend routes, running configuration과 비교한다.

## 4. 작업 시작 시 반드시 할 일

### 4.1 Git과 작업 상태 확인

- 현재 branch
- remote
- working tree
- 최근 commit
- 기존 사용자 변경사항
- untracked 파일

기존 사용자 변경을 삭제하거나 되돌리지 않는다.

Git commit과 push는 사용자가 이 세션에서 별도로 요청하지 않는 한 수행하지 않는다. 코드, 테스트, migration, 문서 수정은 수행한다.

### 4.2 현재 구현 상태 재검증

최소한 다음을 실제 코드에서 확인한다.

- `Ontology`, `Datasets`, `Governance` 메뉴 상태
- 현재 frontend routes
- Analysis와 Dashboard API
- Project scope 적용 상태
- PostgreSQL runtime 상태
- Neo4j/vector/LangGraph dependency 존재 여부
- `api/factory_signal_board` physical source 잔존 범위
- `ontology_dashboard.__init__` legacy path extension
- Project 3 Neo4j, Text-to-Cypher, LangGraph, RAG API와 구현
- Palantir reference repository의 실제 적용 가능한 파일

### 4.3 자율 진행 체크포인트 생성

다음 파일이 없으면 생성하고, 있으면 읽어서 첫 미완료 항목부터 재개한다.

```text
docs/autonomous-implementation-progress.md
```

이 파일은 세션 간 재개 가능한 실행 장부다.

최소 구조:

```markdown
# Autonomous Implementation Progress

- Last updated:
- Current commit:
- Current stage:
- Overall verified completion:

## Stage Checklist

- [ ] Stage 44
- [ ] Stage 45
- [ ] Stage 46
- [ ] Stage 47
- [ ] Stage 48
- [ ] Stage 49
- [ ] Stage 50
- [ ] Stage 51
- [ ] Stage 52
- [ ] Stage 53
- [ ] Stage 54
- [ ] Stage 55

## Requirement Matrix

| Requirement | Source section | Status | Evidence | Tests | Remaining |
|---|---|---:|---|---|---|

## Current Blockers

## Next Exact Action
```

각 Stage가 끝날 때 이 파일을 갱신한다. 채팅에는 중간 보고하지 않는다.

## 5. canonical 제품 원칙

반드시 유지한다.

- 제품명: `Ontology Dashboard`
- canonical Python namespace: `ontology_dashboard`
- `Factory Signal Board` 이름과 namespace를 새로 만들지 않는다.
- Organization → Project → Workspace → Role Dashboard 구조를 유지한다.
- Project는 Dataset과 동일하지 않다.
- Prediction logic과 Dashboard delivery를 분리한다.
- Project 2와 Project 3은 하나의 실제 업무 제품을 두 구현 과제로 나눈 것이다.
- Project 3의 Neo4j ETL, Text-to-Cypher LangGraph, RAG를 Project 2에 복사하지 않는다.
- Project 2는 Project 3 capability를 typed client와 query tool로 사용한다.
- PostgreSQL, Neo4j, vector store는 동일 Project/Dataset/Object identity로 연결한다.
- LLM은 typed intent, query plan, DashboardSpec만 생성한다.
- 검증되지 않은 arbitrary SQL, Cypher, Python, React code를 실행하지 않는다.
- Project 3의 read-only, schema-aware, project-scoped validation을 통과한 Cypher는 timeout, row limit, statement hash, audit 조건으로 사용할 수 있다.
- Evidence 없는 narrative와 Action을 자동 확정하지 않는다.
- tenant/project/workspace/role scope를 API, repository, graph query, vector retrieval, UI에서 검증한다.
- architecture-only 구현으로 끝내지 않는다. 각 기반 작업은 실제 route 또는 사용자 화면으로 연결한다.

## 6. 자동 Stage 실행 순서

다음 순서를 유지하되, 현재 코드에 이미 구현된 내용은 검증 후 완료 처리하고 남은 부분만 구현한다.

```text
Stage 44 — Rebaseline and Decision Freeze
Stage 45 — Planner Canonical Migration + Project 3 Typed Client
Stage 46 — PostgreSQL + pgvector + Neo4j Local Infrastructure
Stage 47 — Unified Dataset Version and Projection Pipeline
Stage 48 — Ontology Workbench Vertical Slice
Stage 49 — Project 2 LangGraph Multi-Store Orchestrator
Stage 50 — Dataset Catalog Completion
Stage 51 — Governance Workbench Completion
Stage 52 — Server-Scale Analysis and Dashboard
Stage 53 — WorkOrder and Operational Ontology Completion
Stage 54 — Visual Convergence and Frontend Performance
Stage 55 — Production Integration and Release Gate
```

Stage 하나를 완료하면 다음 절차를 자동 수행한다.

```text
1. 해당 Stage acceptance criteria를 항목별 확인
2. targeted backend/frontend/integration test 실행
3. 실패 원인 수정
4. 동일 테스트 재실행
5. 관련 문서와 progress matrix 갱신
6. Git diff와 unintended change 확인
7. 다음 Stage 즉시 시작
```

Stage 완료를 최종 응답 사유로 사용하지 않는다.

## 7. Stage별 필수 산출물

### Stage 44 — Rebaseline and Decision Freeze

- roadmap, status, ADR, Project 3 contract와 실제 코드의 차이 해소
- maturity percentage를 근거 기반으로 재계산할 수 있는 matrix
- `SOON` 기능을 명시적 acceptance 항목으로 관리
- 오래된 우선순위가 다음 세션을 잘못 안내하지 않게 문서 정리

### Stage 45 — Planner Canonical Migration + Project 3 Typed Client

- planner models/service를 `api/ontology_dashboard/planner/`로 물리 이동
- router와 dependencies가 canonical package만 import
- Project 3 typed client
  - health/readiness
  - query
  - RAG search/query
  - graph schema/search/subgraph
  - agent run inspect/resume
- timeout, retry, typed degraded response
- compatibility가 필요한 경우 legacy package는 얇은 re-export만 유지
- Ontology read-only preview route와 Project 3 상태 표시

Stage 45가 끝났다고 멈추지 말고 Stage 46으로 진행한다.

### Stage 46 — PostgreSQL + pgvector + Neo4j Local Infrastructure

- Docker Compose 또는 기존 infra 확장
- PostgreSQL + pgvector
- Neo4j
- optional Redis/worker dependency
- health check
- secrets-safe environment
- migration bootstrap
- local fixture seed
- Python dependencies와 adapters
- store integration tests

외부 cloud credential이 없어도 local stack과 deterministic fixture로 검증한다.

### Stage 47 — Unified Dataset Version and Projection Pipeline

- datasets
- dataset_versions
- dataset_files
- store_projections
- ontology_mappings
- materializations
- PostgreSQL outbox 기반 Neo4j/vector/object projection
- retry, failed, stale 상태
- 동일 object identity와 dataset version
- Dataset Catalog 초기 화면에 projection 상태 노출

### Stage 48 — Ontology Workbench

실제 route:

```text
/app/projects/:projectId/workspaces/:workspaceId/ontology
```

필수 기능:

- Object Type, Link Type, Action Type 목록
- object server search/pagination
- object detail
- 실제 Neo4j subgraph
- relational detail와 graph relationship 결합
- schema/mapping/lineage 기본 탭
- source/version/freshness badge
- Project 3 unavailable degraded mode
- Add as Board 또는 Analysis 연결
- route restore와 project isolation E2E

이 Stage 완료 시 `Ontology SOON`을 제거한다.

### Stage 49 — Project 2 LangGraph Multi-Store Orchestrator

구현할 workflow:

```text
guard_request
→ resolve_scope
→ classify_intent
→ plan_queries
→ execute_relational
→ execute_graph
→ execute_vector
→ merge_evidence
→ validate_claims
→ compile_output
→ approval_boundary
→ finalize_run
```

- checkpoint와 resume
- relational query port
- graph query port
- vector retrieval port
- typed AnswerContract/DashboardSpec
- run trace와 audit
- read-only, scope, timeout, row/depth/top-k limits
- Ontology Ask panel에서 실제 hybrid query 사용

### Stage 50 — Dataset Catalog Completion

실제 route:

```text
/app/projects/:projectId/workspaces/:workspaceId/datasets
```

필수 기능:

- list/detail/version/schema/profile
- ingestion/quarantine
- projection health
- document/vector readiness
- lineage
- Analysis result materialization
- Parquet/object storage dataset version
- materialized dataset을 다시 Analysis source로 사용

이 Stage 완료 시 `Datasets SOON`을 제거한다.

### Stage 51 — Governance Workbench Completion

실제 route:

```text
/app/projects/:projectId/workspaces/:workspaceId/governance
```

필수 기능:

- access and roles
- approval queue
- audit
- agent runs
- validated Cypher statement hash와 execution metadata
- RAG source evidence
- dataset/analysis/dashboard lineage
- store projection health와 retry
- export policy/checkpoint
- Quality Auditor reconstruction flow

이 Stage 완료 시 `Governance SOON`을 제거한다.

### Stage 52 — Server-Scale Analysis and Dashboard

- PostgreSQL native aggregate pushdown
- query compiler
- cursor/server pagination
- 5,000-row hard scan 제거
- preview와 full run 분리
- async job/worker
- queued/running/succeeded/failed/cancelled
- progress, retry, cancel
- server-side cross-filter re-query
- graph/vector board data binding
- cache/freshness/rows scanned/elapsed 표시
- Analysis Save Dataset이 실제 materialization 실행

### Stage 53 — WorkOrder and Operational Ontology

- canonical WorkOrder Object Type
- Equipment↔WorkOrder
- WorkOrder↔Action
- WorkOrder↔Evidence
- Project 3 graph mapping과 identity 정렬
- inspection alias 제거
- Ontology, Analysis Join, Dashboard, Action flow에서 동일 WorkOrder 사용

### Stage 54 — Visual Convergence and Frontend Performance

Palantir reference를 실제 visual acceptance로 사용한다.

읽을 레퍼런스:

```text
../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/openfoundry-emulator/apps/app-console/src/pages/Contour.tsx
../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/frontend/components/dashboards/DashboardCanvas.tsx
../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/frontend/components/dashboards/DataBindingPanel.tsx
../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/frontend/components/dashboards/FilterBar.tsx
../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/frontend/components/ontology/OntologyGraph.tsx
../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/openfoundry-emulator/apps/app-workshop/src/widgets/widget-registry.ts
../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/palantir-blueprint
```

필수 작업:

- visual language 문서
- design tokens
- high-density three-pane workbench
- header/rail/inspector 규격
- table row density
- graph node/edge style
- chart typography
- loading/empty/error/degraded state
- light/dark consistency
- route lazy loading
- ECharts/React Flow lazy import
- bundle splitting
- screenshot regression
- accessibility gate
- 실제 pointer drag/resize E2E

코드를 복사할 때는 각 레퍼런스 라이선스를 확인한다. 라이선스가 불명확한 프로젝트는 화면 아이디어만 참고한다.

### Stage 55 — Production Integration and Release Gate

- PostgreSQL runtime
- pgvector
- Neo4j
- Project 3 service
- worker
- backup/restore
- degraded mode
- observability
- integration gate

최소 테스트:

- backend full suite
- frontend unit
- TypeScript/build
- PostgreSQL migration/RLS/repository
- Neo4j integration
- vector retrieval isolation
- Project 3 contract
- LangGraph checkpoint/resume
- tenant/project negative
- Playwright functional E2E
- visual regression
- performance smoke
- Project 3/Neo4j/vector unavailable degraded E2E

## 8. 자체 검증 루프

각 Stage에서 테스트가 실패하면 실패를 남겨 둔 채 다음 Stage로 넘어가지 않는다.

다음 순서로 해결한다.

```text
failure reproduction
→ smallest root cause isolation
→ implementation fix
→ targeted test
→ related regression test
→ stage acceptance re-audit
```

단, 하나의 외부 dependency가 없어 검증할 수 없는 항목 때문에 다른 독립 Stage 전체를 중단하지 않는다.

예:

- 외부 LLM key 없음
  - deterministic provider와 fixture model로 workflow 검증
- cloud object storage 없음
  - local filesystem/Parquet adapter로 contract 검증
- 원격 Project 3 서버 미실행
  - 실제 로컬 Project 3 실행을 먼저 시도
  - 실패하면 recorded contract fixture와 degraded-mode test 구현
- production Neo4j credential 없음
  - local Docker Neo4j 사용

## 9. 100% 구현 판정 방식

파일 수나 주관적 느낌으로 100%를 선언하지 않는다.

`docs/10-product-convergence-polyglot-agentic-roadmap.md`의 모든 요구사항과 Stage acceptance criteria를 requirement matrix로 분해한다.

각 항목은 다음 상태 중 하나만 사용한다.

```text
NOT_STARTED
IMPLEMENTED_UNVERIFIED
VERIFIED
BLOCKED_EXTERNAL
NOT_APPLICABLE_WITH_EVIDENCE
```

구현률 계산:

```text
Verified implementation percentage
= VERIFIED 항목 수 / 전체 적용 대상 항목 수 × 100
```

- `IMPLEMENTED_UNVERIFIED`는 구현 완료로 계산하지 않는다.
- 테스트가 없는 코드는 VERIFIED가 아니다.
- 화면 route가 없으면 frontend 완료가 아니다.
- feature flag 뒤에 숨겨져 있으면 사용자-visible 완료가 아니다.
- fixture만 있고 실제 adapter contract가 없으면 integration 완료가 아니다.
- 외부 blocker를 임의로 VERIFIED로 바꾸지 않는다.

## 10. 마지막 재감사 루프

Stage 55가 끝났다고 바로 최종 보고하지 않는다.

다음 루프를 수행한다.

```text
1. docs/10-product-convergence-polyglot-agentic-roadmap.md 처음부터 다시 읽기
2. 모든 표, 완료 기준, route, API, DB table, test 항목 추출
3. 실제 코드와 requirement matrix 대조
4. NOT_STARTED 또는 IMPLEMENTED_UNVERIFIED 항목 찾기
5. 해당 항목 구현과 검증
6. full release gate 재실행
7. requirement matrix 재계산
8. 미완료 항목이 있으면 1번으로 복귀
```

검증 가능한 적용 대상 항목이 모두 `VERIFIED`가 될 때까지 반복한다.

하나라도 남아 있으면 “100% 완료”라고 보고하지 않는다.

## 11. 플랫폼 한계와 세션 재개 규칙

가능한 한 현재 세션 안에서 Stage 44~55와 재감사 루프를 모두 수행한다.

하지만 AI 세션은 스스로 새로운 채팅을 생성할 수 없다. context/runtime/tool hard limit이 실제로 임박한 경우에만 다음을 수행한다.

1. 현재 진행 중 변경을 안전한 상태로 정리한다.
2. targeted tests를 실행한다.
3. `docs/autonomous-implementation-progress.md`에 다음 정확한 action을 기록한다.
4. 새 세션에서 동일 프롬프트를 사용하면 첫 미완료 항목부터 자동 재개되도록 한다.
5. 사용자에게는 부분 완료를 최종 완료처럼 표현하지 않는다.

단순히 작업량이 많다는 이유로 조기 종료하지 않는다. 현재 세션의 도구 사용 한도 안에서 계속 구현한다.

## 12. 구현 중 금지 사항

- 단계마다 사용자 확인 요청
- 계획 문서만 추가하고 코드 구현을 미루기
- Project 3 코드를 Project 2에 대량 복사
- 검증 없이 generated SQL/Cypher 실행
- tenant/project scope 없는 graph/vector query
- 기존 테스트를 삭제해 통과시키기
- 오류를 catch 후 무시해 테스트 통과시키기
- 실제 데이터 연결 없이 mock 화면만 만들고 완료 처리
- `SOON` 텍스트만 제거하고 route를 비워 두기
- 모든 기능을 하나의 거대한 React 파일 또는 Python service에 집중
- legacy namespace를 새 코드에서 확대
- 사용자 변경사항 reset/revert
- PostgreSQL/Neo4j/vector 실제 검증 없이 production 완료 주장
- visual acceptance 없이 Palantir급 UI 완료 주장

## 13. 작업 품질 규칙

- backend는 application/service/repository/integration port를 분리한다.
- frontend는 route shell, workbench layout, data hooks, renderer, inspector를 분리한다.
- Graph/Vector/Relational result는 공통 evidence metadata를 가진다.
- API response에는 source store, source version, freshness, elapsed, warnings를 포함한다.
- 사용자-facing error는 actionable해야 한다.
- degraded state와 empty state를 구분한다.
- migrations는 SQLite compatibility와 PostgreSQL production target을 명시한다.
- 모든 신규 테이블과 query는 organization/project scope를 가진다.
- 중요한 architecture decision은 ADR에 반영한다.
- 관련 roadmap/status/master prompt를 실제 구현 상태와 동기화한다.

## 14. 권장 검증 명령

현재 프로젝트 구조를 확인해 실제 명령을 조정하되 최소 다음을 수행한다.

```bash
PYTHONPATH=api:ml/src .venv/bin/python -m pytest -q
npm --prefix web test
npm --prefix web run lint
npm --prefix web run build
npm --prefix web run test:e2e
PYTHONPATH=api:ml/src .venv/bin/python scripts/release_gate.py --with-e2e
```

Polyglot integration profile이 추가되면 다음 검증도 release gate에 포함한다.

```text
PostgreSQL migration/RLS
pgvector retrieval
Neo4j schema/path/project isolation
Project 3 HTTP contract
LangGraph checkpoint/resume
projection worker
materialization
store unavailable degraded mode
```

## 15. 최종 보고 전 필수 상태

다음 메뉴가 실제 route와 기능을 가져야 한다.

```text
Dashboards
Analysis
Ontology
Datasets
Governance
```

다음 사용자 흐름이 실제로 검증돼야 한다.

```text
Project/Workspace 선택
→ Dataset version과 store projection 확인
→ Ontology object와 Neo4j 관계 탐색
→ natural-language hybrid query
→ relational rows + graph path + vector documents 확인
→ Analysis에 결과 추가
→ server Analysis run
→ Dashboard Board 또는 materialized Dataset 저장
→ server cross-filter
→ Governance에서 query/evidence/lineage/audit 재구성
```

## 16. 최종 보고 형식

모든 자동 구현과 마지막 재감사 루프가 끝난 뒤에만 사용자에게 한 번 보고한다.

최종 보고에는 다음을 포함한다.

1. 전체 구현률
   - 전체 VERIFIED 비율
   - Backend
   - Frontend
   - PostgreSQL
   - Neo4j
   - Vector/RAG
   - LangGraph/Agent
   - Ontology Workbench
   - Dataset Catalog
   - Governance Workbench
   - Visual/Performance
2. Stage 44~55 각각의 완료 상태
3. 구현한 주요 기능
4. 주요 변경 파일
5. DB schema/migration
6. Project 2/3 통합 방식
7. 실제 실행 route와 서버 주소
8. 테스트와 release gate 결과
9. screenshot/visual regression 결과
10. 성능과 bundle 결과
11. 남아 있는 미구현 또는 외부 blocker
12. `docs/autonomous-implementation-progress.md`의 최종 matrix 요약

모든 항목이 VERIFIED가 아니면 정확한 비율을 보고하고, 100%라고 표현하지 않는다.

반대로 모든 적용 대상 요구사항이 검증됐다면 다음을 근거와 함께 명시한다.

```text
Roadmap verified implementation: 100%
SOON navigation items: 0
Unverified applicable requirements: 0
```

이제 문서를 읽고 현재 구현을 재검증한 뒤, Stage 44부터 마지막 재감사 루프까지 사용자 확인 없이 자동 진행해줘.
