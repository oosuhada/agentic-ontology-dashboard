# Operations 공통 스키마 정의서

## 1. 목적과 상태

이 문서는 화면, API와 LLM 보고서가 사용하는 공통 필드명의 단일 기준이다.
공식 Canonical V3.1 패키지에서 확인한 계약과 제품 계층에서 추가하는 계약을
분리한다.

| 상태 | 의미 |
|---|---|
| `확정` | 공식 V3.1 파일 또는 계약에서 검증됨 |
| `파생` | 확정 필드를 결합하거나 계산함 |
| `제안` | Operations 구현을 위한 계약안이며 제품 결정이 필요함 |
| `제외` | Operations 계약으로 사용하지 않음 |

기준 버전:

- Dataset: `canonical-ai4i-physics-v3.1`
- Model: `independent-logreg-v3.1`
- Result Artifact: `result-artifact-v1.0`

상세 검증 근거는 [Canonical V3.1 필드 검증표](./v3.1-field-validation.md)를
따른다.

## 2. 공통 표현 규칙

- 날짜시간은 시간대가 포함된 ISO-8601 문자열을 사용한다.
- 확률과 confidence는 `0` 이상 `1` 이하의 number다.
- 원천 CSV 필드명과 Result Artifact JSON key는 변경하지 않는다.
- 한국어 이름과 설명은 별도 표시 계층에서 관리한다.
- API 결합·계산 필드를 Canonical 또는 Result Artifact 원문으로 표현하지 않는다.
- Observation은 Backend의 canonical store가 보존하고, Runtime Feature와 score는
  `systems/generator`가 생성한다. Backend는 Prediction Result Batch를 검증하고 threshold와
  업무 정책을 적용해 Result Artifact/Evidence로 승격한다. Report와 Frontend는 공식 read
  boundary를 통해서만 ViewModel을 구성하며 `gen_data` 원본 로그를 직접 파싱하지 않는다.
- 고장 진실(failure truth)은 Observation 및 일반 Feature 입력에서 엄격히 분리하여 별도 Failure 데이터셋으로 관리한다.
- null을 정상값, 0 또는 고장 확정으로 변환하지 않는다.
- evaluation truth는 제품 스키마와 일반 조회 API에서 제외한다.

## 3. Canonical 원천 스키마

### 3.1 Asset

출처: `canonical/dataset/asset_master.csv` · 상태: `확정`

| 필드 | 타입 | 필수 | 설명 | 사용 화면 |
|---|---|:---:|---|---|
| `asset_id` | string | Y | 설비 고유 ID | 전체 |
| `asset_type` | enum | Y | `compressor`, `cnc` | 전체 |
| `site_id` | string | Y | 사이트 ID | 전체 |
| `cell_id` | string | Y | 생산 셀 ID | 전체 |

`display_name`, `is_active`, `assigned_engineer`는 원천 필드가 아니다.

### 3.2 AssetRelation

출처: `canonical/dataset/asset_relation.csv` · 상태: `확정`

| 필드 | 타입 | 필수 | 설명 | 사용 화면 |
|---|---|:---:|---|---|
| `from_asset_id` | string | Y | 연결 시작 설비 | Objects |
| `relation_type` | string | Y | 현재 `SUPPLIES_AIR_TO` 관계 | Objects |
| `to_asset_id` | string | Y | 연결 대상 설비 | Objects |

이 관계는 topology이며 고장 인과관계나 모델 feature가 아니다.

### 3.3 CompressorObservation

출처: `canonical/dataset/compressor_sensor_observation.csv` · 상태: `확정`

| 필드 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `observed_at` | datetime | Y | 관측 시각 |
| `asset_id` | string | Y | 압축기 ID |
| `site_id` | string | Y | 사이트 ID |
| `cell_id` | string | Y | 생산 셀 ID |
| `is_operating` | boolean | Y | 가동 여부 |
| `operating_state` | string | Y | 운전 상태 |
| `voltage_raw` | number | Y | 전압 관측값 |
| `rotation_raw` | number | Y | 회전 관측값 |
| `pressure_raw` | number | Y | 압력 관측값 |
| `vibration_raw` | number | Y | 진동 관측값 |
| `relative_vibration_z` | number | Y | 자산 기준 상대 진동 Z 값 |
| `relative_vibration_zone` | string | Y | 상대 진동 구간 |
| `generator_version` | string | Y | 데이터 생성기 버전 |

