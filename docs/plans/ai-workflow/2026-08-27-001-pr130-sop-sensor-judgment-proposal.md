# PR #130 기반 Agent Review Packet / SOP 판단 계획

## 문서 목적

이 문서는 PR #130 이후 AI workflow를 실제 기능으로 연결하기 위한 실행 계획이다. 기존 SOP 센서 판단 제안은 유지하되, 현재 브랜치의 구현 상태를 기준으로 Agent Review Packet, 현장 위치 reference, UI 요약, LLM 연동, 최소 eval 운영 기준까지 한 흐름으로 정리한다.

## 현재 확정된 경계

Agent는 현장 담당자의 검토를 돕는 read-only 소비자다. Product Result/Evidence를 재계산하지 않고, Closed-loop의 WorkOrder, MaintenanceAction, MaintenanceEvent, Replay, 자동 승인 상태를 생성하거나 변경하지 않는다.

```text
Product Result / Evidence
-> AssetDetailViewModel
-> Agent Review Packet
-> AI 검토 요약
-> 담당자 검토
-> Operations manual Recommendation
-> Manager Decision
-> Maintenance WorkOrder / Action
-> MaintenanceEvent
-> Runtime Overlay 재관측
```

역할 분리는 다음과 같이 둔다.

- Product Result/Evidence: 위험 후보와 근거를 제공한다.
- `field_inspection_reference`: 의심 component를 현장에서 어디서 어떻게 확인할지 제공한다.
- SOP grounding: 점검·교체 시기 검토 기준과 센서 판단 기준을 제공한다.
- Agent Review Packet: 위 근거를 읽기 전용으로 묶어 AI 요약 입력을 만든다.
- Closed-loop: 승인, 작업요청, 정비 실행, 완료, replay 등 상태 변경을 소유한다.

## 현재 구현 상태

현재 브랜치 기준으로 다음은 이미 구현되어 있다.

- `contracts/schemas/agent-review-packet.schema.json`: read-only Agent Review Packet 계약
- `systems/backend/app/operations/agent_review_packet.py`: ViewModel과 SOP retrieval 결과를 Agent Packet으로 합성
- `systems/backend/app/operations/router.py`: `GET /api/objects/{asset_id}/agent-review-packet`
- `systems/backend/app/operations/sop_retrieval.py`: 로컬 SOP metadata 기반 deterministic retrieval
- `contracts/schemas/inspection-location-reference.schema.json`: component-to-field-location reference 계약
- `data/fixtures/inspection_location/demo-cnc-inspection-location-reference-v1.json`: demo CNC 위치 reference fixture
- `systems/frontend/src/features/operations/overview/OperationsWorkflowOverviewPage.tsx`: 현장 담당자 화면의 inline `AI 검토 요약`

현재 기능의 성격은 LLM이 아니라 deterministic review draft다. SOP PDF ingestion, vector RAG, LlamaIndex orchestration, live provider 호출은 아직 구현 범위가 아니다.

## 문제 정의

현재 예지보전 데이터는 위험 신호와 Product Result/Evidence를 제공하지만, 위험 신호가 실제 고장으로 이어졌는지까지 증명하지 않는다. 따라서 AI나 Closed-loop가 다음을 말하면 증거 범위를 넘는다.

- 실제 고장을 예방했다.
- 정비 효과가 입증됐다.
- downtime이 절감됐다.
- SOP가 자동 정비 승인 근거다.

제품에서 필요한 기능은 위험 후보를 안전하게 설명하고, 현장 담당자가 확인할 위치·이력·SOP 기준을 빠르게 읽을 수 있게 만드는 것이다.

## Agent 도입 근거

Agent 도입 근거는 자동 승인이나 자동 정비가 아니다. 이 단계의 agent는 Evidence, SOP, 위치 reference, 이력, Closed-loop 경계를 한 번에 읽어 담당자가 바로 검토할 수 있는 요약으로 바꾸는 read-only reviewer다.

Rule로 충분한 일과 agent가 필요한 일을 분리한다.

- Rule이 할 일: risk grade, top factor, inspection target, SOP match, 위치 reference, evidence gap을 계약대로 계산하고 누락 상태를 fail closed로 표시한다.
- Agent가 할 일: 여러 근거 조각의 관계를 현장 언어로 설명하고, 질문 대신 조회된 이력 요약을 만들며, Closed-loop 권한을 넘는 문구를 제거한다.
- Agent가 하지 않을 일: 위험도 재계산, WorkOrder 승인, MaintenanceAction 실행, MaintenanceEvent 생성, Replay 요청, 낮은 중요도 알림 자동 해소.

