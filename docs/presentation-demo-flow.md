# Hanbit Tech Reliability Operations 10분 발표 흐름

이 문서는 4명이 `dashboard.oosu.dev`를 직접 시연하면서 10분 안에 프로젝트의 전체 기술 흐름과 제품 가치를 설명하기 위한 진행 가이드다.

발표는 기능 목록을 나열하는 방식이 아니라, **하나의 immutable Decision Case를 데이터/모델 → Evidence → Decision/Action → 역할별 Product/Report로 이어서 설명하는 방식**으로 진행한다.

현재 production은 Team DB의 live Result를 사용하고 첫 화면도 telemetry에 따라 adaptive하게 달라질 수 있으므로, 특정 설비나 최신 Event를 문서에 영구 고정하지 않는다. 발표 직전 아래 두 Case를 서로 다른 설비로 확정한다.

- `PROOF_EVENT_ID`: 점검·정비·후속 관측·새 Product Result가 모두 연결된 완료 증명 Case. 타임라인, Before/After, 운영·경영진 보고에 사용한다.
- `ACTIVE_EVENT_ID`: 실제 고위험 Result는 이미 존재하지만 점검 요청은 아직 생성하지 않은 진행형 Case. 운영 관리자 요청 → 현장 수락·기록 → 관리자 판단 → 보고서 초안 흐름에 사용한다.

위험 발생 순간을 발표 중 기다리거나 브라우저가 임의의 Result를 생성하게 하지 않는다. 실시간성은 실제 runtime에서 이미 수신된 최신 관측 시각과 Result 전환으로 증명한다. 별도의 synthetic tick은 `?demo_stream=simulated`를 명시한 내부 시연 모드에서만 허용하며 실제 runtime 화면과 혼용하지 않는다.

---

## 1. 발표 전체 메시지

한빛테크의 설비 이상 신호를 **모델의 재현 가능한 Result Artifact**, **검증 가능한 Evidence**, **사람의 Decision/Action**, **역할별 업무 화면과 Report**로 연결하고, 같은 Event lineage 안에서 끝까지 추적하는 Reliability Operations workspace를 만들었다.

발표에서 반복해서 사용할 핵심 흐름은 다음이다.

```text
Live Observation
→ Feature / Model Artifact
→ Product Result Artifact
→ Evidence
→ Decision Case
→ Inspection / Approval / Maintenance
→ Outcome / Re-observation
→ Role-based Product / Report
```

중요한 것은 예측 점수 하나가 아니라, **누가 어떤 근거로 무엇을 판단했고 이후 어떤 Action과 결과가 연결됐는지 보존하는 것**이다.

---

## 2. 4명 역할 분담

발표 파트는 실제 프로젝트 책임 축과 맞춘다.

| 발표자 | 프로젝트 책임 | 발표에서 설명할 축 | 주 화면 |
|---|---|---|---|
| **우수 (`oosuhada`)** | Product AI & Integration | 문제 정의, 역할별 Product UX, 전체 통합, Executive, 배포/Release | Login, 역할별 workspace, Executive Brief |
| **성민 (`smmini`)** | ML Lifecycle & Contract Engineering | Source → Feature/Label → Model Artifact, 모델 재현성과 provenance | Engineer 원인 분석, Model/Evidence 근거 |
| **광우 (`KOR-GANG`)** | Ontology Operations & Closed-loop | Evidence → Decision → Action → Maintenance → Feedback | Operations Decision Case, Closed-loop |
| **호범 (`enjoylonelines`)** | Backend Intelligence & Dynamic Reporting | Product Result/Evidence, grounded narrative, Assistant, 역할별 Report | Evidence, Assistant, Report |

발표 순서는 제품 이해가 자연스럽도록 다음처럼 구성한다.

```text
우수
제품 문제와 동일 Case 소개
↓
성민
센서/Feature/Model 근거
↓
광우
Decision / Closed-loop
↓
호범
Evidence-grounded Assistant / Report
↓
우수
Executive 관점과 전체 통합 마무리
```

우수가 처음과 마지막을 맡는 이유는 여러 Domain 결과가 최종적으로 하나의 사용자 Product로 합쳐지는 구조를 보여주기 위해서다.

---

## 3. 10분 시간 배분

권장 목표 시간은 **9분 30초**, 버퍼는 **30초**다.

