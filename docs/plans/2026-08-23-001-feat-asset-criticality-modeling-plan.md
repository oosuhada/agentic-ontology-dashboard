---
title: "Asset Criticality Modeling Implementation Plan"
type: feat
status: draft
date: 2026-08-23
---

# Asset Criticality Modeling Implementation Plan

**Goal:** `AssetDetailViewModel`에서 설비 중요도를 예측 위험도와 분리된 제조 운영 맥락으로 모델링하고, 결측/출처/검토 우선순위 의미를 schema와 composer 테스트로 고정한다.

**Architecture:** 현재 규모에서는 별도 graph DB나 full digital twin을 만들지 않는다. `asset.criticality`를 설비 마스터/프로젝트 운영 맥락에서 온 영향도 필드로 두고, `risk.status_grade`는 모델 위험도, `review_priority`는 risk, criticality, history/context를 조합한 표시/검토 우선순위 파생값으로 분리한다. `review_priority`는 WorkOrder priority, 권한, action state가 아니다. 온톨로지 관계는 문서와 typed reference 수준으로 고정하고, 운영/정비 맥락은 SQL/RDB 기반 source와 `AssetDetailViewModel` composition boundary에서 우선 결합한다. PR #107의 Operations `AssetDetailViewModel` API/E2E 연결을 기준 구현으로 삼되, 운영 read-port/PostgreSQL 연결은 후속으로 둔다. 이번 후속 구현 범위에는 schema/composer/API 호환성뿐 아니라 Objects/Operations/Report의 신규 context/review-priority 소비와 중복 UI 정리까지 포함한다. Microsoft Fabric/Eventhouse/KQL 패턴, TimescaleDB/ClickHouse/DuckDB류 시계열 분석 비교는 후순위 검증 항목으로만 남긴다.

**Tech Stack:** Python 3, pytest, jsonschema, existing `systems/backend/app/operations/asset_detail_view_model.py` composer, existing `systems/backend/app/diagnosis/recommendation_policy.py` policy contract, React/TypeScript Operations frontend, Vitest/Playwright.

---

## Final Narrative Frame

예지보전 리포트에서는 같은 시점의 같은 설비 판단을 설명하는 snapshot 정합성이 중요하다.
이번 모델링 판단의 기준점은 "데이터를 많이 보여주는가"가 아니라 "리포트가 보여주는
risk, criticality, evidence, context가 같은 판단 시점과 같은 source boundary에서 온
것이라고 말할 수 있는가"다.

### Problem Baseline

현재 `AssetDetailViewModel`은 Product Result Artifact, Evidence Payload,
Observation series, runtime prediction history, Activity/Maintenance context source를 한 화면에
병합해야 한다. 이 데이터들은 owner와 freshness가 서로 다르다. 따라서 프론트엔드가 여러
API를 호출해 직접 조립하면 다음 판단이 화면별로 갈라질 수 있다.

- `risk.status_grade`는 모델/근거 기반 고장 위험도다.
- `asset.criticality`는 고장 발생 시 제조 운영 영향도다.
- `data_status.is_data_quality_hold`는 위험도가 아니라 데이터 품질 때문에 판단을 보류한 상태다.
- fixture 기준선 `40e37b1`에서 `features[].current`는 `{ observed_at, value, quality_status }` 현재 관측 객체이고, `features[].history`는 `{ source_ref, points }` 이력 envelope다. `history.points[]`는 current instant보다 이전인 관측치만 포함하며 current와 병합하지 않는다.
- `risk_series`, `features[].history`, `equipment_history`는 단일 Event Evidence만으로 항상 채워지지 않는다.

### Observed Symptoms

PR100 검토에서 드러난 실제 현상은 단순 schema typo가 아니라 projection 책임이 흔들린
증상으로 본다.

- `data_quality_hold`가 risk grade처럼 취급될 수 있었다.
- `is_stale=false`가 authoritative freshness fact 없이 생성될 수 있었다.
- `top_factor.evidence_field_id`가 schema optional string인데 `null`로 방출될 수 있었다.
- `risk_prediction_results`처럼 내부 저장/조회 형태가 public contract naming으로 새어 나왔다.
- `criticality`가 없을 때 default를 만들면 추천 우선순위와 리포트 해석이 사실처럼 보일 수 있다.

### Cause Exploration

아키텍처 리뷰 관점에서 원인을 여러 기준으로 다시 본 결과, 핵심 원인은 ViewModel을 단순 편의
응답 DTO로 본 데 있다. 이 객체는 화면 payload 이전에 projection contract다.

- Data modeling 기준: producer fact, asset context, derived review priority, data quality state가 분리되지 않으면 위험도와 운영 영향도가 섞인다.
- Manufacturing 기준: 중요도는 설비 고장 확률이 아니라 라인 중단, 품질 손실, 안전/환경, 복구 난이도 같은 운영 영향이다.
- Ontology 기준: `Asset`, `Observation`, `ProductResultArtifact`, `EvidencePackage`, `MaintenanceRecord`의 관계는 보존되어야 하며, relation을 잃은 화면 조립값은 provenance가 약하다.
- API contract 기준: consumer가 raw source를 직접 읽거나 fallback을 합성하면 source truth가 화면 레이어로 이동한다.
- Review 기준: PR100 코멘트의 null/freshness/naming 문제는 모두 "없는 사실을 어떻게 표현할지"가 중앙에서 고정되지 않은 데서 반복된다.

