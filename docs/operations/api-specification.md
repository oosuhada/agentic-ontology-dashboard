# Operations API 명세서

## 1. 기준과 상태

이 문서는 목표 REST 계약안이다. 현행 API는
[현행 Operations 구현 계약 기준선](./current-operations-implementation-baseline.md)을 따르며, 아래
`/overview`, `/objects`, `/operations`와 page/size 계약은 모두 `변경 제안`이다.
JSON key 목표안은 [스키마 정의서](./schema-definition.md)를 따른다.

책임 분리:

- 팀원3: `/overview`, `/objects`, `/operations` 등 조회·집계 API와 ReportInput에
  필요한 원천·집계 필드 제공
- 팀원4: 현행 Event Report 및 V2 `/reports/executive` 리포트 API 계약·구현
- 팀원2: API·스키마·리포트 계약 문서화와 추적성 관리

> 이 문서는 Backend 제품 API 계약이다. Generator daemon의 내부 학습 API는 Generator 내부
> 운영 계약을 따른다. Generator 내부 API는 외부 제품
> prediction API가 아니며, `/health`, `/internal/train`, `/internal/retrain`과 같은 학습 운영
> 엔드포인트만 제공한다. 상세 허용/금지 범위는
> `docs/architecture-decisions/ADR-002-training-runtime-prediction-ownership.md`를 따른다.

## 1.1 현행 API 계약

Canonical base path:

```text
/api/projects/{project_id}/workspaces/{workspace_id}/predictive-maintenance
```

| Method | Path | 상태 |
|---|---|---|
| GET | `/dashboard` | 현행 구현 |
| GET | `/results/latest` | 현행 구현 |
| GET | `/api/events/{event_id}/evidence` | 현행 구현 |
| POST | `/api/events/{event_id}/report` | 현행 구현 |
| POST | `/api/events/{event_id}/decision` | 현행 구현 |
| POST | `/api/events/{event_id}/notes` | 현행 구현 |
| GET | `/api/events/{event_id}/activity` | 현행 구현 |

`/results/latest`는 `offset`, `limit`, `total`을 사용하며 `limit` 기본값은 100,
최대값은 500이다.

변경 제안 base path: `/api`

## 2. 공통 Query

아래 Query는 현행 설명이 아닌 변경 제안이다.

현재 Operations Objects는 검색·라인·상태·담당자 필터와 현행 URL 상태를 유지한다. 아래
site/cell/유형/기간 Query는 Target이며 이번 주 필수 변경이 아니다.

| Parameter | 타입 | 설명 |
|---|---|---|
| `site_id` | string | 사이트 필터 |
| `cell_id` | string | 셀 필터 |
| `asset_type` | enum | `compressor`, `cnc` |
| `status_grade` | enum | 네 위험 등급 |
| `data_quality_hold` | boolean | ViewModel 품질 보류 필터; 위험 enum과 별도 |
| `from` | datetime | 기간 시작 |
| `to` | datetime | 기간 종료 |
| `page` | integer | 기본 1 |
| `size` | integer | 기본 20, 최대값 합의 필요 |

## 3. Endpoint

아래 Endpoint는 현행 경로 대체 또는 호환 계층이 필요한 변경 제안이다.

| Method | Path | 목적 | 화면 |
|---|---|---|---|
| GET | `/overview` | 전체 설비·위험·운영 요약 | Overview |
| GET | `/objects` | 설비 목록 | Objects |
| GET | `/objects/{asset_id}` | 설비 상세 | Objects |
| GET | `/objects/{asset_id}/observations` | 센서 추세 | Objects |
| GET | `/objects/{asset_id}/maintenance` | 정비 이력 | Objects |
| GET | `/operations` | 생산·정비 요약 | Operations |
| GET | `/operations/production` | 생산 작업 목록 | Operations |
| GET | `/operations/maintenance` | 정비 이력 목록 | Operations |
| POST | `/reports/executive` | 보고서 생성 | Executive Report |

채택 전에는 현행 API를 유지한다. 채택 시 호환 계층·호출부·테스트 전환 계획을
함께 정의한다.

## 4. 응답 계약

### 4.1 목록 envelope

```json
{
  "items": [],
  "page": 1,
  "size": 20,
  "total": 100,
  "as_of": "2026-08-29T23:00:00+09:00",
  "data_status": {
    "source": "canonical",
    "is_stale": false,
    "last_updated_at": "2026-08-29T23:00:00+09:00",
    "warnings": []
  }
}
```

### 4.2 `GET /overview`

응답: `OverviewSummary`. 등급 합과 가동 합 불변식을 만족해야 한다.

