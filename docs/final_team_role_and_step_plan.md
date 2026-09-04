# 최종 역할 분배 및 Step별 실행 계획

> 목적: 4명이 각자 하나의 기능을 만들고 끝나는 방식이 아니라, **프로젝트 종료까지 각자 하나의 전문 축을 계속 소유하면서 서로의 산출물을 다음 단계로 연결하는 구조**로 역할을 고정한다.
>
> 원칙: 역할은 기술 스택 하나로 제한하지 않는다. 각 담당자는 자기 전문 축에 대해 계약 → 구현 → 통합 → 검증 → 배포 → 발표까지 계속 책임진다.

---

## 1. 최종 역할 분배

| 사람 | 프로젝트 전체를 관통하는 역할 | 최종 책임 | 주요 산출물이 넘어가는 곳 |
|---|---|---|---|
| **성민 (`smmini`)** | **ML Lifecycle & Contract Engineering** | Source를 학습 가능한 Feature/Label로 만들고, Model Artifact를 발행하며, 모델 계약·재학습·평가·버전·재현성을 프로젝트 종료까지 유지 | → **호범** Runtime, → **우수** CI/Report provenance |
| **호범 (`enjoylonelines`)** | **Backend Intelligence & Dynamic Reporting** | Model Artifact를 Product Result/Evidence로 만들고, Evidence-grounded 동적 보고서의 내용·grounding·생성 규칙을 책임 | → **광우** Closed-loop, → **우수** Product/LLM runtime |
| **광우 (`KOR-GANG`)** | **Ontology Operations & Closed-loop** | 분석 결과를 Recommendation/Decision/Action/Maintenance/Ontology state로 되돌리고 업무 피드백 루프를 실제로 동작시킴 | → **호범** Report operational context, → **우수** Product surface |
| **우수 (`oosuhada`)** | **Product AI & Integration** | 여러 Domain 결과를 Product API/Report Backend/LLM Runtime/Frontend로 조합하고, CI·E2E·배포·Release까지 실제 사용자 서비스로 완성 | → **전체 팀** Acceptance/Release, → **최종 사용자** |

### 역할을 한 문장으로 요약하면

```text
성민 = 모델의 전체 생명주기와 계약을 끝까지 책임진다.

호범 = 모델 결과를 제품의 판단 근거로 만들고,
       그 근거를 바탕으로 동적 보고서가 무엇을 말할 수 있는지 책임진다.

광우 = 분석 결과를 실제 Decision / Action / Maintenance로 되돌려
       온톨로지 기반 업무 Closed-loop를 완성한다.

우수 = 세 사람의 결과를 Backend Product/AI 계층과 Frontend에서 조합하고,
       CI / E2E / 배포까지 사용자에게 전달되는 하나의 제품으로 완성한다.
```

---

## 2. 프로젝트 전체 연결 구조

```text
Biz-CollabCraft/gen_data
Canonical V3.1 source / simulation / synthetic data
        ↓
┌─────────────────────────────────────────────────────────────┐
│ 성민 — ML Lifecycle & Contract Engineering                 │
│ Extraction → Feature → Label → Train → Evaluate            │
│ → Model Artifact → Retrain / Version / Quality             │
└─────────────────────────────────────────────────────────────┘
        ↓ Model Artifact + Contract
┌─────────────────────────────────────────────────────────────┐
│ 호범 — Backend Intelligence & Dynamic Reporting            │
│ Artifact Load → Runtime Inference → Product Result          │
│ → Evidence → Report Grounding → Dynamic Narrative Rules    │
└─────────────────────────────────────────────────────────────┘
        ↓ Product Result / Evidence
┌─────────────────────────────────────────────────────────────┐
│ 광우 — Ontology Operations & Closed-loop                   │
│ RiskEvent → Recommendation → Decision → Action             │
│ → Maintenance → Ontology State → Feedback                  │
└─────────────────────────────────────────────────────────────┘
        ↓ Result / Evidence / Decision / Action / Activity
┌─────────────────────────────────────────────────────────────┐
│ 우수 — Product AI & Integration                            │
│ Product Aggregation API → Static Report Backend            │
│ → LLM Runtime Integration → Frontend / Visualization       │
│ → CI / E2E / Deployment / Release                          │
└─────────────────────────────────────────────────────────────┘
        ↓
Overview / Objects / Operations / Executive Brief / API
```

이 구조에서 한 사람이 자기 앞 단계만 끝내고 빠지는 것이 아니라, 뒤 단계에서 발견되는 계약 불일치·품질 문제·통합 이슈를 자기 전문 축에서 계속 해결한다.

---

# 3. 사람별 프로젝트 전체 책임

## 3.1 성민 (`smmini`)

### Role: ML Lifecycle & Contract Engineering

성민의 역할은 단순히 “모델 하나 학습시키기”가 아니다.

**데이터가 모델 입력으로 변환되는 순간부터 최종 발표 환경에서 동일 Artifact가 재현되고 설명될 때까지 ML lifecycle 전체를 책임진다.**

### Primary Ownership

```text
Source Data
→ Extraction / Profiling
→ Semantic Mapping
→ Feature Engineering
→ Label Generation
→ Training / Evaluation
→ Model Artifact Publish
→ Artifact Version / Reproducibility
→ Retraining / Quality Regression
→ Runtime Compatibility Support
```

### 프로젝트 전반 담당 작업