### Alternative Exploration

| Alternative | Why considered | Tradeoff | Priority decision |
|---|---|---|---|
| Frontend composes multiple APIs | UI에서 빠르게 조립 가능 | snapshot 정합성, gap, freshness, criticality 해석이 화면별로 분산됨 | Lower |
| Expand generic `/objects`, `/observations`, `/maintenance` APIs first | 재사용 가능한 product API가 됨 | 리포트 전용 판단 시점과 evidence boundary를 보장하기 어려움 | Lower for this implementation scope |
| Extend Event Evidence only | 변경량이 작음 | 시계열, runtime history, maintenance context를 단일 Evidence로 설명할 수 없음 | Lower |
| Build ontology/graph layer first | 장기적으로 관계 질의가 유리함 | 현재 규모 대비 과하고 PR95/100의 즉시 문제를 해결하지 못함 | Defer |
| Add Microsoft Fabric/Eventhouse/KQL-style time-series platform | 예지보전 reference architecture와 시계열 분석 패턴이 명확함 | 현재 stack 밖의 vendor/runtime 의존성이 생기고, 이번 구현 범위의 contract 문제보다 인프라 검증이 커짐 | Defer as future validation |
| Benchmark TimescaleDB/ClickHouse/DuckDB now | 시계열 저장소 선택 근거를 만들 수 있음 | 데이터 생성/적재/쿼리/운영 비교가 별도 프로젝트가 되며 Operations report contract 완성에 직접 필요하지 않음 | Backlog |
| Single `AssetDetailViewModel` API | snapshot, source, gap, quality state를 한 계약에서 통제 가능 | backend adapter 책임 증가 | Preferred |

### Proposed Framing

따라서 제안은 "단일 ViewModel API로 화면을 편하게 만든다"가 아니다. 제안은
"예지보전 리포트의 snapshot 정합성과 evidence boundary를 보장하기 위해 backend-composed
`AssetDetailViewModel` projection을 먼저 고정한다"다.

이 프레이밍에서 `criticality`는 다음처럼 들어간다.

```text
risk = 모델이 판단한 고장 가능성/등급
criticality = 제조 운영에서의 설비 영향도
history/context = 정비 이력, 운영 조건, 반복 이벤트, 기존 작업 상태
review_priority = risk, criticality, history/context를 조합한 review/display 파생값
```

### Product Direction Note

멘토링에서 얻은 제품 방향성 인사이트는, 예지보전 사용자가 궁극적으로 원하는 것이
복잡한 그래프 탐색 화면이나 많은 대시보드가 아니라 "현재 어떤 설비가 위험하고, 왜
위험하며, 지금 무엇을 해야 하는지"를 비서처럼 요약해주는 얕은 앱 레이어일 수 있다는
점이다.

따라서 이번 계획은 UI 기능을 늘리는 방향이 아니라, backend-composed ViewModel이
risk, evidence, operational context, review priority, available actions를 정합성 있게 조립하고, 화면은
이를 검토, 승인, 기록하는 흐름으로 단순화하는 방향을 따른다. 이 인사이트는 표준이나
외부 레퍼런스를 대체하는 근거가 아니라, 표준 기반 evidence/action contract를 사용자가
소화할 수 있는 제품 형태로 바꾸기 위한 디자인 판단의 배경이다.

### Resource-fit Decision

이번 구현 범위의 채택안은 "typed ontology + SQL/RDB 기반 운영 context + backend-composed ViewModel 확장"이다.
이 선택은 새로운 graph DB, KQL platform, time-series warehouse를 도입하지 않고도 현재 repo에 이미 있는
Product Result Artifact, Evidence Payload, Recommendation Policy, Closed-loop 문서/마이그레이션, 그리고
`AssetDetailViewModel` contract test를 재사용할 수 있다.

Design judgment:
- Use now: `AssetDetailViewModel`에 `asset.criticality`, `maintenance_context`/`equipment_history`, `operation_context`, `review_priority`의 의미를 명시하고 unavailable source는 gap/warning으로 표현한다.
- Use now: ontology는 graph database가 아니라 `source_ref`, `evidence_field_id`, `owner_domain`, relation name 같은 typed reference로 보존한다. 이 값들은 각각 원천 데이터 참조, 근거 필드 식별자, 데이터 책임 도메인, 관계 이름을 뜻한다.
- Defer: Microsoft Fabric/Eventhouse/KQL은 vendor-neutral requirement source로만 사용한다. 즉 "최근 30일 반복 이상", "정비 후 위험 재상승", "고부하 구간 warning/critical" 같은 분석 패턴을 도출하되, KQL runtime을 이번 구현 범위의 구현 대상이나 성능 비교군으로 삼지 않는다.
- Backlog: TimescaleDB, ClickHouse, DuckDB/Parquet, PostgreSQL partition 비교는 실제 시계열 병목이나 대규모 분석 요구가 확인된 뒤 별도 performance spike로 수행한다.
- Avoid: RUL, automated criticality scoring, RPN/cost optimization, full AAS/digital twin, OWL/RDF knowledge graph는 현재 데이터와 구현 증거가 부족하므로 이번 계획의 claim에서 제외한다.

