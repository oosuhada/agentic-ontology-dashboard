# Ontology Dashboard Operations 데이터 계약서

- 상태: 멘토링 합의 기반 Operations 공통 데이터 계약
- 적용 화면: Overview, Objects, Operations, Executive Report View
- Source Dataset: Canonical V3.1
- 작성일: 2026-08-06

## 1. 문서 목적

이 문서는 Canonical V3.1의 데이터와 모델 결과를 네 개 Operations 화면에서 동일한 의미로 사용하기 위한 공통 계약을 정의한다.

핵심 목적은 다음과 같다.

- 같은 설비와 Event를 화면마다 다른 ID나 상태로 표현하지 않는다.
- 원본 센서 값, 모델 결과, 운영 정책과 사용자 행동을 분리한다.
- 데이터 품질 문제를 실제 고장으로 오인하지 않는다.
- 임원 보고서의 숫자를 Overview와 Operations의 숫자와 일치시킨다.
- 이후 다른 Dataset을 연결해도 네 화면 계약을 재사용한다.

## 2. 데이터 흐름

```text
Canonical V3.1 files
→ Dataset Version registration
→ Relational materialization
→ Prediction Result
→ Evidence Package
→ Ontology projection
→ Operations API models
→ Four Operations screens
```

화면은 Canonical V3.1 파일을 직접 읽지 않는다.

## 3. 데이터 계층 구분

### 3.1 Source Observation

센서와 생산 조건의 실제 관측값이다.

- 공기 온도
- 공정 온도
- 회전 속도
- 토크
- 공구 마모
- 제품 유형

### 3.2 Prediction Result

모델 또는 deterministic fallback이 생성한 결과다.

- `failure_probability`
- `predicted_failure_type`
- `confidence`
- model version

### 3.3 Operational Policy Result

모델 점수와 운영 정책을 결합한 결과다.

- `status`
- `recommended_decision`
- threshold
- policy version

### 3.4 Human Action

사용자가 실제로 기록한 판단과 조치다.

- 실제 결정
- 점검 요청
- 담당자 배정
- 점검 메모
- 점검 완료

추천과 실제 행동을 같은 필드에 저장하지 않는다.

## 4. 식별자 계약

### 4.1 필수 식별자

| 필드 | 의미 | 예시 | 불변성 |
|---|---|---|---|
| `organization_id` | 조직 | `ontology-demo-org` | 조직 내 불변 |
| `project_id` | 업무 Project | `manufacturing-demo-project` | 불변 |
| `workspace_id` | 업무 공간 | `manufacturing-demo` | 불변 |
| `dataset_id` | Dataset entity | `canonical-v3-1` | Dataset 단위 불변 |
| `dataset_version_id` | 구체 버전 | `dsv-canonical-v3-1` | 버전별 불변 |
| `equipment_id` | 설비 business key | `M-014` | 버전 간 유지 권장 |
| `event_id` | 위험 Event ID | `GS-004` | Event 단위 불변 |
| `prediction_result_id` | 예측 결과 ID | `prediction:M-014:...` | 결과 단위 불변 |
| `evidence_id` | Evidence Package ID | `evidence-GS-004` | 생성본 단위 불변 |
| `ontology_object_id` | Ontology Object ID | `risk_event:GS-004` | Object 단위 불변 |
| `report_id` | 생성 보고서 ID | `report-GS-004-manager-ko-KR` | 생성본 단위 |

### 4.2 ID 생성 금지

프론트엔드는 임의로 다음을 생성하지 않는다.

- 설비명으로 `equipment_id` 추론
- Event ID에서 Dataset Version 추론
- 배열 index로 Object ID 생성
- timestamp만으로 prediction ID 생성

ID는 API 응답을 그대로 사용한다.

## 5. Dataset Version 계약

### 5.1 Operations 기본 버전

Operations의 기본 Dataset Version은 release-ready Canonical V3.1이다.

```text
Canonical V3.1
```

내부 ID는 환경에 따라 달라질 수 있으므로 화면은 display label과 `dataset_version_id`를 함께 사용한다.

### 5.2 버전 선택 규칙

1. 사용자가 명시적으로 선택한 버전이 있으면 해당 버전을 사용한다.
2. 선택이 없으면 Project의 기본 release-ready 버전을 사용한다.
3. 기본 버전은 Canonical V3.1이어야 한다.
4. 한 화면의 모든 데이터는 같은 Dataset Version이어야 한다.
5. Report와 Evidence는 실제 Dataset Version을 lineage에 기록한다.

