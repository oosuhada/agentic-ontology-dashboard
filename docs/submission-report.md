# Hanbit Tech Reliability Operations
## 예지보전 기반 제조 운영 의사결정 워크스페이스 제출 보고서

## 1. 프로젝트 개요

본 프로젝트는 제조 설비의 센서 관측과 예측 결과를 단순한 위험 점수로 끝내지 않고, **현장 근거 확인 → 운영 판단 → 점검·정비 Action → 경영 보고 → 후속 재관측**까지 하나의 추적 가능한 업무 흐름으로 연결하는 Reliability Operations workspace를 구축하는 것을 목표로 한다.

데모 기업은 정밀 가공 및 산업용 구동부품 제조사인 **한빛테크(Hanbit Tech)** 다. 스마트팩토리 A의 CNC 및 압축기 설비에서 발생하는 관측과 예측 결과를 기반으로 설비 신뢰성 업무를 수행한다고 가정한다.

프로젝트의 핵심은 AI가 사람의 판단을 대신하는 것이 아니다. 같은 설비 이상 사건과 근거를 엔지니어, 운영 관리자, 경영진에게 각자의 업무 언어와 우선순위로 제공하고, 사람의 점검·승인·정비 결정이 어떤 Evidence를 기준으로 이루어졌는지 보존하는 데 있다.

## 2. 해결하려는 문제

제조 현장에서는 설비별 센서 데이터가 지속적으로 생성되지만, 다음 단계가 서로 분리되어 운영되는 경우가 많다.

- 센서 데이터와 모델 결과의 출처가 분산된다.
- 어떤 signal이 위험 판단에 기여했는지 현장 언어로 이해하기 어렵다.
- 예측 결과가 점검 요청이나 정비 승인으로 자연스럽게 이어지지 않는다.
- 엔지니어, 운영 관리자, 경영진이 서로 다른 질문을 가지지만 같은 정보 밀도의 화면을 보게 되기 쉽다.
- 보고서가 어떤 Event와 Evidence를 참조했는지 추적하기 어렵다.
- 정비 완료 사실과 실제 위험 감소를 혼동하기 쉽다.
- live telemetry가 갱신될 때 과거 판단 근거가 최신 Event로 조용히 바뀌면 Decision lineage가 깨질 수 있다.

따라서 본 프로젝트는 **예측 정확도 화면**보다 **근거의 불변성, 역할별 정보 구조, 사람의 판단 흐름, Action 이후 결과 추적**을 제품 중심 문제로 정의했다.

## 3. 제품 원칙

### 3.1 하나의 사건, 역할별 다른 깊이

세 역할이 raw sensor stream을 똑같이 보는 것이 아니다. 같은 Product Result와 Event를 기준으로 역할마다 다른 질문에 답한다.

- 엔지니어: 무엇이 변했고 무엇을 점검해야 하는가?
- 운영 관리자: 지금 무엇을 판단·승인해야 하는가?
- 경영진: 전체 운영 리스크, 영향, 병목과 책임자는 무엇인가?

### 3.2 Event identity와 근거는 고정한다

사용자가 명시적으로 선택한 `RESULT#...` Case는 새로운 관측이 들어와도 자동으로 최신 Event로 바꾸지 않는다. 새 관측은 별도의 상태와 CTA로 알리고, 사용자가 직접 전환할 때만 최신 Event를 연다.

### 3.3 고장 확정과 운영 추정을 구분한다

위험도, 생산 영향, 매출 노출, 공헌이익 노출 등은 운영 판단용 추정치다. 실제 고장 확정이나 회계 실적과 동일하게 표현하지 않는다.

### 3.4 사람의 승인 권한을 유지한다

LLM이나 예측 모델은 점검과 보고를 보조하지만 Work Order 생성, 정비 승인, 완료 기록은 사람의 권한과 closed-loop 상태 전이를 통해 수행한다.

### 3.5 정비 완료와 정상 판정을 분리한다

정비 완료는 작업 사실이다. 정상 여부는 후속 관측이 다시 동일 prediction pipeline을 통과한 결과를 통해 확인해야 한다.

## 4. 핵심 용어와 Source of Truth

### Product Result Artifact

runtime prediction과 backend validation/promotion 경계를 거쳐 저장되는 예측 결과의 제품 기록이다. 설비, 관측 시각, 모델·dataset provenance, 위험도, 상태, top factor, 추천 Action 등의 판단 사실을 가진다.