Reference grounding:
- MIMOSA OIIE Use Case 7 frames CBM triggering as condition monitoring/control historian measurements flowing into operational risk interpretation and then a maintenance work request. This supports separating `Recommendation`/CBM request candidates from direct maintenance execution. Reference: https://www.mimosa.org/open-industrial-interoperability-ecosystem-oiie/oiie-use-cases/oiie-use-case-7-condition-based-maintenance-triggering/
- Microsoft Fabric predictive-maintenance architecture uses real-time events plus contextualization data such as asset maintenance history and operational parameters, with Eventhouse/KQL for time-series analysis. This supports deriving repeated-event, post-maintenance, and high-load analysis requirements, but it does not require adopting Fabric/Eventhouse in the current repository. Reference: https://learn.microsoft.com/en-us/fabric/real-time-intelligence/architectures/predictive-maintenance
- OPC UA for Asset Administration Shell describes AAS/Submodel-style digital asset representation. This supports keeping Asset-centered typed contexts, but not implementing a full AAS runtime or graph database for this implementation scope. Reference: https://reference.opcfoundation.org/specs/OPC-30270/full
- Current repository Operations and architecture-review contracts already define the official surface as Overview / Objects / Operations / Event Executive Brief, with Product Result Artifact/Evidence provenance, role-specific workflow, and Backend-computed `available_actions`. This supports improving the existing Object/Action workflow instead of replacing it with a generic graph-first surface.

Current implementation state to verify before execution:
- Fixture clean-contract commit `40e37b1` is the prerequisite baseline for this plan. It changes `features[].current` to an observation object and uses `features[].history { source_ref, points }`; fixture adapter and canonical composer share the same pre-current, timezone-aware, duplicate-instant rejection invariants.
- Focused backend contract/composer/Operations verification for that baseline recorded `64 passed`. Frontend typecheck and browser E2E remain unproven because local frontend dependencies were unavailable at the time of verification; this plan must close that evidence gap before claiming end-to-end adoption.
- PR #107 has merged and introduced the Operations `AssetDetailViewModel` API, backend composer, and frontend consumption path. Start implementation from updated `main`, not from the superseded PR #100 direction.
- PR #100 is superseded by the PR #107 `AssetDetailViewModel` direction. Items from PR #100 review must be rechecked against the latest PR #107/main code before remaining work is kept.
- Already-addressed items such as `runtime_prediction_history` naming, nullable `evidence_field_id`, data-quality-hold mapping, and freshness unknown handling should be recorded as prerequisites or verification checks, not blindly reimplemented.

Automation framing:
- The service can automate detection, replay/runtime inference, Evidence generation, report drafting, Recommendation creation, and CBM request candidate creation without an agent workflow.
- Human approval remains required for recommendation disposition, WorkOrder approval, MaintenanceAction execution, and shutdown review.
- Agent workflow is a later coordination layer, not the automation engine. It may summarize review packets, draft checklists, and prepare handoff notes, but it must not own risk grading, review-priority calculation, authorization, or state transitions.
- This separation should simplify UI information architecture: automated outputs belong in inspection/summary surfaces, while human decisions belong in governed action surfaces.

Simulation/replay ownership:
- `simulation_session_id` is owned by the Diagnosis Runtime/replay runtime implemented in the predictive-maintenance runtime path, not by Closed-loop Maintenance.
- Closed-loop Maintenance may preserve `simulation_session_id` as an opaque correlation reference in `MaintenanceAction` and `maintenance-replay-v1` events after organization/project/workspace scope validation.
- Event Evidence Projection should not become the source of replay session state. If Maintenance needs `simulation_session_id` from a diagnosis `event_id`, add a separate Diagnosis Runtime query port such as `resolve_replay_session_for_event(source_event_id)`.
- Use `source_event_id` or `diagnosis_event_id` in the query contract to avoid confusion with closed-loop integration event IDs.

### Action Path

1. PR #107 및 fixture 기준선 `40e37b1`에서 current/history, freshness, nullable field, data-quality hold의 잔존 이슈를 먼저 확인한다.
2. 이미 확정된 `features[].current` observation object와 `features[].history { source_ref, points }` 계약을 채택하고, frontend typecheck/adapter/browser 경로가 이를 그대로 소비하는지 검증한다.
3. `asset.criticality`, `criticality_basis`, `criticality_source`, source/owner/gap 규칙을 schema/docs에 추가한다.
4. composer가 criticality와 context를 보존하되, 결측 시 default를 만들지 않도록 한다.
5. `operation_context`, `maintenance_context`, `review_priority`를 최소 필드로 추가하고, risk 값을 변경하지 않는 파생값임을 테스트한다.
6. frontend Objects/Operations/Report가 신규 context/review-priority를 소비하고, UI-side synthesis와 중복 설명을 제거한다.

