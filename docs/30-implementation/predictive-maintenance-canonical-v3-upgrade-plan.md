# Predictive Maintenance Canonical v3.1 Upgrade Plan

- 작성일: 2026-08-04
- 대상 애플리케이션: `mvp-프로젝트2` / Ontology Dashboard
- 기존 구현 기준: Predictive Maintenance Canonical v2 Phase 0~2
- 새 데이터 패키지: `/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1`
- 적용 범위: 기존 Phase 0~2의 계약·Adapter·PostgreSQL 적재를 보존하면서 Phase 3 시작 전에 V3.1 호환 bridge를 추가하고, 이후 Ontology·Graph·Replay·Visualization·Dashboard·Governance를 V3.1 의미 계약에 맞게 구현한다.

---

## 1. 현재 Git 및 구현 기준

현재 branch에는 다음 단계가 완료되어 있다.

| Phase | 커밋 | 상태 |
|---:|---|---|
| 0 | `1aa0251` | Bundle Manifest와 identity 계약 고정 |
| 1 | `4b4d46f` | V2 bundle Adapter와 streaming validation |
| 2 | `01a4a9b` | PostgreSQL COPY 기반 원자적 적재 |

Phase 0~2는 폐기하지 않는다. V3.1은 기존 Dataset Version을 수정하는 데이터 교체가 아니라 **새 checksum과 새 source version을 가진 별도 Dataset Version**으로 등록한다.

```text
V2 Dataset Version
canonical-independent-v1.0
        │ 보존
        ▼
V3.1 Dataset Version
canonical-ai4i-physics-v3.1
```

V2와 V3.1을 같은 Dataset 안의 서로 다른 immutable Dataset Version으로 유지해야 lineage, 비교, rollback, 재현성이 보존된다.

---

## 2. V3.1에서 달라진 계약

### 2.1 Canonical source schema

다음 6개 runtime source의 파일 역할과 컬럼 schema는 V2와 호환된다.

- `asset_master.csv`
- `asset_relation.csv`
- `compressor_sensor_observation.csv`
- `cnc_sensor_observation.csv`
- `cnc_production_cycle.csv`
- `maintenance_event.csv`

하지만 센서값, production/maintenance row count, checksum, generator version이 달라졌다. V2 파일을 V3.1 파일로 덮어쓰거나 같은 Dataset Version으로 merge하면 안 된다.

### 2.2 Dataset source contract 확장

V3.1 `dataset_manifest.json`에는 기존 source contract 외에 다음 필드가 추가됐다.

```text
cnc_ai4i_physical_relations: true
failure_modes_satisfy_sensor_conditions: true
asset_variability_policy: small_offsets_plus_time_varying_physical_process
```

현재 프로젝트2의 `PredictiveMaintenanceSourceContract`는 `extra="forbid"`이므로 V3.1 manifest를 그대로 읽으면 실패한다. 실제 확인된 오류는 다음 세 필드의 `extra_forbidden`이다.

따라서 Phase 3의 첫 작업은 Ontology materialization이 아니라 **V3.1 contract compatibility bridge**다.

호환 정책:

- 기존 V2 필드는 그대로 필수 유지
- V3.1 필드는 optional/default로 추가하되 값이 선언되면 의미 검증
- 알 수 없는 임의 필드는 계속 거부
- bundle checksum canonicalization에 V3.1 필드가 포함되어야 함
- V2 checksum 재계산 결과는 기존과 동일해야 함

### 2.3 AI4I 물리 계약

V3.1 canonical manifest에는 다음 물리 계약이 포함된다.

```text
power_w = torque_nm * rotational_speed_rpm * 2*pi/60
temperature_gap_k = process_temperature_k - air_temperature_k
overstrain_load = tool_wear_min * torque_nm
```

Failure condition:

```text
PWF: power_w < 3500 or power_w > 9000
HDF: temperature_gap_k < 8.6 and rotational_speed_rpm < 1380
OSF: overstrain_load > product type threshold
TWF: tool_wear_min between 200 and 240
RNF: condition-independent random failure
```

이 계약은 Dataset Version의 schema/profile/governance metadata로 등록한다. `evaluation_truth`를 runtime table, Ontology property, Agent evidence, Dashboard 데이터로 노출해서 조건을 증명하면 안 된다.

