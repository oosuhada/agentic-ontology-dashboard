# Ontology Dashboard MVP API 명세서

- 상태: 멘토링 합의 기반 MVP 구현 계약
- 적용 화면: `Overview`, `Objects`, `Operations`, `Executive Report View`
- 적용 데이터: Canonical V3.1
- 핵심 사용자: 생산 관리자, 현장 담당자
- 기준 프로젝트: `manufacturing-demo-project`
- 작성일: 2026-08-06

## 1. 문서 목적

이 문서는 [`mvp-scope-and-screen-specification.md`](./mvp-scope-and-screen-specification.md)에 정의된 네 개 MVP 화면이 백엔드와 어떤 계약으로 통신해야 하는지를 고정한다.

다음 세 가지를 구분한다.

1. 현재 코드에 이미 존재하며 그대로 재사용할 API
2. 현재 API를 사용하되 프론트엔드 조합 규칙을 고정할 부분
3. 화면 명세를 완성하기 위해 추가 구현이 필요한 API gap

MVP 구현자는 이 문서를 기준으로 화면마다 임의의 API 조합이나 임의 필드 해석을 추가하지 않는다.

## 2. API 설계 원칙

### 2.1 Project와 Workspace 범위

모든 조회와 변경은 다음 범위를 벗어나지 않아야 한다.

```text
Organization
└── Project
    └── Workspace
        ├── Dataset Version
        ├── Ontology Objects
        ├── Risk Events
        ├── Decisions
        └── Reports
```

Event API는 활성 Project와 요청 대상 Event의 Project가 일치해야 한다.

### 2.2 원본 컬럼 직접 해석 금지

프론트엔드는 `Tool wear`, `Torque`, `Machine failure`와 같은 원본 컬럼을 직접 업무 의미로 변환하지 않는다.

```text
Canonical V3.1
→ Backend projection
→ MVP API contract
→ 화면 렌더링
```

### 2.3 조회와 변경 분리

- GET은 상태를 변경하지 않는다.
- 결정, 메모, 점검 결과와 담당자 변경은 명시적인 write API를 사용한다.
- write API는 CSRF와 권한 검증을 통과해야 한다.
- Action은 `idempotency_key`로 중복 실행을 막는다.

### 2.4 데이터 품질 보류

데이터 품질 문제는 서버 오류가 아니다. 다음 상태는 `200 OK` 응답 안에서 표현한다.

```text
status = data_quality_hold
failure_probability = null
recommended_decision = hold_for_data_check
```

### 2.5 Analysis 제외

다음 API 군은 기존 구현을 유지하되 네 개 MVP 화면의 필수 호출에 포함하지 않는다.

- `/api/analyses`
- `/api/analysis-runs`
- Analysis node result API
- Graph·Canvas authoring API

## 3. 공통 통신 규칙

### 3.1 Base URL

```text
/api
```

### 3.2 인증과 활성 Project

- 세션 쿠키 인증을 사용한다.
- `GET /api/auth/me`로 사용자, 역할, 권한과 활성 Project를 확인한다.
- 대상 Project가 활성화되지 않았으면 `PATCH /api/auth/active-project`를 호출한다.

### 3.3 Content-Type

```http
Content-Type: application/json
Accept: application/json
```

### 3.4 날짜와 시간

- timestamp는 ISO 8601 문자열을 사용한다.
- 저장 기준은 UTC를 권장한다.
- 화면 표시만 사용자 timezone으로 변환한다.
- 정비일처럼 날짜만 의미하는 값은 `YYYY-MM-DD`를 허용한다.

### 3.5 수치와 단위

| 항목 | API 값 | 화면 표시 |
|---|---:|---|
| 고장 확률 | `0.0`–`1.0` | `0%`–`100%` |
| Downtime | 분 단위 정수 | 분 또는 시간 환산 |
| 온도 | Kelvin | 단위 표시 또는 명시적 변환 |
| 회전 속도 | rpm | rpm |
| 토크 | N·m | N·m |
| 공구 마모 | minute | 분 |

### 3.6 공통 오류 응답