### Result, Lesson, Prevention Notes

Draft to resolve:

- Result: 어떤 테스트/문서/코드 수정이 완료됐고 어떤 증거 수준까지 확보했는가?
- Lesson: 이번 건에서 "ViewModel은 DTO가 아니라 projection contract"라는 교훈을 어떻게 표현할 것인가?
- Prevention: 다음 PR에서 같은 실수를 막기 위해 PR checklist, schema assertion, naming rule 중 무엇을 추가할 것인가?
- Prevention candidate: "새 ViewModel 필드는 source, missing behavior, owner_domain, consumer fallback 금지 여부를 문서/테스트에 같이 추가한다."

### Terminology And Public Wording Note

This is a team implementation plan, so PR numbers such as PR95/PR100 may remain
as traceability anchors. Avoid using personal or closed review vocabulary as
architecture evidence.

- Say `아키텍처 리뷰 관점` instead of `ai-dev 관점` in team-facing rationale.
- Say `기존 Object 중심 탐색과 governed Action UI 철학` instead of `Palantir-style` unless explicitly discussing external product inspiration.
- Say `이번 구현 범위` instead of `slice` when describing scope.
- Say `backend-composed` or `백엔드가 조립 책임을 갖는 화면 응답 계약` instead of `backend-owned` when the point is composition responsibility.
- Define implementation identifiers when they appear in rationale:
  - `source_ref` = 원천 데이터 참조
  - `evidence_field_id` = 근거 필드 식별자
  - `owner_domain` = 데이터 책임 도메인
  - `available_actions` = 백엔드가 role, permission, object state, scope, lineage로 계산한 현재 가능한 사용자 액션 목록

---

## Scope

In scope:
- `AssetDetailViewModel` schema에 `asset.criticality` 의미와 출처를 명시한다.
- 중요도 결측을 임의 기본값으로 채우지 않고 `evidence.gaps[]` 또는 `data_status.warnings[]`로 표현한다.
- `risk`, `criticality`, `review_priority`의 의미를 문서에서 분리한다.
- `features[].current` observation object와 `features[].history { source_ref, points }`의 관계, pre-current/timezone/duplicate-instant invariant, baseline 산정 범위를 명시한다.
- 운영/정비 맥락은 현재 source가 제공하는 범위에서 별도 context로 노출하고, 없으면 unavailable/gap으로 표시한다.
- Objects/Operations/Report UI가 신규 context/review-priority를 소비하도록 수정하고, 같은 위험/근거/추천 설명의 중복을 줄인다.
- PR100 코멘트에서 확인된 naming/null/freshness 문제는 최신 PR #107/main 기준 잔존 여부를 재검증한 뒤 필요한 항목만 유지한다.

Out of scope:
- 설비 중요도 자동 산정 모델, RPN, 비용 최적화 모델.
- graph DB, OWL/RDF 전체 온톨로지 구현.
- Microsoft Fabric/Eventhouse/KQL runtime 도입.
- TimescaleDB, ClickHouse, DuckDB/Parquet, PostgreSQL partition 성능 벤치마크.
- RUL/time-to-failure 예측.
- 운영 read-port/PostgreSQL 기반 데이터 연결.
- `event_id` 기준 `simulation_session_id` 역조회 public query 구현.
- LLM enhancement and agent workflow implementation.

---

## Data Modeling Decisions

### D0. `features[].current` and `features[].history` have distinct roles

The fixture clean contract at `40e37b1` is the prerequisite baseline:

```text
features[].current = { observed_at, value, quality_status }
features[].history = { source_ref, points[] }
history.points[] = { observed_at, value, quality_status }
```

Contract invariants:
- `current` is the current observation at the ViewModel snapshot boundary, not a scalar copied into history.
- `history.points[]` contains only observations strictly earlier than the current instant. Compare timezone-aware timestamps as UTC instants.
- Do not merge current into history in the composer, fixture adapter, or frontend adapter. A chart may render current as a separately typed presentation point, but it must not mutate the contract or use collision preference to hide producer inconsistency.
- Reject conflicting observations at the same instant instead of arbitrarily synthesizing or preferring one value.
- Put shared provenance on the `history` envelope through `source_ref`; do not repeat source fields on every point or predeclare speculative backfill/overlay enums.
- Baseline calculation must use its contracted baseline/history input only. Do not silently add current into baseline computation unless a future versioned contract explicitly says so.
- Keep regression coverage for differing current/history timestamps, timezone-equivalent instants, current exclusion, and duplicate-instant conflicts.

### D1. Criticality is asset context, not risk

`criticality`는 고장 가능성이 아니라 고장 발생 시 운영 영향도다.

- Allowed values: `low`, `medium`, `high`
- Source: asset/equipment master, project operational context, or explicit read-port field
- Owner domain: use `equipment` for equipment-master owned values, `project` for project-scoped operational importance, and `unresolved` when ownership is not yet decided
- Missing behavior: do not default to `medium`
- Consumer use: recommendation/review-priority context, not model status replacement

Directional contract:

```text
risk.status_grade = model/evidence-derived failure risk
asset.criticality = business/operations impact if the asset fails
review_priority = display/review ordering derived from risk + criticality
```

