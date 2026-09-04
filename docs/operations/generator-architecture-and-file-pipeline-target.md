# Generator 목표 아키텍처 및 파일 가공 파이프라인 명세서

> **문서 상태**: `Proposed Target` (제안된 목표 설계)
> **주의**: 본 문서는 현재 `main`에 구현된 코드를 설명하는 문서가 아닙니다. 본 문서는 향후 진행될 Generator 구조 개편, 단계별 책임 분리, API 명칭 전환 및 파일 가공 파이프라인 Migration 작업의 단일 기준이 되는 **목표 설계(Target Specification) 문서**입니다.

---

## 1. 배경 및 목적

1. **Observation/Feature Series 책임 정립 (생산자 경계 확립 작업)**:
   - Generator 시스템을 센서/프로토콜 로그로부터 정제된 Observation 및 Feature Series를 생성하는 공식 생산자(Producer)로 정의합니다.
   - 제품 런타임(Backend Diagnosis)은 `gen_data`의 저수준 프로토콜 로그 파일을 직접 파싱하지 않고, Generator가 가공·발행한 정제된 Observation/Feature 산출물 및 Model Artifact를 소비하도록 단방향 데이터 흐름을 확립합니다.

2. **SensorRecord v2 프로토콜과 Reference Fixture (Target dependency)**:
   - `gen_data`의 SensorRecord v2 프로토콜 투영(`protocol/provenance.jsonl`) 및 Protocol-to-Observation Golden Vector는 향후 도입될 **Target dependency(미병합)**입니다.
   - Generator 내부에는 이 파일 가공 흐름을 표준적·안정적으로 수행할 공식 파일 처리 계층이 아직 구현되어 있지 않으므로, 목표 구조와 가공 규칙을 먼저 문서로 확정합니다.

3. **단계 명칭 정립 및 책임 단일화**:
   - 별도 Generator API화 작업에서 설계된 `/extraction`은 데이터셋 구조 분석 및 Plan 수립을 담당했습니다.
   - Target 구조에서는 데이터셋 구조 분석 및 불변 Plan 발행을 `/preprocessing`으로 이전하고, `/extraction`은 protocol data에 지정·승인된 Mapping을 적용하여 Versioned Observation 및 Failure Dataset을 발행하도록 4대 파이프라인 단계(`Extraction` → `Preprocessing` → `Feature` → `Training`)의 역할을 명확히 확정합니다.

---

## 2. 시스템 아키텍처 구조 비교

### 2.1 Current 구조 (현재 main 구현 상태)

현재 `main` 브랜치의 Generator는 다음 단일 수준의 디렉터리 및 모듈 구성을 유지하고 있습니다.

```text
systems/generator/
├─ generator_main.py          # 데몬 진입점 및 FastAPI 애플리케이션 (현재 /internal 엔드포인트)
├─ generator_config.py        # 전역 경로 및 설정 싱글톤
├─ extraction/                # 데이터셋 프로파일링, 추출 계획 수립 (LLM)
├─ feature/                   # 피처 계산 모듈 (feature_builder 등)
├─ model/                     # 모델 알고리즘 학습 및 모델 레지스트리
├─ ontology_mapping/          # legacy/보조 semantic mapping 모듈; 신규 Feature API 실행 계약이 아님
├─ topology/                  # 설비 간 위상 관계 추론
├─ common/                    # 공통 에이전트 및 타임스탬프 정규화 유틸리티
├─ entrypoint.py
├─ Dockerfile
└─ requirements.txt
```

### 2.2 Target 구조 (후속 목표 설계)

후속 구조 개편 작업에서는 프레임워크 비의존 공통 모듈을 `systems/generator/` 최상위에 배치하고, use case와 API 계층을 `app/` 하위 도메인으로 분리합니다 (`core/` 디렉터리는 사용하지 않음).

