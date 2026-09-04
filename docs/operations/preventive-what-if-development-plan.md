# 고장 전조 분석 및 예방조치 What-if 개발 계획

- 문서 상태: `PR #20 완료 · 후속 시뮬레이션 의존성 대기`
- 기준일: `2026-08-13`
- 현재 문서 브랜치: `docs/what-if-model-artifact-contract-alignment`
- 발표일: `2026-09-11`
- 기준 데이터: `canonical-ai4i-physics-v3.1`
- 기준 모델: `WIF-DEC-08`~`WIF-DEC-10` 확정 전 미결정

## 1. 문서 목적

이 문서는 Operations 공통 결과 연결 이후 추가하는 **합성 반사실 예방조치 실험**의
개발 범위, 책임 경계, 데이터 계약, 일정과 완료 조건을 관리한다.

기존 필수 Operations 계약을 변경하지 않고 별도 실험 계층으로 개발한다. 현재
Canonical V3.1, Prediction Timeline과 Result Artifact는 읽기 전용 기준으로
취급하며 What-if 결과를 기존 결과에 덮어쓰지 않는다.

## 2. 해결하려는 문제

현재 제품은 설비별 고장확률과 주요 요인을 제공한다. What-if 기능은 다음 질문에
답할 수 있는 구조화된 분석 결과를 추가한다.

1. 고장확률이 언제부터 상승했는가?
2. 상승 전후에 어떤 센서값이 달라졌는가?
3. 여러 상승 사례에서 반복되는 선행 지표는 무엇인가?
4. 예방조치를 적용하지 않은 경우와 적용한 경우의 예상 확률은 어떻게 달라지는가?
5. 예방조치 비용과 예상 고장 손실은 어떤 차이가 있는가?

결과는 실제 현장 효과가 아니라 Canonical V3.1과 기존 모델을 이용한
`synthetic_counterfactual_simulation`으로 표시한다.

## 3. 책임 경계

### 3.1 What-if Producer

What-if 모듈은 다음 값만 구조화해 생성한다.

- 위험 상승 시작·최고점·상승폭·지속시간
- 상승 전후 센서 통계
- 반복 선행 지표와 모델 기여도
- 조치 코드와 파라미터
- Baseline/Intervention 예상 확률과 감소량
- 예상 정지시간과 경제성 계산값
- Evidence reference, provenance, effect scope, limitation code

### 3.2 Producer에서 제외하는 것

- 관리자·현장 담당자용 최종 문장
- ReportOutput block과 LLM 호출
- 역할별 강조 순서
- UI 색상·아이콘·표시 문구
- 고장 원인 또는 예방 효과의 확정 표현
- 자동 정지·자동 정비 명령

### 3.3 Consumer

| 영역 | 소비 책임 |
|---|---|
| `final/map-report` | What-if Result를 역할별 ReportOutput과 자연어 문장으로 변환 |
| Dashboard | 확률·센서 차트, 상태 문구, 툴팁과 사용자 상호작용 |
| API | 분석 함수 호출, 결과 전달, 실행 상태와 오류 처리 |

### 3.4 운영 판단 권위와 downstream 사용 제한

`systems/backend/app/diagnosis`의 Product Result Artifact와 `evidence_payload`가
`failure_probability`, `status_grade`, `top_factors`, `recommended_action`의
authoritative source다. What-if Producer는 해당 값을 읽기 전용 입력과 provenance로
사용하며 새 운영 판단값으로 덮어쓰거나 승격하지 않는다.

위험 상승 탐지·센서 통계 산출물은 다음 용도로만 연결한다.

- What-if 후보 사건 선정과 오프라인 ranking
- `sensor_evidence`와 baseline 참고 근거
- 후보 선정 정책·source field provenance
- 합성 Baseline/Intervention 실험 입력

Dashboard, Event Evidence projection과 `final/map-report`는 이 산출물을 운영
`status_grade`, 경보 임계값, 점검 명령 또는 `recommended_action`의 source로 사용하지
않는다. 역할별 표현에서도 후보·합성 추정 언어와 limitation을 유지한다.

## 4. 전체 처리 흐름

```text
Canonical V3.1 / Prediction Timeline
→ 고장확률 상승 사건 탐지
→ 상승 전후 센서 구간 비교
→ 반복 선행 지표 통계
→ 예방조치 후보 코드 선택
→ 조치 없음 Baseline 생성
→ 예방조치 Intervention 생성
→ 관련 시계열과 6시간 특징 재계산
→ 동일한 기존 모델로 재평가
→ Baseline/Intervention 예상 확률·비용 비교
→ 구조화된 What-if Result 생성
→ API / Dashboard / map-report가 소비
```

### 4.1 What-if 재평가용 Model Artifact 확정 원칙

What-if는 임의 모델 파일이나 `latest` alias를 직접 선택하지 않는다. Baseline과
Intervention은 동일한 immutable Model Artifact를 사용하며, Artifact manifest와
동봉된 Feature·History 계약을 검증한 뒤 재평가한다.