| 시간 | 발표자 | 화면/내용 | 핵심 메시지 |
|---|---|---|---|
| 0:00–1:20 | 우수 | 문제 정의 → Login → 동일 `PROOF_EVENT_ID` | 같은 사건을 역할별로 다른 깊이로 본다 |
| 1:20–3:20 | 성민 | Engineer 원인 분석 + ML lineage | 관측값이 재현 가능한 Model Artifact와 Result로 바뀐다 |
| 3:20–5:45 | 광우 | Operations Decision Case + Closed-loop | Evidence가 사람의 Decision과 Action으로 이어진다 |
| 5:45–7:45 | 호범 | Evidence → Assistant → Report | AI 출력도 같은 Evidence와 Event에 grounded된다 |
| 7:45–9:30 | 우수 | Executive Brief + 역할 비교 + 배포/품질 | 여러 Domain을 하나의 운영 Product로 통합했다 |
| 9:30–10:00 | 버퍼 | 질문 대비 또는 마무리 | 예측이 아니라 Decision lineage가 핵심 |

시간이 밀리면 다음 순서로 줄인다.

1. Assistant 실질 응답 시연 생략
2. Chart drill-down 생략
3. Report type 두 개 이상 전환하지 않음
4. Executive 상세 drill-down 생략

**Decision Case와 Closed-loop는 생략하지 않는다.**

---

## 4. 발표 데이터 원칙

### 4.1 Gold Scenario와 Production Demo Case를 분리한다

`EVT-GS-002 / CNC-S04-L04-01`은 공구 마모와 토크 상호작용, SOP 연결을 설명하기 위한 **fixture 기반 Gold Scenario**다.

실제 발표 웹사이트는 Team DB에 저장된 immutable `RESULT#...`를 사용한다.

| 구분 | 목적 | 사용 방식 |
|---|---|---|
| Gold Scenario | 모델/근거 설명, 회귀 테스트 | `EVT-GS-002`, fixture 기반 |
| Production Demo Case | 실제 웹 시연 | 발표 전 고정한 Team DB `RESULT#...` |

Gold Scenario와 live Result가 같은 설비를 가리키더라도 같은 Event라고 설명하지 않는다.

### 4.2 발표 전에 반드시 고정할 값

```text
PROOF_EVENT_ID    = RESULT#...  # 완료 이력·Before/After·보고 증명
PROOF_ASSET_ID    = ...
ACTIVE_EVENT_ID   = RESULT#...  # 점검 요청부터 직접 수행할 별도 Case
ACTIVE_ASSET_ID   = ...
```

권장 Case 조건:

- Team DB에서 실제 복원 가능한 immutable `RESULT#...`
- Engineer / Operations / Executive / Report가 모두 열 수 있음
- 가능하면 closed-loop activity가 연결됨
- workflow 완료 시각이 미래가 아님
- 발표 도중 새 Result가 생겨도 기존 Case가 유지됨

발표 중 새 관측이 도착해도 `최신 Event 열기`를 누르지 않는다.

오히려 다음 메시지를 설명한다.

> 운영 의사결정에 사용한 Case는 새 관측이 들어와도 조용히 다른 Event로 바뀌지 않고 선택 당시 근거로 고정됩니다.

### 4.3 발표 전 보강 우선순위

다른 팀 발표 전사/피드백 기준으로 질문이 들어올 가능성이 높은 항목은 기능 추가보다 “화면에서 바로 확인 가능한 수치와 완결된 증거”다.

| 우선 | 보강 항목 | 발표에서 답해야 하는 질문 | 준비할 증거 |
|---|---|---|---|
| P0 | 정비 후 실제 재예측 Closed-loop | 정비 후 위험도가 실제로 내려간 결과가 있나요? | Before Result → Maintenance → After Observation → New Result |
| P0 | 발표용 고정 Case 재현성 | 발표 중 DB가 바뀌어도 같은 사건을 보여주나요? | `PROOF_EVENT_ID`, `ACTIVE_EVENT_ID`, deep link |
| P1 | 모델 성능 설명 | 정확도와 모델 선택 근거는 무엇인가요? | Model Quality 표, selected/rejected 근거 |
| P1 | “실시간” 정의 | 진짜 realtime인가요, polling인가요? | source/ingest/prediction/backend/UI timing 표 |
| P1 | Assistant/RAG 평가 | 근거 없는 답변을 어떻게 막나요? | groundedness/source/boundary scorecard |
| P1 | 생산·재무 영향 산식 | 생산 영향 숫자는 어디서 나왔나요? | 예상 정지시간 × 시간당 계획 생산량 × 단위 공헌이익 |
| P1 | Current Architecture 정본 | generator/backend/DB 책임이 무엇인가요? | Offline/Online architecture 한 장 |
| P2 | 실제 권한 차단 | AI나 Engineer가 승인할 수 있나요? | Engineer 승인 거부, Manager 승인 가능 화면 |
| P2 | 장애 대비 증거 | production demo가 흔들리면 어떻게 하나요? | 90초 backup video, 고정 snapshot |

