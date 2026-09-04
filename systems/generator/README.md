# Generator Domain (개요 및 목표 아키텍처)

`systems/generator`는 센서 데이터셋 분석, 전처리 계획(Preprocessing Plan) 수립, 불변 Plan 발행 및 머신러닝 모델 학습과 Model Artifact 발행을 전담하는 도메인 시스템입니다.

---

## 1. 아키텍처 구조

### 1.1 Current 구조 (현재 구현 상태)

Generator는 `systems/generator/app/main.py`를 정본 FastAPI 애플리케이션으로 사용하며, 기존 `generator_main.py`는 호환성 shim으로 동작합니다.

```text
systems/generator/
├─ app/                       # FastAPI Application 및 도메인 계층
│  ├─ main.py                 # 정본 FastAPI Application Factory (create_app)
│  ├─ extraction/             # [1단계 Current] gen_data Protocol Extraction 및 Canonical Observation 발행
│  │  ├─ extraction_schema.py
│  │  ├─ extraction_service.py
│  │  ├─ extraction_repository.py
│  │  ├─ mapping_validator.py
│  │  ├─ mapping_repository.py
│  │  ├─ dedup_repository.py
│  │  ├─ checkpoint_repository.py
│  │  ├─ extraction_exception.py
│  │  ├─ extraction_router.py
│  │  └─ parsers/
│  │     └─ sensor_record_parser.py
│  ├─ preprocessing/          # [2단계 Current] Observation Dataset 분석 및 Preprocessing Plan 수립·발행
│  │  ├─ preprocessing_schema.py
│  │  ├─ preprocessing_service.py
│  │  ├─ preprocessing_repository.py
│  │  ├─ preprocessing_planner.py
│  │  ├─ preprocessing_profiler.py
│  │  ├─ preprocessing_exception.py
│  │  └─ preprocessing_router.py
│  ├─ feature/                # [3단계 Current] Preprocessing Plan 및 Schema 기반 Feature Dataset Bundle 발행
│  │  ├─ feature_schema.py
│  │  ├─ feature_service.py
│  │  ├─ feature_repository.py
│  │  ├─ feature_schema_provider.py
│  │  ├─ label_schema_provider.py
│  │  ├─ feature_exception.py
│  │  └─ feature_router.py
│  ├─ training/               # [4단계 Current] Feature Bundle 기반 Multi-Model 학습 및 Model Artifact 발행
│  │  ├─ training_schema.py
│  │  ├─ training_service.py
│  │  ├─ data_splitter.py
│  │  ├─ training_exception.py
│  │  └─ training_router.py
│  ├─ runtime_pipeline/       # [5단계 Current] 런타임 자동 예측·이상 신호 파이프라인
│  │  ├─ pipeline_schema.py
│  │  ├─ pipeline_exception.py
│  │  ├─ pipeline_queue.py
│  │  ├─ pipeline_state.py
│  │  ├─ pipeline_repository.py
│  │  ├─ runtime_feature_service.py
│  │  ├─ prediction_service.py
│  │  ├─ aggregation_service.py
│  │  ├─ notification_service.py
│  │  ├─ pipeline_service.py
│  │  ├─ pipeline_worker.py
│  │  ├─ pipeline_manager.py
│  │  └─ pipeline_router.py
│  └─ training_compat/        # [호환성] legacy /internal/train, /internal/retrain 및 lifecycle
│     ├─ training_compat_router.py
│     └─ training_lifecycle.py
│
├─ generator_main.py          # [호환성 Shim] app.main:app 재노출
├─ generator_config.py        # 전역 경로 및 설정 싱글톤
├─ file_integrity.py          # SHA-256 무결성 검증 유틸리티
├─ feature/                   # Feature 계산 모듈 (수학/시계열 변환 기반)
├─ model/                     # 모델 알고리즘 구현 (LightGBM, XGBoost, RandomForest), Registry 및 Publisher
├─ ontology_mapping/          # legacy/보조 semantic mapping 모듈; 신규 Feature API 실행 계약이 아님
├─ topology/                  # 설비 간 위상 관계 추론
├─ common/                    # 공통 에이전트 및 타임스탬프 정규화 유틸리티
├─ entrypoint.py
├─ Dockerfile
└─ requirements.txt
```

