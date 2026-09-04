# Generator Feature Input Contract Examples

본 디렉터리는 Generator `POST /feature` 엔드포인트의 입력 계약 및 Versioned Dataset Manifest 예제를 제공합니다.

## 구성 파일

- `observation-dataset-manifest.json`: Versioned Observation Dataset Manifest 예시 (`generator-dataset-input-manifest.schema.json` 검증 대상)
- `failure-dataset-manifest.json`: Versioned Failure Dataset Manifest 예시 (`generator-dataset-input-manifest.schema.json` 검증 대상)
- `feature-request.external.json`: 외부 Failure Dataset을 참조하는 `FeatureRequest` 예시
- `feature-request.embedded.json`: Observation 내부 indicator를 참조하는 `FeatureRequest` 예시

모든 예제 파일은 자동 JSON Schema 및 Pydantic 유효성 검사 테스트 대상입니다.

### Asset identity requirement

`POST /feature`가 소비하는 Observation Dataset에는 Preprocessing Plan의 `id_column`으로 선언된 설비 식별 컬럼이 반드시 존재해야 한다.

현재 파이프라인은 ID가 없는 Dataset을 자동으로 단일 설비로 간주하거나 임시 ID를 생성하지 않는다. 해당 입력은 `501 FEATURE_ASSET_ID_RESOLUTION_NOT_IMPLEMENTED`로 실패하며 Feature Dataset Bundle을 발행하지 않는다.

ID가 없는 단일 설비 Dataset 지원은 후속 기능으로 별도 구현한다.
