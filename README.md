# gen_data

Biz-CollabCraft의 제조 예지보전 **Source Data Producer** 저장소입니다.

이 저장소의 운영 책임은 raw / simulation / synthetic sensor data 생성·갱신,
Canonical V3.1 물리·생성 기준, source/reference/test fixture, seed 기반 재현성과
source baseline validation까지입니다.

과거 독립 배포 패키지에서 사용하던 `predictive_maintenance_canonical_v3_1/`
wrapper는 제거했습니다. 현재는 **저장소 루트 자체가 Canonical V3.1 source/reference
baseline의 기준 경로**입니다. V3.1은 디렉터리 이름이 아니라 manifest, schema,
release artifact와 Git tag로 버전 관리합니다.

Canonical V3.1의 상세 물리·데이터 설명은 [`CANONICAL_V3_1.md`](./CANONICAL_V3_1.md),
현재 운영 소유권은 [`OWNERSHIP_AND_MIGRATION.md`](./OWNERSHIP_AND_MIGRATION.md)를
따릅니다.

## 저장소 구조

```text
gen_data/
├── app/
│   ├── simulation/          # 기존 physics 기반 단일 SensorRecord producer
│   ├── observation/         # SensorRecord 내부 계약
│   ├── protocol/            # asyncua OPC UA publisher + configured-node collector
│   ├── storage/             # source/protocol/canonical writer
│   ├── runtime/             # run lifecycle / Runtime Overlay / safe stop
│   └── api/                 # FastAPI control routes
├── mappings/                # versioned OPC UA NodeId/DataType/unit mapping
├── canonical/
│   ├── dataset/             # Canonical source observation
│   ├── evaluation_truth/    # 평가/검증 전용 truth
│   ├── model_outputs/       # 과거 ML/prediction/result reference fixture
│   └── validation/          # source/reference 검증 기록
├── scripts/                 # 생성·검증·release tooling
├── agent/                   # evidence/claim 평가 fixture
├── experiments/             # source-side 실험 fixture
├── model/                   # migration/reference implementation
├── tests/                   # producer / OPC UA / runtime / canonical regression
├── docs/                    # 현재 Source Data Producer 계약
├── physics_engine.py        # Canonical generator compatibility facade
├── CANONICAL_V3_1.md
├── SCHEMA.md
└── OWNERSHIP_AND_MIGRATION.md
```

## 저장소 책임과 제품 흐름

```text
gen_data
raw / simulation / Canonical V3.1 source data
Source Data Producer
        ↓ source/reference contract
ontology_dashboard/systems/generator
extraction → ontology mapping → topology → feature → model training
→ versioned Model Artifact
        ↓ Model Artifact contract
ontology_dashboard/systems/backend/diagnosis
current observation + Model Artifact
→ runtime inference
→ Result Artifact / Evidence
        ↓
Backend API / Frontend / Report
```

따라서 `gen_data`는 제품의 Semantic/ML pipeline, versioned Model Artifact,
runtime prediction 또는 Result Artifact/Evidence의 운영 Source of Truth가 아닙니다.

`canonical/model_outputs/*`, `result_artifact_sample.json`,
`model/prediction_pipeline.py`는 V3.1 이관 당시의 호환성·회귀 검증을 위해 남기는
**reference/regression/migration fixture**입니다. 제품 runtime은 이 파일을 최신
운영 결과로 직접 소비하지 않습니다.

## 설치