### 3.4 CncObservation

출처: `canonical/dataset/cnc_sensor_observation.csv` · 상태: `확정`

| 필드 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `observed_at` | datetime | Y | 관측 시각 |
| `asset_id` | string | Y | CNC ID |
| `site_id` | string | Y | 사이트 ID |
| `cell_id` | string | Y | 생산 셀 ID |
| `is_operating` | boolean | Y | 가동 여부 |
| `operating_state` | string | Y | 운전 상태 |
| `product_type` | string | Y | 가공 제품 유형 |
| `air_temperature_k` | number | Y | 공기 온도(K) |
| `process_temperature_k` | number | Y | 공정 온도(K) |
| `rotational_speed_rpm` | number | Y | 회전 속도(RPM) |
| `torque_nm` | number | Y | 토크(Nm) |
| `tool_wear_min` | number | Y | 공구 누적 사용시간(분) |
| `generator_version` | string | Y | 데이터 생성기 버전 |

### 3.5 ProductionCycle

출처: `canonical/dataset/cnc_production_cycle.csv` · 상태: `확정`

| 필드 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `product_id` | string | Y | 제품 또는 작업 ID |
| `cnc_asset_id` | string | Y | 작업 CNC ID |
| `cycle_started_at` | datetime | Y | 작업 시작 시각 |
| `cycle_completed_at` | datetime | Y | 작업 완료 시각 |
| `product_type` | string | Y | 제품 유형 |
| `cutting_minutes` | number | Y | 가공 시간(분) |
| `tool_wear_increment_min` | number | Y | 공구 사용 증가량(분) |

### 3.6 MaintenanceEvent

출처: `canonical/dataset/maintenance_event.csv` · 상태: `확정`

| 필드 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `maintenance_id` | string | Y | 정비 이벤트 ID |
| `asset_id` | string | Y | 정비 대상 설비 ID |
| `maintenance_type` | string | Y | 정비 종류 |
| `started_at` | datetime | Y | 정비 시작 시각 |
| `completed_at` | datetime | Y | 정비 완료 시각 |
| `tool_replaced` | boolean | Y | 공구 교체 여부 |
| `source_event_id` | string | N | 생성 근거 이벤트의 내부 추적 ID |

`source_event_id`를 이용해 evaluation truth의 상세 내용을 일반 화면에 노출하지
않는다.

## 3.7 Extraction Plan

출처: `systems/generator/extraction/extraction_agent.py`의 `ExtractionPlanResponse`

상태: `부분 구현 — long-format 집행 완료, wide-format 구현 필요`

| 필드 | 현행 타입 | 입력 필수 | 정규화 출력 | 현행 설명 | 목표 |
|---|---|:---:|:---:|---|---|
| `id_column` | string/null | N | Y(null 허용) | 설비 식별 컬럼 | 유지 |
| `time_column` | string/null | N | Y(null 허용) | 관측 시각 컬럼 | 유지 |
| `duplicate_policy` | string | N | Y | 기본값 `error`; `error`, `aggregate` | `Literal["error", "aggregate"]` |
| `aggregation` | string/null | N | Y(null 허용) | `mean`, `first`, `sum` | `Literal["mean", "first", "sum"] \| None` |

현행 집행 범위:

- `tabular_row_as_attribute`: 중복 검사 및 `error`/`aggregate` 정책 구현 완료
- `tabular_column_as_attribute`: `[id_column, time_column]` 중복 검사 미구현

상세는 `docs/operations/generator-feature-label-contract.md` §1을 따른다.

## 3.8 Feature Schema

출처: `systems/generator/feature/feature_builder.py` · 상태: `목표 계약 (Target Contract) / 구현 변경 필요`

```json
{
  "feature_schema_version": "pdm-feature-v2",
  "features": [
    {
      "name": "vibration_raw__Vibration__rolling_mean__window_5",
      "source_field": "vibration_raw",
      "source_ontology": "Vibration",
      "dtype": "float64",
      "unit": null,
      "operation": "rolling_mean",
      "parameters": {
        "window": 5
      },
      "partition_by": "asset_id",
      "order_by": "observed_at"
    }
  ]
}
```

