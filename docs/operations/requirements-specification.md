# Operations 요구사항 정의서

## 기준

이 문서는 Canonical V3.1 기반 예지보전 제품의 현재 Operations 요구사항 기준선이다.
필드 근거는 [V3.1 검증표](./v3.1-field-validation.md), 프로토타입 이관 당시의 차이는
[2026-08 Week 2 Gap 분석](./history/2026-08-week2/prototype-operations-gap-analysis.md)을 provenance로 참고한다.

요구사항은 현재 실행 가능한 기능인 `Current Baseline`과 제품 목표인 `Target`을
구분한다. 현재 구현돼 있다는 이유만으로 Target을 확정하지 않으며, Target 요구사항은
현재 반영 여부와 후속 개발 여부를 명시한다.

## 제품 데이터 흐름

```text
gen_data의 버전된 합성 원천 데이터
→ systems/generator의 Feature·Model Artifact
→ systems/backend/diagnosis의 runtime inference
→ Product Result Artifact·Evidence
→ API
→ Dashboard·Report
```

- Canonical V3.1은 seed와 생성 정책으로 사전에 생성된 합성 데이터셋이다.
- 현재 Replay는 저장된 관측값과 사전 계산된 예측을 시간순으로 공개한다.
- Replay 중 센서값을 새로 생성하는 실시간 센서 서버로 표현하지 않는다.
- Closed-loop Target에서는 Canonical Replay를 수정하지 않고 정비 대상 설비만 별도
  `maintenance_replay_overlay` branch에서 정비 후 Observation을 생성한다.
- Runtime Overlay는 실제 센서 수집이나 Canonical source로 표현하지 않으며 대상 설비
  branch clock만 Fast-forward한다.
- Product Result Artifact의 운영 판단값은 Backend diagnosis가 생성한다.
- What-if 결과는 별도 합성 분석 결과이며 Product Result Artifact의
  `failure_probability`, `status_grade`, `top_factors`, `recommended_action`을 덮어쓰지 않는다.

## 사용자

기존 Operations UI compatibility view는 `매니저`, `엔지니어` 표시와 내부 alias
`manager`, `engineer`를 유지할 수 있다. Closed-loop의 canonical 역할은
`process_manager`, `process_engineer`, `maintenance_technician`이며 Product Action 경계는
[`../closed-loop-product-consumption-contract.md`](../closed-loop-product-consumption-contract.md)를 따른다.
아래 명칭은 업무 관점 설명이다.

- 현장 담당자: 위험 설비와 센서·예측 근거를 확인하고 점검 대상을 판단한다.
- 생산 관리자: 설비 위험과 생산·정비 현황을 함께 보고 대응 우선순위를 판단한다.

UI 표시 문자열은 역할 매핑에서 분리해 후속 사용자 검증 후 변경할 수 있게 한다.

## 개발 역할

개발 역할의 2026-08 Week 2 provenance는
[역할 분담 및 산출물 정의](./history/2026-08-week2/team-role-and-deliverables.md)에 보존한다.
현재 구현 책임은 `docs/architecture.md`와 [Runtime Ownership](./runtime-ownership-integration.md)을
우선하며, 아래 표는 당시 역할 분담의 후속 작업 추적을 위한 참고다.

| 담당 | 공식 역할 | 당시 핵심 책임 | 주요 산출물 |
|---|---|---|---|
| 우수 · 팀원1 | Frontend / Operations 화면 | 공통 Product Result Artifact·Evidence를 Overview·Objects·Operations·Event Executive Brief에 연결 | 화면 구현, 캡처, 데모 흐름, API 연결 상태 |
| 광우 · 팀원2 | Contract / Requirements / Specifications | 요구사항·기능·스키마·API·리포트·Operations 설계 계약과 Traceability 관리 | 문서 6종, 결정 기록, Current/Target 구분 |
| 성민 · 팀원3 | Prediction / Data / API | `gen_data` 원천 생성·재현성과 `ontology_dashboard`의 semantic/ML·Prediction·Product Result Artifact/Evidence 연결 | 원천 검증, Model Artifact, Prediction 목록·상세 조회, provenance |
| 호범 · 팀원4 | Report / LLM | Product Result Artifact와 Evidence를 deterministic 우선의 근거 기반 역할별 Report로 변환 | Event Report 입력·출력, 생성·검증 API, fallback, 예시 결과 |

