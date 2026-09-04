# Model Artifact Publish 계약 명세서

- **문서 상태**: `확정 계약 (Confirmed Contract)` — 최초 공식 `model-artifact-v1.0`
- **관련 저장소**: `oosuhada/agentic-ontology-dashboard`
- **대상 파이프라인**: `systems/generator/model` (`model_registry.py`, `model_store`) & `systems/backend/app/diagnosis`

> 이 계약은 최초 공식 `model-artifact-v1.0`이다. 이전에 저장소 코드·문서·테스트에서
> 사용한 동일 버전 문자열(`artifact_provider.py`의 `ARTIFACT_SCHEMA_VERSION` 상수 포함)은
> 이 계약 확정 이전의 개발 초안이며, 공식 Artifact나 호환·마이그레이션 대상으로 보지 않는다.
> dual-version reader, 기존 버전과의 migration, 장기 deprecation 정책은 구현하지 않는다.

> 이 문서가 정의하는 구조는 확정된 문서 계약이며, 아직
> `contracts/schemas/model-artifact.schema.json`, Generator publisher 및 Backend loader에는
> 반영되지 않았다. 현재 main은 PR #9의 실행 가능한 개발 초안
> (`Implemented Draft`)을 사용하며, `tests/test_system_ownership.py`가 해당 초안의
> publish → validation → load 경로를 검증한다. 공식 전환은 아래 후속 구현 완료
> 조건과 통합 병합 게이트를 충족한 뒤 수행한다.

---

## 1. Model Artifact 개념 및 책임 경계

- **Model Artifact**: `systems/generator`가 학습/평가를 완료한 후 발행하는 불변(Immutable) 산출물 패키지.
- **주입 방식**: 환경 변수 `MODEL_ARTIFACT_URI` 또는 Provider 서비스 인터페이스를 통해 `systems/backend`로 주입된다.
- **Backend 탐색 금지**: `systems/backend`는 sibling 경로 (`../generator/...`)나 물리 디렉터리를 정적으로 탐색하는 것을 엄격히 금지한다.

---

## 2. Model Artifact 필수 구성 요소

발행된 Model Artifact 패키지는 아래 6개 파일을 **모두 필수**로 포함해야 한다.
`manifest.json`을 제외한 나머지 5개 파일은 `artifact_files`의 필수 role로
등록되며, consumer는 로드 전 파일별 SHA-256을 검증한다.

| 파일명 | 역할 및 내용 |
|---|---|
| `manifest.json` | artifact_type, model_id, model_version, dataset_version, schema versions, checksum 메타데이터 |
| `model.joblib` | 학습 완료된 추론 모델 객체 |
| `feature_schema.json` | 입력 피처 계약 버전 및 피처 이름/타입/파라미터 명세 |
| `label_schema.json` | 타겟 라벨 호라이즌 및 구간 정의 계약 명세 |
| `history_requirement.json` | Backend 추론 시 필요한 과거 관측 시계열 조건 (`minimum_history_rows`, `maximum_lookback_hours` 등) |
| `metrics.json` | 오프라인 모델 평가 지표 요약 |

---

## 3. Manifest 확정 구조

아래 필드 이름과 계층 구조는 확정본이다. 예시 문자열(`created_at`, `run_id`,
`code_revision` 등)은 실제 발행 시 생성되는 값으로 대체된다.