현재 `model-artifact-v1.0`과 Backend loader의 호환성을 유지하기 위해 다음 기존
최상위 필드는 제거하거나 이름을 바꾸지 않는다.

- `training_config`
- `metrics`
- `checksum`
- `provenance`
- `compatibility`
- `artifact_files`

What-if 계획은 `model-artifact-v1.0`의 호환 확장 방식을 채택한다. prediction,
history, label과 runtime 계약을 명시적으로 추가하되 기존 필드와 소비자 계약을
깨뜨리지 않는다. 다음 메타데이터를 v1.0 호환 확장 필드로 사용한다.

- `dataset_schema_version`
- `label_schema_version`
- `history_requirement_version`
- `metrics_schema_version`
- `prediction_contract`
- `model_runtime`

`metrics_summary`는 기존 `metrics`를 대체하지 않고 `metrics.summary`로 포함한다.
`compatibility.runtime`은 현행 Backend loader 호환을 위해 유지한다. What-if runtime
호환 표시는 추론 실행 주체가 확정된 뒤 선택적으로 추가하며, What-if가 Generator나
Backend 구현 코드를 직접 import할 수 있다는 의미로 사용하지 않는다.

`artifact_files`는 빈 배열을 허용하지 않는다. 최소한 `model`과 `feature_schema` role을
포함하고, History 기반 Feature를 채택하면 `history_requirement`, Label 재현·감사를
요구하면 `label_schema`, 평가 상세를 외부 파일로 둘 경우 `metrics` role을 포함한다.
각 파일은 `artifact_files[*].sha256`와 최상위 `checksum.files`에서 동일한 sha256으로
검증돼야 한다.

`prediction_contract`는 최소한 다음 의미를 고정한다.

- `prediction_task = binary_failure_within_horizon`
- `prediction_horizon_hours`
- `probability_output = positive_class_probability`
- `positive_class_label`
- 학습 시 선택된 기본 `decision_threshold`
- `threshold_policy_version`

운영 환경에서 threshold override가 필요하면 Model Artifact의 학습 기준값을 변경하지
않고 별도 versioned 운영 정책으로 관리한다.

`history_requirement_version`만으로 Feature parity가 보장되지는 않는다.
`feature_schema.json` 또는 연결된 명세에는 asset partition, timestamp ordering,
최소 관측 수, lookback, sampling 규칙, 결측값, dtype, rolling `min_periods`, std
`ddof`, EMA와 categorical transform 파라미터가 재현 가능하게 포함되어야 한다.

따라서 What-if 연동에서 `metrics`, `checksum`, `compatibility.runtime`과 필수
`artifact_files`를 유지한다. `metrics_summary`처럼 기존 필드를 대체하는 새 이름은
사용하지 않고 `metrics.summary`처럼 기존 구조 안에서 확장한다. 이 방식은 기존
Backend를 깨뜨리지 않는 계획상 확정 방향이다.

PR #28 완료 전에는 세부 필드 shape와 구현 시점만 확정하지 않는다. 현행
`contracts/schemas/model-artifact.schema.json`은 `additionalProperties: false`이므로 확장 필드를
허용하도록 JSON Schema를 함께 갱신해야 한다. 이때 기존 필수 필드와 의미는 유지하고
Generator publisher·Backend provider·계약 테스트가 기존 Artifact와 새 확장
Artifact를 모두 처리하는지 확인한다.

기존 필드 이름을 교체하거나 기존 의미를 깨야 한다면 호환 확장으로 처리하지 않는다.
이 경우 `model-artifact-v2.0`으로 올리고 Generator·Backend·JSON Schema·테스트를
동시에 변경한다.

## 5. 입력 데이터

다음 Canonical V3.1 파일을 읽기 전용으로 사용한다.

- `prediction_timeline.jsonl`
- `cnc_sensor_observation.csv`
- `compressor_sensor_observation.csv`
- `cnc_production_cycle.csv`
- `maintenance_event.csv`
- `asset_master.csv`
- `asset_relation.csv`

Evaluation truth는 탐지율·선행시간 평가에만 사용하고 제품 API, Dashboard,
ReportInput과 ReportOutput에는 노출하지 않는다.

## 6. 별도 실험 데이터

기존 Canonical 파일을 변경하지 않고 다음 구조의 별도 파생 실험으로 관리한다.

```text
experiments/preventive_intervention/
├─ dataset/
├─ policies/
├─ simulator/
├─ schemas/
├─ generated/
├─ evaluation/
└─ tests/
```

### 6.1 고장 발생 이력

`failure_event_history.csv`

- `failure_event_id`, `asset_id`
- `detected_at`, `occurred_at`, `reported_at`
- `failure_mode`, `component_code`, `symptom_code`
- `severity`, `operating_impact`, `shutdown_required`
- `related_prediction_id`, `related_rise_event_id`
- `root_cause_status`, `confirmed_root_cause_code`
- `source_type`, `recorded_at`