### 5.3 버전 불일치

다음 상태는 오류 또는 경고로 처리한다.

- Event와 Evidence의 `dataset_version_id` 불일치
- Object와 Prediction Result의 버전 불일치
- Report가 참조한 Evidence 버전이 현재 Event와 다름

화면은 서로 다른 버전 값을 조용히 합치지 않는다.

## 6. 공통 enum

### 6.1 Risk status

```text
normal
attention
warning
critical
data_quality_hold
```

| 상태 | 의미 | 기본 표현 |
|---|---|---|
| `normal` | 즉시 조치 필요 없음 | 정상 |
| `attention` | 경계 또는 저신뢰 | 관찰 필요 |
| `warning` | 운영 기준을 넘은 위험 | 점검 필요 |
| `critical` | 높은 위험과 사람 검토 필요 | 긴급 검토 |
| `data_quality_hold` | 데이터 문제로 판단 보류 | 데이터 확인 |

### 6.2 Recommended decision

```text
continue_monitoring
request_inspection
review_shutdown
hold_for_data_check
```

| 값 | 의미 |
|---|---|
| `continue_monitoring` | 계속 운전하며 관찰 |
| `request_inspection` | 현장 점검 요청 |
| `review_shutdown` | 권한자의 정지 검토 요청 |
| `hold_for_data_check` | 데이터 검증 전 판단 보류 |

`review_shutdown`은 자동 정지 명령이 아니다.

### 6.3 Confidence

권장 정규화 값:

```text
high
medium
low
unavailable
```

기존 payload가 다른 문자열을 반환하면 API adapter에서 위 값으로 정규화한다.

### 6.4 Criticality

```text
low
medium
high
```

설비 중요도는 모델 확률이 아니다. 중요도만으로 `critical` 상태를 만들지 않는다.

### 6.5 Data quality severity

```text
info
warning
error
```

`error` 수준 문제로 예측을 신뢰할 수 없으면 `data_quality_hold`를 사용한다.

## 7. 공통 Operations 모델

### 7.1 OperationsEquipment