현재 lock dependency 기준으로 Python 3.12 이상을 사용합니다.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
```

## Runtime 실행

운영 entrypoint는 FastAPI control layer입니다.

```bash
.venv/bin/python run.py
```

기본 endpoint:

```text
POST /api/runs
POST /api/runs/{run_id}/tick
POST /api/runs/{run_id}/runtime-overlay/fast-forward
POST /api/runs/{run_id}/stop
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/outputs
GET  /health/live
GET  /health/ready
```

`source_kind=simulation`에서는 `RuntimeManager`가 기존 physics를 한 번 계산해
`SensorRecord`를 만들고, 같은 record를 source JSONL, OPC UA SDK DataValue
publish/provenance, canonical CSV에 투영합니다.

`source_kind=opcua`에서는 configured endpoint와 NodeId 목록에 실제 `asyncua`
subscription을 생성하고 수신 `DataValue`를 동일 `SensorRecord` 경계로 정규화합니다.
`StatusCode`, `SourceTimestamp`, `ServerTimestamp`, `received_at`을 provenance로 보존하고,
연결이 끊기면 reconnect 후 subscription을 재생성합니다. unknown/ambiguous Node와
잘못된 DataType/unit은 `protocol/quarantine.jsonl`에 격리하며 동일 notification은
in-process dedup합니다. 이 기능은 SDK 수집 경계이며 실제 wire packet capture는 아닙니다.

OPC UA source run 예시:

```json
{
  "run_id": "plant-opcua-001",
  "source_kind": "opcua",
  "opcua_source_endpoint": "opc.tcp://127.0.0.1:4840/plant/",
  "opcua_node_ids": [
    "ns=2;s=CNC-S01-L01-01.torque_nm"
  ],
  "reconnect_seconds": 1.0,
  "continuous": true
}
```

실제 OPC UA notification은 measurement 단위로 들어오므로 collector는 불완전한
DataValue 묶음을 기존 flat Canonical V3.1 row로 위조하지 않습니다. 기존 canonical
CSV/manifest 계약은 완전한 simulation asset/tick snapshot에서 그대로 유지됩니다.

### Maintenance Runtime Overlay

`GEN_DATA_RUNTIME_OVERLAY_EVENT_FILE`을 설정하면 simulation run이 Backend Outbox에서
전달된 `maintenance-replay-v1` JSONL을 opt-in으로 소비합니다. 이벤트의
`simulation_session_id`는 실행 시작 요청의 동명 필드로 Source run에 명시적으로
바인딩합니다. 생략하면 `run_id`를 기본값으로 사용하며, 다른 Session의 이벤트는 해당
run이 소비하지 않습니다. 이 값은 Diagnosis/Maintenance replay 상관 ID이고 Source
run identity와 같은 개념으로 간주하지 않습니다.

```text
maintenance.started
→ 미래 started와 같은 stream의 completed/replay는 시작 시각까지 함께 pending
→ 첫 due tick 직전에 snapshot 후 대상 설비 Canonical 출력만 중단
→ queued maintenance.completed의 허용된 state_patch를 순서대로 적용
→ queued maintenance.replay_requested의 restart_at부터 대상 branch clock만 진행
→ output/runtime_overlay/{session}/{branch}.jsonl
→ output/runtime_overlay/observations_available.jsonl
```

정비 후에는 Runtime Simulation의 기본 실행 정책으로 대상 Overlay branch에 Observation
36개를 즉시 생성한다. 이는 별도 화면용 fixture가 아니라 Generator가 후속 예측에 소비할
실제 Source Observation이며, 전체 Simulation Clock과 다른 설비의 상태는 전진시키지 않는다.
기본값은 `GEN_DATA_RUNTIME_OVERLAY_FAST_FORWARD_ROWS`로 변경할 수 있고,
`POST /api/runs` 요청의 `runtime_overlay_fast_forward_rows`로 실행별 `0..10000` 범위에서
덮어쓸 수 있다. `0`은 해당 run의 자동 가속을 비활성화한다.

현재 MVP에서 허용하는 typed maintenance patch는 다음 두 가지입니다.

- `TOOL_REPLACEMENT`: `tool_wear_min`을 `0 min`으로 reset
- `COOLING_SYSTEM_RESTORE`: `cooling_system_state`를 `nominal`로 restore

Cooling 복구는 Canonical에 없는 임의 온도 상태를 만들지 않습니다. 정비 전 failure
episode를 제외한 Overlay branch에서 기존 CNC 물리를 정상 baseline으로 재개하고, 관련
없는 `tool_wear_min`은 그대로 보존합니다.

시작 시각 이후 Canonical row가 이미 출력된 late event와 계약을 위반한 inbox line은
`output/runtime_overlay/rejected_maintenance_events.jsonl`에 중복 없이 격리합니다. 한
줄의 오류가 같은 inbox의 이후 정상 이벤트를 막지 않습니다. 저장된 Overlay Observation은
재사용 전에 payload 기준 SHA-256을 다시 계산해 변조 여부를 확인합니다.

Overlay Observation은 `SensorRecord v2`의 `measurements` envelope를 재사용하되 외부
DTO에서 `contract_version=runtime-overlay-observation-v1`,
`source_kind=maintenance_replay_overlay`, `branch_kind=overlay`와 source lineage를
명시합니다. 분기 전 runtime snapshot의 결정론적 SHA-256도 함께 기록합니다. Backend
reader를 위한 동일 값의 flat measurement projection도 함께 기록하지만 Physics를 다시
계산하지 않습니다. available 이벤트는
`contract_version=runtime-overlay-observations-available-v1`을 사용하고
`storage_reference`를 output root 기준 상대경로로 전달합니다. `gen_data`는 Observation
availability만 알리며 Model Artifact, history requirement, Prediction 또는
Result/Evidence를 생성하지 않습니다.

저장 경로 identity는 `[simulation_session_id, overlay_branch_id]`를 공백 없이 JSON으로
직렬화하고 Unicode를 escape하지 않은 UTF-8 byte의 lowercase SHA-256을 사용해
`runtime_overlay/sha256-<digest>.jsonl`로 만든다. 논리 ID를 경로 문자로 치환하지 않으므로
`.`/`..` traversal과 replacement alias를 허용하지 않는다. `observation_sha256`은
`generated_at`과 checksum 필드 자체를 제외한 payload를
`ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False`로 직렬화한
UTF-8 byte의 SHA-256이다. 공용 Unicode/path 기대값은
`tests/fixtures/runtime-overlay-output-v1/`에 고정한다.

## 빠른 검증

현재 checkout의 source/reference baseline을 검증합니다.

```bash
python3 scripts/validate_package.py
python3 scripts/validate_reproducibility.py --days 5 --scope full
python3 -m pytest -q
```

새 source를 생성하는 기본 orchestrator는 Canonical/source와 source-side fixture,
validation에 집중합니다.

```bash
python3 scripts/run_pipeline.py --days 30 --seed 42
```

기존 ML/prediction/result fixture까지 재생성해야 하는 회귀 검증에서만 명시적으로
다음 옵션을 사용합니다.

```bash
python3 scripts/run_pipeline.py \
  --days 30 \
  --seed 42 \
  --include-reference-model-fixtures
