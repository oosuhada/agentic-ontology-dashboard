# PR #128 기반 Runtime / Closed-loop 대범위 병렬 작업 제안

Status: draft
Date: 2026-08-26
Base: PR #128 `feat(operations): 역할별 overview와 asset detail 작업 흐름 정리`
Reference:

- PR #127 `Generator Runtime Prediction Result Pipeline 및 Outbox 전달 경계 구현`
- Issue #99 `Maintenance Loop Prototype 검증 근거 및 이식 전 계약 Gate`

## 1. 제안 목적

PR #128은 화면을 새로 확장하는 작업이 아니라, 사용자 업무 흐름을 다음처럼 정리한 PR이다.

```text
상황 확인
  -> 설비 선택
  -> 상태/근거 확인
  -> 처리 탭에서 작업 흐름 진입
  -> Report 출력
```

따라서 후속 작업은 화면을 더 만드는 것이 아니라, PR #128이 기다리는 Backend runtime result,
closed-loop state, available action, lineage를 실제 데이터로 채우는 것이다.

이번 제안은 작은 read-model 보강이 아니라 다음 end-to-end 범위를 하나의 큰 Integration
PR/stack acceptance 단위로 잡는다.

```text
sensor tick 자동 감지
  -> Generator observation consume
  -> Generator runtime inference
  -> Prediction Result Batch / Outbox
  -> Backend Prediction Inbox
  -> Backend validation / policy / idempotency
  -> Product Result append
  -> API/read model 갱신
  -> PR #128 UI live update
  -> Closed-loop 작업요청/정비/replay 연결
```

Generator Runtime 전환은 PR #127 머지 후 upstream prediction producer 계약으로 채택한다.
내가 먼저 진행할 첫 구현 단위는 Backend Prediction Inbox receive-only gate다. 즉 PR #127
Prediction Result Batch를 원본 그대로 받고, schema/checksum/scope/lineage/idempotency 검증과
rejection/conflict 상태를 닫은 뒤, 별도 후속 PR에서 Product Result/Evidence 승격 E2E로 확장한다.

## 2. 고정 원칙

1. PR #128 UI는 raw observation, raw score, Generator batch를 직접 소비하지 않는다.
2. Frontend는 `AssetDetailViewModel`, Product API, Maintenance API만 소비한다.
3. Closed-loop는 Product Result/Evidence/RecommendationDecision만 trigger로 사용한다.
4. Product Result Artifact는 append-only다. latest는 query 결과이지 저장 overwrite가 아니다.
5. Generator Runtime 전환이 승인되어도 Product Result/Evidence core 의미는 바꾸지 않는다.
6. Generator 산출물이 추가되면 core schema 재설계가 아니라 provenance/source trace로 연결한다.
7. Backend Diagnosis는 Product Result/Evidence 승격 gate를 맡는다.
8. Generator는 raw score / PR #127 Generator Prediction Result Batch producer contract를 끝까지 책임진다.
9. Backend direct inference 제거는 Generator delivery, Backend Inbox, Product Result 승격, rollback 가능 상태 확인 뒤 별도 마지막 PR로만 수행한다.

## 3. 큰 범위

포함:

- live/simulation observation available marker 감지
- Generator runtime observation/history consume
- Generator Prediction Result Batch / Outbox
- Backend Prediction Inbox/checksum/idempotency
- Backend validation/product policy
- Product Result Artifact / Evidence append
- runtime status/readiness API
- `AssetDetailViewModel`의 `current_result_summary` / `runtime_status`
- PR #128 UI polling/refetch 또는 replay signal 기반 live update
- Closed-loop 작업요청/승인/정비 mutation
- Maintenance replay -> post-maintenance Product Result
- Generator Runtime delivery와 failure status 검증

제외:

- Product Result/Evidence core 의미 변경
- Frontend의 raw score 직접 소비
- Closed-loop의 raw Generator batch 직접 소비
- Backend direct inference 선삭제

## 4. PR #128이 요구하는 후속 입력

PR #128의 Overview, Objects, Operations, Side Task View가 안정적으로 동작하려면 Backend가
다음 값을 제공해야 한다.

