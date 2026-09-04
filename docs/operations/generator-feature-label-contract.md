# Generator Feature & Label 계약 명세서

- **문서 상태**: `목표 계약 (Target Specification)` — 부분 구현 완료, 피처 네이밍/스키마 발행 후속 수용 예정
- **관련 저장소**: `oosuhada/agentic-ontology-dashboard`
- **대상 파이프라인**: `systems/generator/feature` (`feature_builder.py`, `feature_label_service.py`)

---

## 1. Extraction Plan 및 데이터 분기 계약

`systems/generator/extraction` 파이프라인은 원본 DataFrame에서 다음 메타데이터를 추출한다.

| 메타데이터 | 역할 | 현행 상태 |
|---|---|---|
| `id_column` | 설비 식별자 (Asset Partition Key) | PR #21 구현 완료 |
| `time_column` | 관측 시각 (Canonical Time Ordering Key) | PR #21 구현 완료 |
| `duplicate_policy` | 중복 처리 정책: `error`, `aggregate` | 부분 구현 — long-format 완료, wide-format 구현 필요 |
| `aggregation` | 집계 방식: `mean`, `first`, `sum` | long-format의 `aggregate` 경로 구현 완료 |

### single_asset 및 Heuristic Fallback 정책

- 현행: `id_column` 식별 실패 시 환경과 관계없이 경고 로그(Warning) 출력 후
  단일 시계열 분기로 처리한다. `single_asset` 필드는 아직 없다.
- 목표: 명시적 `single_asset` 플래그를 도입하고, `id_column` 식별 실패 시
  `production`/`staging` 환경에서는 Fail-Fast, `local`/`demo`/`test`
  환경에서는 경고 후 단일 시계열 분기로 분리한다.
- 상태: `목표 계약 / PR #21~#22 구현 필요 (Target Contract)`

### duplicate_policy 구현 범위

| 필드 | 타입 (실제 Pydantic 정의) |
|---|---|
| `duplicate_policy` | `str`, 기본값 `"error"` (`"error"` \| `"aggregate"`, enum/Literal 아님) |
| `aggregation` | `Optional[str]` (`"mean"` \| `"first"` \| `"sum"`, enum/Literal 아님) |

- 현행: `structure_type="tabular_row_as_attribute"`(long-format) 구조에서는
  `extraction_service.py`가 `[id_col, time_col, attribute_col]` 기준 중복을
  검사하고, `duplicate_policy`에 따라 `aggregate`(지정 `aggregation`으로
  `pivot_table` 집계) 또는 명시적 `ValueError`를 실행한다. **구현 완료.**
- 현행: `structure_type="tabular_column_as_attribute"`(이미 wide 형태) 구조에는
  `(id_col, time_col)` 기준 중복 검사가 없다. `feature_builder.py`도 이 검사를
  하지 않는다. **구현 필요.**
- 목표: `tabular_column_as_attribute` 구조에도 `[id_col, time_col]` 기준 중복
  검사를 추가하고, 동일한 `duplicate_policy`/`aggregation` 필드로 처리한다
  (센서 컬럼에 대해 `aggregation` 함수 적용, `error`면 명시적 실패).
- 목표: `duplicate_policy`/`aggregation` 필드를 `Literal["error", "aggregate"]`
  / `Literal["mean", "first", "sum"] | None`으로 강화해 Pydantic이 잘못된 값을
  자동으로 거부하게 한다.
- 상태: `부분 구현 (long-format 완료) / wide-format 구현 필요 (Target Contract)`

---

## 2. Feature 격리 및 결정론적 계산 계약 (Invariants 15~17)

### 2.1 설비별 시계열 연산 격리 (Invariant 15)
- `rolling_mean`, `rolling_std`, `moving_average`, `diff` (gradient), `shift` (lag), `ema` 연산은 복수 설비 데이터 수용 시 **반드시 `df.groupby(id_col)` 내부에서 수행**한다.
- 설비 경계를 넘어 롤링 윈도우나 시프트 값이 누설(Leakage)되는 것을 금지한다.
- **상태**: `결정 완료 / PR #21 구현 완료`

### 2.2 결정론적 타임스탬프 정렬 (Invariant 16)
- 입력 DataFrame의 행 순서 셔플에 영향을 받지 않도록 `canonicalize_timestamp_series`를 적용하고 `[id_col, time_col]` (또는 `[time_col]`) 기준 명시적 정렬(`sort_values().reset_index(drop=True)`)을 수행한다.
- **상태**: `결정 완료 / PR #21 구현 완료`