> `min_periods`는 아직 확정 계약이 아니다. 현재 PR #21 구현값은 `1`이지만,
> golden-vector 검증과 모델 품질 비교 후 별도로 결정한다.
>
> 영향 범위는 워밍업 행 수, 학습 데이터 크기, rolling 통계 분포 및 기존
> 모델 재학습 여부다.

상세는 `docs/operations/generator-feature-label-contract.md` §2와
`docs/architecture-decisions/ADR-001-unified-feature-contract.md`를 따른다.

## 3.9 Label Schema

출처: `systems/generator/feature/feature_label_service.py` · 상태: `목표 계약 (Target Contract) / 구현 변경 필요`

```json
{
  "label_schema_version": "pdm-label-v3",
  "prediction_task": "binary_failure_within_horizon",
  "prediction_horizon_hours": 24,
  "positive_interval": "[anchor-horizon, anchor)",
  "anchor_semantic": "failure_point",
  "active_failure_policy": "excluded"
}
```

> `pdm-label-v3`는 기존 라벨 의미와 호환되지 않는다. 기존 Feature/Label
> 산출물과 해당 데이터로 학습한 모델은 재생성·재학습이 필요하다.

현재 Result Artifact의 `prediction_horizon_hours=24`와 학습 Label 계약이 실제로 연결되어야
한다. 상세는 `docs/operations/generator-feature-label-contract.md` §3을 따른다.

## 3.10 Training Run Metadata

출처: `systems/generator/model/model_registry.py`의 `runs/v{N}/run_meta.json` · 상태: `제안`

| 필드 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `trained_at` | datetime | Y | 학습 실행 시각 |
| `feature_cols` | string[] | Y | 학습에 사용된 feature 컬럼 순서 |
| `family_id` | string | Y | 설비 계열 식별자 |
| `source_telemetry_key` | string | Y | 학습에 사용된 telemetry 소스 |
| `source_failures_key` | string | Y | 학습에 사용된 failure 소스 |

## 4. Result Artifact 스키마

출처: `canonical/model_outputs/result_artifact.jsonl` · 상태: `확정`

한 행은 자산 한 대의 최신 예측 결과다.

| 필드 | 타입 | 필수 | 제약/설명 | 사용 화면 |
|---|---|:---:|---|---|
| `artifact_id` | string | Y | 결과 고유 ID | 내부 추적 |
| `artifact_type` | string | Y | `predictive_maintenance_result` | 내부 추적 |
| `schema_version` | string | Y | `result-artifact-v1.0` | 전체 |
| `asset_id` | string | Y | 예측 대상 설비 | 전체 |
| `asset_type` | enum | Y | `compressor`, `cnc` | 전체 |
| `observed_at` | datetime | Y | 예측 기준 관측시각 | 전체 |
| `prediction_horizon_hours` | integer | Y | 현재 24 | Objects, Report |
| `prediction_task` | string | Y | `binary_failure_within_horizon` | Objects, Report |
| `failure_probability` | number | Y | 0~1 | 전체 |
| `predicted_failure_type` | enum | Y | `failure_risk`, `no_significant_risk` | 전체 |
| `status_grade` | enum | Y | `normal`, `attention`, `warning`, `critical` | 전체 |
| `confidence` | number | Y | 0~1 | Objects, Report |
| `top_factors` | array | Y | 정확히 3개 | Objects, Report |
| `recommended_action` | object | Y | 정책 권고. 추천 미생성 상태 표현은 후속 schema version에서 nullable 또는 optional 전환 필요 | 전체 |
| `provenance` | object | Y | 데이터·모델·결과 출처 | 전체 |

`predicted_failure_type`은 PWF, HDF, OSF, TWF 등의 고장 모드 분류 결과가 아니다.

### 4.1 TopFactor

| 필드 | 타입 | 필수 | 제약/설명 |
|---|---|:---:|---|
| `rank` | integer | Y | 1~3 |
| `feature` | string | Y | 모델 파생 feature 이름 |
| `feature_value` | number | Y | 자산 내부 정규화 값 |
| `signed_contribution` | number | Y | 해당 관측치의 local factor score. Model Artifact 경로는 전역 feature importance를 단독 사용하지 않고 history baseline 이탈도를 곱한 local proxy를 사용한다. |
| `direction` | enum | Y | `risk_up`, `risk_down` |
| `explanation_method` | string | Y | `deterministic_component_score` 또는 `model_artifact_local_proxy_attribution` |

