# Shared Contracts

이 디렉터리는 Generator, Backend, Frontend 등 둘 이상의 시스템이 공유하는
기계 판독 계약을 관리하기 위한 저장소 최상위 위치다.

현재 공유 JSON Schema는 `contracts/schemas/`로 물리 이동이 완료되었으며,
관련 코드·스크립트·테스트·CI·Docker·문서 참조가 모두 이 디렉터리를 정본으로 바라보도록 설정되어 있다.

## Directory layout

### `schemas/`
여러 시스템이 공유하는 JSON Schema를 보관한다.
기존 최상위 `schemas/` 위치의 공유 JSON Schema는 `contracts/schemas/`로 물리 이전을 완료하였다.

### `openapi/`
시스템 경계를 통과하는 공유 API 계약을 보관한다.
Generator 내부 API나 Backend 공개 API가 실제 OpenAPI 계약으로 확정된 경우에만
파일을 추가한다. 미결정 API를 placeholder 계약으로 만들지 않는다.

### `examples/`
공유 Schema 또는 API 계약을 만족하는 대표 payload 예시를 보관한다.
예시는 반드시 해당 계약의 검증을 통과해야 하며, `"..."` 같은 실행 불가능한
placeholder 값을 사용하지 않는다.

### `test-vectors/`
Producer와 Consumer 사이의 계약 호환성을 검증하는 고정 입력과 기대 결과를 보관한다.
Schema validation, Publisher/Loader round-trip, Feature parity, Label boundary 등
실제 자동 검증에서 사용하는 자료만 추가한다.

## Current status

현재 `contracts/`의 관리 상태는 다음과 같다.

- `contracts/schemas/`: 기존 Schema의 물리 이동과 이후 추가된 공유 JSON Schema 관리 (Training Config 및 Runtime Overlay 스키마 포함)
- `contracts/examples/`: `generator-feature-input/`, `generator-training/`에 실제 검증 가능한 요청/설정 예제 관리
- `contracts/test-vectors/`: `generator-feature-input-v1/` 및 `generator-training-v1/`에 Feature 및 Training Golden Vector 관리
- `project_root()` 마커, `Dockerfile`, `render.yaml`, CI(`architecture.yml`), `scripts/`, `tests/` 참조 전환 완료
- Schema 내용 및 `$id` 식별자 무변경 보존

## Generator 파이프라인 계약 현황 및 후속 Target 계약 후보

Generator 구조 개편 및 파일 가공 파이프라인(Observation/Feature Series 생산자 확립 및 SensorRecord v2 프로토콜 정규화 작업)을 위한 계약 목록과 상태는 다음과 같습니다.

### 계약 상태 표

| 계약 | 현재 상태 | 설명 |
|---|---|---|
| Generator Protocol Record Schema | **Current** | `contracts/schemas/generator-protocol-record.schema.json` (SensorRecord v2 계약 정본) |
| Generator Static Mapping Table Schema | **Current** | `contracts/schemas/generator-static-mapping-table.schema.json` (승인된 정적 매핑 계약 정본) |
| Generator Extraction Runtime Handoff Schema | **Current** | `contracts/schemas/generator-extraction-runtime-handoff.schema.json` (Extraction -> Runtime Prediction 전달 및 큐 연동 계약 정본) |
| Generator Protocol Extraction Golden Vector | **Current** | `contracts/test-vectors/generator-protocol-extraction-v1/` (SensorRecord v2 -> Canonical Observation 변환 및 무결성 검증) |
| Generator Dataset Input Manifest | **Current** | `contracts/schemas/generator-dataset-input-manifest.schema.json` (자동 검증 및 예제/테스트 벡터 존재) |
| Generator Feature Input Golden Vector | **Current** | `contracts/test-vectors/generator-feature-input-v1/` (Multi-asset 라벨링 및 활성 고장 제외 자동 검증) |
| Generator Training Config Schema | **Current** | `contracts/schemas/generator-training-config.schema.json` (설정 버전, 파라미터, 분할 비율 검증) |
| Generator Training Golden Vector | **Current** | `contracts/test-vectors/generator-training-v1/` (데이터 분할 결정성 및 불변 Model Artifact 검증) |
| Model Artifact Schema | **Current** | `contracts/schemas/model-artifact.schema.json` (6개 파일 불변 아티팩트 및 manifest 무결성 정본) |
| Runtime Overlay Observation / Available | **Current** | `contracts/schemas/runtime-overlay-observation.schema.json`, `runtime-overlay-observations-available.schema.json`, `contracts/test-vectors/runtime-overlay-output-v1/` (정비 후 CNC Overlay, digest 경로 identity, Unicode canonical checksum) |
| Generator Runtime Pipeline Run State Schema | **Current** | `contracts/schemas/generator-pipeline-run-state.schema.json` (런타임 5대 Stage 상태, 정본 RuntimeSourceContext, Resumable Checkpoint 및 Model Set digest 불변식 정합화) |
| Generator Runtime Feature Schema | **Current** | `contracts/schemas/generator-runtime-feature.schema.json` (런타임 피처 행렬 및 설비·시간 metadata) |
| Generator Model Prediction Result Schema | **Current** | `contracts/schemas/generator-model-prediction-result.schema.json` (모델별 score 수치, score_type, 실행 상태 및 오류 정보) |
| Prediction Result Batch Schema | **Current** | `contracts/schemas/prediction-result-batch.schema.json` (`prediction-result-batch-v1` 외부 Backend Inbox 전달 정본 배열 계약) |
| Internal Generator Runtime Prediction Stage Schema | **Internal** | `contracts/schemas/generator-runtime-prediction-stage.schema.json` (Generator 내부 staging 및 checkpoint 재개 전용 계약) |
| Generator Runtime Prediction Golden Vector | **Current** | `contracts/test-vectors/generator-runtime-prediction-v1/` (다중 설비 런타임 예측 수치 및 결과 묶음 배치 검증) |
| Generator Pipeline E2E Golden Vector | **Current** | `contracts/test-vectors/generator-pipeline-e2e-v1/` (Protocol -> Extraction -> Dataset -> Handoff -> Runtime Prediction -> Batch 전체 파이프라인 무결성 및 13개 결정적 식별자 불변성 검증) |