```text
systems/generator/
├─ app/                       # [Target] FastAPI 애플리케이션 및 유스케이스 계층
│  ├─ main.py                 # FastAPI Application Factory (create_app)
│  ├─ dependencies.py         # 공통 의존성 주입 (Repository/Service/Settings)
│  ├─ api/                    # 중앙 Router 조립
│  ├─ extraction/             # [1단계 Current] gen_data Protocol Extraction 및 Canonical Observation 발행 도메인
│  │  ├─ extraction_router.py
│  │  ├─ extraction_service.py
│  │  ├─ extraction_repository.py
│  │  ├─ mapping_validator.py
│  │  ├─ mapping_repository.py
│  │  ├─ dedup_repository.py
│  │  ├─ checkpoint_repository.py
│  │  ├─ extraction_exception.py
│  │  ├─ parsers/
│  │  │  └─ sensor_record_parser.py
│  │  └─ extraction_schema.py
│  ├─ preprocessing/          # [2단계 Current] 데이터셋 분석, 불변 Plan 수립 도메인 (기존 extraction 이전)
│  │  ├─ preprocessing_router.py
│  │  ├─ preprocessing_service.py
│  │  ├─ preprocessing_planner.py
│  │  ├─ preprocessing_profiler.py
│  │  ├─ preprocessing_repository.py
│  │  └─ preprocessing_schema.py
│  ├─ feature/                # [3단계 Current] Feature/Label/Series 빌드 및 번들 발행 도메인
│  │  ├─ feature_router.py
│  │  ├─ feature_service.py
│  │  ├─ feature_repository.py
│  │  ├─ feature_schema_provider.py
│  │  ├─ label_schema_provider.py
│  │  └─ feature_schema.py
│  ├─ training/               # [4단계 Current] 모델 학습, 검증, Artifact 발행 및 활성화 도메인
│  │  ├─ training_router.py
│  │  ├─ training_service.py
│  │  ├─ training_repository.py
│  │  └─ training_schema.py
│  │
│  └─ runtime_pipeline/       # [Current] 런타임 자동 예측·이상 신호 파이프라인
│     ├─ pipeline_router.py
│     ├─ pipeline_service.py
│     ├─ pipeline_queue.py
│     ├─ pipeline_state.py
│     ├─ pipeline_worker.py
│     ├─ pipeline_manager.py
│     ├─ runtime_feature_service.py
│     ├─ prediction_service.py
│     ├─ prediction_batch_service.py
│     ├─ prediction_delivery_service.py
│     ├─ prediction_delivery_worker.py
│     ├─ pipeline_repository.py
│     ├─ pipeline_schema.py
│     └─ pipeline_exception.py
│
├─ settings.py                # [Target] 환경설정 싱글톤 (Pydantic Settings)

├─ paths.py                   # [Target] 시스템 전역 파일/디렉터리 경로 레지스트리
├─ logging.py                 # [Target] 구조화 로깅 유틸리티
├─ errors.py                  # [Target] 시스템 전역 표준 ErrorEnvelope 및 공통 예외
├─ file_integrity.py          # [Target] SHA-256 해시 계산 및 파일 안전성 검사기
└─ atomic_publish.py          # [Target] 원자적 임시 디렉터리/파일 Staging 및 교체 유틸리티
```

> **계층 의존성 원칙**: 최상위 공통 기반 모듈(`settings.py`, `paths.py`, `errors.py` 등)은 `app/` 하위 모듈을 절대 import하지 않으며, `FastAPI`에 의존하지 않는 순수 Python 모듈로 작성됩니다.

---

## 3. 4대 파이프라인 단계 및 정본 데이터 흐름 (Target)

시스템 간 통신은 API 호출 및 **파일 기반 Handoff**로 진행되며, `/ingestion`, `/observations` 같은 파일 수신 엔드포인트는 도입하지 않습니다.

