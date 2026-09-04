# Generator Training API Contract Examples

본 디렉터리는 Generator `POST /train` 및 `POST /train/{base_model}` 엔드포인트의 공식 요청 계약 예시 및 Training Configuration 예시를 제공합니다.

## 파일 구성

1. `training-config-v1.json`:
   - 공식 Training Configuration 스키마(`contracts/schemas/generator-training-config.schema.json`)를 준수하는 설정 파일 예시.
   - `asset_time_split` 분할 전략 (train 70%, val 15%, test 15%), random_seed 42, 모델별 기본 하이퍼파라미터 및 평가 메트릭 정의.

2. `training-request-all-models.json`:
   - `POST /train` 전체 모델(LightGBM, XGBoost, Random Forest) 학습 실행 요청 예시.

3. `training-request-single-model.json`:
   - `POST /train/lightgbm` 단일 모델 학습 실행 요청 예시.

## 계약 규칙

- **Training Config 바인딩**: `training_config_version`은 단순한 식별자가 아니며, 시스템에 등록된 버전 파일의 SHA-256 해시 및 스키마 검증과 1:1로 바인딩됩니다.
- **Feature Dataset Bundle 소비**: 5개 필수 파일(`features.npy`, `labels.npy`, `feature_columns.json`, `row_metadata.json`, `feature_metadata.json`)이 완비된 불변 번들만 소비합니다.
- **불변 Model Artifact 발행**: `models_store/artifacts/{model_id}/{model_version}/`에 6개 필수 파일(`manifest.json`, `model.joblib`, `feature_schema.json`, `label_schema.json`, `history_requirement.json`, `metrics.json`)을 원자적으로 발행합니다. 동일 버전 재발행은 `409`로 차단됩니다.