- Canonical source extraction / profiling
- asset별 시계열 격리와 deterministic ordering
- Feature Engineering
- Feature naming contract
- Label contract와 prediction horizon
- active failure 구간 제외 및 leakage 방지
- 모델 학습 / 평가
- Model Artifact v1.0 publish
- manifest / SHA-256 / provenance
- immutable / atomic publish
- training config와 dataset version 기록
- 모델 재학습 / artifact version 갱신
- Backend loader와 Artifact compatibility 검증 지원
- inference 결과 이상 시 feature parity / model input 문제 분석
- Top factor / explainability에 필요한 모델 출력 의미 정리
- Closed-loop가 소비하는 모델 결과와 Feature 의미의 정합성 검토
- Report에 들어갈 model version / metrics / limitation provenance 제공
- golden vector / artifact round-trip test 유지
- 최종 발표용 모델 결과 재현성 검증

### Backend API / Artifact 계약에서의 역할

성민은 Backend implementation owner가 아니라 **ML producer 관점의 계약 작성자**다.

```text
성민
Model Artifact / Prediction Output Contract 제안
        ↓
호범
Backend consumer 관점 검토
        ↓
합의된 Contract
        ↓
호범 / 우수
Runtime / Product integration 구현
```

### Model Artifact 필수 산출물

```text
manifest.json
model.joblib
feature_schema.json
label_schema.json
history_requirement.json
metrics.json
```

### 프로젝트 후반에도 계속 맡는 일

Model Artifact가 발행됐다고 성민 역할이 끝나지 않는다.

- Backend에서 Artifact를 못 읽으면 producer/consumer contract 원인 분석
- 데이터 분포가 바뀌면 retraining 필요 여부 판단
- 모델 버전 변경 시 regression 비교
- UI/Report의 top factor가 모델 의미와 다르면 semantic alignment 수정
- Closed-loop 입력이 Model Artifact와 Feature contract 의미를 왜곡하지 않는지 검토
- 최종 E2E에서 동일 input → 동일 model result 재현성 확인
- 발표에서 dataset → feature → model → artifact lineage 설명

### 하지 않을 일

- Product Result Artifact 최종 producer 소유
- Evidence 최종 producer 소유
- Generator가 `/internal/predict*` 제품 runtime을 소유
- Product UI 구현
- 범용 Feature Store 구축
- 범용 Model Registry 플랫폼 구축
- 필요하지 않은 multi-version compatibility framework 확장

### 최종 완료 조건

> **학습 코드가 동작하는 것뿐 아니라, 최종 배포에서 사용 중인 Model Artifact의 입력·출력·버전·평가·재현성을 팀이 설명하고 다시 생성할 수 있어야 완료다.**

---

## 3.2 호범 (`enjoylonelines`)

### Role: Backend Intelligence & Dynamic Reporting

호범은 **모델 결과를 제품에서 신뢰할 수 있는 판단 근거로 변환하는 Backend Intelligence 축**을 책임진다.

그리고 Product Result / Evidence가 안정화된 이후에는 **Evidence-grounded 동적 보고서 기능의 feature owner**를 맡는다.

호범 파트의 개발 역량 포인트는 단순한 LLM 출력 검증 테스트가 아니라, ML Artifact를 제품 Backend Runtime으로 전환하고 그 결과를 Evidence API와 Grounded Report / LLM 입력까지 연결하는 제품화 레이어다.

### Primary Ownership

```text
Model Artifact
→ Artifact Validation / Load
→ Runtime Inference
→ Product Result Artifact
→ Evidence Payload / Provenance
→ Event Evidence Projection
→ Report Grounding Contract
→ Dynamic Report Content / Prompt Rules
→ Narrative Validation / Limitation Policy
```

### Backend Intelligence 담당 작업

- Model Artifact loader
- manifest / `artifact_files[*].sha256` / compatibility validation
- current observation 조회
- history requirement 처리
- runtime inference orchestration
- failure probability / failure type / status 산출
- Product Result `normal / attention / warning / critical`과 runtime
  `available / unavailable` 상태를 분리해 처리
- Product Result Artifact 생성
- `evidence_payload` producer-side enrichment
- source field evidence
- sensor evidence
- component hypothesis
- `evidence_gap` invariant
- Evidence provenance
- Event Evidence projection
- Product API endpoint 구현
- DB persistence / query
- corrupt / unsupported Artifact fail-fast
- Backend integration test

### Dynamic Report 담당 작업

호범이 **동적 보고서 feature owner**다.

다만 “LLM SDK 연결과 전체 제품 통합”까지 한 사람에게 몰지 않고 역할을 다음처럼 분리한다.

#### 호범이 소유하는 것

- 어떤 Product Result / Evidence가 보고서 근거가 될 수 있는지 정의
- Report Grounding Contract
- 정적 보고서에서 LLM에 전달할 허용 필드 정의
- prompt template의 내용 구조
- 생산 운영 의사결정자용 narrative 요구사항
- `evidence_gap` / `limitations` 문장화 규칙
- Evidence에 없는 사실을 말하지 못하도록 generation rule 정의
- dynamic report output schema
- narrative validation rule
- 숫자 / 상태 / 원인 consistency validation
- hallucination guard 기준
- deterministic fallback이 필요한 조건 정의
- 동적 보고서 품질 테스트 케이스

#### 우수에게 넘기는 것

```text
Report Grounding Contract
Prompt / Output Contract
Validation Rules
        ↓
우수
LLM provider runtime / orchestration / API / UI / deployment
```

즉 **동적 보고서가 무엇을 말해야 하고 무엇을 말하면 안 되는지는 호범 책임**, 실제 외부 LLM provider 연결과 제품 runtime orchestration은 우수 책임이다.

### 프로젝트 후반에도 계속 맡는 일

- Frontend/Report에서 필요한 Evidence가 부족하면 producer enrichment 보강
- 광우 Action 결과가 Report에 포함되도록 projection 구조 조정
- LLM report에서 근거 없는 문장이 발견되면 grounding/prompt/validation 수정
- API response와 Report source 데이터 consistency 검증
- Backend 성능 / unavailable / 오류 경로 검증
- 최종 발표 시 Prediction → Evidence → Dynamic Report lineage 설명