```json
{
  "error": {
    "code": "permission_denied",
    "message": "이 작업을 수행할 권한이 없습니다."
  }
}
```

구현에 따라 `detail` envelope가 사용되더라도 프론트엔드는 최종적으로 `code`와 `message`를 동일하게 추출한다.

### 3.7 공통 오류 코드

| HTTP | 코드 | 의미 | 화면 처리 |
|---:|---|---|---|
| 401 | `authentication_required` | 로그인 필요 | 로그인 화면 이동 |
| 403 | `permission_denied` | 권한 없음 | 기능 단위 비활성화 |
| 403 | `project_scope_denied` | Project 범위 밖 | 접근 불가 안내 |
| 404 | `not_found` | 대상 없음 | Empty 또는 삭제 안내 |
| 409 | `active_project_mismatch` | 활성 Project 불일치 | 활성화 후 재시도 |
| 409 | `report_revision_conflict` | 보고서 revision 충돌 | 최신본 새로고침 |
| 422 | `project_action_not_configured` | Action mapping 미게시 | 조회 유지, Action 차단 |
| 422 | validation error | schema 위반 | 필드별 오류 표시 |
| 500 | `internal_error` | 서버 오류 | 재시도와 오류 안내 |

## 4. 역할과 권한

### 4.1 MVP 사용자 그룹

| MVP 사용자 | 실제 역할 코드 | 기본 화면 |
|---|---|---|
| 생산 관리자 | `process_manager` | Overview |
| 현장 담당자 | `process_engineer` | Objects 또는 Operations |
| 현장 담당자 | `maintenance_technician` | Objects 또는 Operations |
| 임원 보고서 독자 | `executive_viewer` | Executive Report View |

### 4.2 최소 권한

| 권한 | 목적 |
|---|---|
| `app.access` | Project·Workspace 조회 |
| `events.read` | Event·Evidence·Activity·Report 조회 |
| `events.decision` | 운영 판단 저장 |
| `events.note` | 점검 메모와 현장 결과 저장 |
| `ontology.registry.read` | Object·Action schema 조회 |
| `ontology.objects.read` | Object·관계 조회 |
| `ontology.actions.execute` | 허용된 Ontology Action 실행 |
| `dashboards.read` | 역할별 Dashboard 조회 |
| `exports.create` | 보고서 Export 생성 |

권한이 없는 기능은 화면 전체를 실패시키지 않는다.

## 5. 화면별 호출 요약

| 화면 | 필수 API | 선택 API |
|---|---|---|
| Overview | Project, Workspaces, Project Events | Event detail, Evidence |
| Objects | Ontology registry, Object query | Object detail, links, action history |
| Operations | Project Events, Event detail, Activity | Evidence, Decision, Note, Assignment |
| Executive Report | Project Events, generated report, report draft | Export |

## 6. 공통 Project Context API

### 6.1 현재 사용자

```http
GET /api/auth/me
```

응답 핵심 필드:

```json
{
  "user_id": "user-process-manager",
  "roles": ["process_manager"],
  "permissions": ["app.access", "events.read", "events.decision"],
  "workspace_scopes": ["manufacturing-demo"],
  "project_scopes": ["manufacturing-demo-project"],
  "active_project_id": "manufacturing-demo-project",
  "active_project_roles": ["process_manager"]
}
```

### 6.2 활성 Project 변경

```http
PATCH /api/auth/active-project
```

요청:

```json
{
  "project_id": "manufacturing-demo-project"
}
```

필요 조건: 로그인, CSRF, Project scope

### 6.3 Project 조회

```http
GET /api/projects/{project_id}
```

현재 상태: 구현됨  
필요 권한: `app.access`

### 6.4 Workspace 목록

```http
GET /api/projects/{project_id}/workspaces
```

현재 상태: 구현됨  
필요 권한: `app.access`

## 7. Overview API

### 7.1 Project Event 목록

```http
GET /api/projects/{project_id}/events
```

현재 상태: 구현됨  
필요 권한: `events.read`

필요 조건:

- 대상 Project가 사용자 scope에 포함되어야 한다.
- `active_project_id`가 URL의 `project_id`와 일치해야 한다.

응답:

```json
{
  "items": [
    {
      "event_id": "GS-004",
      "scenario_id": "GS-004",
      "equipment": {
        "equipment_id": "M-014",
        "display_name": "절삭 설비 M-014",
        "line": "Line-02",
        "criticality": "high",
        "assigned_engineer": "박지민",
        "last_maintenance_date": "2026-07-29",
        "estimated_downtime_minutes": 120,
        "spare_part_available": false
      },
      "status": "critical",
      "failure_probability": 0.91,
      "confidence": "high",
      "predicted_failure_type": "failure_risk",
      "recommended_decision": "review_shutdown",
      "observed_at": "2026-08-06T01:30:00Z",
      "dataset_version_id": "dsv-canonical-v3-1",
      "ontology_object_id": "risk_event:GS-004"
    }
  ]
}
```

### 7.2 KPI 계산

MVP에서는 별도 aggregate endpoint 없이 Event 목록에서 계산한다.

| KPI | 계산식 |
|---|---|
| Critical | `status == critical` 수 |
| Warning | `status == warning` 수 |
| Average risk | null이 아닌 확률 평균 |
| Downtime impact | Event별 예상 중단 시간 합계 |

규칙:

- null 확률은 평균 분모에서 제외한다.
- `data_quality_hold`는 Critical·Warning에 포함하지 않는다.
- `event_id`로 중복 제거한다.
- 기본 정렬은 상태, 확률, 중요도, 관측 시각 순이다.

### 7.3 향후 aggregate API

다음 endpoint는 대규모 데이터 확장용이며 MVP P0 필수 구현이 아니다.

```http
GET /api/projects/{project_id}/overview?workspace_id={workspace_id}&dataset_version_id={dataset_version_id}
```

## 8. Objects API

### 8.1 Ontology registry

```http
GET /api/ontology/registry
```

현재 상태: 구현됨  
필요 권한: `ontology.registry.read`

사용 목적:

- Object type
- Property label과 unit
- Link type
- Action type schema

### 8.2 Object 목록

```http
GET /api/ontology/objects
```

현재 상태: 기본 조회 구현됨, MVP 필터 gap 존재  
필요 권한: `ontology.objects.read`

현재 query:

| 이름 | 타입 | 필수 | 기본값 |
|---|---|---:|---:|
| `workspace_id` | string | 예 | - |
| `object_type` | string | 아니오 | 전체 |
| `dataset_version_id` | string | 아니오 | 활성 버전 |
| `q` | string | 아니오 | 없음 |
| `offset` | integer | 아니오 | `0` |
| `limit` | integer | 아니오 | `100`, 최대 `200` |

MVP 목표 query:

| 이름 | 상태 | 설명 |
|---|---|---|
| `status` | 추가 필요 | 위험 상태 |
| `line` | 추가 필요 | 생산 라인 |
| `risk_gte` | 추가 필요 | 최소 고장 확률 |
| `criticality` | 추가 필요 | 설비 중요도 |
| `assigned_engineer` | 추가 필요 | 담당자 |
| `sort` | 추가 필요 | 정렬 필드 |
| `order` | 추가 필요 | `asc`, `desc` |

목표 요청:

```http
GET /api/ontology/objects?workspace_id=manufacturing-demo&object_type=equipment&dataset_version_id=dsv-canonical-v3-1&line=Line-02&risk_gte=0.6&offset=0&limit=50
```

응답:

```json
{
  "items": [
    {
      "id": "equipment:M-014",
      "object_type": "equipment",
      "workspace_id": "manufacturing-demo",
      "properties": {
        "display_name": "절삭 설비 M-014",
        "equipment_id": "M-014",
        "line": "Line-02",
        "criticality": "high",
        "assigned_engineer": "박지민",
        "status": "critical",
        "failure_probability": 0.91,
        "dataset_version_id": "dsv-canonical-v3-1"
      },
      "source_refs": ["canonical://v3.1/assets/M-014"],
      "version": 1
    }
  ],
  "total": 1,
  "offset": 0,
  "limit": 50
}
```