Runtime에서는 canonical observation으로 계산 가능한 `power_w`, `temperature_gap_k`, `overstrain_load`, threshold margin만 query-time derived measure로 제공한다.

### 2.4 Result Artifact 추가

V3.1은 기존 prediction 파일 외에 다음 공통 결과 산출물을 추가한다.

```text
canonical/model_outputs/result_artifact.jsonl
```

주요 필드:

```text
artifact_id
artifact_type
schema_version
asset_id
asset_type
observed_at
prediction_horizon_hours
prediction_task
failure_probability
predicted_failure_type
status_grade
confidence
top_factors
recommended_action
provenance
```

현재 Phase 1 Adapter와 Phase 2 ingestion은 이 역할을 모른다. Phase 3 시작 시 다음을 additive migration으로 보완한다.

- `result_artifact` bundle role
- checksum/schema/cross-file validation
- `pm_result_artifacts` 또는 동일 책임의 typed repository
- 100개 자산 coverage와 snapshot prediction identity 연결
- 기존 V2 bundle은 result artifact가 없어도 계속 검증·조회 가능

Result Artifact는 대시보드·에이전트·보고서가 우선 소비할 제품 계약이다. 내부 `prediction_snapshot`과 `prediction_factor`는 compatibility와 세부 provenance를 위해 유지한다.

### 2.5 Prediction type 의미

V3.1 모델은 `binary_failure_within_horizon` 모델이다.

```text
predicted_failure_type = failure_risk | no_significant_risk
```

PWF, HDF, OSF, TWF를 예측하는 multiclass 모델이 아니다. Runtime Ontology, Graph, Dashboard, Agent가 `predicted_failure_type`을 AI4I failure mode처럼 표시하면 안 된다.

### 2.6 Optional agent benchmark

V3.1 optional experiment는 다음 case를 포함한다.

```text
positive_upstream_relation  16
negative_local_only          4
```

Negative 정답 계약:

```json
{
  "candidate_upstream_asset_id": null,
  "relation_type": "NO_UPSTREAM_RELATION",
  "claim_status": "unlikely"
}
```

이 experiment는 canonical runtime bundle에 포함하지 않는다. 별도 evaluation artifact로 등록하거나 Phase 8 release benchmark에서만 사용한다.

- `hidden_truth/`는 evaluator-only
- smoke example case는 formal score에서 제외
- `SUPPLIES_AIR_TO` topology를 causal truth로 해석하지 않음
- negative case에서 상류 압축기를 무조건 지목하는 전략을 실패 처리

---

## 3. V3.1 기준 row count

30일, seed 42, `balanced_demo` 기준:

| 역할 | V3.1 행 수 |
|---|---:|
| assets | 100 |
| relations | 80 |
| compressor observations | 86,400 |
| CNC observations | 345,600 |
| production cycles | 170,875 |
| maintenance events | 790 |
| prediction snapshots | 100 |
| prediction factors | 300 |
| prediction timeline | 68,208 |
| result artifacts | 100 |

기존 V2의 production 170,860, maintenance 795, timeline 68,211을 V3.1 완료 조건으로 사용하지 않는다.

---

## 4. 수정된 Phase 구조

## Phase 3 — V3.1 Compatibility Bridge and Ontology Materialization

Phase 3은 두 개의 완료 gate로 나눈다.

### Gate A: V3.1 package compatibility

- source contract V2/V3.1 version-aware validation
- result artifact role 추가
- additive PostgreSQL migration과 repository/COPY path
- V3.1 package를 새 Dataset Version으로 ingestion
- V2 Dataset Version 불변 및 기존 test regression 확인
- V3.1 package의 `validate_package.py` 결과와 checksum을 ingestion artifact에 기록
- `tool_wear_continuity.pass=true`와 replacement/reset 1:1 정렬을 ingestion gate로 기록

### Gate B: Ontology materialization

- Site, ProductionCell, Equipment
- RiskAssessment/PredictionResult는 Result Artifact를 기준으로 materialize
- MaintenanceEvent를 WorkOrder/MaintenanceAction workflow와 연결
- `recommended_action`은 정책 추천이며 자동 WorkOrder 생성 금지
- raw observations와 prediction timeline point는 object로 만들지 않음
- AI4I contract는 Dataset Version/schema metadata로 노출
- failure truth와 `condition_variant`는 runtime lineage에 포함하지 않음

