# Source Data Producer runtime

## Invariant

simulation 센서값은 `SimulationProducer`에서 한 번만 계산한다. 실제 OPC UA source는
SDK subscription에서 받은 DataValue를 재계산하지 않고 `SensorRecord`로 정규화한다.

```text
existing physics / sensor functions
        ↓
SimulationProducer
        ↓
SensorRecord
   ├─ SourceRecordWriter → source/sensor_records.jsonl
   ├─ OpcUaPublisher     → SDK DataValue + protocol provenance
   └─ CanonicalWriter    → 기존 canonical CSV contract

configured OPC UA Server
        ↓ asyncua subscription
OpcUaCollector
        ↓ reverse mapping / quality / timestamp
SensorRecord(source_kind=opcua)
   ├─ SourceRecordWriter → source/sensor_records.jsonl
   └─ ProtocolRecordWriter → received provenance / quarantine
```

writer나 protocol publisher는 physics 함수를 호출하지 않는다. protocol publish가 실패해도
이미 계산된 SensorRecord와 source/canonical projection은 유지된다.

## SensorRecord

현재 계약은 schema v2다. 필수 필드는 `schema_version`, `run_id`, `sequence`,
`asset_id`, `observed_at`, `measurements`, `generator_version`, `asset_type`,
`site_id`, `cell_id`, `source_kind`, `observation_id`, `observed_at_source`,
`branch_kind`, `record_kind`, `quality`이며 `overlay`는 nullable이다. v1 소비자는 새 필드의 의미를
추론해서는 안 되며, v2를 명시적으로 지원한 뒤 전환해야 한다. v2 writer는 모든
레코드에 새 필드를 직렬화하고 v1 레코드를 생성하지 않는다.

`observation_id`는 run 독립적인 결정론적 식별자다. 생성 시 `run_id`나
sequence를 포함하지 않으며 `asset_id`, `observed_at`, measurement fingerprint,
source kind를 기반으로 생성된다. 이 ID는 gen_data source record와 protocol record를
연결하고 재현·누락·중복을 확인하는 correlation ID다. Backend와 Ontology는 이를
source reference로 보존할 수 있지만, 각 도메인의 최종 Observation/Object ID와
동일한 값으로 간주하거나 그 ID 생성 규칙을 gen_data에 위임하지 않는다.

일반 simulation/collector 출력의 `branch_kind`는 `canonical`이다. Maintenance Runtime
Overlay 출력은 SensorRecord v2의 measurement envelope를 재사용하지만 별도의 외부
Overlay DTO로 투영한다. 이 DTO는 `source_kind=maintenance_replay_overlay`,
`branch_kind=overlay`와 다음 `overlay` 객체를 사용한다.

```json
{
  "branch_kind": "overlay",
  "overlay": {
    "overlay_id": "...",
    "parent_branch": "canonical",
    "maintenance_event_id": "...",
    "state_patch_reference": "...",
    "simulation_session_id": "...",
    "history_segment_id": "...",
    "state_version": 3
  }
}
```

`sequence`는 run 안에서 yield된 record마다 증가한다. source correlation은
`run_id + sequence + asset_id`, protocol measurement correlation은 여기에
`measurement_key`를 더한다.

`record_kind`는 simulation의 asset 단위 feature 묶음을 `full_observation`, OPC UA
DataValue 한 건을 `single_measurement`로 구분한다. 두 경로의 measurement cardinality가
같다고 가정하지 않으며 Generator는 single-measurement protocol record를 명시적으로
조립한다. `quality`는 `good | uncertain | bad` source-quality 분류다. simulation은
생성 계약상 `good`, OPC UA는 수신 StatusCode severity에서 결정한다.

## OPC UA publisher

`app/protocol/opcua.py`는 `asyncua` SDK의 Server/Node/DataValue를 사용한다.
`mappings/opcua_nodes.v1.json`이 NodeId, DataType, unit을 결정하고
`SensorRecord.observed_at`을 OPC UA `SourceTimestamp`로 기록한다.

protocol provenance는 `run_id`, `sequence`, `asset_id`, `measurement_key`, `node_id`,
`data_type`, `unit`, `value`, `status_code`, `source_timestamp`, `published_at`,
`mapping_version`을 남긴다. 이것은 SDK publish provenance이지 wire packet capture가 아니다.

## OPC UA collector

