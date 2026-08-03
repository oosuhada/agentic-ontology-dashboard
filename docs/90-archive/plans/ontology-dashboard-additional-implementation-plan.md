# Ontology Dashboard 추가 기능 구현 계획

- 가칭 제품명: **Ontology Dashboard**
- 현재 구현체: `Factory Signal Board` 제조 예지보전 vertical slice
- 문서 목적: 현재 제조 중심 MVP를 도메인 중립적인 온톨로지 기반 대시보드·업무 애플리케이션으로 확장하기 위한 단계별 구현 계획
- 기준일: 2026-08-01
- 참고 문서:
  - `docs/10-product/role-needs-research.md`
  - `docs/40-ui-ux/reference/palantir-contour-dashboard-benchmark.md`
  - `docs/20-architecture/current-state/current-state.md`
  - `docs/20-architecture/service-contract.md`

---

# 1. 제품 재정의

## 1.1 목표

Ontology Dashboard는 특정 제조업 대시보드가 아니라, 조직의 데이터와 업무를 다음 요소로 통합하는 범용 애플리케이션을 목표로 한다.

```text
Object Types
+ Objects
+ Link Types
+ Links
+ Actions
+ Policies
+ Evidence
+ Dashboards
+ User Preferences
= Ontology-aware operational application
```

사용자는 원시 테이블이나 모델 객체가 아니라 업무적으로 의미 있는 객체와 관계를 탐색하고, 허용된 행동을 수행한다.

예:

```text
제조: Equipment → Event → Work Order → Technician
물류: Shipment → Route → Delay → Carrier
리테일: Product → Store → Inventory → Promotion
금융: Account → Transaction → Alert → Investigation
헬스케어: Patient → Encounter → Test → Care Task
```

## 1.2 기존 Factory Signal Board의 위치

현재 구현은 삭제하거나 폐기하지 않는다.

```text
Ontology Dashboard Platform
└── Manufacturing Predictive Maintenance Pack
    ├── Equipment
    ├── Sensor Observation
    ├── Risk Event
    ├── Evidence Package
    ├── Inspection
    └── Maintenance Action
```

즉, `Factory Signal Board`는 제품 전체 이름이 아니라 첫 번째 도메인 팩 또는 샘플 workspace로 전환한다.

## 1.3 이름 변경 범위

초기 단계에서는 화면 표시명과 문서 개념을 `Ontology Dashboard`로 바꾸되, Python package와 내부 module 이름은 한 번에 바꾸지 않는다.

권장 순서:

1. UI brand와 문서 이름 변경
2. domain-neutral contract 추가
3. 기존 제조 API를 adapter 아래로 이동
4. 테스트 통과 후 package rename 여부 결정
5. GitHub 저장소는 가능하면 `ontology-dashboard`로 생성

급하게 모든 파일명을 바꾸면 현재 통과 중인 회귀 테스트와 import 경로가 불필요하게 깨질 수 있다.

---

# 2. 핵심 제품 원칙

## 2.1 역할 기본값과 개인화의 결합

사용자가 로그인했을 때 보이는 화면은 다음 계층을 합성한다.

```text
Mandatory policy
→ Organization template
→ Role default template
→ Workspace/domain template
→ User persistent preferences
→ Session overrides
```

우선순위 규칙:

1. 안전·보안·감사 필수 요소는 사용자가 숨길 수 없다.
2. 조직 관리자가 게시한 template이 역할 기본 화면을 정한다.
3. 사용자는 허용 범위 내에서 탭, 보드 순서, 크기, 가시성, 기본 필터를 저장한다.
4. 로그인 시 마지막 저장 상태를 복원한다.
5. 세션 중 임시 선택은 명시적으로 저장하지 않으면 재로그인 후 사라진다.

## 2.2 보기와 편집의 분리

세 가지 모드를 구분한다.

### View mode

- 필터·파라미터 변경
- 차트 선택과 drill-down
- 전체화면
- 공유 링크
- 데이터 내보내기
- 허용된 Action 실행

### Personal edit mode

- 개인 탭 순서 변경
- 개인 보드 순서·크기 변경
- 허용된 보드 표시·숨김
- 개인 기본 필터 저장
- 역할 기본값으로 복원

### Template edit mode

- 관리자 또는 FDE가 조직·역할 template 편집
- 보드 추가·삭제
- ontology binding 변경
- 필수 보드 지정
- 역할별 허용 customization 정책 정의
- 새 template version 게시

## 2.3 대시보드는 분석 결과가 아니라 업무 표면

대시보드는 단순 차트 모음이 아니다.

각 Board는 다음 중 하나 이상을 수행한다.

- 객체 상태 관찰
- 관계 탐색
- 추세·분포 분석
- 근거 설명
- 품질·감사 확인
- Action 실행
- 업무 handoff

## 2.4 LLM의 역할

LLM은 다음에 사용한다.

- 자연어 질문을 ontology query intent로 변환
- 사용자의 역할과 사건에 맞는 설명 생성
- 허용된 Board catalog에서 화면 구성 제안
- FDE의 schema·dashboard 초안 작성 보조
- 보고서 초안과 요약 생성