따라서 이번 PR의 agent 가치는 “판단 자동화”가 아니라 “검토 부담 감소와 경계 보호”다.

## 대표 시나리오

### 시나리오 A. 공구/마모 계통 warning

`EVT-GS-002`는 공구 사용 시간과 마모 관련 지표가 warning 위험에 기여하는 사례다. SOP에는 교체 시기 검토 기준이 있고, 위치 reference는 공구/마모 계통의 현장 확인 위치를 제공한다.

기대되는 AI 요약은 다음 관계를 설명해야 한다.

- 이 이벤트는 공구/마모 계통 중심의 점검 후보다.
- SOP상 교체 시기 검토 기준과 연결되지만, 정비 승인 근거는 아니다.
- 최근 정비 이력과 열린 작업요청을 먼저 대조해야 한다.
- 자동 승인이나 예방 성공 주장은 금지된다.

이 시나리오는 agent가 흩어진 Evidence, SOP, 위치, 이력 근거를 하나의 검토 초안으로 합성하는지 확인한다.

### 시나리오 B. 여러 factor가 하나의 점검 target으로 묶임

`EVT-GS-004`는 top factor가 여러 개지만 inspection target은 동력 전달 계통 하나로 묶이는 사례다. 사용자는 “왜 지표는 3개인데 점검 대상은 1개인가?”를 자연스럽게 묻게 된다.

기대되는 AI 요약은 다음 관계를 설명해야 한다.

- 모터 출력, 과부하 누적, 구동 토크가 같은 동력 전달 계통 가설로 묶였다.
- inspection target 수는 점검할 component 가설 수이고, top factor 수는 위험 판단에 반영된 지표 수다.
- 현장 확인 위치와 확인 이유를 분리해 보여준다.
- factor 수를 근거로 WorkOrder나 정비 승인을 자동 생성하지 않는다.

이 시나리오는 agent가 데이터 구조를 현장 담당자가 이해할 수 있는 말로 번역하는지 확인한다.

### 시나리오 C. Data quality hold

`EVT-GS-007`은 센서 품질 문제로 위험 판단을 확정할 수 없는 사례다. 이때 agent의 역할은 무엇을 해야 하는지보다 무엇을 하면 안 되는지를 분명히 하는 것이다.

기대되는 AI 요약은 다음 관계를 설명해야 한다.

- 현재는 센서 품질 문제로 위험 판단을 확정할 수 없다.
- top factor와 SOP 판단을 확정값처럼 말하지 않는다.
- 정비 추천, 자동 승인, 예방 성공 표현을 하지 않는다.
- 먼저 센서 수집 상태와 evidence gap을 확인하도록 안내한다.

이 시나리오는 agent가 불확실한 상태에서 안전하게 보류 판단을 설명하는지 확인한다.

## Auto-triage와의 관계

낮은 중요도 알림 자동 분류나 자동 해소는 이번 agent 도입 근거로 사용하지 않는다. 그것은 별도 `low-risk notification auto-triage` 계획에서 eligibility gate, audit log, override 정책을 먼저 정의해야 한다.

이번 계획에서 허용되는 것은 검토 요약과 초안 생성뿐이다. 알림 상태를 자동으로 닫거나 숨기는 기능도 현재 범위 밖으로 둔다.

## 핵심 결정

1. Agent Review Packet을 LLM 입력의 source of truth로 둔다.

LLM은 raw fixture, hidden truth, evaluation truth, 임의 SOP 원문을 직접 읽지 않는다. API가 만든 packet 안의 `risk_summary`, `sop_retrieval`, `sop_guidance`, `history_review_items`, `evidence_gaps`, `source_refs`, `closed_loop_boundary`만 사용한다.

2. 질문 생성이 아니라 이력 조회 요약으로 표현한다.

사용자에게 “확인됐습니까?” 같은 질문을 던지지 않는다. 시스템이 가진 이력 조회 결과를 요약하고, 연결되지 않은 이력은 “전용 이력 계약 미연결” 또는 evidence gap으로 표시한다.

3. 교체 시기 기준은 판단 초안이지 정비 명령이 아니다.

`replacement_review_guidance`와 `sensor_judgment`는 Inspection Result 판단 기준을 제공한다. 이 기준만으로 MaintenanceEvent를 만들거나 WorkOrder를 승인하지 않는다.