세부 시스템 책임은 다음과 같이 구분한다.

- `gen_data`: raw/simulation/synthetic sensor data와 Canonical V3.1 원천 생성·재현성.
- `systems/generator`:
  - Extraction 단계에서 protocol data에 지정·승인된 Mapping을 적용하여 Versioned Observation Dataset을 발행한다.
  - 별도의 Authorized Training Truth Source를 사용하여 Versioned Failure Dataset을 발행한다.
  - Observation Dataset의 구조와 컬럼 역할을 분석하여 불변 Preprocessing Plan을 발행한다.
  - Ontology Mapping을 조회하지 않고 Feature Schema/Recipe 및 Label Schema를 실행하여 Feature Dataset Bundle을 발행한다.
  - Feature Dataset Bundle을 소비하여 모델을 학습·평가하고 versioned Model Artifact를 발행한다.
- `systems/backend/app/diagnosis`: Model Artifact 검증·로드, runtime inference,
  Product Result Artifact와 Evidence 생성.
- Frontend: API가 제공한 공통 결과의 사용자 화면 표현.
- Report: 검증된 구조화 결과의 역할별 문장·블록 생성.
- `experiments/preventive_intervention`: 광우가 별도 확장으로 진행하는 비배포 What-if
  분석 Producer. Contract/Docs 역할이나 Report 책임을 대체하지 않는다.

과거 역할표의 `팀원2=Report`, `팀원3=API`, `팀원4=Pipeline` 표기는 사용하지 않는다.
API는 하나의 담당으로 뭉뚱그리지 않고 Prediction·조회 API는 성민, Report 생성 API는
호범, API 계약 문서와 Traceability는 광우가 담당한다.

## Operations 화면

1. Overview
2. Objects
3. Operations
4. Executive Report

## 공통 요구사항

| ID | 요구사항 | 완료 기준 |
|---|---|---|
| CM-01 | 모든 화면은 같은 자산 ID와 기준시각을 사용한다. | 같은 조건에서 화면 간 값이 일치한다. |
| CM-02 | 원천 데이터와 파생 Result Artifact를 구분한다. | provenance와 출처를 확인할 수 있다. |
| CM-03 | 위험 등급은 `normal`, `attention`, `warning`, `critical`만 사용한다. | 다른 enum을 반환하지 않는다. |
| CM-04 | 색상과 함께 정상·주의·경고·위험 문구를 표시하고 품질 보류는 데이터 확인으로 구분한다. | 색상 없이도 위험등급과 품질 상태를 식별할 수 있다. |
| CM-05 | 데이터·모델·Artifact schema 버전을 표시한다. | 화면 또는 상세에서 세 버전을 확인한다. |
| CM-06 | loading, empty, error, stale, permission 상태를 구분한다. | 상태별 UI와 오류 응답이 정의된다. |
| CM-07 | 평가 truth를 일반 화면/API에 노출하지 않는다. | 계약 테스트가 노출을 차단한다. |
| CM-08 | 저장된 합성 데이터 Replay와 실제 실시간 수집을 구분한다. | 화면·API·문서가 Replay를 실제 센서 스트리밍으로 표현하지 않는다. |
| CM-09 | Current Baseline과 Target 요구사항을 구분한다. | 미구현 Target을 현재 기능으로 표시하지 않는다. |
| CM-10 | Producer의 구조화 결과와 역할별 문장·UI 표현을 분리한다. | What-if Producer에는 역할별 문장이 없고 Report/UI가 결과를 소비한다. |
| CM-11 | 정비 완료, 정비 후 이력 준비와 실제 Prediction 결과를 구분한다. | `equipment_under_maintenance`, `warming_up`, `history_insufficient`, `ready`, `predicted`가 정상 Prediction과 구분된다. |
| CM-12 | Runtime Overlay는 대상 설비에만 적용한다. | 다른 설비 Replay와 Canonical 원본이 변경되지 않는다. |

## 화면별 요구사항

### Overview

**Current Baseline**

- 위험 KPI, Downtime과 판단 대기 Event 중심

**Target**

- 기준시각과 데이터·모델 버전
- 전체·가동·비가동 설비 수
- 위험 등급별 설비 수
- 유형별 현황
- 상위 위험 설비
- 생산·정비 요약
- 선택 설비의 Objects 이동

