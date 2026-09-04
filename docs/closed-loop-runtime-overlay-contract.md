# Closed-loop Runtime Overlay 통합 계약

## 1. 문서 지위와 목적

이 문서는 최종 예지보전 시연에서 정비 결과를 새로운 Observation과 Runtime
Prediction으로 연결하는 시스템 간 Target 계약이다.

기존 계약과의 책임은 다음처럼 나눈다.

| 문서 | 책임 |
|---|---|
| `closed-loop-domain-contract.md` | Recommendation, Decision, WorkOrder, MaintenanceAction, MaintenanceEvent의 상태와 불변식 |
| `closed-loop-product-consumption-contract.md` | Product API/UI의 역할, Action, 상태·오류 소비 방식 |
| 이 문서 | Closed-loop 완료 이벤트 → 대상 설비 Runtime Overlay → Generator 런타임 추론 및 Backend 판정 연결 |
| `closed-loop-implementation-plan.md` | 구현 PR 순서와 담당자별 인계 |

이 문서는 Canonical V3.1 또는 과거 Result/Evidence를 수정하는 계약이 아니다.
Closed-loop가 발행하는 `maintenance.*` 기계 판독 계약은
`contracts/schemas/maintenance-replay-event.schema.json`에서 versioned JSON Schema로
고정한다. `gen_data`가 발행하는 `runtime_overlay.observations.available` 계약은 해당
producer와 Generator/Backend consumer가 별도 Schema로 확정한다.

## 2. 결정 요약

- 전체 Generator를 재구축하지 않는다.
- 정비 대상 설비만 기존 Replay에서 Runtime Overlay로 분기한다.
- 정비 중 대상 설비의 정상 센서 Replay와 Runtime Prediction을 중단한다.
- 다른 설비의 Replay는 계속 진행한다.
- 정비 완료 후 Snapshot에 정비 효과를 반영한다.
- 실제 시간만큼 기다리지 않고 **대상 설비 Overlay branch의 Simulation Clock만**
  Fast-forward하여 정비 후 Observation 생성을 재개하고 지속한다.
- 필요한 Observation 수와 이력 충족 여부는 Generator 런타임 파이프라인이 현재 Model Artifact의
  `history_requirement.json`으로 계산한다. `gen_data`는 Model Artifact를 읽거나
  inference readiness를 판정하지 않는다.
- Generator는 첫 번째 `inference-ready` Observation에서 신규 Runtime Prediction(`score`)을 산출하여
  Backend로 `Prediction Result Batch`를 송신하고, Backend는 Threshold 적용을 통해 새 Product Result/Evidence를 생성한다 (Backend 수신 및 판정은 `후속 구현` 대상).
- Canonical, 정비 전 Observation, 정비 전 Product Result/Evidence는 immutable하게
  보존한다.
- 정비 완료 자체를 정상 판정으로 사용하지 않는다.
- 정비 효과를 비교하는 정비 전 기준 Result와 정비 후 Overlay Result는 동일한
  `model_id`, immutable `model_version`, Model Artifact manifest checksum 및 판정
  threshold 정책을 사용한다. 하나라도 다르면 정비 효과 개선으로 비교하지 않고
  `model_lineage_mismatch`로 처리한다.
- 활성 Model Artifact가 변경된 경우 정비 후 결과에만 새 모델을 적용하지 않는다.
  새 모델로 정비 전 Observation을 다시 산출한 별도 baseline과 정비 후 Overlay를
  함께 평가하거나, 기존에 고정된 Artifact로 해당 정비 비교를 완료한다.

## 3. 전체 흐름

```text
gen_data observation
  → Generator preprocessing/runtime feature
  → Generator model score inference
  → Prediction Result Batch
  → Backend threshold and decision (후속 구현)
  → Diagnosis / Report / Evidence / Notification (후속 구현)
  → 필요 시 Backend가 재학습 또는 후속 조치 지시 (후속 구현)
```

Closed-loop 책임 원칙:
- **추론 실행**: Generator (Preprocessing → Runtime Feature → Model score inference → Prediction Result Batch 송신)
- **threshold 및 최종 판정**: Backend (후속 구현)
- **유지보수·재학습 지시**: Backend (후속 구현)
- **Overlay Observation 생성**: `gen_data` (관측 데이터 생성자, readiness 미판정)
- **Report/Evidence/알림**: Backend (후속 구현)