### Event

Product Result Artifact를 UI와 업무 흐름에서 하나의 사건으로 취급하기 위한 identity/projection이다. 현재 live production에서는 `RESULT#...` identity가 Decision Case의 기준 Event로 사용된다.

### Evidence

Product Result Artifact와 연결된 sensor/model/provenance 정보를 사용자와 report가 소비할 수 있도록 projection한 근거다. 별도의 독립 truth를 임의 생성하는 것이 아니라 producer artifact와 source reference에서 파생한다.

### Decision Case

하나의 Event를 다음 흐름으로 추적하는 업무 문맥이다.

```text
Event
→ Evidence
→ Decision
→ Action
→ Outcome / Re-observation
→ Report
```

## 5. 데이터 진실 수준

본 프로젝트는 live 데이터, synthetic demo context, 파생 추정치를 구분한다.

| 정보 | 현재 출처 | 성격 | 표현 원칙 |
|---|---|---|---|
| 설비 관측 | runtime sensor stream / Team DB | runtime data | 관측 사실 |
| Product Result | `pm_result_artifacts` | immutable runtime artifact | 예측 결과 |
| Model Artifact | Generator model artifact store | versioned artifact | 모델 provenance |
| SOP | demo inspection fixture | synthetic governance context | 데모 근거임을 명시 |
| 회의록/결정문 | company-context fixture | synthetic governance context | 데모 조직 context |
| 생산 손실 수량 | capacity model | derived estimate | 실제 실적과 구분 |
| 매출/공헌이익 노출 | demo economics model | derived estimate | 회계 손실 확정 금지 |
| 점검/승인/정비 milestone | Team DB workflow 기록 또는 presentation seed | operational/demo record | 사용자 Action과 seed 구분 |
| 정비 후 위험 감소 | 후속 Result Artifact | runtime evaluation | 후속 결과 없으면 미확정 |

## 6. 데모 기업과 조직

한빛테크는 경기도에 위치한 정밀 가공 및 산업용 구동부품 제조 기업으로 가정한다. 주요 생산품은 HX-M, HX-H, HX-L 구동 모듈이며 스마트팩토리 A에 다수의 CNC 및 유틸리티 설비를 운영한다.

| 조직 | 책임 | 관련 역할 |
|---|---|---|
| 경영 운영위원회 | 운영 리스크, KPI, 주요 투자·생산 차질 판단 | 경영진 |
| 생산운영실 | Decision Case 우선순위, 생산 영향, 점검·정비 승인 | 운영 관리자 |
| 설비신뢰성팀 | Signal/Evidence 분석, 원인 후보, 점검 계획 | 엔지니어 |
| 정비실행팀 | 승인된 작업 실행, 체크리스트, 완료 기록 | 정비 실행 |
| 재무·SCM팀 | 제품 경제성, 자재, 부품 리드타임 검토 | 지원 조직 |

## 7. 페르소나와 사용자 흐름

### 7.1 엔지니어

핵심 질문:

- 어느 설비가 이상한가?
- 어떤 Signal이 변했는가?
- 서로 다른 feature가 무엇을 의미하는가?
- 원인 후보와 반증 근거는 무엇인가?
- 어떤 위치를 어떤 방법으로 점검해야 하는가?
- 정비 후 재발 가능성은 있는가?

현재 IA:

```text
OBSERVE
  설비 현황
  모니터링

DIAGNOSE
  원인 분석
  점검
  정비 효과

LEARN
  정비 이력
  현장 기록
```

대표 흐름:

```text
이상 설비 확인
→ Evidence / Signal 확인
→ 원인 후보 검토
→ 점검 위치·방법 확인
→ 현장 점검
→ 정비 이력 및 후속 관측 확인
```

### 7.2 운영 관리자

핵심 질문:

- 지금 가장 먼저 판단해야 하는 Case는 무엇인가?
- 생산 영향은 어느 정도인가?
- 다음 Action은 무엇인가?
- 점검 또는 정비 승인이 필요한가?
- Owner와 현재 workflow 단계는 무엇인가?
- backlog 병목은 어디인가?

현재 IA:

```text
OBSERVE · 감지
  설비 현황
  운영 현황

DECIDE · 판단
  판단 대기
  Decision Case
  생산 영향
  정비 승인

FOLLOW-UP · 후속
  Backlog
  보고
```