```text
risk
features.current
features.history.points
asset.criticality
operation_context
maintenance_context
review_priority
closed_loop summary
available_actions
data_status
evidence.gaps
current_result_summary
runtime_status
```

Frontend는 위 값을 계산하지 않는다. 값이 없으면 `null`, empty array, gap, unavailable reason으로
표시한다.

## 5. 병렬 Track

### Track A. Generator Runtime Prediction Producer

담당: Generator owner

이 Track은 PR #127 기반 upstream prediction path다. Generator는 Product Result/Evidence를 만들지
않지만, live/simulation observation을 consume해 Backend가 승격 가능한 Prediction Result Batch를
생산해야 한다.

책임:

- sensor/live output 또는 simulation overlay available marker 감지
- same-asset observation/history window 구성
- `history_requirement` 기반 readiness 판단
- Model Artifact snapshot/checksum 검증
- runtime feature 계산
- model inference
- Prediction Result Batch 생성
- Outbox retry/dead-letter
- Backend 응답 코드별 retry/stop 처리
- source/model/feature/history/maintenance lineage 전달

완료 기준:

- 새 tick 또는 overlay observation을 처리하면 Prediction Result Batch가 발행된다.
- 같은 tick을 재처리해도 중복 Batch가 생성되거나 중복 delivery되지 않는다.
- inference 불가 상태는 `warming_up`, `history_insufficient`, `failed_*`로 드러난다.
- Product Result/Evidence, severity, recommendation은 생성하지 않는다.

금지:

- history 부족 상태를 정상 score로 보정
- current observation을 history baseline에 중복 포함
- Product Result Artifact / Evidence 생성
- WorkOrder 또는 MaintenanceAction 생성

### Track B. Backend Prediction Inbox / Product Result Gate

담당: Backend Diagnosis / Product Result owner

이 Track이 PR #128과 Closed-loop를 실제 제품 흐름으로 살리는 critical path다. PR #127 머지 후
첫 Backend 작업은 Inbox receive-only gate로 시작한다. Backend는 Generator Prediction Result
Batch를 수신해 원본 payload와 검증 metadata를 보존하고, 검증된 결과만 다음 PR에서
Product Result/Evidence로 승격한다.

책임:

- Prediction Result Batch 수신
- contract/scope/checksum/lineage 검증
- `event_id + payload_sha256` idempotency/conflict 처리
- allowed source/model/status 검증
- receive-only 단계: schema/scope/checksum/lineage/idempotency 검증
- receive-only 단계: duplicate replay reuse, payload conflict fail-closed, rejection reason 저장
- 후속 승격 단계: threshold/status/recommendation product policy 적용
- 후속 승격 단계: `build_product_result_artifact()` 호출
- 후속 승격 단계: Product Result Artifact / Evidence append-only 저장
- 후속 승격 단계: runtime status/readiness record 생성
- 후속 승격 단계: latest/timeline/detail read model 갱신
- 후속 승격 단계: `AssetDetailViewModel` composer에 `current_result_summary`와 `runtime_status` 제공

Generator가 Backend로 넘기는 wire contract는 PR #127의
`prediction-result-batch.schema.json`를 단일 외부 정본으로 둔다. Backend Inbox는 payload
원본을 보존하고 `received_at`, `payload_sha256`, `validation_status`, `rejection_reason`,
`promotion_result_id` 같은 수신/검증 metadata만 덧붙인다. 아래 항목은 Inbox가 검증해야 할
의미적 최소 조건이며, 별도 schema shape를 다시 정의하지 않는다.

```text
batch_id
event_id
producer.id
producer.version
emitted_at
payload_sha256
results[].asset_id
results[].observed_at
results[].score
results[].output_status
results[].failure_reason
results[].source_ref.uri
results[].source_ref.sha256
results[].model_set_id
results[].model_id
results[].model_version
results[].model_artifact_manifest_sha256
results[].feature_schema_version
results[].feature_schema_sha256
results[].history_requirement_version
results[].history_requirement_sha256
results[].lineage
```

Simulation / maintenance replay source이면 추가:

```text
source_kind
maintenance_event_id
maintenance_action_id
overlay_branch_id
history_segment_id
state_version
simulation_session_id
```

금지:

- Generator가 누락한 feature/history/source lineage를 Backend에서 추론해 보정
- raw score를 Product Result 없이 Frontend/Closed-loop에 노출
- asset 기준 overwrite로 기존 Product Result를 갱신
- Evidence를 UI/ViewModel consumer에서 재생성

### Track C. Backend Direct Inference Baseline / Rollback

담당: Backend Diagnosis / Product Result owner

이 Track은 새 canonical upstream이 아니라 migration 안전장치다. PR #127 기반 Generator delivery와
Backend Inbox/Product Result E2E가 안정화되기 전까지 기존 Backend direct inference는 baseline 또는
rollback path로만 기록한다.

책임:

- 기존 Backend direct inference entrypoint 목록화
- feature flag 또는 운영 비활성화 조건 정의
- Generator path 장애 시 rollback 기준 정의
- 동일 observation에 대한 parity/mismatch evidence 수집
- 제거 PR의 acceptance criteria 정의

구현 우선순위:

1. Generator Prediction Result Batch -> Backend Product Result E2E를 먼저 통과시킨다.
2. 기존 Backend direct inference가 동시에 Product Result를 만들지 않게 flag를 정리한다.
3. rollback이 필요한 상태와 허용 환경을 문서화한다.
4. 제거는 별도 마지막 PR로 진행한다.

금지:

- Product Result 이중 생성
- Backend direct inference를 장기 canonical path로 재고정
- rollback path를 UI/Closed-loop 별도 소비 계약으로 노출

### Track D. Closed-loop Domain / Maintenance API

담당: Closed-loop owner

Issue #99 기준으로 Inspection, Recommendation, Decision, WorkOrder, MaintenanceEvent의 기본
상태 전이와 이식 Gate는 상당 부분 마련되어 있다. PR #128 후속에서는 이 상태를 화면이 소비할 수
있는 read model과 mutation response로 연결하고, Maintenance replay trigger까지 end-to-end로 잇는다.

책임:

- Product Result/Evidence 기반 Inspection 후보 연결
- RecommendationDecision / WorkOrder / MaintenanceAction 상태 전이
- idempotency key 처리
- role/permission/scope 검증
- Activity append
- MaintenanceEvent 완료
- replay request 발행
- runtime status와 post-maintenance Product Result를 작업 상태에 연결
- `closed_loop` summary와 `available_actions` 제공

PR #128에 넘겨야 하는 최소 contract:

```text
closed_loop.event_status
closed_loop.work_orders[]
closed_loop.maintenance_actions[]
closed_loop.maintenance_events[]
closed_loop.activities[]
available_actions[]
disabled_reason
lineage references
```

금지:

- raw Generator score로 작업요청 생성
- Product Result/Evidence 없이 RecommendationDecision 생성
- 정비 완료를 정상 Product Result로 표시
- Frontend가 WorkOrder ID나 action state를 합성하게 만들기

### Track E. Frontend PR #128 Live Integration

담당: Frontend / Product API owner

PR #128 UI는 이미 read surface를 제공한다. 후속은 raw data 계산이 아니라 API 연결과 live refresh이다.

책임:

- Backend `AssetDetailViewModel` 우선 소비
- latest/timeline/evidence/detail refetch
- `current_result_summary`와 `runtime_status` 분리 표시
- `closed_loop` summary 표시
- `available_actions` 기반 버튼/disabled state 표시
- `history_insufficient`, `warming_up`, `data_quality_hold`, evidence gap 표시
- replay/live signal 수신 후 Product API refetch
- 새 Product Result 감지 후 Overview/Side Task View/Report entry 갱신

금지:

- raw JSONL, Generator batch, raw score 직접 해석
- probability threshold로 frontend status 재계산
- WorkOrder ID, Recommendation state, permission 합성
- missing runtime 값을 `0`, `normal`, `low`, `false`로 보정

## 6. 병렬 진행 방식