### 2.3 Feature Naming 및 Naming Collision 방지 (Invariant 17)
- **현행 (PR #21 초기)**: `{ontology_node}_{operation}` (예: `Vibration_rolling_mean`)
  - *문제점*: 동일 온톨로지 노드(`Vibration`)로 매핑된 복수 source column(`vibration_sensor_1`, `vibration_sensor_2`) 존재 시 덮어쓰기 충돌 발생.
- **목표 계약 (Target Specification)**:
  - 명시적 구분자 적용: `<source_field>__<ontology_node>__<operation>__<parameters>`
  - 예: `vibration_raw__Vibration__rolling_mean__window_5`
- **상태**: `목표 계약 / 구현 필요 (Target Contract)`

---

## 3. Label Horizon 및 구간 라벨링 계약 (Invariants 18~19)

### 3.1 예측 타스크 계약 (Invariant 18)
- `prediction_task`: `"binary_failure_within_horizon"`
- `prediction_horizon_hours`: 기본값 24시간

### 3.2 Label 구간 매칭 및 Active Failure 정책

failure metadata의 `time_columns`는 서로 다른 의미를 갖는 최소 2개의 역할로
**반드시 분리해서 받는다.** 하나의 `end_col`로 뭉뚱그려 선택하지 않는다.

| 역할 | semantic 태그 | 의미 |
|---|---|---|
| anchor | `failure_point` | 고장이 실제로 발생한 시점. positive 구간의 끝(제외) |
| exclusion_end | `period_end`, `maintenance_end` | 다운타임/정비 완료 시점. 이 시점까지는 학습에서 제외 |
| degradation_start (참고용) | `period_start` | 열화 관측 시작 시점. **positive 구간 계산 및 학습 입력에 사용하지 않는다** |

**Positive interval은 `prediction_task=binary_failure_within_horizon` 의미와
정확히 일치하도록 항상 다음 한 가지 공식을 사용한다.**

```text
positive = [failure_point - prediction_horizon, failure_point)
```

- `degradation_start`(`period_start`)가 있어도 이 공식에는 영향을 주지 않는다.
  `degradation_start`는 positive 구간을 넓히거나 좁히는 데 쓰지 않는다.
- **Target Leakage 방지 정책**: `degradation_start`를 Label DataFrame의 일반 컬럼으로 추가하지 않으며 라벨 계산 및 모델 입력(`X`)에서 제외한다. 필요 시 별도 label metadata 또는 provenance에만 저장한다.
- 모델 학습 시 학습 피처 선택은 임의 컬럼 제외 방식이 아니라 Feature Schema allowlist로 명시적으로 선택한다: `X = labeled_df[feature_schema.feature_names]`

**anchor(`failure_point`)를 metadata에서 찾을 수 없는 경우**

이 정책은 §1의 `id_column` fail-fast 정책과는 별개의 관심사이며, 환경에
따라 분기하지 않는다.

- anchor가 없으면(구간 metadata 유무와 무관하게): 해당 이벤트는 라벨링에서
  제외하고 warning을 남긴다. `period_end`/`maintenance_end`/`period_start`를
  anchor로 대신 쓰지 않는다.

**제외 구간**
- `[failure_point, exclusion_end]` (exclusion_end가 있는 경우)는 정상도 예측
  대상도 아니므로 최종 라벨 DataFrame에서 행 자체를 제거한다. `label=0`으로
  채우지 않는다.
- `exclusion_end`가 없으면 최소한 `failure_point` 자체 시점의 관측 행은
  positive에서 제외한다 (경계 값 포함 금지).

**구현 요구사항 (PR #21)**
- `build_labels()`는 `anchor_col`(`failure_point`), `exclusion_end_col`
  (`period_end`/`maintenance_end`)를 서로 다른 변수로 분리해서 받는다.
  `degradation_start`는 라벨 계산 및 라벨 DataFrame에 관여하지 않는다.
- 구간 metadata 있음/없음 두 분기 모두 동일한 `failure_point - horizon` 계산을
  공유한다.
- 회귀 테스트:
  - `degradation_start`가 `failure_point - horizon`보다 늦어도 positive 구간이
    `[failure_point-horizon, failure_point)` 전체로 유지되는지
  - anchor 없이 exclusion_end/degradation_start만 있는 경우 이벤트가 제외되는지
  - `degradation_start`가 모델 입력에 포함되지 않으며, Feature Schema allowlist 컬럼만 학습에 사용되는지 검증한다.

> **주의**: 이 절 변경은 기존에 생성된 Feature/Label과 그 위에서 학습된
> 모델의 의미를 바꾼다. `label_schema_version`을 올리고(`pdm-label-v3`),
> 기존 산출물을 재사용하지 않고 재생성한다. PR #21 라벨 구현·테스트,
> PR #22 학습 데이터가 함께 영향받는다.

---

## 4. Feature / Label Schema 버전 관리

- **`feature_schema_version`**: `"pdm-feature-v2"`
- **`label_schema_version`**: `"pdm-label-v3"`
- 학습 실행 및 Model Artifact Publish 시 `feature_schema.json`과 `label_schema.json`이 함께 패키징되어 저장되어야 한다.
- **상태**: `목표 계약 / PR #22 구현 필요 (Target Contract)`

---

## 5. 완료 조건

- [ ] positive 구간이 항상 `[failure_point-horizon, failure_point)`로
      계산되며 `degradation_start`로 clip되지 않는다.
- [ ] `degradation_start`는 Label DataFrame 및 모델 입력(`X`)에서 제외되어 target leakage가 방지된다.
- [ ] Feature Schema에 선언된 컬럼 allowlist만 모델 학습 입력으로 사용된다.
- [ ] anchor 없이 exclusion_end/degradation_start로 대체되지 않는다.
- [ ] 제외 구간이 label=0이 아니라 행 자체 제거로 처리된다.
- [ ] 구간 metadata 있음/없음 두 분기가 동일한 계산 로직을 공유한다.
- [ ] `tabular_column_as_attribute` 구조에 `[id_col, time_col]` 기준 중복 검사가 추가된다.
- [ ] `duplicate_policy`/`aggregation`이 `Literal` 타입으로 강화된다.
- [ ] 기존 학습 데이터·모델 재생성 필요성이 완료 노트에 기록된다 (§3.2 참조).