첫 진입은 live telemetry에 따라 설비 현황, 판단 대기, 운영 현황 중 하나로 adaptive하게 결정된다.

### 7.3 경영진

핵심 질문:

- 지금 전체 운영 리스크가 얼마나 큰가?
- 생산·재무 영향은 어느 정도인가?
- 어떤 판단이 지연되고 있는가?
- 누가 무엇을 결정해야 하는가?
- 보고서가 어떤 근거와 Case를 참조하는가?

현재 primary IA:

```text
Executive Brief
→ 운영 리스크
→ 운영 KPI
→ 의사결정 병목
→ 보고 산출물
```

상세 근거는 정비 효과, 개선 과제, 설비 상태 근거로 drill-down한다.

## 8. 시연 시나리오 전략

### 8.1 Gold Scenario

저장소의 `EVT-GS-002 / CNC-S04-L04-01`은 공구 마모와 토크 상호작용, SOP 근거, 점검 흐름을 설명하기 위한 fixture 기반 Gold Scenario다.

이 시나리오는 테스트와 의미 설명에 사용한다.

- 공구 마모
- 토크
- 회전 속도
- 공구/회전체 SOP
- 생산 영향 추정

### 8.2 Production Demo Case

실제 `dashboard.oosu.dev` 시연에서는 Team DB의 immutable `RESULT#...`를 하나 선택해 `DEMO_EVENT_ID`로 고정한다.

Production Demo Case의 조건:

- API에서 복원 가능한 Event
- reload 및 live refresh 이후에도 같은 Event 유지
- Engineer / Operations / Executive / Report가 동일 Event를 참조
- closed-loop 전체를 보여줄 경우 해당 Event에 실제 workflow activity가 연결됨

**Gold Scenario와 Production Demo Case가 같은 설비일 수는 있지만 동일 Event라고 간주하지 않는다.**

## 9. Offline Model Lifecycle

모델 학습과 operational runtime prediction은 분리한다.

```text
Source Data
→ Extraction
→ Versioned Observation / Failure Dataset
→ Preprocessing Plan
→ Feature Dataset Bundle
→ Training / Evaluation
→ Immutable Model Artifact
```

Generator의 offline/model authoring 영역은 다음을 담당한다.

- protocol/source 데이터를 canonical observation 구조로 변환
- preprocessing contract 발행
- feature/label schema 기반 Feature Dataset Bundle 생성
- LightGBM, XGBoost, Random Forest 등 모델 학습·평가
- versioned Model Artifact와 provenance 발행

학습 후 평가 결과와 실제 production prediction은 동일 개념으로 취급하지 않는다.

## 10. Production Runtime Pipeline

현재 Mac mini 배포 기준 runtime은 offline training과 별도의 실행 경로를 가진다.

```text
Live Observation
→ live-ingestor
→ Generator Runtime Queue
→ Runtime Feature / Prediction
→ prediction-result-batch-v1
→ Backend /internal/prediction-results
→ validation / promotion
→ Team DB pm_result_artifacts
→ Event / Evidence / Decision Case / Report ViewModel
→ Reliability Operations Frontend
```

현재 배포에서는 Generator Runtime이 runtime prediction batch를 생성하고, Backend가 수신한 batch의 scope, 중복, schema와 product 계약을 검증한 뒤 Team DB의 Product Result read boundary로 승격한다. 즉 **runtime scoring 실행 위치**와 **제품 Result Artifact의 검증·승격·조회 책임**을 구분한다.

이 설명은 초기 설계 문서의 ownership 표현과 일부 다를 수 있으며, **제출 보고서는 현재 production에 배포된 실행 구조를 기준으로 한다.**

### 10.1 Current Architecture 정본

팀 발표와 제출 보고서에서는 아래 구조를 단일 정본으로 사용한다.

```text
Offline
Source / Protocol Data
→ Extraction
→ Feature / Label Dataset
→ Training / Evaluation
→ Versioned Model Artifact

Online
Live Source
→ live-ingestor
→ Generator Runtime Prediction
→ Backend Validation / Promotion
→ Team DB Product Result Artifact
→ Product UI / Report / Assistant Context
```

핵심 책임 분리는 다음과 같다.

- Generator Runtime: runtime feature 구성과 prediction batch 생성
- Backend: scope, schema, 중복, product contract 검증 및 Team DB 승격
- Team DB: 운영 화면과 report가 참조하는 authoritative product record
- Frontend: Result, Evidence, Decision, Action, Report를 역할별 업무 흐름으로 재구성