```json
{
  "equipment_id": "M-014",
  "display_name": "절삭 설비 M-014",
  "line": "Line-02",
  "criticality": "high",
  "assigned_engineer": "박지민",
  "last_maintenance_date": "2026-07-29",
  "estimated_downtime_minutes": 120,
  "spare_part_available": false
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `equipment_id` | string | 예 | 설비 business key |
| `display_name` | string | 예 | 사용자 표시명 |
| `line` | string | 예 | 생산 라인 |
| `criticality` | enum | 예 | 설비 중요도 |
| `assigned_engineer` | string | 아니오 | 현재 담당자 표시명 |
| `last_maintenance_date` | date | 아니오 | 최근 정비일 |
| `estimated_downtime_minutes` | integer | 예 | 예상 중단 영향 |
| `spare_part_available` | boolean | 아니오 | 부품 확보 여부 |

### 7.2 OperationsRiskEvent

```json
{
  "event_id": "GS-004",
  "scenario_id": "GS-004",
  "equipment": {},
  "status": "critical",
  "failure_probability": 0.91,
  "confidence": "high",
  "predicted_failure_type": "failure_risk",
  "recommended_decision": "review_shutdown",
  "observed_at": "2026-08-06T01:30:00Z",
  "dataset_version_id": "dsv-canonical-v3-1",
  "ontology_object_id": "risk_event:GS-004"
}
```

| 필드 | 타입 | null | 설명 |
|---|---|---:|---|
| `event_id` | string | 아니오 | Event ID |
| `scenario_id` | string | 아니오 | Gold/demo 시나리오 ID |
| `equipment` | OperationsEquipment | 아니오 | 설비 요약 |
| `status` | RiskStatus | 아니오 | 정책 상태 |
| `failure_probability` | number | 예 | `0`–`1`, 품질 보류 시 null |
| `confidence` | Confidence | 아니오 | 결과 신뢰 수준 |
| `predicted_failure_type` | string | 아니오 | 모델 결과 클래스 |
| `recommended_decision` | RecommendedDecision | 아니오 | 정책 추천 |
| `observed_at` | datetime | 예 | 관측 기준 시각 |
| `dataset_version_id` | string | 아니오 | 결과 버전 |
| `ontology_object_id` | string | 예 | Ontology 연결 ID |

### 7.3 OperationsSensorObservation

```json
{
  "timestamp": "2026-08-06T01:30:00Z",
  "product_type": "H",
  "air_temperature_k": 298.4,
  "process_temperature_k": 309.2,
  "rotational_speed_rpm": 1420,
  "torque_nm": 52.4,
  "tool_wear_min": 218
}
```

| 필드 | 단위 | null 허용 | 주요 화면 |
|---|---|---:|---|
| `air_temperature_k` | K | 예 | Objects·Evidence |
| `process_temperature_k` | K | 예 | Objects·Evidence |
| `rotational_speed_rpm` | rpm | 예 | Objects·Evidence |
| `torque_nm` | N·m | 예 | Objects·Operations |
| `tool_wear_min` | minute | 예 | Objects·Operations |

null 센서는 `0`으로 대체하지 않는다.

### 7.4 OperationsEvidence

```json
{
  "evidence_id": "evidence-GS-004",
  "event_id": "GS-004",
  "scenario_id": "GS-004",
  "equipment": {},
  "model": {
    "model_version": "ai4i-random_forest-v1",
    "policy_version": "trained-model-policy-v1",
    "mode": "model"
  },
  "status": "critical",
  "recommended_decision": "review_shutdown",
  "confidence": "high",
  "failure_probability": 0.91,
  "threshold": 0.85,
  "predicted_failure_type": "failure_risk",
  "observation": {},
  "history": [],
  "detected_interval": {
    "start": "2026-08-06T01:20:00Z",
    "end": "2026-08-06T01:30:00Z"
  },
  "top_factors": [],
  "maintenance_context": {},
  "data_quality_warnings": [],
  "lineage": {},
  "generated_at": "2026-08-06T01:31:00Z"
}
```

### 7.5 OperationsFactor

```json
{
  "evidence_field_id": "factor.tool_wear_min",
  "feature": "tool_wear_min",
  "display_name": "공구 마모",
  "value": 218,
  "unit": "minute",
  "normal_range": "0–200",
  "direction": "risk_up",
  "contribution": 0.34,
  "source_type": "model_explanation"
}
```

규칙:

- `contribution`은 확률이 아니다.
- contribution 합이 반드시 1일 필요는 없다.
- `normal_range`가 학습 범위인지 운영 기준인지 구분한다.
- 인과관계로 표현하지 않는다.

### 7.6 OperationsOperationalDecision

추천 결정과 사용자 결정을 분리한다.

```json
{
  "decision_id": "decision-GS-004-001",
  "event_id": "GS-004",
  "recommended_decision": "review_shutdown",
  "actual_decision": "request_inspection",
  "actor_user_id": "user-process-manager",
  "actor_display_name": "김현우",
  "note": "정지 전 현장 점검을 우선 진행합니다.",
  "created_at": "2026-08-06T02:00:00Z"
}
```

### 7.7 OperationsAssignment

```json
{
  "assignment_id": "assignment-GS-004-001",
  "event_id": "GS-004",
  "assignee_id": "user-process-engineer",
  "assignee_display_name": "박지민",
  "status": "assigned",
  "due_at": "2026-08-06T00:00:00Z",
  "note": "다음 교대 전 점검",
  "created_by": "user-process-manager",
  "created_at": "2026-08-06T02:05:00Z",
  "updated_at": "2026-08-06T02:05:00Z"
}
```

권장 assignment status:

```text
assigned
in_progress
completed
blocked
cancelled
```

### 7.8 OperationsActivity

```json
{
  "id": "activity-001",
  "event_id": "GS-004",
  "activity_type": "decision_recorded",
  "actor_user_id": "user-process-manager",
  "actor_display_name": "김현우",
  "summary": "현장 점검 요청",
  "detail": "정지 전 현장 점검을 우선 진행합니다.",
  "source_object_id": "risk_event:GS-004",
  "created_at": "2026-08-06T02:00:00Z"
}
```

권장 activity type:

```text
decision_recorded
assignment_created
assignment_updated
inspection_note_added
inspection_completed
inspection_issue_reported
inspection_blocked
report_updated
```

### 7.9 OperationsExecutiveReport

```json
{
  "report_id": "report-GS-004-manager-ko-KR",
  "revision": 3,
  "project_id": "manufacturing-demo-project",
  "workspace_id": "manufacturing-demo",
  "event_id": "GS-004",
  "dataset_version_id": "dsv-canonical-v3-1",
  "locale": "ko-KR",
  "headline": "M-014 설비 위험 대응 보고",
  "summary": "현장 점검이 진행 중이며 생산 영향은 120분으로 추정됩니다.",
  "status": "critical",
  "confidence": "high",
  "recommended_decision": "review_shutdown",
  "actual_decision": "request_inspection",
  "sections": [],
  "evidence_references": ["evidence-GS-004"],
  "published_at": "2026-08-06T02:30:00Z",
  "updated_by": "user-process-engineer"
}
```

## 8. Canonical V3.1 필드 매핑

### 8.1 Observation

| Canonical V3.1 개념 | Operations 필드 | 변환 |
|---|---|---|
| Equipment identifier | `equipment.equipment_id` | 문자열 유지 |
| Product type | `observation.product_type` | category 유지 |
| Air temperature | `air_temperature_k` | Kelvin 유지 |
| Process temperature | `process_temperature_k` | Kelvin 유지 |
| Rotational speed | `rotational_speed_rpm` | rpm 유지 |
| Torque | `torque_nm` | N·m 유지 |
| Tool wear | `tool_wear_min` | minute 유지 |
| Observation time | `observed_at` | ISO 8601 |

### 8.2 Prediction

| Result Artifact | Operations 필드 | 규칙 |
|---|---|---|
| binary score | `failure_probability` | `0`–`1` |
| binary class | `predicted_failure_type` | V3.1 semantic label |
| model version | `model.model_version` | 필수 |
| policy version | `model.policy_version` | 필수 |
| threshold | `threshold` | 실제 사용값 |
| confidence | `confidence` | 정규화 enum |

### 8.3 Operational metadata

| 정책·업무 결과 | Operations 필드 |
|---|---|
| risk band | `status` |
| recommended action | `recommended_decision` |
| downtime metadata | `equipment.estimated_downtime_minutes` |
| criticality metadata | `equipment.criticality` |
| responsible person | `equipment.assigned_engineer` 또는 Assignment |

## 9. Predicted failure type 의미

Canonical V3.1의 현재 예측 과업을 개별 고장 원인을 확정하는 다중 클래스 진단으로 과장하지 않는다.

허용 표현:

```text
failure_risk
no_significant_risk
unavailable
```

금지 표현:

- 모델이 제공하지 않은 특정 부품 고장 확정
- `PWF`, `HDF`, `OSF`, `TWF`를 검증 없이 예측 원인으로 사용
- 높은 확률을 실제 고장 발생으로 표현

원인 후보는 Evidence factor와 정비 맥락을 근거로 “점검 우선 후보”라고 표현한다.

## 10. 상태 결정 규칙

### 10.1 데이터 품질 우선

```text
if prediction unavailable because of data quality:
    status = data_quality_hold
    failure_probability = null
    predicted_failure_type = unavailable
    recommended_decision = hold_for_data_check
