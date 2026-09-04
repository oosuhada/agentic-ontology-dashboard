# Production Planning Assumptions

## Purpose

이 문서는 생산관리자 화면과 리포트에서 사용할 `production_plan` / `production_impact`
컨텍스트의 산출 기준을 정의한다. 목표는 생산량을 임의로 고정하지 않고, 현재
데이터셋의 설비 규모와 공개 제조업 벤치마크를 근거로 데모용 생산계획을 계산하는
것이다.

이 값은 고장확률, 위험등급, Top factor, 추천 액션을 산정하는 Evidence가 아니다.
생산계획 컨텍스트는 위험 결과가 생산계획, 납기, 라인 운영에 주는 영향을 설명하는
운영 문맥으로만 사용한다.

## Source Boundary

| 항목 | 사용 기준 | Evidence 사용 여부 |
| --- | --- | --- |
| 설비 수 | `experiments/preventive_intervention/policies/risk-rise-detection-v1.json`의 `distribution_basis.cnc_asset_count = 80` | 운영 규모 산출 기준 |
| 원천 데이터 | UCI AI4I 2020 Predictive Maintenance Dataset | 센서/고장 예측 데이터셋 |
| 제품명 | 원천 데이터에 실제 SKU/품목명이 없으므로 `정밀 가공 부품`으로 일반화 | 운영 표시명 |
| 제품 변형 | AI4I `Type`의 L/M/H | 제품 등급 또는 가공 부하 변형 |
| OEE | discrete manufacturing의 world-class benchmark 85% 계열 | 생산능력 산출 가정 |
| Cycle time | 원천 데이터에 없으므로 명시적 demo assumption | 생산계획 산출 가정 |

UCI AI4I는 synthetic predictive-maintenance dataset이며, 10,000개 row와 센서/고장
관련 feature를 제공한다. AI4I의 `Product ID`와 `Type`은 실제 생산 품목명이나
고객 SKU를 제공하지 않는다.

## Product Context

기본 제품군은 다음처럼 일반화한다.

```json
{
  "product_context": {
    "source_type": "synthetic_demo_context",
    "product_family": "정밀 가공 부품",
    "product_variant": "L",
    "product_grade": "low",
    "basis": "AI4I Product Type L/M/H only; no real SKU name is provided."
  }
}
```

라인별 표시가 필요하면 `정밀 가공 부품`을 유지하되, 화면 표시명만 다음처럼 좁힌다.

| 라인/설비 문맥 | 표시 제품군 |
| --- | --- |
| 가공/CNC/절삭 | 정밀 가공 부품 |
| 프레스 | 금속 성형 부품 |
| 성형 | 성형 부품 |
| 조립 | 조립 부품 |

이 표시명은 실제 고객 품목, 산업별 수주 물량, 납품 계약을 의미하지 않는다.

## Capacity Formula

계획 생산량은 다음 계산식으로 산출한다.

```text
planned_units =
  active_asset_count
  * planned_operating_hours
  * 60
  * oee
  * yield_rate
  / standard_cycle_minutes_per_unit
```

권장 기본값:

| 변수 | 기본값 | 근거/성격 |
| --- | ---: | --- |
| `active_asset_count` | 80 | 현재 데이터셋의 CNC 설비 수 기준 |
| `planned_operating_hours` | 16 | 2교대 x 8시간 demo planning window |
| `oee` | 0.846 | 90% availability x 95% performance x 99% quality |
| `yield_rate` | 0.99 | OEE quality 구성과 중복되지 않도록 별도 적용 시 주의 |
| `standard_cycle_minutes_per_unit` | 4.0 | 명시적 demo assumption |

OEE는 이미 quality factor를 포함하므로, `yield_rate`를 별도 곱할 경우 문서와 화면에서
중복 적용 여부를 명확히 표시해야 한다. 기본 구현에서는 단순화를 위해 다음 중 하나를
선택한다.

1. `oee = 0.846`, `yield_rate = 1.0`
2. `availability = 0.90`, `performance = 0.95`, `yield_rate = 0.99`