Evaluation truth에서 변환할 경우 `occurred_at`이 지난 이벤트만 운영 이력으로 공개한다.

### 6.2 수리 작업·부품·비용·결과 이력

| 파일 | 역할 |
|---|---|
| `repair_work_order_history.csv` | 작업 유형, 조치 코드, 시작·완료·재가동 시각과 정지시간 |
| `repair_part_history.csv` | 교체 부품, 수량, 단가, 제거 상태와 설치 시각 |
| `repair_cost_history.csv` | 부품비·인건비·외주비·물류비·재가동 비용 |
| `repair_outcome_history.csv` | 수리 전후 위험도, 정상화 여부, 24시간·7일·30일 재발 |

고장, 수리 작업, 비용과 결과를 한 테이블에 합치지 않고
`failure_event_id → work_order_id → cost_id/outcome_id`로 연결한다.

### 6.3 예방조치 결정·실행 이력

| 파일 | 역할 |
|---|---|
| `intervention_decision.csv` | 추천 조치, 수락·거절·보류, 선택 조치와 정책 버전 |
| `intervention_outcome.csv` | 실제 실행 여부, 전후 위험도, 고장·정지시간·비용 결과 |

추천, 실행과 결과를 구분해야 향후 실제 treatment-effect 학습 데이터를 구성할 수 있다.

## 7. 경제성 데이터

### 7.1 설비 경제 기준

`asset_economic_master.csv`

- 취득·교체·설치 비용
- 기대 사용연수와 잔존가치
- 설비 중요도
- 통화, 유효기간, 가격 버전
- `source_type`, `source_reference`

설비 가격 전체는 전손 또는 교체 시나리오에서만 사용한다.

### 7.2 제품 경제 기준

`product_economic_master.csv`

- L/M/H 제품 유형
- 단위 판매가격과 변동비
- 단위 공헌이익
- 폐기·재작업 비용
- 통화, 유효기간과 가격 버전

생산중단 손실은 판매가격 전체가 아니라 단위 공헌이익으로 계산한다.

### 7.3 예방조치 기준

`maintenance_action_catalog.csv`

- `action_code`, 적용 설비와 고장 모드
- 기본 정지시간과 작업시간
- 부품비·인건비·외주비
- shutdown 필요 여부와 정책 버전
- 실제·견적·합성 가격 구분

실제 가격이 없으면 임의의 `0`이 아니라 `null`과 `source_type=missing`을 사용한다.
이 기준정보는 Backend의 versioned cost-basis provider가 공급한다. Product UI는 비용값을
작성하는 주체가 아니라 분석 요청과 결과·누락 사유를 표시하는 consumer이다.

### 7.4 금액 출처 등급과 사용 규칙

Canonical V3.1은 생산 주기, 정비 시간과 공구 교체 여부를 제공하지만 설비 취득가,
부품 단가, 정비 인건비, 제품 공헌이익과 고장 손실 금액은 제공하지 않는다. 따라서
Canonical 데이터만으로 실제 비용 또는 실제 절감액을 계산하지 않는다.

금액 입력은 다음 우선순위로 선택한다.

| 우선순위 | `source_type` | 허용 출처 | 결과 표시 |
|---:|---|---|---|
| 1 | `actual` | 자산대장, 구매전표, 세금계산서, ERP·MES·CMMS 작업·비용 이력 | 실제 관측값 |
| 2 | `vendor_quote` | 제조사·공급사 견적서, 유지보수 계약서 | 견적 기반 추정값 |
| 3 | `public_reference` | 나라장터 계약·입찰 가격, 공공 임금 통계, 공식 전기요금표 | 외부 기준 대리값 |
| 4 | `policy_assumption` | 팀이 승인한 계산식과 범위 | 정책 가정값 |
| 5 | `synthetic` | 데모용 합성 분포에서 생성한 값 | 합성 시나리오 값 |
| 6 | `missing` | 사용 가능한 근거 없음 | 계산 제외 또는 결과 `null` |

공개 가격은 대상 설비·부품의 제조사, 모델, 규격, 납품 범위, 설치비와 기준일이
일치할 때만 직접 대리값으로 사용한다. 조건이 다르면 단일 확정값이 아니라
`estimate_low`, `estimate_base`, `estimate_high` 범위로 사용한다. 공개된 CNC 장비 한 건의
조달가격을 모든 CNC 설비의 가격으로 복제하지 않는다.

각 경제 입력에는 최소한 다음 provenance를 저장한다.

- `amount`, `currency`, `price_basis`, `effective_from`, `effective_to`
- `source_type`, `source_name`, `source_reference`, `retrieved_at`
- `asset_model_or_part_number`, `quantity`, `included_cost_scope`
- `estimate_method`, `estimate_low`, `estimate_base`, `estimate_high`
- `assumption_version`, `approved_by`, `confidence_grade`