### D2. Start with manual/rule-based criticality

Current scale does not justify an automated importance model. Treat criticality as a manually curated or source-projected enum with reason codes.

Minimal fields:

```text
criticality: low | medium | high | null
criticality_basis: string[]
criticality_source: manual_initial_assessment | equipment_master | project_context | unknown
```

`criticality_basis` examples:
- `line_stop_risk`
- `quality_sensitive`
- `safety_or_environment_risk`
- `long_repair_time`
- `spare_part_dependency`

### D3. Ontology stays as typed relationships

Represent the ontology in documentation and stable references first:

```text
Asset HAS_OBSERVATION Observation
Observation INPUT_TO ProductResultArtifact
ProductResultArtifact HAS_EVIDENCE EvidencePackage
ProductResultArtifact HAS_REVIEW_CONTEXT AssetCriticality
EvidencePackage SUPPORTS Recommendation
Recommendation MAY_CREATE Decision
Decision MAY_CREATE FieldTask
FieldTask MAY_PRODUCE MaintenanceRecord
```

No new graph storage is required for this implementation scope.

### D4. Operational context is separate from model risk

Operational and maintenance data can explain why a risky asset should be handled first,
but they must not rewrite the model's failure risk.

Directional contract:

```text
risk.status_grade = model/evidence-derived failure risk
maintenance_context = maintenance-owned event/work summary and open-work context
operation_context = operations-owned load/runtime/production context
asset.criticality = business/operations impact if the asset fails
review_priority = derived review/display ordering from the above contexts
```

Initial context fields should be intentionally small:
- `maintenance_context.last_maintenance_days_ago`
- `maintenance_context.similar_events_30d`
- `maintenance_context.open_work_order_exists`
- `operation_context.load_level`
- `operation_context.runtime_hours_7d`
- `operation_context.production_impact`

Missing operational context must not be converted to `normal`, `low`, `false`, or `0`.
Use `null`, an empty collection, `data_status.warnings[]`, or an `evidence.gaps[]`
entry with the owning domain.

### D5. Time-series platform comparison is a later performance spike

Microsoft Fabric/Eventhouse/KQL is useful as a reference for event/time-series analysis
patterns, not as a required runtime for this branch. The current implementation should
name the query needs without choosing a new platform:

```text
recent repeated warning/critical events by asset
post-maintenance risk re-rise
high-load window risk events
open work-order deduplication context
```

If these queries become slow or product-critical, run a separate spike comparing:
- PostgreSQL baseline or partitioned tables
- TimescaleDB-style PostgreSQL time-series extension
- DuckDB/Parquet or ClickHouse-style analytical path
- Microsoft Fabric/Eventhouse/KQL as external reference only if deployment context requires it

### D6. Implement Object/Action UI cleanup, not generic graph-first UX

The existing UI direction is useful when it behaves like an Object-centered
operations workbench: choose an Asset/Object, inspect evidence and provenance,
follow lineage, and execute only governed actions. It is not useful if the
generic Ontology Workbench becomes the primary predictive-maintenance workflow.

Keep:
- Object/Asset-centered navigation.
- Same `asset_id`, `event_id`, filter, and snapshot continuity across Overview, Objects, Operations, and Report.
- Evidence/provenance visibility.
- Backend-computed `available_actions`; the frontend must not calculate permission/state transitions.
- Separation between producer Recommendation, human Decision, WorkOrder, MaintenanceAction, and Activity lineage.

Break or defer:
- Graph/traversal-first screen as the core PdM decision surface.
- Generic ObjectSet exploration when it hides the evidence/action sequence a user needs.
- UI-side synthesis of `review_priority`, WorkOrder IDs, recommendation states, or missing context defaults.
- Duplicate risk/evidence/recommendation explanations across Objects, Operations, and Report.

Product surface decision:

```text
Objects = canonical Asset inspection surface for risk, evidence, context, review priority, gaps
Operations = governed action surface for Recommendation, available_actions, WorkOrder/CBM request state
Report = grounded narrative surface using the same Artifact/Evidence/action state
Ontology Workbench = auxiliary exploration/debugging surface, not the official PdM decision flow
```

UI implementation boundary:
- Objects should show the asset-level risk/evidence/context/review-priority packet once, with clear gaps.
- Operations should show action state and human decision controls, not duplicate full factor explanations.
- Report should summarize the same ViewModel/action state as narrative and link back to the canonical evidence owner.
- Frontend must not synthesize `criticality`, `review_priority`, WorkOrder IDs, Recommendation state, or role/state permissions.
- Browser/E2E coverage is required for the new context/review-priority rendering path and for absence of duplicate or contradictory recommendation language.

Simplified user flow:

```text
System detected
→ Review evidence
→ Review recommended action candidate
→ Approve, reject, defer, or record field note
```

Screen grouping:
- Automated outputs: risk detection, top factors, Evidence, gaps, report draft, policy recommendation, CBM request candidate.
- Human decisions: recommendation disposition, WorkOrder approval, MaintenanceAction start/complete, shutdown review, field notes.
- Optional agent assistance: role-specific briefing, duplicate WorkOrder summary, checklist draft, handoff summary.