### 8.3 Object 상세

```http
GET /api/ontology/objects/{object_id}?workspace_id={workspace_id}&dataset_version_id={dataset_version_id}
```

현재 상태: 구현됨  
필요 권한: `ontology.objects.read`

### 8.4 Object 관계

```http
GET /api/ontology/objects/{object_id}/links
```

현재 상태: 구현됨  
필요 권한: `ontology.objects.read`

MVP에서는 `depth=1`을 기본값으로 사용한다.

### 8.5 Action 이력

```http
GET /api/ontology/objects/{object_id}/action-invocations?workspace_id={workspace_id}
```

현재 상태: 구현됨  
필요 권한: `ontology.objects.read`

## 9. Operations 조회 API

### 9.1 Event 상세

```http
GET /api/events/{event_id}
```

현재 상태: 구현됨  
필요 권한: `events.read`

### 9.2 Evidence

```http
GET /api/events/{event_id}/evidence
```

현재 상태: 구현됨  
필요 권한: `events.read`

응답 핵심 구조:

```json
{
  "evidence_id": "evidence-GS-004",
  "event_id": "GS-004",
  "model": {
    "model_version": "ai4i-random_forest-v1",
    "policy_version": "trained-model-policy-v1",
    "mode": "model"
  },
  "status": "critical",
  "recommended_decision": "review_shutdown",
  "confidence": "high",
  "failure_probability": 0.91,
  "threshold": 0.85,
  "predicted_failure_type": "failure_risk",
  "observation": {},
  "history": [],
  "top_factors": [],
  "data_quality_warnings": [],
  "lineage": {
    "dataset_version_id": "dsv-canonical-v3-1"
  },
  "generated_at": "2026-08-06T01:31:00Z"
}
```

### 9.3 Activity

```http
GET /api/events/{event_id}/activity
```

현재 상태: 구현됨  
필요 권한: `events.read`

MVP 표준 응답:

```json
{
  "items": [
    {
      "id": "activity-001",
      "event_id": "GS-004",
      "action": "request_inspection",
      "actor": "manager@ontology.local",
      "note": "다음 교대 전 점검 요청",
      "created_at": "2026-08-06T02:00:00Z"
    }
  ]
}
```

repository가 배열을 직접 반환하면 프론트 adapter에서 `{items}`로 정규화한다.

## 10. Operations 변경 API

### 10.1 운영 결정

```http
POST /api/events/{event_id}/decision
```

현재 상태: 구현됨  
필요 권한: `events.decision`

요청:

```json
{
  "actor": "김현우",
  "decision": "request_inspection",
  "note": "다음 교대 시작 전 공구 상태와 토크 센서를 확인합니다."
}
```

허용 값:

```text
continue_monitoring
request_inspection
review_shutdown
hold_for_data_check
```

`review_shutdown`은 실제 설비 정지 명령이 아니다.

### 10.2 현장 메모

```http
POST /api/events/{event_id}/notes
```

현재 상태: 구현됨  
필요 권한: `events.note`

```json
{
  "actor": "박지민",
  "body": "공구 마모 상태를 확인했고 교체가 필요합니다."
}
```

### 10.3 Ontology Action

```http
POST /api/ontology/actions/invoke
```

현재 상태: 구현됨  
route 권한: `app.access`  
실제 실행 권한: Action type의 `required_permissions`

```json
{
  "action_type": "complete_inspection",
  "object_id": "inspection:GS-004",
  "workspace_id": "manufacturing-demo",
  "parameters": {
    "checklist": ["공구 상태 확인", "토크 센서 확인"],
    "measurements": {
      "torque_nm": 52.4,
      "tool_wear_min": 218
    },
    "note": "교체 권고",
    "location": "Line-02"
  },
  "idempotency_key": "inspection-GS-004-complete-20260806-001"
}
```

### 10.4 담당자 배정 gap

현재 명시적 assignment write API가 없다.

MVP 목표:

```http
POST /api/events/{event_id}/assignment
```

목표 권한: `events.decision`