> **단방향 의존성 원칙**: 공통 기반 모듈(`systems/generator/*.py`)은 `app` 하위 모듈을 절대 import하지 않으며, `FastAPI`에 의존하지 않습니다.
>
> **Python 실행 환경 계약 (Execution Environment Contract)**:
> - Generator 시스템은 저장소 루트(Repository Root)를 표준 `PYTHONPATH`로 사용하는 패키지 구조를 가집니다.
> - 저장소 루트 실행: `python -c "import systems.generator.app.extraction; import systems.generator.app.preprocessing; import systems.generator.app.feature; import systems.generator.app.training; import systems.generator.app.runtime_pipeline"`
> - `systems/generator` 작업 디렉터리 실행: `PYTHONPATH=<repository-root>` 환경변수를 제공하여 legacy facade 및 모듈을 실행합니다.

---

## 2. 도메인 API 현황 및 파이프라인

### 2.1 Current API (현재 구현 상태)

현재 Generator 정본 애플리케이션(`systems/generator/app/main.py`)에 실제로 구현되어 동작하는 엔드포인트입니다.

| Method | Path | 현재 의미 | 상태 |
|---|---|---|---|
| GET | `/health` | Generator 데몬 상태 및 시스템 식별자 확인 | Current (구현 완료) |
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
| POST | `/internal/runtime-pipeline/enqueue` | 새 관측 소스 파일을 런타임 예측 FIFO 큐에 내부 등록 | Current — 구현 및 정본 Generator App 등록 완료 |
| POST | `/internal/runtime-pipeline/retry-failed/{job_id}` | 실패(failed/dead_letter) 작업 명시적 정리 및 신규 시퀀스 재등록 | Current — 구현 및 정본 Generator App 등록 완료 |
| POST | `/internal/train` | 데몬 최초 학습 실행 (단일 프로세스 Lock 제어) | Current (호환성 유지) |

| POST | `/internal/retrain` | 데몬 새 버전 재학습 실행 (단일 프로세스 Lock 제어) | Current (호환성 유지) |

`POST /internal/runtime-pipeline/enqueue`는 `source_kind`, source contract/schema version,
pipeline contract version, Dataset 식별자와 lineage를 입력 시점에 확정한다. 이 문맥은
Queue, retry, RunState, Checkpoint와 외부 Prediction Result Batch까지 변경 없이 보존된다.
과거 Queue 행에 이 문맥이 없으면 임의로 `live_sensor`로 보정하지 않고
`PIPELINE_SOURCE_CONTEXT_MIGRATION_REQUIRED` dead-letter로 격리한다. 외부 Batch를
발행하는 실행 환경은 provenance용 `GENERATOR_RUNTIME_VERSION`도 반드시 설정해야 한다.


### 2.2 Target API (후속 목표 및 고도화 설계)

향후 모델 수동 관리 및 고도화를 위해 고려 중인 Target API 목록입니다.

| Method | Path | Target 의미 및 고도화 단계 | 상태 |
|---|---|---|---|
| POST | `/models/{base_model}/activate/{model_version}` | 기존 발행된 불변 Model Artifact 패키지 수동 활성화 | Target (후속 고도화) |
| GET | `/models/{base_model}/active` | 현재 활성화된 Model Artifact 정보 조회 | Target (후속 고도화) |

### 2.3 파이프라인 흐름

Generator의 4대 파이프라인 단계별 책임과 데이터 흐름입니다.

```text
1. Extraction
   ├─ 지정 Mapping 기반 Protocol Parsing
   ├─ Canonical Observation Dataset 발행
   └─ Authorized Truth Source 기반 Failure Dataset 발행

2. Preprocessing
   ├─ Observation Dataset 구조 분석
   ├─ ID/time/attribute/value 역할 판정
   └─ Immutable Preprocessing Plan 발행

3. Feature
   ├─ Feature Schema allowlist/recipe 적용 (Ontology Mapping 미소비)
   ├─ Label Schema 적용
   └─ Immutable Feature Dataset Bundle 발행

4. Training
   ├─ Feature Dataset Bundle 무결성 검증 (Feature 재계산 없음)
   ├─ asset_time_split (설비·시간 기준 분할)
   ├─ 모델별 학습 및 평가
   └─ Immutable Model Artifact 발행 & latest.json 포인터 갱신
```

---

## 3. Preprocessing Plan 불변 저장 구조 및 provenance 계약

