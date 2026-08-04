# Ontology Dashboard Implementation Status

- Last updated: 2026-08-02
- Baseline: backend 118 PASS, frontend unit 3 PASS, Playwright 28 PASS, live three-store Agent gate PASS
- Current execution plan: `docs/10-product-convergence-polyglot-agentic-roadmap.md`

## Current Maturity

```text
Backend        97%
Frontend       96%
Architecture   96%
PostgreSQL     85%
Project Layer  90%
Adapter Layer  80%
```

이 비율은 단순 파일 개수가 아니라 목표 아키텍처 대비 구현·검증·운영 준비도를 반영한 추정치다. 모든 외부 streaming connector와 실제 다중 인스턴스 운영을 완료했다는 의미는 아니다. Project Home, Analysis lifecycle, Agent/Ontology/Dataset/Governance Workbench와 live Project 3 three-store 경로는 실제 route·persistence·E2E 또는 live HTTP gate까지 연결됐다.

## User-Visible Product Surface

```text
Dashboards   CONNECTED
Analysis     CONNECTED
Agent        CONNECTED EVIDENCE WORKBENCH
Ontology     CONNECTED WORKBENCH / DEGRADED GRAPH SAFE
Datasets     CONNECTED CATALOG / IMMUTABLE MATERIALIZATION / REUSABLE INPUT
Governance   CONNECTED PROJECT WORKBENCH
```

- Agent Evidence Workbench는 scoped query, persisted run restore, claim→evidence navigation, store/version/object trace와 orchestration lineage를 제공한다.
- Ontology Workbench는 exact project/workspace route, object search, graph/inspector, Add Graph Board, multi-store Ask, route restore와 isolation E2E를 제공한다.
- Dataset Catalog는 server pagination/filter, immutable versions, schema/profile, files, projection readiness, mappings, ingestion/quarantine, lineage와 Analysis result materialization→reusable Dataset input을 제공한다.
- Governance Workbench는 project-scoped access, approvals, server-paginated Agent runs, claims/evidence/traces/checkpoints, lineage, projection health와 permission-gated retry를 통합한다.
- Project Home은 Project KPI, Workspace entry points, active role context와 Project 3 readiness를 제공한다.

## Backend — 93%

### Implemented

- FastAPI application factory
- security middleware와 production fail-fast
- feature router 분리 기반
- cookie authentication
- Argon2id password hashing
- session rotation·revocation
- CSRF
- RBAC
- organization tenant isolation의 주요 경계
- canonical Project model/repository/service/API
- Project scope를 포함한 principal과 Project별 Workspace 조회
- Ontology registry
- object/link/action API
- persistent SQLite Ontology object/link store
- dashboard template/preferences/saved views/share
- role workspaces
- approval workflows
- planner safety boundary
- export and audit
- transactional outbox foundation
- migration runner
- typed multi-store orchestrator와 persisted run/checkpoint/trace
- Analysis create/update 시 Join whitelist와 DAG cycle validation
- server-computed Analysis quality summary
- polyglot health capability boundary

### Remaining

- legacy `factory_signal_board` physical package의 canonical namespace 이동
- Identity/Dashboard/Workflow/Export 전체 PostgreSQL repository 전환
- production IdP 기반 SSO와 invitation/reset lifecycle
- 다중 인스턴스 Redis/worker 운영 부하 검증

## Frontend — 89%

### Implemented

- login and registration
- role-aware landing
- governed dashboard runtime
- dashboard editor
- saved view and share
- role-specific executive/audit/field/FDE/ML views
- planner preview
- export flow
- workspace/event/detail hooks
- dashboard editor command hook
- mobile field E2E
- Project selector와 `/app/projects/:projectId` route foundation
- Project별 Workspace loading
- `/app/projects/:projectId/workspaces/:workspaceId/agent` Evidence Workbench
- `/app/projects/:projectId/workspaces/:workspaceId/ontology` Workbench
- `/app/projects/:projectId/workspaces/:workspaceId/governance` Workbench
- Agent/Ontology/Governance route restore, project/workspace isolation, screenshot artifact E2E
- Agent claim→evidence drill-down과 persisted run reload
- Governance agent trace·evidence·lineage·projection retry
- Agent persisted run server pagination/status/route/search filter와 Governance 양방향 deep link
- Admin/Manufacturing/Analysis/Board renderer route-level lazy boundary
- build-time 300 KiB initial JavaScript budget gate (`213.87 KiB` verified)
- Project Home과 Project별 active role selector
- Dataset Catalog server pagination/filter와 Analysis materialization flow
- Governance server Agent run filter/pagination
- shared visual token/density system and `docs/ui/palantir-visual-language.md`
- ECharts Pie/Cartesian runtime split과 lightweight virtual DataTable

### Remaining

- Dashboard editor undo/redo와 unsaved draft recovery
- Project Home·Dataset screenshot baseline의 장기 visual regression 관리
- 접근성 자동 검사를 Workbench 전체 route로 확대

## Architecture — 95%

### Implemented

- canonical product naming
- application factory
- router boundaries
- dependency composition
- service/repository separation
- organization/project/workspace target hierarchy documented
- Ontology Core and domain-pack strategy
- Prediction/Dashboard separation
- migration and outbox strategy
- PostgreSQL RLS strategy
- multi-project dataset strategy

### Remaining

- physical canonical source relocation
- feature modules가 legacy handler container를 전혀 참조하지 않는 상태
- Docker/Kubernetes 기반 다중 인스턴스 deployment drill

## PostgreSQL — 70%

### Implemented