### 10.2 Runtime Timing 정의

“실시간”은 모든 계층이 zero-latency로 움직인다는 뜻이 아니다. 본 프로젝트에서는 지속적으로 들어오는 관측을 runtime pipeline에서 처리하고, 제품 UI가 최신 Result를 주기적으로 확인하는 구조로 정의한다.

| 단계 | 현재 동작 |
|---|---|
| Source observation | simulation/live source cadence에 따라 관측 생성 |
| live-ingestor | 약 5초 polling 기준으로 source 확인 |
| Generator prediction | 새 batch 수신 후 runtime prediction 실행 |
| Backend promotion | prediction result 수신 후 validation/promotion |
| Product UI | 약 10초 자동 refresh로 최신 Result 확인 |

### 10.3 Model Quality 발표 요약

모델 품질은 “정확도가 높다”가 아니라 release gate를 통과한 모델과 아직 운영 성숙도가 낮은 모델을 구분해 설명한다.

| Model | PR-AUC | ROC-AUC | Precision | Recall | F1 | 판단 |
|---|---:|---:|---:|---:|---:|---|
| CNC RandomForest | 0.696 | 0.890 | 0.546 | 0.679 | 0.605 | release candidate 유지 |
| CNC XGBoost | ranking metric 우수 | - | 0.345 | - | - | deployment precision floor 미달 |
| Compressor | 0.509 | - | 0.135 | 0.750 | 0.229 | recall은 확보했지만 precision 낮음 |

CNC 모델은 leave-one-site-out AP 0.604와 threshold 0.07 기준 operating point를 함께 설명한다. Compressor 모델은 한계를 숨기지 않고 operational maturity가 낮은 모델로 분리한다.

## 11. Team DB와 배포 구조

현재 production 서비스는 Mac mini의 containerized application과 Team DB를 사용한다.

주요 runtime service:

- frontend
- backend
- live-ingestor
- generator-runtime
- redis
- production support services

Backend와 live runtime은 Team DB를 authoritative operational database로 사용한다.

Team DB에는 다음과 같은 제품 기록이 유지된다.

- Product Result Artifact
- prediction inbox/promotion 기록
- Decision / Activity
- Work Order
- Inspection Result
- Maintenance Recommendation / Decision / Action / Event
- 사용자 및 프로젝트 scope

presentation용 workflow record를 seed할 수 있지만, 이는 live sensor observation이나 실제 고장 사실을 조작하는 용도가 아니라 **업무 milestone을 재현하기 위한 demo operational record**다.

## 12. 역할별 Frontend

Frontend는 같은 Event를 역할에 맞게 composition한다.

### Engineer

- 위험 기여 근거
- 점검 대상과 방법
- 센서/feature signal
- chart drill-down
- 정비 이력과 현장 기록

### Operations Manager

- 판단 대기
- workflow stage
- Decision Case
- 생산·재무 영향
- 업무 Action / 승인
- backlog / report

### Executive

- 전체 risk summary
- 생산·재무 impact
- decision bottleneck / Owner
- KPI
- report readiness
- 필요 시 evidence drill-down

역할별 UI는 서로 다르지만 selected Event identity는 공통으로 유지한다.

## 13. Evidence와 RAG Context

Reliability Assistant와 report는 검증 가능한 source context를 사용한다.

현재 데모 환경의 주요 governance fixture 예시는 다음과 같다.

- `SOP-DEMO-CNC-ROTATING-ASSEMBLY-001`: CNC 회전체 및 공구 계통 점검 SOP fixture
- `meeting:OPS-2026-08-17`: 운영회의 context fixture
- `meeting:EXEC-2026-08-31`: 경영 보고 원칙 fixture
- `decision:DEC-2026-0817-02`: 공구 마모 경보 판단 원칙 fixture

이 자료는 실제 한빛테크 사내문서가 아니라 **데모를 위해 버전 관리되는 synthetic governance context**다.

Assistant는 다음 원칙을 따른다.

- 선택 Case 문맥을 우선한다.
- 고장을 확정하지 않는다.
- 사람의 승인 권한을 대신하지 않는다.
- raw retriever 구현명이나 내부 token을 사용자 문장에 노출하지 않는다.
- 과도한 정밀도의 숫자를 그대로 출력하지 않는다.
- 근거가 없으면 추측 대신 limitation을 표현한다.

