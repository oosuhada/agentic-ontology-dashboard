# Ontology Operations & Closed-loop 구현 계획

## 1. 문서 목적

이 문서는 광우(`KOR-GANG`)가 담당하는 **Ontology Operations & Closed-loop**의
구현 범위, 팀원 간 경계, 선행 입력, 산출물과 작업 순서를 한 곳에 고정한다.

가장 중요한 목적은 다음 두 가지다.

1. 이미 저장소에 있는 Event, Decision, Work Order, Ontology Action을 다시 만들지 않는다.
2. 성민의 ML/Artifact, 호범의 Product Result/Evidence, 우수의 Product API/UI 영역을
   침범하지 않고 정해진 계약으로 연결한다.

이 계획의 기준은 main에 반영된 `docs/final_team_role_and_step_plan.md`이며, 해당
문서와 충돌할 경우 팀 합의로 기준 문서를 먼저 수정한 뒤 이 문서를 맞춘다.

Closed-loop 계약의 정본은 역할별로 분리한다.

- Domain 객체·상태·lineage: [`closed-loop-domain-contract.md`](./closed-loop-domain-contract.md)
- Product/API/UI 소비·역할·Action·오류·E2E:
  [`closed-loop-product-consumption-contract.md`](./closed-loop-product-consumption-contract.md)
- 정비 완료 → 대상 설비 Runtime Overlay → 정비 후 Runtime Prediction:
  [`closed-loop-runtime-overlay-contract.md`](./closed-loop-runtime-overlay-contract.md)

이 구현 계획은 canonical contract의 상세 내용을 복제하지 않고 구현 순서와 변경 범위만 관리한다.

```text
Closed-loop architecture/workflow (아키텍처 / 유스케이스 패턴 명칭)
        ↓
Backend owner: app/maintenance (Backend bounded context 명칭)
```


## 2. 구현 목표

대표 CNC Tool Replacement 사례 하나에서 다음 흐름을 실제 데이터와 상태 전이로
완성한다.

```text
호범: Product Result / Evidence 생성
                 ↓
광우: RiskEvent에 Result / Evidence 연결
                 ↓
      Producer recommendation을 운영 RecommendedAction으로 materialize
                 ↓
우수: 현장 엔지니어가 Evidence / 설비 상태 확인 및 점검·분석 근거 기록
                 ↓
      생산 운영 의사결정자가 Recommendation / operational Decision 판단
                 ↓
      승인된 MaintenanceAction / Work Order 실행
                 ↓
      정비 작업자가 실제 작업 수행
                 ↓
      MaintenanceEvent와 Activity 기록
                 ↓
      Equipment / Ontology 운영 상태 갱신
                 ↓
광우: 단계별 Maintenance Integration 이벤트를 Outbox로 발행
                 ↓
성민: 대상 설비만 Runtime Overlay로 분기하고 정비 효과 반영
                 ↓
      대상 설비 Overlay branch clock에서 Observation 지속 생성/available
                 ↓
호범: history_requirement 검증
      ├─ 부족: Prediction 없이 다음 Observation 대기
      └─ 충족: 첫 inference-ready Observation으로 새 Product Result/Evidence 생성
                 ↓
우수: 전 과정을 Product API / UI / E2E로 노출
```

Closed-loop는 과거 예측 결과를 수정하는 기능이 아니다. 정비 전 Product Result와
정비 이력을 보존하고, 정비 후 새 Observation에 대해 **별도의 새 Product Result**를
생성하여 이전 판단·조치와 추적 가능하게 연결하는 것이 목표다.

## 3. 담당 경계

### 3.1 광우가 직접 구현하는 범위

| 영역 | 구현 책임 |
|---|---|
| RiskEvent 연결 | Product Result/Evidence를 동일 Equipment의 운영 Event에 연결하고 중복 Event 정책 적용 |
| RecommendedAction | 호범의 구조화 recommendation을 의미 변경 없이 운영 workflow 객체로 materialize하고 실제 실행 Action과 분리 |
| Decision | 생산 운영 의사결정자의 판단, 근거, 행위자, 시각 및 대상 Recommendation 기록 |
| Work Order / MaintenanceAction | 정책 기반 점검 Work Order와 승인 후 정비 실행 Work Order/Action을 구분하고 허용 상태 전이 구현 |
| MaintenanceEvent | 실제 수행 결과, 작업자, 시작·종료 시각, 정비 내용을 이력으로 기록 |
| Ontology projection | 호범 계약의 Evidence ID와 의미를 변경하지 않고 Equipment–RiskEvent–Evidence–WorkOrder–MaintenanceAction 관계 유지 |
| Equipment state | 정비 완료 후 운영 상태와 최신 정비 참조 갱신 |
| Activity / audit | 후보 생성부터 완료까지 모든 업무 변경을 시간순으로 추적 |
| Closed-loop API | Domain 상태를 조회·변경하는 안정적인 Backend API 제공 |
| Domain tests | 상태 전이, 권한, 멱등성, 관계, 감사 기록 및 실패 케이스 검증 |

### 3.2 다른 팀원이 담당하며 광우가 구현하지 않는 범위

