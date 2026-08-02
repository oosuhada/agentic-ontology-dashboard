# Ontology Dashboard Project Catalog

- Last updated: 2026-08-01
- Purpose: multi-project showcase and validation catalog

## Catalog Principles

- Project는 dataset과 동일하지 않다.
- 각 Project는 명확한 사용자 판단과 역할별 Dashboard 목적을 가져야 한다.
- 모든 Project는 공통 Ontology Core와 Prediction Result Contract에 mapping한다.
- Project별 schema와 board catalog는 분리한다.

## 1. Manufacturing Demo Project

### Status

Active migrated Project / regression baseline

Canonical ID: `manufacturing-demo-project`

Default Workspace: `manufacturing-demo`

### Purpose

현재 Gold fixture와 기존 역할별 flow를 보존하고 Project Layer migration의 회귀 기준으로 사용한다.

### Data

- GS-001 ~ GS-008 fixture
- local operational records

### Main Roles

- Process Manager
- Process Engineer
- Executive Viewer
- Quality Auditor
- Maintenance Technician
- Data Scientist
- FDE
- Tenant Admin

### Current Capabilities

- role dashboard
- evidence/report/layout
- governed actions
- template approval
- model release approval
- planner
- export and audit

### Implemented Project Foundation

- Project entity와 organization-scoped API
- 기존 `manufacturing-demo` Workspace를 Project 하위로 migration
- principal project scope와 Project selector
- `/app/projects/manufacturing-demo-project` route foundation
- PostgreSQL project RLS

### Next Work

- Dashboard Template·preference·saved view key에 project_id 추가
- Ontology·Action·Workflow·Export repository runtime에 project predicate 적용
- 두 번째 Project를 이용한 selector switch와 resource isolation E2E

## 2. Azure Fleet Maintenance Project

### Proposed ID

`azure-fleet-maintenance`

### Status

NEXT / primary showcase

### Dataset

Microsoft Azure Predictive Maintenance sample dataset

Expected files:

- machines
- telemetry
- errors
- failures
- maintenance

### Purpose

- fleet 비교
- model·age peer comparison
- error-to-failure risk
- maintenance evidence
- 역할별 우선순위와 조치 설명

### Core Mapping

```text
Machine             → Asset
Telemetry           → Observation
Error               → Event
Failure             → Event
Maintenance         → Maintenance
Risk Result         → AnalysisRun output
```

### Role Views

#### Manager

- fleet risk priority
- peer percentile
- unresolved warnings
- maintenance recommendation

#### Engineer

- telemetry trend
- error sequence
- component maintenance history
- failure evidence

#### Data Scientist

- conversion rate
- cohort definition
- model metrics
- data quality

#### Executive

- fleet-wide risk
- operational impact assumptions
- overdue actions

### Required Derived Metrics

- error type별 24시간 내 failure conversion
- preventive/corrective maintenance interval
- machine model and age cohort
- failure and maintenance frequency

## 3. MetroPT Compressor Monitoring Project

### Proposed ID

`metropt-compressor-monitoring`

### Status

Planned second project

### Purpose

Azure와 다른 고밀도 시계열 구조를 통해 platform abstraction을 검증한다.

### Domain

- compressor
- sensor observations
- anomaly intervals
- air leak events

### Main Role Views

- Engineer: time-series and anomaly interval
- Technician: canonical WorkOrder checklist and field action
- Manager: downtime and unresolved event summary
- Data Scientist: detection quality and threshold

### Validation Goal

Azure 전용 조건문 없이 같은 Project·Dashboard·Ontology platform 위에서 작동해야 한다.

## 4. AI4I Failure Classification Project

### Proposed ID

`ai4i-failure-classification`

### Status

Later

### Purpose

고장 유형 분류와 모델 검증 UI를 단순하고 재현 가능한 구조로 제공한다.

### Main Role

Data Scientist / ML Validator

### Key Views

- confusion matrix summary
- failure type distribution
- feature contribution
- threshold comparison
- model release request

### Limitation

Fleet 정비 workflow를 대표하는 showcase로는 제한적이다.

## 5. NASA C-MAPSS RUL Project

### Proposed ID

`cmapss-rul-planning`

### Status

Later

### Purpose

잔여수명 예측과 계획정비 판단을 제공한다.

### Core Mapping

```text
Engine Unit       → Asset
Operating Cycle   → Observation
RUL Estimate      → AnalysisRun output
Threshold Alert   → Event
Planned Service   → Recommendation
```

### Role Views

- Manager: RUL priority and schedule impact
- Engineer: sensor degradation trend
- Data Scientist: MAE, RMSE, NASA score

## 6. CiP-DMD Cylinder Quality Project

### Proposed ID

`cip-dmd-cylinder-quality`

### Status

Later / domain-specific project

### Purpose

실제 산업 품질·이상 시나리오와 현장 점검 workflow를 제공한다.

### Key Strength

- real-world industrial context
- anomaly and quality workflow

### Limitation

설비 수가 제한되어 fleet comparison에는 적합하지 않다.

## Project Selector and Home UI

```text
Project selector
├── Manufacturing Demo
├── Azure Fleet Maintenance
├── MetroPT Compressor Monitoring
├── AI4I Failure Classification
├── NASA C-MAPSS RUL
└── CiP-DMD Cylinder Quality

Project Home
├── Project/Workspace KPIs
├── Dataset count and risk events
├── Project 3 readiness
├── allowed role context
└── Dashboard / Agent / Ontology / Governance / Dataset entry points
```

상단 context switcher:

```text
[Project ▼] [Workspace ▼] [Active Role ▼] [Time Range]
```

## Project Readiness Matrix

| Project | Data Adapter | Ontology Mapping | Dashboard | Prediction Contract | E2E | Overall |
|---|---:|---:|---:|---:|---:|---:|
| Manufacturing Demo | 100% | 95% | 96% | 90% | 100% | Active Project baseline |
| Azure Fleet Maintenance | 70% adapter | 35% design | 20% design | 80% contract | contract tests | Data ingestion next |
| MetroPT | 70% adapter | 30% design | 15% design | 80% contract | contract tests | Time-series data ingestion next |
| AI4I | 0% | 10% design | 5% design | 5% design | 0% | Later |
| C-MAPSS | 0% | 10% design | 5% design | 5% design | 0% | Later |
| CiP-DMD | 0% | 10% design | 5% design | 5% design | 0% | Later |

## Admission Criteria for New Projects

새 Project를 catalog에 추가하려면 다음을 문서화한다.

- 사용자 판단 목표
- target roles
- dataset provenance and license
- data adapter
- domain mapping
- prediction contract mapping
- dashboard template
- acceptance scenario
- release impact