### 하지 않을 일

- Feature Engineering 정책 소유
- Label 정책 소유
- 모델 학습 소유
- LLM provider SDK / secret / deployment platform 단독 소유
- Executive Brief Frontend surface 소유
- Generator daemon 확장
- 장기 범용 계약 거버넌스 플랫폼 구축

### 최종 완료 조건

> **Backend가 Model Artifact를 사용해 Product Result/Evidence를 안정적으로 제공하고, 동적 보고서가 그 Evidence에 근거해 검증 가능한 문장만 생성하도록 규칙과 품질을 보장해야 완료다.**

---

## 3.3 광우 (`KOR-GANG`)

### Role: Ontology Operations & Closed-loop

광우는 “분석 결과를 보여주는 것”에서 끝내지 않고, **그 결과가 실제 업무 Decision과 Action으로 다시 돌아가는 온톨로지 Closed-loop**를 책임진다.

범용 플랫폼을 만드는 것이 아니라 대표 Use Case 하나를 E2E로 완성해 프로젝트의 온톨로지 서비스성을 증명한다.

광우 파트의 개발 역량 포인트는 단순히 온톨로지 용어를 문서화하는 것이 아니라, Product Result / Evidence를 실제 Decision / Action / Activity / Equipment state로 전환하는 업무 workflow 레이어다.

Closed-loop의 사용자 역할·Action·Product API/UI 소비 규칙은
[`closed-loop-product-consumption-contract.md`](./closed-loop-product-consumption-contract.md)를 정본으로
사용한다. `process_manager`는 시스템 Admin이 아닌 생산 운영 의사결정자이며,
`process_engineer`와 `maintenance_technician`은 현장 엔지니어와 정비 작업자로 구분한다.

### Primary Ownership

```text
Equipment / Process Context
→ RiskEvent
→ Evidence Association
→ RecommendedAction
→ Decision
→ WorkOrder
→ MaintenanceAction
→ MaintenanceEvent
→ Ontology State Update
→ Activity / Audit Trail
→ Feedback to Product / Report
```

### 대표 Use Case

**CNC Tool Replacement Closed-loop**

```text
CNC 위험 상승
        ↓
Product Result / Evidence
        ↓
현장 엔지니어 점검·분석 근거
        ↓
RecommendedAction
        ↓
생산 운영 의사결정자 Decision
        ↓
승인된 WorkOrder
        ↓
정비 작업자의 TOOL_REPLACEMENT Action
        ↓
Maintenance Event
        ↓
Equipment / Ontology State Update
        ↓
Activity 기록
        ↓
Dashboard / Report에 결과 재반영
```

### 프로젝트 전반 담당 작업

- Equipment / component / process context 정리
- RiskEvent와 Equipment 관계
- Evidence와 RiskEvent 관계
- RecommendedAction semantics
- Decision model
- RecommendedAction
- MaintenanceAction
- MaintenanceEvent
- Action state transition
- Activity / audit trail
- Ontology state update
- before / after state 비교
- 조치 이후 다음 Event / Result와의 연결
- Closed-loop API
- Operations 화면이 소비할 workflow state 제공
- Report가 소비할 Decision / Action / Activity context 제공
- Recommendation 후보와 승인된 실제 Action을 구분
- 실제 설비 자동제어가 아닌 human approval 기반 업무 반영

### 프로젝트 후반에도 계속 맡는 일

- 모델/Backend 결과를 실제 RiskEvent로 연결
- Evidence가 새로 추가되면 Ontology association 보강
- Operations UI에서 필요한 workflow state 개선
- 보고서에서 “무엇을 판단했고 무엇을 실행했는가” 데이터 제공
- E2E에서 Action 완료 후 state가 실제로 되돌아오는지 검증
- 발표에서 prediction → decision → action → feedback loop 시연

### 최소 관계

```text
Equipment
  └─ HAS_RISK_EVENT → RiskEvent
                         │
                         ├─ SUPPORTED_BY → Evidence
                         │
                         └─ RECOMMENDS → RecommendedAction
                                             │
Manager ─ APPROVES ─────────────────────────┘
                                             ↓
                                     MaintenanceAction
                                             ↓
                                      MaintenanceEvent
                                             ↓
                                       UPDATES Equipment
```

### 최소 API 범위

```text
POST /events/{event_id}/decision
POST /events/{event_id}/actions
POST /actions/{action_id}/complete
GET  /events/{event_id}/activity
```

### 하지 않을 일

- 범용 Ontology Engine 구축
- 범용 Workflow Engine 구축
- MES / ERP 전체 구현
- 실제 설비 자동 정지
- 범용 Agent framework 확장
- 모든 공정 / 모든 Action 유형 구현

### 최종 완료 조건

> **한 개 대표 CNC Event에서 Evidence → Recommendation → Decision → Action → Maintenance → Ontology 상태 갱신 → Dashboard/Report 재반영까지 한 사이클이 실제로 돌아야 완료다.**

---

## 3.4 우수 (`oosuhada`)

### Role: Product AI & Integration

우수는 Frontend만 담당하지 않는다.

**각 Domain의 결과를 실제 제품이 소비할 수 있도록 Backend application layer에서 조합하고, Report Backend와 LLM Runtime을 연결한 뒤 Frontend·CI·E2E·배포까지 책임지는 Full-stack Product Integration 역할**을 맡는다.

우수 파트의 개발 역량 포인트는 화면을 단순히 꾸미는 것이 아니라, Backend Result / Evidence, Closed-loop Action, Report / LLM output을 사용자가 따라갈 수 있는 제품 경험과 E2E 검증으로 묶는 통합 레이어다.

### Primary Ownership

