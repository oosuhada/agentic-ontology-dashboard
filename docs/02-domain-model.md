# Ontology Dashboard Domain Model

- Last updated: 2026-08-01
- Scope: multi-project decision-support platform

## 1. Core Aggregate Hierarchy

```text
Organization
└── Project
    └── Workspace
        ├── Users and Roles
        ├── Dashboard Templates
        ├── Saved Views
        ├── Objects and Links
        ├── Analysis Runs
        ├── Actions
        └── Audit Records
```

## 2. Platform Entities

### Organization

Tenant boundary.

주요 속성:

- id
- slug
- name
- status
- created_at

### Project

업무 목적, 데이터, 분석, 화면 설정을 묶는 최상위 application boundary.

현재 canonical Project aggregate와 SQLite/PostgreSQL persistence, organization-scoped API가 구현되어 있다. 기존 Gold fixture는 `manufacturing-demo-project` 아래의 `manufacturing-demo` Workspace로 migration된다.

주요 속성:

- id
- organization_id
- slug
- display_name
- description
- domain_pack_code
- status
- default_workspace_id
- created_at
- updated_at

### Workspace

Project 안에서 사용자와 역할이 협업하는 범위.

주요 속성:

- id
- organization_id
- project_id
- slug
- display_name
- workspace_type
- status

### DataSource

원본 데이터를 공급하는 시스템 또는 파일 묶음.

예:

- CSV directory
- REST endpoint
- Kafka topic
- MQTT broker
- OPC-UA node set

### DatasetVersion

Project에서 사용한 데이터 snapshot 또는 dataset release.

주요 속성:

- id
- project_id
- source_id
- version
- checksum
- record_counts
- schema_snapshot
- imported_at

### DomainPack

Project별 object type, link type, action type, dashboard capability를 정의하는 package.

### PredictionContract

외부 분석 결과와 Dashboard 사이의 안정된 계약.

공통 필드 예시:

```json
{
  "project_id": "fleet-maintenance",
  "asset_id": "machine-42",
  "analysis_type": "failure-risk",
  "observed_at": "2026-08-01T08:00:00Z",
  "status": "warning",
  "score": 0.73,
  "score_unit": "probability",
  "evidence": [],
  "recommended_actions": []
}
```

### AnalysisRun

Prediction 또는 분석 작업의 실행 기록.

주요 속성:

- id
- project_id
- dataset_version_id
- analysis_profile_id
- model_version
- status
- started_at
- completed_at
- metrics
- source_revision

## 3. Ontology Core

Project별 schema는 다음 공통 Core에 mapping한다.

### Asset

관리·분석 대상.

예:

- Machine
- Compressor
- Engine Unit
- Cylinder
- Product Cycle

### Observation

센서값, 상태값, 측정값 등 시간 기반 관측.

### Event

사람의 판단 또는 조치가 필요한 사건.

예:

- Error
- Failure
- Air Leak
- Risk Warning
- Data Quality Hold

### Evidence

주장, 위험도, 권장 Action을 뒷받침하는 근거.

### Maintenance

정비·점검·교체·수리 이력.

### Recommendation

근거 기반 권장 조치.

### Action

사용자가 실행하거나 승인하는 통제된 업무 행동.

## 4. Core Relationships

```text
Organization HAS_PROJECT Project
Project HAS_WORKSPACE Workspace
Project USES_DATA_SOURCE DataSource
Project HAS_DATASET_VERSION DatasetVersion
Project USES_DOMAIN_PACK DomainPack
Project HAS_ANALYSIS_RUN AnalysisRun
Workspace CONTAINS Asset
Asset HAS_OBSERVATION Observation
Asset HAS_EVENT Event
Event SUPPORTED_BY Evidence
Event RECOMMENDS Recommendation
Recommendation MAY_TRIGGER Action
Asset HAS_MAINTENANCE Maintenance
AnalysisRun PRODUCES Event
AnalysisRun PRODUCES Evidence
```

