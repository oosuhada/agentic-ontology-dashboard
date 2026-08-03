# Ontology Dashboard System Architecture

- Last updated: 2026-08-01
- Architecture maturity target: production-oriented modular monolith with project-aware boundaries

## 1. Context

Ontology Dashboard는 여러 Project의 데이터와 분석 결과를 역할별 Dashboard와 Report로 전달한다.

```text
Organization
    ↓
Project
    ↓
Workspace
    ↓
Role Dashboard
    ↓
Report / Action / Export
```

Prediction과 Dashboard의 책임은 분리한다.

```text
Source Data / External System
            ↓
      Prediction Module
            ↓
 Prediction Result Contract
            ↓
   Ontology Dashboard API
            ↓
 Role Dashboard / Report
```

## 2. Core Layers

### Presentation Layer

- React application
- Project selector
- Workspace selector
- Role-aware routes
- Dashboard runtime
- Dashboard editor
- Report and export UI
- Admin UI

### API Layer

- FastAPI application factory
- Feature routers
- Authentication and RBAC dependencies
- Project and workspace scope guards
- CSRF and session handling
- Rate limiting

### Application Service Layer

- Identity Service
- Project Service
- Ontology Service
- Dashboard Service
- Planner Service
- Export Service
- Role Workflow Service
- Domain Pack Services

### Adapter Layer

- File Adapter
- REST Adapter
- Kafka Adapter
- MQTT Adapter
- OPC-UA Adapter
- Dataset-specific adapters
- Prediction Result normalizer

현재 구현률은 낮으며 File Adapter와 dataset ingestion contract가 우선이다.

### Repository Layer

- Identity Repository
- Project Repository
- Dashboard Repository
- Ontology Instance Repository
- Action Repository
- Workflow Repository
- Export Repository
- Transactional Outbox

SQLite는 local/demo compatibility 용도다. PostgreSQL이 production target이다.

### Persistence Layer

- PostgreSQL
- JSONB
- Row Level Security
- Schema migrations
- Transactional outbox
- Ontology objects and links
- Project metadata
- Dataset versions
- Analysis runs

## 3. Project Model

```text
Organization
└── Project
    ├── Project Metadata
    ├── Data Sources
    ├── Dataset Versions
    ├── Domain Schema
    ├── Ontology Mappings
    ├── Analysis Profiles
    ├── Prediction Contracts
    ├── Workspaces
    ├── Dashboard Templates
    └── Analysis Runs
```

Project는 데이터셋과 동일한 개념이 아니다.

한 Project는 여러 data source를 가질 수 있고, 하나의 dataset은 여러 Project에서 다른 목적으로 사용될 수 있다.

## 4. Workspace Model

Workspace는 사용자가 실제로 협업하고 데이터를 보는 경계다.

```text
Project
├── Main Workspace
├── Site Workspace
├── Team Workspace
└── Audit Workspace
```

MVP에서는 한 Project당 기본 Workspace 하나로 시작할 수 있다.

## 5. Request Flow

### Project Dashboard Load

```text
User
→ React Project Selector
→ GET /api/projects
→ Project 선택
→ GET /api/projects/{project_id}/workspaces
→ `/app/projects/{project_id}` route context 복원
→ GET /api/dashboards/resolved
→ Project-scoped Ontology query
→ Role template + user preferences
→ Dashboard render
```

### Analysis Result Ingestion

```text
Source Adapter
→ Raw Result
→ Prediction Result Contract validation
→ Project mapping
→ AnalysisRun 저장
→ Evidence 생성
→ Event / Object / Link materialization
→ Outbox event
→ Dashboard query
```

### Governed Action

```text
User Action
→ CSRF validation
→ Permission check
→ Project/workspace scope check
→ Object and parameter validation
→ Idempotency reservation
→ Domain transaction
→ Audit + Outbox
→ Result response
```

## 6. Current Runtime Architecture

### Backend

- `ontology_dashboard.application.create_app()`
- feature router modules
- dependency composition module
- SQLite active runtime
- canonical `ontology_dashboard.projects` model/repository/service
- organization-scoped Project list/detail/admin APIs
- `workspaces.project_id`와 Manufacturing Demo Project migration
- principal의 `project_scopes`와 초기 `active_project_id`
- PostgreSQL organization + optional project RLS verification
- persistent ontology object/link store
- transactional outbox foundation

### Frontend

- React
- role-aware application
- dashboard editor
- Project selector와 `/app/projects/:projectId` route foundation
- Project별 Workspace 조회
- workspace and event data hooks
- role workspace hooks

현재 Project selector는 Manufacturing Demo Project에서 동작한다. Project Home, 다중 Project E2E, role별 active project persistence는 후속 범위다.

## 7. Target Backend Package Structure

```text
api/ontology_dashboard/
├── application.py
├── dependencies.py
├── settings.py
├── routers/
├── identity/
├── projects/
├── ontology/
├── dashboards/
├── planner/
├── exports/
├── workflows/
├── adapters/
├── persistence/
└── domain_packs/
    ├── azure_pdm/
    ├── metropt/
    ├── ai4i/
    ├── cmapss/
    └── cip_dmd/
```

## 8. Target Frontend Structure

```text
web/src/
├── app/
├── routing/
├── features/
│   ├── projects/
│   ├── workspaces/
│   ├── dashboards/
│   ├── reports/
│   ├── ontology/
│   ├── admin/
│   └── role-workspaces/
├── components/
├── hooks/
└── api/
```

## 9. Security Boundaries

- Organization boundary
- Project boundary
- Workspace boundary
- Role and permission boundary
- Object and Action boundary
- Share token scope
- Export scope
- Admin scope

PostgreSQL에서는 `app.organization_id`와 선택적 `app.project_id` session setting을 사용한다.

현재 `projects`, `workspaces`, Ontology persistence, outbox migration에 organization/project predicate가 정의되어 있고 실서버 ephemeral PostgreSQL negative check를 통과한다. 다만 SQLite 중심 active runtime의 Ontology·Dashboard·Action repository가 모든 write에 `project_id`를 채우고 query predicate에 사용하는 작업은 남아 있다.

## 10. Deployment Model

### Local / Demo

- React dev server
- FastAPI
- SQLite
- local fixture or file adapter

### Pilot

- React static build
- FastAPI containers
- PostgreSQL
- object storage
- HTTPS reverse proxy
- structured logging

### Production Target

- managed PostgreSQL
- migration job
- Redis rate limiting
- object storage
- OpenTelemetry
- backup and restore
- secret manager
- CI/CD staging gate

## 11. Architecture Constraints

- `Factory Signal Board` namespace를 다시 만들지 않는다.
- Project selector와 project scope 없이 새로운 dataset을 직접 global workspace에 추가하지 않는다.
- Prediction logic을 React나 Dashboard Service 안에 넣지 않는다.
- Dataset-specific schema를 Core Ontology에 무리하게 합치지 않는다.
- PostgreSQL 지원이 완전하지 않은 상태에서 production 지원 완료라고 표시하지 않는다.
