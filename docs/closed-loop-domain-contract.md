# Closed-loop Domain 계약

이 문서는 `closed-loop-implementation-plan.md`의 PR 1 구현 기준이다. HTTP, DB,
Product Result/Evidence projection은 이 범위에 포함하지 않는다.

사용자 역할, 역할별 Action, `available_actions`, Event API additive compatibility, 오류와 E2E 소비 규칙은
[`closed-loop-product-consumption-contract.md`](./closed-loop-product-consumption-contract.md)가 정본이다.
Product/UI 문서는 이 문서의 상태 머신을 재정의하지 않는다.

정비 완료를 대상 설비 Runtime Overlay와 정비 후 Prediction으로 연결하는 시스템 간
handoff는 [`closed-loop-runtime-overlay-contract.md`](./closed-loop-runtime-overlay-contract.md)를
따른다. Runtime Overlay 계약은 이 문서의 Domain 상태 머신을 재정의하지 않는다.

## 기존 Decision과 실행 권한 매핑

| 기존 Decision 값 | 운영 의미 | 점검 Work Order | 정비 Work Order |
|---|---|---:|---:|
| `continue_monitoring` | 관찰 지속 | 불가 | 불가 |
| `request_inspection` | 현장 점검 요청 | 가능 | 불가 |
| `review_shutdown` | 가동 중단 검토 및 현장 확인 요청 | 가능 | 불가 |
| `hold_for_data_check` | 데이터 확인 전 보류 | 불가 | 불가 |

기존 Decision 네 값에는 정비 승인이 없다. 따라서 `review_shutdown`을 승인으로
해석하지 않으며, 정비 Work Order는 해당 Operational RecommendedAction에 대한 별도
`RecommendationDecision(disposition=accept)`이 있고 추천 상태가 `accepted`일 때만
허용한다.

## 객체 경계

- Producer recommendation: Product Result/Evidence producer가 소유하는 원본 후보
- Operational RecommendedAction: 원본 의미를 바꾸지 않고 운영 ID와 상태만 추가한 projection
- RecommendationDecision: 사람이 추천을 승인·거절·보류한 판단
- WorkOrder: 점검 또는 정비 업무 단위
- MaintenanceAction: 승인된 정비 Work Order 안에서 수행하는 실제 행동
- MaintenanceEvent: 완료된 정비 사실을 나타내는 불변 이력

`request_inspection`과 `review_shutdown`은 기존 동작에 맞춰 inspection Work Order만
허용한다. 둘 다 정비 승인의 의미는 없다. maintenance Work Order와 MaintenanceAction은
명시적인 추천 승인 없이는 생성할 수 없다.

모든 운영 레코드는 `organization_id`, `project_id`, `workspace_id` scope를 보존한다.
RecommendedAction은 Equipment, Event, Product Result, Evidence와 producer action을
직접 참조한다. 이후 Decision, WorkOrder, MaintenanceAction, MaintenanceEvent는 직전
객체 ID와 Event/Equipment scope를 보존해 전체 흐름을 역추적할 수 있어야 한다.

MaintenanceAction은 승인된 maintenance Work Order에서만 계획할 수 있다.
MaintenanceEvent는 동일 scope와 lineage를 가진 Work Order와 MaintenanceAction이 모두
`completed`인 경우에만 생성한다.

## Identity와 멱등성

- Operations는 `equipment_id = asset_id`를 사용한다.
- stable equipment key는 `organization_id + project_id + asset_id`이며 Dataset Version을
  포함하지 않는다.
- mapping 누락, 중복, `asset_type` 불일치는 추정하지 않고 실패한다.
- Operational RecommendedAction 중복 방지 키는
  `source_product_result_id + source_action_id`다.
- Producer의 action/result/evidence/schema/policy ID와 label, kind, approval requirement,
  basis는 materialization 과정에서 변경하지 않는다.
- Producer가 소유하는 `kind`는 Closed-loop enum으로 재해석하지 않고 opaque string으로
  그대로 보존한다. 운영 Decision은 Event Evidence Projection의 별도
  `operational_decision_kind` 계약을 사용한다. Producer `kind` 문자열이 기존
  OperationalDecisionKind와 같아도 Maintenance는 이를 직접 변환하지 않는다.
- `operational_decision_kind`는 Event Evidence Projection `assessment`의 공식 machine field다.
  기존 `assessment.recommended_decision`은 display compatibility field이며 Maintenance가 운영
  Decision으로 소비하면 안 된다. 허용
  값은 `continue_monitoring`, `request_inspection`, `review_shutdown`, `hold_for_data_check`이고,
  추천이 없거나 policy/basis/criticality가 충족되지 않으면 null 또는 absent로 둔다. 이 값은
  Diagnosis policy의 `action_id`에서 별도 projection하며, Producer `kind` 문자열 비교나 기존
  `recommended_decision` mapping으로 추정하지 않는다. 계약 파일은
  `contracts/schemas/event-evidence-projection.schema.json`이다. 필드가 없거나 null이면 inspection
  WorkOrder를 생성하지 않는다.