문서 URL만으로 재현할 수 없는 견적·사내 자료는 문서 번호나 익명화된 참조 ID를 남긴다.
합성값은 실제값처럼 승격하지 않으며 실제 자료가 들어오면 동일 키의 새 가격 버전으로
교체한다.

### 7.5 실제값이 없을 때의 산정 정책

실제값이 없는 경우에도 경제성 비교는 구현할 수 있다. 단, 아래 산정식을 버전 있는
정책으로 관리하고 결과를 `synthetic_scenario_estimate`로 제한한다.

- 설비 교체비: 동급 사양의 2건 이상 견적·조달가격 범위 + 운송·설치·시운전 비용
- 부품비: 동일 부품번호 견적을 우선하고, 없으면 호환 부품 가격 범위
- 정비 인건비: 작업시간 × 직종별 시간당 총노무비. 최저임금만으로 숙련 정비 인건비를
  대표하지 않는다.
- 생산중단 손실: Canonical 생산 주기로 계산한 미생산 수량 × 제품별 단위 공헌이익
- 폐기·재작업비: 영향 제품 수량 × 제품별 폐기·재작업 단가
- 재가동비: 재가동 작업시간 인건비 + 시험 생산 폐기비 + 추가 에너지비

제품 공헌이익 또는 수리 부품비처럼 공개자료로 사업장 실제값을 대체할 수 없는 항목은
팀이 승인한 저·기준·고 시나리오를 사용한다. 하나라도 필수 입력이 `missing`이면 단일
원화 최적값을 반환하지 않고 손익분기 임계값 또는 입력 필요 항목을 반환한다.

### 7.6 경제성 결과의 신뢰 수준

경제성 결과에는 사용한 입력 중 가장 낮은 신뢰 수준을 결과 신뢰 수준으로 전파한다.

- `observed`: 필수 금액이 모두 사내 실제 이력
- `quoted`: 실제값과 유효한 공급사 견적의 조합
- `reference_estimate`: 공공·공식 대리값 포함
- `synthetic_scenario`: 정책 가정 또는 합성값 포함
- `insufficient`: 필수 금액 누락으로 비교 불가

`reference_estimate` 이하 결과는 "예상 절감액" 또는 "시나리오 비교"로만 표시하고,
실제 절감 보장, 투자 회수 확정 또는 최적 교체 시점 확정으로 표현하지 않는다.

## 8. 위험 상승과 선행 지표 분석

설비별 Prediction Timeline에서 상승 시작·최고점·종료점, 확률 상승폭과 지속시간을
계산한다. 초기 임계값을 코드에 고정하지 않고 데이터 분포 분석 후 버전 있는 정책으로
관리한다.

센서별 정상 기준 구간과 위험 구간의 평균, 중앙값, 표준편차, 변화율,
Baseline 표준편차 기준 이동량과
모델 contribution을 계산한다.

- CNC: 공기·공정 온도, 온도 차, RPM, Torque, Power, Tool wear, 제품 유형
- Compressor: 전압, 회전, 압력, 진동, 상대 진동 Z-score

최종 통계는 선행 지표별 동반 사건 수·비율·평균 변화량·평균 선행시간을 제공한다.
문서에 사용하는 숫자는 계약 설명용 예시와 실제 분석 결과를 명확히 구분한다.

## 9. 예방조치 시뮬레이션

### 9.1 Baseline

```text
현재 상태 유지
→ 예방조치 없음
→ 이후 시계열 생성
→ 시간창 Feature 재계산
→ 기존 모델 재평가
```

### 9.2 Intervention

```text
동일 초기 상태
→ 예방조치 적용
→ 연결된 물리값과 이후 시계열 재계산
→ 동일 Feature Engineering
→ 동일 모델 재평가
```

### 9.3 현재 프로젝트 Action 범위

| 상태 | `action_code` | 내용 | 대상 |
|---|---|---|---|
| 현재 구현 | `TOOL_REPLACEMENT` | 카바이드 절삭 인서트 1개 교체, Tool wear 초기화와 이후 마모 재계산 | TWF·OSF |
| 후속 vertical slice | `COOLING_SYSTEM_RESTORE` | 공정·공기 온도 차 정상화 | HDF |

`CUTTING_LOAD_REDUCTION`은 실제 정비보다 운전 조건을 변경하는 OperationalAction에
가깝고, 현재 프로젝트에는 별도 OperationalAction 승인·실행 경로가 없다. 따라서
Maintenance Action vocabulary와 구현 순서에서 제외한다. Torque·overstrain 징후는
제거하지 않으며 Inspection에서 공구 마모 또는 냉각 문제가 확인될 때만 각각
`TOOL_REPLACEMENT` 또는 `COOLING_SYSTEM_RESTORE` 후보로 연결한다.

RNF는 센서 조건과 무관하므로 예방조치 효과 비교 대상에서 제외한다.

## 10. 모델 범위

초기 단계에서는 새로운 머신러닝 모델을 만들지 않는다.