## 4. Canonical과 Runtime Overlay 분리

Canonical/source reference Replay는 계속 read-only다. Canonical CSV에 없는 값을
Canonical Replay가 생성한다고 표현하지 않는다.

Runtime Overlay는 Closed-loop 시연을 위한 별도의 opt-in 실행 경로다.

```text
Canonical 예정값
220 → 221 → 222 → 223 ...
            │ TOOL_REPLACEMENT
            └─ 기존 예정값 재개 금지

Runtime Overlay branch
0 → 1 → 2 → 3 ...
```

다음 데이터는 수정하지 않는다.

- Canonical source와 reference fixture
- 정비 전 Observation
- 정비 전 Product Result/Evidence
- 기존 Recommendation, Decision, WorkOrder, MaintenanceAction, MaintenanceEvent

정비 후 Runtime state, Observation과 Result/Evidence는 append-only로 추가한다.

## 5. 설비 상태와 Maintenance gap

```text
RUNNING
  │ maintenance.started
  ▼
MAINTENANCE
  │ maintenance.completed + effect 적용
  ▼
RESTARTING
  │ restart_at 도달 + history 준비
  ▼
RUNNING
```

- `maintenance.started`부터 대상 설비의 정상 센서 Observation과 Prediction을 중단한다.
- Maintenance gap을 정상값이나 센서값 `0`으로 채우지 않는다.
- 정비 상태는 센서 Observation이 아니라 운영 상태와 Activity로 표현한다.
- `maintenance_completed_at`이나 `restart_at`이 늦게 오면 pause 상태를 유지한다.
- Timeout만으로 자동 재개하지 않는다.
- 다른 설비의 Replay Clock과 데이터 생성은 영향을 받지 않는다.

## 6. 단계별 Integration 이벤트

### 6.1 `maintenance.started`

Closed-loop가 발행하고 Runtime Overlay consumer가 소비한다.

- 대상 설비를 `MAINTENANCE`로 전환
- 대상 설비 정상 Replay·Prediction pause
- 중복 수신 시 동일 결과 replay
- 완료된 MaintenanceEvent는 아직 존재하지 않으므로 `maintenance_action_id`를 lifecycle
  correlation key로 사용하고 `maintenance_event_id`를 임의 생성하지 않는다.

### 6.2 `maintenance.completed`

MaintenanceAction, WorkOrder와 MaintenanceEvent가 Domain 계약에 따라 완료된 transaction에서
Outbox에 적재한다.

- 공유 이벤트 완료 시각 필드명은 `maintenance_completed_at`을 사용한다.
- 내부 Domain/DB의 `completed_at`은 유지할 수 있으며 발행 adapter에서 매핑한다.
- `action_code`와 정비 효과를 검증한다.
- 완료만으로 Replay를 재개하거나 정상으로 판정하지 않는다.

### 6.3 `maintenance.replay_requested`

- 완료된 MaintenanceEvent가 존재해야 한다.
- `restart_at >= maintenance_completed_at >= maintenance_started_at`이어야 한다.
- `restart_at` 이후 대상 설비 Overlay branch에서만 Observation 생성을 재개한다.
- `restart_at`이 미래이면 해당 virtual time까지 대기한다.
- 이미 지난 경우 최초 가능한 Overlay tick부터 생성한다.
- 재개 후에는 Backend의 추가 요청 없이 Simulation Session의 정상 tick 정책에 따라
  Observation 생성을 지속한다. 명시적인 Session 종료, 새 `maintenance.started` 또는
  생성 실패가 있을 때만 중단한다.

### 6.4 발행·소비 경계

기계 이벤트 이름은 기존 Outbox의 소문자 dot notation을 따른다.

| event type | producer | consumer | 역할 |
|---|---|---|---|
| `maintenance.started` | Closed-loop | `gen_data` Runtime Overlay adapter | 대상 설비 pause |
| `maintenance.completed` | Closed-loop | `gen_data` Runtime Overlay adapter | 완료 사실과 effect 전달 |
| `maintenance.replay_requested` | Closed-loop | `gen_data` Runtime Overlay adapter | restart/branch 생성 요청 |
| `runtime_overlay.observations.available` | `gen_data` Runtime Overlay | Generator / Backend ingestion adapter | 생성 완료된 batch와 Observation 범위 인계. readiness 의미 없음 |