## 14. Report 생성

Report는 선택 Event와 Evidence를 기반으로 역할별 artifact를 생성한다.

현재 주요 report type:

- `inspection-summary`
- `operations-decision`
- `executive-brief`

추가 report type으로 maintenance effect 및 period risk 계열을 지원할 수 있다.

Report의 핵심 계약은 다음과 같다.

- report artifact가 참조하는 Event ID를 보존한다.
- role/report type에 따라 실제 artifact와 section이 바뀐다.
- Executive report에는 raw model token과 내부 구현명을 노출하지 않는다.
- 사실, 추정, 권고를 구분한다.
- print flow는 브라우저 출력 단계까지 검증한다.

## 15. Closed-loop 업무 흐름

예측 결과는 다음 업무 흐름으로 연결된다.

```text
Result / Event
→ Decision
→ Inspection Work Order
→ Inspection Result
→ Maintenance Recommendation
→ Human Approval
→ Maintenance Work
→ Completion
→ Re-observation / re-evaluation
```

중요한 것은 마지막 단계다. 정비 완료 event만으로 설비를 정상으로 확정하지 않는다.

현재 프로젝트에는 maintenance replay/runtime overlay를 통해 정비 후 observation을 다시 prediction pipeline에 연결하기 위한 계약과 구현이 존재한다. 다만 presentation seed 자체는 workflow milestone을 재현하는 데이터일 수 있으며, `risk_after`를 실제 새 Result Artifact 없이 임의로 정상화하지 않는다.

따라서 후속 Result가 없을 때 UI와 보고서는 **재관측 대기 / 결과 대기** 상태를 유지해야 한다.

## 16. KPI 원칙

운영 KPI는 단순 화면 update 시각이 아니라 업무 milestone에서 계산한다.

예:

- 점검 처리 시간: Work Order 요청 → Inspection Result 기록
- 승인 후 정비 착수 시간: 승인 milestone → Maintenance Action 시작
- Decision Lead Time: Event/Case 기준 판단 milestone
- Backlog: 현재 workflow state와 Owner를 기준으로 계산

데모 seed를 사용하는 경우에도 timestamp 간 관계를 명시적으로 구성하고, 의미 없는 `0분`을 성공 KPI처럼 표시하지 않는다.

## 17. 품질 관리와 Release Gate

이 프로젝트의 QA는 단순 화면 smoke가 아니라 product contract 검증을 포함한다.

### 17.1 Decision lineage

explicit Event를 선택한 뒤 다음을 검증한다.

```text
reload
→ live refresh tick 최소 2회
→ URL event_id
→ Case anchor
→ Decision Case surface
→ Evidence
→ Action
→ Report artifact
```

모두 같은 Event ID를 유지해야 한다.

복원할 수 없는 explicit Event는 최신 Event로 조용히 fallback하지 않고 차단 상태로 표시한다.

### 17.2 Adaptive UI

production telemetry에 따라 존재 여부가 달라지는 UI와 항상 지켜야 할 invariant를 분리한다.

예:

- Manager landing은 telemetry에 따라 달라질 수 있음
- Decision Case first blocks의 업무 순서는 invariant
- Executive first viewport는 risk/impact/bottleneck/report readiness 우선
- Engineer 원인 분석은 Evidence/Inspection을 chart보다 우선

### 17.3 Interaction

- 실제 chart hover tooltip
- SVG chart keyboard 진입과 arrow-key navigation
- report dialog뿐 아니라 실제 `window.print()` 호출
- mobile → desktop reverse resize
- navigation open/close
- Assistant drawer interaction

### 17.4 Responsive matrix

주요 viewport:

- 390×667
- 390×844
- 768×700
- 900×700
- 1024×700
- 1280×800
- 1440×800
- 1440×900
- 1920×1080

가로 overflow뿐 아니라 first viewport 정보 우선순위, sticky overlap, drawer, navigation 복원도 함께 확인한다.

### 17.5 Accessibility

- 사용자-facing 소형 텍스트 하한 유지
- 낮은 대비 muted text 방지
- chart point 수십 개를 각각 Tab stop으로 만들지 않음
- chart당 한 번 focus 후 방향키 탐색
- 버튼의 accessible name과 active/current state 제공

## 18. 주요 기능 요약

### 센서 / Observation

설비 관측을 공통 identity와 timestamp 계약으로 관리하고 live history를 제공한다.

### Model / Prediction