두 방식은 같은 의미이므로 동시에 품질 손실을 두 번 반영하지 않는다.

## Baseline Calculation

Operations 기본 산출은 다음 값을 사용한다.

```text
80 assets * 16 hours/day * 60 minutes/hour * 0.846 OEE / 4.0 minutes
= 16,243 units/day
```

따라서 기본 일 생산계획은 `16,200 units/day`로 반올림해 표시한다. 이는 실제 생산량이
아니라 `synthetic_capacity_model` 결과다.

제품 변형별 계획이 필요하면 L/M/H 비중을 AI4I 설명에 맞춰 50/30/20으로 분해한다.

| 제품 변형 | 비중 | 계획 수량 |
| --- | ---: | ---: |
| L | 50% | 8,100 |
| M | 30% | 4,860 |
| H | 20% | 3,240 |
| 합계 | 100% | 16,200 |

## Fixture Shape

Gold event fixture에는 바로 추가하지 않는다. 현재 `input-event.schema.json`은
`additionalProperties: false`이며, Gold fixture는 센서/위험 이벤트 입력 계약으로 유지한다.
생산계획은 별도 operation-context fixture로 관리한다.

현재 세팅:

- Schema: `contracts/schemas/operation-context.schema.json`
- Fixture: `data/fixtures/operation_context/production-planning-context-v1.json`

ViewModel 또는 API projection에 연결할 때는 다음 형태로 노출한다.

```json
{
  "operation_context": {
    "production_plan": {
      "source_type": "synthetic_capacity_model",
      "asset_count_basis": {
        "source": "risk-rise-detection-v1.distribution_basis",
        "cnc_asset_count": 80
      },
      "oee_basis": {
        "source": "discrete_manufacturing_world_class_benchmark",
        "availability": 0.9,
        "performance": 0.95,
        "quality": 0.99,
        "oee": 0.846
      },
      "planning_window": {
        "shift_count": 2,
        "hours_per_shift": 8,
        "planned_operating_hours": 16
      },
      "cycle_time_basis": {
        "source_type": "explicit_demo_assumption",
        "standard_cycle_minutes_per_unit": 4.0,
        "note": "AI4I has sensor and tool-wear signals, not real production takt time."
      },
      "calculated_daily_capacity_units": 16200,
      "product_mix": [
        {"variant": "L", "share": 0.5, "planned_units": 8100},
        {"variant": "M", "share": 0.3, "planned_units": 4860},
        {"variant": "H", "share": 0.2, "planned_units": 3240}
      ]
    }
  }
}
```

## Temporal Consistency

운영 fixture를 별도로 둘 때의 시간 정합성은 Backend composer가 보장한다. Frontend가
event와 operation context를 직접 join하거나 생산량을 재계산하지 않는다.

정합성 규칙:

1. `operation_context.temporal_scope.snapshot_id`를 ViewModel provenance에 남긴다.
2. Event의 `observation.timestamp`는 `temporal_scope.valid_from <= timestamp < valid_to`
   범위 안에 있어야 한다.
3. `production_plan.plan_date`와 `capacity_model.planning_window.plan_date`는
   `temporal_scope`의 영업일과 일치해야 한다.
4. 같은 ViewModel 안의 `plan_summary`, `line_impacts`, `event_impacts`는 동일
   `snapshot_id`에서만 조립한다.
5. 시간 범위가 맞지 않으면 생산 영향은 계산하지 않고 `operation_context_unavailable` gap으로
   표시한다.
6. data-quality hold event는 시간 범위가 맞아도 생산 영향 수치를 만들지 않고
   `withheld_data_quality_hold`로 둔다.

현재 demo fixture의 temporal scope:

```json
{
  "snapshot_id": "OPS-SNAPSHOT-2026-08-01-A-B",
  "timezone": "Asia/Seoul",
  "valid_from": "2026-08-01T00:00:00+09:00",
  "valid_to": "2026-08-02T00:00:00+09:00",
  "generated_at": "2026-08-01T00:00:00+09:00"
}
```