## Phase 4 — Neo4j Projection via Project 3

- V3.1 Dataset Version identity와 result artifact provenance를 typed batch에 포함
- `SUPPLIES_AIR_TO`는 topology edge로만 projection
- Result Artifact는 RiskAssessment/PredictionResult node 또는 property로 projection
- 모든 raw observations/timeline point와 optional experiment hidden truth는 graph에 넣지 않음
- graph answer가 topology만으로 인과를 확정하지 않도록 provenance와 relation semantics 반환

## Phase 5 — Result Artifact and Replay Vertical

- Result Artifact를 latest product result의 우선 API contract로 사용
- 기존 PredictionResult repository와 deterministic identity 연결
- snapshot/factor API는 compatibility와 drill-down 용도
- timeline 68,208행을 historical replay source로 사용
- query-time AI4I derived measures 지원
- seek 시 모델 재학습 금지, evaluation truth 접근 금지

## Phase 6 — AI4I-Aware Semantic Visualization Planner

- canonical 센서 unit과 semantic role 등록
- `power_w`, `temperature_gap_k`, `overstrain_load`를 allowlisted derived measure로 등록
- Result Artifact의 `status_grade`, `recommended_action.priority`, probability, confidence 등록
- `predicted_failure_type`은 binary class로 명시
- runtime에서 `site × PWF/HDF/...` heatmap 추천 금지
- 대신 `site × status_grade`, risk distribution, power threshold, rpm/torque, temperature gap, wear/torque 관계를 추천

## Phase 7 — V3.1 Dataset-Driven Dashboard

- Manager: status grade, probability, recommended action, site/cell risk
- Engineer: sensor trend와 물리 derived measure, factor, maintenance, replay
- Data Scientist: AI4I profile, model task/version, confidence, physical validation summary
- FDE/Admin: V2/V3.1 version lineage, checksum/schema diff, source contract, projection readiness
- recommended action을 자동 실행된 action으로 표시하지 않음
- failure mode multiclass처럼 표시하지 않음

## Phase 8 — V3.1 Governance and Release

- V2와 V3.1 Dataset Version lineage와 rollback 검증
- V3.1 package `ai4i_physics.pass`와 `tool_wear_continuity.pass`를 release evidence로 등록
- source checksum과 Result Artifact/model contract 결합 검증
- evaluation truth/experiment hidden truth leakage negative tests
- positive 16 + negative 4 Agent benchmark, false-upstream-claim test, maintenance evidence canonical matching
- smoke example case를 formal score에서 제외
- 최종 V3.1 row count, API, graph, replay, planner, dashboard provenance 검증

---

## 5. Phase 0~2에서 유지할 것과 보완할 것

### 유지

- Dataset Bundle Manifest v2 envelope
- path/order-independent bundle checksum
- evaluation truth runtime 차단
- PostgreSQL operational source of truth
- COPY staging/merge와 atomic transaction
- Dataset Version checksum identity
- RLS와 project/workspace isolation
- raw observation typed fact table

### Phase 3에서 additive 보완

- V3.1 source contract optional fields
- package validation artifact metadata
- result artifact role와 storage
- V3.1 row count verifier
- V2/V3.1 compatibility tests
- tool-wear continuity와 maintenance-evidence validation artifact

기존 migration `0011_predictive_maintenance_domain_pack.sql`을 수정해 이미 적용된 환경을 깨지 말고, 새 번호의 additive migration을 사용한다.

---

## 6. V3.1 완료 기준

```text
V3.1 package validation
→ V3.1 bundle manifest/checksum
→ V2와 다른 새 Dataset Version
→ 6 canonical source + 4 model/result artifacts ingestion
→ Result Artifact 기반 latest product result
→ Ontology materialization
→ Project 3 / Neo4j projection
→ PostgreSQL replay
→ AI4I-aware semantic visualization
→ 역할별 Dashboard
→ V2/V3.1 lineage, tool-wear continuity, negative-control release verification
```

최종 결과 어디에서도 다음을 주장하면 안 된다.

- topology edge가 인과관계 정답이라는 주장
- binary `predicted_failure_type`이 PWF/HDF/OSF/TWF 분류라는 주장
- recommended action이 승인·실행된 WorkOrder라는 주장
- evaluation truth 또는 hidden truth가 사용자 evidence라는 주장