발표 멘트는 “모든 기능이 완벽하다”가 아니라 “release gate를 통과한 것과 아직 운영 성숙도가 낮은 것을 구분한다”로 잡는다.

### 4.4 실시간 표현 원칙

“실시간 예측 시스템”이라고 뭉뚱그리면 위험하다. 현재 production 설명은 다음처럼 고정한다.

> 지속적으로 들어오는 관측을 runtime pipeline에서 처리하고, UI는 10초 주기로 최신 Result를 확인합니다.

| 단계 | 현재 설명 |
|---|---|
| Source observation | simulation/live source cadence로 관측 생성 |
| live-ingestor | 약 5초 polling 기준으로 source 확인 |
| Generator Runtime | 새 batch 수신 후 prediction 실행 |
| Backend validation/promotion | schema, scope, 중복, product contract 검증 후 Team DB 승격 |
| Product UI | 약 10초 자동 refresh로 최신 Result 확인 |

### 4.5 발표용 모델 품질 요약

성능 수치는 appendix가 아니라 시연 중 20~30초라도 보여준다.

| Model | PR-AUC | ROC-AUC | Precision | Recall | F1 | Release 판단 |
|---|---:|---:|---:|---:|---:|---|
| CNC RandomForest | 0.696 | 0.890 | 0.546 | 0.679 | 0.605 | Selected |
| CNC XGBoost | ranking 우수 | - | 0.345 | - | - | precision floor 미달로 rejected |
| Compressor | 0.509 | - | 0.135 | 0.750 | 0.229 | precision 낮아 operational maturity 제한 |

핵심 문장:

> CNC는 단순히 AUC가 높은 모델이 아니라 실제 알람 workload를 고려한 operating point를 통과한 RandomForest를 선택했습니다. 압축기 모델은 recall은 확보했지만 precision이 낮아, 한계를 먼저 공개하고 current artifact 기준으로 운영 성숙도를 분리했습니다.

---

## 5. 시연 전 브라우저 준비

발표 도중 로그인/탐색에 시간을 쓰지 않도록 같은 브라우저에서 아래 탭을 미리 준비한다.

### Tab 1 — Login / Product 소개

```text
https://dashboard.oosu.dev/login
```

### Tab 2 — Engineer

동일 `asset_id`, `event_id`가 포함된 Engineer deep link.

### Tab 3 — Operations

동일 `asset_id`, `event_id`가 포함된 Operations Decision Case deep link.

### Tab 4 — Executive / Report

동일 `asset_id`, `event_id`가 포함된 Executive 또는 Report deep link.

발표자는 새로 로그인하거나 검색하지 않고 탭만 넘긴다.

브라우저 조작 담당은 가능하면 **우수 1명으로 고정**한다. 발표자가 바뀔 때 노트북까지 서로 넘기면 화면 전환 시간이 늘고 실수가 생기기 쉽다.

---

## 6. 발표 전 Production 체크리스트

### 시스템

- [ ] `/login` 실제 로그인 성공
- [ ] frontend healthy
- [ ] backend healthy
- [ ] generator-runtime healthy
- [ ] live-ingestor running
- [ ] Team DB Result Artifact 조회 가능

### Decision lineage

- [ ] `PROOF_EVENT_ID` API/UI 복원 가능
- [ ] `ACTIVE_EVENT_ID`에 기존 진행 workflow가 없음
- [ ] reload 후 동일 Event 유지
- [ ] 최소 두 refresh tick 후 동일 Event 유지
- [ ] Case header / Evidence / Action / Report가 동일 Event 사용
- [ ] 새 관측 CTA가 선택 Case를 자동 교체하지 않음

### 발표용 workflow

- [ ] Operations Decision Case에 설명할 다음 Action 존재
- [ ] Closed-loop를 보여줄 경우 activity 존재
- [ ] Report artifact 생성 가능
- [ ] Assistant 사용 시 응답 문구 사전 확인