LLM이 할 수 없는 일:

- 권한 우회
- 임의 React/HTML 실행
- ontology schema를 승인 없이 production 반영
- 원본 Evidence 수치 변경
- 허용되지 않은 Action 실행
- 사용자 template을 동의 없이 덮어쓰기

---

# 3. 목표 사용자 구조

## 3.1 일반 사용자 앱 역할

현재 역할과 확장 역할:

| Role code | 화면 이름 | 주요 목적 |
|---|---|---|
| `executive_viewer` | 임원 Viewer | 조직 전체 위험·성과·추세·대응 상태 확인 |
| `process_manager` | 운영 매니저 | 우선순위·배정·기한·에스컬레이션 |
| `process_engineer` | 도메인 엔지니어 | 원인 분석·근거 검토·점검 계획·보고 |
| `maintenance_technician` | 현장 작업자 | 배정 작업·체크리스트·측정·완료 기록 |
| `quality_auditor` | 품질·감사 Viewer | lineage·버전·사용자 행동·증거 재구성 |
| `ml_validator` | 데이터 사이언티스트 | 모델·데이터·threshold·오류·drift 검증 |
| `fde` | Forward Deployed Engineer | 고객 workflow·ontology·integration·template 구축 |

## 3.2 관리자 앱 역할

관리자 페이지는 일반 역할 화면과 분리한다.

| Admin role | 권한 |
|---|---|
| `tenant_admin` | 사용자, 역할, resource scope, 조직 설정 |
| `security_admin` | 인증, session, security policy, 감사 접근 |
| `dashboard_admin` | 조직·역할 dashboard template 게시 |
| `integration_admin` | 외부 datasource, LLM, webhook, connector 상태 |
| `super_admin` | 개발·로컬 환경 전용 전체 관리 |

MVP에서는 하나의 `tenant_admin` test account로 시작하되 내부 schema는 역할 분리를 허용한다.

## 3.3 FDE와 관리자의 차이

FDE는 고객 문제 해결과 애플리케이션 구축 역할이다.

FDE가 할 수 있는 것:

- 고객 workspace의 ontology schema 초안
- object·link mapping
- dashboard template 작성
- datasource·integration 상태 진단
- 역할별 preview
- feature flag와 demo configuration
- 사용자 workflow 테스트

FDE가 기본적으로 하면 안 되는 것:

- 조직 전체 사용자 계정 임의 삭제
- 비밀번호 열람
- production secret 원문 열람
- 감사 로그 삭제
- 보안 정책 우회
- 승인 없이 production schema 게시

---

# 4. 회원가입·로그인·테스트 계정 계획

## 4.1 인증 UX

### 회원가입

경로:

```text
/register
```

입력:

- 이름
- 이메일
- 비밀번호
- 조직명 또는 초대 코드
- 이용약관 동의

가입 상태:

```text
pending_approval
```

일반 사용자가 회원가입 과정에서 임의로 `executive`나 `admin` 역할을 선택할 수 없게 한다.

관리자 승인 후:

- 조직 연결
- 역할 할당
- 프로젝트·workspace scope 할당
- 계정 활성화

### 로그인

경로:

```text
/login
```

지원:

- 이메일·비밀번호
- 로그아웃
- session 만료
- 잘못된 비밀번호 오류
- 비활성화 계정 차단
- 향후 SSO 확장

### 관리자 로그인

동일 인증 체계를 사용하되 권한에 따라 redirect한다.

```text
일반 사용자 → /app
관리자 → /admin
FDE → /app/fde 또는 허용된 customer workspace
```

관리자용 별도 비밀번호 체계를 만들지 않는다. 같은 identity 위에서 role과 permission을 분리한다.

## 4.2 인증 기술 권장안

MVP:

- FastAPI
- SQLite 또는 PostgreSQL
- Argon2id password hash
- HttpOnly·Secure·SameSite cookie session
- CSRF 방어
- rate limit
- session rotation
- audit log

피해야 할 방식:

- localStorage에 access token 장기 저장
- 평문 비밀번호 저장
- 테스트 비밀번호를 production seed에 포함
- 클라이언트에서 role만 검사
- 관리자 route를 CSS로만 숨김

## 4.3 데모 테스트 계정

개발·데모 환경에서만 seed한다.

| Role | ID | Password |
|---|---|---|
| 관리자 | `admin@ontology.local` | `OntologyAdmin!2026` |
| 임원 Viewer | `executive@ontology.local` | `Executive!2026` |
| 운영 매니저 | `manager@ontology.local` | `Manager!2026` |
| 도메인 엔지니어 | `engineer@ontology.local` | `Engineer!2026` |
| 현장 작업자 | `technician@ontology.local` | `Technician!2026` |
| 품질·감사 | `quality@ontology.local` | `Quality!2026` |
| 데이터 사이언티스트 | `datascientist@ontology.local` | `DataScience!2026` |
| FDE | `fde@ontology.local` | `FDE!2026` |

