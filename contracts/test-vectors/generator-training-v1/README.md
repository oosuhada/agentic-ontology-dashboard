# Generator Training Contract Golden Test Vector (v1)

본 테스트 벡터는 Generator `POST /train` 및 `POST /train/{base_model}` 파이프라인의 다음 정합성을 검증합니다:

1. **Training Request 및 Training Config JSON Schema 정합성**
2. **Config Version, File SHA-256 및 Parameter 로드 정합성**
3. **Feature Dataset Bundle 소비 및 Provenance 교차 검증**
4. **설비·시간 분할(`asset_time_split`)의 결정성**
5. **불변 Model Artifact 패키지 (6개 파일: `manifest.json`, `model.joblib`, `feature_schema.json`, `label_schema.json`, `history_requirement.json`, `metrics.json`) 구성 및 Checksum 정합성**
6. **동일 `model_id/model_version` 재발행 시 `409` 차단 및 불변성 보장**

## 디렉터리 구성

- `request.json`: 테스트 실행 요청 페이로드
- `training-config.json`: 테스트에 사용되는 검증된 Training Config
- `expected/`:
  - `split-summary.json`: 기대되는 데이터셋 분할 요약 메트릭
  - `artifact-manifest-required.json`: 기대되는 Model Artifact `manifest.json` 필수 필드 및 구조