이 snapshot은 `EVT-GS-*` fixture의 `2026-08-01` 관측 이벤트를 위한 demo planning
context다. 다른 날짜의 Event에 재사용하지 않는다.

## History vs Series Naming

현재 Gold/Event fixture의 원천 관측 이력 필드 이름은 `series`가 아니라 `history`다.

```text
data/fixtures/GS-*.json
  -> history

Backend composer
  -> fixture.history를 읽어 feature_series로 변환

AssetDetailViewModel
  -> features[].history.points
```

용어 경계:

| 이름 | 위치 | 의미 |
| --- | --- | --- |
| `history` | `input-event.schema.json`, `data/fixtures/GS-*.json` | 현재 관측 전후의 source observation rows |
| `feature_series` | Backend composer 내부 인자 | `history`를 feature별 그래프 입력으로 변환한 중간값 |
| `features[].history.points` | `AssetDetailViewModel` | 프론트가 그래프로 렌더링하는 ViewModel 필드 |
| `risk_series` | `AssetDetailViewModel` | 센서 이력이 아니라 runtime prediction/Product Result history |

파생값 시계열도 같은 경계를 따른다.

```text
fixture.history 원센서 rows
  -> Backend composer가 row별 파생값 계산
  -> ViewModel features[].history.points에 포함
  -> Frontend는 계산하지 않고 렌더링만 수행
```

따라서 문서와 코드에서 `fixture series`라고 부르지 않는다. fixture는 `history`, 화면용
시계열은 `features[].history.points`로 구분한다. Frontend 내부 adapter가 화면 컴포넌트
편의를 위해 `historyPoints`로 매핑할 수는 있지만, 공식 API 계약 필드명은
`features[].history.points`다.

## Production Impact Calculation

설비 위험 이벤트가 생산계획에 주는 영향은 다음처럼 계산한다.

```text
asset_units_per_hour =
  60 * oee / standard_cycle_minutes_per_unit

estimated_lost_units =
  affected_asset_count * estimated_downtime_hours * asset_units_per_hour
```

예: 설비 1대가 240분 정지될 경우

```text
60 * 0.846 / 4.0 = 12.69 units/hour
1 asset * 4 hours * 12.69 = 50.76 units
```

화면에는 `약 51 units 생산 지연 가능`처럼 표시한다. 이 값은 고장 발생 확정 손실이
아니라, 현재 위험 이벤트가 실제 정지로 이어질 경우의 생산계획 영향 추정치다.

## Screen Information Design

생산계획 fixture는 화면에 다음 질문에 답하기 위한 컨텍스트만 제공한다.

| 화면 | 제공 정보 | 사용하지 않는 것 |
| --- | --- | --- |
| Overview | 일 계획 수량, 위험 이벤트의 총 생산 영향, 우선 확인 라인 | 고장확률 재계산 |
| Objects | 설비별 제품군, 제품 변형, 예상 정지 시 지연 수량 | 센서 Top factor 대체 |
| Operations | 교대/계획 window, 점검 우선순위, data-quality hold 시 영향 미산정 | 자동 WorkOrder/정비 완료 |
| Report | 생산계획 산출 근거, 한계, 생산 영향 문장 | 실제 납기/고객 손실 주장 |

대표 event-impact 판정:

| Event | 화면 우선순위 | 생산 영향 |
| --- | --- | ---: |
| `EVT-GS-004` | `plan_at_risk` | 51 units 지연 가능 |
| `EVT-GS-002` / `EVT-GS-008` | `shift_inspection` | 25 units 지연 가능 |
| `EVT-GS-003` | `shift_inspection` | 32 units 지연 가능 |
| `EVT-GS-005` | `shift_inspection` | 21 units 지연 가능 |
| `EVT-GS-006` | `monitor` | 13 units 지연 가능 |
| `EVT-GS-007` | `data_check_required` | data-quality hold 해소 전 미산정 |
| `EVT-GS-001` | `none` | 정상 상태라 표면화하지 않음 |