보안 규칙:

- `.env.example`과 seed script에는 demo 전용임을 명시
- `APP_ENV=production`에서는 seed 금지
- DB에는 hash만 저장
- 첫 로그인 비밀번호 변경은 실제 배포 단계에서 필수
- GitHub 공개 전 실제 고객 이메일·비밀번호 포함 금지

---

# 5. 관리자 페이지 계획

## 5.1 정보 구조

```text
/admin
├── Overview
├── Users
├── Roles & Permissions
├── Organizations
├── Workspaces & Projects
├── Dashboard Templates
├── Board Registry
├── Ontology Registry
├── Integrations
├── LLM Providers
├── Audit Logs
└── Development Tools
```

`Development Tools`는 `APP_ENV=development|demo`에서만 노출한다.

## 5.2 Overview

표시:

- 활성 사용자
- pending 가입 요청
- 역할별 사용자 수
- 최근 관리자 변경
- integration health
- dashboard template version
- 실패한 LLM/provider 호출
- 권한 오류

## 5.3 Users

기능:

- 가입 승인·거절
- 사용자 검색
- 활성·비활성
- 역할 할당
- 조직 연결
- workspace·project scope
- session 강제 만료
- 비밀번호 재설정 링크 발급
- 사용자 활동 감사

## 5.4 Roles & Permissions

권한 모델:

```text
Permission = Role × Resource Scope × Environment × Action
```

예:

```text
process_engineer
× workspace=manufacturing-demo
× object_type=Equipment,RiskEvent,Inspection
× action=view,create_inspection,submit_report
```

관리자는 역할 이름뿐 아니라 실제 계산된 권한을 preview할 수 있어야 한다.

## 5.5 Dashboard Templates

기능:

- 역할별 default dashboard template 생성
- tab 추가·순서 변경
- board 추가·삭제·크기 조정
- 필수 board 지정
- 사용자의 개인 수정 허용 범위
- template preview as role
- draft·published 상태
- template version history
- 새 버전 게시
- rollback

## 5.6 Board Registry

기능:

- Board type 등록
- category 지정
- 입력 parameter schema
- output schema
- 허용 object type
- 허용 role
- data binding validation
- minimum·maximum size
- cross-filter source·target capability
- export 가능 여부

## 5.7 Ontology Registry

MVP 기능:

- Object type 목록
- Property 목록
- Link type 목록
- Action type 목록
- domain pack 확인
- schema version
- datasource mapping 상태
- read-only preview

초기에는 전체 ontology editor를 만들지 않고 registry와 configuration 중심으로 시작한다.

## 5.8 Development Tools

- demo DB seed
- local record reset
- test account seed
- provider failure simulation
- template reset
- Gold scenario load

production에서는 route 자체를 등록하지 않거나 강하게 차단한다.

---

# 6. Ontology Core 데이터 모델

## 6.1 최소 공통 모델

### ObjectType

```json
{
  "id": "equipment",
  "display_name": "Equipment",
  "properties": [],
  "interfaces": [],
  "domain_pack": "manufacturing"
}
```

### Object

```json
{
  "id": "M-014",
  "object_type": "equipment",
  "properties": {},
  "source_refs": [],
  "version": 1
}
```

### LinkType

```json
{
  "id": "assigned_to",
  "source_type": "risk_event",
  "target_type": "user"
}
```

### Link

```json
{
  "id": "link-001",
  "link_type": "assigned_to",
  "source_id": "event-002",
  "target_id": "engineer-001"
}
```

### ActionType

```json
{
  "id": "assign_inspection",
  "parameters": [],
  "submission_policy": [],
  "effects": []
}
```

## 6.2 현재 제조 데이터 mapping

| 현재 개념 | Ontology 개념 |
|---|---|
| equipment fixture | `Equipment` object |
| Gold scenario event | `RiskEvent` object |
| sensor observation | `Observation` object 또는 time-series property |
| Evidence Package | `EvidencePackage` object |
| decision | `Decision` object |
| note | `ActivityNote` object |
| checklist | `InspectionTask` object |
| model run | `ModelRun` object |
| report | `GeneratedReport` object |

## 6.3 Action-first write 원칙

사용자가 object property를 직접 임의 수정하지 않는다.

예:

- `AssignInspection`
- `AcknowledgeRisk`
- `SubmitInspectionResult`
- `EscalateEvent`
- `ApproveModelRelease`
- `PublishDashboardTemplate`

각 Action은:

- parameter schema
- permission
- validation
- side effect
- audit
- idempotency

를 가진다.

---

# 7. Dashboard·Tab·Board 데이터 모델

## 7.1 DashboardTemplate

조직 또는 역할의 기본값이다.

필드:

```text
id
name
organization_id
workspace_id
role_code
version
status: draft|published|archived
mandatory_board_ids
customization_policy
created_by
published_at
```

## 7.2 UserDashboardInstance

사용자에게 적용된 template과 personal override를 연결한다.