현행 Overview는 `/dashboard` 응답으로 위험 KPI·Downtime·판단 대기 Event를
구성한다. `/overview`와 가동·생산·정비 집계는 V2 변경 제안이다.

### 4.3 `GET /objects`

응답 items: `AssetPredictionSummary[]`.

기본 정렬: 위험 등급 우선 후 `failure_probability desc`, `asset_id asc`.

현행 Objects는 `/results/latest`의 offset/limit 결과를 검색·라인·상태·담당자로
클라이언트 필터링한다. site/cell/유형/기간 Query는 V2 변경 제안이다.

### 4.4 `GET /objects/{asset_id}`

응답: `AssetDetail`.

```json
{
  "asset": {},
  "latest_observation": null,
  "prediction": null,
  "relations": [],
  "maintenance_events": [],
  "data_status": {}
}
```

없는 값을 임의 객체로 채우지 않는다.

### 4.5 `GET /objects/{asset_id}/observations`

필수 Query: `from`, `to`. 선택 Query: 반복 가능한 `sensor`.

```json
{
  "asset_id": "CNC-S01-L01-01",
  "asset_type": "cnc",
  "from": "2026-08-29T17:00:00+09:00",
  "to": "2026-08-29T23:00:00+09:00",
  "observations": []
}
```

설비 유형에 존재하지 않는 센서 key는 400으로 처리한다.

### 4.6 `GET /objects/{asset_id}/detail-view`

상태: Operations 현행 소비 계약. 현행 Event Report API를 대체하지 않고, Asset Detail/Overview UI가 같은 snapshot을 읽는 composition endpoint로 사용한다.

응답: `AssetDetailViewModel`.

계약 객체명에는 구현 네임스페이스 접두어를 붙이지 않는다. 현행 프론트엔드의
`Operations*` 타입명은 기존 Operations 화면 구현명으로만 참고하고, Product API 계약명은
`AssetDetail`, `AssetDetailViewModel`처럼 도메인 객체명으로 표기한다.

설비 상세 화면, 피쳐별 센서 그래프, 위험도 그래프, evidence gap 표시를 위한 composition endpoint다. Backend adapter가 Product Result Artifact/Evidence, Backend Observation read contract와 Feature Executor result, Backend Diagnosis Runtime Prediction History Query Contract, Activity/Maintenance source를 병합한다.

필수 Query: 없음. 선택 Query: `project_id`, `dataset_version_id`.

```json
{
  "asset": {
    "criticality": "high",
    "criticality_basis": ["equipment master"],
    "criticality_source": "equipment_master"
  },
  "risk": {},
  "risk_series": [],
  "features": [
    {
      "key": "rotation_raw",
      "current": {"observed_at": "2026-08-01T00:00:00+09:00", "value": 1820.0, "quality_status": "good"},
      "history": {"source_ref": "observation://asset/rotation_raw", "points": []}
    }
  ],
  "equipment_history": [],
  "maintenance_context": {
    "last_maintenance_days_ago": null,
    "similar_events_30d": null,
    "open_work_order_exists": null
  },
  "operation_context": {
    "load_level": null,
    "runtime_hours_7d": null,
    "production_impact": "medium",
    "context_id": "production-planning-context-v1",
    "source_type": "synthetic_capacity_model",
    "temporal_scope": {
      "snapshot_id": "OPS-SNAPSHOT-2026-08-01-A-B",
      "timezone": "Asia/Seoul",
      "valid_from": "2026-08-01T00:00:00+09:00",
      "valid_to": "2026-08-02T00:00:00+09:00",
      "generated_at": "2026-08-01T00:00:00+09:00"
    },
    "production_plan": {
      "plan_id": "PLAN-2026-08-01-GS-DEMO",
      "plan_date": "2026-08-01",
      "planned_units": 16200,
      "product_mix": [{"variant": "M", "share": 0.3, "planned_units": 4860}]
    },
    "capacity_model": {
      "active_asset_count": 80,
      "planned_operating_hours": 16,
      "oee": 0.846,
      "standard_cycle_minutes_per_unit": 4.0,
      "asset_units_per_hour": 12.69,
      "daily_capacity_units": 16200,
      "basis": "80 assets, 16h/day, OEE 0.846, cycle 4.0min 기준"
    },
    "event_impact": {
      "event_id": "EVT-GS-002",
      "equipment_id": "CNC-S04-L04-01",
      "line": "S04-L04",
      "product_variant": "M",
      "screen_priority": "shift_inspection",
      "impact_status": "estimated",
      "estimated_lost_units": 25,
      "basis": {
        "estimated_downtime_minutes": 120,
        "asset_units_per_hour": 12.69,
        "formula": "120 / 60 * 12.69"
      }
    },
    "limitations": ["Estimated lost units are planning impact estimates, not confirmed downtime or realized production loss."]
  },
  "review_priority": null,
  "closed_loop": {
    "work_orders": [],
    "maintenance_actions": [],
    "maintenance_events": [],
    "activities": [],
    "available_actions": [],
    "runtime_status": null
  },
  "evidence": {
    "artifact_id": null,
    "source_kind": "runtime_inference",
    "gaps": []
  },
  "data_status": {}
}
```