### D7. Replay session correlation stays outside Event Evidence Projection

The maintenance-replay contract requires `simulation_session_id`, but this is
a runtime correlation reference, not a diagnostic evidence fact.

Current repository history shows the responsibilities are split:
- PR #48 defined the Runtime Overlay contract.
- PR #49 added the `maintenance-replay-v1` event schema where
  `simulation_session_id` is required.
- PR #9 introduced the replay session runtime path, later migrated through
  PR #86 and PR #92 into the current Diagnosis Runtime modules.

Design decision:
- Closed-loop Maintenance owns `MaintenanceAction`, `WorkOrder`,
  `MaintenanceEvent`, and `maintenance.*` event publication.
- Diagnosis Runtime owns replay session creation, session lookup, and the
  meaning of `simulation_session_id`.
- Runtime Overlay/gen_data owns overlay branch observation generation.
- Maintenance may store `simulation_session_id` as an opaque correlation
  reference after scope validation, but must not create, parse, or infer it.

Current Operations boundary:
- The caller passes a replay session selector.
- Diagnosis Runtime validates organization/project/workspace scope, session
  state, Dataset binding, and target equipment inclusion through a public query.
- Diagnosis Runtime returns a validated canonical `simulation_session_id` as an
  opaque reference.
- Maintenance stores that reference only; it does not interpret session state,
  Dataset IDs, replay timing, or target eligibility.

Future event-resolution boundary:
- Product Result/Event to Replay Session canonical mapping must exist before an
  event-based resolver can be authoritative.
- Only after that mapping exists should Diagnosis Runtime expose a query like:

```text
resolve_replay_session_for_event(
  organization_id,
  project_id,
  workspace_id,
  source_event_id
) -> simulation_session_id | unavailable
```

The query must use `source_event_id` or `diagnosis_event_id` naming to avoid
confusing it with closed-loop integration event IDs.

---

## Tradeoffs

| Choice | Pros | Cons | Decision |
|---|---|---|---|
| Manual 3-level criticality | Fast, explainable, enough for Operations | Subjective, needs later calibration | Use now |
| Numeric score/RPN | Better ranking math later | Invents precision without data today | Defer |
| Criticality required string | Simple UI and sorting | Forces fake defaults when unknown | Use nullable or gap-aware handling |
| Full ontology/graph DB | Flexible relationship traversal | Too much infra and migration cost | Defer |
| Typed ontology references | Preserves relation/provenance without new infrastructure | Does not support arbitrary graph traversal | Use now |
| KQL/Eventhouse-style platform | Strong reference for streaming/time-series analytics | Adds vendor/runtime scope outside this branch | Reference only |
| Time-series DB benchmark now | Could support future scale decision | Distracts from current report contract and requires synthetic load design | Backlog |
| RUL prediction | Strong predictive-maintenance story | Current data lacks time-to-failure labels and degradation lifecycle evidence | Avoid claim |
| Preserve Object/Action UI philosophy | Matches existing Operations contracts and governed action boundaries | Needs information architecture cleanup to avoid duplicated panels | Use now |
| Generic graph-first UX | Shows relationships visually | Does not directly solve evidence sufficiency, operational context, or action governance | Defer/avoid as core flow |
| Agent workflow as automation engine | Could appear advanced | Blurs source-of-truth, authorization, and state-transition ownership | Avoid |
| Agent workflow as coordination assistant | Improves review packets and handoff quality | Requires stable Evidence/ViewModel/action contracts first | Backlog |
| Event Evidence carries `simulation_session_id` | Convenient for Maintenance lookup | Couples evidence projection to mutable replay/session state | Avoid as default |
| Diagnosis Runtime query resolves replay session by event | Keeps replay state in runtime owner | Requires explicit event-to-session mapping | Use when Maintenance integration needs it |
| Backend-composed review_priority | Consistent report semantics | Backend owns more projection logic | Use for report ViewModel later |
| Frontend-derived review_priority | Quick display change | Duplicates policy and hides missing evidence | Avoid for contract logic |

---

## Tasks

### Task 0: Rebase Point And Residual-Issue Audit

**Files:**
- Inspect: `contracts/schemas/asset-detail-view-model.schema.json`
- Inspect: `systems/backend/app/operations/asset_detail_view_model.py`
- Inspect: `systems/backend/app/operations/service.py`
- Inspect: `systems/frontend/src/features/operations/api/operationsAdapters.ts`
- Inspect: `tests/test_asset_detail_view_model_contract.py`
- Inspect: `tests/test_asset_detail_view_model_composer.py`
- Inspect: `tests/test_operations.py`

- [ ] **Step 1: Start from PR #107 or post-merge main**

Create the implementation branch from updated `main` because PR #107 has merged.
Do not branch from PR #100 or reintroduce PR #100 naming/shape assumptions.

- [ ] **Step 2: Recheck PR #100 review remnants**

Verify whether these are already fixed in the base branch:
- `runtime_prediction_history` naming
- nullable or omitted `evidence_field_id`
- `data_quality_hold` consistency
- freshness unknown as `is_stale: null` plus warning