```json
{
  "artifact_type": "predictive_maintenance_model",
  "artifact_schema_version": "model-artifact-v1.0",

  "model_id": "lightgbm",
  "model_version": "1.0.0",
  "created_at": "<발행 시각, ISO-8601>",

  "dataset_version": "<학습에 사용한 dataset 식별자>",
  "dataset_schema_version": "<dataset 스키마 버전>",
  "feature_schema_version": "pdm-feature-v2",
  "label_schema_version": "pdm-label-v3",
  "history_requirement_version": "<history_requirement.json 스키마 버전>",
  "metrics_schema_version": "<metrics.json 스키마 버전>",

  "prediction_contract": {
    "prediction_task": "binary_failure_within_horizon",
    "prediction_horizon_hours": 24,
    "probability_output": "positive_class_probability",
    "positive_class": 1
  },

  "model_runtime": {
    "format": "joblib",
    "framework": "<lightgbm | xgboost | scikit-learn>",
    "framework_api": "sklearn",
    "framework_version": "<실행 환경의 실제 버전>",
    "python_version": "<실행 환경의 실제 버전>",
    "entry_role": "model",
    "output_type": "positive_class_probability"
  },

  "training_config": {
    "algorithm": "<lightgbm | xgboost | random_forest>",
    "target_name": "label",
    "feature_count": "<int>",
    "random_seed": "<int>",
    "split_strategy": "asset_time_split"
  },

  "provenance": {
    "training": {
      "run_id": "<run registry의 run 식별자>",
      "code_revision": "<학습에 사용된 코드의 커밋 해시>",
      "source_dataset_manifest_checksum": "<dataset manifest의 checksum>",
      "publisher": "systems/generator"
    }
  },

  "compatibility": {
    "feature_executor_version": "<Feature Contract 실행기 호환 버전>"
  },

  "artifact_files": [
    { "role": "model", "path": "model.joblib", "sha256": "..." },
    { "role": "feature_schema", "path": "feature_schema.json", "sha256": "..." },
    { "role": "label_schema", "path": "label_schema.json", "sha256": "..." },
    { "role": "history_requirement", "path": "history_requirement.json", "sha256": "..." },
    { "role": "metrics", "path": "metrics.json", "sha256": "..." }
  ]
}
```

**최상위 필수 필드**: `artifact_type`, `artifact_schema_version`, `model_id`,
`model_version`, `created_at`, `dataset_version`, `dataset_schema_version`,
`feature_schema_version`, `label_schema_version`, `history_requirement_version`,
`metrics_schema_version`, `prediction_contract`, `model_runtime`,
`training_config`, `provenance`, `compatibility`, `artifact_files`.

**`framework`와 `algorithm`은 개념이 다르다.** `framework`는 모델 객체를 로드하는 데
실제로 필요한 라이브러리를, `algorithm`은 학습에 사용한 알고리즘 이름을 가리킨다.
RandomForest는 별도 라이브러리가 아니라 scikit-learn 구현이므로 둘이 일치하지 않는다.

| algorithm | framework |
|---|---|
| `lightgbm` | `lightgbm` |
| `xgboost` | `xgboost` |
| `random_forest` | `scikit-learn` |

**`compatibility.feature_executor_version`**은 Backend에만 국한된 버전이 아니라,
Feature Contract(ADR-001)를 실행하는 어떤 executor든(현재는 Backend) 지켜야 하는
호환 버전 표기다.

**최상위 `checksum` 필드는 사용하지 않는다.** 파일 무결성은 `artifact_files[*].sha256`
하나로만 검증한다 (기존 문서의 "deprecated checksum 유지" 제안은 철회).

### training_config.split_strategy 확정

`training_config.split_strategy = "asset_time_split"`은 예시 값이 아니라
이번 계약의 기본 정책이다. 설비 간 데이터 누수와 미래 시점 정보 누수를 막기
위해 asset(설비)과 time(시간) 기준으로 train/test를 분리한다.

이 값은 PR #22 학습 구현과 테스트에 동일하게 적용한다. 실제 데이터 구조상
이 전략을 적용할 수 없는 사유가 발견되면, 임의로 다른 전략으로 바꾸지 않고
변경 필요성과 영향(재학습 범위, 평가 결과 변화)을 별도로 보고한다.

---

## 4. 모델 식별 규칙

하나의 학습 파이프라인은 여러 모델(LightGBM/XGBoost/RandomForest 등)을 독립적으로
학습·발행할 수 있다. 각 모델은 자신의 Artifact와 버전을 갖는다.

**Manifest 내부 필드**: 추적과 불변성 검증을 위해 `model_id`(예: `"lightgbm"`)와
`model_version`(예: `"1.0.0"`)을 항상 별도 필드로 유지한다.

**파생 표시값**: `{model_base}_{version}` 형식은 화면 표시와 파일 경로 등에서 참고용으로 사용할
수 있는 파생 표시값이다.

```text
lightgbm_1.0.0
xgboost_1.0.0
random_forest_1.0.0
```

Manifest의 canonical identity는 어디까지나 `model_id`/`model_version` 별도 필드이며,
이 파생 표시값이 이를 대체하지 않는다.

