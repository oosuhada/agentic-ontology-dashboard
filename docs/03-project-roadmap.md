# Ontology Dashboard Project Roadmap

- Last updated: 2026-08-01
- Roadmap owner: project team
- Canonical entrypoint: `docs/next-session-master-prompt.md`

## Status Legend

- `DONE`: 구현 및 release gate 검증 완료
- `PARTIAL`: 핵심 기반 구현, production-level 잔여 작업 존재
- `NEXT`: 다음 우선순위
- `LATER`: 후속 확장

## Current Stage Summary

| Stage | Status | Scope |
|---|---|---|
| 16~31 | DONE | Auth, RBAC, Ontology adapter, Dashboard platform, role workspaces, planner, export, release gate |
| 32 | DONE | Ontology Dashboard canonical naming과 runtime safety |
| 34 | PARTIAL | Application factory, dependency composition, feature router 분리 |
| 35 | PARTIAL | SQLite migration, PostgreSQL DDL, migration runner, transactional outbox |
| 36 | DONE/PARTIAL | organization tenant isolation의 주요 admin·workspace 경계 구현 |
| 37 | PARTIAL | persistent Ontology object/link store와 PostgreSQL repository foundation |
| 38 | PARTIAL | frontend orchestration 분리, resource route·project selector 잔여 |
| 39 | PARTIAL | production fail-fast, session·CSRF·RBAC 기반; identity lifecycle 잔여 |
| 40 | PARTIAL | PostgreSQL 실서버 migration·RLS check, handler 이동·frontend editor 분리 |

## NEXT 1 — Project Layer

### Status

`PARTIAL` — persistence/API/selector foundation과 Manufacturing Demo migration 완료. Operational repository 전체의 project predicate와 다중 Project E2E는 남아 있다.

### Goal

여러 dataset과 domain scenario를 하나의 global manufacturing workspace에 넣지 않고 Project 단위로 선택·격리한다.

### Implemented in Current Substage

- SQLite/PostgreSQL `projects` table과 ordered migration
- canonical `ontology_dashboard.projects` model/repository/service
- Project list/detail와 admin create/update API
- organization-scoped access와 tenant/project negative tests
- `workspaces.project_id`
- `user_project_scopes`, principal `project_scopes`, 초기 `active_project_id`
- existing Manufacturing Demo를 `manufacturing-demo-project`로 migration
- Project selector와 `/app/projects/:projectId` route foundation
- Project별 Workspace API와 UI filtering
- PostgreSQL `app.project_id` setting과 Project/Workspace/Ontology RLS predicate
- 기존 Gold 8/8, Playwright 14, release gate 12/12 회귀 유지

### Remaining Deliverables

- Project membership와 project-level role assignment의 독립 관리 UI/API
- active project session persistence와 명시적 role context
- Dashboard Template, preference, saved view, share key에 `project_id` 추가
- SQLite/PostgreSQL Ontology object/link/action/workflow/export repository write와 query에 project predicate 적용
- Project selector의 두 번째 Project 실제 switch 검증
- 두 번째 Project를 이용한 end-to-end resource isolation 검증

### Acceptance Criteria

- 로그인 사용자는 접근 가능한 Project 목록만 본다. **완료**
- tenant A가 tenant B Project를 조회할 수 없다. **완료**
- Project를 변경하면 workspace가 함께 변경된다. **foundation 완료**
- board catalog, object query, saved view도 명시적 project scope를 사용한다. **미완료**
- 기존 Gold E2E는 migrated demo Project에서 유지된다. **완료**

## NEXT 2 — Dataset Adapter and Prediction Contract

### Goal

Prediction과 Dashboard를 분리하고 dataset-specific 입력을 공통 contract로 정규화한다.

### Deliverables

- Prediction Result JSON Schema
- Dataset Manifest Schema
- File Adapter interface
- ingestion run state machine
- validation and quarantine
- source checksum and dataset version
- adapter registry
- Azure PdM adapter