---

## 7. 파트 1 — 우수: 문제 정의와 Product 구조

### 시간

`0:00–1:20`

### 화면

`Login → 선택 Case anchor`

### 보여줄 것

- Hanbit Tech / Reliability Operations
- 엔지니어 / 운영 관리 / 경영진 역할
- 역할 설명은 info popover로 숨겨져 있고 선택 UI는 간결한 점
- 발표/프로젝터 preset
- 동일 `PROOF_EVENT_ID`

### 설명 순서

#### 1. 문제 정의

> 제조 현장에서 예측 결과가 만들어져도 실제 현장 점검, 운영 승인, 정비 실행, 경영 보고가 각각 분리되면 결과가 업무로 이어지기 어렵습니다.

#### 2. 제품의 해결 방식

```text
Event
→ Evidence
→ Decision
→ Action
→ Outcome
→ Report
```

#### 3. 역할별 UI

> 모든 사람이 같은 대시보드를 보는 것이 아니라 같은 Event를 기준으로 엔지니어는 원인과 점검 근거, 운영 관리자는 생산 영향과 Action, 경영진은 전체 리스크와 의사결정 병목을 먼저 봅니다.

### 성민에게 넘기는 멘트

> 그럼 이 Event가 단순한 화면용 점수가 아니라 어떤 데이터와 모델 계약을 거쳐 만들어졌는지 성민님이 이어서 설명하겠습니다.

---

## 8. 파트 2 — 성민: Source → Feature → Model Artifact → Engineer Evidence

### 시간

`1:20–3:20`

### 담당 축

**ML Lifecycle & Contract Engineering**

### 화면

`Engineer · 원인 분석`

현재 Engineer IA:

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

### 설명할 기술 흐름

```text
Source Observation
→ Versioned Dataset
→ Feature / Label
→ Model Training / Evaluation
→ immutable Model Artifact
→ Runtime Prediction
```

여기서 중요한 점은 모델 파일만 저장하는 것이 아니다.

- Dataset version
- Feature schema
- Label schema
- Model version
- metrics
- checksum
- history requirement
- provenance

를 같이 보존해 같은 결과가 어떤 입력과 모델에서 나왔는지 추적 가능하게 만든다.

### 화면에서 보여줄 순서

```text
위험 기여 근거
→ 점검 대상
→ Signal
→ 필요 시 Chart
```

### 강조할 것

- 현재값 / 이동 평균 / 통계 feature가 서로 구분됨
- raw token보다 사용자 의미가 우선 표시됨
- 위험 기여 factor가 단순 전역 모델 설명이 아니라 현재 Event의 판단 근거로 연결됨
- chart는 필요할 때만 drill-down

Gold Scenario를 설명해야 할 때는 다음 정도만 예로 든다.

```text
공구 마모
토크
회전 속도
```

하지만 `PROOF_EVENT_ID`의 factor가 다르면 실제 화면의 factor를 그대로 설명한다.

### 핵심 멘트

> 이 화면의 위험도는 임의로 만든 UI 값이 아니라 버전이 고정된 데이터와 Model Artifact를 거쳐 생성된 결과이고, 어떤 feature가 판단에 연결됐는지 provenance를 추적할 수 있습니다.

### 광우에게 넘기는 멘트

> 여기까지가 이상을 발견하고 근거를 만드는 단계입니다. 이제 이 Evidence가 실제 사람의 판단과 작업으로 어떻게 이어지는지 광우님이 보여드리겠습니다.

---

## 9. 파트 3 — 광우: Evidence → Decision → Action → Maintenance

### 시간

`3:20–5:45`

### 담당 축

**Ontology Operations & Closed-loop**

### 화면

`Operations · Decision Case`

현재 Operations IA:

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

### 설명 순서

```text
현재 Workflow 단계
→ Decision
→ 생산 영향
→ Action
→ Closed-loop lineage
```

### 핵심 메시지

> 모델이 추천했다고 바로 정비가 실행되는 구조가 아닙니다. Evidence를 기준으로 사람이 점검 요청, 정비 권고, 승인, 작업 실행을 명시적으로 기록합니다.

### 보여줄 closed-loop

먼저 동일 `PROOF_EVENT_ID`에서 다음 완료 흐름을 보여준다.