```text
gen_data SensorRecord v2 protocol provenance
  ↓ (상태: Target dependency — 미병합)
Generator Observation Extraction (지정·승인된 Mapping 적용)
  ↓
Versioned Observation Dataset
  ↓
Generator Preprocessing (구조 및 역할 분석)
  ↓
Immutable Preprocessing Plan
  │
  └──────────────────────────────┐
                                 ↓
Authorized Training Truth Source │ (상태: Authorized Training Truth Source — Target 계약 필요)
  ↓                              │
Generator Failure Extraction     │
  ↓                              │
Versioned Failure Dataset ───────┤
                                 ↓
Generator Feature (Feature Schema allowlist/recipe + Label Schema 적용)
  ↓
Feature / Label / Series / Feature Dataset Bundle
  ↓
Generator Training
  ↓
Immutable Model Artifact (latest.json pointer)
  ↓
Backend Diagnosis (Runtime inference / Result Artifact / Evidence / Prediction History)
  ↓
Backend Detail ViewModel (AssetDetailViewModel composition via read port)
```

---

## 4. 단계별 상세 책임 명세 (Target)

### 4.1 1단계: Extraction (신규 파일 가공 — Target)

Extraction 도메인은 프로토콜 투영 로그와 별도의 공인된 Training Truth Source라는 두 개의 독립 입력 경로를 소유하며, 하위 use case를 엄격히 분리하여 정제된 시계열 Observation 및 Failure 데이터셋을 발행합니다.

```text
Extraction
├─ Observation Extraction
│  └─ protocol provenance + approved Mapping → Observation Dataset
└─ Failure Extraction
   └─ Authorized Training Truth Source → Failure Dataset
```

두 입력 소스는 독립적으로 schema, version, checksum 및 lineage를 검증합니다.

#### A. Observation Extraction (입력: 프로토콜 투영 로그)
- **입력**: `output/runs/{run_id}/protocol/provenance.jsonl` (`상태: Target dependency — 미병합`)
- **Protocol Provenance 공통 필드 (19개)**:
  - `direction`, `schema_version`, `observation_id`, `source_kind`, `record_kind`, `quality`, `run_id`, `sequence`, `asset_id`, `measurement_key`, `node_id`, `data_type`, `unit`, `value`, `status_code`, `observed_at_source`, `branch_kind`, `overlay`, `mapping_version`
- **Direction별 추가 필드 규격**:
  - `direction=published`: `source_timestamp`, `published_at` 추가 검증
  - `direction=received`: `source_timestamp`, `server_timestamp`, `received_at`, `status_code_value` 추가 검증
- **오류·격리 필드 분리 원칙**:
  - `reason`은 정상 provenance 공통 필드가 아니며, 오류 레코드(`errors.jsonl`) 또는 격리 레코드(`quarantine.jsonl`)의 오류/격리 사유로만 분리하여 기록합니다.
  - 정상 provenance, error record, quarantine record는 서로 다른 계약으로 관리하며 단일 스키마로 혼합하지 않습니다.
  - 확정 JSON Schema는 후속 계약 작업에서 direction별 `oneOf` 또는 discriminator 구조로 정의합니다.