| 담당자 | 정본 산출물 | 광우의 사용 방식 | 광우가 하지 않을 일 |
|---|---|---|---|
| 성민 | Feature/Label 계약, Model Artifact, 학습·발행 및 `gen_data` Runtime Overlay Observation 지속 생성/available | model/feature 의미와 Overlay Observation 계약을 읽기 전용으로 참조 | Feature 계산, 모델 학습, Artifact 발행·선택, Overlay 생성 |
| 호범 | Runtime readiness, inference, Product Result Artifact, Evidence Payload/API | Event와 Action의 근거 입력으로 소비 | probability·risk grade·top factor 재계산, Evidence 재생성 |
| 우수 | Product API orchestration, Operations UI, Report/LLM 연결, CI/E2E/배포 | 안정적인 Closed-loop Domain API와 fixture 제공 | 화면 구현, LLM 문장 생성, 전체 배포 파이프라인 소유 |

### 3.3 명시적으로 보류하는 범위

- 실시간 What-if 실행
- 위험도 감소량 시뮬레이션
- 자동 정비 실행 또는 실제 설비 제어
- 범용 Workflow/Ontology Engine
- MES/ERP 전체 기능
- 모든 설비·모든 고장 유형 지원
- 비용 기반 정비 대안 분석

비용 기반 정비 대안 분석은 핵심 Closed-loop와 공개 E2E가 완료된 뒤 시간이 남을
때만 별도 계획과 PR로 진행한다. 현재 필수 API, Schema, CI gate에는 포함하지 않는다.

## 4. 현재 저장소 기준 재사용·확장 판단

새 구현 전에 아래 자산을 정본 후보로 사용한다. 이름이 비슷하다는 이유만으로 별도
모델이나 API를 추가하지 않는다.

| 현재 자산 | 현재 역할 | 처리 방침 |
|---|---|---|
| `GET /api/events`, `GET /api/events/{event_id}` | Event 조회 | 재사용·확장 |
| `GET /api/events/{event_id}/evidence` | Evidence 조회 | 호범 계약을 소비하도록 유지 |
| `POST /api/events/{event_id}/decision` | 운영 판단 기록 | 새 API를 만들지 않고 계약·상태 규칙을 확장 |
| `GET /api/events/{event_id}/activity` | Event 활동 조회 | Action/Maintenance 활동까지 포함하도록 확장 |
| `AuditRepository.decisions` | 기존 Decision 저장 | 폐기하지 않고 Target persistence와 통합 방법 결정 |
| `record_operational_decision` | RiskEvent Ontology Action | Decision 실행 진입점으로 재사용 |
| `work_order` | 점검 또는 정비를 현장에 전달하는 canonical 업무 객체 | `work_type`으로 점검과 정비 실행을 구분하여 재사용 |
| `complete_work_order` 등 | 현장 작업 Action | 상태 머신과 결과 계약을 보강해 재사용 |
| `maintenance_action` | 사람이 수행한 정비 행동 객체 | Recommendation과 구분하여 확장 |
| `pm_maintenance_events` | Canonical 데이터 패키지의 과거 정비 이력 | 제품 런타임 명령 저장소로 오용하지 않고 학습/조회 이력으로 유지 |

현재 확인된 주요 공백은 다음과 같다.

- RecommendedAction의 공식 저장·조회 계약이 없다.
- 승인된 Recommendation에서 Work Order/MaintenanceAction을 생성하는 공식 흐름이 없다.
- 작업 완료와 MaintenanceEvent 생성, Equipment state 갱신의 원자적 규칙이 없다.
- 현재 Event activity 응답은 Decision/Note/Conversation 중심이어서 전체 Closed-loop를
  재구성하기 어렵다.
- fixture 기반 Event와 실제 Product Result/Evidence runtime 사이의 연결 정책을
  확정해야 한다.
- 현재 `ontology_adapter.py`는 Decision과 점검 Note도 `maintenance_action` 객체로
  투영한다. Decision, Note와 실제 수행 정비를 구분하려면 이 호환 projection을 그대로
  정본으로 사용하지 말고 객체 의미와 link를 바로잡아야 한다.
- 현재 점검 필요 정책만으로도 `work_type=inspection` Work Order가 투영될 수 있다.
  기존 점검 요청과 생산 운영 의사결정자 승인 후 정비 실행 Work Order를 같은 생성 규칙으로 묶지
  않아야 한다.
- Product Result 최상위 `recommended_action`과
  `evidence_payload.recommended_actions[]`, Closed-loop RecommendedAction의 관계가
  아직 공식 계약으로 고정되지 않았다.
- 현재 Event Evidence projection은 Product Result의 `asset_id`를 `equipment_id`로
  직접 사용한다. 이 동일성 규칙과 Dataset Version을 넘어 유지할 Equipment identity를
  구현 전에 고정해야 한다.

## 5. Domain 계약 초안

세부 필드와 상태 값은 구현 PR 전에 팀과 확정하고, 시스템 경계를 넘는 계약은 향후
`contracts/`의 versioned Schema를 정본으로 사용한다. 아래는 구현 논의를 위한 최소
초안이다.

### 5.1 핵심 식별자

모든 Closed-loop 레코드는 최소한 다음 연결을 보존한다.

```text
organization_id
project_id
workspace_id
asset_id
equipment_id
event_id
product_result_id
evidence_id
recommendation_id
decision_id
work_order_id
maintenance_action_id
maintenance_event_id
```

모든 레코드에 모든 ID가 항상 필요한 것은 아니지만, 어느 단계에서도 상위 근거를
잃어버리면 안 된다. Product Result, Evidence, Decision과 정비 이력을 동일 Event와
Equipment 기준으로 추적할 수 있어야 한다.