TopFactor 결정 변경:

- `top_factors`는 모델 설명서가 아니라 해당 Result Artifact 판단을 설명하는 event-local 근거다.
- 3주차 기준으로 Model Artifact는 SHAP/local explanation artifact와 이를 조회하는 API 계약을 아직 제공하지 않는다. 따라서 Product Result Artifact는 공식 instance attribution을 claim하지 않고, 현재 구현 가능한 proxy 수준으로 우선 계약한다.
- Model Artifact가 `feature_importances_`나 `coef_` 같은 전역 모델 가중치를 제공하더라도, 그 값을 그대로 rank/score로 쓰지 않는다. 전역 값만 쓰면 정상 설비와 critical 설비가 같은 feature/rank/score를 받기 때문이다.
- Model Artifact 경로의 현행 구현은 `전역 모델 가중치 × 현재 관측치의 history baseline 이탈도`로 local proxy score를 만든다. 이는 SHAP 같은 완전한 instance attribution이 아니므로 `model_artifact_local_proxy_attribution`으로 라벨링한다.
- local proxy를 만들 수 없는 feature는 top factor 후보에서 제외한다. basis를 억지로 만들지 않는다.
- history baseline은 observation timestamp와 같은 row를 제외한 과거 history로 계산한다. 따라서 GS-002 fixture처럼 history에 현재 observation이 중복 포함된 경우 baseline 표본은 3개이며, 현재 관측치는 비교 대상이지 baseline 구성원이 아니다.
- sensor evidence와 Model Artifact local proxy는 동일한 history baseline helper를 사용한다. dedupe, current-row exclusion, zero-variance 처리 정책이 두 곳에 따로 존재하지 않아야 한다.

현재 한계:

- `signed_contribution`은 SHAP value, logit contribution, probability contribution이 아니다.
- `direction`과 score scale은 모델군 간 동일한 절대 척도로 비교하지 않는다.
- top factor는 인과 원인이나 정비 root cause가 아니라, 현재 시점에서 모델 관련성과 baseline 이탈도를 함께 만족한 판단 근거 후보로 해석한다.
- 공식 local attribution이 필요하면 후속 Model Artifact explanation contract와 API 이식이 먼저 필요하다.
- SHAP은 현재 Product Result Artifact proxy 구현에 포함하지 않는다. SHAP은 별도 Model Artifact explanation contract에서 `method`, `scope`, `output_space`, `feature_space`, `background_dataset_version`, `explainer_version`을 명시한 뒤 도입한다.

### 4.2 RecommendedAction

| 필드 | 타입 | 필수 | 값 |
|---|---|:---:|---|
| `action` | enum | Y | `continue_monitoring`, `schedule_targeted_diagnostic_check`, `inspect_within_current_shift`, `immediate_inspection_and_stop_review` |
| `priority` | enum | Y | `routine`, `medium`, `high`, `urgent` |

권고는 자동 설비 정지 또는 자동 Work Order 실행 명령이 아니다.

### 4.3 Provenance

| 필드 | 타입 | 필수 | 제약/설명 |
|---|---|:---:|---|
| `dataset_version` | string | Y | `canonical-ai4i-physics-v3.1` |
| `model_version` | string | Y | `independent-logreg-v3.1` |
| `prediction_id` | string | Y | 내부 예측 결과 연결 ID |
| `source_type` | string | Y | `derived_result_artifact` |
| `canonical_source_mutated` | boolean | Y | 항상 `false` |

## 5. API/ViewModel 공통 스키마

이 절의 객체는 제품 계층 계약안이며 상태는 `제안`이다. Frontend·Backend 계약 확정 후 API
명세와 TypeScript/Pydantic 타입에 동일하게 반영한다.

### 5.0 역할 매핑

| 계층 | 생산 운영 의사결정자 | 현장 엔지니어 | 정비 작업자 |
|---|---|---|---|
| Identity/RBAC role code | `process_manager` | `process_engineer` | `maintenance_technician` |
| 제품 표시 의미 | 생산 운영 의사결정자 | 현장 엔지니어 | 정비 작업자 |
| legacy Report/UI view alias | `manager` | `engineer` | `engineer` |
| 업무 관점 | Evidence·엔지니어 결과 기반 운영 판단 | Evidence 확인·점검·분석 근거 작성 | 승인된 WorkOrder/MaintenanceAction 실행 |