4. 위치 계약은 Closed-loop가 아니라 field inspection reference가 소유한다.

위치 reference는 “어디를 볼지”의 읽기 전용 계약이다. Closed-loop가 소유하는 것은 승인·상태 변경·정비 실행 흐름이다.

5. Top factor 수와 inspection target 수는 다를 수 있다.

여러 위험 지표가 하나의 component 가설로 묶이면, top factor는 3개여도 inspection target은 1개일 수 있다. UI는 이를 `위험 판단에 반영된 지표`와 `확인 이유`로 분리해 보여준다.

## 통합된 이전 계획 결정

이 문서는 이전 AI workflow 초안의 중복 결정을 흡수한 정본이다.

### UI / Agent 단계 경계

이전 Asset Detail UI/UX agent flow 계획의 핵심 결정은 다음처럼 유지한다.

- Objects는 canonical inspection surface다.
- Operations는 governed human decision surface다.
- Report는 grounded narrative surface다.
- Agent는 coordination draft layer이며, risk, criticality, `review_priority`, authorization, WorkOrder/MaintenanceAction state, replay session 의미를 소유하지 않는다.
- Approval-request draft는 만들 수 있지만 pending approval 상태에서 멈춘다.
- 사용자가 승인해도 backend command endpoint가 authorization, state, scope, lineage, idempotency를 다시 검증한다.

### SOP Grounding 소비 gate

이전 SOP Grounding 소비 계약 제안의 핵심 결정은 다음처럼 유지한다.

```text
procedure-grounding schema validation
-> source_kind + maturity gate
-> applicability matching
-> inspection_guidance projection
```

사용자-facing guidance 허용 조건:

| `source_kind` | `maturity` | 소비 정책 |
|---|---|---|
| `demo_sop_fixture` | `fixture` | Operations demo guidance 허용 |
| `site_sop` | `approved` | 현장 SOP guidance 허용 |
| `site_sop` | `draft` | 검색 후보로만 보존, UI guidance 금지 |
| `site_sop` | `retired` | 이력/감사 조회 외 신규 guidance 금지 |
| `industry_standard_reference` | any | 별도 정책 전까지 직접 작업 안내 금지 |

SOP Grounding은 Product Evidence가 아니라 점검 참고 절차다. WorkOrder와 MaintenanceAction은 SOP 노출만으로 생성되지 않는다.

## 구현 계획

### U1. Packet Golden Set 추가

**Goal:** Agent Review Packet이 실제 LLM 입력으로 안전한지 회귀 검증할 최소 gold set을 만든다.

**Files:**

- `tests/fixtures/agent_review_packets/GS-002.json`
- `tests/fixtures/agent_review_packets/GS-004.json`
- `tests/fixtures/agent_review_packets/GS-007.json`
- `tests/test_agent_review_packet_golden.py`

**Approach:** 현재 deterministic composer 출력에서 대표 3개를 고정한다. 정확한 문장 전체를 과하게 고정하기보다, 계약과 경계 조건을 assert한다.

**Test scenarios:**

- GS-002: 시나리오 A처럼 tooling 위치 reference와 SOP guidance가 포함된다.
- GS-004: 시나리오 B처럼 inspection target은 1개지만 factor refs는 3개로 묶인 상태가 유지된다.
- GS-007: 시나리오 C처럼 data quality hold에서 정비 추천이나 예방 성공 표현이 나오지 않는다.
- 공통: `mutation_allowed=false`, forbidden actions 포함, `source_refs` 존재, public `human_questions` 미노출.

**Verification:** packet fixtures가 schema를 통과하고, 세 대표 케이스의 도메인 경계 assert가 통과한다.

### U2. LLM Summary Output 계약 추가

**Goal:** LLM이 생성할 결과를 packet과 분리된 출력 계약으로 제한한다.

**Files:**

- `contracts/schemas/agent-review-summary.schema.json`
- `contracts/schemas/README.md`
- `tests/test_agent_review_summary_contract.py`

**Approach:** LLM 출력은 요약 문서만 담는다. 권장 구조는 `title`, `summary`, `history_summary`, `inspection_focus`, `evidence_gaps`, `source_refs`, `boundary_note`, `confidence_label` 정도로 제한한다. WorkOrder/action/replay 생성 필드는 스키마에 넣지 않는다.

**Test scenarios:**

- 유효한 summary payload는 schema를 통과한다.
- action 생성, approval, maintenance event, replay 지시 필드가 있으면 실패한다.
- `source_refs`가 비어 있거나 packet에 없는 source를 참조하면 실패한다.