Canonical V3.1 Operations에서는 다음 identity 계약을 사용한다.

```text
equipment_id = asset_id
stable equipment key = organization_id + project_id + asset_id
```

- `asset_master.asset_id`와 PostgreSQL에 적재된 `pm_assets.asset_id`를 source of truth로
  사용한다.
- Dataset Version은 Observation/Product Result provenance이며 stable equipment key에
  포함하지 않는다.
- Dataset Version이 바뀌어도 동일 물리 설비는 동일 `asset_id/equipment_id`를 유지한다.
- Ontology의 version-scoped object ID를 운영 Equipment identity로 사용하지 않는다.
- mapping 누락·중복·모호성 또는 `asset_type` 불일치는 추정하지 않고 fail-fast한다.
- 이름, 배열 순서나 표시 label을 이용한 fuzzy mapping은 허용하지 않는다.
- 향후 외부 시스템에서 두 ID가 달라지면 versioned identity mapping registry와 별도
  ADR을 먼저 확정한다. 이 경우에도 원본 `asset_id`와 운영 `equipment_id`를 lineage에
  함께 보존한다.

### 5.2 추천과 실행의 구분

```text
Producer recommendation    = 호범의 Product Result/Evidence가 생성한 구조화 후보
Operational RecommendedAction = Producer recommendation을 운영 workflow에 materialize한 객체
Decision          = 사람이 후보를 승인·거절·보류한 판단
WorkOrder         = 점검 또는 승인된 정비 작업을 현장에 전달하는 업무 단위
MaintenanceAction = WorkOrder 안에서 실제로 수행한 행동
MaintenanceEvent  = 수행된 정비 사실과 결과를 나타내는 이력
```

RecommendedAction 생성만으로 MaintenanceAction이나 MaintenanceEvent를 자동 생성하지
않는다. 기존 정책이 `work_type=inspection` Work Order를 생성하는 흐름은 유지할 수
있지만, `work_type=maintenance` 실행 Work Order와 MaintenanceAction은 생산 운영 의사결정자의 승인
Decision을 통과한 경우에만 만들 수 있다.

Operations에서는 광우가 별도 recommendation 의미를 새로 계산하지 않는다.

- materialization source는 stable `action_id`와 승인·근거 필드를 가진
  `evidence_payload.recommended_actions[]`다.
- Product Result 최상위 `recommended_action`은 producer의 요약 정책 결과로 보존하며,
  Closed-loop 실행 객체로 직접 승격하지 않는다.
- Operational RecommendedAction은 workflow용 `recommendation_id`와 상태를 추가하되
  원본 `action_id`, label, kind, `requires_human_approval`, basis를 변경하지 않는다.
- Producer `kind`는 opaque string으로 보존하고 Closed-loop enum으로 재해석하지 않는다.
  `request_inspection`과 `review_shutdown`을 운영 Decision으로 연결해야 할 때는
  Event Evidence Projection이 제공하는 별도 `operational_decision_kind`만 소비한다.
- `operational_decision_kind`는 Event Evidence Projection `assessment`의 공식 machine field다.
  현행 compatibility `assessment.recommended_decision`은 이 계약을 충족한 필드가 아니다. 허용 값은 `continue_monitoring`,
  `request_inspection`, `review_shutdown`, `hold_for_data_check`이며, 추천 미생성 또는
  policy 입력 부족 상태에서는 null/absent로 둔다. Producer `kind` 문자열 비교나 기존
  `recommended_decision` mapping으로 생성하지 않고 Diagnosis policy `action_id`에서 별도로
  projection하며 `contracts/schemas/event-evidence-projection.schema.json`으로 검증한다.
- `unavailable`은 recommendation `kind`가 아니라 추천 미생성 상태다. 근거 부족이나
  unresolved basis 때문에 정책 추천을 만들 수 없으면 Operational RecommendedAction을
  materialize하지 않고 Evidence gap 또는 limitation으로 남긴다.
- 최소한 `recommendation_origin=product_result_projection`, `source_action_id`,
  `source_product_result_id=artifact_id`, `source_evidence_id`, `source_schema_version`,
  `source_policy_version`과 원본 basis를 보존한다.
- `source_product_result_id + source_action_id`를 materialization 중복 방지 키로 사용한다.
- producer 계약에 stable `action_id`나 policy/version이 없으면 임의 값을 만들지 않고
  PR 3 착수를 중단해 호범 계약을 먼저 보완한다.
- 향후 Operations 정책이 별도 recommendation을 생성하려면 producer projection과 다른
  origin·ID·정책 버전을 사용하고 별도 ADR로 승인한다. producer recommendation을
  덮어쓰거나 같은 객체인 것처럼 취급하지 않는다.

### 5.3 상태 전이 정본

상태 전이는 PR #42에서 확정되어 `docs/closed-loop-domain-contract.md`가 canonical owner다.
이 계획에서 별도 상태 집합을 유지하지 않는다. Product/UI가 어떤 상태와 Action을 노출하는지는
`docs/closed-loop-product-consumption-contract.md`의 `available_actions` 계약을 따른다.

### 5.4 중복과 멱등성

- 동일 Product Result/Evidence를 같은 Event에 두 번 연결해도 한 번만 반영한다.
- 동일 `source_product_result_id + source_action_id`의 Operational RecommendedAction은
  한 번만 materialize한다.