## Contract Review

### 아키텍처 리뷰 관점

판정: `Partially Verified`, Architecture Fit: `Pass` for fixture separation.

- Product Result Artifact/Evidence 입력 fixture를 직접 확장하지 않고 별도
  `operation_context` fixture로 분리했다.
- `failure_probability`, `status_grade`, `top_factors`, `recommended_action`을 바꾸지 않는다는
  금지 조건을 schema fixture와 limitations에 명시했다.
- `evaluation_truth`/`hidden_truth`를 사용하지 않는다.
- Frontend는 여러 fixture/API를 직접 조합하지 않고 Backend가 조립한 단일
  `AssetDetailViewModel`을 소비한다는 기존 모델링 원칙을 유지한다.
- 생산계획/정비 overlay/readiness 정보는 별도 화면용 ViewModel로 즉시 분리하지 않고,
  기존 `AssetDetailViewModel`에 optional typed section으로 additive 확장한다.
- `equipment_history[]`는 사람이 읽는 timeline projection으로 유지하고,
  `maintenance_event_id`, `overlay_branch_id`, `history_segment_id`, `runtime_status` 같은
  기계 판독 lineage 필드를 임의로 끼워 넣지 않는다.
- Backend API/ViewModel 연결은 `codex/operation-context-api` 브랜치에서 구현했다.
  화면 제공은 UI 워크트리 반영 전이므로 Frontend delivery는 별도 검증 대상이다.

### 데이터 모델링 계약 관점

판정: `Partially Verified`, Architecture Fit: `Pass` with one open ViewModel extension.

- 생산계획은 `source_type = synthetic_capacity_model`로 표시된다.
- 설비 수는 `risk-rise-detection-v1`의 `cnc_asset_count = 80`을 참조한다.
- OEE와 cycle time은 산출 근거와 assumption을 분리했다.
- data-quality hold event는 생산 영향 수치를 만들지 않고 `withheld_data_quality_hold`로 둔다.
- 별도 화면용 ViewModel schema를 만들지 않고, 기존 Operations consumer ViewModel 흐름에
  `operation_context` typed section을 additive로 붙인다. Frontend 타입은
  `operation_context` summary와 rich production-planning field를 모두 소비하도록 정렬해야 한다.
- 정비 overlay/readiness가 화면에 필요하면 `equipment_history[]`를 확장하지 않고
  `maintenance_context` 또는 runtime-status typed section을 additive로 붙인다.
  이 section의 공식 공개 위치는 Maintenance/Diagnosis/ViewModel 팀 합의 후 schema에 반영한다.
- `operation-context.schema.json`은 화면용 ViewModel이 아니라 Backend composer가 읽는 운영 context
  fixture 계약이다. Frontend가 이 fixture를 직접 파싱하거나 생산량을 재계산하지 않는다.
- 시간 정합성은 Backend composer에서 `event.observation.timestamp`와
  `operation_context.temporal_scope`를 비교해 보장한다.

### Fixture 계약 관점

판정: `Verified` for schema validation, Architecture Fit: `Pass`.

- `operation-context.schema.json`은 `additionalProperties: false`로 운영 context 필드를 고정한다.
- `production-planning-context-v1.json`은 schema validation을 통과했다.
- 기존 `GS-001`~`GS-008` fixture는 변경하지 않았고 기존 `input-event.schema.json` validation을 통과했다.
- 공식 Gold fixture family와 operation context를 결합하려면 `event_id` + `equipment_id`로 join해야 한다.

## Report Wording

권장 문구:

```text
생산계획은 실제 공장 실적이 아니라, 현재 데이터셋의 CNC 설비 수 80대와 discrete
manufacturing OEE benchmark를 기준으로 산출한 synthetic planning context입니다.
이 값은 고장확률 산정에는 사용하지 않고, 생산관리자 화면의 납기/라인 영향도 판단에만
사용합니다.
```

금지 문구:

- 실제 공장 일 생산량
- 실제 고객 납기 영향
- 실제 OEE 검증값
- 정비로 확보된 실제 절감량
- 생산계획이 고장확률을 개선/악화시켰다는 인과 주장