로컬 및 Mac mini 시연의 Closed-loop outbound transport는
`app.maintenance_replay_dispatcher`가 담당한다. 이 worker는 현재 Organization/Project
scope의 transactional outbox에서 위 `maintenance.*` 세 종류만 claim하고,
`maintenance-replay-v1` Schema를 다시 검증한 뒤 `gen_data`가 소비하는 JSONL inbox에
durable append한다. 다른 Domain의 Outbox 이벤트는 claim하지 않는다.

파일 append 이후 DB delivery 완료 기록 전에 process가 중단되면 같은 이벤트가 다시
전달될 수 있다. JSONL adapter와 `gen_data` consumer는 동일 `event_id`와 payload의 재수신을
멱등 처리하고, 같은 ID의 다른 payload는 conflict로 거부한다. retry/dead-letter와 lease
만료 복구는 Backend Outbox worker가 담당한다. 이 JSONL transport는 adapter이므로 향후
broker로 교체해도 Maintenance Domain event와 Schema는 변경하지 않는다.

Generator 런타임 파이프라인은 `maintenance.*` 이벤트만 보고 Prediction하지 않는다.
`runtime_overlay.observations.available`의 branch가 append-only Overlay 저장소에 반영된
뒤 해당 Observation과 현재 Model Artifact의 `history_requirement.json`을 읽어 history requirement를 평가한다.
`gen_data`는 Observation batch와 progress를 durable commit한 뒤 available 이벤트를
발행한다. 같은 persistence를 사용하면 transactional outbox로 함께 commit하고, 다른
persistence라면 recoverable delivery record와 idempotent publish retry를 사용해 데이터만
남고 이벤트가 유실되는 dual-write gap을 막는다. Generator/Backend가 available 이벤트를 수신할 때
저장 reference를 읽을 수 있어야 한다. 비동기 저장소의 일시적인 가시성 지연은 새 event를
만들지 않고 동일 event의 멱등 consumer retry로 처리한다.

`gen_data`는 `maintenance.replay_requested` 이후 해당 branch의 Simulation Clock 정책에
따라 Observation을 계속 생성한다. `available`은 Generator/Backend가 저장된 Observation을 소비할
수 있다는 뜻이며 inference-ready를 뜻하지 않는다. 이력이 부족하면 Generator는
역방향 생성 요청을 발행하지 않고 다음 `available` Observation을 기다린다. 충분하면
`ready`로 전이해 추론 점수를 계산하고 `Prediction Result Batch`를 Backend로 송신한다 (Backend 수신 및 Threshold 판정은 `후속 구현`). Closed-loop 소유 이벤트는
`contracts/schemas/maintenance-replay-event.schema.json`을 따르며,
Overlay Observation과 `runtime_overlay.observations.available`은 각각
`contracts/schemas/runtime-overlay-observation.schema.json`과
`contracts/schemas/runtime-overlay-observations-available.schema.json`을 따른다.

## 7. 멱등성과 순서

| 필드 | 목적 |
|---|---|
| `maintenance_action_id` | 시작부터 완료까지의 lifecycle correlation |
| `maintenance_event_id` | 완료 이후 정비 전후 업무 lineage |
| `idempotency_key` | 동일 delivery의 중복 여부 |
| `state_version` | Closed-loop가 발행하는 `maintenance.*` lifecycle 순서와 최신성 |

- Closed-loop event producer가 동일
  `simulation_session_id + equipment_id + maintenance_action_id` 범위에서
  `state_version`을 단조 증가시킨다.
- `maintenance.started`, `maintenance.completed`, `maintenance.replay_requested`의
  일반적인 version은 각각 `1`, `2`, `3`이지만 consumer는 event type 문자열 정렬이
  아니라 전달된 version과 Domain 선행 조건을 함께 검증한다.
- 동일 key와 동일 payload는 기존 처리 결과를 반환한다.
- 동일 key에 다른 payload는 conflict다.
- `maintenance.*`의 낮은 `state_version`은 stale event로 거절하거나 명시적으로 무시한다.
- `maintenance.*`의 동일 version과 동일 payload는 멱등 처리한다.
- `maintenance.*`의 동일 version에 다른 payload는 conflict다.
- 완료되지 않은 Maintenance의 restart 요청은 처리하지 않는다.
- `available` 이벤트의 `state_version`은 원인이 된 maintenance lifecycle version의
  lineage이며 batch 순서가 아니다. 반복 batch는 고유 `event_id`/`idempotency_key`와
  단조 증가하는 Observation range로 구분한다.

