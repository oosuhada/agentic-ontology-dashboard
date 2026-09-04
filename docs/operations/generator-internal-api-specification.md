# Generator 내부 API 명세서

## 1. 기준과 상태

이 문서는 `systems/generator`가 노출하는 **내부 전용 제어 API**의 계약이다. [API 명세서](./api-specification.md)가 `backend`의 제품 API(사용자·프론트엔드가 소비)를 다루는 것과 달리, 이 문서는 `backend`(또는 운영자)가 `generator` 데몬을 제어하기 위한 API를 다룬다. **외부(프론트엔드)에는 노출되지 않는다.**

- 정본 앱 진입점: `systems.generator.app.main:app` (Application Factory `create_app()` 제공)
- 호환성 진입점: `systems.generator.generator_main:app` (Compatibility Shim)
- Base path: (별도 접두사 없음, `generator` 프로세스가 단독으로 사용)
- 책임: Generator는 단계별 Versioned Observation/Failure Dataset, Preprocessing Plan, Feature
  Dataset Bundle 및 Model Artifact를 발행하고, 런타임 관측으로 score를 계산해 Prediction
  Result Batch를 Backend에 전달한다.

Backend는 Prediction Result Batch를 검증·멱등 저장하고 threshold와 업무 정책을 적용해 Product
Result Artifact 및 Evidence로 승격한다.

Extraction이 사용하는 protocol field Mapping은 canonical Observation 변환 계약이다. Feature 실행 계약은 Feature Schema/Recipe이며 Ontology Mapping이 아니다.

---

## 2. 책임 경계 (허용 / 금지 범위)

[런타임 소유권 통합 계약](./runtime-ownership-integration.md) 및
[ADR-003](../architecture-decisions/ADR-003-generator-runtime-prediction-result-and-backend-decision-ownership.md)에
따라 다음 경계를 엄격히 준수한다.

### 허용 범위
- `GET /health` (데몬 상태 확인)
- `POST /extraction` (gen_data 증분 파싱 및 Canonical Observation Dataset 발행)
- `GET /extraction/status` (Extraction Manager, Background Worker 및 Handoff 큐 상태 조회)
- `GET /extraction/handoffs/{handoff_id}` & `POST /extraction/handoffs/{handoff_id}/retry` (Handoff 조회 및 재시도)
- `POST /preprocessing` (Observation Dataset 분석 및 Preprocessing Plan 수립·발행, 동기 endpoint 실행)
- `POST /feature` (Observation/Failure Dataset 및 Plan 기반 Feature Dataset Bundle 발행)
- `POST /train` & `POST /train/{base_model}` (Multi-Model 학습 및 Model Artifact 발행)
- `GET /runtime-pipeline/status`, `GET /runtime-pipeline/runs/{run_id}`, `GET /runtime-pipeline/queue` (런타임 예측 파이프라인 상태 조회)
- `POST /internal/runtime-pipeline/enqueue`, `POST /internal/runtime-pipeline/retry-failed/{job_id}` (런타임 작업 등록 및 재시도)
- `POST /internal/train` & `POST /internal/retrain` (기존 main 제어 API 호환성 유지)
- Target 제어 API (후속 고도화): `POST /models/{base_model}/activate/{model_version}`, `GET /models/{base_model}/active`

> **Preprocessing 도메인 책임 경계**
>
> - Preprocessing은 Observation Dataset의 구조 분석, 컬럼 역할 판정, 전체 변환 가능성 검증 및 불변 Preprocessing Plan 발행만 담당한다.
> - Preprocessing은 Ontology Mapping을 생성하거나 소비하지 않는다.
> - 원본 protocol field를 canonical Observation field로 변환하는 Mapping은 선행 Extraction 단계가 적용한다.
> - Feature 단계는 Ontology Mapping을 조회하지 않으며, Feature Schema/Recipe에 명시된 source field와 계산 규칙을 사용한다.
>
> **Generator 전체 책임 및 Backend 연계 책임 경계**:
>
> - Generator는 단계별 Versioned Observation/Failure Dataset, Preprocessing Plan, Feature Dataset Bundle 및 Model Artifact를 발행한다.
> - Generator의 실행 책임은 versioned Model Artifact 발행과 활성 포인터 관리뿐 아니라 Runtime
>   Feature, Model score와 Prediction Result Batch delivery까지다.
> - Preprocessing Plan의 `latest.json`은 해당 Dataset version에서 현재 선택된 Preprocessing Plan을 가리키는 포인터이며, Model Artifact 활성 버전 포인터와 동일한 파일 또는 저장 경계를 의미하지 않는다.
> - Backend는 Generator의 Model Artifact나 Feature executor를 직접 실행하지 않고 전달된 Batch를
>   검증·판정·승격한다.

### 금지 범위
- `POST /internal/predict`, `POST /internal/predict/file`
- Frontend 사용자 요청에 직접 결합된 ad-hoc inference
- `data_preprocessed/predictions/*.json` 파일 생성
- Product Result Artifact / Evidence 생성
- Product Result, Evidence와 사용자용 Report 형식 노출
- Frontend의 Generator 직접 호출

---

## 3. 엔드포인트 목록 및 Migration 매핑

### 3.1 Current API (현재 구현 상태)

현재 Generator 정본 애플리케이션(`systems/generator/app/main.py`)에 실제로 구현되어 동작하는 엔드포인트입니다.