- **지원 구조 유형 (Structure Types)**: 공식 지원 범위는 `tabular_column_as_attribute`, `tabular_row_as_attribute` 2종류로 한정되며, `wide_pivot` 및 미지원 형식은 임의 fallback 없이 422 오류로 처리됩니다.
- **Plan 식별**: `preprocessing_plan_id` (`pp-{UUID4}`)와 `preprocessing_plan_version` (`preprocessing-plan-{hash}`) 분리.
- **Dataset 결합 및 Provenance**: Plan은 `source_dataset_uri`, `source_dataset_sha256`, `source_schema_fingerprint`, `decision_source`, `fallback_reason`, `planner_version`과 결합되며, `preprocessing_plan_version`은 이를 포함한 canonical 해시로 산출.
- **논리 URI Fail-Closed**: `source_dataset_uri`, `preprocessing_plan_uri`는 허용된 저장소 루트(`data_dir`, `models_store`, workspace) 기반의 논리 상대경로만 저장되며, 허용 루트 밖 경로는 Fail-Closed로 거부되고 API 응답에 전체 절대경로가 노출되지 않습니다.
- **저장 디렉터리**: `models_store/cache/preprocessing_plans/{dataset_id}/{dataset_version}/`
- **불변 파일 및 포인터**: `pp-{uuid}.json` (고유 불변 파일 atomic rename 발행) 및 `latest.json` (별도 atomic replace 갱신).
- **재사용 및 Fail-Fast 검증**: `force_reanalyze=False` 시 dataset sha256, schema fingerprint 및 중복 정책 불일치 시 `409 PREPROCESSING_PLAN_CONFLICT` 반환. `selected_columns` 또는 역할 컬럼 누락 시 422 fail-fast.
- **동기 실행**: `/preprocessing` 라우터는 동기 함수로 구성되어 FastAPI threadpool에서 안전하게 실행됩니다.

---

## 4. Feature Dataset Bundle 불변 저장 구조 및 Versioned Dataset 입력 계약

- **Versioned Dataset 입력 경로 및 Manifest 계약**:
  - Observation: `data/observations/{dataset_id}/{dataset_version}/` (`dataset_manifest.json`, `observations.csv` 또는 `.jsonl`)
  - Failure: `data/failures/{dataset_id}/{dataset_version}/` (`dataset_manifest.json`, `failures.csv` 또는 `.jsonl`)
  - `contracts/schemas/generator-dataset-input-manifest.schema.json`에 정의된 Manifest 필수 필드, 단일 role(`observations`, `failures`), payload 상대경로 안전성, 실제 파일 SHA-256 및 크기(size_bytes) 일치 여부를 `FeatureInputResolver`가 철저히 검증.
  - unversioned 파일(`data/{dataset_id}.csv` 등)의 암묵적 검색 fallback을 완전히 제거하여 버전 위조를 원천 차단.
- **Preprocessing Plan과 Observation Manifest 상호 검증**:
  - `request.dataset_id == Plan.dataset_id == Observation Manifest.dataset_id`
  - `request.dataset_version == Plan.dataset_version == Observation Manifest.dataset_version`
  - `Plan.source_dataset_sha256 == Observation payload SHA-256`
  - 불일치 시 `422 FEATURE_CONTRACT_ERROR`로 fail-closed.
- **Bundle 식별**: `feature_dataset_version` (`feature-dataset-{hash16}`)은 Observation/Failure Dataset Manifest 및 Payload SHA-256, `failure_source_mode`, Preprocessing Plan(ID/ver/sha), Feature Schema, Label Schema, prediction horizon의 canonical fingerprint로 결정론적 산출.
- **저장 디렉터리**: `models_store/cache/features/{dataset_id}/{dataset_version}/{feature_dataset_version}/`
- **Failure Source 모드 계약**:
  - `external_dataset` (기본값): Failure 데이터셋이 필수이며 파일 미발견 시 404 Fail-Fast (Observation 대체 fallback 없음).
  - `embedded_observation`: Observation 내부 indicator 컬럼(`Machine failure` 등)을 직접 소비.
- **Feature `ffill` 의미 보존**:
  - `missing_value_policy="ffill"` 적용 시 원본 source 컬럼으로 되돌아가지 않고, 이미 계산된 lag/diff/rolling/ewm series 자체를 설비 단위(`asset_id`)로 forward-fill.