```

## CI 기준

PR과 `main` push에서는 `.github/workflows/source-validation.yml`이 다음 검증을
필수로 실행합니다.

- Canonical/source 및 reference fixture package validation
- seed 기반 full reproducibility validation
- SensorRecord/OPC UA/runtime/FastAPI/canonical regression test
- Runtime Overlay 대상 설비 격리·멱등성·checkpoint 복구 regression test
- Canonical generator와 Source Data Producer import smoke
- Python compile 및 whitespace 검증
- validation output이 checkout의 기준 파일과 일치하는지 확인

Release ZIP 검증은 `.github/workflows/release-validation.yml`에서 tag 또는 수동 실행
시 수행합니다. 저장소가 평탄화되어도 배포 artifact 이름과 ZIP 내부 루트는 기존과
동일하게 `predictive_maintenance_canonical_v3_1`을 유지합니다.

## 데이터 사용 주의

- `canonical/dataset/`은 관측 가능한 source baseline입니다.
- `canonical/evaluation_truth/`과 experiment `hidden_truth/`는 평가·검증 전용이며
  제품 Dashboard/API/LLM 입력으로 노출하지 않습니다.
- `canonical/model_outputs/`은 운영 결과가 아니라 compatibility/regression fixture입니다.
- Result Artifact의 운영 producer는 `ontology_dashboard/systems/backend/diagnosis`입니다.
- `.env`, credential, cache, 가상환경과 재생성 가능한 `dist/` 압축본은 Git에
  커밋하지 않습니다.