## 5. Project-Specific Domain Mapping

### Azure Fleet Maintenance

```text
Machine                    → Asset
Telemetry Row              → Observation
Error Record               → Event
Failure Record             → Event
Maintenance Record         → Maintenance
Failure Risk Result        → AnalysisRun output
Model + Age Peer Group     → Comparison cohort
```

대표 관계:

```text
Machine HAS_TELEMETRY Observation
Machine HAS_ERROR ErrorEvent
Machine HAS_FAILURE FailureEvent
Machine HAS_MAINTENANCE MaintenanceEvent
ErrorEvent PRECEDES FailureEvent
MaintenanceEvent APPLIES_TO Machine
```

### MetroPT Compressor Monitoring

```text
Compressor                 → Asset
Sensor Sample              → Observation
Air Leak Interval          → Event
Anomaly Detection Result   → AnalysisRun output
```

### AI4I Failure Classification

```text
Product Cycle              → Asset-like analysis subject
Process Measurement        → Observation
Failure Type               → Event
Classification Result      → AnalysisRun output
```

### NASA C-MAPSS

```text
Engine Unit                → Asset
Operating Cycle            → Observation
RUL Estimate               → AnalysisRun output
Maintenance Threshold      → Recommendation trigger
```

### CiP-DMD Cylinder Quality

```text
Cylinder / Equipment       → Asset
Sensor Sequence            → Observation
Anomaly Code               → Event
Rework / Inspection        → Action or Maintenance
```

## 6. Dashboard Domain

### DashboardTemplate

기본 layout과 board 구성을 정의한다.

Scope key:

```text
organization_id
project_id
workspace_id or workspace_type
role_code
template_version
```

### DashboardPreference

사용자의 override.

### SavedView

parameter, filter, active tab 상태를 저장한 view.

### Share

권한을 우회하지 않는 제한된 shared view token.

### BoardDefinition

catalog에 등록된 안전한 board type.

### BoardInstance

특정 Dashboard에 배치된 board.

## 7. Identity and Governance

### Principal

- user_id
- organization_id
- active_project_id
- project_scopes
- roles
- permissions
- workspace_scopes

현재 `project_scopes`는 Workspace scope에서 backfill되며, tenant admin은 Organization의 모든 Project를 가진다. `active_project_id`는 접근 가능한 첫 Project로 초기화되고 frontend route가 실제 화면 context를 복원한다. 사용자별 active project를 session persistence로 저장하는 기능은 남아 있다.

### RoleAssignment

MVP에서는 organization-level role과 workspace scope를 사용한다.

Target:

- organization role
- project role
- workspace role
- active role context

### ApprovalRequest

- template publish request
- model release request
- governed action request

## 8. Persistence Rules

모든 operational record는 최소 다음 scope를 가져야 한다.

```text
organization_id
project_id
workspace_id
```

예외는 global registry 또는 immutable platform metadata로 제한한다.

PostgreSQL target에서는 organization RLS와 선택적 project predicate를 적용한다. 현재 migration과 ephemeral PostgreSQL 검증은 완료되었지만, active SQLite runtime의 모든 operational repository가 `project_id`를 저장·조회하는 전환은 진행 중이다.

## 9. Invariants

- Workspace는 반드시 하나의 Project에 속한다.
- Project는 반드시 하나의 Organization에 속한다.
- DatasetVersion은 Project 범위 밖에서 직접 조회하지 않는다.
- AnalysisRun은 사용한 DatasetVersion과 contract version을 기록한다.
- Dashboard Template은 project와 role을 구분한다. 현재 runtime key는 Workspace와 role 중심이므로 Project key 추가가 남아 있다.
- Action은 대상 Object와 같은 project/workspace scope에서만 실행된다.
- Evidence 없는 자동 narrative claim은 publish하지 않는다.