## 8. 정비 효과 계약

Operations의 두 Maintenance Action은 Action별 typed patch를 사용한다.

```json
{
  "action_code": "TOOL_REPLACEMENT",
  "state_patch": {
    "tool_wear_min": {
      "operation": "reset",
      "value": 0,
      "unit": "min"
    }
  }
}
```

```json
{
  "action_code": "COOLING_SYSTEM_RESTORE",
  "state_patch": {
    "cooling_system_state": {
      "operation": "restore",
      "value": "nominal",
      "unit": "state"
    }
  }
}
```

- `action_code`별 허용 field, operation, value, unit을 whitelist한다.
- `TOOL_REPLACEMENT`는 승인된 공구 마모 상태만 변경한다.
- `COOLING_SYSTEM_RESTORE`는 냉각계통을 정상 상태로 복구하라는 명령만 표현한다.
  실제 post-maintenance 온도 Observation은 Generator가 같은 Simulation Session의
  Overlay 규칙으로 생성하며 Maintenance가 임의의 센서값을 작성하지 않는다.
- 허용되지 않은 필드나 단위는 fail-fast한다.
- patch는 Canonical이 아니라 해당 Simulation Session의 Overlay Snapshot에만 적용한다.
- Closed-loop의 immutable `MaintenanceEvent`에는 위 typed patch 명령을 그대로 보존하고,
  운영 `Equipment state`에는 명령 객체가 아니라 적용된 현재값
  (`tool_wear_min: {value: 0, unit: "min"}` 또는
  `cooling_system_state: {value: "nominal", unit: "state"}`)을 저장한다.
- 향후 범용화할 때는 versioned `maintenance_effect` 계약으로 확장할 수 있다.

## 9. 이벤트 최소 필드

```json
{
  "contract_version": "maintenance-replay-v1",
  "event_type": "maintenance.replay_requested",
  "event_id": "EVT-001",
  "idempotency_key": "MAINT-001:3",
  "state_version": 3,
  "simulation_session_id": "DEMO-001",
  "maintenance_event_id": "MAINT-001",
  "maintenance_action_id": "ACTION-001",
  "work_order_id": "WO-001",
  "equipment_id": "CNC-S02-L04-03",
  "maintenance_started_at": "...",
  "maintenance_completed_at": "...",
  "restart_at": "...",
  "action_code": "TOOL_REPLACEMENT",
  "state_patch": {
    "tool_wear_min": {
      "operation": "reset",
      "value": 0,
      "unit": "min"
    }
  },
  "caused_by": {
    "source_product_result_id": "RESULT-001",
    "source_evidence_id": "EVIDENCE-001",
    "decision_id": "DEC-001"
  }
}
```

모든 시각과 완료 ID를 최초 이벤트에 강제하지 않는다. 이벤트별 required field는
다음과 같이 구분하고 최종 JSON Schema에서 고정한다.

| event type | 추가 required field |
|---|---|
| 모든 이벤트 공통 | `contract_version`, `event_type`, `event_id`, `idempotency_key`, `simulation_session_id`, `maintenance_action_id`, `equipment_id` |
| `maintenance.*` 공통 | `state_version` |
| `maintenance.started` | `work_order_id`, `maintenance_started_at`, `action_code` |
| `maintenance.completed` | `maintenance_event_id`, `maintenance_completed_at`, `action_code`, `state_patch` |
| `maintenance.replay_requested` | `maintenance_event_id`, `restart_at` |
| `runtime_overlay.observations.available` | `maintenance_event_id`, `overlay_branch_id`, `history_segment_id`, Observation 범위·개수와 저장 reference |

`runtime_overlay.observations.available`의 `contract_version`은
`runtime-overlay-observations-available-v1`이다. `batch_rows`와 `observed_from`/`observed_to`는
이번 이벤트가 새로 알리는 delta batch를 뜻하고, `generated_rows`는 같은 branch에서 지금까지
생성된 누적 행 수다. `storage_reference`는 producer 로컬 절대경로가 아니라 stream root 기준
상대경로만 허용한다. 파일 경로에는 논리 ID를 치환해 직접 넣지 않는다. 대신
`[simulation_session_id, overlay_branch_id]` 배열을 공백 없는 JSON으로 직렬화하고 Unicode를
escape하지 않은 UTF-8 byte에 대해 lowercase SHA-256 digest를 사용한다.