- `unavailable`은 recommendation `kind`가 아니라 추천 미생성 상태다. Producer가
  근거 부족, unresolved basis, criticality 누락 등으로 추천을 만들 수 없으면 빈
  Operational RecommendedAction을 materialize하지 않고 `evidence_gap` 또는 limitation으로
  표현한다. `hold_for_data_check`는 데이터 확인 전 보류 recommendation으로 유지한다.
- Product Result Artifact v1.0은 root `recommended_action` key를 유지하되 추천 미생성 시
  `null`을 사용하고 `evidence_payload.recommended_actions=[]`와 일치시킨다. 기존 key를 제거하지
  않는 정합성 수정이므로 이 작업에서는 schema version을 올리지 않는다.
- 동일 idempotency key와 동일 요청이 성공한 경우 기존 결과를 replay한다.
- 동일 key에 다른 요청을 사용하면 conflict, 기존 요청이 실행 중이거나 실패했다면 각각
  명시적인 `action_in_progress`, `prior_action_failed` 상태로 처리한다.

## 상태 전이

- RiskEvent: `open → acknowledged → in_progress → resolved → closed`
- RecommendedAction: `proposed → accepted | rejected | deferred | superseded`
- deferred recommendation: `deferred → accepted | rejected | superseded`
- WorkOrder: `requested → approved → in_progress → completed | blocked | failed | cancelled`
- MaintenanceAction: `planned → in_progress → completed | failed | cancelled`

완료·거절·차단 등 terminal 상태를 과거 상태로 되돌리지 않는다.

## Operations manual Recommendation 계약

점검 후 실제 정비가 필요하다는 사람의 판단은 Diagnosis ProducerRecommendation을
변경하거나 재해석하지 않고 별도 `recommendation_origin=operations_manual` 객체로
생성한다.

- Operations Maintenance action vocabulary는 `TOOL_REPLACEMENT`와
  `COOLING_SYSTEM_RESTORE`로 제한한다. 두 Action 모두 구조화된 Inspection Result에서
  각각의 후보 조건을 만족한 경우에만 선택할 수 있다.
- `TOOL_REPLACEMENT`의 교체 단위는 공구 홀더나 공구 세트가 아니라 **마모된 카바이드
  절삭 인서트 1개**이다.
- 비용 분석에서 `COOLING_SYSTEM_RESTORE`는 **사내 냉각 경로 세척·막힘 해소·동작
  확인**으로 제한한다. 팬·펌프·칠러 등 부품 교체가 확인되면 이 Action의 비용 기준을
  재사용하지 않고 별도의 견적/Action basis를 요구한다.
- `source_product_result_id`, `source_evidence_id`, `event_id`, Equipment scope를 유지해
  최초 위험 판단까지 역추적할 수 있어야 한다.
- `source_inspection_work_order_id`와 opaque `source_inspection_reference`를 함께 보존한다.
  Maintenance는 이 reference의 내부 형식을 해석하지 않으며 Inspection owner가 제공한
  stable reference만 소비한다.
- `source_policy_version=operations-manual-recommendation-v1`, 작성자와 작성 시각, basis를
  필수로 보존한다.
- 동일 `source_inspection_work_order_id + source_inspection_reference + action_code`는 한
  번만 추천으로 생성한다. 표시 label이나 재전송 시각은 중복 방지 키에 포함하지 않는다.
- 수동 추천 자체는 정비 승인이 아니다. 별도
  `RecommendationDecision(disposition=accept)` 이후에만 maintenance Work Order를 만든다.
- `product_result_projection` 추천은 점검 판단의 근거이며 직접 maintenance Work Order를
  만들 수 없다. 정비 Work Order 생성 경로는 승인된 `operations_manual`의 공식
  Maintenance action으로 제한한다.
- Inspection Result는 Maintenance가 소유하는 불변 운영 사실이며 checklist, measurements,
  findings, outcome, note, 작성자/시각과 원본 inspection WorkOrder lineage를 보존한다. Diagnosis는
  Maintenance DB를 직접 조회하지 않으며, Operations의 Operations manual recommendation은 공식
  Maintenance command/read 경계 안에서만 이 결과를 소비한다.

## 기존 compatibility projection 교정 범위

현재 `ontology_adapter.py`는 기존 Decision과 Note, 현장 작업 결과를 모두
`maintenance_action` 객체로 투영한다. PR 1에서는 runtime projection을 변경하지 않고
다음 Target 의미만 고정한다.