### Prediction 관련 내부/외부 계약 경계 원칙

1. **외부 wire 정본**: `contracts/schemas/prediction-result-batch.schema.json` (`prediction-result-batch-v1`) 하나뿐이며, Generator에서 Backend Prediction Inbox로 전송되는 유일한 외부 계약이다.
2. **내부 저장 계약**: `contracts/schemas/generator-runtime-prediction-stage.schema.json`은 Generator 내부 staging 및 checkpoint 재개를 위한 전용 저장 계약이며 Backend로 절대 전송되지 않는다.
3. **공식 변환 경계**: 내부 Stage(`InternalPredictionResultBatchStage`)를 외부 Batch(`PredictionResultBatchPayload`)로 변환하는 공식 경계는 `to_external_result_item()`과 `PredictionResultBatchPayload`이다.


### Target 계약 관리 원칙

- **본 문서 변경 범위**: 빈 파일이나 placeholder Schema를 일체 생성하지 않으며, 실제 스키마 생성은 별도 계약·구현 작업에서 수행합니다.
- **기존 계약 재사용 우선**: 기존 계약으로 표현 가능한 경우 새 스키마를 중복 생성하지 않습니다.
- **Feature Dataset Bundle 재사용 검토**: Feature Dataset Bundle의 경우 신규 스키마를 추가하기 전에 기존 `dataset-bundle-manifest.schema.json`의 재사용 및 확장 가능성을 먼저 검토합니다.

### 스키마 물리 이관 완료 후 수행할 정합성 검증 항목

별도 스키마 물리 이관 작업이 완료된 후에는 다음 검증을 순차적으로 수행합니다:
1. 실제 `contracts/schemas/` 목록과 문서 목록 1:1 비교
2. 문서 내 `미작성`, `이전 예정` 상태 태그 갱신
3. `$id`와 `$ref` 검증
4. 스키마 경로 참조 검증
5. 예시 JSON과 JSON Schema 정합성 검증 (Draft 2020-12)
6. API 모델과 Schema 필드 정합성 검증
7. 기존 스키마와 신규 스키마의 역할 중복 검사

## Verification & CI

계약 자산의 무결성을 검증하기 위해 두 단계의 검증 체계를 운영합니다.

### 1. 경량 정적 계약 검증 (`systems/verify_contract_vectors.py`)
- **실행 명령**: `python systems/verify_contract_vectors.py`
- **실행 시간**: 로컬 기준 약 1~3초 (초경량 정적 검증)
- **검증 범위**:
  - `contracts/schemas/**/*.schema.json` 문법, Draft 메타 스키마 유효성 및 `$id` 중복 검사
  - `contracts/examples/`의 예제 JSON 및 Dataset Manifest 유효성
  - `contracts/test-vectors/` 디렉터리 구조, 필수 파일 존재 여부 및 Dataset Manifest 무결성 (role, SHA-256, `size_bytes`, 경로 안전성)
  - `expected/` 산출물 간 정적 정합성 (`feature_columns.count`, `labels` 행 수, `row_metadata` 행 수, `summary.json` 라벨/행 분포)
  - Schema 또는 Test Vector 부재 시 성공하는 false-green 차단
- **CI 워크플로우**: `.github/workflows/contract-vectors.yml` (Docker·DB·브라우저·LLM 없이 순수 파일/스키마 검증)

### 2. Generator 런타임 및 Golden Parity 검증 (`generator-feature-runtime.yml`)
- **검증 범위**:
  - Generator Docker 이미지 빌드 및 컨테이너 내부 환경 구동
  - `POST /feature` 실제 실행 및 Feature Dataset Bundle 생성
  - 계산된 Feature, Label, Row Metadata, Summary 및 Provenance와 Golden Vector Expected 간 100% 런타임 Parity 검증
- **역할 분담**: 정적 Schema 및 테스트 벡터 파일 무결성은 경량 CI(`contract-vectors.yml`)가 담당하고, 실제 비즈니스 로직 계산 및 Docker 런타임 검증은 런타임 CI(`generator-feature-runtime.yml`)가 담당합니다.

## Migration principle

향후 추가 Migration에서는 실제로 존재하고 시스템이 사용하는 계약만 이전한다.
존재하지 않는 Schema를 목표 구조를 채우기 위해 새로 만들지 않는다.
사용 여부가 불명확한 파일은 삭제하지 않으며 먼저 생산자·소비자·테스트 참조를 확인한다.
