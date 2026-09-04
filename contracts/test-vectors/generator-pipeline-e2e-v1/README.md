# Generator Pipeline E2E Golden Vector v1

이 테스트 벡터는 `Protocol Record` -> `Canonical Observation` -> `Dataset Manifest` -> `Runtime Handoff` -> `RuntimeInputIdentity` -> `Prediction Result Batch` 전 과정을 하나의 결정적(Deterministic) 통합 벡터로 검증합니다.

## 결정적 비교 불변 식별자 (Deterministic Invariants)
- `dataset_id`: gen-data-S01-L01
- `dataset_version`: window-20260828T130000Z-map-d545f01d
- `source_uri`: data/observations/gen-data-S01-L01/window-20260828T130000Z-map-d545f01d/observations.jsonl
- `source_checksum`: observations.jsonl의 SHA-256
- `source_kind`: live_sensor
- `source_contract_version`: generator-dataset-input-v1
- `source_schema_version`: canonical-observation-v1
- `pipeline_contract_version`: generator-prediction-result-v1
- `handoff_id`: Dataset과 RuntimeInput에 기반한 결정적 식별자
- `runtime_job_id`: run-e2e-handoff-d545f01d
- `asset_id`: CNC-01
- `model_id`: pdm-lightgbm
- `model_version`: pdm-lightgbm-v1.0