### Acceptance Criteria

- invalid result는 operational object로 materialize되지 않는다.
- 같은 contract로 file과 API 입력을 처리할 수 있다.
- AnalysisRun에 source, dataset version, model version이 기록된다.

## NEXT 3 — Azure Fleet Maintenance Project

### Goal

Azure Predictive Maintenance dataset을 대표 showcase Project로 구현한다.

### Deliverables

- telemetry/errors/failures/maint/machines 5개 파일 ingestion
- machineID relation
- model·age peer cohort
- maintenance type comparison
- error-to-failure conversion analysis
- role-specific dashboard templates
- Manager, Engineer, Data Scientist views

### Acceptance Criteria

- fleet 100대 비교가 가능하다.
- 계산된 비율과 중앙값이 재현 가능한 analysis artifact로 남는다.
- 리포트 문장은 계산된 Evidence를 인용한다.

## NEXT 4 — Second Project for Abstraction Validation

추천: MetroPT-3 Compressor Monitoring.

### Goal

Azure와 구조가 다른 단일 설비·고밀도 시계열 Project로 플랫폼 추상화를 검증한다.

### Deliverables

- MetroPT File Adapter
- time-series observation ingestion
- anomaly interval Event
- project-specific board catalog
- project switch E2E

### Acceptance Criteria

- Azure 전용 코드 수정 없이 두 Project가 공존한다.
- Core Ontology와 Dashboard runtime이 재사용된다.

## NEXT 5 — PostgreSQL Runtime Completion

### Goal

현재 SQLite 중심 repository를 production PostgreSQL implementation으로 전환한다.

### Deliverables

- psycopg dependency installation
- connection pool
- identity repository PostgreSQL implementation
- dashboard repository PostgreSQL implementation
- action/workflow/export repository PostgreSQL implementation
- project-aware RLS
- transaction and outbox worker
- migration upgrade/rollback test

### Acceptance Criteria

- production startup이 PostgreSQL에서 정상 동작한다.
- SQLite production pilot flag가 불필요해진다.
- concurrent preference와 Action test가 통과한다.
- tenant/project RLS negative test가 통과한다.

## NEXT 6 — Remaining Backend Modularization

### Goal

legacy handler container 역할을 하는 `main.py`를 제거하고 feature modules가 handler를 직접 소유한다.

### Deliverables

- dashboard handlers 이동
- planner handlers 이동
- role-workspace handlers 이동
- export handlers 이동
- manufacturing domain handlers 이동
- legacy physical source directory canonical 이동

### Acceptance Criteria

- `main.py`가 app composition 또는 compatibility entrypoint 수준으로 축소된다.
- feature router가 `main.py`를 import하지 않는다.
- `api/factory_signal_board` 물리 디렉터리가 제거된다.

## NEXT 7 — Frontend Resource Routing and UX

### Deliverables

- `/app/projects/:projectId`
- `/app/projects/:projectId/workspaces/:workspaceId`
- `/app/objects/:objectType/:objectId`
- active role selector
- route restore and deep link
- dashboard editor 추가 hook 분리
- error boundary
- accessibility gate

## LATER — Additional Projects

- AI4I Failure Classification
- NASA C-MAPSS RUL
- CiP-DMD Cylinder Quality
- additional customer-specific domain packs

## LATER — Production Operations

- Redis distributed rate limiting
- object storage export
- OpenTelemetry
- structured logging
- error tracking
- backup/restore drill
- CI/CD staging deployment
- SAST/DAST

## Priority Rule

다음 우선순위는 원칙적으로 유지한다.

```text
Project Layer
→ Prediction Contract
→ File Adapter
→ Azure Project
→ Second Project
→ PostgreSQL Runtime Completion
→ Production Operations
```

새로운 시각 기능은 Project scope와 contract 기반이 마련된 이후에 추가한다.
