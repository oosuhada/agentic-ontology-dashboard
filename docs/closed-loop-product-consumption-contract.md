# Closed-loop Product/API/UI 소비 계약

## 1. 문서 지위와 목적

이 문서는 Ontology Operations & Closed-loop를 **Product API와 Frontend가 어떻게 소비하는지**를
정의하는 canonical contract다. 상태 머신 자체의 정본은
[`closed-loop-domain-contract.md`](./closed-loop-domain-contract.md)이며, 이 문서는 Domain 상태를
재정의하지 않는다.

Backend Domain과 Product/UI가 서로 다른 상태·역할·Action 의미를 만들지 않도록 저장소 안의
공식 소비 계약으로 유지한다.

문서 정본의 역할은 다음과 같이 나눈다.

| 문서 | canonical 책임 |
|---|---|
| `docs/closed-loop-domain-contract.md` | Closed-loop 객체 경계, 상태 전이, lineage, Domain invariant |
| `docs/closed-loop-product-consumption-contract.md` | 사용자 역할, Product Action, `available_actions`, Event API 소비, 오류, E2E, 구현 소유권 |
| `docs/closed-loop-runtime-overlay-contract.md` | 정비 완료 이후 대상 설비 Overlay와 정비 후 Runtime Prediction handoff |

문서가 충돌하면 Domain 상태 자체는 Domain 계약을, Product/API/UI 표현과 소비 방식은 이
문서를, 정비 완료 이후 Runtime Overlay handoff는 Runtime Overlay 계약을 따른다.

## 2. 핵심 원칙

1. Closed-loop 상태 머신의 canonical owner는 Backend Domain이다.
2. Frontend는 Domain 상태 머신을 재구현하지 않는다.
3. Backend는 role + permission + object state + scope + lineage를 기준으로
   `available_actions`를 계산해 반환한다.
4. 기존 Event API는 key 삭제·rename 없이 additive extension으로 유지한다.
5. Frontend는 Recommendation, WorkOrder, MaintenanceAction 등 운영 객체 ID를 합성하지 않는다.
6. mutation 응답은 Persistence가 확정한 ID와 resulting state를 반환한다.
7. `process_manager`는 시스템 Admin이 아니라 **생산 운영 의사결정자**다.
8. `process_engineer`는 **현장 엔지니어**다.
9. `maintenance_technician`은 승인된 작업을 실제 수행하는 **정비 작업자**다.
10. 핵심 Operations UX는 **현장 엔지니어 → 생산 운영 의사결정자** 흐름이며, 정비가 필요한 경우
    **정비 작업자**가 Closed-loop 실행을 이어간다.

## 3. 역할·표시명 계약

### 3.1 canonical RBAC role code와 legacy view alias를 구분한다

Identity/RBAC의 canonical role code는 다음 세 역할이다.

| RBAC role code | 제품 표시 의미 | 주요 사용자 |
|---|---|---|
| `process_manager` | 생산 운영 의사결정자 | 생산팀장, 공정·생산 관리자, 운영 판단 책임자 |
| `process_engineer` | 현장 엔지니어 | 설비·공정 엔지니어, Evidence/점검·분석 담당자 |
| `maintenance_technician` | 정비 작업자 | 승인된 정비 작업을 수행하는 정비기사·현장 작업자 |

`manager` / `engineer`는 기존 Event Report와 일부 Week 2 UI에서 사용하는 legacy presentation/report
view alias다. Identity/RBAC role code와 동일한 enum으로 문서화하지 않는다. 현재 compatibility mapping은
`process_manager → manager`, `process_engineer → engineer`,
`maintenance_technician → engineer`를 사용할 수 있지만, 이 매핑이 두 현장 역할의 업무 권한을 같게
만든다는 뜻은 아니다.

시스템 계정·권한·workspace scope를 관리하는 역할은 `tenant_admin`이다. 따라서
`process_manager`를 단독으로 `관리자`라고 표기해 system administrator와 혼동시키지 않는다.