```text
id
user_id
template_id
template_version
active_tab_id
last_opened_at
preference_version
```

## 7.3 DashboardTab

```text
id
dashboard_id
name
order
icon
visibility_policy
parameter_scope
```

Top tab 사용 예:

```text
운영 개요 | 사건 분석 | 점검 현황 | 품질·감사 | 모델 검증
```

사용자는 권한과 역할에 따라 일부 탭만 본다.

## 7.4 BoardDefinition

재사용 가능한 board type이다.

```text
id
type
category
display_name
input_schema
output_schema
supported_object_types
supported_actions
parameter_capabilities
cross_filter_capabilities
allowed_roles
```

## 7.5 BoardInstance

대시보드에 실제 배치된 board이다.

```text
id
board_definition_id
tab_id
title
query_binding
parameter_binding
x
y
width
height
order
required
collapsible
visibility_policy
```

## 7.6 UserBoardOverride

```text
user_id
board_instance_id
hidden
custom_title
x
y
width
height
order
collapsed
```

## 7.7 SavedView

```text
id
user_id
dashboard_id
name
parameter_values
filter_state
selection_state
active_tab
is_default
shared_scope
```

## 7.8 SessionOverride

브라우저 세션 동안만 유지된다.

- 현재 parameter
- chart selection
- drill-down path
- expanded board
- temporary sorting

명시적으로 `현재 보기 저장`을 누르면 SavedView로 전환한다.

---

# 8. Palantir 벤치마크를 반영한 화면 구조

## 8.1 Global header

상단 고정:

- Ontology Dashboard logo
- organization/workspace selector
- global object search
- notification
- help
- user profile

## 8.2 Dashboard tab bar

프로젝트 목록을 좌측에 길게 표시하는 현재 구조를 축소하고, 대시보드·업무 view는 상단 탭으로 전환한다.

이유:

- 현재 작업 맥락이 명확함
- 탭 간 이동이 빠름
- board를 다른 탭으로 이동시키기 쉬움
- 역할별 default view를 template로 표현하기 쉬움
- 사용자의 개인 탭을 저장하기 쉬움

## 8.3 Left contextual panel

좌측 패널은 다음 중 현재 mode에 필요한 내용을 표시한다.

### View mode

- Parameters
- Filters
- Saved views
- Ontology object context
- Related objects
- Assigned tasks

### Personal edit mode

- Board catalog
- Suggested boards
- Hidden boards
- tab list

### FDE·template edit mode

- Object types
- Link types
- Actions
- Board catalog categories
- query binding explorer
- preview role selector

## 8.4 Main canvas

- 12-column responsive grid
- 최대 3개 board per row를 기본값으로 지원
- 1/3, 1/2, 2/3, full width
- drag-and-drop
- board header actions
- inline insert zone
- text board
- empty state suggestion

## 8.5 Right inspector

편집 모드에서만 표시한다.

- Board title
- Data/Ontology binding
- chart type
- aggregation
- parameter mapping
- cross-filter targets
- role visibility
- export policy
- required/optional
- size constraints

첨부된 Palantir 화면의 차트 설정 우측 패널과 유사한 역할이지만, 원시 column보다 ontology property와 relation을 우선한다.

---

# 9. Board Catalog

## 9.1 카테고리

Palantir의 Suggested·Filter·Visualize·Join·Transform 구조를 참고하되 운영 애플리케이션에 맞춰 다음과 같이 재구성한다.

### Suggested

현재 역할, 탭, object type, 선택 상태에 맞는 추천 board.

### Observe

- KPI
- Status summary
- Object list
- Table
- Timeline
- Time series
- Distribution
- Map

### Explore

- Object details
- Relationship graph
- Linked object list
- Drill-down table
- Compare objects

### Explain

- Evidence
- Factor contribution
- Data quality
- Model explanation
- Generated narrative

### Act

- Assignment
- Checklist
- Approval
- Escalation
- Action form
- Comment·handoff

### Audit

- Lineage
- Version history
- Activity timeline
- Access log
- Export checkpoint

### Build

FDE·data scientist에게만 노출:

- Filter
- Join
- Transform
- Derive property
- Query result
- Model diagnostics
- Parameter
- Text

## 9.2 기존 UI Block migration

| 현재 Block | 새 Board |
|---|---|
| `StatusSummary` | `status-summary` |
| `RiskKpi` | `kpi` |
| `PriorityList` | `object-priority-list` |
| `ImpactSummary` | `impact-summary` |
| `ManagerDecisionCard` | `action-panel` |
| `SensorLineChart` | `time-series` |
| `AnomalyTimeline` | `event-timeline` |
| `FactorContribution` | `evidence-contribution` |
| `EvidenceTable` | `evidence-table` |
| `RecommendedActions` | `action-recommendations` |
| `EngineerChecklist` | `task-checklist` |
| `DataQualityWarning` | `data-quality` |
| `ModelDetails` | `model-diagnostics` |
| `ConversationThread` | `assistant-thread` |

---

# 10. 파라미터·필터·상호작용