**Verification:** summary schema가 packet schema와 별도로 검증되고, mutation 성격 필드는 허용되지 않는다.

### U3. Provider Adapter와 Deterministic Fallback

**Goal:** 실제 LLM provider를 붙이되 provider 장애나 잘못된 응답에서 기존 deterministic draft로 fail closed한다.

**Files:**

- `systems/backend/app/operations/agent_review_summary.py`
- `systems/backend/app/infra/llm.py`
- `systems/backend/app/operations/router.py`
- `tests/test_agent_review_summary.py`

**Approach:** API는 packet endpoint를 오염시키지 않고 별도 summary endpoint로 둔다. 우선 후보는 `POST /api/objects/{asset_id}/agent-review-summary`다. provider unavailable, timeout, invalid JSON, schema violation, forbidden action 표현이 있으면 deterministic fallback을 반환한다.

**Test scenarios:**

- provider off: deterministic fallback 반환
- provider success: schema-valid summary 반환
- invalid JSON: fallback 반환
- forbidden action 또는 자동 승인 표현: reject 후 fallback 반환
- missing citation/source refs: reject 후 fallback 반환

**Verification:** provider 상태와 무관하게 UI가 항상 안전한 요약을 받을 수 있다.

### U4. Prompt / Validator Guardrail

**Goal:** LLM이 packet 밖의 사실을 만들거나 Closed-loop 권한을 넘지 않도록 입력·출력 양쪽을 검증한다.

**Files:**

- `systems/backend/app/operations/agent_review_summary.py`
- `tests/test_agent_review_summary.py`

**Approach:** prompt는 “packet only”를 명시하고, output validator가 금지 표현과 source citation을 검사한다. validator는 정교한 자연어 심판보다 먼저 deterministic rule로 시작한다.

**Test scenarios:**

- packet에 없는 downtime, 예방 성공, 수리 완료 주장을 포함하면 실패한다.
- data quality hold에서 정비 실행 또는 자동 승인 문구가 나오면 실패한다.
- `closed_loop_boundary.mutation_allowed=false`인데 action 실행을 제안하면 실패한다.

**Verification:** 최소 경계 위반은 LLM 품질과 무관하게 차단된다.

### U5. Frontend Summary 전환

**Goal:** 현장 담당자 화면의 `AI 검토 요약`을 LLM summary API 결과로 교체하되 fallback 상태를 표시한다.

**Files:**

- `systems/frontend/src/api.ts`
- `systems/frontend/src/features/operations/api/operationsContracts.ts`
- `systems/frontend/src/features/operations/api/operationsAdapters.ts`
- `systems/frontend/src/features/operations/overview/OperationsWorkflowOverviewPage.tsx`
- `systems/frontend/src/features/operations/api/operationsAdapters.test.ts`

**Approach:** 드롭다운이나 별도 실행 버튼 대신 현재처럼 inline 표시를 유지한다. summary API가 fallback이면 “검토 전용 / fallback” 성격만 작게 표시하고, 사용자가 action 가능 상태로 오해할 버튼은 만들지 않는다.

**Test scenarios:**

- LLM summary success 표시
- deterministic fallback 표시
- evidence gap이 있는 경우 gap 문구 표시
- 질문형 문구 미노출
- Closed-loop 상태 변경 버튼과 혼동되는 command UI 미노출

**Verification:** 현장 담당자 workflow 화면에서 요약이 바로 보이고, 버튼 없이 읽기 전용임이 유지된다.

### U6. 운영 최소 Eval

**Goal:** 배포 전후에 과하지 않게 볼 최소 평가축을 만든다.

**Files:**

- `tests/eval/agent_review_summary_cases.jsonl`
- `tests/eval/test_agent_review_summary_eval.py`
- `docs/plans/ai-workflow/2026-08-27-001-pr130-sop-sensor-judgment-proposal.md`

**Approach:** 지금 단계에서는 평가 플랫폼을 만들지 않는다. Golden set과 deterministic validator로 release gate를 만들고, 운영 중에는 fallback rate와 human review outcome만 관찰한다.

**Release gate:**

- Groundedness: packet/source에 없는 사실을 만들지 않는다.
- Boundary Compliance: WorkOrder, MaintenanceAction, MaintenanceEvent, Replay, auto approval을 생성·승인하지 않는다.
- Packet Completeness: SOP, 위치, 이력, evidence gap이 계약대로 들어온다.