```text
Diagnosis Result / Evidence       ← 호범
Decision / Action / Activity      ← 광우
Model provenance / metrics        ← 성민
              ↓
Product Aggregation / Report Context Backend
              ↓
Static Executive Brief Backend
              ↓
LLM Provider Runtime / Orchestration
              ↓
Watcher-driven Summary Materialization
              ↓
Product API / Frontend / Visualization
              ↓
CI / E2E / Deployment / Release
```

### Backend / Product Application 담당 작업

- Product-oriented aggregation API
- 여러 Domain API 결과 orchestration
- Report Context Builder
- deterministic Static Report model
- Executive Brief backend endpoint
- LLM provider adapter 실제 연결
- API key / environment configuration
- LLM client runtime
- timeout / retry
- structured output parsing
- schema validation
- report generation orchestration
- generation status
- watcher-driven summary materialization
- summary key / cache / persistence
- snapshot diff based regeneration
- LLM failure → deterministic report fallback wiring
- Report API와 Frontend 연결

예시 Product/Application API:

```text
GET  /api/equipment/{equipment_id}/overview
GET  /api/events/{event_id}/workspace
GET  /api/reports/{event_id}/context
POST /api/reports/{event_id}/generate
GET  /api/reports/{report_id}
POST /api/reports/{report_id}/regenerate
GET  /api/agent-review-summaries/{summary_id}
```

위 API는 새로운 Domain Truth를 만들기 위한 것이 아니라 기존 Domain 결과를 제품 단위로 조합하는 application layer다.

```text
성민 / 호범 / 광우
= Domain Truth Producer

우수
= Product/Application Orchestrator
```

### Frontend / Visualization 담당 작업

- Overview
- Objects
- Operations
- Executive Brief
- role-aware surface
- sensor trend
- failure probability
- state timeline
- top contributing factors
- Evidence / provenance visualization
- 정비 전후 상태와 Maintenance history
- Decision / Action UI
- Maintenance Activity
- loading / empty / error / unavailable
- cross-screen equipment/event/result identity consistency

### Static Executive Brief 담당

정적 보고서는 우수가 owner다.

```text
Product Result
Evidence
Decision
Action
Activity
Model Provenance
       ↓
Report Context Builder
       ↓
Deterministic Static Report
       ↓
Executive Brief UI
```

정적 보고서는 LLM이 없어도 반드시 동작해야 한다.

### LLM Runtime에서의 역할

동적 보고서와 Agent Review Summary의 **내용/grounding feature owner는 호범**이지만, 실제 LLM Runtime,
watcher orchestration, 저장된 Summary API와 제품 연결은 우수가 맡는다.

```text
호범
Grounding / Prompt / Output / Validation Contract
        ↓
우수
LLM Provider Adapter
→ Runtime Invocation
→ Structured Output Parse
→ Validation Pipeline 연결
→ Static Fallback
→ Summary Materialization
→ Report / Agent Review Summary API
→ Executive Brief / Workflow UI
```

따라서 우수도 LLM과 Backend를 직접 구현하지만, Evidence 의미나 narrative truth rule을 임의로 변경하지 않는다.
UI 사이드뷰 열림, 탭 전환, 새로고침 같은 presentation event는 LLM 생성 트리거가 아니다. Product
Result/Evidence snapshot, source checksum, prompt/schema/model version이 달라졌을 때 watcher가
Summary를 재생성하고, UI와 Report는 저장된 Summary를 조회한다.

### CI / Acceptance / Release 담당 작업

- architecture rules
- contract validation
- Model Artifact publish/load round-trip
- Backend integration gate
- Product API contract test
- Closed-loop E2E
- Frontend unit/build
- Playwright user journey
- Docker runtime smoke
- Vercel / Render / Neon integration
- preview deployment verification
- final release gate
- demo account / final URL / fallback scenario

### 프로젝트 후반에도 계속 맡는 일

- 새 Backend 결과가 Product UI와 Report에 실제로 연결되는지 검증
- Domain 사이 ID / timestamp / status 불일치 해결
- LLM Runtime 오류와 fallback UX 검증
- watcher 기반 Summary materialization, stale/error/fallback 상태 검증
- 배포 환경 secret / proxy / CORS / DB 연결 검증
- 전체 시나리오 Playwright/E2E 유지
- 최종 발표 환경과 demo flow 책임

### 하지 않을 일

- ML Feature / Label 의미 임의 변경
- Product Result/Evidence Truth 임의 생성
- 광우 Action/Ontology semantics 임의 변경
- LLM이 새로운 사실을 만들어 Domain Truth를 대체하게 하는 구현
- UI 클릭 또는 탭 전환을 LLM 반복 호출 트리거로 사용하는 구현

### 최종 완료 조건

> **다른 세 사람의 Domain 산출물이 실제 공개 URL에서 하나의 Product API / Dashboard / Closed-loop / Executive Brief / LLM Report로 연결되고, CI/E2E로 재현 가능해야 완료다.**

---

# 4. Step별 역할 분배

아래 Step은 “해당 단계의 담당자 한 명”을 의미하지 않는다.

각 Step마다 네 사람이 자기 전문 축에서 해야 할 일을 동시에 수행하고, 다음 단계로 전달할 산출물을 만든다.

---

## Step 1. 공통 계약 기준선 고정

### 목표

Feature / Label / Model Artifact / Product Result / Evidence / Action / Report가 서로 다른 팀원의 구현에서도 같은 의미를 갖도록 계약을 고정한다.