## Implementation Notes

- ViewModel은 하나의 `AssetDetailViewModel` 소비 계약을 유지한다.
- `production_plan`은 `operation_context` 또는 `production_impact` 하위에 둔다.
- 정비 lineage/readiness는 `maintenance_context` 또는 runtime-status typed section 하위에 둔다.
- `equipment_history[]`에는 사용자가 읽는 정비/점검 timeline 문장만 둔다.
- `EvidencePackage`, `ProductResultArtifact`의 위험도/확률/Top factor 계산에는 넣지 않는다.
- optional context가 없으면 `근거 부족` 또는 unavailable로 표시하고 0, normal, 평균값으로 채우지 않는다.
- `evaluation_truth`나 failure-mode hidden truth를 생산계획 산출에 사용하지 않는다.
- 실제 MES/ERP/APS 연동 전까지 모든 생산계획 값은 `synthetic_capacity_model`로 표시한다.

## Maintenance Overlay Assumption

정비 이력은 기존 canonical `history` row에 임의로 끼워 넣지 않는다. 정비 완료 후 관측은
Source Runtime에서 분기된 `maintenance_replay_overlay` observation으로 수집하고, 기존
Gold fixture/history는 불변으로 둔다.

정비 overlay의 기본 흐름:

```text
maintenance.started
  -> 대상 설비 canonical 출력 제외
  -> source runtime snapshot에서 overlay branch 생성

maintenance.completed
  -> 허용된 state_patch만 overlay branch에 적용
  -> Operations 기준 TOOL_REPLACEMENT는 tool_wear_min reset -> 0 min

maintenance.replay_requested
  -> restart_at부터 post-maintenance observation 생성
  -> history_segment_id가 다른 정비 후 시계열로 취급
```

계약 경계:

- gen_data는 `runtime_overlay.observations.available`까지 제공한다.
- gen_data는 Model Artifact, `history_requirement`, inference-ready 판단, Runtime Prediction,
  Product Result/Evidence, 정비 성공/정상화 판정을 생성하지 않는다.
- Backend composer는 overlay observation을 읽어 정비 전/정비 gap/정비 후 segment를 구분하고,
  history 충분 여부와 재예측 가능 여부를 별도로 판단한다.
- Frontend는 overlay JSONL을 직접 읽지 않고, Backend ViewModel/API가 조립한
  `features[].history.points`, `equipment_history`, `risk_series` 또는 후속 overlay section만 렌더링한다.

시간 정합성 요구:

- `maintenance_started_at <= maintenance_completed_at <= restart_at` 순서를 보장한다.
- `maintenance.started`는 실제 source runtime의 해당 시점 snapshot과 결합되어야 한다.
- `maintenance_started_at`이 현재 source virtual clock보다 미래인 이벤트는 해당 tick까지
  pending 처리한 뒤 snapshot을 생성해야 한다.
- `maintenance_started_at`이 이미 지난 late event는 대상 설비 canonical row 오염 가능성이
  있으므로 reject 또는 quarantine 대상으로 본다.
- 정비 gap 동안 대상 설비의 canonical/source observation은 생성하지 않는다.
- 정비 후 overlay observation은 기존 `history`와 같은 segment로 병합하지 않고 별도
  `history_segment_id`를 유지한다.

UI 표현 경계:

- 표시 가능: `정비 후 관측 수집 중`, `재예측 대기`, `history 부족`, `정비 후 시계열 segment 존재`.
- 금지: 정비 효과, 운영 성과, 생산 개선이 입증된 것처럼 보이는 표현.
- 생산 KPI 실적 산출은 실제 생산량, downtime, 정비 완료 결과, 재예측 결과가 연결되기 전까지
  후순위 backlog로 둔다.

## Backlog

### 후순위: 파생값 시계열 그래프

파생값 시계열 그래프는 후속 구현으로 둔다. 현재 계획서 기준에서는 구현하지 않고,
fixture 보강, Backend ViewModel 조립, UI 렌더링 요구사항만 명시한다.