- 운영 Decision은 Decision/Activity로 유지하며 MaintenanceAction으로 승격하지 않는다.
- Note는 Note/Activity로 유지하며 MaintenanceAction으로 승격하지 않는다.
- inspection Work Order의 현장 점검 결과와 실제 정비 MaintenanceAction을 구분한다.
- 실제 projection 교정은 persistence/API 작업과 Product Result/Evidence 계약 반영 순서에
  맞춰 후속 PR에서 수행한다.

기존 Ontology Action은 후속 PR에서 다음 Target 의미로 연결한다. 기존
`field_task_actions` 레코드를 곧바로 새 Domain 객체로 간주하지 않으며, 모든 상태 변경은
대상 Work Order의 `work_type`과 현재 상태를 확인한 뒤 수행한다.

| 기존 Ontology Action | Target 객체·상태 | 유지할 의미와 제한 |
|---|---|---|
| `record_work_order_note` | WorkOrder에 연결된 Note/Activity | WorkOrder 상태를 변경하거나 MaintenanceAction을 생성하지 않는다. |
| `complete_work_order` | WorkOrder `completed` | inspection이면 점검 완료 사실만 기록한다. maintenance이면 연결된 MaintenanceAction 완료와 MaintenanceEvent 생성 조건을 충족한 하나의 완료 명령으로 처리하며, WorkOrder만 단독 완료하지 않는다. |
| `report_work_order_issue` | WorkOrder Activity `issue_found` | 이 보고만으로 WorkOrder를 `blocked`나 `failed`로 전이하지 않는다. |
| `mark_work_order_blocked` | WorkOrder `blocked` | 허용된 상태 전이를 통하며 MaintenanceEvent를 생성하지 않는다. |
| `record_inspection_note` | inspection WorkOrder에 연결된 Note/Activity | 점검 메모를 실제 정비 MaintenanceAction으로 승격하지 않는다. |
| `complete_inspection` | inspection WorkOrder `completed`와 점검 결과 Activity | 점검 완료는 정비 승인이나 MaintenanceEvent가 아니다. |
| `report_inspection_issue` | inspection WorkOrder Activity `issue_found` | 발견 결과를 기록하되 자동으로 정비 WorkOrder/Action을 생성하지 않는다. |
| `mark_inspection_blocked` | inspection WorkOrder `blocked` | 점검 수행 불가 상태만 기록하며 정비 완료로 해석하지 않는다. |

## Runtime Overlay 인계 경계

MaintenanceAction과 maintenance WorkOrder 완료, MaintenanceEvent 생성, Equipment state와
Activity 기록은 하나의 운영 transaction으로 확정한다. 같은 transaction에 Runtime
Overlay consumer로 전달할 Integration Outbox를 적재하되 외부 Generator 호출이나
Prediction 실행을 transaction 안에서 동기 수행하지 않는다.

- Domain/DB의 기존 완료 필드는 `completed_at`을 유지할 수 있다.
- 시스템 간 Maintenance 완료 이벤트에서는 의미를 명확히 하기 위해
  `maintenance_completed_at`으로 매핑한다.
- Closed-loop는 `maintenance.started`, `maintenance.completed`,
  `maintenance.replay_requested`와 재시작 요청에 필요한
  `maintenance_action_id`, 완료 이후의 `maintenance_event_id`, `idempotency_key`,
  `state_version`, 정비 효과와 lineage를 제공한다.
- 완료 정보나 `restart_at`이 늦게 도착하면 대상 설비는 pause 상태를 유지하며 Timeout으로
  자동 재개하지 않는다.
- Closed-loop는 대상 설비 Overlay 생성, Simulation Clock Fast-forward, Feature history
  계산 또는 Product Result/Evidence 생성을 소유하지 않는다.
- 정비 완료 사실은 정상 Prediction을 의미하지 않는다.

단계별 이벤트, typed `state_patch`, 시각 순서와 consumer 책임의 상세 기준은
[`closed-loop-runtime-overlay-contract.md`](./closed-loop-runtime-overlay-contract.md)를
따른다.

## Product Result/Evidence 연동 선행 조건

PR 1은 아래 필드를 임의 생성하지 않고 필수 lineage로 정의한다. 실제 materialization을
연결하는 PR은 호범 담당 계약에서 공식 source가 제공된 뒤에만 시작한다.

- `source_policy_version`: recommendation 또는 Event Evidence Projection에서 사용할
  공식 policy version source를 먼저 확정한다. `unknown` 기본값을 만들지 않는다.
- `source_evidence_id`: canonical Event Evidence Projection의 stable Evidence ID 또는
  공식 식별 reference를 먼저 확정한다. `event_id`나 `artifact_id`를 임의 대입하지 않는다.

위 두 필드가 확정되기 전까지 Product Result/Evidence runtime 연동은 중단하되, HTTP·DB가
없는 순수 Domain 계약과 상태 머신은 독립적으로 사용할 수 있다.