- **`binary_failure_within_horizon` Feature Dataset 발행 조건 (Fail-Closed)**:
  1. **Canonical Observation timestamp 필수**: 누락 또는 NaT 포함 시 `422 FEATURE_LABEL_ALIGNMENT_ERROR`로 거부.
  2. **유효한 failure event 최소 1건 필수**: 외부 Failure Dataset 0행 시 `422 INSUFFICIENT_TRAINING_DATA`로 거부.
  3. **Active failure filtering 후 event 최소 1건 필수**: indicator 필터링 후 0건 시 `422 INSUFFICIENT_TRAINING_DATA`로 거부.
  4. **내장 failure event timestamp 오류 거부**: embedded indicator 행의 timestamp NaT 시 건너뛰지 않고 `422 FEATURE_LABEL_ALIGNMENT_ERROR`로 거부.
  5. **최종 Label 클래스 `{0, 1}` 양자 공존 필수**: 최종 생존 라벨에 0과 1이 모두 존재해야 하며, 단일 클래스 시 `422 INSUFFICIENT_TRAINING_DATA`로 거부.
  6. **설비 Identity & 제외 구간 엄격성**: 다중 설비에서 failure asset 누락/미소속 시 `422`, `anchor`/`exclusion_end` 누락, NaT, 또는 `exclusion_end < anchor` 위반 시 `422` 반환 및 `[anchor, exclusion_end]` 전체 구간 학습 데이터 제외.
- **Asset identity requirement (Fail-Closed 501)**:
  - `POST /feature`가 소비하는 Observation Dataset에는 Preprocessing Plan의 `id_column`으로 선언된 설비 식별 컬럼이 반드시 존재해야 한다.
  - 현재 파이프라인은 ID가 없는 Dataset을 자동으로 단일 설비로 간주하거나 임시 ID(`row_{idx}`, `default_asset`)를 생성하지 않는다.
  - Plan에 `id_column` 누락, Dataset 내 컬럼 미존재, 또는 null/empty ID 값 포함 시 `501 FEATURE_ASSET_ID_RESOLUTION_NOT_IMPLEMENTED`로 실패하며 Feature Dataset Bundle을 발행하지 않는다.
  - ID가 없는 단일 설비 Dataset 지원은 후속 기능으로 별도 구현한다.
- **허용되지 않는 Fallback (Prohibited Fallbacks)**:
  - `row_{idx}`, `default_asset` 등 임시 asset ID 생성 금지
  - Preprocessing Plan의 `id_column` 누락 시 임의 컬럼 휴리스틱 선택 금지
  - timestamp 위치 기반 추측 금지
  - invalid timestamp 행 조용한 건너뛰기(silent skip) 금지
  - 빈 Failure Dataset을 정상 Dataset으로 처리 금지
  - all-zero Label Bundle 발행 금지
  - 단일 클래스 Label을 Training 단계로 전달 금지
  - unversioned 파일 검색 fallback 금지
- **5개 필수 파일 구성**:
  1. `features.npy`: 2D float64 배열, `allow_pickle=False`, NaN/Inf 불가
  2. `labels.npy`: 1D int64 배열 `{0, 1}`, `allow_pickle=False`
  3. `feature_columns.json`: Feature Schema 선언 순서의 컬럼 목록 및 수량
  4. `row_metadata.json`: Feature/Label 행과 1:1 대응되는 실제 설비 식별자(`asset_id`) 및 timestamp
  5. `feature_metadata.json`: 데이터셋 Manifest/payload provenance, 스키마 provenance, 클래스 분포, 4개 payload 파일의 개별 SHA-256 체크섬 (자기참조 순환 방지)
- **원자적 발행 및 불변성 정책**:
  - 임시 디렉터리(`.tmp_{uuid}`)에서 전체 생성 및 검증 완료 후 atomic rename/replace.
  - 동일 fingerprint 시 기존 유효 Bundle 즉시 재사용. Fingerprint 불일치 시 `409 FeaturePublishConflictError`, 파일 손상 시 `422 FeatureDatasetIntegrityError` 반환.
- **동기 실행**: `/feature` 엔드포인트는 동기 함수로 구성되어 FastAPI threadpool에서 안전하게 실행됩니다.

---

## 5. Training 도메인 및 불변 Model Artifact 패키지 발행