versioned Model Artifact와 runtime pipeline을 분리하며 prediction provenance를 보존한다.

### Product Result / Evidence

예측 결과와 판단 근거를 immutable artifact와 projection으로 제공한다.

### Decision Case

Event를 Evidence, Decision, Action, Outcome, Report로 연결한다.

### Role-aware Workspace

Engineer, Operations, Executive가 같은 Event를 각자의 질문에 맞는 정보 구조로 본다.

### Reliability Assistant

선택 Case와 검증 가능한 context를 기반으로 설명과 보고 문장 작성을 보조한다.

### Reporting

role/report type별 artifact를 생성하고 Event lineage를 유지한다.

### Closed-loop

점검, 승인, 정비 milestone을 추적하고 후속 관측 전에는 정상 상태를 확정하지 않는다.

## 19. 기대 효과

- 이상 설비의 우선순위를 빠르게 파악한다.
- 엔지니어가 raw chart 전에 Evidence와 점검 대상을 이해한다.
- 운영 관리자가 생산 영향과 다음 Action을 같은 Case에서 판단한다.
- 경영진이 세부 sensor보다 risk, impact, bottleneck을 먼저 본다.
- 예측 근거, 작업 기록, report가 동일 Event lineage로 연결된다.
- live telemetry가 갱신되어도 과거 Decision Case 근거를 보존할 수 있다.
- AI 설명과 보고서의 source traceability를 높인다.

## 20. 현재 한계

### Synthetic business context

생산 수량, 경제성, SOP, 회의록, 조직 context 중 일부는 데모용 synthetic fixture 또는 추정 model이다. 실제 MES, ERP, CMMS 실적과 동일하지 않다.

### Closed-loop re-evaluation

정비 workflow와 runtime overlay/replay 연결은 구현되어 있으나, 모든 presentation Case가 실제 post-maintenance Result Artifact까지 가지고 있는 것은 아니다. 발표 전에는 최소 1건의 고정 Case에 대해 `Before Result → Maintenance → After Observation → New Result`가 실제 artifact로 닫히는지 확인해야 한다. 후속 Result가 없는 경우 결과를 미확정으로 유지한다.

### Assistant/RAG evaluation scale

contract/eval 테스트는 grounding, source reference, tool boundary를 검증하지만, 발표용 객관 지표로는 별도 20~30개 synthetic/internal question set이 필요하다. 제출·발표 시에는 `Grounded answer rate`, `Unsupported claim reject`, `Correct source citation`, `Correct role framing`, `Boundary violation`을 수치로 제시하는 것을 목표로 한다.

### Team DB operational dependency

production demo는 Team DB, generator-runtime, live-ingestor, backend가 함께 정상 동작해야 한다. 발표 전 health 및 Event 복원 검증이 필요하다.

### Report lifecycle

보고 artifact 생성과 출력은 지원하지만, 실제 조직 적용을 위해서는 승인, 배포, revision governance를 더 강화할 필요가 있다.

### RAG governance

실제 운영 적용에서는 문서 권한, 최신성, 폐기 버전, 정보 보안 정책을 시스템적으로 연동해야 한다.

## 21. 향후 과제

- 실제 MES / ERP / CMMS 연동
- 실제 생산실적·재무실적 기반 impact model 보정
- Decision Lead Time 및 closed-loop KPI 장기 축적
- post-maintenance observation과 Outcome 자동 연결 강화
- report 승인 / 배포 / revision lifecycle 강화
- RAG 문서의 권한·최신성·버전 governance
- 모바일 현장 입력 및 offline fallback
- Demo Case를 명시적으로 관리하는 presentation fixture/selection 도구

## 22. 결론

Hanbit Tech Reliability Operations는 설비 이상 가능성을 예측하는 데서 끝나는 대시보드가 아니다.

하나의 Product Result를 Event로 고정하고, 이를 Evidence, 사람의 Decision, 현장 Action, 후속 Outcome, 역할별 Report로 연결한다. 엔지니어, 운영 관리자, 경영진은 서로 다른 첫 화면과 언어를 사용하지만 같은 사건의 provenance를 공유한다.

프로젝트의 핵심 가치는 AI가 판단을 대신하는 것이 아니라, **사람이 더 빠르고 신뢰성 있게 판단할 수 있도록 같은 사건과 근거를 역할별 업무 흐름 안에 배치하고 끝까지 추적 가능하게 만드는 것**이다.