| Method | Path | 현재 의미 | 상태 |
|---|---|---|---|
| GET | `/health` | Generator 데몬 프로세스 상태 확인 | Current (구현 완료) |
| POST | `/extraction` | gen_data sensor_stream.jsonl 또는 프로토콜 로그에 승인된 정적 매핑을 적용하여 불변 Versioned Canonical Observation Dataset 발행 (단일/전체 Source 처리, 단일 작성자 Lock 및 멱등성 보장) | Current (구현 완료) |
| GET | `/extraction/status` | Extraction Manager, Background Polling Worker 및 Runtime Handoff 큐 상태, Source별 체크포인트 offset 및 최근 오류 조회 | Current (구현 완료) |
| GET | `/extraction/handoffs/{handoff_id}` | 특정 Extraction -> Runtime Prediction Handoff 기록 상세 조회 | Current (구현 완료) |
| POST | `/extraction/handoffs/{handoff_id}/retry` | 실패 또는 대기 중인 Handoff 항목을 Runtime Prediction 큐에 명시적 재등록 | Current (구현 완료) |
| POST | `/preprocessing` | Observation Dataset 분석, 역할 판정 및 불변 Preprocessing Plan 수립·발행 (동기 방식) | Current — 구현 및 정본 Generator App 등록 완료 |
| POST | `/feature` | Observation/Failure Dataset, Preprocessing Plan, Feature/Label Schema를 소비하여 Feature Dataset Bundle 발행 (동기 방식, local file adapter) | Current — 구현 및 정본 Generator App 등록 완료 |
| POST | `/train` | Feature Dataset Bundle을 소비하여 등록된 전체 머신러닝 모델 학습 및 불변 Model Artifact 패키지 발행 (동기 방식, 부분 성공 격리 지원) | Current — 구현 및 정본 Generator App 등록 완료 |
| POST | `/train/{base_model}` | Feature Dataset Bundle을 소비하여 지정된 머신러닝 모델(`lightgbm`, `xgboost`, `random_forest`) 개별 학습 및 Model Artifact 발행 (동기 방식) | Current — 구현 및 정본 Generator App 등록 완료 |
| GET | `/runtime-pipeline/status` | 런타임 파이프라인 큐 길이, 워커 상태 및 최근 실행 결과 조회 | Current — 구현 및 정본 Generator App 등록 완료 |
| GET | `/runtime-pipeline/runs/{run_id}` | 특정 실행 ID의 단계별 상태(StageState) 및 다중 모델 예측 결과 상세 조회 | Current — 구현 및 정본 Generator App 등록 완료 |
| GET | `/runtime-pipeline/queue` | FIFO 작업 큐 상태 목록 조회 (queued/running/succeeded/failed) | Current — 구현 및 정본 Generator App 등록 완료 |
| POST | `/internal/runtime-pipeline/enqueue` | 새 관측 소스 파일을 런타임 예측 FIFO 큐에 내부 등록 | Current — 구현 및 정본 Generator App 등록 완료 |
| POST | `/internal/runtime-pipeline/retry-failed/{job_id}` | 실패(failed/dead_letter) 작업 명시적 정리 및 신규 시퀀스 재등록 | Current — 구현 및 정본 Generator App 등록 완료 |
| POST | `/internal/train` | 데몬 최초 학습 실행 (내부 Lock 제어, 호환성 유지) | Current (호환성 유지) |
| POST | `/internal/retrain` | 데몬 새 버전 재학습 실행 (내부 Lock 제어, 호환성 유지) | Current (호환성 유지) |

#### Runtime Pipeline enqueue 문맥 계약

`POST /internal/runtime-pipeline/enqueue` 요청은 다음 값을 필수로 제공하며 알려지지 않은
추가 필드는 `422`로 거부한다.

- `job_id`, `source_uri`, lowercase SHA-256 `source_checksum`
- `source_kind`: `live_sensor`, `simulation_overlay`, `maintenance_replay_overlay` 중 하나
- `source_contract_version`, `source_schema_version`, `pipeline_contract_version`
- `dataset_id`, `dataset_version`
- `lineage`: 일반 센서 입력은 빈 객체를 허용하지만,
  `maintenance_replay_overlay`는 session/branch/history/maintenance/state lineage 6개를 요구한다.

입력 문맥은 Queue 영속화, retry, RunState, Checkpoint, 내부 staging과 외부
`prediction-result-batch-v1`까지 그대로 전달한다. 기존 Queue 행에 문맥이 없으면
`live_sensor`나 임의 버전으로 추정하지 않고
`PIPELINE_SOURCE_CONTEXT_MIGRATION_REQUIRED` dead-letter로 분리한다.

외부 Batch의 `producer.runtime_version`은 환경변수 `GENERATOR_RUNTIME_VERSION`에서만
가져오며, 누락 시 Batch 발행을 중단한다. Artifact가 로드되기 전에 실패해 실제
Feature/History/Label 버전을 알 수 없는 상태는 `null`로 표현하고 `v1`, `v1.0`,
`unknown` 같은 가짜 provenance를 만들지 않는다.



### 3.2 Target API (후속 목표 설계)

후속 구조 개편(4대 파이프라인 단계별 책임 분리)이 완료된 후 도입될 목표 엔드포인트입니다 (`/ingestion`, `/observations` 같은 파일 수신 엔드포인트는 도입하지 않으며 파일 handoff 방식을 유지함).

