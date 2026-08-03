# ML

AI4I 데이터 검증, 누수 차단, 파생변수, 모델 비교, 임계값 선택과 Evidence 생성을 담당한다.

## CLI

```bash
export PYTHONPATH="$PWD/ml/src"
python -m ontology_dashboard_manufacturing_ml.cli validate-fixtures --root .
python -m ontology_dashboard_manufacturing_ml.cli audit-dataset data/raw/ai4i2020.csv
python -m ontology_dashboard_manufacturing_ml.cli train data/raw/ai4i2020.csv --output ml/artifacts
python -m ontology_dashboard_manufacturing_ml.cli evidence data/fixtures/GS-002-tool-wear-warning.json
```

## 정책 분리

- `config/trained_model_policy.json`: AI4I Random Forest 전용
- `config/threshold_policy.json`: offline Gold predictor 전용

두 정책의 확률을 서로 교환해 사용하지 않는다. `TWF/HDF/PWF/OSF/RNF`는 모델 입력으로 사용할 수 없다.

모델 binary는 재생성 가능하므로 기본 Git 추적 대상이 아니다.