### 3.2 생산 운영 의사결정자 (`process_manager`)

현장 상태, Evidence, 엔지니어의 점검·분석 결과를 보고 운영 판단을 내리는 역할이다.

허용 Product Action:

- Event / Evidence / Recommendation 조회
- 현장 엔지니어의 점검·분석 결과 확인
- 기존 operational decision 기록
- Recommendation 승인 / 거절 / 보류
- 승인된 Recommendation에 대한 WorkOrder 승인
- 현재 상태와 권한에서 가능한 다음 Action 조회

기본 Product UX에서 현장 체크리스트 입력, 실제 정비 작업 시작·완료 같은 작업자 Action을 대신
수행하지 않는다.

### 3.3 현장 엔지니어 (`process_engineer`)

설비 상태와 Evidence를 직접 확인하고 점검·분석 결과와 의사결정 근거를 만드는 역할이다.

허용 Product Action:

- Event / Equipment / Evidence 상세 조회
- 센서·예측 결과 및 원인 후보 확인
- 점검 note 기록
- Inspection 수행 및 결과 기록
- 측정값 / 체크리스트 / 현장 확인 내용 기록
- 이상 상태 또는 추가 정비 필요 여부 보고
- 생산 운영 의사결정자에게 판단 근거 전달
- 현재 상태와 권한에서 가능한 다음 Action 조회

Recommendation 승인/거절/보류 또는 maintenance WorkOrder 승인 권한을 갖지 않는다.

### 3.4 정비 작업자 (`maintenance_technician`)

승인된 WorkOrder / MaintenanceAction에 따라 실제 정비 작업을 수행하는 역할이다.

허용 Product Action:

- 배정 WorkOrder / Action 조회
- 작업 메모 기록
- 작업 시작 / 완료
- 문제 발견 보고
- 작업 불가(`blocked`) 기록
- 측정값 / 체크리스트 / 사진 metadata / handoff note 기록
- 현재 상태와 권한에서 가능한 다음 Action 조회

Recommendation 승인/거절/보류 또는 WorkOrder 승인 권한을 갖지 않는다.

### 3.5 역할별 Action 경계

기존 Ontology Action의 의미를 우선 재사용한다.

- WorkOrder: `complete_work_order`, `report_work_order_issue`, `mark_work_order_blocked`
- Inspection: `complete_inspection`, `report_inspection_issue`, `mark_inspection_blocked`
- 메모: `record_work_order_note`, `record_inspection_note`

`process_engineer`와 `maintenance_technician`은 같은 역할로 합치지 않는다. 현재 coarse permission이
일부 겹치더라도 Backend의 Product Action resolver가 role, 대상 객체의 `work_type`, 현재 상태, 배정,
scope와 lineage를 함께 검사해야 한다.

Domain에 `failed` / `cancelled` 상태가 존재한다는 이유만으로 Frontend가 사용자 버튼을 임의 생성하지
않는다. 사용자 명령과 permission mapping이 합의된 경우에만 `available_actions`로 노출한다.

## 4. `available_actions` 계약

Frontend는 role, permission, Domain transition을 조합해 가능한 버튼을 자체 계산하지 않는다.
Asset detail ViewModel의 `asset.criticality`, `maintenance_context`, `operation_context`,
`review_priority`는 화면 검토 순서와 근거 설명을 위한 read-model field다. 이 값으로
Recommendation disposition, WorkOrder priority, WorkOrder ID, MaintenanceAction state 또는
`available_actions`를 Frontend에서 합성하지 않는다. 값이 없으면 `null`/gap으로 표시하고
Backend가 제공하지 않은 `normal`, `low`, `false`, `0` 기본값을 만들지 않는다.

Backend는 현재 요청 principal과 대상 객체를 기준으로 최소 다음 조건을 평가한다.

