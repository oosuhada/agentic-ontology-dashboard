# Ontology Dashboard Implementation Status

- Last updated: 2026-08-02
- Baseline: release gate 13/13 PASS with isolated Playwright E2E
- Current execution plan: `docs/10-product-convergence-polyglot-agentic-roadmap.md`

## Current Maturity

```text
Backend        93%
Frontend       89%
Architecture   95%
PostgreSQL     70%
Project Layer  60%
Adapter Layer  10%
```

이 비율은 단순 파일 개수가 아니라 2026-08-01 목표 아키텍처 대비 구현·검증·운영 준비도를 반영한 역사적 추정치다. Palantir 수준의 전체 시각 완성도나 모든 메뉴의 운영 준비도를 의미하지 않는다. `Ontology`와 `Governance` 전용 Workbench는 실제 route와 E2E까지 연결되었고, `Datasets`는 Stage 47 foundation 위에서 Catalog 완성 작업이 남아 있다.

## User-Visible Product Surface

```text
Dashboards   CONNECTED
Analysis     CONNECTED
Agent        CONNECTED EVIDENCE WORKBENCH
Ontology     CONNECTED WORKBENCH / DEGRADED GRAPH SAFE
Datasets     PARTIAL CATALOG / MATERIALIZATION FOUNDATION
Governance   CONNECTED PROJECT WORKBENCH
```

- Agent Evidence Workbench는 scoped query, persisted run restore, claim→evidence navigation, store/version/object trace와 orchestration lineage를 제공한다.
- Ontology Workbench는 exact project/workspace route, object search, graph/inspector, Add Graph Board, multi-store Ask, route restore와 isolation E2E를 제공한다.
- Dataset Version·projection·mapping·materialization backend와 초기 Catalog route는 있으나 profile/quarantine와 재사용 가능한 Analysis materialization user journey가 남아 있다.
- Governance Workbench는 project-scoped access, approvals, agent claims/evidence/traces/checkpoints, lineage, projection health와 permission-gated retry를 통합한다.

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

- dashboard/planner/export/role-workspace/manufacturing handler의 완전한 feature module 이동
- 전체 PostgreSQL repository 전환
- trusted proxy hardening
- distributed rate limiting
- Dashboard·Ontology·Action·Workflow·Export repository의 project-aware write/query
- project-level role assignment와 active project session persistence
- identity invitation/reset/SSO lifecycle

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
- build-time 300 KiB initial JavaScript budget gate (`212.25 KiB` verified)
- first visual token/density slice and `docs/ui/palantir-visual-language.md`

### Remaining

- `/app/projects/:projectId/workspaces/:workspaceId/datasets` Catalog 완성
- 전체 제품 visual language와 three-workbench screenshot review
- Project Home
- active role selector
- additional editor hook separation
- undo/redo and draft recovery
- 725 KiB lazy `DataTableRenderer` chunk의 renderer/vendor 단위 최적화

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
- Project Layer를 실제 코드와 DB에 구현
- full production deployment architecture verification

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

- Python `psycopg` runtime dependency installation in active environment
- connection pool
- Identity repository
- Dashboard repository
- Workflow repository
- Action repository
- Export repository
- PostgreSQL Project repository runtime 연결
- operational write에서 non-null project_id 강제
- transaction recovery worker
- backup/restore drill
- production startup enablement

Ephemeral PostgreSQL migration, RLS와 runtime repository gate는 통과했다. 다만 production connection, backup/restore와 Docker-backed pgvector/Neo4j 통합이 남아 있으므로 Production 전체 완료로 표시하면 안 된다.

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

- project membership and project-level role assignment 관리
- active project session persistence
- project-aware dashboard templates/preferences/saved views/share
- project-aware object/link/action/workflow/export runtime records
- SQLite repository project predicate와 PostgreSQL runtime 연결
- 두 번째 Project switch와 deleted route handling
- 두 번째 Project의 end-to-end resource isolation 검증

## Adapter Layer — 10%

### Implemented

- adapter concept
- domain adapter snapshot projection
- file-based automatic analysis direction
- prediction contract draft

### Remaining

- adapter protocol/interface
- Dataset Manifest schema
- Prediction Result JSON Schema
- File Adapter
- ingestion state machine
- invalid data quarantine
- Azure PdM adapter
- MetroPT adapter
- REST/Kafka/MQTT/OPC-UA adapters
- source version and checksum
- adapter registry

## Test Baseline

```text
Canonical naming: 84 files, 0 violations
PostgreSQL organization/project migration/RLS: PASS
Backend tests: 65 PASS
Gold scenarios: 8/8 PASS
Frontend unit tests: 1 PASS
TypeScript: PASS
Production build: PASS
Playwright E2E: 14 PASS
Release gate: 12/12 PASS
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