```text
기존 모델
+ 기존 Feature Engineering
+ 새 예방조치 시뮬레이터
```

기존 모델의 특징, 가중치와 임계값을 변경하지 않는다. 조치/미조치 시계열에 동일한
특징 계산과 추론을 적용한다. 합성 조치 쌍이 충분히 축적된 후에만 별도
treatment-effect 모델을 후속 검토한다.

## 11. 경제성 계산

경제성 계산은 한 개의 고정 금액만 비교하지 않고 각 금액의 저·기준·고 입력에 대해
민감도 분석을 수행한다. 추천 시점은 기준 시나리오의 최소 기대비용 시점이며, 저·고
시나리오에서도 동일 선택이 유지되는지 함께 제공한다.

```text
고장 발생 손실
= 직접 수리비
+ 생산중단 손실
+ 폐기·재작업 비용
+ 재가동 비용
```

```text
생산중단 손실
= 미생산 예상 수량 × 제품 유형별 단위 공헌이익
```

```text
Baseline 기대손실
= baseline_probability × 고장 발생 시 예상 손실
```

```text
Intervention 기대비용
= 예방조치 직접비
+ 예방조치 정지손실
+ intervention_probability × 고장 발생 시 예상 손실
```

```text
예상 순편익
= Baseline 기대손실 - Intervention 기대비용
```

모든 경제 결과는 `synthetic_scenario_estimate`로 표시하고 실제 절감액처럼 표현하지 않는다.
향후 사내 실제 이력만 사용한 결과는 `observed`로 승격할 수 있으나, 사용한 source와
계산 정책 버전을 결과에 계속 포함한다.

## 12. 구현 기준 경로

| 경로 | 역할 | 현재 상태 |
|---|---|---|
| `experiments/preventive_intervention/contracts.py` | Pydantic 입출력 계약과 검증 규칙 | 구현 완료 |
| `experiments/preventive_intervention/policies.py` | 비파괴 예방조치 변환 | 공구 교체 구현 완료 |
| `experiments/preventive_intervention/policies/tool-replacement-v1.json` | 공구 교체 정책 | 구현 완료 |
| `contracts/schemas/preventive-what-if.schema.json` | Producer JSON Schema | 구현 완료 |
| `data/fixtures/what_if/` | 계약 fixture | 1건 작성 완료 |
| `tests/test_preventive_what_if_foundation.py` | 계약·정책 불변성 테스트 | 작성 완료 |
| `experiments/preventive_intervention/risk_rise.py` | CNC 위험 상승 사건 탐지와 공구 마모 후보 ranking | PR #20 구현 완료 |
| `experiments/preventive_intervention/sensor_analysis.py` | 대표 사례 baseline/risk 센서 통계 | PR #20 구현 완료 |
| `experiments/preventive_intervention/cli.py` | 위험 상승·대표 사례 분석 재현 CLI | PR #20 구현 완료 |
| `experiments/preventive_intervention/` | 비배포 What-if producer | 탐지·후보 분석 완료, Intervention 시계열 미구현 |

## 13. 현재 구현 상태

### 완료

- [O] `main` 기준 독립 브랜치 생성
- [O] What-if Result Pydantic 계약
- [O] Draft 2020-12 JSON Schema
- [O] `TOOL_REPLACEMENT` 정책 계약
- [O] 원본 관측을 변경하지 않는 공구 교체 변환
- [O] 계약 fixture와 검증 테스트
- [O] Producer 결과에서 역할별 Report 필드 제외
- [O] What-if를 비배포 Experiment 계층으로 명문화
- [O] 공구 교체 typed parameter와 cross-field 의미 검증
- [O] 상승 시작부터 peak까지의 시간을 `time_to_peak_hours`로 명확화
- [O] Canonical V3.1 CNC Prediction Timeline 분포 분석
- [O] `risk-rise-detection-v1` 정책과 deterministic 탐지기 구현
- [O] 공구 마모 `risk_up` 후보 ranking과 대표 CNC 사례 선정
- [O] 대표 사례의 6시간 baseline/risk 센서 통계 조인
- [O] PR #20 머지 및 운영 판단 비권위 경계 명문화

### 현재 체크포인트

PR #20으로 다음 vertical slice 전단계를 완료했다.

```text
Canonical V3.1 CNC Prediction Timeline
→ 분포 기반 위험 상승 정책
→ 전체 CNC 위험 상승 후보 탐지
→ 공구 마모 risk_up 후보 선별
→ 대표 사례 선정
→ baseline/risk 센서 통계와 provenance
```

재현 기준 결과는 위험 상승 후보 2,606건, 공구 마모 후보 1,027건, 대표 설비
`CNC-S02-L04-03`이다. 이 값들은 고장 원인이나 예방조치 효과가 아니라 후속 What-if
입력 후보와 참고 근거다.

### 후속 작업 상태