`manager` / `engineer`는 기존 Report와 일부 legacy Operations 화면의 compatibility view 값이며 Identity/RBAC
role code가 아니다. `process_engineer`와 `maintenance_technician`은 legacy view alias가 같더라도 업무
역할과 허용 Action을 합치지 않는다. 상세 Action matrix와 표시 용어는
[`../closed-loop-product-consumption-contract.md`](../closed-loop-product-consumption-contract.md)를 정본으로
사용한다.

### 5.1 AssetPredictionSummary

Overview와 Objects 목록의 공통 행이다.

| 필드 | 타입 | 필수 | 출처 | 상태 |
|---|---|:---:|---|---|
| `asset_id` | string | Y | Asset/Artifact | 확정 |
| `asset_type` | enum | Y | Asset/Artifact | 확정 |
| `site_id` | string | Y | Asset 결합 | 파생 |
| `cell_id` | string | Y | Asset 결합 | 파생 |
| `observed_at` | datetime | Y | Artifact | 확정 |
| `is_operating` | boolean | Y | 최신 Observation | 파생 |
| `operating_state` | string | Y | 최신 Observation | 파생 |
| `failure_probability` | number | Y | Artifact | 확정 |
| `predicted_failure_type` | enum | Y | Artifact | 확정 |
| `status_grade` | enum | Y | Artifact | 확정 |
| `confidence` | number | Y | Artifact | 확정 |
| `recommended_action` | RecommendedAction | Y | Artifact. 추천 미생성 상태 표현은 후속 schema version에서 nullable 또는 optional 전환 필요 | 확정 |
| `dataset_version` | string | Y | Artifact provenance | 파생 |
| `model_version` | string | Y | Artifact provenance | 파생 |
| `artifact_schema_version` | string | Y | Artifact | 파생 |

### 5.2 AssetDetail

| 필드 | 타입 | 필수 | 출처 | 상태 |
|---|---|:---:|---|---|
| `asset` | Asset | Y | Canonical | 확정 |
| `latest_observation` | CompressorObservation 또는 CncObservation | N | Canonical 최신행 | 파생 |
| `prediction` | ResultArtifact | N | 최신 Artifact | 파생 |
| `relations` | AssetRelation[] | Y | Canonical | 확정 |
| `maintenance_events` | MaintenanceEvent[] | Y | Canonical | 확정 |
| `data_status` | DataStatus | Y | API | 제안 |

예측 또는 관측이 없으면 객체를 임의 값으로 채우지 않고 null과 `data_status`로
이유를 전달한다.

### 5.3 AssetDetailViewModel

객체명: `AssetDetailViewModel` · 상태: V2 변경 제안.

계약 객체명에는 `Operations` 같은 구현 네임스페이스 접두어를 붙이지 않는다. 현행
프론트엔드의 `OperationsEventDetailModel`, `OperationsAsset`, `OperationsReportModel`은 기존
구현의 기준 필드 확인용이며, API/schema 계약명은 `AssetDetail`,
`AssetDetailViewModel`, `AssetDetailFeature`처럼 접두어 없는 도메인
객체명으로 유지한다.

설비 상세 화면과 `map-report` 계열 그래프 UI를 위한 composition ViewModel이다. Product Result Artifact, Evidence Payload, Observation series, runtime prediction series, Activity/Maintenance source를 Backend adapter에서 병합해 제공한다. 프론트엔드는 raw JSONL, `gen_data` model output fixture, prototype adapter를 직접 파싱하지 않는다.