- **Observation Pivot 정책 및 Direction 처리**:
  - **입력 Direction 결정 정책 (`상태: Accepted Input Direction — Target 계약 확정 필요`)**:
    - `direction=received`를 기본 입력으로 사용할지, `direction=published`도 허용할지는 입력 계약 확정 시 결정합니다.
    - 동일 run에서 published와 received를 동시에 입력하면 같은 측정값이 중복될 수 있으므로 자동 혼합하지 않습니다.
    - 한 Extraction 실행은 허용된 단일 `direction` 또는 명시적인 source projection 하나만 소비합니다.
  - **식별 기준**: `node_id` 문자열을 자산 및 measurement 식별의 정본으로 분해하지 않고, `asset_id`, `measurement_key`, `mapping_version`, `node_id`를 기본 필드로 우선 사용합니다 (`node_id`는 versioned mapping과의 일치 여부 검증용).
  - **Pivot 그룹 키**: `run_id`, `branch_kind`, `asset_id`, `normalized_observed_at` 기준으로 Observation 행을 묶어 피벗합니다 (Canonical과 Overlay, 서로 다른 run의 데이터 혼합 방지).
  - **중복 및 충돌 정책**:
    - 완전히 동일한 레코드 재수신 시: idempotent dedupe
    - 동일 measurement에 동일 값·상태: 단일 측정값으로 축약하고 lineage 보존
    - 동일 measurement에 서로 다른 값 또는 StatusCode 충돌: 임의 집계(aggregate)를 금지하고 명시적 quarantine 또는 conflict 처리
    - `Bad`, `Uncertain`, `null` 상태값: `0`이나 `Good`으로 변환하지 않고 원본 품질 상태를 보존
    - 원본 메타데이터 보존: `source_observation_ids[]`와 함께 입력 `direction` 및 `mapping_version`을 provenance에 보존
  - **완료 기준 (파일 기반 Handoff)**:
    - `run_manifest`가 완료 상태이고, 입력 파일이 finalize되었으며, checksum 검증이 완료된 run만 처리합니다. 미완료 또는 쓰기 중인 파일은 처리하지 않습니다.
- **출력 경로 (Target 예시)**:
  - `data_preprocessed/observations/{dataset_id}/{dataset_version}/observations.jsonl`
  - `data_preprocessed/observations/{dataset_id}/{dataset_version}/observation_metadata.json`

```json
// Observation JSONL 레코드 규격 (Target 예시)
{
  "asset_id": "CNC-S01-L01-01",
  "observed_at": "2026-08-20T01:00:00Z",
  "measurements": {
    "voltage": 220.5,
    "rotation": 1502.1
  },
  "quality": {
    "voltage": {"status_code": "Good", "quality": "Good"},
    "rotation": {"status_code": "Good", "quality": "Good"}
  },
  "provenance": {
    "run_id": "run-20260820-001",
    "branch_kind": "canonical",
    "direction": "received",
    "source_observation_ids": ["obs-001", "obs-002"],
    "mapping_version": "v1.0"
  }
}
```

#### B. Failure Extraction (입력: 공인된 Training Truth Source)
- **입력**: `Authorized Training Truth Source` (`상태: Authorized Training Truth Source — Target 계약 필요`)
- **Failure Truth 계약 요구사항**:
  - `truth_source_id`, `truth_schema_version`, `truth_dataset_version`, `truth_checksum`, `asset_id`, `event_id`, `anchor_timestamp`, `failure_type`, `failure interval 또는 exclusion interval`, `Observation 연결 키`
- **Truth 분리 원칙**:
  - 정상 프로토콜 provenance에는 hidden truth나 failure truth를 절대 포함하지 않습니다.
  - Failure truth를 Observation이나 일반 Feature 입력에 임의로 병합하지 않습니다.
  - Failure Dataset은 Preprocessing의 입력이 아니며, 오직 Feature 단계에서만 결합됩니다.
  - Failure Dataset은 별도의 승인된 Training Truth Source에서만 생성합니다.
  - 확정되지 않은 truth 파일 경로는 임의로 추측하지 않습니다.
- **출력 경로 (Target 예시)**:
  - `data_preprocessed/failures/{failure_dataset_id}/{failure_dataset_version}/failure_events.jsonl`
  - `data_preprocessed/failures/{failure_dataset_id}/{failure_dataset_version}/failure_metadata.json`

---