- RBAC role
- effective permission
- organization / project / workspace scope
- 현재 object state
- object type / `work_type`
- assignment 또는 actor eligibility
- Event / Equipment / Recommendation / WorkOrder lineage
- idempotency 또는 동시 실행 상태

그 결과를 `available_actions`로 반환한다. Frontend는 이를 **presentation과 사용자 입력 진입점**에만
사용한다. Frontend가 받은 배열을 보안 경계로 신뢰해서는 안 되며, mutation 요청 시 Backend가 동일한
authorization/state 검증을 다시 수행한다.

각 item은 최소 다음 필드를 갖는다.

```json
{
  "action_id": "approve_work_order",
  "target_type": "work_order",
  "target_id": "wo-..."
}
```

- `action_id`: Backend가 정의한 stable machine identifier다. Frontend가 Domain transition 이름을 조합해
  생성하지 않는다.
- `target_type`: Action이 적용되는 canonical object type이다.
- `target_id`: Persistence/API가 반환한 대상 객체 ID다. Frontend가 합성하지 않는다.

display label, disabled reason, 입력 schema 같은 표현 metadata는 additive하게 확장할 수 있으나,
Frontend가 `action_id`를 Domain transition으로 재해석하거나 이 세 필드만으로 authorization을 우회하지
않는다.

## 5. Closed-loop 상태 소비 계약

상태 값과 허용 전이는 `closed-loop-domain-contract.md`를 그대로 사용한다.

```text
RiskEvent
open → acknowledged → in_progress → resolved → closed

RecommendedAction
proposed → accepted | rejected | deferred | superseded
deferred → accepted | rejected | superseded

WorkOrder
requested → approved → in_progress → completed | blocked | failed | cancelled

MaintenanceAction
planned → in_progress → completed | failed | cancelled
```

추가 Product 의미는 다음과 같다.

- `Decision`은 별도 mutable lifecycle을 만들지 않는 immutable operational decision record다.
- 기존 operational decision은 `continue_monitoring`, `request_inspection`, `review_shutdown`,
  `hold_for_data_check`를 유지한다.
- Recommendation 판단은 `accept`, `reject`, `defer` disposition으로 표현한다.
- `superseded`는 일반 사용자 Action 버튼보다 대체된 Recommendation의 상태 표현으로 본다.
- `MaintenanceEvent`는 완료된 정비 사실을 나타내는 immutable fact다.
- `Activity`는 별도 stateful object가 아니라 immutable timeline이다.

### 5.1 WorkOrder / MaintenanceAction 생성 경계

정비가 필요한 Recommendation을 `accept`할 때와 WorkOrder를 `approve`할 때의 생성 책임을 분리한다.

```text
Recommendation accept
→ maintenance WorkOrder(requested) 생성
→ 이 단계에서는 MaintenanceAction을 생성하지 않음

WorkOrder approve
→ 해당 WorkOrder에 대한 MaintenanceAction(planned) 생성

maintenance_technician
→ approved WorkOrder / planned MaintenanceAction을 시작
```

따라서 Recommendation 승인 mutation이 WorkOrder와 MaintenanceAction을 동시에 생성하는 것으로 구현하지
않는다. 각 생성 mutation의 응답은 Persistence가 확정한 `work_order_id` 또는
`maintenance_action_id`를 반환하고, 다음 단계는 그 ID를 그대로 사용한다.

### 5.2 정비 후 Runtime 준비 상태

MaintenanceEvent 완료 이후 Product/API/UI는 정비 완료 사실과 Prediction 준비·결과를
같은 상태로 합치지 않는다. Runtime Overlay 상세 동작은
[`closed-loop-runtime-overlay-contract.md`](./closed-loop-runtime-overlay-contract.md)를
따른다.