| 필드 | 타입 | 필수 | 출처 | 상태 |
|---|---|:---:|---|---|
| `asset` | Asset summary | Y | Asset/Object read model | 제안 |
| `risk` | object | Y | Product Result Artifact | 제안 |
| `risk.current` | number 또는 null | Y | Product Result Artifact `failure_probability` | 제안 |
| `risk.threshold` | number 또는 null | Y | Artifact root `threshold` 또는 policy | 제안 |
| `risk.status_grade` | string | Y | Product Result Artifact `status_grade` | 제안 |
| `risk.prediction_horizon_hours` | integer 또는 null | Y | Product Result Artifact | 제안 |
| `risk_series` | PredictionSeriesPoint[] | Y | Backend Product Result History Query Contract. canonical source는 `pm_result_artifacts` append-only history이며, detail payload가 필요할 때만 `prediction_result_id`로 `prediction_results`를 join | 제안 |
| `features` | AssetDetailFeature[] | Y | Feature catalog + Observation + Evidence | 제안 |
| `features[].key` | string | Y | Feature catalog | 제안 |
| `features[].label` | string | Y | Feature catalog 또는 display projection | 제안 |
| `features[].unit` | string | Y | Feature catalog 또는 Evidence sensor unit | 제안 |
| `features[].current` | CurrentObservation | Y | Product Result Artifact observation 또는 sensor evidence | 제안 |
| `features[].current.observed_at` | datetime | Y | Product Result Artifact observation time | 제안 |
| `features[].current.value` | number 또는 null | Y | Product Result Artifact observation 또는 sensor evidence | 제안 |
| `features[].current.quality_status` | enum | Y | Observation/Evidence quality | 제안 |
| `features[].baseline` | Baseline 또는 null | N | `evidence_payload.sensor_evidence.sensors[*].basis` | 제안 |
| `features[].history` | ObservationHistory | Y | Backend Observation read contract + Generator Runtime Feature result | 제안 |
| `features[].history.source_ref` | string | N | history 전체가 공유하는 Observation/Feature source reference | 제안 |
| `features[].history.points` | ObservationSeriesPoint[] | Y | actual pre-current observations | 제안 |
| `features[].top_factor` | Factor summary 또는 null | N | Product Result Artifact `top_factors` | 제안 |
| `equipment_history` | EquipmentHistoryRow[] | Y | Activity/Decision/Maintenance source | 제안 |
| `maintenance_context` | object | Y | Maintenance/Activity read model | 제안 |
| `maintenance_context.last_maintenance_days_ago` | integer 또는 null | Y | 정비 이력 | 제안 |
| `maintenance_context.similar_events_30d` | integer 또는 null | Y | Event/Activity 집계 | 제안 |
| `maintenance_context.open_work_order_exists` | boolean 또는 null | Y | Closed-loop read model | 제안 |
| `operation_context` | object | Y | 운영 read model | 제안 |
| `operation_context.load_level` | `low`/`normal`/`high` 또는 null | Y | 운영 상태 | 제안 |
| `operation_context.runtime_hours_7d` | number 또는 null | Y | 운영 집계 | 제안 |
| `operation_context.production_impact` | `none`/`low`/`medium`/`high` 또는 null | Y | 운영 영향 추정 | 제안 |
| `review_priority` | object 또는 null | Y | risk + criticality + context 조합 | 제안 |
| `evidence` | ReportEvidenceStatus | Y | Artifact/Evidence provenance | 제안 |
| `evidence.gaps` | EvidenceGap[] | Y | Backend adapter | 제안 |
| `data_status` | DataStatus | Y | API | 제안 |

`asset.criticality`는 모델 위험도나 WorkOrder priority가 아니라 설비/프로젝트 맥락의
운영 영향도다. 허용값은 `low`, `medium`, `high`, `null`이며, 누락 시 `medium`으로
기본값을 만들지 않는다. 이 경우 `asset.criticality=null`,
`asset.criticality_basis=[]`, `asset.criticality_source=unknown`과 함께
`evidence.gaps[]`에 `field=asset.criticality`,
`reason=criticality_missing_or_unresolved`를 기록한다. `owner_domain`은 표시 위치가 아니라
해결 책임 source를 뜻하며 `equipment`, `project`, `operations`, `maintenance`,
`diagnosis`, `dataset`, `report`, `frontend`, `unresolved` 중 하나를 사용한다.

`review_priority`는 화면 검토 순서를 설명하는 파생값이며 권한, WorkOrder priority,
Recommendation state가 아니다. 필요한 risk, criticality, context 입력이 없으면
`review_priority=null`과 gap으로 표현하고, 프론트엔드는 fallback 우선순위를 계산하지 않는다.