| Method | Path | Target 의미 및 4대 파이프라인 단계 | 상태 |
|---|---|---|---|
| GET | `/health` | Generator 데몬 상태 확인 | Current (유지) |
| POST | `/extraction` | gen_data protocol data에 지정·승인된 Mapping을 적용하여 Versioned Canonical Observation Dataset을 발행하고, 별도 Authorized Truth Source로 Failure Dataset을 발행 (관련 후속 작업: Issue #108) | Target — 미병합 |
| POST | `/preprocessing` | Observation Dataset을 분석하여 불변 Preprocessing Plan 수립 및 발행 (신규 2단계) | Current — 구현 완료 |
| POST | `/feature` | Observation Dataset, Failure Dataset, Preprocessing Plan, Feature Schema 및 Label Schema를 소비하여 Feature/Label Dataset Bundle 발행 (신규 3단계) | Current — 구현 완료 |
| POST | `/train` | Feature Dataset Bundle을 소비하여 전체 머신러닝 모델 학습 및 Model Artifact 발행 (신규 4단계) | Current — 구현 완료 |
| POST | `/train/{base_model}` | Feature Dataset Bundle을 소비하여 특정 머신러닝 모델 학습 및 Model Artifact 발행 (신규 4단계) | Current — 구현 완료 |
| POST | `/models/{base_model}/activate/{model_version}` | 기존 발행된 불변 Model Artifact 패키지 수동 활성화 | Target — 미병합 |
| GET | `/models/{base_model}/active` | 현재 활성화된 Model Artifact 정보 조회 | Target — 미병합 |

---

## 4. Preprocessing Plan 불변 식별 및 저장 구조 계약

### 4.1 Plan ID와 Plan Version 분리

- **`preprocessing_plan_id`**: 발행 단위 고유 식별자 (`pp-{UUID4}`, 예: `pp-7c106819-cc59-46da-90dd-22c37c441ac9`).
- **`preprocessing_plan_version`**: Dataset 식별자, `source_dataset_sha256`, `source_schema_fingerprint`, `decision_source`, `fallback_reason`, `planner_version`, 구조 유형, 선택 컬럼 및 중복 정책을 포함하는 canonical 지문 기반 16자리 SHA-256 해시 버전 (`preprocessing-plan-{hash}`, 예: `preprocessing-plan-38f74cc175d5ad12`).

### 4.2 Dataset Provenance, Schema Fingerprint 및 Planner 판단 이력

- **입력 결합**: Preprocessing Plan은 Dataset ID/version뿐 아니라 실제 입력 Dataset의 SHA-256 체크섬(`source_dataset_sha256`) 및 논리 상대경로(`source_dataset_uri`)와 결합되어 발행됩니다.
- **Source Schema Fingerprint**: 원본 Dataset의 컬럼 index, 컬럼명, canonical dtype을 기반으로 한 64자리 SHA-256 지문(`source_schema_fingerprint`)을 기록하여 값 변경과 구조 변경을 명확히 구분합니다.
- **Planner 판단 이력**: Plan 생성 방식(`decision_source`: `llm` 또는 `rule_fallback`), fallback 발생 시 정제된 사유(`fallback_reason`), Planner 계약 버전(`planner_version`: `preprocessing-planner-v1`)을 기록합니다.
- **버전 결정성**: 같은 Dataset과 역할 설정이라도 파일 내용(sha256), 컬럼 구조(schema fingerprint), Planner 생성 경로(`decision_source`) 또는 Planner 버전이 다르면 다른 `preprocessing_plan_version`이 생성됩니다.

### 4.3 Structure Type 허용 목록 및 Logical URI Fail-Closed 계약

- **공식 지원 `structure_type`**: `tabular_column_as_attribute`, `tabular_row_as_attribute` 2종류만 공식 지원합니다. `wide_pivot` 및 미지원 형식은 임의 fallback 없이 `422 PREPROCESSING_PLAN_VALIDATION_ERROR`로 거부됩니다.
- **Logical URI Fail-Closed**: `source_dataset_uri`, `preprocessing_plan_uri`는 허용된 저장소 루트(`PATHS.data_dir`, `PATHS.models_store`, workspace) 기반의 논리 상대경로만 저장됩니다. 허용 루트 밖의 경로는 Fail-Closed로 거부(`422 DATASET_CONTRACT_ERROR`)되며 오류 응답에 전체 절대경로가 노출되지 않습니다.

### 4.4 Plan 검증 및 재사용 규칙

- **입력 및 구조 무결성 검증**: `force_reanalyze=False` 시 현재 Dataset의 SHA-256 및 Schema Fingerprint와 Plan의 메타데이터를 비교하여 불일치 시 `409 PREPROCESSING_PLAN_CONFLICT`를 반환합니다 (detail에 `content_changed`, `schema_changed`, 이전/현재 해시 상세 제공).
- **중복 정책 검증**: 요청된 `duplicate_policy` 및 `aggregation`이 기존 Plan과 다르면 `409 PREPROCESSING_PLAN_CONFLICT`를 반환합니다.
- **Fail-Fast 컬럼 검증**: Plan에 선언된 `selected_columns` 또는 역할 컬럼(`id_column`, `time_column` 등) 중 하나라도 Dataset에 없으면 임의 fallback 없이 즉시 `422 PREPROCESSING_PLAN_VALIDATION_ERROR`를 발생시킵니다.
- **Wide-format Timestamp 정규화**: Wide-format에서도 `time_column`이 선언된 경우 `datetime64[ns]` 정규화 및 `[id_column, time_column]` 안정 정렬(stable sort)을 수행합니다.
- **발행 안정성**: 전체 Dataset 변환이 성공적으로 검증된 경우에만 Plan 파일과 `latest.json` 포인터가 발행됩니다.

### 4.5 저장 디렉터리 및 원자적 발행 순서

```text
models_store/cache/preprocessing_plans/
└─ {dataset_id}/
   └─ {dataset_version}/
      ├─ pp-{uuid}.json    # 불변 Plan 파일 (덮어쓰기 금지)
      └─ latest.json       # 현재 유효한 Plan을 가리키는 원자적 포인터 파일
```

- **Plan 본문 원자적 발행**: Plan 본문은 고유 ID의 불변 파일(`pp-{uuid}.json`)로 원자적으로 발행한다.
- **포인터 원자적 갱신**: Plan 파일 작성과 checksum 검증이 완료된 뒤 `latest.json` 포인터를 별도의 원자적 replace로 갱신한다.
- **포인터 무결성**: `latest.json`은 검증되지 않았거나 불완전한 Plan을 가리키지 않는다. Plan 파일 발행 후 포인터 갱신 전에 프로세스가 중단되면 latest에서 참조되지 않는 비활성 Plan 파일이 남을 수 있으나, 비활성 Plan은 활성 계약을 오염시키지 않으며 후속 점검 또는 정리 작업에서 식별할 수 있다.
- **기존 캐시 정책**: 기존 flat 캐시 파일(`{dataset_id}-{dataset_version}.json`)은 자동으로 최신 정본으로 승격하지 않으며 로그에 legacy 캐시 감지를 기록하고 새 구조로 신규 발행합니다.

---

## 5. Current 요청/응답 계약

### 5.1 `GET /health`

**성공 응답 본문:**
```json
{
  "status": "ok",
  "system": "generator"
}
```

### 5.2 `POST /preprocessing`

**요청 본문:**
```json
{
  "dataset_id": "ai4i",
  "dataset_version": "canonical-v3.1",
  "source_uri": "ai4i/canonical-v3.1.csv",
  "force_reanalyze": false,
  "duplicate_policy": "error",
  "aggregation": null
}
```

**성공 응답 본문:**
```json
{
  "request_id": "req-9c8f2a1b",
  "run_id": "preprocessing-3d4e5f6a",
  "status": "succeeded",
  "dataset_id": "ai4i",
  "dataset_version": "canonical-v3.1",
  "preprocessing_plan_id": "pp-7c106819-cc59-46da-90dd-22c37c441ac9",
  "preprocessing_plan_version": "preprocessing-plan-38f74cc175d5ad12",
  "result": {
    "structure_type": "tabular_column_as_attribute",
    "id_column": "UDI",
    "time_column": null,
    "attribute_column": null,
    "value_column": null,
    "duplicate_policy": "error",
    "aggregation": null,
    "preprocessing_plan_uri": "models_store/cache/preprocessing_plans/ai4i/canonical-v3.1/pp-7c106819-cc59-46da-90dd-22c37c441ac9.json",
    "preprocessing_plan_sha256": "4a7f...e3b8"
  }
}
```

### 5.3 `POST /internal/train`, `POST /internal/retrain` (호환성)

**요청 본문:**
```json
{
  "data_dir": "data",
  "force_reanalyze": false
}
```

**성공 응답 본문:**
```json
{
  "capabilities": {
    "EquipmentMonitoring": true,
    "SensorAnalytics": true,
    "MaintenanceHistory": false,
    "FailurePrediction": true,
    "ErrorTracking": false
  },
  "mappings": {},
  "registry": {
    "run_version": 3,
    "run_id": "run-v3-20260818070000",
    "trained_at": "2026-08-18T07:00:00+00:00",
    "models": {
      "lightgbm": {
        "model_id": "pdm-cnc-tool-wear-lightgbm",
        "model_version": "v3",
        "local_path": "models_store/lightgbm/model_v3.joblib",
        "artifact_uri": "models_store/artifacts/pdm-cnc-tool-wear-lightgbm/v3",
        "train_positive_rate": 0.0507,
        "validation_metrics": { "average_precision": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0 },
        "test_metrics": { "average_precision": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0 }
      }
    },
    "failed_models": null,
    "published_artifacts": {
      "pdm-cnc-tool-wear-lightgbm": {
        "model_id": "pdm-cnc-tool-wear-lightgbm",
        "model_version": "v3",
        "artifact_uri": "models_store/artifacts/pdm-cnc-tool-wear-lightgbm/v3"
      }
    }
  }
}
```

### 5.4 Current Model Artifact 발행 계약

- 학습에 성공한 모델은 immutable한 Model Artifact 패키지(`model-artifact-v1.0`)로 발행됩니다.
- 동일한 `model_id`와 `model_version` 조합의 기존 아티팩트는 덮어쓰지 않습니다.
- 발행 위치는 `MODEL_ARTIFACT_URI` 환경변수 또는 주입된 artifact 경로를 사용합니다.
- Generator 학습과 Runtime Prediction이 소비하는 정본은 Manifest와 Role 파일을 온전히 포함한
  Model Artifact입니다. Backend는 Model Artifact 대신 versioned Prediction Result Batch를 소비합니다.

### 5.5 Current Startup · Shutdown · 동시성 계약

- **Startup 아티팩트 검사**: Generator startup은 `has_any_published_model_artifact()`를 사용하여 대상 디렉터리에 유효하게 발행된 Model Artifact가 존재하는지 확인합니다.
- **Initial Training 백그라운드 예약**: 유효한 Model Artifact가 존재하지 않을 경우 initial training을 백그라운드 태스크로 예약하며, ASGI startup 프로세스를 차단하지 않습니다.
- **Startup 자동 학습 생략**: 유효한 Model Artifact가 이미 존재하면 startup 시 자동 학습을 안전하게 생략합니다.
- **Shutdown 대기**: 프로세스 shutdown 시 현재 실행 중인 initial training worker가 정상 완료될 때까지 대기합니다.
- **프로세스 전역 Training Lock**: startup 학습과 `POST /internal/train` 및 `POST /internal/retrain`은 동일한 process-wide training lock(`_training_lock`)을 공유합니다.

### 5.6 Feature Dataset Bundle 계약 (`POST /feature` — Current)

Observation Dataset, Failure Dataset(또는 내장 Failure indicator), Preprocessing Plan, Feature Schema 및 Label Schema를 소비하여 Feature 및 Horizon Label을 계산하고 불변 Feature Dataset Bundle(5개 필수 파일)을 원자적으로 발행합니다.

```json
// 요청 예시 (external_dataset 모드)
{
  "dataset_id": "ai4i",
  "dataset_version": "canonical-ai4i-physics-v3.1",
  "failure_source_mode": "external_dataset",
  "failure_dataset_id": "ai4i_failures",
  "failure_dataset_version": "canonical-ai4i-failures-v1",
  "preprocessing_plan_id": "pp-7c106819-cc59-46da-90dd-22c37c441ac9",
  "preprocessing_plan_version": "preprocessing-plan-a1b2c3d4e5f67890",
  "feature_schema_version": "ai4i-feature-v1",
  "label_schema_version": "ai4i-label-24h-v1",
  "prediction_horizon_hours": 24
}
```

- **Versioned Dataset 입력 경로 및 Manifest 계약**:
  - Observation: `data/observations/{dataset_id}/{dataset_version}/` (`dataset_manifest.json`, `observations.csv` 또는 `.jsonl`)
  - Failure: `data/failures/{dataset_id}/{dataset_version}/` (`dataset_manifest.json`, `failures.csv` 또는 `.jsonl`)
  - `contracts/schemas/generator-dataset-input-manifest.schema.json` 검증, 단일 role(`observations`, `failures`), payload SHA-256 및 크기 검증.
  - unversioned 파일(`data/{dataset_id}.csv` 등)의 암묵적 검색 fallback 완전 제거.
- **Preprocessing Plan과 Observation Manifest 상호 검증**:
  - `request.dataset_id == Plan.dataset_id == Observation Manifest.dataset_id`
  - `request.dataset_version == Plan.dataset_version == Observation Manifest.dataset_version`
  - `Plan.source_dataset_sha256 == Observation payload SHA-256`
  - 불일치 시 `422 FEATURE_CONTRACT_ERROR`로 fail-closed.
- **Failure Source 계약 (`failure_source_mode`)**:
  - `external_dataset`: `failure_dataset_id` 및 `failure_dataset_version`이 필수이며, 파일 부재 시 Observation 데이터셋으로 대체하지 않고 즉시 `404 FEATURE_INPUT_NOT_FOUND`로 실패합니다.
  - `embedded_observation`: Observation 내부 failure indicator 컬럼(`Machine failure` 등)을 사용하며, indicator 컬럼 부재 시 `422`로 실패합니다.
- **계산된 Feature 의미 보존**:
  - `lag`, `diff`, `rolling`, `ewm` 등 변환 연산 결과(`series`)에 대해 `missing_value_policy == "ffill"` 적용 시 원본 source 컬럼으로 되돌아가지 않고 계산된 series 자체를 설비 단위(`asset_id`)로 forward-fill합니다.
- **Failure 설비 Identity 및 제외 구간 Fail-Closed**:
  - 다중 설비 데이터셋에서 Failure 데이터셋의 asset ID 컬럼 누락, 결측치 또는 Observation에 존재하지 않는 asset ID 포함 시 `422 FEATURE_LABEL_ALIGNMENT_ERROR`를 반환합니다.
  - Label Schema가 선언한 `anchor` 및 `exclusion_end` 컬럼 누락, NaT 또는 `exclusion_end < anchor` 위반 시 `422`로 처리하며, `[anchor, exclusion_end]` 전체 구간을 학습 데이터에서 엄격히 제거합니다.
- **`binary_failure_within_horizon` Feature Dataset 발행 조건 (Fail-Closed)**:
  1. **Canonical Observation timestamp 필수**: 누락 또는 NaT 포함 시 `422 FEATURE_LABEL_ALIGNMENT_ERROR`로 거부.
  2. **유효한 failure event 최소 1건 필수**: 외부 Failure Dataset 0행 시 `422 INSUFFICIENT_TRAINING_DATA`로 거부.
  3. **Active failure filtering 후 event 최소 1건 필수**: indicator 필터링 후 0건 시 `422 INSUFFICIENT_TRAINING_DATA`로 거부.
  4. **내장 failure event timestamp 오류 거부**: embedded indicator 행의 timestamp NaT 시 건너뛰지 않고 `422 FEATURE_LABEL_ALIGNMENT_ERROR`로 거부.
  5. **최종 Label 클래스 `{0, 1}` 양자 공존 필수**: 최종 생존 라벨에 0과 1이 모두 존재해야 하며, 단일 클래스 시 `422 INSUFFICIENT_TRAINING_DATA`로 거부.
  6. **설비 Identity & 제외 구간 엄격성**: 다중 설비에서 failure asset 누락/미소속 시 `422`, `anchor`/`exclusion_end` 누락, NaT, 또는 `exclusion_end < anchor` 위반 시 `422` 반환 및 `[anchor, exclusion_end]` 전체 구간 학습 데이터 제외.
- **Asset identity requirement (Fail-Closed 501)**:
  - `POST /feature`가 소비하는 Observation Dataset에는 Preprocessing Plan의 `id_column`으로 선언된 설비 식별 컬럼이 반드시 존재해야 합니다.
  - 현재 파이프라인은 ID가 없는 Dataset을 자동으로 단일 설비로 간주하거나 임시 ID(`row_{idx}`, `default_asset`)를 생성하지 않습니다.
  - Preprocessing Plan에 `id_column` 누락, Dataset 내 선언된 ID 컬럼 부재, 또는 ID 컬럼에 null/빈 문자열이 존재할 경우 `501 Not Implemented` (`code: FEATURE_ASSET_ID_RESOLUTION_NOT_IMPLEMENTED`)로 실패하며 Feature Dataset Bundle을 발행하지 않습니다.
  - ID가 없는 단일 설비 Dataset 지원은 후속 기능으로 별도 구현합니다.

```json
// 501 FEATURE_ASSET_ID_RESOLUTION_NOT_IMPLEMENTED 응답 예시
{
  "error": {
    "code": "FEATURE_ASSET_ID_RESOLUTION_NOT_IMPLEMENTED",
    "message": "Observation Dataset에서 설비 ID를 식별할 수 없습니다. 현재 Feature 파이프라인은 Preprocessing Plan에 의해 명시된 asset ID가 필요하며, ID가 없는 단일 설비 데이터의 자동 ID 생성 기능은 아직 지원하지 않습니다.",
    "path": "/feature",
    "request_id": "req-17091db43b52",
    "error_id": "err-3c819d4a",
    "details": [
      {
        "required_contract": "preprocessing_plan.id_column",
        "unsupported_case": "observation_without_asset_id",
        "required_follow_up": "single-asset identity resolution 기능 구현"
      }
    ]
  }
}
```

- **허용되지 않는 Fallback (Prohibited Fallbacks)**:
  - `row_{idx}`, `default_asset` 등 임시 asset ID 생성 금지
  - Preprocessing Plan의 `id_column` 누락 시 임의 컬럼 휴리스틱 선택 금지
  - timestamp 위치 기반 추측 금지
  - invalid timestamp 행 조용한 건너뛰기(silent skip) 금지
  - 빈 Failure Dataset을 정상 Dataset으로 처리 금지
  - all-zero Label Bundle 발행 금지
  - 단일 클래스 Label을 Training 단계로 전달 금지
  - unversioned 파일 검색 fallback 금지
- **5개 필수 파일 구성**: `features.npy`, `labels.npy`, `feature_columns.json`, `row_metadata.json` (실제 `asset_id` 보존), `feature_metadata.json`
- **저장 디렉터리**: `models_store/cache/features/{dataset_id}/{dataset_version}/{feature_dataset_version}/`
- **식별자 결정론**: `feature_dataset_version`은 입력 Dataset Manifest 및 Payload SHA-256, `failure_source_mode`, Plan(ID/ver/sha), Schema(ver/sha)의 canonical fingerprint로 결정론적 산출.
- **Ontology Mapping 배제**: Feature 단계는 Ontology Mapping을 조회하지 않고 Feature Schema allowlist/recipe만 실행합니다.

### 5.7 Training 및 Model Artifact 발행 계약 (`POST /train`, `POST /train/{base_model}` — Current)

검증된 Feature Dataset Bundle을 소비하여 설비·시간 기준 분할(`asset_time_split`), 모델별 학습 및 평가를 수행하고 불변 Model Artifact 패키지(6개 파일)를 원자적으로 발행하며 `latest.json` 포인터를 자동 갱신합니다.

> **현재 계약 원칙**: `latest.json`은 검증된 Model Artifact가 정상 발행될 때마다 Generator가 자동으로 갱신하는 시스템 관리 포인터입니다. 현재 API는 사용자에 의한 버전 선택 또는 포인터 변경을 지원하지 않습니다.

```json
// 요청 예시
{
  "dataset_id": "ai4i",
  "dataset_version": "canonical-ai4i-physics-v3.1",
  "feature_dataset_version": "feature-dataset-a1b2c3d4e5f67890",
  "training_config_version": "training-config-v1",
  "model_version": "lightgbm-v1.0"
}
```

```json
// 응답 예시
{
  "request_id": "req-17091db43b53",
  "run_id": "run-a8b9c0d1e2f3",
  "status": "succeeded",
  "dataset_id": "ai4i",
  "dataset_version": "canonical-ai4i-physics-v3.1",
  "feature_dataset_version": "feature-dataset-a1b2c3d4e5f67890",
  "training_config_version": "training-config-v1",
  "results": [
    {
      "base_model": "lightgbm",
      "model_id": "pdm-lightgbm",
      "model_version": "lightgbm-v1.0",
      "status": "succeeded",
      "published": true,
      "latest_updated": true,
      "model_artifact_uri": "models_store/artifacts/pdm-lightgbm/lightgbm-v1.0",
      "artifact_uri": "models_store/artifacts/pdm-lightgbm/lightgbm-v1.0",
      "metrics_summary": {
        "f1": 0.8571,
        "precision": 0.8823,
        "recall": 0.8333,
        "accuracy": 0.9850,
        "roc_auc": 0.9654,
        "pr_auc": 0.8920
      },
      "activated": true,
      "activation_error_code": null,
      "error_code": null
    }
  ]
}
```

- **Training Config 및 Hyperparameter 해결 계약**:
  - `training_config_version`은 `contracts/schemas/generator-training-config.schema.json` 검증을 통과한 설정 파일과 1:1 바인딩됩니다.
  - 설정 파일 부재 시 `404`, 스키마/버전 불일치 시 `422`로 실패하며, 설정 파일 SHA-256 및 논리 URI가 manifest provenance에 기록됩니다.
  - 최상위 `random_seed`가 학습 시드의 유일한 단일 정본으로 사용되며, 모델별 `hyperparameters` 내부의 `random_state`, `seed`, `random_seed` 중복 선언은 정적 검증 및 런타임에서 `422 TRAINING_CONTRACT_ERROR`로 Fail-Closed 차단됩니다.
  - Trainer의 `resolve_parameters(configured, random_seed)`를 통해 기본값보다 설정값을 우선 적용한 `resolved_parameters`가 실제 Estimator `get_params()` 및 Manifest `training_config`에 온전히 기록됩니다.
- **Prediction Horizon 의미 계약 및 Schema 교차 검증**:
  - Feature Bundle provenance의 `prediction_horizon_hours`는 양의 정수(`int > 0`, `bool`/`float`/`str` 불가)여야 합니다.
  - Model Artifact staging 및 발행 전 Label Schema 스냅샷의 `prediction_horizon_hours`와 일치하는지 교차 검증하며, 불일치 시 `422 TRAINING_CONTRACT_ERROR`로 즉시 Fail-Closed 처리되어 불완전한 아티팩트 생성을 방지합니다.
- **Feature/Label Schema 스냅샷 및 History Requirement**:
  - 축약 없는 온전한 Feature Schema 및 Label Schema 스냅샷을 검증하여 아티팩트에 포함합니다.
  - `history_requirement.json`은 원본 센서 필드 목록(`required_columns`)과 연산 파라미터(lag/rolling/ewm)를 반영하여 `minimum_history_rows`를 결정론적으로 산출합니다.
- **Fail-Closed 데이터 분할 (`asset_time_split`)**:
  - `row_metadata.json`의 모든 행에 `asset_id`와 `timestamp`가 필수이며, 결측 또는 NaT 발생 시 `422 TrainingDatasetError`로 처리합니다.
  - 시간 분할 후 train partition에 단일 클래스만 존재할 경우 즉시 `422 TrainingDatasetError`로 Fail-Closed 처리됩니다.
- **6개 필수 파일 구성**: `manifest.json`, `model.joblib`, `feature_schema.json`, `label_schema.json`, `history_requirement.json`, `metrics.json`
- **저장 디렉터리**: `models_store/artifacts/{model_id}/{model_version}/`
- **2단계 발행(Two-Phase Publication) 및 불변성 정책**:
  - **Phase A (불변 아티팩트 원자적 발행)**: 임시 디렉터리(`.tmp_{uuid}`)에서 6개 파일 생성 및 manifest 전수 검증 완료 후 atomic rename으로 커밋합니다.
  - **Phase B (최신 포인터 갱신)**: non-blocking OS advisory lock(`artifacts/{model_id}/.latest.lock`) 하에서 `latest.json`을 원자적으로 갱신합니다.
  - **상태 분리 및 부분 실패 보존**: Phase B 실패 시 이미 커밋된 불변 아티팩트를 삭제하거나 rollback하지 않고 보존하며, API 응답/details에 `published=True`, `model_artifact_uri=...`, `latest_updated=False`, `latest_error_code=...`를 투명하게 기록합니다.
  - **동일 아티팩트 멱등 복구**: 동일 입력 계약으로 재요청 시 디렉터리와 checksum이 온전히 존재하면 아티팩트 재작성을 건너뛰고 `latest.json` 갱신만 안전하게 재시도합니다. 이미 최신 포인터로 활성화된 상태라면 `409 MODEL_ARTIFACT_CONFLICT`를 반환합니다.
- **오류 체계 및 장애 격리 정책**:
  - 현재 Generator는 단일 인스턴스와 순차 Pipeline 실행을 기본으로 합니다. 비정상 Bundle 입력, 동일 Artifact 발행 경쟁 및 저장소 I/O 장애가 발생하면 자동 복구를 추측하지 않고 fail-closed하며, 실패 단계에 맞는 409·422·500 오류를 반환합니다.
  - 다중 Worker·Replica의 분산 상호 배제, 저장소 장애 자동 복구, staging 잔재 정리 및 reconciliation은 Issue #117의 운영 고도화 범위로 관리합니다.

| HTTP | 오류 코드 | 적용 상황 |
|---:|---|---|
| 422 | `FEATURE_DATASET_INTEGRITY_ERROR` | `row_metadata`가 배열이 아니거나 항목이 객체가 아님, 파일 누락/체크섬 불일치 |
| 422 | `TRAINING_DATASET_ERROR` | timestamp 누락·파싱 실패·bool·NaN·Inf, 단일 클래스, 행 수 부족 |
| 409 | `MODEL_ARTIFACT_CONFLICT` | 동일 Artifact 존재 또는 동시 rename 충돌 |
| 500 | `MODEL_ARTIFACT_PUBLISH_ERROR` | Artifact staging·작성·commit I/O 실패 |
| 409 | `MODEL_LATEST_UPDATE_IN_PROGRESS` | 실제 latest 포인터 lock 경합 |
| 500 | `MODEL_LATEST_UPDATE_FAILED` | 포인터 파일 준비·작성·교체 I/O 실패 |
| 500 | `MODEL_LATEST_VERIFY_FAILED` | 포인터 교체 후 read-back 불일치 |

- **부분 성공 격리**: 전체 모델 학습(`POST /train`) 시 특정 모델의 실패는 `partially_succeeded`로 격리되어 정상 모델의 성공 아티팩트 발행을 취소하지 않습니다.

### 5.8 Extraction 및 Canonical Observation 발행 계약 (`POST /extraction` — Current)

`POST /extraction`은 최초 승인 Mapping(`generator-static-mapping-table`)을 기준으로 동일 Source의 append-only 증분 추출을 수행합니다.

- **Logical Source Scope Single-Writer Lock**:
  - 동시성 제어 및 single-writer 락은 파일 내용과 무관한 `source_lock_identity = hash(source_uri + site_id + cell_id + source_format)`을 기준으로 획득합니다.
  - provenance 추적용 `source_identity`는 첫 레코드 해시를 포함하는 기존 계약을 유지하며, 락 식별자와 분리됩니다.
- **모든 경로에서의 Scope Checkpoint 검증**:
  - 신규 0바이트, 불완전 첫 행, 정상 첫 행, EOF, 신규 append, recovery 등 모든 요청은 락 내부에서 `find_checkpoint_by_source()`를 최우선으로 거칩니다.
- **오류 판정 우선순위 (Error Priority Hierarchy)**:
  1. `요청 Mapping 계약 검증`: 요청 본문의 Mapping 스키마/규격 오류 시 즉시 거부
  2. `기존 Checkpoint 상태 검증`: Checkpoint I/O 실패(`500 EXTRACTION_CHECKPOINT_READ_FAILED`), 손상(`422 EXTRACTION_CHECKPOINT_INVALID`), Scope 중복(`409 EXTRACTION_CHECKPOINT_SCOPE_CONFLICT`), 구형 Migration(`422 EXTRACTION_CHECKPOINT_MAPPING_MIGRATION_REQUIRED`), 파일명/본문 identity 불일치(`422 EXTRACTION_CHECKPOINT_INVALID`) 검증
  3. `Mapping Identity 불일치 감지`: 요청 Mapping과 기존 Checkpoint Mapping 불일치 시 `409 EXTRACTION_MAPPING_REBUILD_NOT_IMPLEMENTED` (Source 0바이트/EOF보다 우선 판정)
  4. `Source Identity 및 Prefix 검증`: 첫 레코드 해시 변경 또는 verified prefix checksum 불일치 시 `422 EXTRACTION_SOURCE_PREFIX_MISMATCH`
  5. `Source Truncate 검증`: committed offset 또는 pending batch offset 대비 파일 크기 축소 시 `422 EXTRACTION_SOURCE_TRUNCATED`
  6. `신규 빈 Source`: Checkpoint가 없는 신규 0바이트/미완성 Source에 한해 `status="no_data"` 반환
  7. `Pending Recovery 및 정상 증분 처리`: pending batch 검증 및 commit 후 정상 증분 추출 진행

- **Silent Ignore 금지 및 탐색 정책**:
  - 동일 Source scope(`source_uri`, `site_id`, `cell_id`)에 해당하는 구형 또는 손상 Checkpoint는 절대 "없는 Checkpoint"로 무시하지 않으며, 명시적인 Migration 또는 무결성 오류로 즉시 Fail-Closed 처리합니다.
  - Checkpoint 저장소 탐색 중 손상·읽기 실패 파일이 발견되면 안전을 위해 탐색 전체를 Fail-Closed합니다. (Source별 index 및 격리는 운영 자산 Registry 후속 범위)
- **Pending Fragment Recovery 안전성**:
  - `fragment_staged` 상태의 pending batch 복구 시, 현재 파일 크기가 pending batch의 `source_end_offset` 이상이고 Mapping Identity가 일치하는 경우에만 commit을 확정합니다.
- **불변성 보존**:
  - Mapping/scope/source 무결성 검증 실패는 기존 상태를 변경하지 않음
  - processing 진입 이후 실패는 committed offset과 기존 fragment/dataset을 보존하되 recovery를 위해 checkpoint status가 변경될 수 있음

#### Extraction 오류 코드 표

| HTTP | 오류 코드 | 조건 | 재시도 |
|---:|---|---|---|
| 409 | `EXTRACTION_MAPPING_REBUILD_NOT_IMPLEMENTED` | 동일 Source가 기존 checkpoint와 다른 Mapping으로 요청됨 | 불가 |
| 422 | `EXTRACTION_SOURCE_PREFIX_MISMATCH` | Source 첫 레코드 해시 또는 verified prefix checksum 불일치 | 불가 |
| 422 | `EXTRACTION_CHECKPOINT_MAPPING_MIGRATION_REQUIRED` | 기존 checkpoint에 Mapping identity가 없음 | 자동 재시도 불가 |
| 422 | `EXTRACTION_CHECKPOINT_INVALID` | Checkpoint 파일 JSON 손상, 스키마 위반, 파일명/본문 identity 불일치, pending 불일치 | 자동 재시도 불가 |
| 500 | `EXTRACTION_CHECKPOINT_READ_FAILED` | Checkpoint 파일 읽기 I/O 오류 | 가능 |
| 409 | `EXTRACTION_CHECKPOINT_SCOPE_CONFLICT` | 동일 Scope(`source_uri`, `site_id`, `cell_id`)에 복수의 Checkpoint 존재 | 불가 |
| 422 | `EXTRACTION_SOURCE_TRUNCATED` | 기존 checkpoint offset 또는 pending batch end offset보다 Source 크기가 작거나 0바이트로 축소됨 | 불가 |
| 409 | `EXTRACTION_SOURCE_LOCKED` | 동일 Source에 대해 다른 추출 프로세스가 락을 보유 중 | 가능 |
| 500 | `EXTRACTION_FRAGMENT_WRITE_FAILED` | Fragment 파일 open/write/flush 또는 rename I/O 실패 | 가능 |
| 409 | `EXTRACTION_FRAGMENT_CONFLICT` | 동일 batch_id 대상 상이/손상된 Fragment 존재 | 불가 |

#### Extraction 기능 지원 현황 (Current vs Target)

| 기능 | 현재 상태 | 설명 |
|---|:---:|---|
| 최초 승인 Mapping 기반 추출 | **Current** | 승인된 정적 매핑 테이블 기반 canonical observation 변환 |
| 동일 Mapping append-only 증분 처리 | **Current** | Source offset checkpoint 기반 안전한 증분 추출 |
| Logical Scope Single-Writer Lock | **Current** | source_uri/site_id/cell_id 기준 상호 배제 Lock |
| Mapping identity 불일치 감지 | **Current** | Checkpoint에 mapping_id/version/sha256 보존 및 비교 |
| Source 교체/Prefix 불일치 감지 | **Current** | 422 EXTRACTION_SOURCE_PREFIX_MISMATCH 반환 |
| Mapping 변경 요청 fail-closed | **Current** | 409 EXTRACTION_MAPPING_REBUILD_NOT_IMPLEMENTED 반환 |
| 0바이트 Truncate 및 손상 감지 | **Current** | 422 EXTRACTION_SOURCE_TRUNCATED 반환 |
| Checkpoint I/O 및 손상 감지 | **Current** | 500 READ_FAILED / 409 SCOPE_CONFLICT / 422 INVALID 반환 |
| Mapping 변경 과거 Source replay | **Target** | offset 0부터 결정론적 replay (Issue #146) |
| Mapping별 Checkpoint·Dataset 재구성 | **Target** | Multi-mapping Checkpoint 분리 및 Dataset Version 재발행 (Issue #146) |
| Mapping 활성화·rollback | **Target** | 런타임 활성 Mapping 전환 및 rollback (Issue #146) |
| Mapping 관리 UI | **Target** | Mapping 조회/편집/승인 웹 UI (Issue #146) |

---

## 6. Target Contract 예시 (후속 목표 설계 — Issue #117)

> **주의**: 특정 버전 조회·실행·운영 전환·rollback은 Issue #117에서 단계적으로 구현합니다. 해당 기능이 도입되기 전까지 모든 Runtime 소비자는 유효한 `latest.json`을 기본 포인터로 사용합니다.

### 6.1 Issue #117 단계적 고도화 로드맵
- **Phase 1 (현재 완료)**: Model Artifact 정상 발행 시 `latest.json` 자동 갱신 및 파일 락, 원자적 교체, 부분 실패 보존.
- **Phase 2 (후속)**: 모델별 발행 버전 목록 및 최신 포인터 조회 전용 API (`GET /models`, `GET /models/{model_id}/versions`, `GET /models/{model_id}/latest`).
- **Phase 3 (후속)**: 특정 버전 지정 일회성 실행 (기본 `latest.json` 변경 없음, 감사 로그 기록).
- **Phase 4 (후속)**: 운영자 전용 수동 버전 전환 및 rollback 내부 API (`POST /internal/models/{model_id}/select-version`, `POST /internal/models/{model_id}/rollback`).
- **Phase 5 (후속)**: 자동 최신 포인터(`latest.json`)와 운영 선택 포인터(`selected.json`) 역할 분리 검토.