| 상태 | Product/UI 의미 |
|---|---|
| `equipment_under_maintenance` | 정비 진행 중 |
| `warming_up` | 정비 후 Observation 이력 생성 중. 가능하면 `n/N` 진행률 표시 |
| `history_insufficient` | 요구 이력을 확보하지 못해 Prediction 불가 |
| `ready` | Backend가 추론 가능한 이력을 확보함 |
| `predicted` | 신규 Runtime Prediction과 Product Result/Evidence 생성 완료 |

`equipment_under_maintenance`, `warming_up`, `history_insufficient`, `ready`를
`NORMAL` Prediction으로 표현하지 않는다. 정비 완료 자체도 정상 판정이 아니며, 정비 후
실제 Product Result가 조치 불필요로 판정한 경우에만 정상으로 표시한다.

Inference readiness의 canonical owner는 Backend Diagnosis다. `gen_data`는 생성된
Observation availability를 알릴 뿐 `ready` 또는 `history_insufficient`를 판정하지 않는다.

> **Deferred:** Product API의 canonical runtime-status read location은 `gen_data` Runtime
> Overlay의 versioned Observation/status handoff 계약이 확정된 이후 Backend integration
> 단계에서 결정한다. 현재 문서는 상태 의미와 `status_grade` 분리 원칙만 고정한다.

## 6. Event API Product 소비 계약

### 6.1 additive compatibility

기존 Event API key를 삭제하거나 rename하지 않는다. 이미 배포된 Frontend/Report consumer가 읽는 기존
shape는 유지하고 Closed-loop 정보만 additive하게 확장한다.

`GET /api/events/{event_id}`의 기존 top-level key는 그대로 유지하고, 새 Closed-loop 정보는 **하나의
top-level `closed_loop` envelope 아래**에 추가한다. 새 필드를 top-level과 `closed_loop` 양쪽에 중복
노출하지 않는다.

```json
{
  "existing_field": "...",
  "closed_loop": {
    "event_status": "open",
    "recommendations": [],
    "latest_decision": null,
    "work_orders": [],
    "maintenance_actions": [],
    "maintenance_events": [],
    "available_actions": []
  }
}
```

Recommendation / WorkOrder / MaintenanceAction은 한 Event에 복수 존재할 수 있으므로 singular object로
축약하지 않고 배열을 기본으로 한다.

### 6.2 mutation 응답

`POST /api/events/{event_id}/decision`은 기존 응답을 깨지 않고 필요 시 다음 정보를 additive하게
반환한다.

- `recommendation_id`
- `disposition`
- `previous_recommendation_status`
- `recommendation_status`
- `work_order_id`
- `replayed`

모든 Closed-loop mutation 응답은 Frontend가 결과를 추측하지 않도록 최소 다음을 반환한다.

1. Persistence가 확정한 생성·변경 객체 ID
2. 변경 전/후 상태 또는 최종 resulting state
3. idempotency replay 여부

서버가 아직 commit하지 않은 임시 ID를 반환하거나 Frontend가 다음 ID를 규칙으로 합성하는 방식을
허용하지 않는다.

### 6.3 Idempotency key 전달 계약

모든 Closed-loop state-changing mutation은 클라이언트가 HTTP `Idempotency-Key` header를 전달하는
방식을 canonical retry 계약으로 사용한다. 서버가 요청 처리 때마다 새 UUID를 만들어 client retry key를
대체해서는 안 된다.

서버는 key와 canonical request fingerprint를 함께 저장하고, commit된 결과와 연결한다.

- 동일 `Idempotency-Key` + 동일 canonical request
  → 새 side effect를 만들지 않고 기존 persisted 결과를 반환하며 `replayed=true`
- 동일 `Idempotency-Key` + 다른 canonical request
  → `409 idempotency_key_conflict`
- 최초 성공 처리
  → commit된 persisted ID/resulting state를 반환하며 `replayed=false`