대상 파생값:

| 파생값 | 계산식 | 화면 의미 |
| --- | --- | --- |
| `temperature_difference_k` | `process_temperature_k - air_temperature_k` | 열 발산/온도 차이 추세 |
| `mechanical_power_w` | `torque_nm * rotational_speed_rpm * 2π / 60` | 부하 상승 추세 |
| `overstrain_index` | `torque_nm * tool_wear_min` | 토크와 공구마모의 복합 과부하 추세 |

구현 순서:

1. Fixture 보강
   - Gold/Event fixture의 원천 필드는 계속 `history`로 유지한다.
   - `history` row에 파생값을 직접 저장할지, Backend composer가 row별 계산할지는 별도 결정한다.
   - 기본 방향은 원센서 `history`를 source of truth로 두고, 파생값은 Backend composer에서 계산한다.

2. Backend ViewModel 조립
   - `fixture.history`의 각 row에 동일한 파생 공식 `derive_features()`를 적용한다.
   - 계산된 파생값은 기존 `AssetDetailViewModel.features[].history.points`에 포함한다.
   - Frontend가 `temperature_difference_k`, `mechanical_power_w`, `overstrain_index`를 직접 계산하지 않는다.
   - 계산 불가 row가 있으면 `value: null`, `quality_status: "bad"` 또는 evidence gap으로 표시한다.

3. UI 반영
   - 기존 설비 상세/리포트 화면의 feature graph 영역에 파생값 3종을 추가한다.
   - 원센서 그래프와 파생 지표 그래프를 구분해서 표시한다.
   - 그래프 라벨은 현장관리자/엔지니어가 이해할 수 있게 `부하 지표`, `복합 과부하`, `온도 차이`처럼 표시한다.
   - 그래프는 고장 확정 근거가 아니라 위험 판단을 설명하는 보조 추세로 표현한다.

정합성 규칙:

- `history`는 원천 fixture 필드이고, `features[].history.points`는 ViewModel 필드다.
- `risk_series`와 혼동하지 않는다. `risk_series`는 runtime prediction/Product Result history다.
- 파생값 시계열이 없다고 프론트에서 임의 보간하거나 생성하지 않는다.
- 파생값 그래프는 Product Result/Evidence의 위험도, 확률, Top factor를 수정하지 않는다.

### 후순위: 예방 점검 생산영향 KPI

예방 점검으로 인해 생산량이 얼마나 개선됐는지 보여주는 KPI는 후순위로 둔다. 현재
데이터와 fixture만으로는 실제 생산 개선, 실제 납기 방어, 실제 설비효율 개선을 실적 KPI로
주장할 수 없다.

후속 구현에서 허용할 수 있는 범위는 다음처럼 `synthetic_scenario_estimate`로 제한한다.

```json
{
  "kpi_type": "synthetic_prevention_impact",
  "event_id": "EVT-GS-004",
  "action": "preventive_inspection_assumed",
  "estimated_downtime_avoided_minutes": 240,
  "estimated_protected_units": 51,
  "evidence_level": "synthetic_scenario_estimate",
  "actual_performance_claim_allowed": false
}
```

후속 작업 전제:

- 점검 전 위험 이벤트와 예방 점검 수행 기록을 분리한다.
- 실제 downtime, 실제 생산량, 계획 대비 실적, 제품 mix, 교대 window가 확보되기 전까지
  `실적 개선`으로 표현하지 않는다.
- 화면 문구는 `생산량을 올렸다`가 아니라 `생산 지연 가능성을 방어한 것으로 추정`으로 제한한다.
- Product Result/Evidence의 고장확률이나 위험등급을 KPI 산출 결과로 수정하지 않는다.

## References

- UCI Machine Learning Repository, AI4I 2020 Predictive Maintenance Dataset:
  https://archive.ics.uci.edu/dataset/601/ai4i
- OEE.com, World-Class OEE:
  https://www.oee.com/world-class-oee/