- 같은 승인 요청이나 완료 요청이 재전송되어도 Work Order, MaintenanceEvent가
  중복 생성되지 않도록 idempotency key를 사용한다.
- 같은 Equipment에 열린 Event가 있을 때 새 Result를 기존 Event에 연결할지 새
  Event를 만들지는 failure type, Event 상태와 시간 간격 규칙으로 결정한다.
- `resolved` 또는 `closed` 이후 새 위험이 발생하면 과거 Event를 다시 열지 않고 새
  Event를 생성하는 것을 기본 원칙으로 한다.

### 5.5 무결성과 트랜잭션

- 승인되지 않은 Recommendation으로 정비 실행 Work Order나 MaintenanceAction을
  생성할 수 없다. 점검 요청 Work Order는 별도 정책과 권한을 따른다.
- 허용되지 않은 상태 전이는 `409` 등 명시적인 오류로 실패한다.
- PostgreSQL operational persistence를 Closed-loop 운영 상태의 source of truth로 사용한다.
- Work Order 완료, MaintenanceAction 완료, MaintenanceEvent 생성, Equipment state 갱신,
  Activity/Audit 기록과 Ontology projection용 outbox 적재는 **하나의 PostgreSQL
  transaction에서 함께 commit하거나 전체 rollback**한다.
- 일부 단계가 실패하면 완료 상태, 부분 MaintenanceEvent 또는 outbox 없는 운영 변경이
  남아서는 안 된다.
- Ontology/Neo4j 등 외부 projection은 위 transaction에 직접 묶지 않고 transactional
  outbox consumer가 비동기로 처리한다.
- projection consumer는 idempotent해야 하며 실패 시 retry하고, 반복 실패는
  dead-letter와 운영 상태로 추적한다. projection 실패가 PostgreSQL 운영 정본을
  되돌리지는 않는다.
- SQLite 기반 로컬·테스트 adapter도 동일한 unit-of-work rollback과 멱등성 invariant를
  검증한다.
- 과거 Product Result와 Evidence는 수정하거나 삭제하지 않는다.
- Runtime Overlay Integration Outbox는 운영 transaction과 함께 적재하되 Generator와
  Backend Diagnosis 호출은 외부 consumer가 비동기로 수행한다.
- Closed-loop가 발행하는 `maintenance.*` Integration delivery는 HTTP mutation
  idempotency와 별도로 `idempotency_key`와 단조 증가 `state_version`을 사용한다.
- 내부 `completed_at`은 유지할 수 있으며 공유 이벤트에서
  `maintenance_completed_at`으로 매핑한다.

## 6. API 계획

기존 `/api/events`와 Ontology Action API를 우선 재사용한다. 최종 URL은 우수의 Product
API orchestration과 합의해 고정한다. Product 소비 규칙, additive compatibility, mutation 응답과
오류 계약의 정본은 `docs/closed-loop-product-consumption-contract.md`를 따른다.
Runtime Overlay 준비 상태의 canonical Product read location은 versioned
Observation/status handoff 계약 확정 이후 Backend integration 단계에서 결정하는
Deferred 항목이다.

| 기능 | 우선 방침 |
|---|---|
| Event 상세·Evidence·Activity 조회 | 기존 API 확장 |
| Recommendation 조회 | `GET /api/events/{event_id}/recommendations` 후보 |
| 생산 운영 의사결정자 Decision | 기존 `POST /api/events/{event_id}/decision` 확장 |
| 승인 후 Work Order/Action 생성 | `POST /api/events/{event_id}/actions` 후보 또는 Ontology Action 재사용 |
| 작업 시작 | 기존 Ontology Action 확장 우선, 필요 시 `POST /api/actions/{id}/start` |
| 작업 완료 | `complete_work_order` 재사용 우선, 필요 시 호환 endpoint 제공 |
| Equipment 정비 이력 | 기존 runtime 조회 가능 여부 확인 후 `GET /api/equipment/{id}/maintenance` 결정 |

새 endpoint를 추가하기 전 다음을 반드시 확인한다.

1. 동일 기능의 Ontology Action이나 router가 이미 있는가?
2. Frontend가 이미 소비하는 응답을 깨뜨리지 않고 확장할 수 있는가?
3. Product Result/Evidence 정본을 복제하지 않고 ID로 참조하는가?
4. OpenAPI response contract와 권한 검증을 함께 갱신했는가?

## 7. 구현 단계와 PR 분리

### PR 1. Domain 계약과 상태 머신

목표는 HTTP나 DB 없이 업무 규칙을 먼저 고정하는 것이다.

- 기존 Decision/Work Order/Action 의미와 Target 매핑표 작성
- Decision과 Note를 `maintenance_action`으로 투영하는 기존 호환 동작의 교정 범위 작성
- 점검 Work Order와 정비 실행 Work Order의 생성 조건 분리
- Producer recommendation → Operational RecommendedAction materialization 계약과
  원본 참조 필드 정의
- `asset_id = equipment_id` Operations identity 계약과 Dataset Version 독립 stable key 정의
- RecommendedAction, Decision, WorkOrder/MaintenanceAction,
  MaintenanceEvent 최소 모델 정의
- 허용·금지 상태 전이 구현
- 승인 없는 실행 금지, 중복 생성 금지, 멱등성 규칙 구현
- 순수 Domain unit test 작성