> 신호(signal) 내에서 모델을 어떻게 식별할지는 이 문서의 범위가 아니다. 여러
> 모델의 예측을 주기적으로 실행하고 결과를 취합해 이상 신호를 만드는 흐름과,
> 그 안에서 모델 식별 방식은 `GEN-STACK-02`(`ADR-002` 미해결 항목)에서 결정한다
> — 아직 확정되지 않았다.

---

## 5. History Requirement 및 Backend Runtime Feature Execution (ADR-002 연동)

rolling mean/std, lag, EMA 등의 시계열 피처는 단일 Current Observation만으로 계산할 수 없으므로 `history_requirement.json` 계약에 따라 Backend가 자산별 관측 이력을 로드하여 피처를 재현한다.

```json
{
  "expected_sampling_interval_seconds": 3600,
  "minimum_history_rows": 10,
  "maximum_lookback_hours": 24,
  "history_sufficiency_policy": "decision-required",
  "missing_history_policy": "fail"
}
```

> 아래 값은 설명용 예시이며 전역 고정값이 아니다.
> `expected_sampling_interval_seconds`, `minimum_history_rows`,
> `maximum_lookback_hours`는 학습 데이터 프로파일과 Feature Schema에 따라
> Artifact publish 시 결정한다.

---

## 6. Run Registry와 Model Artifact의 책임 분리

| 구분 | Run registry | Model Artifact |
|---|---|---|
| 목적 | 내부 운영 메타데이터 (어떤 run이 언제 실행됐는지) | Generator 학습·Runtime이 신뢰하고 로드하는 모델 계약 |
| 불변성 | 매 run마다 갱신됨 | `model_version` 단위로 immutable |
| 소비자 | Generator 내부 운영 | `systems/generator` training/runtime pipeline |

두 책임을 분리한다. run registry(`models_store/registry.json`)만 구현하고
Model Artifact publish API를 생략하지 않는다. run registry에만 기록하고
publish를 생략하면 Generator Runtime이 새 모델을 재현 가능하게 활성화할 수 없다.

---

## 7. Immutable publish 규칙

- `model_version`은 `model_id`별로 독립적으로 증가한다. 한 run에서 일부 모델만
  성공해도 성공한 모델만 새 version을 받는다.
- 동일 `model_version`으로 재publish를 시도하면 명시적으로 실패시킨다
  (`FileExistsError` 또는 동등한 예외). 기존 파일을 덮어쓰지 않는다.

---

## 8. Atomic publish

- publish는 임시 디렉터리에 전체 파일 집합(`manifest.json`, `model.*`,
  `feature_schema.json`, `label_schema.json`, `history_requirement.json`,
  `metrics.json`)을 먼저 완성한 뒤, 최종 위치로 원자적 연산(`os.replace()`
  또는 동등한 방식)으로 이동한다.
- publish 도중 예외가 발생하면 목적지에 부분 결과가 남지 않는다.
- publish 실패 시 run registry도 갱신하지 않는다 — registry에 기록된 version은
  항상 실제로 publish가 완료된 version이어야 한다.

---

## 9. 공개 API 유지

- 기존 `publish_model_artifact()`, `validate_manifest()`, `ModelRegistry` 공개
  API를 삭제하지 않고 유지한다.
- `train_and_publish_model` 심볼은 `ml/src/factory_signal_ml/cli.py`,
  `tests/test_system_ownership.py`가 이미 import하고 있으므로 이름을 바꾸지
  않는다.

---

## 10. 완료 조건 및 후속 구현 완료 조건 — 공식 v1.0 전환

- [ ] PR #22에서 Generator publisher가 공식 `model-artifact-v1.0` Manifest와
      필수 파일 6개를 생성할 수 있도록 구현한다.
- [ ] Backend/#24 작업에서 `artifact_provider.py`가 공식 Manifest 필드와
      필수 role 5개를 검증하도록 구현한다.
- [ ] `contracts/schemas/model-artifact.schema.json`은 publisher와 loader가 모두 준비된
      통합 전환 시점에 공식 v1.0 구조로 교체한다. Schema만 먼저 바꾸지 않는다.
- [ ] `tests/test_system_ownership.py`를 새 계약에 맞게 함께 갱신한다.
- [ ] Schema, publisher, loader 및 테스트를 하나의 호환 전환 단위로 검증한다.
- [ ] publish → JSON Schema validation → Backend load round-trip이 통과한다.
- [ ] 한쪽만 공식 계약으로 전환된 main 상태를 배포하지 않는다.
- [ ] PR #24 완료 후 공유 Schema를 `contracts/schemas/`로 이식하고 코드,
      테스트, 스크립트, Docker, Render, CI 및 문서 참조를 함께 갱신한다.