```text
runtime_overlay/
  sha256-<sha256(canonical UTF-8 identity pair)>.jsonl
```

따라서 `.`, `..`와 구두점이 포함된 논리 ID도 path segment로 해석되지 않으며 서로 다른
ID가 replacement sanitizer 때문에 같은 파일로 합쳐지지 않는다. consumer는 이 경로를
다시 계산하고 최종 resolved path가 stream root 내부인지 확인해야 한다.

## 10. Overlay branch와 Simulation Clock

Fast-forward는 전체 Session Clock에 적용하지 않는다.

```text
Canonical Replay Clock
├── CNC-01 계속 진행
├── CNC-02 pause
│   └── CNC-02 Overlay branch clock만 Fast-forward
└── CNC-03 계속 진행
```

- 대상 설비 branch의 `observed_at`은 단조 증가해야 한다.
- `restart_at` 이전 Overlay Observation은 생성하지 않는다.
- `observed_at`은 virtual observation time이다.
- `generated_at`은 시스템이 실제로 레코드를 생성한 wall-clock time이다.
- 같은 Canonical version, seed, Snapshot과 정비 효과로 재실행하면 동일한 Overlay를
  재현할 수 있어야 한다.

## 11. Overlay Observation과 lineage

```json
{
  "contract_version": "runtime-overlay-observation-v1",
  "observation_id": "OBS-POST-001",
  "equipment_id": "CNC-S02-L04-03",
  "observed_at": "...",
  "generated_at": "...",
  "source_kind": "maintenance_replay_overlay",
  "base_dataset_version": "canonical-v3.1",
  "base_source_sha256": "<sha256>",
  "observation_sha256": "<sha256>",
  "simulation_session_id": "DEMO-001",
  "overlay_branch_id": "MAINT-001:post",
  "maintenance_event_id": "MAINT-001",
  "state_version": 3,
  "history_segment_id": "MAINT-001:post"
}
```

Model Artifact의 학습 provenance와 운영 Maintenance lineage를 혼합하지 않는다.
Observation의 `state_version`은 원인이 된 최신 maintenance lifecycle version의 복사본이며
`gen_data`의 생성 순서를 뜻하지 않는다. 생성 순서는 branch 내 `observed_at`과
`observation_id`로 추적한다.

### 11.1 저장과 조회 경계

현재 Canonical Observation 저장소는 `source_kind=canonical_observation` 의미와 Dataset
Version 기반 identity를 사용한다. Runtime Overlay 행을 Canonical 테이블에 그대로
삽입하거나 Canonical 행을 update하지 않는다.

Operations Target은 별도 append-only Runtime Overlay 저장소를 사용한다. 실제 테이블명은
migration PR에서 확정하지만 논리적으로 다음 key와 lineage를 보존해야 한다.

```text
organization_id + project_id + workspace_id
+ simulation_session_id + overlay_branch_id
+ equipment_id + observed_at
```

권장 저장소 이름은 `pm_runtime_overlay_observations`다. 동일 key에 다른 payload가 오면
conflict로 처리하고, `observation_sha256`이 같은 재전송은 멱등 처리한다.

branch-aware read model은 다음 규칙을 사용한다.

- 정비 대상이 아닌 설비: 기존 Canonical Replay를 계속 조회
- 정비 대상 설비의 `maintenance_started_at` 이전: 기존 Canonical Observation 조회
- Maintenance gap: 정상 센서 Observation 없음
- 정비 대상 설비의 `restart_at` 이후: 해당 `overlay_branch_id` Observation만 조회
- 대상 설비의 정비 전 예정 Canonical 미래 행을 Overlay 뒤에 다시 합치지 않음

단순 `UNION ALL`로 Canonical 미래 행과 Overlay 행을 함께 반환하지 않는다. Backend
Feature history와 Product Observation API는 동일 branch-aware read rule을 사용해야 한다.