**Operational monitoring:**

- Fallback Rate: provider 실패, invalid output, citation 누락, forbidden action 차단 비율
- Human Review Outcome: 담당자 override, ignore, accepted-with-edit 비율

**Test scenarios:**

- GS-002/GS-004/GS-007 최소 3개 gold case가 release gate를 통과한다.
- forbidden action은 0건이어야 한다.
- groundedness fail은 0건이어야 한다.
- packet completeness fail은 0건이어야 한다.
- fallback rate는 초기에는 관찰 지표로만 두고 차단 기준으로 쓰지 않는다.

**Verification:** LLM provider를 붙이기 전에도 summary 품질과 권한 경계가 회귀 테스트로 확인된다.

## SOP / 위치 / 이력 데이터 방침

SOP PDF 원문을 바로 LLM에 넘기지 않는다. PDF ingestion이나 LlamaIndex가 필요하다면 그것은 후속 적재 파이프라인의 구현 도구일 뿐, 현재 runtime 판단의 source of truth가 아니다.

현재 우선순위는 다음 순서다.

1. Packet 계약과 deterministic summary를 안정화한다.
2. 작은 gold set으로 packet과 summary output을 검증한다.
3. LLM provider를 packet-only summary 생성기로 붙인다.
4. SOP PDF/RAG ingestion은 실제 승인 SOP corpus와 운영 필요가 생긴 뒤 추가한다.

## 허용 문구 / 금지 문구

허용:

- "AI가 근거 패킷을 요약한 검토 초안"
- "SOP 기준상 점검·교체 시기 검토 필요"
- "센서 기준이 현장 확인 필요성을 지지"
- "조회된 이력과 SOP 근거를 대조"
- "정비 전 위험 판단과 정비 후 재관측을 연결할 수 있음"

금지:

- "실제 고장 예방 입증"
- "정비로 downtime 절감"
- "정비 완료 후 정상화"
- "SOP가 자동 정비 승인"
- "AI가 작업요청을 생성/승인"

## 외부 기준 반영

현재 계획은 다음 업계 기준을 최소 범위로 차용한다.

- OpenAI Evals: 작은 golden set으로 시작하고, 실패 사례를 기준으로 반복 개선한다. [OpenAI Evals](https://platform.openai.com/docs/guides/evals)
- LangSmith agent evaluation: 최종 응답뿐 아니라 tool/step/trajectory 단위 평가를 분리한다. 지금은 full trajectory 대신 output contract와 forbidden action만 둔다. [LangSmith Evaluation](https://docs.smith.langchain.com/evaluation)
- Azure AI Foundry evaluation: groundedness, relevance, completeness, tool call accuracy, protected material 같은 평가축 중 groundedness와 tool/action boundary만 우선 적용한다. [Azure AI Foundry Evaluation](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/evaluation-metrics-built-in)
- RAGAS: retrieval 품질은 faithfulness, answer relevance, context precision/recall로 확장 가능하지만, 현재는 SOP metadata retrieval이므로 full RAGAS는 보류한다. [RAGAS Metrics](https://docs.ragas.io/en/stable/concepts/metrics/)
- NIST AI RMF: 운영 AI는 govern, map, measure, manage를 반복해야 한다. 지금은 measure/manage의 최소 release gate와 fallback 관찰로 제한한다. [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework)
- OWASP LLM Top 10: prompt injection, sensitive information disclosure, excessive agency, improper output handling을 후속 운영 위험으로 본다. [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)

## 범위 밖

이번 계획에서 바로 하지 않는다.

- SOP PDF 대량 ingestion
- vector DB 또는 LlamaIndex 도입
- LLM-as-judge 채점 시스템
- LangSmith/Azure Foundry 운영 연동
- token/cost dashboard
- Closed-loop mutation API 구현
- 낮은 중요도 알림 자동 분류/자동 해소
- 자동 승인 또는 자동 정비 실행
- 실제 고장 예방, downtime 절감, SLA 효과 주장

## 다음 작업 순서

1. U1 Packet Golden Set
2. U2 Summary Output 계약
3. U3 Provider Adapter와 fallback
4. U4 Prompt / Validator Guardrail
5. U5 Frontend Summary 전환
6. U6 운영 최소 Eval

가장 먼저 할 작업은 U1과 U2다. 이 둘이 있어야 실제 LLM을 붙였을 때 “그럴듯한 문장”이 아니라 계약을 지키는 요약인지 판단할 수 있다.