- [ ] `artifact_schema_version`이 `model-artifact-v1.0`(최초 공식)으로 발행된다.
- [ ] `manifest.json`이 §3의 확정 구조(신규 3개 필드 포함)를 모두 포함한다.
- [ ] 6개 파일이 모두 존재하고, `manifest.json`을 제외한 5개가 `artifact_files`
      필수 role로 등록된다.
- [ ] `artifact_files`의 모든 항목이 개별 SHA-256으로 검증된다.
- [ ] 최상위 `checksum` 필드가 manifest에 존재하지 않는다.
- [ ] role 중복, path 중복이 거부된다.
- [ ] `artifact_files[*].path`가 Artifact root 기준 상대경로만 허용하고,
      절대경로·`../` 경로 이탈은 거부된다.
- [ ] 동일 `model_id` + `model_version` 재publish가 명시적으로 실패한다.
- [ ] publish 도중 예외 발생 시 목적지에 부분 결과가 남지 않는다 (atomic).
- [ ] publish 실패 시 run registry가 갱신되지 않는다.
- [ ] `training_config.split_strategy`가 `"asset_time_split"`으로 기록된다.
- [ ] `model_id`와 `model_version`이 Manifest에 별도 필수 필드로 기록된다.
- [ ] 필요한 공개 학습·publish 심볼이 유지된다.
- [ ] 필수 import 실패를 `None` 또는 빈 registry로 숨기지 않는다.

---

## 11. 공식 전환 병합 게이트 및 구현 참고사항

### 11.1 공식 전환 병합 게이트

PR별 구현 책임과 main 반영 시점을 구분한다.

```text
PR #22
→ 공식 publisher와 필수 파일 생성 구현

PR #24 / Backend
→ 공식 loader 구현
→ 공식 Schema 전환
→ round-trip 테스트 갱신 및 통과

통합 병합 게이트
→ Schema + publisher + loader + 테스트가 모두 준비된 경우에만 공식 전환
```

Stacked PR을 유지하는 경우 PR #24에서 전체 round-trip을 통과시킨 뒤 #22~#24를
중간 배포 없이 연속 병합한다. 필요하면 공식 전환 부분을 별도 통합 PR로 묶는다.

다음 중간 상태는 허용하지 않는다.

```text
새 publisher + 구 Schema/loader
구 publisher + 새 Schema/loader
새 Schema + 구 publisher/loader
```

### 11.2 Artifact path containment (Backend loader 구현 참고)

JSON Schema는 `artifact_files[*].path`가 비어 있지 않은 문자열인지 등 기본 형태만
검증한다. 절대경로, Windows drive 경로, 역슬래시 traversal, symlink 및 Artifact
root 이탈은 Backend loader에서 검증한다.

문자열 `startswith()`만으로 root containment를 판정하지 않는다.

```python
from pathlib import Path


def _resolve_within_root(root: Path, rel_path: str) -> Path:
    resolved_root = root.resolve()
    raw_path = Path(rel_path)

    if raw_path.is_absolute() or raw_path.drive:
        raise ValueError(f"artifact path must be relative: {rel_path!r}")

    candidate = (resolved_root / raw_path).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            f"artifact_files path escapes artifact root: {rel_path!r}"
        ) from exc

    return candidate
```

### 11.3 필수 role과 path 중복 검사 (Backend loader 구현 참고)

```python
REQUIRED_ARTIFACT_ROLES = (
    "model",
    "feature_schema",
    "label_schema",
    "history_requirement",
    "metrics",
)

roles = [item["role"] for item in manifest["artifact_files"]]
if sorted(roles) != sorted(REQUIRED_ARTIFACT_ROLES):
    raise ValueError(
        f"artifact_files roles must be exactly {REQUIRED_ARTIFACT_ROLES}, got {roles}"
    )

paths = [item["path"] for item in manifest["artifact_files"]]
if len(paths) != len(set(paths)):
    raise ValueError("artifact_files declares duplicate paths")
```

각 role이 정확히 한 번씩 존재하는지는 JSON Schema의 `minItems`만으로 보장하지
않고 loader에서 검증한다.