| 사람 | 이 Step의 책임 | 다음 단계로 넘길 것 |
|---|---|---|
| **성민** | Feature/Label/Model Artifact/Prediction Output 계약 작성, training provenance와 model runtime 요구사항 정의 | Feature/Label schema, Model Artifact v1.0 contract |
| **호범** | Backend consumer 관점에서 Artifact 계약 검토, Product Result/Evidence 및 `evidence_payload` contract 확인 | Backend runtime/result/evidence contract |
| **광우** | Event/Decision/Action/Maintenance/Activity에 필요한 ID·상태·관계 정의 | Closed-loop domain contract |
| **우수** | Frontend/Report/Product API consumer 관점 필드 검토, acceptance criteria와 CI gate 정의 | Product/Report input contract, contract test plan |

### 완료 조건

```text
Feature Contract
Label Contract
Model Artifact Contract
Product Result / Evidence Contract
Action Contract
Report Input Contract
```

의 producer와 consumer가 명확하다.

---

## Step 2. Feature / Label Pipeline 구현

### 목표

Canonical source를 재현 가능한 학습 입력과 label로 변환한다.

| 사람 | 이 Step의 책임 | 다음 단계로 넘길 것 |
|---|---|---|
| **성민** | extraction, asset isolation, timestamp canonicalization, feature engineering, prediction horizon label, leakage 방지 구현 | deterministic Feature/Label dataset |
| **호범** | 향후 runtime inference에 동일 feature 의미를 재현할 수 있는지 consumer 관점 검토, evidence source field와 연결 가능성 확인 | runtime/evidence 요구사항 feedback |
| **광우** | feature/source field가 Equipment/Component/Process context와 연결 가능한지 semantic mapping 검토 | ontology field mapping |
| **우수** | Feature/Label 관련 contract test와 CI gate 추가, schema drift가 main에 들어오지 않도록 검증 | CI evidence / failure gate |

### 완료 조건

> 동일 source와 config에서 deterministic Feature/Label이 생성되고, downstream이 필요한 의미 정보가 보존된다.

---

## Step 3. Model Training / Evaluation / Artifact Publish

### 목표

Backend가 독립적으로 소비할 수 있는 immutable Model Artifact를 실제 발행한다.

| 사람 | 이 Step의 책임 | 다음 단계로 넘길 것 |
|---|---|---|
| **성민** | train/evaluate, metrics, 6-file Artifact, `artifact_files[*].sha256`, provenance, atomic publish, retrain/version 정책 구현 | 실제 Model Artifact + metrics |
| **호범** | 샘플 Artifact를 Backend loader 관점에서 사전 검토하고 consumer fixture 준비 | loader acceptance fixture |
| **광우** | model output/failure type/top factor가 RiskEvent/Recommendation으로 연결될 최소 semantic requirement 검토 | ontology consumption mapping |
| **우수** | Artifact publish/schema/round-trip CI 추가, Artifact version/provenance가 제품에서 노출 가능한지 확인 | CI publish gate + report provenance requirement |

### 완료 조건

> 실제 Model Artifact가 생성되고, 다른 프로세스가 Generator Python 구현 없이 읽을 수 있다.

---

## Step 4. Backend Artifact Loader / Runtime Inference

### 목표

학습 산출물을 실제 제품 runtime prediction으로 연결한다.

| 사람 | 이 Step의 책임 | 다음 단계로 넘길 것 |
|---|---|---|
| **성민** | loader에서 발생하는 feature/schema/model version mismatch 분석, runtime feature parity 지원 | producer-side compatibility fix |
| **호범** | Artifact validation/load, history requirement, current observation, inference, status/unavailable 처리 구현 | runtime prediction service |
| **광우** | prediction 결과가 Equipment/RiskEvent identity와 연결되도록 asset/event key 검증 | runtime→ontology identity mapping |
| **우수** | publish→load round-trip CI, 고정 이력에 대한 Generator/Backend Feature golden-vector parity, Backend health/integration smoke, Product API에서 사용할 runtime adapter 요구사항 정리 | integration gate + application adapter plan |

### 완료 조건

> 성민이 발행한 Artifact를 호범 Backend가 독립적으로 읽어 실제 observation에
> inference하고, 동일 고정 이력에서 Generator와 Backend의 Feature 이름·순서·dtype·값이
> 일치한다. Operations active model과 threshold/risk-grade mapping도 명시되어 있다.

---

## Step 5. Product Result Artifact / Evidence Enrichment

### 목표

Raw prediction을 Dashboard/Report/Action이 공통으로 소비할 수 있는 Product Result와 Evidence로 바꾼다.

| 사람 | 이 Step의 책임 | 다음 단계로 넘길 것 |
|---|---|---|
| **성민** | top factor 의미, model metrics, model limitation, input feature provenance 제공 | model-side evidence metadata |
| **호범** | Product Result Artifact, `evidence_payload`, source field/sensor/component hypothesis/evidence_gap/provenance producer 구현 | Product Result / Evidence API |
| **광우** | Evidence를 RiskEvent/Equipment/Component와 projection하고 Action 판단에 필요한 정보 확인 | Event Evidence projection |
| **우수** | Product Result/Evidence를 Product View Model로 변환할 aggregation adapter와 consumer contract test 구현 | Product aggregation input |

### 완료 조건

> API, Closed-loop, Dashboard, Report가 동일 Result/Evidence를 공유할 수 있다.

---

## Step 6. Ontology Closed-loop 구현

### 목표

분석 결과가 실제 Decision / Action / Maintenance state로 되돌아가는 대표 loop를 완성한다.

| 사람 | 이 Step의 책임 | 다음 단계로 넘길 것 |
|---|---|---|
| **성민** | Model/Feature 의미 검토와 `gen_data` 대상 설비 Runtime Overlay Observation 지속 생성/available | model constraints + overlay observation availability |
| **호범** | Action 판단용 Result/Evidence 제공, 정비 후 history readiness 판정·Runtime Prediction 연결 | readiness + evidence + post-maintenance result |
| **광우** | Recommendation → Decision → TOOL_REPLACEMENT → MaintenanceEvent → Ontology state → Integration Outbox 구현 | closed-loop state + maintenance handoff |
| **우수** | Operations용 Product API/UI, Runtime 준비 상태와 상태 전이 acceptance flow 구현 | usable closed-loop product flow |