```text
Result / Evidence
→ Inspection Work Order
→ Inspection Result
→ Recommendation
→ Human Decision
→ Maintenance Work Order
→ Maintenance Action
→ Maintenance Event
→ Follow-up Observation
→ New Product Result
```

그 다음 `ACTIVE_EVENT_ID`로 전환해 점검 요청 생성 → 현장 수락 → 점검 결과 기록까지만 직접 수행한다. 위험 발생을 기다리거나 완료 증명 Case에 새 작업을 덧붙이지 않는다.

### 강조할 것

- Recommendation과 Decision은 분리됨
- 사람이 승인해야 Action이 진행됨
- WorkOrder / MaintenanceAction / Activity가 Event에 연결됨
- 생산 영향은 추정치이며 실제 회계 손실이 아님
- 정비 완료와 정상 판정은 다름

### 반드시 말할 한계

> 정비 완료 기록만으로 설비가 정상이라고 확정하지 않습니다. 정비 이후 새 관측이 들어오고 같은 prediction pipeline에서 다시 평가돼야 조치 효과를 확인할 수 있습니다.

presentation seed의 `maintenance.completed`만 있는 경우 실제 위험 감소를 주장하지 않는다.

### 호범에게 넘기는 멘트

> 이렇게 Decision과 Action의 이력이 남으면 이후 설명과 보고도 임의의 문장이 아니라 같은 Event와 Evidence를 기준으로 만들어져야 합니다. 그 부분을 호범님이 이어서 설명하겠습니다.

---

## 10. 파트 4 — 호범: Product Result → Evidence → Assistant → Report

### 시간

`5:45–7:45`

### 담당 축

**Backend Intelligence & Dynamic Reporting**

### 기술 흐름

```text
Prediction Result
→ Backend validation / promotion
→ Product Result Artifact
→ Evidence projection
→ Grounded Narrative
→ Role-specific Report
```

### Evidence에서 설명할 것

- Product Result Artifact가 판단 원천
- Evidence는 해당 Result의 sensor/source/provenance와 연결
- Evidence가 없으면 임의로 생성하지 않고 unavailable/gap으로 표현
- 보고서와 Assistant도 같은 Event ID 사용

### Assistant

추천 질문은 하나만 사용한다.

```text
이 Case에서 운영 관리자가 지금 판단해야 할 것은 뭐야?
```

또는

```text
경영진 보고 시 사실, 추정, 권고를 구분해줘
```

### Assistant 핵심 메시지

> Reliability Assistant는 일반 챗봇이 아니라 현재 선택한 Case의 Evidence와 운영 context를 기준으로 답합니다. 설명을 보조하지만 고장을 확정하거나 승인 권한을 대신하지 않습니다.

시간이 부족하거나 응답이 늦으면 Assistant는 즉시 생략한다.

### Report

가능하면 두 report type만 보여준다.

```text
운영 판단 보고
Executive Brief
```

보여줄 것:

- report type 변경
- 실제 artifact ID 변경
- `Case {PROOF_EVENT_ID}` 유지
- source/evidence reference

### 핵심 멘트

> 보고서는 화면을 캡처한 문서가 아니라 같은 Product Result와 Evidence를 역할별 언어로 변환한 추적 가능한 artifact입니다.

### 우수에게 넘기는 멘트

> 지금까지 데이터, 모델, Evidence, 업무 Action과 Report가 각각 연결되는 것을 봤습니다. 마지막으로 이 결과들이 실제 사용자 역할과 배포 환경에서 하나의 제품으로 어떻게 통합됐는지 우수님이 정리하겠습니다.

---

## 11. 파트 5 — 우수: Executive Brief와 Product Integration 마무리

### 시간

`7:45–9:30`

### 화면

`Executive Brief`

현재 Executive IA:

```text
PRIMARY · 경영 판단
  Executive Brief
  운영 리스크
  운영 KPI
  의사결정 병목
  보고 산출물

EVIDENCE · 근거/상세
  정비 효과
  개선 과제
  설비 상태 근거
```

### Executive Brief 설명 순서

```text
전체 리스크
→ 생산·재무 영향
→ 막힌 Decision / Owner
→ Report readiness
```

### 핵심 메시지

> 경영진은 센서 12개와 정비 로그를 먼저 볼 필요가 없습니다. 같은 Event를 기준으로 전체 리스크, 생산 영향, 의사결정 병목과 보고 준비 상태만 우선 보고, 필요할 때 상세 Evidence로 내려갑니다.