Keep only unresolved items in the implementation PR.

### Task 1: Adopt And Verify Current/History Fixture Contract

**Files:**
- Modify: `contracts/schemas/asset-detail-view-model.schema.json`
- Modify: `systems/backend/app/operations/asset_detail_view_model.py`
- Modify: `tests/fixtures/asset_detail_view_model/*.json`
- Test: `tests/test_asset_detail_view_model_contract.py`
- Test: `tests/test_asset_detail_view_model_composer.py`

- [x] **Step 1: Establish the fixture clean-contract baseline**

Commit `40e37b1` defines `features[].current` as an observation object and
`features[].history` as a source envelope with historical points. Backend focused
verification recorded `64 passed`.

- [ ] **Step 2: Verify frontend contract and adapter adoption**

Confirm TypeScript contracts and adapters consume `current` and `history` without
reconstructing the removed `series` shape, repeating provenance per point, or
merging current into history. Run typecheck and adapter tests with dependencies installed.

- [ ] **Step 3: Verify chart presentation keeps roles separate**

If a chart renders both history and current, represent current as a separate
presentation role. Do not mutate `history.points`, silently dedupe conflicts, or
prefer current on timestamp collision.

- [ ] **Step 4: Preserve baseline and timestamp invariants**

Keep current out of baseline calculation unless a future versioned contract says
otherwise. Retain regression coverage for pre-current history, timezone-equivalent
instants, differing timestamps, and duplicate-instant conflict rejection.

- [ ] **Step 5: Close browser evidence gap**

Run the Operations browser/E2E path against the clean fixture contract and record the
result. Until frontend typecheck, adapter tests, and browser E2E pass, contract
adoption is only partially verified.

### Task 2: Extend Criticality Contract

**Files:**
- Modify: `contracts/schemas/asset-detail-view-model.schema.json`
- Modify: `contracts/schemas/README.md`
- Modify: `docs/operations/schema-definition.md`
- Modify: `docs/operations/api-specification.md`
- Modify: `docs/closed-loop-product-consumption-contract.md`
- Modify: `tests/fixtures/asset_detail_view_model/*.json`
- Test: `tests/test_asset_detail_view_model_contract.py`

- [ ] **Step 1: Add asset-impact fields**

Extend `asset` with:
- `criticality`: `low | medium | high | null`
- `criticality_basis`: string array
- `criticality_source`: `manual_initial_assessment | equipment_master | project_context | unknown`

- [ ] **Step 2: Add owner/gap rule**

Missing criticality must not default to `medium`.
Use:

```text
criticality = null
criticality_basis = []
criticality_source = unknown
field = asset.criticality
reason = criticality_missing_or_unresolved
owner_domain = diagnosis | dataset | equipment | project | operations | maintenance | report | frontend | unresolved
```

Do not default this gap to `maintenance` unless the missing source is actually
maintenance-owned.

`owner_domain` classifies which source/owner must resolve the missing field,
not where the gap is displayed. Use `equipment` for equipment-master values,
`project` for project-scoped operational importance, `operations` for runtime
operating context, `maintenance` for maintenance-owned facts, `dataset` for
missing observation/history data, `diagnosis` for model/evidence producer gaps,
`report` for projection/report composition gaps, `frontend` for rendering or
adapter defects, and `unresolved` only when ownership is deliberately undecided.

- [ ] **Step 3: Add contract assertions**

Test scenarios:
- schema accepts `high`, `medium`, `low`
- schema accepts `criticality: null`
- schema rejects unknown criticality values such as `standard`
- missing criticality fixture validates only when the gap/warning is explicit
- `risk.status_grade` still does not include `data_quality_hold`

### Task 3: Add Context And Review Priority Composition

**Files:**
- Modify: `systems/backend/app/operations/asset_detail_view_model.py`
- Modify: `systems/backend/app/operations/service.py`
- Modify: `contracts/schemas/asset-detail-view-model.schema.json`
- Modify: `tests/fixtures/asset_detail_view_model/*.json`
- Test: `tests/test_asset_detail_view_model_composer.py`
- Test: `tests/test_operations.py`

- [ ] **Step 1: Preserve criticality from contracted inputs**

Composer should copy explicit `criticality`, `criticality_basis`, and
`criticality_source` from asset/equipment/read-port data when available.

- [ ] **Step 2: Add intentionally small context fields**

Start with minimal operational context:
- `maintenance_context.last_maintenance_days_ago`
- `maintenance_context.similar_events_30d`
- `maintenance_context.open_work_order_exists`
- `operation_context.load_level`
- `operation_context.runtime_hours_7d`
- `operation_context.production_impact`

Missing values stay `null`, empty, warning, or gap. Do not convert missing
context to `normal`, `low`, `false`, or `0`.

- [ ] **Step 3: Add review_priority as a derived review/display value**

Add a bounded `review_priority` block that explains why the asset should be reviewed
first. It may use risk, criticality, context, and existing action state, but it
must not rewrite `risk.status_grade` or create authorization/action state.

Fail-closed rule:
- `review_priority` may be `null`.
- Do not create a default review-priority level when required risk,
  criticality, or context inputs are unavailable.