```

### 10.2 Policy profile 분리

현재 프로젝트는 모델 평가용 policy와 Gold demo fallback policy를 구분한다.

```text
trained_model_policy.json
threshold_policy.json
```

서로 다른 model version에 다른 profile의 threshold를 적용하지 않는다.

### 10.3 미탐·오탐 최적값 제안

Operations는 절대적인 단일 최적 threshold를 주장하지 않는다.

권장 payload:

```json
{
  "recommended_threshold": 0.2,
  "recommended_range": {
    "min": 0.18,
    "max": 0.25
  },
  "objective": "recall_constrained",
  "assumptions": {
    "false_negative_cost": 10,
    "false_positive_cost": 1,
    "minimum_recall": 0.8
  },
  "metrics": {
    "precision": 0.42,
    "recall": 0.83,
    "f1": 0.56
  },
  "policy_version": "trained-model-policy-v1"
}
```

화면은 가정과 목적을 숨기지 않는다.

## 11. 화면별 데이터 사용

### 11.1 Overview

필수 모델:

- `OperationsRiskEvent[]`
- `OperationsEquipment`
- Dataset Version label

사용 필드:

- status
- failure probability
- criticality
- line
- estimated downtime
- recommended decision

Overview는 원시 센서 history 전체를 로드하지 않는다.

### 11.2 Objects

필수 모델:

- Ontology `ObjectRecord`
- Object type definition
- source refs
- object version
- Dataset Version

설비 Object 권장 properties:

```json
{
  "equipment_id": "M-014",
  "display_name": "절삭 설비 M-014",
  "line": "Line-02",
  "criticality": "high",
  "assigned_engineer": "박지민",
  "status": "critical",
  "failure_probability": 0.91,
  "dataset_version_id": "dsv-canonical-v3-1"
}
```

### 11.3 Operations

필수 모델:

- `OperationsRiskEvent`
- `OperationsEvidence`
- `OperationsOperationalDecision`
- `OperationsAssignment`
- `OperationsActivity[]`

추천과 실제 상태를 함께 표시한다.

```text
Recommended: review_shutdown
Actual: request_inspection
Inspection: in_progress
```

### 11.4 Executive Report View

필수 모델:

- `OperationsExecutiveReport`
- 최신 `OperationsRiskEvent`
- 최신 `OperationsActivity[]`
- Evidence references

다음 값은 임의 편집 대상이 아니다.

- failure probability
- status
- Dataset Version
- model version
- policy version
- source evidence ID

## 12. Lineage 계약

주요 숫자와 주장은 다음 경로로 추적 가능해야 한다.

```text
Report sentence or metric
→ evidence_field_id
→ Evidence Package
→ Prediction Result or Observation
→ Dataset Version
→ Canonical source reference
```

### 12.1 필수 lineage

```json
{
  "dataset_version_id": "dsv-canonical-v3-1",
  "prediction_result_id": "prediction:M-014:2026-08-06T01:30:00Z",
  "model_version": "ai4i-random_forest-v1",
  "policy_version": "trained-model-policy-v1",
  "source_refs": [
    "canonical://v3.1/observations/M-014/2026-08-06T01:30:00Z"
  ]
}
```

### 12.2 Evidence field ID

권장 패턴:

```text
failure_probability
threshold
equipment.criticality
equipment.estimated_downtime_minutes
observation.torque_nm
observation.tool_wear_min
factor.tool_wear_min.contribution
```

보고서 section은 사용한 field ID 목록을 보존한다.

## 13. Null·Unknown·Unavailable

### 13.1 기본 규칙

- null을 `0`으로 바꾸지 않는다.
- 빈 문자열을 정상 값으로 처리하지 않는다.
- 알 수 없음과 사용 불가를 구분한다.

### 13.2 화면 표시

| API 값 | 표시 |
|---|---|
| null probability | `—` |
| unavailable prediction | `예측 사용 불가` |
| 담당자 없음 | `미배정` |
| 정비일 없음 | `기록 없음` |
| 부품 여부 없음 | `확인 필요` |

### 13.3 데이터 품질 경고

```json
{
  "code": "missing_required_sensor",
  "field": "torque_nm",
  "message": "토크 값이 없어 결과를 신뢰할 수 없습니다.",
  "severity": "error"
}
```

## 14. 단위와 표시

### 14.1 API 단위

| 필드 | 단위 |
|---|---|
| `air_temperature_k` | K |
| `process_temperature_k` | K |
| `rotational_speed_rpm` | rpm |
| `torque_nm` | N·m |
| `tool_wear_min` | minute |
| `estimated_downtime_minutes` | minute |

### 14.2 화면 변환

- 온도를 섭씨로 표시하면 Kelvin 원본과 변환 사실을 tooltip에 표시한다.
- Downtime을 시간으로 표시해도 원본 분 값은 유지한다.
- 반올림은 표시 계층에서만 수행한다.
- 보고서 근거는 반올림 전 source value를 참조한다.

## 15. 정렬과 우선순위

권장 상태 점수:

```text
critical = 5
warning = 4
attention = 3
data_quality_hold = 2
normal = 1
```

`data_quality_hold`는 위험도가 낮다는 뜻이 아니라 판단 불가 상태다.

기본 정렬:

```text
status_priority DESC
→ failure_probability DESC NULLS LAST
→ criticality_priority DESC
→ observed_at DESC
```

## 16. 보고서 숫자 일치

### 16.1 Source of truth

| 데이터 | Source of truth |
|---|---|
| 현재 위험 상태 | 최신 Event |
| 고장 확률 | 최신 Prediction Result 또는 Evidence |
| 권장 결정 | 정책 결과 |
| 실제 결정 | 최신 사용자 Decision |
| 담당자 | 최신 Assignment |
| 점검 상태 | Inspection 또는 Work Order |
| 보고서 서술 | Shared Draft 또는 Grounded Report |

### 16.2 충돌 처리

보고서 서술 숫자와 최신 Evidence가 다르면:

1. 화면 KPI는 최신 Evidence 사용
2. Draft 본문은 보존
3. 불일치 경고 표시
4. 수정 권한 사용자에게 갱신 제안

## 17. 개인정보와 민감정보

Operations 데이터에는 실제 고객 개인정보를 포함하지 않는다.

담당자 정보는 데모 표시명 또는 내부 식별자로 제한한다.

금지:

- 주민등록번호
- 개인 휴대전화
- 개인 주소
- 외부 고객 비밀정보
- 실제 설비 인증정보

## 18. 데이터 품질 검증

### 18.1 Dataset ingest

- 필수 schema 존재
- sensor numeric type 확인
- timestamp parse 가능
- Equipment identifier 존재
- Dataset Version 불변성
- duplicate row 검증
- Result Artifact 연결 검증

### 18.2 API projection

- probability `0`–`1`
- status enum
- recommended decision enum
- criticality enum
- Event와 Equipment 연결
- Evidence와 Event 연결
- lineage 필수값

### 18.3 화면 전송 전

- 동일 `event_id` 중복 제거
- null과 zero 구분
- 최신 revision 선택
- 권한 범위 밖 object 제거

## 19. 데이터 gap

| ID | Gap | 우선순위 | 완료 기준 |
|---|---|---:|---|
| `Operations-DATA-GAP-01` | Assignment 공통 모델 미고정 | P1 | schema·저장·조회 구현 |
| `Operations-DATA-GAP-02` | Activity type enum 미표준 | P1 | 공통 enum·adapter 구현 |
| `Operations-DATA-GAP-03` | Confidence 문자열 비정규 | P1 | 4개 enum 정규화 |
| `Operations-DATA-GAP-04` | Report와 Evidence 불일치 검증 부족 | P2 | 경고·테스트 추가 |
| `Operations-DATA-GAP-05` | Threshold recommendation payload 없음 | P2 | 가정 포함 schema 추가 |

## 20. 인수 조건

### 20.1 동일 Event 일관성

- 네 화면에서 같은 `event_id`의 status가 일치한다.
- Overview와 Report의 failure probability가 일치한다.
- Objects와 Operations의 Equipment ID가 일치한다.
- Operations Decision이 Report 대응 현황에 반영된다.

### 20.2 데이터 품질 보류

- probability는 null이다.
- status는 `data_quality_hold`다.
- decision은 `hold_for_data_check`다.
- Critical count에 포함되지 않는다.
- Report가 고장을 단정하지 않는다.

### 20.3 Dataset Version

- 네 화면이 동일 V3.1 ID를 표시한다.
- Evidence lineage에 같은 ID가 존재한다.
- 다른 버전 값이 섞이면 테스트가 실패한다.

### 20.4 Human action

- 추천과 실제 결정이 별도 필드다.
- actor와 timestamp가 기록된다.
- Assignment와 점검 결과가 Activity에 남는다.
- 실제 설비 제어 명령은 생성하지 않는다.

## 21. 구현 참조

```text
web/src/types.ts
web/src/features/ontology/types.ts
web/src/features/dashboard/types.ts
api/ontology_dashboard/contracts.py
api/ontology_dashboard/dashboard_models.py
api/ontology_dashboard/ontology.py
ml/src/factory_signal_ml/evidence.py
ml/src/factory_signal_ml/predictor.py
ml/config/trained_model_policy.json
ml/config/threshold_policy.json
```

## 22. 변경 관리

- 필드 추가·삭제·의미 변경 시 API 명세와 함께 수정한다.
- 원본 Dataset schema 변경을 화면에 직접 전파하지 않는다.
- enum 추가 시 기존 화면의 Unknown fallback을 확인한다.
- Dataset Version 변경 시 Report와 Evidence lineage를 재검증한다.
- 미탐·오탐 정책 변경은 policy version을 올리고 기존 결과를 덮어쓰지 않는다.