### 완료 조건

> 하나의 CNC Event가 Evidence 확인부터 Action 완료까지 동작하고, 대상 설비 Runtime
> Overlay batch를 Backend가 `history_requirement`으로 검증해 ready로 판정한 뒤 별도
> Prediction Result를 생성한다.

---

## Step 7. Product API / 4개 화면 통합

### 목표

각 Domain API를 사용자가 이해할 수 있는 하나의 제품 흐름으로 묶는다.

| 사람 | 이 Step의 책임 | 다음 단계로 넘길 것 |
|---|---|---|
| **성민** | UI에 노출되는 model status/factor/metrics가 모델 의미와 일치하는지 검토 | model interpretation feedback |
| **호범** | Frontend가 요구하는 Result/Evidence field와 projection 누락 보완, API consistency 유지 | stable Product Result/Evidence API |
| **광우** | Operations의 Decision/Action/Activity state와 ontology relation을 UI에 제공 | stable closed-loop API/state |
| **우수** | Product aggregation API + Overview/Objects/Operations/Executive Brief navigation과 visualization 구현 | end-user product surface |

### 화면 흐름

```text
Overview
  ↓ equipment_id
Objects
  ↓ result_id / event_id
Operations
  ↓ decision / action / activity
Executive Brief
```

### 완료 조건

> 동일 Equipment/Event/Result가 네 화면에서 같은 상태와 근거로 연결된다.

---

## Step 8. Deterministic Executive Brief / Report Backend

### 목표

LLM 없이도 항상 생성되는 정적 보고서와 Report Context를 먼저 완성한다.

### 진입 조건

Backend producer가 Product Result / Evidence를 실제로 만들고, Closed-loop에서 Decision / Action / Activity를 조회할 수 있어야 한다.

| 사람 | 이 Step의 책임 | 다음 단계로 넘길 것 |
|---|---|---|
| **성민** | report에 노출할 model/dataset/artifact version, metrics, limitation provenance 제공 | model provenance block |
| **호범** | Report가 사용할 Evidence field, evidence_gap, limitation, source reference 규칙 정의 | Report Grounding Contract |
| **광우** | Decision/Action/Maintenance/Activity와 before/after operational context 제공 | operational report context |
| **우수** | Report Context Builder, Static Report Backend/API, deterministic Executive Brief UI 구현 | Structured Executive Brief |

### 정적 보고서 최소 구조

```text
1. 상황 요약
2. 설비 / Event
3. 위험 상태와 확률
4. 주요 Evidence
5. 모델 / 데이터 provenance
6. Recommendation
7. Decision
8. Action / Maintenance
9. 현재 상태
10. Limitations / Evidence Gap
```

### 완료 조건

- LLM 없이 생성 가능
- 같은 입력 → 같은 결과
- Dashboard 숫자와 일치
- 없는 사실을 만들지 않음
- source / evidence trace 가능

---

## Step 9. Evidence-grounded Dynamic Report + Agent Summary Materialization

### 목표

정적 보고서와 Agent Review Packet을 Truth source로 두고, Evidence에 근거한 자연어 Executive
Narrative와 역할별 Agent Review Summary를 저장 가능한 산출물로 생성한다.

### 진입 조건

Step 8의 Structured Executive Brief가 먼저 안정화되어야 한다.

| 사람 | 이 Step의 책임 | 다음 단계로 넘길 것 |
|---|---|---|
| **성민** | 모델 결과/metrics/limitation 문장이 원래 Artifact 의미를 왜곡하지 않는지 검증 | model narrative validation cases |
| **호범** | **Dynamic Report feature owner**: grounding selection, prompt content, output schema, narrative rule, evidence citation, hallucination guard, limitation/fallback rule, 품질 테스트 | Grounding/Prompt/Output/Validation Contract |
| **광우** | Decision/Action/Activity 관련 문장이 실제 workflow state와 일치하는지 검증 | operational narrative validation cases |
| **우수** | LLM provider adapter, runtime invocation, watcher orchestration, summary key/idempotent persistence, structured output parse, timeout/retry, validation pipeline 연결, static fallback, Report/Agent Summary API, Executive Brief/Workflow UI 연결 | deployed materialized LLM summary runtime |

### 역할 경계

```text
호범
= 동적 보고서/Agent Summary의 내용과 Grounding 책임

우수
= 동적 보고서/Agent Summary를 실제 LLM 서비스로 실행하고 저장 산출물로 제품에 연결하는 Runtime 책임
```

### 생성 트리거

```text
Product Result / Evidence Snapshot 변경
→ watcher가 snapshot/source checksum/prompt/schema/model version diff 확인
→ summary_key가 없거나 stale이면 LLM 후보 생성
→ validation 통과 또는 deterministic fallback 확정
→ Agent Review Summary / Dynamic Report Summary 저장
→ UI / Report는 저장본 조회
```

UI 사이드뷰 클릭, 탭 전환, 화면 새로고침은 조회 이벤트이며 LLM 생성 이벤트가 아니다.

### 완료 조건

- 숫자 hallucination 없음
- Evidence에 없는 원인 생성 금지
- Action 상태 왜곡 없음
- 정적 보고서와 의미 불일치 없음
- LLM 실패 시 static fallback
- 생성 결과 source trace 가능
- 같은 snapshot과 prompt/schema/model version에서는 저장된 Summary 재사용
- snapshot diff가 없는데 UI 조작만으로 LLM이 재호출되지 않음

---

## Step 10. End-to-End CI / Acceptance 자동화

### 목표