- **엔드포인트**: `POST /train` (전체 등록 모델: `lightgbm`, `xgboost`, `random_forest`) 및 `POST /train/{base_model}` (지정 모델).
- **입력 소비**: 5개 파일이 완비된 불변 **Feature Dataset Bundle**만 소비하며, 원본 센서 데이터를 직접 파싱하거나 Feature/Label을 재계산하지 않습니다.
- **Training Config 및 Hyperparameter 해결 계약**:
  - `training_config_version`은 `contracts/schemas/generator-training-config.schema.json`에 정의된 버전 관리 설정 파일과 1:1로 바인딩됩니다.
  - 설정 파일 부재 시 `404`, 스키마 위반 또는 분할 비율 오류 시 `422`로 Fail-Closed 처리되며, 설정 파일의 SHA-256 및 논리 URI가 Model Artifact provenance에 기록됩니다.
  - 최상위 `random_seed`가 학습 시드의 유일한 단일 정본으로 사용되며, 모델별 `hyperparameters` 내부의 `random_state`, `seed`, `random_seed` 중복 선언은 정적 검증 및 런타임에서 `422 TRAINING_CONTRACT_ERROR`로 Fail-Closed 차단됩니다.
  - Trainer의 `resolve_parameters(configured, random_seed)`를 통해 기본값보다 설정값을 우선 적용한 `resolved_parameters`가 실제 Estimator `get_params()` 및 Manifest `training_config`에 온전히 기록됩니다.
- **Prediction Horizon 의미 계약 및 Schema 교차 검증**:
  - Feature Bundle provenance의 `prediction_horizon_hours`는 양의 정수(`int > 0`, `bool`/`float`/`str` 불가)여야 합니다.
  - Model Artifact staging 및 발행 전 Label Schema 스냅샷의 `prediction_horizon_hours`와 일치하는지 교차 검증하며, 불일치 시 `422 TRAINING_CONTRACT_ERROR`로 즉시 Fail-Closed 처리되어 불완전한 아티팩트 생성을 방지합니다.
- **Feature/Label Schema 스냅샷 보존 및 History Requirement 산출**:
  - 축약되거나 임의 기본값으로 대체되지 않은 완전한 Feature Schema 및 Label Schema 스냅샷을 검증하여 아티팩트에 보존합니다.
  - `history_requirement.json`은 Feature Schema 레시피로부터 파생 Feature명이 아닌 **원본 센서 필드 목록(`required_columns`)** 및 연산 파라미터(lag/rolling/ewm)를 반영하여 `minimum_history_rows`를 결정론적으로 산출합니다.
- **Fail-Closed 데이터 분할 (`asset_time_split`)**:
  - `row_metadata.json`의 모든 행에 `asset_id`와 유효한 `timestamp`가 필수이며, 결측 또는 NaT 발생 시 `422 TrainingDatasetError`를 반환합니다 (`default_asset` 또는 행 번호 대체 금지).
  - 시간 분할 후 train partition에 단일 클래스만 남을 경우 즉시 `422 TrainingDatasetError`로 Fail-Closed 처리됩니다.
  - Training Config에 정의된 분할 비율(예: 70/15/15) 및 `random_seed`를 엄격히 적용합니다.
- **저장 디렉터리**: `models_store/artifacts/{model_id}/{model_version}/`
- **6개 필수 파일 구성**:
  1. `manifest.json`: 5개 payload 파일의 상대 경로 및 SHA-256 체크섬, provenance, compatibility, training_config (자기참조 순환 제외, role 및 path 중복 검증 필수)
  2. `model.joblib`: 학습된 직렬화 모델 바이너리 (`joblib.dump(compress=3)`)
  3. `feature_schema.json`: 학습에 실제 사용된 Feature Schema 확정본
  4. `label_schema.json`: 학습에 실제 사용된 Label Schema 확정본
  5. `history_requirement.json`: Feature Schema 기준 결정론적 산출 (`minimum_history_rows`, `required_columns`, `missing_history_policy`)
  6. `metrics.json`: 계산된 validation 지표, 클래스 분포, primary metric
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
- **동기 실행**: `/train` 및 `/train/{base_model}` 엔드포인트는 동기 함수로 구성되어 FastAPI threadpool에서 안전하게 실행됩니다.

---

## 6. 전체 확정 파이프라인 흐름 및 런타임 연계 (End-to-End Pipeline)

Generator는 `gen_data` 센서 로그에서부터 Backend Inbox까지의 7단계 연속 흐름을 지원합니다.