```json
{
  "assignee_id": "user-process-engineer",
  "assignee_display_name": "박지민",
  "due_at": "2026-08-06T09:00:00+09:00",
  "note": "다음 교대 전 점검"
}
```

구현 원칙:

- 내부적으로 Ontology Action으로 위임할 수 있다.
- Event와 Inspection 또는 Work Order에 동일 assignee가 반영되어야 한다.
- 프론트 local state만 변경하는 구현은 완료로 인정하지 않는다.

## 11. Executive Report API

### 11.1 Grounded Report 생성

```http
POST /api/events/{event_id}/report
```

현재 상태: 구현됨  
필요 권한: `events.read`

요청:

```json
{
  "role": "manager",
  "locale": "ko-KR",
  "use_llm": true
}
```

LLM 장애 시에도 `mode = deterministic_fallback`으로 동일 schema를 반환한다.

### 11.2 공유 Draft 조회

```http
GET /api/reports/draft?workspace_id={workspace_id}&event_id={event_id}&role=manager&locale=ko-KR
```

현재 상태: 구현됨  
필요 권한: `events.read`

Draft가 없으면 다음을 반환한다.

```json
{
  "draft": null
}
```

### 11.3 공유 Draft 저장

```http
PUT /api/reports/draft
```

현재 상태: 구현됨  
필요 권한: `events.note`

```json
{
  "workspace_id": "manufacturing-demo",
  "event_id": "GS-004",
  "role": "manager",
  "locale": "ko-KR",
  "base_revision": 3,
  "headline": "주간 설비 위험 보고",
  "summary": "M-014 점검을 요청했고 결과를 대기 중입니다.",
  "sections": [
    {
      "section_id": "response-status",
      "title": "대응 현황",
      "body": "Line-02 담당자에게 현장 점검을 배정했습니다.",
      "evidence_field_ids": [
        "event_id",
        "equipment.assigned_engineer",
        "recommended_decision"
      ]
    }
  ],
  "content_origin": "edited",
  "source_locale": null,
  "source_revision": null
}
```

### 11.4 Report 조합 규칙

```text
Project Events
+ 선택 Event Grounded Report
+ 선택 Event Shared Draft
+ Event Activity
= Executive Report View
```

우선순위:

1. Draft가 있으면 서술에 사용한다.
2. Draft가 없으면 Grounded Report를 사용한다.
3. 위험 수치와 상태는 최신 Event·Evidence를 사용한다.
4. Draft 숫자가 Evidence와 충돌하면 경고한다.

### 11.5 Export

MVP에서는 V1 Report의 Print CSS를 필수로 사용한다. 서버 PDF Export는 시간 허용 시 연결한다.

필수 조건:

- A4 인쇄 레이아웃
- revision과 발행 시각
- Evidence field reference

## 12. Pagination·검색·버전

### 12.1 Pagination

```json
{
  "items": [],
  "total": 0,
  "offset": 0,
  "limit": 50
}
```

- Object 목록은 pagination 필수다.
- Event 목록은 현재 fixture 규모에서는 전체 반환을 허용한다.

### 12.2 검색

- 대소문자를 구분하지 않는다.
- 설비 ID, 표시 이름, 라인, 담당자를 검색한다.
- 공백 입력은 검색 조건 제거로 처리한다.

### 12.3 Dataset Version

- 네 화면은 동일한 `dataset_version_id`를 사용한다.
- 생략하면 Project 기본 release-ready V3.1을 사용한다.
- 응답에는 실제 선택 버전을 포함한다.
- 서로 다른 버전을 한 화면에서 섞지 않는다.

## 13. Empty·Partial failure·Retry

### 13.1 Empty

| 상황 | 응답 | 화면 |
|---|---|---|
| Event 없음 | `items: []` | 현재 판단할 Event 없음 |
| Object 없음 | `items: [], total: 0` | 필터 초기화 안내 |
| Draft 없음 | `draft: null` | 생성 Report 사용 |
| Activity 없음 | 빈 배열 | 기록된 조치 없음 |

### 13.2 Partial failure