- [O] Canonical V3.1 공구 마모 위험 사례 선정
- [O] 상승 사건 탐지 기준의 데이터 분포 분석
- [보류] Baseline/Intervention 시간창 생성
- [보류] 조치 후 공구 마모 누적과 생산·정비 상태 재계산
- [보류] 기존 Feature Engineering 재사용
- [보류] 동일 모델로 확률 재평가
- [ ] 실제 실행 결과 fixture로 계약 예시 교체
- [ ] 고장·수리·경제 확장 데이터 Schema 구현

위 항목 중 Baseline/Intervention 시계열 생성부터 동일 모델 재평가까지는 현재 개발을
중단한다. 열린 stacked PR #21~#24가 Feature Engineering, 모델 학습·버전 관리,
Generator 실행 방식과 Prediction 서비스를 변경하고 있어 지금 연결하면 기준 모델과
Feature 계약이 달라질 수 있기 때문이다.

독립적으로 구현 가능한 시계열 변환도 후속 Feature·추론 인터페이스에 맞춘 재작업을
피하기 위해 함께 보류한다. PR #20의 탐지·후보 분석 산출물은 현재 main에서 완결된
체크포인트로 유지한다.

### 개발 재개 조건

PR #21~#24의 구현 방향과 PR #28의 계약이 최종 대상 브랜치에 반영된 뒤 다음 조건을
확인하고 계획을 다시 승인한다.

1. 최종 Feature schema와 window 의미가 확정돼야 한다.
   - Canonical V3.1의 6시간 Feature
   - PR #21의 5·10행 rolling Feature
   - 두 체계를 병행할 경우 명시적 version 경계
2. What-if 비교에 사용할 model ID, algorithm과 immutable version을 고정해야 한다.
   `latest`를 재현 가능한 비교 기준으로 사용하지 않는다.
3. Baseline과 Intervention이 동일 Feature Engineering과 동일 Model Artifact를 사용하는
   추론 인터페이스를 확정해야 한다.
4. Generator prediction, Backend diagnosis와 비배포 What-if experiment의 책임을 다시
   확인해야 한다.
5. Generator 결과가 Product Result Artifact의 운영 판단값을 직접 대체하지 않는다는
   기존 경계를 유지해야 한다.
6. 확정된 main에서 대표 사례의 입력 Feature와 기존 Prediction Timeline 호환성을
   다시 검증해야 한다.
7. 최종 Model Artifact manifest가 현행 필수 필드, 파일별 checksum과 최소 file role을
   보존하는지 확인해야 한다.
8. `prediction_contract`, Feature schema와 History requirement가 동일 horizon·feature
   순서·window 의미를 재현할 수 있는지 golden-vector contract test로 검증해야 한다.

### 외부 PR 의존성 현황

2026-08-12 확인 기준으로 다음 stacked PR이 열려 있다.

| PR | 변경 영역 | What-if 영향 | 현재 처리 |
|---|---|---|---|
| `#21` | Extraction·Feature pipeline | 6시간 Feature와 5·10행 rolling Feature의 호환성 | 머지 후 재검토 |
| `#22` | LightGBM·XGBoost·RandomForest 학습·버전 | 비교 모델과 immutable version 선택 | 머지 후 재검토 |
| `#23` | Generator daemon·재학습 API | 오프라인 실험보다 후속 실행 방식에 영향 | 머지 후 재검토 |
| `#24` | Prediction service·latest 모델 로딩 | 추론 주체, 다중 모델 선택과 재현성 | 머지 후 재검토 |
| `#28` | Feature/Label·Model Artifact 목표 계약과 ADR | manifest 확장, History requirement, Feature parity 기준 | 계약 확정 후 계획 갱신 |

PR #21~#24는 `main → #21 → #22 → #23 → #24` 순서로 쌓인 의존 PR이다. 개별 PR의
중간 계약을 What-if의 확정 인터페이스로 사용하지 않고 최종 반영된 main을 기준으로
다시 검증한다.

PR #17의 Backend Artifact inference와 Product Result Artifact 경계도 추론 adapter
결정 시 함께 확인하되, demo/local `HeuristicPredictor`를 Canonical V3.1 What-if의
공식 비교 모델로 사용하지 않는다.

현재 `82% → 21%` 같은 값은 계약 구조 설명용 fixture이며 실제 시뮬레이션 성능
결과가 아니다.

## 14. 주차별 계획

### Week 2 — 2026-08-10~08-16

- Producer/Consumer 책임과 입력·출력 계약 확정
- 공구 교체 정책과 계약 fixture
- 고장·수리·예방조치·경제 데이터 Schema 설계
- PR #20 위험 상승 탐지·대표 사례 분석 완료
- PR #21~#24 Feature/Model/Prediction 계약 검토 및 후속 개발 보류 결정

### Week 3 — 2026-08-17~08-23