request fingerprint는 최소 대상 object, requested action/disposition, state-changing payload를 포함해야 하며,
표시용 metadata나 전송 순서 차이 때문에 동일 논리 요청이 다른 요청으로 오인되지 않게 canonicalize한다.
mutation authorization/state validation은 replay 여부와 무관하게 Backend 소유권 경계를 유지한다.

## 7. Activity 계약

`GET /api/events/{event_id}/activity`의 기존 top-level 소비 계약인 다음 key는 유지한다.

- `decisions`
- `notes`
- `conversations`

새 Closed-loop timeline은 기존 세 key를 대체하거나 섞어 쓰지 않고 additive top-level `activities` 배열에
담는다.

`activities[]`의 Closed-loop timeline item은 해당 activity에 적용되는 lineage와 transition 값만 포함한다. 가능한 필드는
다음과 같다.

- `activity_id`
- `activity_type`
- `event_id`
- `equipment_id`
- `recommendation_id`
- `work_order_id`
- `work_type` (`inspection` 또는 `maintenance`; WorkOrder와 연결되지 않은 activity는 null 가능)
- `maintenance_action_id`
- `maintenance_event_id`
- `actor_user_id`
- `actor_display_name`
- `before_status`
- `after_status`
- `created_at`

모든 activity에서 모든 ID를 강제하지 않는다. 예를 들어 Recommendation 판단에는
`maintenance_event_id`가 없어도 된다. 대신 존재하는 ID는 같은 Event/Equipment lineage를 깨뜨리면 안
된다.

### 7.1 Maintenance canonical command/read 위치

2단계 점검→정비 판단 경계는 다음 project/workspace-scoped API를 사용한다.

| Method | Path | Actor |
|---|---|---|
| `POST` | `/api/projects/{project_id}/workspaces/{workspace_id}/maintenance/inspection-work-orders` | `process_manager` |
| `POST` | `.../inspection-work-orders/{work_order_id}/approve` | `process_manager` |
| `POST` | `.../inspection-work-orders/{work_order_id}/start` | `process_engineer` |
| `POST` | `.../inspection-work-orders/{work_order_id}/complete` | `process_engineer` |
| `POST` | `.../inspection-results/{inspection_result_id}/recommendations` | `process_manager` |
| `POST` | `.../recommendations/{recommendation_id}/decisions` | `process_manager` |
| `GET` | `.../events/{event_id}/lineage` | `events.read` principal |

모든 mutation은 `Idempotency-Key`를 요구한다. canonical lineage read는 producer Product
Result/Evidence → inspection WorkOrder/Result → Operations manual recommendation → 두 번째
RecommendationDecision → maintenance WorkOrder와 `activities[].work_type`을 한 응답에서 보존한다.
Inspection 완료 응답의 `maintenance_event_id`는 null이며 별도 추천 승인 전에는 maintenance
WorkOrder를 만들지 않는다.

Inspection WorkOrder 요청 본문은 `event_id`만 받는다. `asset_id`, `equipment_id`, `asset_type`,
`operational_decision_kind`, Product Result/Evidence/Action ID와 schema/policy version은
클라이언트 입력을 신뢰하지 않는다. Backend가 동일 organization/project/workspace scope의
Diagnosis public query로 canonical Event Evidence Projection을 조회하고, 다음 조건을 모두
검증한 뒤 WorkOrder authorization과 lineage를 서버에서 구성한다.

- Event와 scope가 실제 canonical Product Result에 존재한다.
- Projection의 `asset_id = equipment_id`이고 subject/artifact의 `asset_type`이 일치한다.
- `assessment.operational_decision_kind`가 `request_inspection` 또는 `review_shutdown`이다.
- 단일 `recommended_actions[0].action_id`가 operational decision과 일치한다.
- Product Result/Evidence/Action ID와 schema/policy version이 Projection에 존재한다.

존재하지 않거나 scope가 다른 Event는 not found로, 누락·불일치·비허용 결정은 fail-fast
계약 오류로 처리한다. WorkOrder와 Inspection Result에는 Projection에서 얻은 `asset_type`을
보존하며, Operations manual recommendation이 이를 이어받는다.