개별 PR 성공이 아니라 전체 서비스 흐름을 자동으로 보호한다.

| 사람 | 이 Step의 책임 | 다음 단계로 넘길 것 |
|---|---|---|
| **성민** | feature/label/model artifact regression과 대상 설비 Overlay 재현성·다른 설비 무영향 검증 | ML/source quality gate |
| **호범** | runtime/result/evidence, post-maintenance history와 unavailable negative case 유지 | Backend intelligence gate |
| **광우** | Decision/Action/Maintenance state, Integration Outbox와 closed-loop E2E fixture 유지 | closed-loop gate |
| **우수** | 모든 gate를 GitHub Actions와 Playwright/Docker E2E로 묶고 release-blocking acceptance 관리 | integrated CI/release gate |

### 핵심 E2E

```text
Source
→ Feature / Label
→ Model Artifact
→ Runtime Inference
→ Product Result / Evidence
→ Recommendation / Decision / Action
→ Maintenance / Activity / Ontology State
→ 대상 설비 Runtime Overlay / history 준비
→ 새로운 Observation / Prediction Result
→ Executive Brief
→ Dynamic Report
```

### 완료 조건

> main의 핵심 acceptance gate가 green이고 실패 시 어느 역할의 문제인지 식별 가능하다.

---

## Step 11. 공개 배포 / 운영 준비

### 목표

로컬이 아니라 실제 발표 환경에서 동일 파이프라인이 동작하게 한다.

| 사람 | 이 Step의 책임 | 다음 단계로 넘길 것 |
|---|---|---|
| **성민** | 배포 환경에서 사용하는 Model Artifact version 고정, 필요 시 retrain/publish, artifact reproducibility 확인 | release model artifact |
| **호범** | Render Backend에서 Artifact load/inference/evidence/dynamic report grounding smoke, fail-fast 오류 경로 확인 | backend release sign-off |
| **광우** | Neon 등 영속 환경에서 Decision/Action/Activity state와 closed-loop persistence 확인 | operations release sign-off |
| **우수** | Vercel/Render/Neon, LLM secret, proxy/CORS, Product API, E2E, preview/final URL 검증 및 release orchestration | production-like demo environment |

### 배포 기준

```text
Vercel
Frontend
        ↓
Render
FastAPI Backend / Report / LLM Runtime
        ↓
Neon
PostgreSQL

사전 학습 또는 CI
→ 검증된 Model Artifact 영속 발행
→ `MODEL_ARTIFACT_URI`
→ Backend Runtime

Render의 임시 파일시스템은 Model Artifact 정본으로 사용하지 않는다.
```

### 완료 조건

> 발표용 공개 URL에서 로그인부터 Dynamic Executive Brief까지 핵심 흐름이 실제로 동작한다.

---

## Step 12. 최종 시연 / 발표 / 회귀 안정화

### 목표

새 기능을 추가하는 것이 아니라 하나의 스토리로 전체 기술 흐름을 증명한다.

| 사람 | 이 Step의 책임 | 발표에서 설명할 축 |
|---|---|---|
| **성민** | 최종 Artifact 재현과 대상 설비 Runtime Overlay/branch clock 재현성 확인 | Source → Feature/Label → Model Artifact/Overlay |
| **호범** | 정비 전후 Result/Evidence, history와 Dynamic Report grounding consistency 검증 | Artifact → Runtime → Evidence → Grounded Narrative |
| **광우** | 대표 CNC closed-loop 상태, action history와 Maintenance Integration event 안정화 | Evidence → Decision → Action → Maintenance → Feedback |
| **우수** | 전체 demo orchestration, UI/LLM/배포/backup scenario, CI green, 발표용 최종 release | 여러 Domain을 하나의 사용자 Product로 통합 |

### 최종 데모 시나리오

```text
1. Overview에서 CNC 위험 상승 확인
2. Objects에서 probability / sensor / top factor 확인
3. Evidence와 provenance 확인
4. 현장 엔지니어가 Operations에서 Evidence를 확인하고 점검·분석 결과를 기록
5. 생산 운영 의사결정자가 Evidence와 엔지니어 결과를 확인하고 Recommendation 판단
6. 정비 필요 시 WorkOrder 승인
7. 정비 작업자가 TOOL_REPLACEMENT Action을 시작·완료
8. MaintenanceEvent / Activity / Ontology state 갱신 확인
9. 동일 mutation replay의 idempotency 확인
10. 대상 설비만 Runtime Overlay로 분기되고 다른 설비 Replay가 유지되는지 확인
11. 대상 설비 branch clock Fast-forward, 지속 Observation availability와 Backend history
    준비 상태 확인
12. Backend가 ready로 판정한 첫 inference-ready Observation의 새로운 Prediction Result 확인
13. Static Executive Brief 확인
14. Evidence-grounded Dynamic Report 확인
15. 동일 근거가 Dashboard / Decision / Action / Report에 일관되게 사용됨을 설명
```

---

## 선택 확장 — 비용 기반 정비 대안 분석

이 기능은 핵심 Closed-loop와 공개 배포 E2E가 완료된 후 시간이 남는 경우에만 구현한다.
필수 완료 경로와 CI gate에는 포함하지 않는다.

### 목표

고장이력, 수리이력, 설비·부품 가격, 정비 시간과 생산 중단 비용을 이용해 다음 대안을 비교한다.

- 즉시 수리 또는 교체
- 다음 계획 정비 시 수리
- 일정 시간 운전 후 재평가

### 출력

- 선택지별 부품비·수리비
- 예상 정지 시간과 생산 손실
- 총 기대비용
- 현재 입력과 가정에서 비교되는 수리 방법과 시점의 참고 비용
- 실제값·추정값·정책 기본값 구분
- 근거와 제한사항

### 안전 원칙