등급별 합은 전체 설비 수와 같고, 같은 필터의 Operations 집계와 일치해야 한다.

### Objects

**Current Baseline**

- 검색·라인·상태·담당자 필터
- 선택 Event와 설비의 Evidence 확인

**Target**

- 자산 ID·사이트·셀·유형·가동·위험 필터
- 자산 기본정보
- Compressor/CNC별 최신 센서와 추세
- 고장 확률, 등급, 신뢰도, 24시간 horizon
- Artifact Top-3 판단 근거
- 연결 topology
- 정비 이력
- 원천/파생 구분과 provenance

`predicted_failure_type`은 PWF/HDF/OSF/TWF 고장 모드로 표현하지 않는다.

### Operations

**Current Baseline**

- Event Queue, Evidence, Decision, Note, Activity 중심

**Target**

- 기간별 생산 작업과 완료 현황
- 제품·CNC·시작·완료·가공시간·공구마모 증가량
- 기간별 정비 이력과 공구 교체 여부
- 생산/정비 대상 자산의 현재 위험 등급
- 기간·사이트·셀·자산유형 필터
- 자산의 Objects 이동

프로토타입의 Event Queue, Decision, Note Activity를 Operations에 포함할지는 합의가
필요하다. 비용·손실·인과 효과는 근거 없이 생성하지 않는다.

### Executive Report

**Current Baseline**

- 선택 Event 기반 역할별 grounded report
- `POST /api/events/{event_id}/report`

**Target**

- 보고 기간·생성시각·버전
- 전체·가동·위험 설비와 생산·정비 건수
- 위험 등급 분포
- 상위 위험 설비와 정책 권고
- 데이터로 검증 가능한 시사점
- 합성 데이터와 예측 결과의 한계
- LLM 실패 시 deterministic/template fallback

동일 조건의 Overview, Objects, Operations와 수치가 일치해야 한다.

## 예방조치 What-if 확장 요구사항

What-if는 운영 판단을 대신하는 기능이 아니라 동일 초기 상태에서 조치 미적용과
적용 시나리오를 비교하는 합성 분석 Producer다. 세부 구현 계획은
[예방조치 What-if 개발 계획](./preventive-what-if-development-plan.md)을 따른다.

| ID | 요구사항 | 완료 기준 |
|---|---|---|
| WIF-01 | 위험 상승 사건과 선행 지표를 구조화한다. | 시작·peak·상승폭과 모든 지표의 source reference가 존재한다. |
| WIF-02 | Baseline과 Intervention은 동일 초기 상태에서 시작한다. | 조치 필드 외 입력과 기준시각이 동일하다는 테스트를 통과한다. |
| WIF-03 | 두 시나리오에 동일 Feature·Model Artifact를 사용한다. | model·feature·history 계약 버전과 checksum이 결과 provenance에 남는다. |
| WIF-04 | 조치 전후 예상 위험을 비교한다. | `estimated_probability_reduction = baseline_probability - intervention_probability`를 만족한다. |
| WIF-05 | 결과를 Product Result Artifact와 분리한다. | 운영 판단 필드를 덮어쓰지 않고 `synthetic_counterfactual_simulation`으로 표시한다. |
| WIF-06 | 역할별 최종 문장은 Report/UI가 생성한다. | What-if 출력에는 구조화된 결과와 근거만 포함된다. |

첫 vertical slice는 대표 CNC 설비의 `TOOL_REPLACEMENT`를 검증하고, 이후 적용 가능한
전체 CNC 위험 상승 사건으로 확장한다. 대표 사례 한 건의 성공을 프로젝트 전체 완료로
표현하지 않는다.

Operations에서 `TOOL_REPLACEMENT`의 교체 단위는 마모된 카바이드 절삭 인서트 1개이다. 공구
홀더·공구 세트 전체 교체 비용을 이 Action의 부품비로 사용하지 않는다.

## 경제성 비교 요구사항

경제성 비교의 목표는 위험 감소량만 보여주는 것이 아니라 예방조치, 고장 후 수리와
설비 교체 시나리오의 기대비용을 비교해 비용상 유리한 조치 시점을 찾는 것이다.

Canonical V3.1에는 `asset_id`, `maintenance_id`, `product_type`, 생산·정비 시간은 있지만
설비 모델, 부품 ID, 설비·부품 가격, 정비 인건비와 제품 공헌이익은 없다. 기존
Canonical 파일에 임의의 금액을 역기입하지 않고 버전된 Economic Extension으로 연결한다.