## 10.1 Parameter definition

```text
id
name
type
allowed_values
source_query
default_value
scope: dashboard|tab|board
persistence: session|saved_view|user_default
```

예:

- 기간
- 조직
- 공장·라인
- object type
- status
- owner
- model version

## 10.2 Inline parameter

Board 제목, text board와 dashboard 제목에서 parameter를 참조한다.

```text
${workspace.name}의 ${date_range} 운영 현황
```

## 10.3 Chart-to-chart filtering

Board selection event:

```json
{
  "source_board_id": "risk-by-line",
  "selection": {
    "object_type": "ProductionLine",
    "object_ids": ["LINE-02"]
  }
}
```

대상 board는 등록된 dependency graph를 따라 갱신한다.

UI에는 `이 선택이 3개 보드에 영향을 줍니다`와 같은 설명을 표시한다.

## 10.4 임시 상태와 저장 상태

Palantir Contour viewer override는 reload 후 유지되지 않는 구조다. Ontology Dashboard에서는 이를 확장한다.

- 기본: session override
- `현재 보기 저장`: SavedView 생성
- `내 기본 화면으로 저장`: user default 갱신
- `조직 template로 게시`: 관리자·FDE 권한 필요

---

# 11. 역할별 Default View

## 11.1 임원 Viewer

Tabs:

```text
Executive Overview | Risk Trend | Response Status | Business Impact
```

Default boards:

- 전체 위험 KPI
- 조직·workspace별 상태
- 영향 추세
- 중대 미조치 사건
- 대응 완료율
- 주요 변화 narrative
- drill-down link

개인화:

- 기본 기간
- 관심 조직·project
- KPI 순서
- 보고용 saved view

## 11.2 운영 매니저

Tabs:

```text
Priority | Assignments | Escalations | History
```

Default boards:

- 우선순위 object list
- 미배정·기한 초과
- 선택 사건 상태
- 생산·사업 영향
- 담당자·기한 Action
- 핵심 Evidence
- 보고 진행 상태

## 11.3 도메인 엔지니어

Tabs:

```text
My Workspace | Analysis | Procedures | Reports
```

Default boards:

- 담당 object
- 고정 핵심 signal
- 시계열
- 이상 구간
- Evidence
- 관련 object·history
- SOP
- 점검 계획
- manager handoff

## 11.4 현장 작업자

Tabs:

```text
My Tasks | In Progress | Completed
```

Default boards:

- 배정 작업
- object 위치·식별
- 안전 안내
- 단계별 checklist
- 측정·사진·메모
- 완료·문제 발견 Action

모바일 우선으로 별도 responsive profile을 둔다.

## 11.5 품질·감사 Viewer

Tabs:

```text
Audit Queue | Event Reconstruction | Evidence | Exports
```

Default boards:

- 검토 대기 사건
- 사건 timeline
- input·model·policy version
- Evidence→Report trace
- 사용자 Action history
- 예외·누락
- audit package export

## 11.6 데이터 사이언티스트

Tabs:

```text
Model Health | Data Quality | Errors | Releases
```

Default boards:

- model·dataset version
- AP·Precision·Recall·F1
- threshold cost
- false positive·negative slice
- drift
- schema anomalies
- explanation stability
- Gold regression
- release approval request

## 11.7 FDE

Tabs:

```text
Customer Workspace | Ontology | Integrations | Templates | Diagnostics
```

Default boards:

- customer objective·workflow map
- object·link type inventory
- datasource mapping status
- integration health
- role template preview
- usage·error diagnostics
- feature flags
- deployment checklist

FDE workflow:

```text
customer problem
→ object/link/action model
→ data mapping
→ board composition
→ role preview
→ customer validation
→ publish request
→ observe usage
```

---

# 12. 공유·전체화면·내보내기

## 12.1 공유 링크

공유 링크에 포함 가능한 것:

- dashboard ID
- active tab
- saved view ID
- allowed parameter values
- selected object IDs

보안:

- 링크가 권한을 부여하지 않음
- 수신자는 동일한 object access 정책을 통과해야 함
- 민감 parameter는 URL plaintext 대신 saved state token 사용
- 만료일 선택

## 12.2 전체화면

- board 단위 전체화면
- 좌우 화살표로 board 이동
- presentation mode
- parameter context 유지
- 민감 정보 표시 정책 유지

## 12.3 PDF·CSV·JSON export

- 현재 filter·selection 반영
- export metadata 포함
- 생성 사용자·시간·dashboard version
- Evidence source reference
- 감사 역할은 export checkpoint를 요구할 수 있음
- export 자체를 audit log에 기록

---

# 13. Personalization 저장 정책

## 13.1 저장 대상

로그인 후 복원:

- 마지막 workspace
- 마지막 dashboard
- active tab
- tab 순서
- board 순서
- board 크기
- board 표시·숨김
- collapsed state
- 기본 기간
- saved filters
- favorite objects
- preferred view

## 13.2 저장하지 않는 항목

기본적으로 session only:

- 일시적인 chart selection
- hover 상태
- 임시 drill-down
- 아직 저장하지 않은 parameter override
- 임시 전체화면

## 13.3 Template update merge

새 역할 template version이 게시됐을 때:

1. mandatory board 추가
2. 제거된 board override 정리
3. 사용자 위치·크기 override 최대한 보존
4. 충돌이 있으면 `새 기본 화면 적용` 안내
5. 사용자는 `내 설정 유지`, `새 기본값으로 재설정`, `비교` 선택

## 13.4 Reset 개념 분리

- `역할 기본 화면으로 복원`: 사용자 preference만 삭제
- `현재 보기 초기화`: session override만 삭제
- `개발 데이터 초기화`: 관리자·CLI 전용
- `운영 기록 삭제`: 일반 기능으로 제공하지 않음

---

# 14. API 확장 계획

## 14.1 Auth

```text
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
POST /api/auth/refresh
GET  /api/auth/me
POST /api/auth/change-password
```

## 14.2 Admin

```text
GET  /api/admin/users
POST /api/admin/users/{id}/approve
POST /api/admin/users/{id}/disable
PUT  /api/admin/users/{id}/roles
PUT  /api/admin/users/{id}/scopes
GET  /api/admin/roles
GET  /api/admin/permissions
GET  /api/admin/audit
```

## 14.3 Ontology

```text
GET /api/ontology/object-types
GET /api/ontology/object-types/{id}
GET /api/ontology/objects
GET /api/ontology/objects/{type}/{id}
GET /api/ontology/objects/{type}/{id}/links
GET /api/ontology/action-types
POST /api/ontology/actions/{action_type}/apply
```

## 14.4 Dashboard

```text
GET  /api/dashboards
GET  /api/dashboards/{id}
GET  /api/dashboards/{id}/resolved
POST /api/dashboards/{id}/saved-views
PUT  /api/dashboards/{id}/preferences
DELETE /api/dashboards/{id}/preferences
GET  /api/boards/catalog
POST /api/dashboards/{id}/boards
PUT  /api/dashboards/{id}/boards/{board_id}
POST /api/dashboards/{id}/share-links
POST /api/dashboards/{id}/exports
```

## 14.5 Template

```text
GET  /api/admin/dashboard-templates
POST /api/admin/dashboard-templates
POST /api/admin/dashboard-templates/{id}/preview
POST /api/admin/dashboard-templates/{id}/publish
POST /api/admin/dashboard-templates/{id}/rollback
```

---

# 15. 데이터베이스 계획

## 15.1 MVP persistence

현재 SQLite를 유지하되 migration framework를 추가한다.

필수 테이블:

```text
organizations
users
password_credentials
sessions
roles
permissions
role_permissions
user_roles
resource_scopes
user_scopes
workspaces
projects
ontology_object_types
ontology_link_types
ontology_action_types
dashboard_templates
dashboard_template_versions
dashboard_tabs
board_definitions
board_instances
user_dashboard_instances
user_board_overrides
saved_views
share_links
export_jobs
audit_log
```

## 15.2 Production 전환

- PostgreSQL
- Redis session·rate limit 선택
- object data는 adapter 또는 graph/search store
- migration: Alembic
- backup·retention
- row-level policy

---

# 16. Frontend routing 계획

```text
/
├── /login
├── /register
├── /pending
├── /app
│   ├── /workspaces/:workspaceId
│   ├── /dashboards/:dashboardId
│   ├── /objects/:objectType/:objectId
│   ├── /tasks
│   └── /fde
└── /admin
    ├── /users
    ├── /roles
    ├── /workspaces
    ├── /templates
    ├── /boards
    ├── /ontology
    ├── /integrations
    └── /audit
```

Frontend shell:

- `UserAppShell`
- `AdminAppShell`
- `FDEWorkbenchShell`
- `AuthShell`

---

# 17. 단계별 구현 순서

## 16단계. 제품 reframe와 domain-neutral contract

- 구현 상태: **완료 (2026-08-01)**

### 구현

- UI 표시명 `Ontology Dashboard`
- 기존 제조 기능을 `manufacturing` domain pack으로 명시
- domain-neutral Object·Link·Action contract
- 기존 Evidence schema adapter
- README·architecture 갱신

### 완료 조건

- 기존 Gold 8개 통과
- UI에서 제조 전용 제품명 제거
- 제조 demo workspace 선택 가능
- 현재 기능이 domain pack을 통해 동일하게 동작

---

## 17단계. 인증·회원가입·로그인

- 구현 상태: **완료 (2026-08-01)**

### 구현

- user·credential·session schema
- Argon2id hash
- register·login·logout·me
- HttpOnly cookie
- pending approval
- auth route guard
- test account seed
- login·register 화면

### 완료 조건

- 8개 test account 로그인 가능
- 잘못된 비밀번호 차단
- disabled·pending 사용자 차단
- logout 후 protected API 접근 불가
- production에서 demo seed 비활성

---

## 18단계. RBAC·resource scope·관리자 페이지