완료 조건:

- 정상 흐름과 rejected/deferred/blocked/중복 요청 케이스가 테스트로 설명된다.
- producer recommendation의 의미와 provenance가 Operational RecommendedAction에서
  변경되지 않는다.
- identity mapping 누락·충돌·type 불일치의 fail-fast 규칙이 테스트로 설명된다.
- 기존 enum과 중복되는 새 상태 집합이 없다.
- 팀이 요청·응답 및 상태 매핑을 검토할 수 있다.

### PR 2. Persistence와 Closed-loop API

- 기존 SQLite/PostgreSQL repository 패턴에 맞춘 migration과 repository 구현
- 기존 Decision 저장 경로와 Ontology Action 실행 경로 통합
- Recommendation, Work Order/Action, MaintenanceEvent 저장·조회
- Event activity에 전체 상태 변경 포함
- PostgreSQL unit of work 안에서 운영 변경과 transactional outbox를 함께 commit
- `maintenance.started`, `maintenance.completed`, `maintenance.replay_requested` 단계별
  Integration event payload와 내부 `completed_at` → `maintenance_completed_at` 매핑
- 시작 단계의 `maintenance_action_id`, 완료 이후의 `maintenance_event_id`,
  `idempotency_key`, `state_version`, typed `state_patch`와 Product Result/Evidence
  lineage를 outbox payload에 보존
- tenant/project/workspace scope, 권한, CSRF, idempotency 검증
- OpenAPI response contract와 API test 추가

2026-08-18 기준 최신 `main`의 PostgreSQL/SQLite migration은
`0029_governed_event_automation.sql`이다. 따라서 이 기준선에서 첫 Closed-loop migration은
`0030_closed_loop_...sql`부터 시작하되, 구현 branch에서 최신 `main`을 다시 확인해 더 높은 번호가
생겼다면 그 다음 번호를 사용한다.

완료 조건:

- 서버 재시작 후에도 상태가 보존된다.
- 다른 tenant/project의 데이터가 조회·변경되지 않는다.
- 같은 요청을 재전송해도 레코드가 중복되지 않는다.
- 잘못된 상태 전이가 명시적으로 실패한다.
- transaction 실패 시 Work Order/Action/MaintenanceEvent/Equipment state/Activity/outbox가
  모두 rollback된다.
- outbox consumer의 retry·idempotency·dead-letter 흐름이 검증된다.
- 완료·재시작 정보가 지연돼도 완료 전에 자동 재개 이벤트를 발행하지 않는다.

### PR 3. Product Result/Evidence 및 Ontology 통합

이 PR은 호범이 Product Result/Evidence Schema와 version, recommendation의 stable
`action_id`·policy/version, 식별자, 조회 API 및 Event Evidence Projection의 근거
의미를 확정하고, `asset_id/equipment_id` identity 계약이 검증된 뒤에만 착수한다.
계약이 확정되기 전에는 Evidence payload, recommendation 의미, projection field 또는
Report grounding 의미를 광우 PR에서 임의로 추가·변경하지 않는다.

- 호범의 실제 Product Result/Evidence ID를 payload 복사 없이 RiskEvent에 연결
- `evidence_payload.recommended_actions[]`를 원본 의미·ID·provenance를 보존한
  Operational RecommendedAction으로 materialize
- Producer `kind`를 직접 OperationalDecisionKind로 변환하지 않고, 공식
  `operational_decision_kind` projection이 null이 아니며 허용 값일 때만 inspection WorkOrder
  결정에 사용
- `unavailable`은 빈 추천으로 materialize하지 않고 추천 미생성 + Evidence gap으로 표현
- `asset_id = equipment_id`와 stable equipment key를 검증하고 실패 시 fail-fast
- 호범 계약의 Evidence 필드·근거 의미를 보존한 채
  Equipment–RiskEvent–Evidence–WorkOrder–MaintenanceAction 관계만 projection
- Recommendation에 근거 Evidence 참조와 정책 버전 기록
- 완료 시 Equipment 운영 상태와 최신 정비 참조 갱신
- Runtime Overlay 계약에 따라 생성된 정비 후 Observation/새 Product Result와 과거
  Event를 lineage로 연결
- publish/load가 아닌 Product Result→Closed-loop integration test 추가

완료 조건:

- Product Result/Evidence를 다시 계산하거나 복사하지 않고 참조한다.
- Operational RecommendedAction이 원본 action ID, Product Result/Evidence ID,
  schema/policy version과 basis를 보존한다.
- Dataset Version이 변경돼도 동일 설비의 stable Equipment identity가 유지된다.
- Event Evidence Projection의 필드와 근거 의미가 호범 계약과 일치한다.
- 관계 탐색으로 판단 근거와 실제 조치 이력을 재구성할 수 있다.
- 정비 전후 Result가 별도 불변 레코드로 존재한다.

### PR 4. 팀 통합 지원

이 PR의 주 소유자는 우수일 수 있으며, 광우는 Closed-loop fixture와 Domain 검증을
담당한다.

- 우수에게 안정된 API, OpenAPI, 예제 payload와 오류 규칙 전달
- 호범에게 Report용 Decision/Action/Maintenance/Activity context 전달
- Operations UI acceptance flow에 필요한 fixture 제공
- 공개 환경의 persistence 및 Closed-loop E2E 실패 수정