### 필요한 경제 데이터 계약

| 데이터 | 연결 키 | 필수 내용 |
|---|---|---|
| 설비 카탈로그 | `asset_id → asset_model_id` | 제조사·모델명과 경제 기준 연결 |
| 설비 경제 기준 | `asset_model_id` | 교체·운송·설치·시운전 비용, 잔존가치 |
| 부품 마스터 | `part_id` | 부품번호·명칭·제조사·호환 설비 모델 |
| 부품 가격 기준 | `part_id` | 단가, 통화, 유효기간과 가격 버전 |
| 조치 카탈로그 | `action_code` | 필요 부품·수량·작업 역할·작업시간·정지시간 |
| 인건비 기준 | `labor_role` | 시간당 총노무비와 적용 기간 |
| 제품 경제 기준 | `product_type` | 단위 공헌이익·폐기비·재작업비 |
| 수리 비용 이력 | `maintenance_id` | 부품비·인건비·외주비·재가동비 |

### 금액 사용 규칙

| 우선순위 | 출처 유형 | 용도 |
|---:|---|---|
| 1 | `actual` | 자산대장·ERP·MES·CMMS·구매 및 수리 이력 |
| 2 | `vendor_quote` | 제조사·공급사 견적과 유지보수 계약 |
| 3 | `public_reference` | 조달가격·공식 임금 통계·공식 요금표 대리값 |
| 4 | `policy_assumption` | 팀 승인 산정식과 저·기준·고 범위 |
| 5 | `synthetic` | 데모용 합성 경제 시나리오 |
| 6 | `missing` | 계산 불가 또는 입력 필요 |

모든 금액은 `currency`, 유효기간, `source_type`, `source_reference`, 가격·가정 버전을
가진다. 공개 대리값이나 합성값을 실제 사업장 금액으로 표현하지 않는다.

`TOOL_REPLACEMENT`와 `COOLING_SYSTEM_RESTORE` 비용 분석 요청은 사용자가 경제 기준값을
직접 제출하는 입력창이 아니다. 사용자는 Action과 점검에서 참고한 SOP 식별자·버전만
보내고, Backend Maintenance가 Action별 버전 관리 비용 기준 provider에서 입력을 조회한다.
냉각 복구 기준은 사내 냉각 경로 세척·막힘 해소·동작 확인으로 제한하며 부품 교체가
확인되면 별도의 견적/Action basis를 요구한다. 즉시와 12시간 후 비용 산정 가정 시각은
서버 `calculated_at`에서 파생하고 `Asia/Seoul` 22:00~06:00에는 단일 50% 야간 가산
데모 요율을 적용한다. `assumed_execution_at`은 실제 WorkOrder 일정이나 정비 실행 시각이
아니며, 실제 통상임금이나 중복 가산을 계산하는 급여 엔진도 아니다.
Action별 공식 미래 확률이 없는 시점은 임의 보간하지 않고 `insufficient`로 표시한다.
상세 기준과 제한은 `docs/operations/maintenance-cost-basis.md`를 따른다.

`COOLING_SYSTEM_RESTORE`는 냉각 전용 미래 위험 데이터가 없는 현재 Operations에서 Product
UI에 `즉시 복구 예상 비용`만 표시한다. 계획·재점검·미조치 option은 Backend의 공유
결과 snapshot에 보존하지만 최적 시점 비교처럼 노출하지 않는다. 향후 냉각 전용
Prediction과 실제 정비·미조치 이력이 확보되면 계획·미조치 비교를 확장한다.

Cost What-if는 읽기 전용 의사결정 참고 기능이다. 비용 option과
`lowest_calculated_cost_option_id`는 Operations manual Recommendation, 승인, WorkOrder,
MaintenanceAction을 생성하지 않는다. 사용자의 실제 정비 판단은 Inspection Result와
Action 후보를 근거로 기존 Maintenance command에서 별도로 수행한다.
다만 사용자가 참고한 비용 분석 snapshot과 직접 선택한 Action 후보의 식별자는 감사
lineage로 Recommendation에 보존한다. 특정 비용 option을 직접 선택하지 않은 경우에는
`source_cost_option_id`를 기록하지 않으며, 최저비용 option을 사후 선택으로 간주하지 않는다.