- 구현 상태: **완료 (2026-08-01)**

### 구현

- role·permission·scope schema
- `/admin` shell
- user 승인·비활성화
- 역할·workspace scope 지정
- 관리자 audit
- 일반 사용자 reset API 미노출 유지

### 완료 조건

- 관리자만 `/admin` 접근
- 일반 사용자가 admin API 호출 시 403
- 역할 변경이 다음 로그인부터 반영
- resource scope 밖 object가 API와 UI에서 모두 보이지 않음

---

## 19단계. Ontology registry와 제조 domain adapter

- 구현 상태: **완료 (2026-08-01)**

### 구현

- ObjectType·LinkType·ActionType registry
- Equipment·RiskEvent·Evidence·Inspection mapping
- object query API
- relation traversal
- Action execution contract

### 완료 조건

- 기존 사건을 ontology object로 조회
- Equipment→RiskEvent→Inspection link 탐색
- 현재 decision·note workflow를 Action으로 실행
- 모든 Action audit 기록

---

## 20단계. Dashboard template·tab·board persistence

- 구현 상태: **완료 (2026-08-01)**

### 구현

- template·version
- dashboard tab
- board definition·instance
- role default template seed
- resolved dashboard API
- mandatory board policy

### 완료 조건

- 역할별 서로 다른 default tabs·boards
- template version 조회
- mandatory board 제거 차단
- template preview API

---

## 21단계. 새 Dashboard shell UI

- 구현 상태: **완료 (2026-08-01)**

### 구현

- 상단 workspace selector
- 상단 dashboard tabs
- 좌측 contextual panel
- main board canvas
- right inspector
- view·edit mode
- 현재 좌측 설비 사건 목록을 object context 또는 board로 이동

### 완료 조건

- 첨부 Palantir 예시처럼 tabs로 대시보드 구분
- 좌측 panel이 parameter·filter·object context에 사용
- board full width·1/2·1/3 layout
- responsive 동작

---

## 22단계. 개인화 저장과 복원

- 구현 상태: **완료 (2026-08-01)**

### 구현

- drag-and-drop order
- resize
- hide/show
- personal tab order
- active tab 저장
- user board override
- saved view
- role default restore

### 완료 조건

- 로그아웃 후 다시 로그인해도 개인 설정 복원
- 다른 사용자의 화면에는 영향 없음
- session override는 저장 전까지 영구 반영되지 않음
- 역할 template update와 user override merge

---

## 23단계. Board catalog와 편집 UX

- 구현 상태: **완료 (2026-08-01)**

### 구현

- Suggested·Observe·Explore·Explain·Act·Audit·Build
- board 검색
- inline insertion
- 특정 tab에 추가
- 새 tab 생성
- text board
- board settings inspector
- FDE·admin template editor

### 완료 조건

- 허용 role에 맞는 board만 검색됨
- board binding schema validation
- 임의 HTML·script 불가
- board 추가·삭제·복제·이동 가능

---

## 24단계. Parameter·cross-filter·공유

- 구현 상태: **완료 (2026-08-01)**

### 구현

- dashboard·tab·board parameter
- inline parameter text
- chart selection event
- dependency graph
- affected boards 표시
- share link
- board fullscreen

### 완료 조건

- 선택이 등록된 downstream board에만 반영
- 영향을 받는 board 수 표시
- 공유 링크가 parameter state 복원
- 권한 없는 object는 공유 링크로도 조회 불가

---

## 25단계. 역할 확장 1 — 임원 Viewer

- 구현 상태: **완료 (2026-08-01)**

### 구현

- executive template
- 조직·workspace aggregate
- 위험·영향·추세
- 미조치 중요 사건
- 보고 saved view

### 완료 조건

- 세부 센서 없이도 조직 위험 이해
- drill-down 가능
- 사업 영향의 추정값·가정 표시

---

## 26단계. 역할 확장 2 — 품질·감사 Viewer

- 구현 상태: **완료 (2026-08-01)**

### 구현

- 사건 재구성
- input·model·policy version
- Evidence→Report trace
- action history
- export checkpoint

### 완료 조건

- 특정 판단을 원본 Evidence까지 추적
- 과거 version snapshot 유지
- audit export 기록

---

## 27단계. 역할 확장 3 — 현장 작업자

- 구현 상태: **완료 (2026-08-01)**

### 구현

- mobile task view
- 안전·위치
- checklist
- measurement·photo metadata
- 완료·문제 발견·작업 불가 Action

### 완료 조건

- 작은 화면에서 작업 완료 가능
- offline queue는 후속 옵션으로 설계
- engineer handoff 완료

---

## 28단계. 역할 확장 4 — FDE Workbench

- 구현 상태: **완료 (2026-08-01)**

### 구현

- customer workspace overview
- ontology registry
- integration health
- role preview
- dashboard template builder
- deployment checklist
- diagnostic events

### 완료 조건

- FDE가 고객 workflow를 template 초안으로 변환
- admin 권한 없이 user credential·secret 접근 불가
- publish는 승인 workflow 필요