`features[].history.points`는 센서 Observation과 파생 Feature 시계열이므로 Product API가
`gen_data` raw JSONL이나 canonical CSV를 직접 파싱해 만들지 않는다. 같은 history가 공유하는
provenance는 point마다 반복하지 않고 `features[].history.source_ref` envelope에 한 번만 둔다.
point에는 `observed_at`, `value`, `quality_status`만 유지한다. 센서 Observation series는 Backend의
canonical/overlay branch-aware Observation read contract에서 읽고, 파생 Feature series는
Generator Runtime이 versioned Feature Schema/transform contract로 생성한 결과를 사용한다.
`systems/generator`는 Feature/Label 의미, History Requirement, transform contract, Model Artifact
publish와 Runtime Prediction을 소유한다. `risk_series`는 Backend가 Generator의 Prediction Result
Batch를 검증·승격해 저장한 Product Result history에서 파생한다. 현재 canonical source는
`pm_result_artifacts`의 asset별 append-only Product Result history이며, 상세
payload가 실제로 필요한 경우에만 `prediction_result_id`로 `prediction_results`를 조회한다. Product
API는 내부 테이블 shape를 직접 노출하지 않는다. `pm_prediction_timeline`,
`gen_data/canonical/model_outputs/prediction_timeline.jsonl`, legacy `precomputed_prediction_timeline`을
최신 운영 결과처럼 직접 소비하지 않는다.

추천 미생성 상태는 기존 Product Result Artifact schema와 별도 정렬이 필요하다. 현행
`recommended_action` 필수 object 계약은 그대로 유지하되, `unavailable`을 kind로 넣어
빈 추천 객체를 만들지 않는다. 근거 부족, unresolved basis, criticality 누락은 우선
`evidence_payload.recommended_actions=[]`와 `evidence_payload.evidence_gaps[]`로 표현하고,
Product Result root의 `recommended_action` nullable/optional 전환은 후속 schema version
변경으로 확정한다.

기존 Operations 상세 화면이 사용하던 Event detail 필드(asset, 현재 센서값, top factors,
threshold, data quality warning, activity, report, provenance)는 이 계약의 기준선이다.
아래 필드는 기준선에 추가되는 상세 리포트 필드이며, 단일 Product Result Evidence만으로
모두 채워진다고 가정하지 않는다.

| 필드 묶음 | 현재 Evidence만으로 산출 | 추가 source | 비고 |
|---|---|---|---|
| 현재 asset/risk/status/action | 가능 | 없음 | 최신 Product Result Artifact 기준 |
| 현재 센서값 | 가능 | 없음 | `observation` 또는 `sensor_evidence.sensors` |
| top factors/report citations | 가능 | 없음 | `top_factors`, `report.sections[].evidenceFieldIds` |
| feature baseline | 부분 가능 | Evidence Payload 노출 필요 | `sensor_evidence.sensors[*].basis`가 있는 feature만 가능 |
| feature 시계열 | 불가 | Observation API 또는 gen_data Layer 2 정규화 결과 | 단일 Event Evidence는 현재값 중심 |
| risk 시계열 | 불가 | Backend Diagnosis runtime prediction/result timeline | gen_data model output fixture 대체 금지 |
| crossing marker/history row | 불가 또는 부분 가능 | Observation series, baseline, Activity/Maintenance source | 합성 금지 |

시계열과 baseline의 최소 추적 필드는 다음과 같다.

| 객체 | 필수 추적 필드 |
|---|---|
| PredictionSeriesPoint | `observed_at`, `failure_probability`, `status_grade`, `prediction_id` 또는 result/artifact reference, `source_kind` |
| ObservationHistory | envelope의 `source_ref`와 `points[]` |
| ObservationSeriesPoint | `observed_at`, `value`, `quality_status`; source reference는 history envelope가 소유 |
| Baseline | `mean`, `std`, `lower`, `upper`, `reference`, evidence field/source reference |
| EquipmentHistoryRow | `occurred_at`, `kind`, `source`, activity/maintenance reference |

값이 없으면 UI 표시를 위해 합성 series나 임의 baseline을 만들지 않는다. Backend adapter는 빈 배열, null, `evidence.gaps[]`, `data_status.warnings[]`로 unavailable 상태를 표현한다.

### 5.4 DataStatus

| 필드 | 타입 | 필수 | 설명 | 상태 |
|---|---|:---:|---|---|
| `source` | enum | Y | `canonical`, `fallback` 후보 | 제안 |
| `is_stale` | boolean | Y | 현재 Operations는 프론트 observed_at 24시간 정책 | 현행 |
| `is_data_quality_hold` | boolean | Y | ViewModel 품질 보류; Artifact 등급과 별도 | 제안 |
| `last_updated_at` | datetime | N | 응답 생성 또는 적재 기준시각 | 제안 |
| `warnings` | string[] | Y | 데이터 누락·fallback·신선도 경고 | 제안 |