같은 `app/protocol/opcua.py`의 `OpcUaCollector`는 configured endpoint/NodeId만 구독한다.
자동 browse/discovery나 범용 gateway를 만들지 않는다. versioned mapping template를
역으로 적용해 `asset_id`, `asset_type`, `measurement_key`, `unit`을 결정하고 수신된
DataValue 한 건을 measurement 하나를 가진 `SensorRecord(source_kind=opcua)`로 만든다.

수신 provenance는 publish provenance와 구별하기 위해 `direction=received`를 기록하며
`StatusCode`, `SourceTimestamp`, `ServerTimestamp`, `received_at`을 모두 보존한다.
`observed_at`은 SourceTimestamp → ServerTimestamp → received_at 순으로 선택한다.
SensorRecord에도 `observed_at_source` (`source` | `server` | `received`)를 함께 기록한다.
OPC UA quality는 source quality일 뿐 Diagnosis 상태로 해석하지 않는다. 원본
`StatusCode`와 정수 값은 provenance에 보존하고, `SensorRecord.quality`에는
Good/Uncertain/Bad severity만 전달해 소비자가 별도 파일 join 없이 fail-closed 정책을
적용할 수 있게 한다.

현재 measurement 값은 기존 `measurements: dict[str, value]` 계약을 유지한다.
simulation은 `record_kind=full_observation`, OPC UA는
`record_kind=single_measurement`로 cardinality를 명시한다. simulation의 `quality=good`은
OPC UA 통신 상태를 흉내 낸 값이 아니라 generator가 만든 observation이 유효하다는
source-quality 기본값이다.

## Generator ingestion contract

`protocol/provenance.jsonl`은 단순 감사 로그가 아니라 정상 OPC UA DataValue 단위의
append-only protocol record이며 Generator ingestion의 공식 입력 계약이다. Generator는
이 파일에서 schema/mapping을 검증하고 measurement를 asset-time 단위로 조립한 뒤
quality policy, history window, feature 생성과 inference를 수행한다. `errors.jsonl`과
`quarantine.jsonl`은 정상 feature/prediction 입력에서 제외한다.

```text
source/sensor_records.jsonl = 생성 원본 확인, 재현, protocol correlation
protocol/provenance.jsonl  = Generator 운영 입력
canonical/*.csv + manifest = 기존 데이터 계약의 회귀·호환 검증
```

Generator prediction은 `observation_id`, `run_id`, `sequence`, `mapping_version`,
`schema_version`을 source lineage로 전달한다. Canonical CSV는 운영 inference 입력이
아니며, Backend/Ontology 도메인 ID는 각 owner domain에서 별도로 만든다.

Overlay identity는 Maintenance handoff의 `simulation_session_id`,
`maintenance_action_id`, `maintenance_event_id`, `state_version`에서 파생·보존한다.
`gen_data`는 Maintenance가 확정한 Action 의미를 재해석하지 않고 현재 MVP whitelist인
두 typed patch만 적용한다.

- `TOOL_REPLACEMENT`: `tool_wear_min reset -> 0 min`
- `COOLING_SYSTEM_RESTORE`: `cooling_system_state restore -> nominal`

Cooling 복구는 임의 온도값을 주입하지 않는다. 정비 전 고장 episode를 제외한 대상 설비
Overlay branch에서 기존 CNC 물리를 정상 baseline으로 재개하며, 공구 마모처럼 관련 없는
상태는 변경하지 않는다. `gen_data`는 추론 readiness와 정비 성공 여부를 판단하지 않는다.

최소 수집 안전장치는 다음과 같다.

- connection loss → reconnect → configured Node re-subscribe
- 같은 node/timestamp/value/status notification → in-process duplicate suppression
- unknown/ambiguous Node → quarantine
- mapping과 다른 DataType → quarantine
- server가 engineering unit property를 노출하고 mapping unit과 다름 → quarantine

collector는 SDK DataValue 수신 경계이며 wire packet capture가 아니다. PKI 자동화,
NodeSet 자동 discovery, multi-server federation, late-arrival aggregation은 현재 범위가 아니다.

## RuntimeManager / FastAPI

`RuntimeManager`가 run 중 producer, writers, OPC UA session, manifest를 소유한다.
simulation run의 manual tick과 continuous loop는 같은 `process_tick`을 사용한다.
`source_kind=opcua` run은 subscription worker를 소유하며 manual tick은 지원하지 않는다.
stop 시 writer flush와 OPC UA client/subscription cleanup을 수행한다.
시작 입력과 mapping은 run 디렉터리 생성 전에 검증하며, context 초기화 실패 시 열린
writer와 새 run 디렉터리를 rollback한다. stop timeout 뒤 worker가 남아 있으면 상태를
`stopping`으로 유지하고 writer를 닫지 않는다. collector/session과 worker가 실제로
종료된 뒤에만 writer를 flush/close하고 terminal 상태를 확정한다.