## 8. Product aggregation / identity 계약

Product aggregation root는 `event_id`다.

운영 객체 join key:

- `event_id`
- `equipment_id`
- `recommendation_id`
- `work_order_id`
- `maintenance_action_id`
- `maintenance_event_id`

Operations identity는 `asset_id = equipment_id`를 사용한다. Frontend는 operational ID를 생성하지 않고
Persistence/API가 반환한 ID를 이어서 사용한다.

다음 값은 provenance이며 operational join ID의 대체물이 아니다.

- `source_action_id`
- `source_product_result_id`
- `source_evidence_id`
- `source_schema_version`
- `source_policy_version`

## 9. 오류 계약

기존 ErrorEnvelope를 유지한다.

```json
{
  "error": {
    "code": "...",
    "message": "..."
  }
}
```

Product/UI는 최소 다음 오류를 구분한다.

| HTTP | code | Product 의미 |
|---:|---|---|
| 401 | `authentication_required` | 로그인 필요 또는 세션 만료 |
| 403 | `permission_denied` | Action permission 부족 |
| 403 | `project_scope_denied` | 허용 Project 범위 밖 |
| 403 | `workspace_scope_denied` | 허용 Workspace 범위 밖 |
| 404 | `not_found` | 대상 객체 없음 |
| 409 | `active_project_mismatch` | 활성 Project와 대상 불일치 |
| 409 | `invalid_state_transition` | 현재 상태에서 허용되지 않는 Domain transition |
| 409 | `idempotency_key_conflict` | 같은 key에 다른 요청 |
| 409 | `action_in_progress` | 동일 Action 요청 처리 중 |
| 409 | `prior_action_failed` | 동일 요청의 이전 실행 실패 |
| 422 | `contract_validation_failed` | 입력 계약 검증 실패 |
| 422 | `project_action_not_configured` | Project에 Action 미구성 |
| 5xx | persistence/transaction failure | 운영 transaction 확정 실패 |

잘못된 Domain transition을 generic `ValueError → 422 contract_validation_failed`로 합치지 않고 가능한 한
`409 invalid_state_transition`으로 구분한다.

Operational PostgreSQL transaction 실패와 outbox/외부 projection 실패도 같은 UI failure로 취급하지
않는다. 운영 transaction이 commit되지 못한 경우 mutation 자체 실패다. transaction은 성공했지만
Ontology projection이 지연·실패한 경우에는 PostgreSQL 운영 정본을 되돌리지 않고 projection 상태를
별도로 표시·복구한다.

## 10. Operations E2E persona와 기본 흐름

대표 fixture:

- Project: `manufacturing-demo-project`
- Workspace: `manufacturing-demo`
- Event: `EVT-GS-002`
- Equipment: `M-014`

persona:

| 제품 역할 | demo account | RBAC role |
|---|---|---|
| 생산 운영 의사결정자 | `manager@ontology.local` | `process_manager` |
| 현장 엔지니어 | `engineer@ontology.local` | `process_engineer` |
| 정비 작업자 | `technician@ontology.local` | `maintenance_technician` |

`process_engineer`는 optional persona가 아니라 핵심 Operations 의사결정 흐름의 선행 역할이다.

기본 업무 흐름:

```text
현장 엔지니어가 Evidence / 설비 상태 확인
→ 점검·분석 결과와 판단 근거 기록
→ 생산 운영 의사결정자가 근거를 확인하고 Recommendation / operational decision 판단
→ 정비가 승인된 경우 정비 작업자가 WorkOrder / MaintenanceAction 수행
```

권장 E2E 순서:

1. Product Result / Evidence 생성·조회
2. `process_engineer`가 Event / Equipment / Evidence 확인
3. 현장 inspection / note / 측정 결과 기록
4. `process_manager`가 Evidence + engineer 결과 확인
5. Recommendation 승인 / 거절 / 보류
6. Recommendation `accept` + 정비 필요 시 `WorkOrder(requested)` 생성 확인
7. `process_manager`가 WorkOrder 승인 → `MaintenanceAction(planned)` 생성 확인
8. `maintenance_technician`이 approved WorkOrder / planned MaintenanceAction 작업 시작
9. checklist / measurement / note와 함께 작업 완료
10. MaintenanceEvent / Equipment state / `activities[]` 반영
11. 동일 `Idempotency-Key` + 동일 요청의 replay 및 다른 요청의 conflict 검증
12. 대상 설비만 Runtime Overlay로 분기되고 정비 후 이력이 준비되는 상태 확인
13. Backend가 이력 부족 시 Prediction하지 않고 다음 available Observation을 기다리는지 확인
14. 첫 inference-ready Observation에서 새 Product Result/Evidence 생성 확인
15. 정비 전 Result → Decision → Action → 정비 후 Result lineage 확인

Recommendation / WorkOrder / MaintenanceAction ID는 E2E 코드에 하드코딩하지 않는다. 앞 mutation/API가
반환한 persisted ID를 다음 요청으로 전달한다.

공개 `/api/demo/reset` endpoint를 추가하지 않는다. fixture reset/setup이 필요하면 테스트·배포 환경에
한정된 기존 setup 경계나 직접 repository fixture를 사용하고 public Product API로 노출하지 않는다.

## 11. 역할 경계와 구현 소유권

### Closed-loop domain

- Closed-loop Domain
- Persistence
- repository / PostgreSQL
- outbox / projection consumer
- migrations
- backend Domain API
- OpenAPI
- Closed-loop backend tests

Closed-loop domain이 직접 소유하지 않는 범위:

- `systems/generator/`
- `systems/backend/app/diagnosis/`
- `systems/frontend/`
- Product Result/Evidence 의미 변경
- Event Evidence Projection 의미 변경
- Report grounding 의미 변경

### 우수

- Product API aggregation / orchestration
- Frontend / UI consumption
- 최종 Product E2E / release orchestration

이 문서는 Backend와 Frontend 사이의 공유 contract이므로 양쪽 구현에서 공식 참조 문서로 사용한다.

## 12. 구현 및 migration 기준

Closed-loop Persistence/API는 canonical `systems/backend/app` 도메인, repository/PostgreSQL,
outbox, migration과 contract test를 함께 변경한다. 제거 대상인
`systems/backend/ontology_dashboard` compatibility 경로에는 신규 기능을 추가하지 않는다.

### 12.1 migration 번호

새 migration은 현재 `main`의 마지막 migration 번호를 확인하고 그 다음 번호를 사용한다. 기존
번호를 덮어쓰거나 운영 DB에 적용된 migration을 다시 작성하지 않는다.

## 13. 완료 조건

Product/API/UI Closed-loop 구현은 최소 다음 조건을 만족해야 한다.

- Backend Domain 상태와 Frontend 버튼 상태가 중복 state machine 없이 연결된다.
- 세 역할의 제품 의미와 허용 Action이 분리된다.
- `process_manager`가 system administrator로 표현되지 않는다.
- `available_actions`가 role + permission + state + scope + lineage를 반영한다.
- 기존 Event API key와 기존 Activity key가 유지된다.
- mutation 응답으로 persisted ID와 resulting state를 이어갈 수 있다.
- invalid transition과 contract validation 오류가 구분된다.
- operational transaction 실패와 projection 실패가 구분된다.
- E2E에서 engineer → manager → technician 흐름과 persisted ID chaining을 검증한다.
- 정비 전·후 Product Result와 Decision/Action/MaintenanceEvent lineage를 재구성할 수 있다.
- 정비 완료, 이력 준비 중, 이력 부족과 실제 Prediction 결과를 서로 다른 상태로
  소비한다.