| ID | 요구사항 | 완료 기준 |
|---|---|---|
| ECO-01 | 기존 ID와 경제 데이터를 참조 무결성이 있는 키로 연결한다. | 모든 `asset_id`, `part_id`, `action_code`, `labor_role`, `product_type` 참조가 유효하다. |
| ECO-02 | 조치 직접비와 조치 정지손실을 계산한다. | 부품·인건비·외주비·미생산 손실의 입력 근거를 역추적할 수 있다. |
| ECO-03 | 미조치·예방조치·고장 후 수리/교체의 기대비용을 비교한다. | 동일 horizon과 동일 가격 버전으로 시나리오별 비용이 생성된다. |
| ECO-04 | 시점별 최소 기대비용을 계산한다. | 비교한 후보 시점, 최소 시점과 비용 차이를 구조화해 반환한다. |
| ECO-05 | 저·기준·고 민감도 분석을 제공한다. | 각 시나리오 결과와 추천 유지 여부를 함께 반환한다. |
| ECO-06 | 결과 신뢰 수준을 표시한다. | `observed`, `quoted`, `reference_estimate`, `synthetic_scenario`, `insufficient` 중 하나가 존재한다. |
| ECO-07 | 필수 금액이 없으면 절감액을 단정하지 않는다. | `missing` 입력이 있으면 단일 원화 최적값 대신 누락 항목 또는 손익분기 임계값을 반환한다. |

초기 구현의 경제 결과는 `synthetic_scenario_estimate`이며 실제 절감 보장이나 확정된
투자 회수 효과로 표현하지 않는다.

## 제외와 결정 결과

### 유지할 제외 범위

- Analysis, Agent, Admin, Modeling Workbench
- 자동 설비 정지와 자동 Work Order
- 자동 생산계획 변경
- 평가 truth의 운영 노출

### 2026-08 Week 2 결정 기록

- UI 표시명은 매니저·엔지니어로 하고 내부 enum·권한과 매핑한다.
- 로그인·RBAC와 Decision·Note를 유지한다.
- Operations는 Event Activity를 Current로 유지하고 생산·정비 중심 구성은 Target이다.
- 위험등급은 Artifact 값을 그대로 사용하고 데이터 품질 상태와 분리한다.
- 현행 pagination과 프론트 24시간 stale 정책을 유지한다.
- Event Evidence 기반 deterministic Report를 우선하고 기간 집계형은 Target이다.
- Gold Fixture fallback은 source와 warning을 항상 표시한다.
- Canonical V3.1은 저장된 합성 데이터이고 Replay는 실시간 재생성이 아니다.
- Runtime Overlay는 Closed-loop Target의 별도 opt-in source 경로이며 Canonical Replay
  또는 실제 센서 스트리밍으로 표현하지 않는다.
- What-if는 구조화된 합성 분석 Producer이며 역할별 문장 생성은 Report/UI가 담당한다.
- 경제성 데이터는 Canonical에 역기입하지 않고 별도 버전의 Economic Extension으로 관리한다.
- 실제 금액이 없는 초기 경제성 비교는 출처가 표시된 합성 시나리오로 제한한다.

## 대표 흐름

1. Overview에서 전체 위험과 기준시각을 확인한다.
2. 위험 설비를 선택해 Objects에서 센서와 Top-3 근거를 확인한다.
3. Operations에서 관련 생산·정비 현황을 확인한다.
4. Executive Report에서 같은 집계와 한계를 확인한다.
5. What-if에서 동일 초기 상태의 조치 전후 위험과 근거를 비교한다.
6. 경제성 비교에서 예방조치·미조치·고장 후 수리/교체의 기대비용과 민감도를 확인한다.

Closed-loop 최종 시연 Target은 별도로 다음 흐름을 사용한다.

```text
위험 Result/Evidence
→ 사람의 Decision과 TOOL_REPLACEMENT
→ MaintenanceEvent
→ 대상 설비 Runtime Overlay + branch-local Fast-forward
→ gen_data Observation 지속 생성/available
→ Backend history_requirement 검증, 부족 시 다음 Observation 대기
→ Backend ready
→ 새 Runtime Prediction / Product Result / Evidence
```

상세 계약은
[`../closed-loop-runtime-overlay-contract.md`](../closed-loop-runtime-overlay-contract.md)를
따른다.