완료 조건:

- UI에서 현장 엔지니어의 Evidence 확인·점검 근거 → 생산 운영 의사결정자 판단 → 정비 작업자 실행
  → 완료 → 이력 확인이 가능하다.
- Report가 실제 Decision과 수행 결과만 서술한다.
- 공개 환경에서도 새 Result와 과거 조치의 연결이 유지된다.

### 선택 PR. 비용 기반 정비 대안 분석

핵심 PR 1~4와 공개 E2E가 모두 완료된 경우에만 별도로 시작한다. 즉시 교체, 계획
정비, 지연 후 재평가의 비용을 실제값·추정값·정책 기본값으로 나누어 보여주는 읽기
전용 참고 기능이다. 비용 결과나 최저비용 option은 Recommendation, 승인, WorkOrder 또는
실행 Action을 생성하지 않는다.

## 8. 파일 소유와 변경 충돌 방지

다음 표는 구현 전에 팀에 공유할 **변경 예약 범위**다. 실제 PR에서 범위가 달라지면
먼저 팀에 알린다.

| 경로 | 광우 작업 | 협의 대상 |
|---|---|---|
| `systems/backend/app/maintenance/` | Recommendation/Decision/WorkOrder/MaintenanceAction/MaintenanceEvent 상태와 use case | 우수 |
| `systems/backend/app/equipment/` public port | Equipment identity와 적용된 운영 상태 연결 | 우수, 호범 |
| `systems/backend/app/ontology/` public port | Closed-loop Object/Link/Action projection | 우수, 호범 |
| `systems/backend/app/infra/db/` 및 Maintenance repository adapter | 운영 상태 persistence | 우수 |
| `systems/backend/app/infra/`의 실제 Maintenance messaging adapter 및 Maintenance integration port | Outbox retry·idempotency; 구현이 생길 때 구체 package 경로 확정 | 우수 |
| `systems/backend/migrations/` | Closed-loop 운영 레코드 migration | 우수 |
| `systems/backend/app/diagnosis/` public contract | Evidence 의미 변경 없이 Product Result/Evidence 식별자만 소비 | 호범 계약 확정·검토 후 |
| `systems/backend/app/maintenance/maintenance_router.py` | 응답 계약과 HTTP 변환 | 우수 |
| `tests/`의 Closed-loop 관련 파일 | Domain/API/integration regression | 우수 |

광우는 아래 경로를 직접 소유하지 않는다.

- `systems/generator/`
- `systems/backend/app/diagnosis/`
- `systems/frontend/`
- `experiments/preventive_intervention/`
- Model Artifact/Feature/Label Schema
- Product Result/Evidence Schema의 의미 변경
- Event Evidence Projection의 필드·근거 의미 변경
- Report grounding에서 Evidence/Activity 필드를 해석·매핑하는 계약 변경

다른 담당 경로의 변경이 필요하면 해당 owner에게 요구 계약과 실패 재현 테스트를
전달하고, 공동 수정 여부를 합의한다.

PR #41의 Product Result/Evidence handoff 계약은 merge되었다. 이후 구현은 최신 `main`과
[`backend-migration-map.md`](./backend-migration-map.md)를 기준으로 `app/maintenance`에
수렴한다. 레거시 `routers/manufacturing.py`, `service.py`, `repository.py`를 확장하지 않고,
필요한 호환 API는 도메인 Router 또는 composition adapter로 대체한 뒤 제거한다.


## 9. 팀원별 선행 입력과 인계 산출물

### 9.1 구현 전에 받아야 할 입력

아래 호범 입력은 단순 참고 자료가 아니라 **PR 3 착수 gate**다. Schema, 식별자,
recommendation provenance, 조회 방식과 근거 의미 중 하나라도 미확정이면 광우가 임의
계약을 만들어 통합 구현을 진행하지 않는다.

#### 호범에게 받을 것

- Product Result Artifact와 Evidence Payload의 최종 Schema/version
- `product_result_id`, `evidence_id`, `asset_id`, 생성 시각
- `evidence_payload.recommended_actions[]`의 stable `action_id`, policy/version과 basis
- `asset_id = equipment_id` Operations 규칙과 Dataset Version 독립 stable identity 검증 기준
- risk grade, failure type, top factor의 공식 의미
- Result/Evidence 조회 API와 unavailable/error 규칙
- Event Evidence Projection의 필드와 근거 의미
- Report grounding에서 참조할 Evidence/Activity 인계 계약
- Overlay Observation 이후 새 Product Result를 요청하거나 조회하는 공식 방식
- Backend가 `history_requirement` 충족 여부를 단독 판정하고, 부족하면 Prediction 없이
  지속 생성되는 다음 Observation을 기다리는 계약
- `warming_up`, `history_insufficient`, 첫 inference-ready Observation 처리 계약

#### 성민에게 확인할 것

- Recommendation에 표시 가능한 model status/factor 의미
- Model Artifact version과 Product Result provenance 연결 방식
- Closed-loop에서 사용하면 안 되는 Feature/Label 해석
- 대상 설비 Overlay pause/branch와 branch-local Simulation Clock 처리 방식
- `action_code`별 typed `state_patch` whitelist와 Overlay Observation provenance
- Model Artifact를 읽지 않는 지속 Overlay Observation 생성/available 방식과 stream
  종료·실패 상태 handoff

#### 우수와 합의할 것