- Frontend adapters must not calculate fallback review priority.
- Detailed rule/version calculation may be separated into a later policy PR.

- [ ] **Step 4: Keep policy ownership intact**

Composer must not reimplement `status x criticality` recommendation policy.
It exposes context and review-priority explanation for downstream report/UI consumers.

### Task 4: Update Frontend UI Consumption And Remove Duplication

**Files:**
- Modify: `systems/frontend/src/features/operations/api/operationsContracts.ts`
- Modify: `systems/frontend/src/features/operations/api/operationsAdapters.ts`
- Modify: `systems/frontend/src/features/operations/objects/OperationsObjectsPage.tsx`
- Modify: `systems/frontend/src/features/operations/operations/OperationsOperationsPage.tsx`
- Modify: `systems/frontend/src/features/operations/report/OperationsReportsPage.tsx`
- Modify: `systems/frontend/src/features/operations/report/OperationsExecutiveReportPage.tsx`
- Modify as needed: `systems/frontend/src/features/operations/report/OperationsMapReportAssetDetailView.tsx`
- Test: `systems/frontend/src/features/operations/api/operationsAdapters.test.ts`
- Test: `systems/frontend/e2e/operations-frontend-convergence.spec.ts`

- [ ] **Step 1: Update frontend contracts/adapters**

Type the new criticality/context/review-priority fields and preserve nulls.
Frontend adapters must not synthesize `criticality`, `review_priority`, WorkOrder IDs,
Recommendation state, or role/state permissions.

- [ ] **Step 2: Assign screen ownership**

Implement the screen split:
- Objects: asset risk, evidence, context, review priority, and gaps
- Operations: Recommendation, `available_actions`, approval/defer/reject/note state
- Report: grounded summary from the same ViewModel/action state

- [ ] **Step 3: Remove duplicated explanations**

Move repeated risk/evidence/recommendation explanations into one canonical
owner per detail level. Other screens may show compact summaries and cross-links.

- [ ] **Step 4: Add UI verification**

Add or update frontend unit/E2E coverage for:
- missing criticality displays as unavailable/확인 필요
- review_priority reasons render from backend/ViewModel data
- Objects and Operations do not show contradictory recommendation language
- action controls still depend on backend-provided action state

### Task 5: Validation And Boundary Report

**Files:**
- Modify: `tests/test_report_domain_migration.py`
- Modify: `docs/operations/functional-specification.md`
- Modify: `docs/operations/operations-design-specification.md`
- Modify: `docs/operations/report-specification.md`

- [ ] **Step 1: Keep canonical module guard current**

Ensure the ViewModel composer remains in `systems/backend/app/operations/asset_detail_view_model.py`
and does not import generator/prototype/infra modules directly. Report may
consume the ViewModel/result state but does not own a duplicate composer.

- [ ] **Step 2: Document UI responsibility**

Document that Overview, Objects, Operations, and Event Executive Brief remain
the official PdM surfaces, with Ontology Workbench as auxiliary exploration or
debugging.

- [ ] **Step 3: Run focused verification**

Expected verification:
- contract fixture tests pass
- composer tests pass
- Operations API compatibility tests pass
- frontend adapter tests pass
- Operations E2E for context/review-priority path passes
- whitespace check passes

- [ ] **Step 4: Report evidence boundary**

Final report must state:
- implemented: current/history fixture contract, criticality, context, review priority, UI consumption, docs/tests
- not implemented: operating read-port/PostgreSQL source wiring, TSDB/KQL platform, RUL, LLM/agent implementation
- criticality is operational context, not failure probability or model risk

### Backlog: LLM, Agent Workflow, And Platform Spikes

These are explicitly not part of the criticality/context/review-priority UI implementation PR.

- LLM may later produce role-specific summaries, evidence-linked report language,
  limitation wording, and deterministic fallback improvements.
- LLM must not create risk grades, review_priority, recommendations, authorization, or
  WorkOrder state.
- Agent workflow may later prepare review packets, duplicate WorkOrder summaries,
  checklist drafts, handoff notes, and approval-request drafts.
- Agent workflow must not execute mutations without user approval or own domain
  state transitions.
- Microsoft Fabric/Eventhouse/KQL, TimescaleDB, ClickHouse, DuckDB/Parquet, and
  PostgreSQL partition comparisons remain later performance/platform spikes.

---

## Suggested Delivery Order

1. Start from the latest main containing merged PR #107 and its current `AssetDetailViewModel` API/composer/frontend path.
2. Recheck PR #100 review remnants and keep only unresolved items.
3. Adopt fixture baseline `40e37b1`, verify `features[].current`/`features[].history` frontend consumption, and close the typecheck/adapter/E2E evidence gap.
4. Add criticality source/owner/gap contract.
5. Add context and review-priority composition.
6. Update frontend contracts and UI consumption, removing duplicated explanations.
7. Run backend contract/composer/API tests, frontend adapter/type/E2E checks, and produce a boundary report.

This keeps one larger implementation PR focused on the ViewModel-to-UI decision flow while avoiding a premature ontology platform, time-series warehouse, or LLM/agent ownership change.