기존 Backend/Frontend의 `source_kind: "canonical_observation"` literal은 구현 PR에서
`"canonical_observation" | "maintenance_replay_overlay"`로 additive 확장한다.
`base_source_sha256`은 기반 Canonical Snapshot의 checksum이고,
`observation_sha256`은 canonicalized Overlay Observation과 lineage의 무결성 값이다.
정본 직렬화는 `generated_at`과 `observation_sha256`을 제외한 전체 payload를 key 오름차순,
공백 없는 JSON으로 직렬화하고 UTF-8 byte로 인코딩한 뒤 SHA-256을 계산한다. 문자열의
Unicode code point는 ASCII escape로 바꾸지 않고(`ensure_ascii=false`) Unicode normalization도
적용하지 않는다. 비유한수는 허용하지 않는다. Python 구현 기준 옵션은
`ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False`다.
`contracts/test-vectors/runtime-overlay-output-v1/`의 Unicode payload와 기대 SHA가 두 저장소의
공용 byte-level 기준이다. `measurements`가 센서값의 정본이며
Backend 호환용 최상위 센서 필드는 같은 값을 복사한 projection이므로 서로 다르면 계약
위반이다.

## 12. Feature history와 Prediction

- `restart_at`부터 새 `history_segment_id`를 시작한다.
- 별도 계약이 없으면 정비 전 history를 정비 후 Rolling/Lag Feature에 섞지 않는다.
- Generator 런타임 파이프라인이 현재 Model Artifact의 `history_requirement.json`을 읽고 최소
  Observation 수, lookback, partition/order와 유효성을 평가한다.
- `gen_data`는 Runtime Overlay Observation을 지속 생성할 뿐 `history_requirement`을 소비하거나
  `ready`/`history_insufficient`를 판정하지 않는다.
- 고정된 demo 숫자를 Model contract 대신 사용하지 않는다.
- 요구 이력이 부족하고 Overlay stream이 진행 중이면 Generator는 `warming_up`으로 유지하고
  이후 `available` Observation을 기다린다.
- `history_insufficient`는 단순히 현재 row가 부족하다는 뜻이 아니다. Overlay stream이
  종료·실패했거나 Session 종료 조건, 데이터 유효성 문제 등으로 해당 history segment에서
  유효 이력을 더 이상 확보할 수 없음이 확정된 경우에만 사용한다. 그 종료/status 신호의
  기계 판독 handoff는 후속 versioned Schema에서 고정한다.
- 요구 이력을 충족하지 못하면 heuristic이나 silent fallback으로 Prediction하지 않는다.
- 첫 번째 `inference-ready` Observation에서 최초 Runtime Prediction(`score`)을 정확히 한 번 생성하여 `Prediction Result Batch`로 송신한다.
- Backend는 수신된 score에 Threshold Policy를 적용하여 신규 Product Result/Evidence를 생성한다 (Backend 수신 및 판정은 `후속 구현`).
- 이후에는 정상 Runtime Prediction 주기를 유지한다.

최초 Prediction 중복 방지 키는 최소 다음 식별자를 결합한다.

```text
maintenance_event_id + history_segment_id + prediction_target_time
```

## 13. API/UI 상태 의미

| 상태 | Product 의미 |
|---|---|
| `equipment_under_maintenance` | 대상 설비 정비 진행 중 |
| `warming_up` | 정비 후 요구 Observation 이력 생성 중 |
| `history_insufficient` | 요구 이력을 확보할 수 없어 Prediction 불가 |
| `ready` | 추론 가능한 이력 확보 |
| `predicted` | 신규 Runtime Prediction과 Result/Evidence 생성 완료 |

`warming_up`과 `history_insufficient`를 `NORMAL`로 표시하지 않는다. 정비 완료 역시
정상 Prediction이 아니다. 정비 후 실제 Prediction이 조치 불필요로 판정한 경우에만
정상으로 표시한다.

Product API의 canonical runtime-status read location은 이 PR에서 확정하지 않는다.
`gen_data` Runtime Overlay의 Observation/status handoff Schema가 확정된 이후 Backend
integration 단계에서 결정한다. 이는 누락된 TBD가 아니라 선행조건이 명시된 Deferred
decision이다. 기존 Result의 `status_grade`와 Runtime Overlay 준비 상태는 어떤 위치를
채택하더라도 별도 필드와 의미로 유지한다.

## 14. 역할 경계