- 위험도 변화를 필수 출력으로 요구하지 않는다.
- 실제 예방효과나 인과관계를 확정하지 않는다.
- 비용 데이터가 없으면 임의 값을 생성하지 않는다.
- “최적” 또는 자동 추천으로 표현하지 않고 현재 입력과 가정에 따른 참고 결과로 표시한다.
- 비용 option은 Recommendation, 승인, WorkOrder 또는 MaintenanceAction을 생성하지 않는다.

---

# 5. 역할 간 인계 규칙

## 5.1 성민 → 호범

```text
Model Artifact
+ Feature / Label Contract
+ history requirement
+ metrics / provenance
```

호범은 Generator implementation을 직접 import하지 않는다.

---

## 5.2 호범 → 광우

```text
Product Result Artifact
+ Evidence Payload
+ Event Evidence Projection
```

광우는 prediction truth를 다시 계산하지 않는다.

---

## 5.3 광우 → 성민 / 호범 / 우수

```text
Decision
RecommendedAction
MaintenanceAction
MaintenanceEvent
Activity
Ontology State
maintenance.started / maintenance.completed / maintenance.replay_requested
maintenance_event_id + idempotency_key + state_version + state_patch
runtime_overlay.observations.available
overlay_branch_id + Observation range + storage reference
```

성민은 지속 Runtime Overlay Observation 생성/available로, 호범은 history readiness와
정비 후 Result/Evidence로, 우수는 후속 Backend integration에서 확정될 Product read
location과 E2E로 사용한다. 상세 handoff는
[`closed-loop-runtime-overlay-contract.md`](./closed-loop-runtime-overlay-contract.md)를
따른다.

---

## 5.4 호범 → 우수: Dynamic Report 계약

```text
Grounding Fields
Prompt Content Contract
Output Schema
Narrative Validation
Fallback Conditions
Summary Key Inputs
Snapshot Diff Trigger
```

우수는 이 계약을 사용해 실제 LLM provider runtime, watcher 기반 Summary materialization,
Product API를 구현한다. Summary는 UI 이벤트마다 새로 만들지 않고, Product Result/Evidence
snapshot과 prompt/schema/model version이 달라질 때만 새 산출물로 저장한다.

---

## 5.5 우수 → 전체 팀

```text
CI Failure
E2E Failure
Integration Contract Failure
Deployment Failure
```

문제가 발견되면 우수가 모든 코드를 대신 수정하는 것이 아니라, 해당 Domain owner에게 실패 근거를 넘기고 각 owner가 자기 영역을 수정한다.

---

# 6. 공통 작업 원칙

## Rule 1. 역할은 Step이 끝나도 종료되지 않는다

예를 들어 성민이 Model Artifact를 발행한 뒤에도:

```text
Backend mismatch
Report model provenance 문제
Closed-loop model interpretation 문제
Final regression
```

은 계속 성민의 책임 범위다.

같은 원칙을 네 사람 모두에게 적용한다.

---

## Rule 2. 새로운 아키텍처 제안은 E2E 필요성으로 판단한다

> **이 작업을 하지 않으면 최종 E2E 데모가 동작하지 않는가?**

- Yes → 지금 처리
- No → Parking Lot

다음은 기본적으로 Parking Lot 후보로 둔다.

- 범용 Feature Store
- 범용 Schema Registry
- 범용 Workflow Engine
- 범용 Ontology Engine
- 여러 버전 동시 협상 인프라
- 새 microservice 분리
- 범용 Agent Platform

---

## Rule 3. Contract 작성자와 구현자는 다를 수 있다

```text
Producer
Contract 제안
    ↓
Consumer
구현 가능성 검토
    ↓
합의된 Contract
    ↓
각 Domain 구현
```

계약을 작성했다는 이유로 다른 Domain 구현까지 소유하지 않는다.

---

## Rule 4. Domain Truth와 Product Orchestration을 구분한다

```text
성민 = Model Truth
호범 = Prediction / Evidence Truth
광우 = Decision / Action / Operational Truth
우수 = Product / Report / LLM Runtime Orchestration
```

Product layer는 Domain Truth를 새로 만들어내지 않는다.

---

## Rule 5. LLM은 Truth Producer가 아니다

```text
Structured Data / Evidence = Truth
LLM = Expression Layer
Materialized Summary = 검증된 표현 산출물
```

동적 보고서의 Grounding/내용 규칙은 호범이 책임지고, 실제 LLM Runtime/Product 연결은 우수가 책임진다.

LLM 실패 여부와 관계없이 Static Executive Brief는 항상 제공되어야 한다.
Agent Review Summary와 Dynamic Report Summary는 Closed-loop 명령이 아니다. Closed-loop는 Summary
문장이 아니라 Product Result/Evidence snapshot basis와 Recommendation/Action 계약을 기준으로 동작한다.

---

# 7. 최종 프로젝트 완료 정의

프로젝트 완료는 네 사람이 각각 자기 PR을 merge하는 것이 아니다.

다음 흐름이 **공개 배포 환경에서 하나의 사용자 시나리오로 동작하고 각 단계의 owner가 결과를 설명할 수 있어야** 완료다.

```text
Canonical V3.1 Source
        ↓
Feature / Label
        ↓
Model Training / Evaluation
        ↓
Model Artifact
        ↓
Backend Runtime Inference
        ↓
Product Result / Evidence
        ↓
Ontology Recommendation / Decision / Action
        ↓
Maintenance / Activity / State Feedback
        ↓
새로운 Observation / Prediction Result
        ↓
Static Executive Brief
        ↓
Evidence-grounded Dynamic Report
        ↓
Dashboard / Report / API
```

그리고 이 전체 흐름을 CI / E2E / Vercel / Render / Neon 환경에서 재현할 수 있어야 한다.