### 4.2 2단계: Preprocessing (기존 Extraction 기능 이전 — Target)
- **입력**: `Versioned Observation Dataset` (`observations.jsonl`, `observation_metadata.json` — Failure Dataset은 Preprocessing의 입력이 아님)
- **처리**:
  - Observation Dataset 파일 프로파일링 및 데이터 구조 타입 판별 (`tabular_column_as_attribute`, `tabular_row_as_attribute`)
  - 역할 컬럼 확정 (`id_column`, `time_column`, `duplicate_policy` 등)
  - 전체 데이터 변환 가능성 검증
  - 내용 기반 해시(SHA-256) 버전 산출 (`preprocessing-plan-<hash>`)
- **출력**: `Immutable Preprocessing Plan` (`pp-{uuid}.json`, `latest.json` 포인터)

---

### 4.3 3단계: Feature (Current)
- **입력**: `Versioned Observation Dataset` (Manifest 포함) + `Versioned Failure Dataset` (Manifest 포함) + `Preprocessing Plan` + `Feature Schema` + `Label Schema`
- **처리**:
  - `FeatureInputResolver`를 통한 Versioned Dataset Manifest, payload SHA-256 및 크기 검증, unversioned 파일 검색 배제
  - Preprocessing Plan과 Observation Manifest identity 및 payload SHA-256 상호 검증
  - Preprocessing Plan의 `id_column` 필수 검증 및 Dataset 내 존재/결측치 부재 검증 (미충족 시 `501 FEATURE_ASSET_ID_RESOLUTION_NOT_IMPLEMENTED` Fail-Closed)
  - Feature Schema allowlist 및 Feature Recipe에 명시된 source field, operation, parameters 실행
  - 설비별 시계열 피처 추출 (`missing_value_policy == "ffill"` 의미 보존), 고장 이력 기반 라벨링 (`[anchor-horizon, anchor)` 양성, `[anchor, exclusion_end]` 활성 고장 제외)
  - `binary_failure_within_horizon`의 경우 최종 Label `{0, 1}` 양자 존재 검증
  - Feature Schema 선언 순서 유지 및 누수 컬럼 배제
  - NPY 및 메타데이터 원자적 발행 (실제 `asset_id` 보존)
- **출력**: `Feature Dataset Bundle` (`features.npy`, `labels.npy`, `feature_columns.json`, `row_metadata.json`, `feature_metadata.json`)

---

### 4.4 4단계: Training (Current)
- **입력**: `Feature Dataset Bundle` (5개 필수 파일) + `Training Config` (`generator-training-config.schema.json`)
- **처리**:
  - `TrainingConfigProvider`를 통한 설정 로드, 스키마 검증, 분할 비율 및 SHA-256 검증
  - Feature Bundle 파일/체크섬/차원/타입 전수 검증 및 Feature/Label Schema 스냅샷 보존
  - Feature Schema 레시피로부터 원본 센서 필드 목록(`required_columns`) 및 `minimum_history_rows` 결정론적 산출
  - `asset_time_split` 기반 설비별 시간순 분할 (설비 ID 또는 타임스탬프 결측/NaT 시 `422` fail-closed)
  - 등록 모델(`lightgbm`, `xgboost`, `random_forest`) 학습 및 지표 산출 (모델별 실패 격리)
  - 6개 파일 불변 Model Artifact 패키지 발행 및 Validator 검증 (동일 버전 재발행 시 `409` 차단)
  - `activation_policy == "activate_on_success"` 시 새 아티팩트 발행 완료 후에만 `latest.json` 포인터 원자적 갱신
- **출력**: 불변 Model Artifact 패키지 (`model-artifact-v1.0`), 활성 모델 포인터 (`latest.json`)

---