- Product API의 소비·response envelope 원칙은
  `docs/closed-loop-product-consumption-contract.md`를 정본으로 사용하고 실제 OpenAPI 구현과 일치하는지 확인
- 사용자 역할별 권한과 Decision/Action 화면 상태는 canonical role + `available_actions` 계약과 일치하는지 확인
- E2E fixture ID 및 테스트 실행 순서
- Neon 등 공개 persistence 환경과 migration 적용 방식

### 9.2 광우가 넘길 것

#### 호범에게

- 실제 Decision, RecommendedAction, WorkOrder/MaintenanceAction
- MaintenanceEvent와 before/after 운영 상태
- 단계별 Integration 이벤트, `maintenance_completed_at`, `maintenance_event_id`,
  `state_version`과 정비 후 history segment lineage
- Report grounding의 입력으로 사용할 Activity와 actor/timestamp

광우는 위 운영 사실을 제공하고, 이를 Evidence와 결합해 Report 근거로 해석·매핑하는
계약과 문장 생성 규칙은 호범의 확정 계약을 따른다.

#### 우수에게

- OpenAPI 또는 기계 판독 가능한 요청·응답 계약
- 허용 상태 전이와 오류 코드
- 권한별 가능한 Action
- 안정된 E2E fixture와 reset/setup 방법
- Product Result/Evidence ID에서 Activity까지 이어지는 추적 예제

## 10. 테스트 계획

### Domain unit test

- Evidence 없는 Recommendation 생성 거부
- producer recommendation의 action ID·label·kind·approval requirement·basis 불변
- producer `kind`를 OperationalDecisionKind로 직접 재해석하지 않는지 확인
- `unavailable` recommendation materialization 거부
- 같은 Product Result/action ID의 중복 materialization 방지
- Operations 독자 recommendation과 producer projection origin 혼용 거부
- asset mapping 누락·중복·type 불일치 fail-fast
- Dataset Version 변경 후 stable Equipment identity 유지
- 승인 없는 정비 실행 Work Order/Action 생성 거부
- 승인·거절·보류 처리
- 정상 시작·완료 전이
- 완료 후 재완료 요청의 멱등성
- 완료 상태에서 과거 상태로 되돌리기 거부
- blocked/failed/cancelled 예외 흐름

### Repository/API test

- tenant/project/workspace 격리
- 역할별 권한과 CSRF
- 중복 idempotency key 처리
- 트랜잭션 실패 시 운영 변경과 outbox 전체 rollback
- outbox projection retry·idempotency·dead-letter 처리
- 재시작 후 persistence
- 기존 Event/Evidence/Decision API 하위 호환

### Ontology/integration test

- Equipment → RiskEvent → Evidence 관계 탐색
- RiskEvent → Decision/Recommendation → Work Order → MaintenanceAction 탐색
- 완료된 MaintenanceEvent가 올바른 Equipment와 Action을 참조
- 정비 전 Product Result와 정비 후 새 Product Result가 모두 보존
- Activity만으로 누가 언제 무엇을 판단·실행했는지 재구성

### 확정 E2E scenario

1. CNC 위험 Product Result/Evidence를 조회한다.
2. 동일 Equipment의 RiskEvent에 근거를 연결한다.
3. Diagnosis producer recommendation의 `kind`는 opaque로 보존하고 Event Evidence Projection의
   별도 `operational_decision_kind=request_inspection|review_shutdown`을 근거로
   `process_manager`가 `event_id`만 제출해 inspection WorkOrder를 요청·승인한다. Backend는
   같은 scope의 Diagnosis public query에서 canonical Projection을 다시 조회하여 Product
   Result/Evidence/Action ID, schema/policy version, Equipment identity와 decision을 서버에서
   확정하며 클라이언트가 제출한 lineage나 decision은 받지 않는다.
4. `process_engineer`가 inspection WorkOrder를 시작하고 checklist, measurements, findings,
   outcome, note를 포함한 불변 Inspection Result를 기록한다. 이 완료는 MaintenanceEvent나
   정비 승인이 아니다.
5. 점검 결과가 `maintenance_recommended`이면 Maintenance가 구조화된 checklist와
   measurements에서 `TOOL_REPLACEMENT` 또는 `COOLING_SYSTEM_RESTORE` Action 후보를
   산출한다. `process_manager`는 필요할 때 후보별 비용을 읽기 전용 참고정보로 확인할 수
   있지만 비용 option을 선택하거나 그 결과로 추천을 생성하지 않는다. 정비 판단을 내린
   경우에는 Inspection Result와 Action 후보를 근거로 별도 `origin=operations_manual`
   추천을 작성한다. 동일 inspection result/action은 stable ID와 idempotency/dedupe 규칙으로
   한 번만 생성한다.
   이때 `TOOL_REPLACEMENT`는 마모된 카바이드 절삭 인서트 1개 교체를 의미한다.
   비용 분석에서 `COOLING_SYSTEM_RESTORE`는 사내 냉각 경로 세척·막힘 해소·동작
   확인으로 한정하고, 부품 교체가 확인되면 별도 견적/Action basis를 사용한다.
6. `process_manager`가 Evidence와 엔지니어 결과를 확인하고 Operations recommendation을
   승인·거절·보류한다.