- PR #20에서 선행 완료한 위험 상승 탐지·센서 구간 비교 결과 유지
- PR #21~#24 최종 반영 상태 확인
- PR #28 Feature/Label·Model Artifact 계약 확정 상태 확인
- `WIF-DEC-08`~`WIF-DEC-10` 결정 및 `WIF-DEC-11` 세부 shape 반영
- 의존 PR이 미완료이면 시뮬레이션 구현을 시작하지 않음

### Week 4 — 2026-08-24~08-30

- 의존 계약 확정 시 공구 교체 Baseline/Intervention 시계열 생성
- 확정된 version Feature 재계산
- 고정된 동일 Model Artifact로 재평가와 위험 감소량 계산
- 재현성·물리 규칙·Canonical 불변 검증

### Week 5 — 2026-08-31~09-06

- 가공 부하 완화·냉각 복원 확장
- 고장·수리 이력과 경제성 계산 연결
- API·Dashboard·`map-report` 통합

### 발표 주 — 2026-09-07~09-11

- 테스트와 데모 시나리오 고정
- 수치·단위·시간대·truth 비노출 검증
- 합성 효과와 실제 효과의 한계 표시
- 발표 자료와 백업 시연 준비

## 15. 팀 합의 필요 사항

| ID | 결정 사항 | 영향 |
|---|---|---|
| `WIF-DEC-01` | 기존 Feature Engineering과 추론 함수 재사용 인터페이스 | Week 4 모델 재평가 |
| `WIF-DEC-02` | **결정 완료:** `experiments/preventive_intervention` 비배포 계층 | 제품 system과 분리하고 Artifact/API 계약으로만 연결 |
| `WIF-DEC-03` | What-if Result의 ReportInput 연결 방식 | `map-report` 통합 |
| `WIF-DEC-04` | `action_code`, limitation code, Evidence reference 목록 | Producer/Consumer 계약 |
| `WIF-DEC-05` | API 동기 실행 또는 사전 생성 결과 조회 | 실행 시간·오류 계약 |
| `WIF-DEC-06` | 실제·견적·합성 가격 구분과 가정 승인 방식 | 경제성 결과 신뢰도 |
| `WIF-DEC-07` | Evaluation truth를 운영 고장 이력으로 공개하는 시점 규칙 | 누수 방지 |
| `WIF-DEC-08` | What-if 재평가에 사용할 Feature schema와 window version | PR #21과 기존 6시간 Feature 호환성 |
| `WIF-DEC-09` | model ID·algorithm·immutable version 선택 | PR #22/#24의 다중 모델·latest 사용 방지 |
| `WIF-DEC-10` | 추론 실행 주체: Artifact adapter, Backend port 또는 Generator API | 시스템 direct import와 운영 책임 경계 |
| `WIF-DEC-11` | **결정 완료:** `model-artifact-v1.0` 호환 확장 채택; 기존 필드 교체 시에만 v2 전환 | Generator publisher·Backend provider·What-if adapter 동시 호환 |

`WIF-DEC-11`의 호환 전략은 확정했다. `WIF-DEC-08`~`WIF-DEC-10`과 v1 확장 필드의
세부 shape는 PR #21~#24와 PR #28의 최종 계약이 main에 반영된 뒤 결정한다. 해당
Feature·모델·추론 계약이 확정되기 전에는 `intervention_probability`와 위험 감소량을
공식 산출하지 않는다.

## 16. 검증 기준

- 동일 입력·seed·정책은 동일 결과를 생성한다.
- Baseline과 Intervention은 같은 초기 상태에서 시작한다.
- Intervention 이외의 조건은 임의로 바꾸지 않는다.
- 공구 교체 시 `tool_wear_min=0`, `is_operating=0`, `operating_state=maintenance`다.
- 조치 이후 시간창 Feature를 다시 계산한다.
- 두 시나리오는 동일 모델·버전·임계값을 사용한다.
- Model Artifact의 `model_id`, immutable `model_version`, Feature/Label/History 계약
  버전과 file checksum을 결과 provenance에 남긴다.
- `training_config.feature_count`는 `feature_schema.json`의 실제 입력 Feature 수와
  일치해야 한다.
- Generator가 publish한 Artifact를 Backend provider 또는 확정된 What-if adapter가
  동일하게 검증·로드하는 round-trip test를 통과해야 한다.
- 동일 고정 입력에 대해 학습 측 Feature executor와 재평가 측 Feature executor가 같은
  순서와 값의 Feature vector를 생성하는 golden-vector test를 통과해야 한다.
- `estimated_probability_reduction = baseline - intervention`을 만족한다.
- 모든 선행 지표에 source reference가 존재한다.
- 모든 선행 지표의 `source_reference.asset_id`는 결과의 `asset_id`와 같다.
- `intervention.policy_version`과 `provenance.simulation_policy_version`은 같다.
- `TOOL_REPLACEMENT`는 0 이상의 `tool_wear_after`를 필수로 가진다.
- `time_to_peak_hours`는 `rise_event.started_at`부터 `peak_at`까지의 시간과 일치한다.
- 모든 결과에 effect scope와 필수 limitation code가 있다.
- Canonical 원본·Prediction Timeline·Result Artifact checksum을 변경하지 않는다.
- Evaluation truth가 제품 응답에 포함되지 않는다.
- Producer는 역할별 문장과 UI 표현을 생성하지 않는다.
- 실험 정책은 운영 `status_grade`, 경보 또는 `recommended_action`을 결정하지 않는다.
- What-if 산출물은 Product Result Artifact의 운영 판단 필드를 덮어쓰지 않는다.