`data_quality_hold`는 Result Artifact의 `status_grade`가 아니다. 데이터 품질 때문에
위험등급 표시를 보류하는 ViewModel 상태이며 `DataStatus` 또는 별도 품질 필드에서
표현한다. 화면은 이를 위험등급보다 우선해 `데이터 확인`으로 표시할 수 있다.

### 5.5 OverviewSummary

| 필드 | 타입 | 필수 | 계산 기준 | 상태 |
|---|---|:---:|---|---|
| `as_of` | datetime | Y | 동일 Artifact snapshot 기준시각 | 제안 |
| `total_asset_count` | integer | Y | Asset 수 | 파생 |
| `operating_asset_count` | integer | Y | 최신 Observation 가동값 | 파생 |
| `non_operating_asset_count` | integer | Y | 전체-가동 | 파생 |
| `status_counts` | object | Y | Artifact 네 위험 등급별 자산 수 | 파생 |
| `data_quality_hold_count` | integer | Y | 위험등급 표시가 보류된 자산 수 | 파생 |
| `asset_type_counts` | object | Y | Compressor/CNC별 자산 수 | 파생 |
| `top_risk_assets` | AssetPredictionSummary[] | Y | 등급 우선, 확률 내림차순 | 파생 |
| `production_cycle_count` | integer | Y | 요청 기간 내 작업 수 | 파생 |
| `maintenance_event_count` | integer | Y | 요청 기간 내 정비 수 | 파생 |
| `data_status` | DataStatus | Y | API 상태 | 제안 |

## 6. 화면 표시 매핑

| 원본 값 | 한국어 표시 | 비고 |
|---|---|---|
| `normal` | 정상 | 색상만으로 표현하지 않음 |
| `attention` | 주의 | `관심`과 혼용하지 않음 |
| `warning` | 경고 | enum 원문 보존 |
| `critical` | 위험 | `심각`과 혼용하지 않음 |
| `data_quality_hold` | 데이터 확인 | ViewModel 품질 상태; Artifact enum 아님 |
| `risk_up` | 위험 증가 요인 | 확정 원인 표현 금지 |
| `risk_down` | 위험 감소 요인 | 보호 효과 단정 금지 |

표시 문구가 바뀌더라도 API enum은 변경하지 않는다.

## 7. Operations 제외 스키마

다음은 현재 Canonical에 없고 멘토링 기준상 Operations 이후 범위다.

- 사용자·로그인·권한·담당 범위
- 알림
- 점검 요청과 점검 결과 입력
- 정비 요청·승인·예정 일정
- 자동 Work Order와 설비 제어
- 모델 재학습 요청

현행 프로토타입의 Decision/Note는 저장·권한·감사 이력이 구현돼 있다. 제외하려면
별도 제품 변경 결정과 코드 영향 분석이 필요하다.

## 8. 결정 상태와 후속 합의 사항

| ID | 담당 | 결정 사항 | 상태 |
|---|---|---|---|
| SCH-DEC-01 | Frontend | 내부 enum과 분리한 Operations 한국어 상태 문구 | 2026-08 Week 2 결정 |
| SCH-DEC-02 | Frontend·Backend | 현행 `offset`/`limit`/`total`과 검색·라인·상태·담당자 필터 | 결정 완료; `page`/`size`는 V2 |
| SCH-DEC-03 | Generator·Backend | Generator score에 Backend threshold 정책을 적용해 위험등급 생성 | 결정 완료 |
| SCH-DEC-04 | Frontend·Backend | 최신 `observed_at` 기준 프론트 24시간 stale Operations 정책 | 결정 완료 |
| SCH-DEC-05 | Generator·Backend | 로컬 compatibility fallback 표시, 비로컬 Model Artifact 누락은 fail-closed | 결정 완료 |
| SCH-DEC-06 | Backend | 현행 Evidence 호환 provenance 유지; JSON Pointer 전환 | V2 검토 |
| SCH-DEC-07 | Report API | 현행 Event Report 입력 범위와 기간 집계 Summary/Detail 범위 | 현행 확정·V2 후속 합의 |
| SCH-DEC-08 | Report API | 현행 grounded report, 근거 참조와 deterministic fallback | 결정 완료; 기간 집계 출력은 V2 |