`features[].history.points`는 Backend canonical/overlay Observation read contract와 Backend
Feature Executor result에서 파생한다. 같은 history가 공유하는 provenance는
`features[].history.source_ref` envelope에 한 번만 두며, point에는 시간·값·품질만 둔다. `systems/generator`는 Feature/Label 의미, History Requirement,
transform contract, Model Artifact publish를 소유하지만, Product API가 소비하는 제품 runtime
series를 publish하지 않는다. Product API 계약은 `gen_data` 내부 파일명이나 canonical CSV를 직접
의존하지 않는다.
`risk_series`는 Backend Diagnosis Runtime Prediction History Query Contract에서 파생해야 한다.
현재 canonical source는 Backend Diagnosis가 생성한 `pm_result_artifacts`의 asset별 append-only
Product Result history다. 상세 payload가 실제로 필요한 경우에만 `prediction_result_id`로
`prediction_results`를 조회한다. public Product API는 내부 테이블 shape를 직접 노출하지 않는다.
`pm_prediction_timeline`, `gen_data`의 `model_outputs/prediction_timeline.jsonl` 또는 legacy
`precomputed_prediction_timeline`을 최신 운영 결과처럼 직접 읽어 대체하지 않는다.

기존 Operations 상세 화면이 이미 소비하는 필드(asset, 현재 risk/status/action, 현재 센서값,
top factors, report section, provenance)는 기준선으로 유지한다. `map-report`
이식에 필요한 그래프·피쳐 이력 필드는 이 기준선에 추가되는 필드이며, 단일 Event
Evidence만으로 채울 수 있다고 가정하지 않는다.

`asset.criticality`는 설비/프로젝트 운영 영향도이며 `risk.status_grade`나
WorkOrder priority가 아니다. 누락 시 `null`로 두고 `evidence.gaps[]`에
`asset.criticality` gap을 남긴다. `maintenance_context`, `operation_context`,
`review_priority`도 같은 규칙을 따른다. `review_priority`는 검토 표시 순서용 설명값이며
필수 입력이 없으면 `null`이다. Product API 또는 Backend composer가 계산하지 않은 값을
Frontend가 `normal`, `low`, `false`, `0` 또는 fallback priority로 합성하지 않는다.

근거 추적을 위해 시계열 history envelope에는 source reference를, point에는 `observed_at`과
quality/status 정보를 보존한다. 화면 표시용 `number[]`만 반환하지 않는다.

없는 값은 합성하지 않고 null, 빈 배열, `evidence.gaps[]`, `data_status.warnings[]`로 표현한다.

`operation_context`는 optional typed section이다. Backend composer가 별도
`operation-context` fixture/API source를 Event 관측 시각과 Project scope로 검증한 뒤
붙인다. 이 값은 생산계획/생산영향 표시용 문맥이며 Product Result/Evidence의
`failure_probability`, `status_grade`, `top_factors`, `recommended_action`을 변경하지 않는다.

### 4.7 Operations

`GET /operations`는 같은 필터의 생산·정비 목록 합계와 일치하는 요약을 반환한다.
생산 행의 위험 등급은 `cnc_asset_id`와 동일 snapshot Artifact를 결합한 파생값이다.

### 4.8 `POST /reports/executive`

현행은 `POST /api/events/{event_id}/report`에서
`ReportRequest(role, locale, use_llm)`와 role-aware grounded report를 사용한다.

`POST /reports/executive`는 [리포트 정의서](./report-specification.md)의 V2
`ReportInput`/`ReportOutput` 후보이며 현행 API를 대체하지 않는다. 이번 단계에서는
팀원4가 담당하며, 이번 단계에서는 endpoint를 수정·구현하지 않고 mock 입력과
deterministic 출력 계약부터 검증한다.

## 5. 오류 envelope

```json
{
  "error": {
    "code": "invalid_filter",
    "message": "요청 조건을 확인하십시오.",
    "details": []
  }
}
```