### 제품 통합에서 강조할 것

- 하나의 Event를 역할별로 다른 정보 밀도로 표현
- Engineer / Operations / Executive가 같은 source를 공유
- Team DB가 operational source of truth
- frontend / backend / generator-runtime / live-ingestor가 실제 배포 환경에서 연결됨
- E2E는 화면 렌더만 보는 것이 아니라 Event lineage, print, hover, keyboard, responsive 상태를 검증

### 최종 멘트

> 저희 프로젝트의 핵심은 예측 모델 하나를 보여주는 것이 아닙니다. 하나의 설비 이상 Event를 재현 가능한 모델 결과와 Evidence로 만들고, 사람의 Decision과 Action을 거쳐 경영 보고까지 같은 lineage로 연결한 제조 Reliability Operations 제품입니다.

---

## 12. 발표 중 반드시 피할 표현

### 피할 표현

- “AI가 고장을 확정합니다.”
- “위험도 87%니까 곧 고장납니다.”
- “생산 영향 금액은 실제 손실입니다.”
- “정비 완료 버튼을 누르면 정상입니다.”
- “LLM이 정비 판단을 합니다.”
- “Gold Scenario와 지금 live Event는 같은 사건입니다.”

### 권장 표현

- “현재 관측과 모델 근거에서 이상 가능성이 높아 점검이 필요한 상태입니다.”
- “위험도는 운영 우선순위를 위한 예측 결과입니다.”
- “생산·재무 영향은 의사결정용 추정치입니다.”
- “Recommendation과 최종 Decision은 분리되어 있습니다.”
- “정비 완료와 정상 판정은 분리합니다.”
- “후속 관측을 같은 pipeline으로 다시 평가합니다.”
- “Assistant는 검증된 Evidence를 바탕으로 설명과 보고서 작성을 보조합니다.”

---

## 13. 발표자별 절대 놓치면 안 되는 한 문장

### 우수

> 같은 Event를 역할마다 다른 깊이로 보여주되 source와 lineage는 하나로 유지합니다.

### 성민

> 결과가 어떤 Dataset, Feature, Model Artifact에서 나왔는지 재현 가능하게 보존합니다.

### 광우

> 모델 추천이 바로 실행되는 것이 아니라 사람의 Decision과 WorkOrder를 거쳐 Closed-loop가 진행됩니다.

### 호범

> Assistant와 Report도 임의로 문장을 만드는 것이 아니라 같은 Product Result와 Evidence에 grounded됩니다.

---

## 14. 발표 중 화면 전환 원칙

### 발표자가 바뀔 때

화면을 처음부터 다시 찾지 않는다.

```text
우수 → Engineer tab
성민 → Operations tab
광우 → Report/Assistant tab
호범 → Executive tab
우수 → 마무리
```

전환 시간 목표는 **5초 이하**다.

### 새 관측이 도착했을 때

`최신 Event 열기`를 누르지 않는다.

현재 Case가 유지되는 것을 설명하고 계속 진행한다.

### adaptive landing이 예상과 다를 때

첫 화면을 고치려고 하지 말고 준비한 deep link를 사용한다.

---

## 15. 발표 실패 시 fallback

### Assistant가 늦을 때

즉시 생략하고 Report로 넘어간다.

### live Case의 데이터가 바뀌었을 때

준비한 `PROOF_EVENT_ID` deep link로 다시 연다.

### closed-loop activity가 보이지 않을 때

없는 완료 상태를 만들지 않는다.

Decision Case의 현재 단계까지만 설명하고 다음 계약을 말한다.

### Chart가 늦게 로드될 때

Evidence factor와 Inspection target만 설명한다.

### production network가 순간적으로 불안정할 때

재로그인/새 Case 탐색을 반복하지 말고 준비한 탭을 먼저 사용한다.

---

## 16. 최종 30초 마무리

시간이 남으면 우수가 다음 구조로 정리한다.

```text
성민
재현 가능한 Model Truth

호범
Prediction / Evidence / Grounded Narrative Truth

광우
Decision / Action / Maintenance Closed-loop

우수
Role-based Product / LLM / Integration / Release
```

최종 문장:

> 네 명이 서로 다른 기능을 따로 만든 것이 아니라, Source에서 Model Artifact, Evidence, Decision, Action, Report까지 각자의 책임 경계를 이어 하나의 Reliability Operations 제품으로 완성했습니다.