---

## 29단계. 데이터 사이언티스트 Console

- 구현 상태: **완료 (2026-08-01)**

### 구현

- model·dataset version
- metrics·threshold cost
- slice·error analysis
- drift·schema anomaly
- Gold regression
- release candidate·approval request

### 완료 조건

- 일반 운영 대시보드와 분리
- model release가 Action과 승인 기록으로 남음
- 운영 threshold와 학습 지표 혼합 금지

---

## 30단계. LLM·Ontology Planner 고도화

- 구현 상태: **완료 (2026-08-01)**

### 구현

- 자연어 → object query intent
- 역할별 board recommendation
- dashboard draft generation for FDE
- grounded narrative
- user preference-aware suggestion
- schema·permission validation

### 완료 조건

- LLM은 board catalog 밖 type 생성 불가
- object permission을 우회하는 query 불가
- 사용자 설정은 제안 후 승인해야 저장
- provider 장애 시 기존 dashboard 유지

---

## 31단계. Export·보안·성능·릴리스

- 구현 상태: **완료 (2026-08-01)**

### 구현

- PDF·CSV·JSON
- export checkpoint
- rate limit
- CSRF
- session security
- permission regression
- template migration tests
- dashboard performance test
- E2E role matrix

### 완료 조건

- 모든 test role login E2E
- 사용자 A 설정이 사용자 B에 노출되지 않음
- admin·FDE 권한 분리 테스트
- share link permission 테스트
- 10개 이상의 board가 있는 dashboard 성능 기준 충족

---

# 18. 테스트 전략

## 18.1 Auth

- signup pending
- admin approve
- login success/failure
- disabled user
- session expiry
- CSRF
- password hash 검증

## 18.2 Permission matrix

모든 role에 대해:

- route 접근
- API 접근
- object type 접근
- object instance scope
- Action apply
- template edit
- export

## 18.3 Personalization

- 사용자별 tab order
- board size
- hidden board
- saved view
- role default restore
- template migration
- multi-device last-write 정책

## 18.4 Dashboard interaction

- board add
- tab move
- resize
- inline text
- parameter
- cross-filter
- fullscreen
- share link
- export

## 18.5 Ontology

- object·link integrity
- Action validation
- permission-aware traversal
- audit event
- domain pack isolation

---

# 19. MVP 범위와 이후 범위

## 이번 추가 MVP에 반드시 포함

- Ontology Dashboard brand
- 회원가입·로그인
- test accounts
- 관리자 페이지
- RBAC·workspace scope
- 역할 default dashboard
- top tabs
- board 순서·크기 개인 저장
- saved filters/views
- 임원·품질감사·현장작업자·FDE·데이터사이언티스트 역할
- 기존 매니저·엔지니어 유지
- board catalog
- parameter·cross-filter
- FDE template preview

## 후속으로 미룰 수 있음

- 기업 SSO
- 실시간 공동 편집
- 복잡한 visual query builder
- arbitrary code board
- full ontology schema editor
- offline mobile sync
- 고객별 custom domain pack marketplace
- scheduled PDF email
- multi-region deployment
- ABAC policy language UI

---

# 20. 주요 기술 위험과 대응

## 역할 explosion

대응:

- 역할과 resource scope 분리
- permission bundle 사용
- user별 임의 권한 최소화

## 사용자의 과도한 customization

대응:

- mandatory board
- allowed customization policy
- 역할 기본값 복원
- admin preview

## template update 충돌

대응:

- immutable template version
- override merge
- conflict preview
- rollback

## LLM이 잘못된 dashboard를 생성

대응:

- board registry whitelist
- schema validation
- permission validation
- draft only
- human publish approval

## ontology를 너무 크게 먼저 설계

대응:

- 기존 manufacturing pack으로 vertical validation
- 최소 공통 Object·Link·Action부터 시작
- 고객 workflow에서 필요한 type만 확장

## 관리자 페이지가 사용자 앱과 혼합

대응:

- 별도 route·shell
- 별도 navigation
- 별도 permission
- production development tools 비활성

---

# 21. GitHub 저장소 관련 결정

아직 독립 GitHub 저장소를 만들지 않았다면 권장 이름:

```text
oosuhada/ontology-dashboard
```

설명:

```text
Ontology-aware role-based dashboards with persistent personal views and governed actions
```

현재 `Factory Signal Board` 이름은 README에서 제조 demo pack 이름으로 보존할 수 있다.

---

# 22. 첫 구현 세션 권장 범위

한 세션에서 전체 역할 화면까지 바로 만들지 않는다.

첫 세션 목표:

1. 현재 tests baseline 확인
2. 제품 표시명 `Ontology Dashboard`
3. auth DB schema
4. test accounts seed
5. login·register 화면
6. protected `/app`와 `/admin`
7. 역할별 redirect
8. 관리자 Users 목록 read-only
9. 기존 manager·engineer dashboard를 로그인 후 표시
10. release gate 통과

다음 세션부터 dashboard template과 personalization을 구현한다.