```text
gen_data (sensor_stream.jsonl append)
  │
  ▼
[Stage 1: Incremental Extraction] (ExtractionWorker & Manager)
  │  - 정적 승인 Mapping (`gen-data-sensor-stream-canonical` v1) 적용
  │  - 단일 작성자 Lock 및 체크포인트 영속화
  ▼
[Stage 2: Canonical Observation Dataset] (dataset_manifest.json + observations.jsonl)
  │  - 불변 Window Dataset 발행
  │  - ExtractionRuntimeHandoffService를 통한 멱등 Handoff 생성
  ▼
[Stage 3: Runtime Handoff & FIFO Queue] (PipelineQueue SQLite)
  │  - RuntimeInputIdentity 생성 및 큐 등록
  │  - 15대 핵심 식별자 및 RuntimeSourceContext 보존
  ▼
[Stage 4: Runtime Feature & Prediction] (PipelineWorker & PredictionService)
  │  - 모델 Feature Schema 기반 변환 및 이력 요건(`minimum_history_rows`) 검증
  │  - LightGBM / XGBoost 등 모델 추론 및 raw score 산출
  ▼
[Stage 5: Prediction Result Batch] (PredictionDeliveryService Outbox)
  │  - 공식 `prediction-result-batch-v1` 스키마 직렬화 및 SHA-256 페이로드 서명
  ▼
[Stage 6: HTTP Dispatch] (PredictionDeliveryWorker)
  │  - POST /internal/prediction-results 비동기 전송 및 지수 백오프 재시도
  ▼
[Stage 7: Backend Prediction Inbox] (PredictiveMaintenanceRuntimeService)
     - 수신, 권한/Scope 검증, 중복 수신 시 `duplicate` 멱등 처리
```

### 6.1 파이프라인 검증 범위 및 Model Artifact 정책

- **현재 검증된 범위 (In-Process Integration)**:
  - `gen_data` Extraction $\rightarrow$ Runtime Handoff $\rightarrow$ Runtime Prediction $\rightarrow$ Prediction Result Batch $\rightarrow$ Backend Router/Service 경계까지의 계약 및 멱등 처리 in-process 통합 검증이 완료되었습니다.
  - E2E 검증(`tests/test_generator_extraction_e2e.py`)은 테스트 실행 중 생성되는 임시 Model Artifact를 사용합니다.
- **후속 배포/운영 분리 범위**:
  - 실제 배포 환경은 사전에 검증된 Model Artifact와 Active Model Set(`latest.json`)을 별도로 주입해야 합니다.
  - 실제 SQLite/PostgreSQL Inbox persistence, Generator·Backend 다중 컨테이너 Docker Compose HTTP 통신, 실제 배포 환경 인증·네트워크 검증은 별도 후속 배포 작업으로 분리하여 관리합니다.

---

## 7. 시스템 간 책임 경계 (Responsibility Boundaries)

각 도메인 시스템은 아래의 명확한 단일 책임을 유지하며, 상호 영역을 침범하지 않습니다.

### 1. gen_data
- 프로토콜 로그 생성 (PLC / CNC / Compressor 센서 스트림)
- `sensor_stream.jsonl` 원본 파일 append 유지
- 원본 로그 파일의 영구 소유권 보유

### 2. Generator Extraction
- 원본 로그 탐색 및 증분 파싱 (`SensorRecordParser`)
- 승인된 정적 매핑(`generator-static-mapping-table`) 적용
- 불변 `Canonical Observation Dataset` 발행 및 체크포인트 관리
- `Runtime Handoff` 레코드 생성 및 Pipeline Queue 연동

### 3. Generator Runtime
- `RuntimeSourceContext` 보존 및 FIFO 큐 실행
- Runtime Feature 계산 및 이력 조건 fail-closed 검증
- Model Artifact 로드 및 다중 머신러닝 모델 inference
- raw score 및 `Prediction Result Batch` (`prediction-result-batch-v1`) 생성
- Backend Inbox로의 Outbox 영속화 및 HTTP 전송

### 4. Backend
- Prediction Result Batch 수신 및 인증/Scope 검증
- Backend Prediction Inbox 멱등 저장
- Threshold 정책 및 의사결정(decision policy) 적용
- Product Result Artifact 및 Evidence 후속 승격 전담

---

## 8. Mapping 정책 및 미구현 범위 분리 (Mapping Policy & Unimplemented Scope)