병렬 진행의 공통 경계는 Product Result/Evidence와 PR #128 ViewModel이다.
Generator migration을 병렬로 열 경우에도 Generator -> Backend wire contract는 PR #127의
`prediction-result-batch.schema.json`을 단일 외부 정본으로 참조한다. PR #129는
Backend Inbox wrapper와 validation metadata 위치만 계획한다.

```text
Track A Generator Runtime Prediction
  -> Prediction Result Batch / Outbox

Track B Backend Prediction Inbox
  -> validation / policy / Product Result/Evidence append

Track C Backend Direct Inference
  -> baseline / rollback / removal gate

Track D Closed-loop
  -> Product Result/Evidence 기반 작업 상태 전이

Track E Frontend
  -> PR #128 live read surface API 연결
```

초기 진행 정본은 PR #127 머지 후 Backend Inbox receive-only gate를 먼저 닫고, 그 다음
Generator Prediction Result Batch를 Backend가 승격하는 경로로 확장하는 것이다.

```text
1. PR #127을 머지해 Generator Runtime Prediction Result Batch/Outbox를 upstream producer 계약으로 고정한다.
2. 내가 Backend Prediction Inbox receive-only gate를 먼저 구현한다.
3. Backend가 검증된 Inbox record만 Product Result/Evidence로 승격한다.
4. PR #128 UI는 Backend Product API/ViewModel 변화를 refetch한다.
5. Closed-loop는 Product Result/Evidence 기반으로 작업요청/정비/replay를 연결한다.
6. rollback 가능 상태 확인 후 기존 Backend direct inference 제거를 별도 마지막 PR로 진행한다.
```

## 7. 큰 범위 구현 순서

### Step 1. Backend Prediction Inbox receive-only gate

- PR #127 `prediction-result-batch.schema.json` payload를 Backend가 원본 그대로 수신한다.
- Inbox record에 `received_at`, `payload_sha256`, `validation_status`, `rejection_reason`,
  `promotion_result_id` 같은 Backend metadata만 추가한다.
- schema/scope/checksum/lineage/idempotency를 검증한다.
- duplicate replay는 기존 receive record를 재사용하고, 같은 `event_id`의 다른 payload는 conflict로 남긴다.
- receive-only 단계에서는 Product Result/Evidence, ViewModel, Closed-loop trigger를 만들지 않는다.

완료 기준:

- valid PR #127 batch가 Inbox receive record로 보존된다.
- invalid schema/checksum/scope/lineage batch가 rejected 상태로 남는다.
- duplicate/conflict 케이스가 deterministic하게 검증된다.
- Backend가 Generator Python 구현을 import하지 않는다.

### Step 2. Runtime tick consume / idempotency

- live sensor 또는 simulation overlay available marker를 Generator worker가 감지한다.
- 처리 cursor, source checksum, consume status를 저장한다.
- duplicate tick은 skip/reuse하고 checksum conflict는 fail-closed로 남긴다.

완료 기준:

- 같은 marker를 두 번 처리해도 Product Result가 중복 생성되지 않는다.
- 처리 실패 상태가 runtime status로 조회된다.

### Step 3. Observation -> Diagnosis execution

- Generator가 새 observation과 same-asset history window를 구성한다.
- Generator가 `history_requirement`를 확인한다.
- 준비되면 Generator runtime inference를 실행하고 Prediction Result Batch를 만든다.
- 부족하면 Product Result를 만들지 않고 `warming_up`/`history_insufficient`를 전달한다.

완료 기준:

- current observation이 history에 섞이지 않는다.
- inference 가능한 tick에서 Generator runtime prediction이 실행된다.
- 불가능한 tick은 정상으로 보정되지 않는다.

### Step 4. Backend Prediction Inbox -> Product Result/Evidence append

- 기존 Product Result/Evidence core 계약을 유지한다.
- Backend가 Prediction Result Batch의 contract/scope/checksum/lineage/idempotency를 검증한다.
- `build_product_result_artifact()`로 Artifact를 생성한다.
- 새 runtime result는 새 artifact/result ID로 append한다.
- latest는 query에서 선택한다.

완료 기준:

- 같은 asset의 정비 전/후 Result가 둘 다 조회된다.
- 기존 Result가 overwrite되지 않는다.
- Evidence projection/report consumer가 raw input을 재생성하지 않는다.

### Step 5. Runtime status + AssetDetailViewModel + API

- `current_result_summary`와 `runtime_status`를 분리한다.
- Product Result 판단 시점과 runtime 진행 시점을 따로 노출한다.
- PR #128 UI가 필요한 `risk`, `data_status`, `evidence.gaps`, `closed_loop` summary를 내려준다.

완료 기준:

- Overview, Side Task View, Operations, Report entry가 같은 ViewModel snapshot을 소비한다.
- runtime 대기/실패 상태가 기존 Product Result를 덮어쓰지 않는다.

### Step 6. Frontend live update

- polling 또는 replay/live signal로 runtime status/latest result 변화를 감지한다.
- 변화가 있으면 latest/detail/evidence/ViewModel API를 refetch한다.
- raw observation/raw score는 화면에 직접 반영하지 않는다.

완료 기준:

- 새 Product Result가 생기면 #128 Overview와 Side Task View가 갱신된다.
- `history_insufficient`/`warming_up`이 UI에 별도 상태로 표시된다.

### Step 7. Closed-loop mutation/API 연결

- 작업요청, 승인, 점검 시작/완료, RecommendationDecision, MaintenanceAction을 API로 연결한다.
- mutation 응답은 persisted ID와 resulting state를 반환한다.
- `available_actions`는 Backend가 계산한다.

완료 기준:

- PR #128 처리 탭이 persisted ID/state만 표시한다.
- 권한 없는 액션은 disabled reason 또는 403으로 일관되게 처리된다.

### Step 8. Generator Runtime delivery integration

- Generator score batch를 Backend Inbox에 전달한다.
- Backend는 검증 전 score/source/model lineage를 Product API/UI/Closed-loop에 노출하지 않는다.
- delivery failure와 mismatch는 runtime status로 남긴다.

완료 기준:

- delivery retry, dead-letter, mismatch 처리 규칙이 문서화된다.
- Generator 산출물 누락을 Backend가 추론 보정하지 않는다.

### Step 9. Maintenance replay / simulation overlay 연결

- MaintenanceEvent 완료 후 replay request를 발행한다.
- Runtime Overlay observation available을 Generator Runtime Pipeline이 소비한다.
- replay source kind는 공식 계약의 `maintenance_replay_overlay`를 사용한다.
- 이력 부족이면 `warming_up`/`history_insufficient`를 표시한다.
- 첫 inference-ready observation에서 Generator가 Prediction Result Batch를 발행한다.
- Backend Inbox delivery가 연결된 뒤에만 Batch 검증과 새 Product Result/Evidence append를 수행한다.

완료 기준:

- PR #128 UI에서 정비 전/후 상태가 같은 asset lineage로 비교된다.
- `simulation_session_id`, `overlay_branch_id`, `history_segment_id`,
  `maintenance_event_id`, `maintenance_action_id`, `state_version` lineage가 보존된다.

### Step 10. Backend direct inference 제거 여부 결정

- 팀 승인, Generator delivery, Backend Inbox, Product Result/Evidence E2E, rollback 조건이 모두 충족되면 제거한다.
- 제거 전까지 Backend direct inference는 baseline/fallback path로만 둔다.
- 제거 후에도 Product Result/Evidence core 계약은 유지한다.

완료 기준:

- Product Result 생성 source flag가 하나만 활성화된다.
- Backend direct inference 제거는 별도 후속 PR로 진행한다.

## 8. Contract Freeze

현재 구현된 receive-only 범위:

- `contracts/schemas/prediction-result-batch.schema.json`
- Backend typed validator `PredictionResultBatch`
- public receive endpoint:
  `POST /api/projects/{project_id}/workspaces/{workspace_id}/predictive-maintenance/prediction-result-batches`
- internal receive endpoint:
  `POST /internal/prediction-results?project_id=...&workspace_id=...`