### 4.5 5단계: Runtime Prediction Pipeline (Current)
- **입력**: `Completed Observation Protocol File` (FIFO 큐 작업 수신)
- **실행 모델**: `PipelineManager` 애플리케이션 싱글톤 + 영속 FIFO `PipelineQueue` + 단일 Worker 비동기 루프 + `PredictionDeliveryWorker` 전송 워커
- **처리**:
  - `PipelineQueue`에 중복 방지 키(`normalized_source_uri + source_checksum`)로 영속 등록 및 순차 처리
  - **Stage 1 (Preprocessing)**: `PreprocessingService` 직접 호출로 데이터셋 유효성 검증 및 불변 Plan 발행 참조 기록
  - **Stage 2 (Runtime Feature)**: Failure/Label을 전혀 사용하지 않는 Label-free 수식으로 `feature_schema.json` 및 `history_requirement.json` 검증 후 2D float64 특성 행렬 원자적 발행
  - **Stage 3 (Runtime Prediction)**: 활성 Model Artifact 로드 및 모델별 raw score (`0.0~1.0` 확률 또는 decision score), `score_source`, 실제 추론 행 메타데이터 기반 `observed_at` 산출 (threshold 미적용, 이상 여부 미판정)
  - **Stage 4 (Batch Building)**: 설비별 `model_id` 키 기반 K-V 딕셔너리(`model_results: dict[str, ModelPredictionResult]`) 구조로 `PredictionResultBatchPayload` 생성 (시각 불일치/메타데이터 결측 시 `501` fail-closed)
  - **Stage 5 (Prediction Delivery)**: `GENERATOR_PREDICTION_RESULT_URL`로 `Idempotency-Key` 포함 HTTP POST 멱등 전송 (Outbox 영속화 및 전용 Worker 백오프 재시도, 시스템 재시작 시 `sending` 자동 복구)
- **출력**: 불변 `PipelineRunState` (`data_preprocessed/pipeline_runs/{run_id}.json`), 결과 배치 Outbox (`data_preprocessed/prediction_outbox/{event_id}.json`)

---

## 5. API 명칭 및 Migration 계획

### 5.1 Current API (현재 main 구현 상태) vs Target API (후속 목표 설계)