- PostgreSQL DDL
- schema migration runner
- real ephemeral PostgreSQL migration test
- RLS policy creation
- non-superuser tenant RLS verification
- JSONB and indexes
- Ontology PostgreSQL repository foundation
- tenant/project-scoped session helper
- `projects` table과 `workspaces.project_id`
- Project/Workspace/Ontology/outbox의 선택적 project RLS predicate
- ephemeral PostgreSQL project isolation negative check
- transactional outbox schema

### Remaining

- Identity, Dashboard, Workflow, Export repository의 PostgreSQL 완전 전환
- managed PostgreSQL에서의 실제 backup/restore 및 failover drill
- connection pool/Redis/outbox worker의 장시간 부하 검증

Ephemeral PostgreSQL migration·RLS·runtime repository, pooled tenant connection, transactional outbox retry/dead-letter와 SQLite backup/restore tamper detection은 테스트됐다. 현재 host에는 Docker CLI가 없어 compose 기반 PostgreSQL/pgvector 재현은 별도 환경에서 수행해야 한다.

## Project Layer — 60%

### Implemented

- architecture and domain definition
- project catalog
- Project != Dataset principle
- SQLite/PostgreSQL projects table과 migration
- canonical Project repository/service/API
- organization/project access negative tests
- `workspaces.project_id`
- `user_project_scopes`, principal `project_scopes`, 초기 `active_project_id`
- Manufacturing Demo Project migration
- Project selector와 project route foundation
- Project별 Workspace query
- PostgreSQL project RLS verification
- 기존 Gold/E2E 회귀 유지

### Remaining

- 삭제된 Project deep link의 전용 tombstone UX
- PostgreSQL로 완전 전환되지 않은 legacy operational repository의 project predicate 통합

## Adapter Layer — 80%

### Implemented

- adapter protocol and registry
- Dataset Manifest schema and checksum/source version
- strict Prediction Result contract
- CSV/JSON/JSONL/Parquet file ingestion
- ingestion run state and invalid-row quarantine
- Azure PdM and MetroPT adapters
- Dataset Version/projection registration
- adapter contract and quarantine API tests

### Remaining

- production REST/Kafka/MQTT/OPC-UA connector credentials and retry policy
- schema evolution compatibility matrix for external connector versions
- streaming backpressure and replay load test

## Test Baseline

```text
Canonical naming: PASS
PostgreSQL organization/project migration/RLS/runtime: PASS
Backend tests: 118 PASS
Gold scenarios: 8/8 PASS
Frontend unit tests: 3 PASS
TypeScript: PASS
Production build: PASS
Initial JavaScript: 213.87 KiB / 300 KiB PASS
Largest deferred chunk: 443.24 KiB / 500 KiB target PASS
Playwright E2E: 28 PASS
Live Project 2→Project 3 stores: PostgreSQL 1 + Neo4j 3 + Project 3 RAG 1 PASS
```

## Current Technical Debt

### High Priority

- `ontology_dashboard.__init__`의 legacy path extension과 `api/factory_signal_board` physical source 잔존
- planner logic이 단일 legacy `ontology_planner_service.py`에 집중
- Project 3의 Neo4j/LangGraph/RAG capability가 flat context adapter로 축소돼 연결됨
- Project 2에 Neo4j GraphQueryPort, vector retrieval, multi-store LangGraph orchestration 없음
- Ontology/Datasets/Governance 전용 Workbench 없음
- Project entity foundation은 구현되었으나 operational repository의 project_id 전환 미완료
- active PostgreSQL runtime 미완료
- Project scope가 persistence record에 없음
- source files가 물리적으로 legacy directory에 남아 있음
- `main.py` 일부 handler container 역할 유지

### Medium Priority

- frontend unit test 부족
- accessibility gate 없음
- rate limiter가 process-local
- actual object storage 없음
- actual LLM provider quality evaluation 부족

### Low Priority / Deferred

- real-time collaborative editing
- domain pack marketplace
- complete protocol adapter set

## Architecture Risks

1. Project Layer 전에 dataset-specific 기능을 추가하면 global manufacturing workspace에 결합된다.
2. SQLite repository를 유지하며 production 기능을 늘리면 transaction과 concurrency 위험이 커진다.
3. Azure 수치를 코드로 재현하지 않고 문서 숫자로만 사용하면 발표 신뢰성이 떨어진다.
4. Ontology Core에 dataset-specific 속성을 계속 추가하면 multi-project 재사용성이 무너진다.
5. `main.py` handler 이동을 중단하면 router 분리가 형식적인 구조로 남는다.

## Release Risks

- PostgreSQL production runtime unavailable
- Project API와 PostgreSQL RLS isolation은 구현되었으나 Dashboard·Ontology·Action runtime isolation은 Workspace scope에 의존
- dataset license/provenance review pending
- no real-data Azure ingestion yet
- no second-project abstraction validation
- no automated accessibility gate

## Immediate Next Work

`docs/10-product-convergence-polyglot-agentic-roadmap.md`의 Stage 44~45를 우선한다.

```text
1. product/architecture rebaseline와 ADR 갱신
2. planner canonical physical migration
3. Project 3 typed health/query/RAG/graph client
4. read-only Ontology Workbench vertical slice
5. PostgreSQL + pgvector + Neo4j local integration foundation
6. Dataset Version과 multi-store projection
7. 기존 Project scope/PostgreSQL repository 작업을 새 vertical slice에 통합
```

## Status Update Rule

작업 완료 후 다음을 함께 수정한다.

- maturity percentage
- implemented items
- remaining items
- test baseline
- architecture and release risks
- immediate next work

근거 없는 비율 변경은 하지 않는다.