- `pm_prediction_result_inbox_batches` / `pm_prediction_result_inbox_items`
- raw payload 보존, schema/checksum/scope/idempotency 검증, duplicate/conflict/rejected receipt
- service-to-service 송신 계약:
  Backend `PREDICTION_RESULT_INGEST_TOKEN`과 Generator `GENERATOR_PREDICTION_RESULT_TOKEN`을
  같은 secret으로 설정하고 `Authorization: Bearer ...`로 호출

이 범위는 Product Result 생성, Evidence append, ViewModel 갱신, Closed-loop trigger를 수행하지 않는다.

### 유지

- Product Result core:
  - `failure_probability`
  - `status_grade`
  - `top_factors`
  - `recommended_action`
  - `evidence_payload`
- Event Evidence projection 의미
- AssetDetailViewModel 소비 의미
- Closed-loop trigger 의미

### Additive만 허용

- source/provenance reference
- runtime status/readiness
- maintenance/replay lineage
- Generator event/batch reference

### 금지

- Product Result를 Generator batch로 대체
- raw score를 UI/Closed-loop trigger로 사용
- schema 확장을 이유로 fixture truth를 먼저 창작
- existing Product Result overwrite

## 9. E2E 목표

### E2E A. Sensor tick to UI live update

```text
sensor tick / observation available
  -> Generator consume
  -> Generator Runtime Prediction
  -> Prediction Result Batch / Outbox
  -> Backend Prediction Inbox validation
  -> Product Result/Evidence append
  -> runtime status predicted
  -> AssetDetailViewModel updated
  -> PR #128 Overview/Side Task View refetch
```

### E2E B. PR #128 runtime read

```text
Product Result/Evidence exists
  -> AssetDetailViewModel composed
  -> Overview risk queue 표시
  -> Side Task View 상태/처리 표시
  -> Report 출력 진입
```

### E2E C. 작업요청 수집

```text
Product Result/Evidence
  -> Inspection candidate
  -> WorkOrder request
  -> approve/start/complete
  -> Activity append
  -> PR #128 처리 탭 refetch
```

### E2E D. 정비 후 재예측

```text
MaintenanceAction complete
  -> MaintenanceEvent
  -> replay requested
  -> Runtime Overlay Observation available
  -> Generator readiness / Prediction Result Batch
  -> Backend Prediction Inbox validation
  -> post-maintenance Product Result/Evidence
  -> PR #128 UI pre/post 비교
```

### E2E E. Generator delivery failure

```text
Generator score batch
  -> Backend Inbox 검증 실패
  -> runtime status failed_*
  -> 기존 Product Result는 overwrite되지 않음
```

## 10. 팀 합의가 필요한 결정

1. 큰 Integration PR의 acceptance criteria를 sensor tick -> UI live update까지로 볼지.
2. PR #127 기반 Generator Runtime을 upstream prediction producer로 freeze할지.
3. Backend direct inference를 baseline/fallback으로만 남길지.
4. PR #127 Generator Prediction Result Batch를 어떤 후속 PR에서 additive 확장할지, 그리고
   Backend Inbox receive metadata를 어디에 저장/노출할지.
5. 정비 후 runtime status의 public read location을 `AssetDetailViewModel` summary와 상세 Product API 중 어디까지 노출할지.
6. 기존 Backend direct inference 제거 시점을 어떤 gate 이후로 둘지.

## 11. 결론

PR #128을 기준으로 보면 후속 작업의 중심은 UI 확장이 아니라 Backend/Product/Closed-loop 데이터
연결과 runtime execution E2E다. PR #127 기반 Generator Runtime은 upstream prediction producer로
병렬 개발할 수 있지만, PR #128 UI와 Closed-loop는 계속 Backend Product Result/Evidence만 소비해야 한다.

권장 진행은 다음이다.

```text
PR #128 read surface 확정
  -> Generator Runtime Prediction / Prediction Result Batch
  -> Backend Prediction Inbox / Product Result append-only path
  -> runtime status + UI live update
  -> Closed-loop mutation/API 연결
  -> maintenance replay/post-result E2E
  -> Backend direct inference 제거 여부 결정
```