### 8.1 Extraction 고정 Mapping Operations 계약
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
  - 검증 및 추출 실패 시 기존 Checkpoint, Fragment 및 Dataset 파일은 일절 수정되거나 삭제되지 않고 100% 보존됩니다.

### 8.2 기능 지원 현황 (Current vs Target)

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

### 8.3 기타 미구현 범위
- **LLM Mapping 자동 생성**: 현재는 승인된 정적 매핑 테이블(`generator-static-mapping-table`)만 지원합니다.
- **비표준 Protocol 자동 추론**: 정의되지 않은 프로토콜 형식의 자동 감지는 지원하지 않으며 Fail-Closed 처리됩니다.
- **결측치 자동 보정 (Imputation)**: 임의 결측치 대체 없이 `ffill` 및 엄격한 null 검증 정책을 유지합니다.
- **사용자 Model Version 선택**: 런타임은 활성 Model Set 포인터(`latest.json`)를 단일 정본으로 소비합니다.
- **Product Result / Evidence 신규 생성**: Generator는 raw score가 포함된 `Prediction Result Batch`만 발행하며, 최종 제품 리포트/Evidence는 Backend가 전담합니다.
- **Dashboard 알림 UI**: 실시간 이상 알림 UI 구성은 프론트엔드/대시보드 도메인에서 처리합니다.
- **Closed-loop 재지시 (PLC 제어)**: 설비 제어기 직접 피드백 루프는 본 파이프라인의 범위가 아닙니다.

### 8.4 Legacy와 gen_data 중복 방지 계약 구분 (Dedup Architecture Distinction)
- **Legacy ExtractionService**:
  - `DedupRepository` 기반 영속 record dedup
  - Target Dataset lease 및 갱신 방식
- **GenDataExtractionRequest 운영 경로**:
  - Logical Source Scope 배타적 OS 파일 Lock (`GenDataSourceLock` with `source_lock_identity`)
  - Source byte-offset 기반 증분 Checkpoint (`GenDataExtractionCheckpoint`)
  - Source identity + offset 범위 + Mapping identity 기반 결정적 `batch_id`
  - Polling cycle 간 Cross-run Fragment 멱등 재사용 (`find_fragment_by_batch_id`)
  - Fragment consumption record 기반 수명주기 및 Fully-consumed 추적
  - 불변 `Canonical Observation Dataset` 발행 및 SHA-256 conflict fail-closed 검증


---

## 9. 산출물 수명주기 및 보존 정책 (Artifact Lifecycle)

파이프라인 운영 중 생성되는 각 산출물의 수명주기 및 관리 원칙은 다음과 같습니다.

1. **`gen_data` 원본 파일**:
   - Generator가 절대 삭제하거나 수정하지 않음 (Producer 소유권 보존).
2. **`Extraction Fragment` (중간 청크)**:
   - Window Dataset 발행 및 검증이 완료된 후 안전하게 자동 정리.
3. **`Canonical Observation Dataset`**:
   - 재현성과 학습 재구성을 위해 불변 Artifact(`dataset_manifest.json` + `observations.jsonl`)로 영구 보존.
4. **`Runtime Handoff` 레코드**:
   - 감사(Audit), 추적성 및 장애 재시도를 위해 영구 유지.
5. **`Runtime Checkpoint`**:
   - 파이프라인 작업 정상 완료 및 설정된 보존 기간에 따라 주기적 정리.
6. **`Prediction Outbox`**:
   - Backend 전달 완료(`delivered`) 후 보존 정책에 따라 보관 및 정리.
7. **`Dead-letter` (실패 격리 레코드)**:
   - 운영자의 원인 분석 및 수동 확인 전까지 자동 삭제 금지.

---

## 10. Docker 실행 가이드

### 1. Docker 이미지 빌드
```bash
docker build --file systems/generator/Dockerfile --tag ontology-generator:latest .
```

### 2. 컨테이너 실행
```bash
docker run --rm -d \
  --name ontology-generator \
  -p 8000:8000 \
  -v "$(pwd)/data:/data/source" \
  -v "$(pwd)/data_preprocessed:/data/preprocessed" \
  -v "$(pwd)/models_store:/data/models" \
  -v "$(pwd)/artifacts:/artifacts" \
  --env-file systems/generator/.env \
  ontology-generator:latest
```

### 3. 상태 확인
```bash
curl http://localhost:8000/health
curl http://localhost:8000/extraction/status
curl http://localhost:8000/runtime-pipeline/status
```