| 담당 | 소유 책임 | 소유하지 않는 책임 |
|---|---|---|
| 광우 / Closed-loop | Maintenance 상태, transaction, 단계별 Outbox 이벤트, 운영 lineage | Overlay 생성, Feature 계산, Prediction |
| 성민 / `gen_data` Generator·Replay | 대상 설비 pause/branch, Snapshot effect, branch-local Fast-forward, 지속 Overlay Observation 생성/available | Model Artifact/history requirement 해석, readiness 판정, Product Result/Evidence |
| Generator / Runtime Pipeline | Overlay Observation 전처리, Runtime Feature 추출, Model Artifact 기반 raw score 추론, `Prediction Result Batch` Outbox 송신 | Threshold 적용, 최종 이상 판정, Product Result/Evidence/Report/알림 생성 |
| 호범 / Backend Diagnosis (후속 구현) | `Prediction Result Batch` 수신, Threshold 정책 적용, 최종 이상 판정, Diagnosis, Product Result/Evidence/Report/알림 생성, 재학습/후속 조치 지시 | Overlay 센서 생성, ML 피처 직접 계산/중복 추론 |
| 우수 / Product API·UI·E2E | 진행 상태·결과 노출, 통합 시나리오 검증 | Domain 상태·Prediction 의미 재계산 |

`ontology_dashboard/systems/generator`의 책임은 Feature/Label, training, Model Artifact
publish 및 Runtime Prediction Pipeline(추론 점수 계산 및 `Prediction Result Batch` 송신)이며 최종 이상 판정과 Report/Evidence 생성 주체가 아니다.

## 15. 완료 조건

- [ ] 대상 설비만 기존 Replay에서 분기된다.
- [ ] Maintenance gap 동안 대상 설비 정상 Replay와 Prediction이 중단된다.
- [ ] 다른 설비의 Replay Clock과 데이터는 영향을 받지 않는다.
- [ ] 부분·지연 이벤트에도 완료 전 자동 재개하지 않는다.
- [ ] `idempotency_key`, maintenance `state_version`, available Observation 순서 규칙이 검증된다.
- [ ] 정비 효과가 action별 whitelist를 통과한다.
- [ ] Canonical과 정비 전 Observation/Result/Evidence는 변경되지 않는다.
- [ ] Overlay Observation에 `source_kind`, branch, Maintenance lineage가 기록된다.
- [ ] Overlay Observation은 Canonical 테이블과 분리된 append-only 저장소에 기록된다.
- [ ] branch-aware read가 대상 설비의 정비 후 Canonical 미래 행을 다시 섞지 않는다.
- [ ] Generator만 필요한 이력을 `history_requirement.json`에서 계산하고 readiness를 판정한다.
- [ ] 이력 부족 시 Generator가 Prediction하지 않고 지속 생성되는 다음 Observation을 기다린다.
- [ ] `history_insufficient`가 일시적인 warming-up과 명확히 구분된다.
- [ ] 정비 전후 Feature history가 암묵적으로 혼합되지 않는다.
- [ ] 첫 inference-ready Observation에서 신규 score 추론 및 Backend의 Result/Evidence 생성이 한 번 수행된다.
- [ ] 정비 완료나 warming-up 상태가 정상 Prediction으로 표시되지 않는다.
- [ ] 정비 전 Result부터 정비 후 Result까지 `maintenance_event_id`로 추적할 수 있다.

## 16. 기계 판독 계약

Closed-loop 소유 이벤트와 Generator/Backend handoff는 다음 JSON Schema를 정본으로 쓴다.

```text
contracts/schemas/maintenance-replay-event.schema.json
contracts/schemas/runtime-overlay-observation.schema.json
contracts/schemas/runtime-overlay-observations-available.schema.json
```

첫 번째 파일은 Closed-loop가 발행하는 `maintenance.*`, 두 번째 파일은 Generator가 저장하는
개별 Overlay Observation, 세 번째 파일은 새 delta batch를 Backend에 알리는 available 이벤트의
정본이다. JSON Schema가 형식을 검증하고, publisher/consumer validator가 checksum, 중첩 lineage
일치, measurement projection 일치, 시간 범위와 누적 개수 같은 교차 필드 invariant를 검증한다.
계약 변경은 Generator와 Backend Diagnosis 소유자 리뷰를 거친다.
