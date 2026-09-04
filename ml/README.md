# ML compatibility entrypoint

이 디렉터리는 PR #9 이관 코드의 기존 import/CLI 호환성을 유지한다. 운영 책임은 아래처럼 분리됐다.

- `systems/generator`: feature engineering, 모델 학습·평가, versioned Model Artifact publish
- `systems/backend/app/diagnosis`: current observation runtime inference, Product Result Artifact, Evidence
- `ml/src/factory_signal_ml/*`: 위 시스템으로 위임하는 compatibility adapter

`gen_data`의 기존 model/prediction/result 파일은 regression/migration fixture이며 이 디렉터리가 운영 SoT로 읽지 않는다.

## CLI

```bash
export PYTHONPATH="$PWD/ml/src"
python -m ontology_dashboard_manufacturing_ml.cli validate-fixtures --root .
python -m ontology_dashboard_manufacturing_ml.cli audit-dataset data/raw/ai4i2020.csv
python -m ontology_dashboard_manufacturing_ml.cli train data/raw/ai4i2020.csv --artifact-uri /tmp/model-artifacts
python -m ontology_dashboard_manufacturing_ml.cli evidence data/fixtures/GS-002-tool-wear-warning.json
```

## 정책 분리

- `config/trained_model_policy.json`: AI4I Random Forest 전용
- `config/threshold_policy.json`: 이관 provenance용 legacy copy. 운영 runtime 정책 SoT는 `systems/backend/app/diagnosis/threshold_policy.json`

두 정책의 확률을 서로 교환해 사용하지 않는다. `TWF/HDF/PWF/OSF/RNF`는 모델 입력으로 사용할 수 없다.

모델 binary는 재생성 가능하므로 기본 Git 추적 대상이 아니다. 운영 Backend는 `MODEL_ARTIFACT_URI`로 주입된 immutable Model Artifact를 소비한다.