| HTTP | code | 조건 |
|---:|---|---|
| 400 | `invalid_filter` | enum·기간·센서 오류 |
| 404 | `asset_not_found` | 자산 없음 |
| 409 | `snapshot_mismatch` | 기준 snapshot 불일치 |
| 422 | `contract_validation_failed` | 응답·보고서 계약 오류 |
| 503 | `canonical_unavailable` | Canonical 사용 불가, fallback 미허용 |
| 503 | `report_generation_unavailable` | 모든 보고서 생성 방식 실패 |

## 6. 출처·버전 계약

- 목록은 `as_of`, `data_status`를 포함한다.
- 상세은 Result Artifact의 원본 `provenance`를 보존한다.
- `site_id`, `cell_id`는 Asset 결합 필드다.
- fallback 사용 시 `source=fallback`과 warning을 반환한다.
- evaluation truth를 반환하지 않는다.
- 현재 Operations stale은 timezone을 포함한 `observed_at` 기준 프론트 24시간 판정을
  유지한다. 이는 도메인 불변값이 아니라 현재 Operations freshness 정책이다.
- provenance는 구조화해 보존하되 `source_field`는 현행 Evidence 호환 형식을
  사용한다. JSON Pointer는 구현 비교 후 Target으로 검토한다.

## 7. 결정 반영과 후속 확인

### 2026-08 Week 2 결정 기록

- 현행 `/dashboard`, `/results/latest`와 Event API를 유지한다.
- Closed-loop 확장은 기존 Event API key를 삭제·rename하지 않는 additive extension으로 유지하며,
  역할별 Action과 mutation 응답은
  [`../closed-loop-product-consumption-contract.md`](../closed-loop-product-consumption-contract.md)를 따른다.
- 점검→정비 판단의 canonical command/read API는
  `/api/projects/{project_id}/workspaces/{workspace_id}/maintenance` 아래에 둔다. 점검 요청·승인과
  Operations manual 추천·판단은 `process_manager`, 점검 시작·결과 기록은 `process_engineer`가
  수행한다. 모든 mutation은 `Idempotency-Key`를 요구한다.
- `GET .../maintenance/events/{event_id}/lineage`는 Product Result/Evidence source ID,
  inspection WorkOrder/Result, Operations manual recommendation, 두 번째 RecommendationDecision,
  maintenance WorkOrder와 `activities[].work_type`을 반환하는 canonical 운영 lineage 위치다.
- 정비 후 Runtime Overlay의 Target 상태는 `equipment_under_maintenance`, `warming_up`,
  `history_insufficient`, `ready`, `predicted`를 사용한다. 기존 Result의 `status_grade`를
  이 준비 상태로 덮어쓰지 않는다.
- Runtime Overlay readiness는 Backend Diagnosis가 현재 Model Artifact의
  `history_requirement.json`으로 결정한다. `gen_data`는 Overlay Observation을 지속
  생성하고 availability를 알릴 뿐 readiness를 판정하지 않는다. 진행률 필드의 구체적인
  shape는 canonical read location과 함께 후속 Backend integration에서 결정한다.
- Runtime Overlay의 이벤트·Observation lineage는
  [`../closed-loop-runtime-overlay-contract.md`](../closed-loop-runtime-overlay-contract.md)를 따른다.
- Observation `source_kind`는 Target 구현에서 `canonical_observation` 또는
  `maintenance_replay_overlay`를 반환한다. Overlay 응답은 `simulation_session_id`,
  `overlay_branch_id`, `maintenance_event_id`, `history_segment_id`를 함께 보존한다.
- 최신 결과 pagination은 `offset`, `limit`, `total`을 유지한다.
- `status_grade`는 runtime inference가 생성하는 Result Artifact 계약에 포함한다.
- stale은 timezone을 포함한 최신 `observed_at` 기준 프론트 24시간 Operations 정책을 유지한다.
- Identity/RBAC는 `process_manager`, `process_engineer`, `maintenance_technician` role code를 사용하고,
  기존 `manager`/`engineer`는 Report/UI compatibility view alias로 유지한다.
- fallback은 로컬 데모 compatibility 경로에서 명시적으로 표시하며, Model Artifact가
  필요한 비로컬 실행 환경은 fail-closed를 따른다.

### 후속 확인

- 보고서 생성 timeout과 retry 정책
- V2 목표 경로와 `page`/`size` 계약 채택 여부 및 전환 계획
- **Deferred:** Product API의 canonical runtime-status read location은 `gen_data` Runtime
  Overlay의 versioned Observation/status handoff 계약 확정 이후 Backend integration
  단계에서 결정한다. 후보는 Event `closed_loop` envelope, Equipment 상태 API 또는 별도
  runtime status endpoint이며, 결정 시 OpenAPI·Frontend adapter·E2E를 함께 갱신한다.
- `warming_up` 진행률 필드와 `history_insufficient` 사유 envelope