7. 정비가 필요한 경우 WorkOrder를 승인하고, API가 반환한 persisted ID를 다음 단계에 전달한다.
8. `maintenance_technician`이 배정된 WorkOrder/MaintenanceAction을 시작하고 체크리스트·측정값·note와
   함께 완료한다.

`operations_manual` 추천은 Diagnosis ProducerRecommendation과 같은 객체가 아니며 작성자/시각,
inspection source, Product Result/Evidence lineage, `operations-manual-recommendation-v1`, basis와
`requires_human_approval=true`를 보존한다. 별도 `RecommendationDecision(accept)`이 maintenance
WorkOrder를 생성하고, 이 시점에는 MaintenanceAction을 만들지 않는다.

후속 continuation은 다음과 같다.

1. MaintenanceEvent, Equipment state와 Activity가 함께 갱신된다.
2. 동일 mutation을 replay해 idempotency가 보장되는지 확인한다.
3. 대상 설비만 Runtime Overlay로 분기되고 다른 설비 Replay는 계속 진행한다.
4. `gen_data`가 Overlay Observation을 지속 생성하고 Backend가 각 available
   Observation의 `history_requirement`을 검증하며, 부족하면 다음 Observation을 기다린다.
5. Backend가 `ready`로 판정한 첫 inference-ready Observation으로 별도의 새 Product
    Result/Evidence가 생성된다.
6. 정비 전 Result → Decision → Action → 정비 후 Result를 끝까지 추적한다.

## 11. 완료 정의

다음 조건을 모두 만족해야 광우의 핵심 구현이 완료된 것으로 본다.

- 대표 CNC Event 한 건이 전체 Closed-loop를 통과한다.
- Product Result/Evidence의 예측 진실을 재계산하지 않는다.
- producer recommendation, 운영 materialization과 실제 Action이 구분되고 원본
  provenance가 보존된다.
- Dataset Version과 무관한 stable Equipment identity가 유지된다.
- 사람의 승인 없이 정비 실행 객체가 생성되지 않는다.
- 상태 전이, 권한, 멱등성, PostgreSQL transaction/outbox와 scope 격리가 테스트된다.
- 관계와 Activity로 판단 근거 및 실행 이력을 재구성할 수 있다.
- 정비 전후 Product Result가 별도로 보존되고 lineage로 연결된다.
- Canonical과 다른 설비 Replay를 변경하지 않고 대상 설비 Overlay로 정비 후 이력을
  생성한다.
- 정비 완료, warming-up과 실제 정상 Prediction을 구분한다.
- 호범의 Report와 우수의 Product/UI가 동일 Closed-loop 상태를 소비한다.
- 공개 persistence 환경의 E2E가 통과한다.

## 12. 착수 전 팀 확인 체크리스트

- [ ] 이 문서의 광우 담당 범위와 비담당 범위를 팀이 확인했다.
- [ ] 기존 Decision 값과 Target 상태 전이의 매핑을 확정했다.
- [ ] Work Order와 MaintenanceAction의 차이 및 생성 시점을 확정했다.
- [ ] MaintenanceEvent의 runtime 저장 위치를 확정했다.
- [ ] Runtime Overlay 단계별 이벤트, `maintenance_completed_at`, `state_version`, typed
      `state_patch`와 branch-local Fast-forward 계약을 확정했다.
- [ ] Backend만 정비 후 최소 이력을 Model Artifact의 `history_requirement`에서 계산하고
      readiness를 판정하기로 확정했다.
- [ ] Observation 지속 생성/available, stream 종료·실패 handoff와
      `history_insufficient` 전이 조건을 확정했다.
- [ ] `warming_up`, `history_insufficient`, `ready`, `predicted`의 Product 표현을
      확정했다.
- [ ] Product API canonical runtime-status read location은 versioned handoff 확정 후
      Backend integration 단계에서 결정하는 Deferred 항목으로 기록했다.
- [ ] Producer recommendation을 의미 변경 없이 운영 객체로 materialize하고 원본
      ID·Product Result/Evidence ID·schema/policy version·basis를 보존하기로 확정했다.
- [ ] `asset_id = equipment_id`, stable equipment key, fail-fast와 Dataset Version 변경
      시 identity 유지 규칙을 확정했다.
- [ ] PostgreSQL operational transaction + transactional outbox를 Closed-loop 원자성
      전략으로 확정했다.
- [ ] **PR 3 착수 gate:** Product Result/Evidence Schema·version·식별자·recommendation
      provenance·조회 API와 Event Evidence Projection/Report grounding 인계 계약을
      호범에게 받았다.
- [x] Product/API/UI 소비 원칙과 역할·Action·오류·E2E 계약을
      `closed-loop-product-consumption-contract.md`로 합의·문서화했다.
- [ ] 실제 Product API endpoint/OpenAPI payload가 canonical 소비 계약과 일치하는지 구현 PR에서 검증했다.
- [ ] 변경 예약 파일과 PR 순서를 팀 채널에 공유했다.
- [ ] 비용 분석과 What-if가 핵심 Operations 범위 밖임을 재확인했다.
- [ ] 이 문서 PR과 이후 구현 PR은 merge 전에 최신 `origin/main`을 반영하고
      architecture/backend-contract CI를 다시 통과시킨다.

체크리스트가 완료되기 전에는 공통 파일의 대규모 수정이나 새 API 구현을 시작하지
않는다. 다만 기존 코드 조사, Domain unit test 초안과 상태 매핑표 작성은 병행할 수
있다.