### Runtime Overlay integration

simulation run은 `GEN_DATA_RUNTIME_OVERLAY_EVENT_FILE`이 설정된 경우에만 Backend의
project-scoped JSONL inbox를 읽는다. 실행 시작 시 `simulation_session_id`를 Source
run에 명시적으로 바인딩하고 그 ID가 일치하는 이벤트만 적용한다. 생략 시 `run_id`를
기본값으로 사용하지만 두 ID를 같은 개념으로 정의하지 않는다.

- `maintenance.started`: 미래 시각 이벤트는 pending으로 보존하고 첫 Source tick이 해당
  시각에 도달하기 직전에 Runtime snapshot을 만든다. 그 tick부터 Canonical
  Source/OPC UA/CSV projection에서 대상 설비만 제외한다.
- future started와 같은 stream의 `maintenance.completed` 및
  `maintenance.replay_requested`가 먼저 도착하면 격리하지 않고 state version 순서로
  함께 보존한다. started tick에 snapshot을 만든 뒤 queued lifecycle을 순차 적용한다.
- 동일 Source Session에서 대상 설비의 Canonical Observation이 이미
  `maintenance_started_at` 이상으로 출력된 late event는 과거 상태를 추정하거나
  Canonical row를 다시 쓰지 않는다. 마지막 Canonical Tick의 다음 Tick을
  `source_effective_started_at`으로 사용해 Overlay branch로 전환한다.
- `maintenance.completed`: action별 whitelist를 검증한 뒤 snapshot에 `state_patch`를
  적용한다.
- `maintenance.replay_requested`: `restart_at`부터 branch-local clock으로 Observation을
  생성한다.
- 다른 설비의 global simulation clock과 출력은 계속 진행한다.
- event ID/idempotency key/state version과 append-only observation hash를 검증한다.
  저장 파일을 다시 열 때는 선언된 hash를 신뢰하지 않고 실제 payload의 semantic
  SHA-256을 재계산한다.
- 잘못된 inbox line은 `rejected_maintenance_events.jsonl`에 raw-line SHA-256과 사유를
  한 번만 기록하고, 같은 파일의 이후 정상 이벤트 처리를 계속한다.
- pending lifecycle stream 전체는 checkpoint에서 복구한다. checkpoint에 먼저 기록된
  pending availability는 Overlay coordinator 재구성 시 JSONL outbox로 복구한다. 전체
  `RuntimeManager` run resume는 별도 runtime lifecycle 범위다.
- checkpoint는 write별 고유 임시 파일을 fsync한 뒤 원자적으로 교체한다. Windows에서
  별도 reader가 target 파일을 잠깐 열어 발생하는 `PermissionError`는 제한된 지수
  backoff로 재시도하고, 반복 실패는 `partial_failure`로 그대로 노출한다.

Overlay branch 파일은 SensorRecord v2 payload와 동일한 `measurements`를 정본으로
보존한다. Backend Runtime Overlay reader에는 같은 measurement를 flat field로도 투영하고
두 값이 다르면 발행을 거부한다. 외부 DTO는
`contract_version=runtime-overlay-observation-v1`과
`source_kind=maintenance_replay_overlay`를 사용하며,
`base_source_sha256`은 `maintenance.started` 시점의 분기 전 source runtime snapshot을
결정론적으로 식별한다. 이 projection은 호환용이며 별도 Physics 계산 경로가 아니다.
`observations_available.jsonl`은
`contract_version=runtime-overlay-observations-available-v1`을 사용한다. 여기서
`batch_rows`는 해당 이벤트의 delta, `generated_rows`는 branch 누적값이며,
`storage_reference`는 producer 머신의 절대경로가 아닌 output root 기준 상대경로다.
논리 session/branch ID 쌍은 compact JSON array의 unescaped UTF-8 byte에 대한 SHA-256으로
경로화하며, 파일은 `runtime_overlay/sha256-<digest>.jsonl`에 저장한다. Overlay Observation
checksum은 `generated_at`과 `observation_sha256`을 제외하고 key를 정렬한 compact JSON을
`ensure_ascii=false`, `allow_nan=false`로 UTF-8 인코딩한 byte를 기준으로 한다.