| Method | Path | Current 상태 (현재 main) | Target 의미 (후속 목표) |
|---|---|---|---|
| GET | `/health` | Generator 데몬 상태 확인 | Generator 데몬 상태 확인 |
| POST | `/internal/train` | 데몬 최초 학습 실행 (내부 Lock 제어) | 후속 migration 시 호환 shim 유지 또는 정리 검토 |
| POST | `/internal/retrain` | 데몬 새 버전 재학습 실행 (내부 Lock 제어) | 후속 migration 시 호환 shim 유지 또는 정리 검토 |
| POST | `/extraction` | Target — 미병합 | **gen_data protocol data에 지정·승인된 Mapping을 적용하여 Versioned Canonical Observation Dataset을 발행하고, 별도 Authorized Truth Source로 Failure Dataset을 발행 (관련 후속 작업: Issue #108)** |
| POST | `/preprocessing` | Current — 구현 및 정본 Generator App 등록 완료 | **Observation Dataset 분석, 역할 판정 및 불변 Preprocessing Plan 수립·발행 (신규 2단계)** |
| POST | `/feature` | Current — 구현 및 정본 Generator App 등록 완료 | **Observation Dataset, Failure Dataset, Preprocessing Plan, Feature Schema 및 Label Schema를 소비하여 Feature/Label Dataset Bundle 발행 (신규 3단계)** |
| POST | `/train` | Current — 구현 및 정본 Generator App 등록 완료 | **전체 머신러닝 모델 학습 및 Model Artifact 발행 (신규 4단계)** |
| POST | `/train/{base_model}` | Current — 구현 및 정본 Generator App 등록 완료 | **특정 머신러닝 모델 학습 및 Model Artifact 발행 (신규 4단계)** |
| GET | `/runtime-pipeline/status` | Current — 구현 및 정본 Generator App 등록 완료 | **런타임 파이프라인 큐 길이, 워커 상태 및 최근 실행 결과 조회** |
| GET | `/runtime-pipeline/runs/{run_id}` | Current — 구현 및 정본 Generator App 등록 완료 | **특정 실행 ID의 단계별 상태(StageState) 및 다중 모델 예측 결과 상세 조회** |
| GET | `/runtime-pipeline/queue` | Current — 구현 및 정본 Generator App 등록 완료 | **FIFO 작업 큐 상태 목록 조회 (queued/running/succeeded/failed)** |
| POST | `/internal/runtime-pipeline/enqueue` | Current — 구현 및 정본 Generator App 등록 완료 | **새 관측 소스 파일을 런타임 예측 FIFO 큐에 내부 등록** |
| POST | `/internal/runtime-pipeline/retry-failed/{job_id}` | Current — 구현 및 정본 Generator App 등록 완료 | **실패(failed/dead_letter) 작업 명시적 정리 및 신규 시퀀스 재등록** |
| POST | `/models/{base_model}/activate/{model_version}` | Target — 미병합 | **기존 발행된 불변 Model Artifact 패키지 수동 활성화** |

| GET | `/models/{base_model}/active` | Target — 미병합 | **현재 활성화된 Model Artifact 정보 조회** |


### 5.2 타입 및 클래스 Migration Mapping 계획

| 선행 API화 작업 대상 (Migration source) | Target (후속 목표 대상) | Migration 계획 및 비고 |
|---|---|---|
| 선행 API 설계 `POST /extraction` | `POST /preprocessing` | 엔드포인트 URL 변경 (데이터셋 분석 및 Plan 기능을 /preprocessing으로 이전) |
| `ExtractionPlan` | `PreprocessingPlan` | Pydantic 스키마 변경 |
| `ExtractionPlanResponse` | `PreprocessingPlanResponse` | 응답 스키마 변경 |
| `extraction_plan_version` | `preprocessing_plan_version` | 식별자 및 메타데이터 키 변경 |
| `ExtractionService` | `PreprocessingService` | 서비스 클래스 변경 |
| `ExtractionRepository` | `PreprocessingRepository` | 저장소 클래스 변경 |
| `ExtractionPlanner` | `PreprocessingPlanner` | LLM 계획기 클래스 변경 |
| `ExtractionProfiler` | `PreprocessingProfiler` | 프로파일러 클래스 변경 |
| (신규 구현) | `POST /extraction` | 신규 Observation/Failure 추출 엔드포인트 구현 |
| (신규 구현) | `ExtractionService` | 신규 Observation/Failure Dataset 발행 서비스 구현 |

---

## 6. 기존 Generator 코드 이식 계획

현재까지 개발된 무결성 검증 및 비즈니스 로직은 누락 없이 새 구조로 이동할 계획입니다:

1. **현재 Extraction 기능 → `app/preprocessing/`으로 이전**:
   - Dataset profiling, LLM 2단계 구조 판별 및 규칙 수립 로직
   - long-format (`tabular_row_as_attribute`) 역할 컬럼 검증
   - Plan 내용 기반 해시 버전 발행 및 원본 source SHA-256 검증
2. **현재 Feature 기능 → `app/feature/`에 유지·정리**:
   - Feature Bundle 재사용 전 원본 Sensor/Failure 파일 및 provenance 전수 재검증
   - Failure Dataset 버전 경로 고정 및 설비 ID 호환성 검증
   - 시계열 Feature 추출, horizon 라벨링, allowlist 및 선언 순서 유지
   - `split_indices` 및 `row_metadata.json` 무결성 검증
3. **현재 Training 기능 → `app/training/`에 유지·정리**:
   - 전체 및 개별 모델 학습 오케스트레이션
   - Feature Dataset Bundle 전수 체크섬 검증
   - `asset_time_split` 시간순 분할 인덱스 검증
   - 모델별 학습 실패 격리 및 불변 Model Artifact 패키지 발행
   - `activation_policy`(`latest`/`manual`), `latest.json` 원자적 갱신 및 수동 활성화 복구
4. **실행 진입점 및 설정 모듈 이전**:
   - `generator_main.py` → `app/main.py`의 `create_app()` 팩토리 기반으로 migration
   - `generator_config.py` → `settings.py` 및 `paths.py` 정본 모듈로 migration
   - 기존 파일은 migration 기간 동안 compatibility shim으로 유지하되 신규 로직 추가는 금지

---

## 7. 계약 스키마 관리 상태 및 후속 정합성 검증 계획

### 7.1 계약 스키마 상태 표

| 계약 대상 | 상태 | 설명 |
|---|---|---|
| Protocol-to-Observation Golden Vector | **Target — 미작성** | 선행조건: gen_data 입력 계약 확정 |
| `generator-observation.schema.json` | **Target — 미작성** | Extraction 구현 단계에서 작성 예정 |
| `generator-failure-event.schema.json` | **Target — 미작성** | Extraction 구현 단계에서 작성 예정 |
| `generator-extraction-result.schema.json` | **Target — 미작성** | Extraction 구현 단계에서 작성 예정 |
| `generator-preprocessing-plan.schema.json` | **Target — 이전 예정** | 기존 Extraction Plan 스키마 검토 후 migration 예정 |
| `generator-feature-series.schema.json` | **Target — 미작성** | Feature 구현 단계에서 작성 예정 |
| Feature Dataset Bundle | **Target — 검토 필요** | 기존 `dataset-bundle-manifest.schema.json` 재사용·확장 여부 검토 |

> **주의**: 본 문서 변경 범위에서는 빈 스키마 파일이나 placeholder JSON을 일체 생성하지 않습니다.

### 7.2 스키마 물리 이관 완료 후 수행할 정합성 검증 항목

별도 스키마 물리 이관 작업이 완료된 후에는 다음 검증을 순차적으로 수행합니다:
1. 실제 `contracts/schemas/` 파일 목록과 문서 내 참조 목록의 1:1 일치 여부 비교
2. 문서 내 `미작성`, `이전 예정` 상태 태그 현행화
3. 스키마 `$id` 식별자 및 내부 `$ref` 경로 유효성 검증
4. 문서 내 예시 JSON payload와 JSON Schema 간의 유효성 검증 (Draft 2020-12)
5. Pydantic API 모델과 JSON Schema 필드 간의 100% 정합성 검증
6. 기존 스키마와 신규 스키마 간의 역할 중복 여부 전수 검사

---

## 8. 후속 구현 로드맵 (단계별 계획)

```text
[구조 migration 단계]
  ├─ 공통 기반 모듈(settings.py, paths.py, errors.py, file_integrity.py, atomic_publish.py) 구성
  ├─ FastAPI Application Factory (app/main.py create_app) 및 Router Composition
  ├─ 기존 Extraction 도메인 → Preprocessing 도메인 rename 및 이전
  ├─ Feature / Training 도메인 파일 이식 및 정리
  ├─ Compatibility Shim 구성 (기존 import 경로 임시 지원)
  └─ API 테스트 회귀 검증

        ↓

[프로토콜 로그 Extraction 구현 단계]
  ├─ SensorRecord v2 protocol provenance 파서 구현 (Direction별 추가 필드 처리)
  ├─ measurement_key 기반 식별 및 Pivot
  ├─ quality/lineage 보존 및 Failure truth 소스 분리
  ├─ Versioned Observation / Failure Dataset 원자적 발행 및 SHA-256 체크섬
  └─ Protocol-to-Observation Golden Vector 계약 테스트 작성

        ↓

[파이프라인 통합·검증 단계]
  ├─ Observation Dataset → Preprocessing 파이프라인 연결
  ├─ Observation + Failure + Preprocessing Plan + Feature Schema + Label Schema → Feature 파이프라인 연결
  ├─ Feature Dataset Bundle → Training 파이프라인 연결
  ├─ Observation/Feature Series 공식 계약 스키마 확정
  └─ Architecture CI 규칙 추가 (공통 모듈 app 역참조 금지, FastAPI 비의존 등)
```