- Overview Event가 성공하면 Evidence 상세 실패로 전체 화면을 막지 않는다.
- Objects 목록이 성공하면 관계 실패로 목록을 막지 않는다.
- Activity 실패 시 Operations 판단 기능은 유지한다.
- Draft 실패 시 Grounded Report fallback을 사용한다.

### 13.3 Retry

- GET만 자동 1회 재시도할 수 있다.
- POST·PUT은 자동 재실행하지 않는다.
- Action은 동일 idempotency key로 사용자 재시도를 허용한다.

## 14. 구현 gap

| ID | Gap | 우선순위 | 완료 기준 |
|---|---|---:|---|
| `MVP-API-GAP-01` | Object 서버 필터 부족 | P1 | line, status, risk, criticality, assignee 필터 |
| `MVP-API-GAP-02` | 담당자 배정 영속 API 없음 | P1 | 저장·조회·Activity 반영 |
| `MVP-API-GAP-03` | Activity envelope 비표준 가능성 | P1 | `{items}` 또는 adapter 고정 |
| `MVP-API-GAP-04` | Report 단일 aggregate API 없음 | P2 | 조합 규칙 테스트로 우선 대체 |
| `MVP-API-GAP-05` | Event pagination 없음 | P3 | 대규모 데이터 도입 시 구현 |

## 15. 화면별 인수 조건

### 15.1 Overview

- `process_manager` 계정으로 403 없이 로드된다.
- Canonical V3.1 Event가 표시된다.
- 품질 보류 Event를 고장으로 집계하지 않는다.
- 선택 Event ID가 다음 화면으로 유지된다.

### 15.2 Objects

- 엔지니어와 정비 기술자가 조회할 수 있다.
- Dataset Version과 source reference를 확인할 수 있다.
- 필터 count와 실제 row 수가 일치한다.
- 관계 실패가 목록 전체 오류로 확산되지 않는다.

### 15.3 Operations

- 생산 관리자는 Decision을 저장한다.
- 현장 담당자는 Note와 점검 결과를 저장한다.
- 변경 결과가 Activity에 나타난다.
- 동일 idempotency key가 중복 기록을 만들지 않는다.

### 15.4 Executive Report

- 임원 Viewer가 읽을 수 있다.
- Draft가 없어도 Generated Report로 로드된다.
- revision을 표시한다.
- 수치가 최신 Event·Evidence와 일치한다.

## 16. 테스트 요구사항

### Backend

- endpoint별 권한 200·403
- active Project mismatch 409
- data quality hold null probability
- Decision enum validation
- Report revision conflict
- Object filter·pagination
- Assignment와 Activity 반영

### Frontend E2E

- 생산 관리자: Overview → Operations → Decision
- 현장 담당자: Objects → Event → 점검 메모
- 임원 Viewer: Report 읽기·인쇄
- 데이터 품질 보류: 확률 `—`, 판단 보류
- 권한 없는 기능: 화면 전체가 아닌 버튼 차단

## 17. 구현 참조

```text
api/ontology_dashboard/routers/projects.py
api/ontology_dashboard/routers/ontology.py
api/ontology_dashboard/routers/manufacturing.py
api/ontology_dashboard/routers/dashboards.py
api/ontology_dashboard/contracts.py
api/ontology_dashboard/dashboard_models.py
api/ontology_dashboard/ontology.py
web/src/api.ts
web/src/types.ts
web/src/features/ontology/types.ts
web/src/features/dashboard/types.ts
web/src/features/blueprint/BlueprintManufacturingApp.tsx
web/src/features/reports/RoleReportWorkbench.tsx
```

## 18. 변경 관리

- endpoint 또는 필드명을 바꾸면 이 문서와 OpenAPI contract를 함께 수정한다.
- 화면 필드 추가 전에 데이터 계약을 먼저 수정한다.
- 새 API 추가 전에 기존 API 조합으로 가능한지 확인한다.
- Analysis와 Commercial V4 API를 MVP 필수 dependency로 추가하지 않는다.
- 구현 완료 후 gap 표를 갱신한다.