## 17. 완료 기준

### 17.1 첫 번째 End-to-End 검증 기준

> 대표 CNC 설비 한 대의 고장확률 상승을 탐지하고 선행 센서 지표와 근거를
> 구조화한다. 동일 초기 상태에서 공구 교체를 적용한 경우와 적용하지 않은 경우를
> 동일 Feature Engineering과 기존 모델로 비교해 예상 위험 감소량을 생성한다.
> 결과에는 합성 시뮬레이션 범위와 한계를 명시한다.

대표 사례 한 건의 성공은 전체 기능 완료가 아니라 위험 탐지부터 예방조치 효과
평가까지의 vertical slice 검증 완료를 의미한다.

### 17.2 프로젝트 완료 기준

> 검증된 위험 상승 탐지와 What-if 파이프라인을 Canonical V3.1의 적용 가능한
> 전체 CNC 설비 및 공구 마모 관련 위험 상승 사건에 반복 적용한다. 사건별
> 예방조치 결과와 함께 설비·사건 전체의 효과 분포 및 집계 결과를 생성한다.

프로젝트 완료를 위해 다음을 만족해야 한다.

- 전체 CNC Prediction Timeline을 동일한 버전 정책으로 분석한다.
- 공구 마모 관련 위험 상승 사건을 재현 가능하게 선별한다.
- 적용 가능한 각 사건에 동일한 공구 교체 정책을 적용한다.
- Baseline과 Intervention은 동일 초기 상태에서 시작한다.
- 두 시나리오에 동일한 Feature Engineering과 모델 버전을 사용한다.
- 사건별 `baseline_probability`, `intervention_probability`,
  `estimated_probability_reduction`을 생성한다.
- 효과가 없거나 위험이 증가한 사건도 결과에서 제외하지 않는다.
- 분석 대상 수, 적용 성공·실패 수, 평균·중앙값과 위험 감소량 분포를 집계한다.
- 모든 결과에 dataset, model, detection policy와 simulation policy provenance를 남긴다.
- 모든 수치는 `synthetic_counterfactual_simulation` 결과로 표시한다.
- 실제 인과 효과나 현실의 예방 효과로 단정하지 않는다.
- Producer는 역할별 자연어 문장이나 UI 표현을 생성하지 않는다.
- 역할별 자연어 문장은 구조화된 결과를 소비하는 `final/map-report`가 생성한다.

### 17.3 후속 도메인 확장 기준

CNC 공구 교체 파이프라인을 검증하고 전체 적용한 후 다음 예방조치를 별도 정책으로
확장할 수 있다.

- `COOLING_SYSTEM_RESTORE`
- Compressor 진동·압력·공기 공급 관련 예방조치

`CUTTING_LOAD_REDUCTION`은 이 문서의 후속 Maintenance Action 확장 대상에도 포함하지
않는다. 향후 별도 OperationalAction 도메인과 사람 승인·실행 계약을 설계하는 경우에만
독립 안건으로 다시 검토한다.

각 예방조치는 별도의 typed parameter, 물리 변환 정책, 적용 가능 조건과 검증 기준을
가져야 한다. CNC 공구 교체 정책과 같은 임계값 또는 변환 규칙을 공유한다고 가정하지
않는다.

## 18. 후속 범위

- 실제 예방조치 이력 축적 후 treatment-effect 모델
- 고장 유형별 다중 분류 모델
- 실제 비용·생산계획 기반 경제성 보정
- 부품 재고와 조달 기간
- 현장 전문가의 조치 정책 검증

## 19. 변경 이력

| 날짜 | 변경 |
|---|---|
| 2026-08-11 | 실행 계획 최초 작성, 현재 구현 상태와 기준 경로 반영 |
| 2026-08-11 | What-if Producer와 `final/map-report` Consumer 경계 반영 |
| 2026-08-11 | 고장·수리·예방조치·경제 데이터 계획 반영 |
| 2026-08-12 | 대표 사례 vertical slice와 전체 CNC 프로젝트 완료 기준 분리 |
| 2026-08-12 | Product Result Artifact 권위 경계와 후보·합성 표현 제한 반영 |
| 2026-08-12 | PR #20 완료 상태, PR #21~#24 의존성 대기와 개발 재개 조건 반영 |
| 2026-08-28 | `CUTTING_LOAD_REDUCTION`을 현재·후속 Maintenance Action 범위에서 제외하고 지원 상태를 구분 |