```text
output/runtime_overlay/
├── runtime_overlay_state.json
├── observations_available.jsonl
├── rejected_maintenance_events.jsonl
└── sha256-{session-and-branch-identity-digest}.jsonl
```

FastAPI는 control layer만 담당한다.

```text
POST /api/runs
POST /api/runs/{run_id}/tick
POST /api/runs/{run_id}/simulation/fast-forward
POST /api/runs/{run_id}/runtime-overlay/fast-forward
POST /api/runs/{run_id}/stop
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/outputs
GET  /health/live
GET  /health/ready
```

`simulation/fast-forward`는 전체 Simulation Clock을 목표 경과 시간까지 진행한다. 모든
설비의 중간 tick을 실제로 생성하므로 센서 상태, 고장 episode, 생산 및 정비 상태가
보존된다. 현재보다 이전인 목표와 run 종료 시각 이상의 목표는 거부한다. 이 API는
단일 정비 설비만 앞당기는 `runtime-overlay/fast-forward`와 별개의 제어 경계다.

`runtime-overlay/fast-forward`는 `equipment_id`와 절대 누적 목표인
`target_generated_rows`를 받아 해당 post-maintenance branch만 빠르게 생성한다. 이 호출은
global Simulation Clock, Canonical sequence, 다른 설비의 runtime state를 전진시키지 않는다.
목표 행 수는 Source 생성 정책이며 inference readiness를 선언하지 않는다.
Fast-forward 이후에는 branch-local 시차를 유지하며 일반 Source tick마다 해당 branch도 한 행씩
계속 생성하므로, 전역 시각이 따라올 때까지 대상 설비 관측이 멈추지 않는다.
이 프로젝트의 정본 실행 환경은 합성 데이터 기반 Runtime Simulation이므로, 정비 완료 후
예측 이력을 현실 시간만큼 기다리지 않도록 기본 생성 목표를
`GEN_DATA_RUNTIME_OVERLAY_FAST_FORWARD_ROWS=36`으로 둔다. 이는 화면만 바꾸는 데모
처리가 아니라 대상 설비의 Overlay Observation을 실제로 생성하는 Source 실행 정책이다.
전체 Simulation Clock, Canonical sequence 및 다른 설비 상태는 가속하지 않는다.

`POST /api/runs`의 `runtime_overlay_fast_forward_rows`로 실행별 목표를 `0..10000`
범위에서 덮어쓸 수 있다. 필드를 생략하면 application 기본값 `36`을 사용하고, 명시적으로
`0`을 전달하면 해당 run의 자동 가속만 비활성화한다. 실제 적용값은 Run Manifest의
`runtime_overlay_fast_forward_rows`에 기록한다.

### Top-level compatibility imports

현재 저장소 CI의 import/compile smoke가 아직 `api`, `daemon`, `line_worker`,
`protocol`, `state_tracker` top-level 경로를 확인한다. 이 경로들은 기존
Flask/daemon/raw protocol 구현을 유지하지 않고 새 canonical 구현의 타입만
re-export하는 최소 compatibility shim이다.

- `api.create_app` → `app.main.create_app`
- `daemon.RuntimeManager` → `app.runtime.manager.RuntimeManager`
- `line_worker.SimulationProducer` → `app.simulation.producer.SimulationProducer`
- `protocol.OpcUaPublisher` → `app.protocol.opcua.OpcUaPublisher`
- `state_tracker.RunState` → `app.runtime.state.RunState`

운영 entrypoint와 application code는 이 top-level shim을 사용하지 않는다. 기존
custom Modbus/OPC-UA-shaped frame encoder/decoder와 global daemon loop는 제거된 상태다.

## Outputs

```text
output/runs/{run_id}/
├── source/sensor_records.jsonl
├── protocol/provenance.jsonl
├── protocol/errors.jsonl
├── protocol/quarantine.jsonl
├── canonical/
│   ├── asset_master.csv
│   ├── asset_relation.csv
│   ├── compressor_sensor_observation.csv
│   ├── cnc_sensor_observation.csv
│   ├── cnc_production_cycle.csv
│   └── maintenance_event.csv
└── run_manifest.json
```

정적 Canonical V3.1 생성도 같은 `SimulationProducer`와 `CanonicalWriter`를 사용하므로
별도의 physics 재계산 경로를 갖지 않는다.
