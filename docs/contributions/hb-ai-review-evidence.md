# AI Review / Evidence Boundary Contribution

상태: 기여 근거 문서
최종 갱신: 2026-09-01
범위: MVP 워크플로우에서 hb가 담당한 AI 검토, 근거 검증, 권한 경계 정리

이 문서는 `ontology-dashboard` MVP 워크플로우에서 AI 검토와 Evidence 소비 경계를 정리한 기여
범위를 기록한다. 설명은 실제 PR, 계약 문서, Schema, 테스트 근거에 연결된 항목으로 제한한다.

## 1. 적용한 책임 경계

### 업무 착수 전 역할과 권한 경계를 먼저 확인한다

워크플로우, 요약, 리포트, 조치 흐름을 다룰 때 다음 책임 경계를 먼저 확인했다.

- Backend Diagnosis는 raw prediction output을 검증하고 Product Result / Evidence로 승격한다.
- UI와 Report는 typed read model을 소비하며 raw evidence를 다시 계산하지 않는다.
- Agent Review는 준비된 evidence packet을 읽고 사람의 검토를 돕는 설명을 생성한다.
- Closed-loop는 추천, 승인, 상태 전이, command-side mutation 경로를 소유한다.

이 경계는 AI가 생성한 설명이 암묵적인 승인이나 상태 변경 명령으로 해석되는 것을 막기 위한 기준이다.

### AI 검토는 read-only로 제한한다

Agent Review Summary는 read-only 지원 산출물이다. 위험, 근거, 한계, 검토 포인트를 설명할 수는 있지만
작업 요청을 승인하거나 정비 상태를 변경하지 않는다.

요약 경로는 다음 규칙을 따른다.

- 입력은 검증된 프로젝트 근거로 구성한 Agent Review Packet이다.
- Packet은 source reference, limitation, read-only domain section을 노출한다.
- 생성된 summary는 packet field에 근거해야 한다.
- 누락되거나 오래된 근거는 정상값으로 보정하지 않고 gap으로 드러낸다.
- Closed-loop 판단은 summary 문장이 아니라 Product Result / Evidence와 snapshot guard를 기준으로 한다.

### Evidence 관련 PR은 전체 소비 경로로 확인한다

AI summary, evidence, report, UI, schema, action flow를 건드리는 변경은 특정 테스트 하나의 통과 여부만
보지 않고 다음 소비 경로로 확인했다.

```text
Generator output
  -> Backend validation / promotion
  -> Product Result / Evidence
  -> AssetDetailViewModel / Agent Review Packet / Report projection
  -> UI or Closed-loop consumer
```

리뷰 기준은 각 경계에서 의미, 소유권, evidence state가 유지되는지 확인하는 것이었다.

### 리뷰 중 발견한 반례는 테스트 또는 기준으로 되돌린다

리뷰 중 발견한 edge case는 다음 리뷰 루프의 입력으로 다뤘다. 후속 조치는 다음 중 하나로 남긴다.

- 해당 failure mode에 대한 regression test
- schema 또는 contract assertion
- review checklist 항목
- `Partially Verified` 같은 더 좁은 상태 표기
- 구현 근거가 아직 없을 때의 plan item

이 방식은 plan, fixture, local observation을 완료된 product behavior처럼 말하는 것을 막는다.

## 2. 기여 범위에서 다룬 경계

이 기여 범위에서 다룬 아키텍처 경계는 다음과 같다.

- Raw Generator output은 UI, Report, Closed-loop, Agent Review에 직접 노출하지 않는다.
- Backend Diagnosis가 Product Result / Evidence를 검증하고 승격하는 경계다.
- UI는 frontend에서 raw source를 join하지 않고 `AssetDetailViewModel`을 소비한다.
- Agent Review Summary는 read-only packet에서 생성하며 snapshot key 기준으로 저장 또는 재사용한다.
- Summary text는 Closed-loop 상태 변경의 권한 근거가 아니다.
- Snapshot basis로 UI, AI review, mutation path가 같은 evidence에 근거하는지 비교한다.
- Runtime visibility surface는 운영자가 존재를 알 수 있게 유지하되, 감사 로그 데이터 조회는
  `admin.audit.read` 권한으로 보호한다.

## 3. 관련 문서 지도

이 문서는 기여 근거의 요약본이다. Evidence Package, Product Result Artifact, ViewModel,
Schema 설계는 각각의 정본 문서와 계약에서 관리한다.

| 주제 | 정본 위치 | 역할 |
| --- | --- | --- |
| Product Result Artifact 설계 | [ADR-004](../architecture-decisions/ADR-004-product-result-evidence-viewmodel-trust-boundary.md), [Product Result / Evidence 신뢰 경계 구현 계획](../plans/ai-workflow/2026-08-29-002-product-result-evidence-materialization-plan.md), [`contracts/schemas/product-result-artifact.schema.json`](../../contracts/schemas/product-result-artifact.schema.json) | raw prediction을 product-facing 판단 artifact로 승격하는 경계 |
| Evidence Package / Evidence Projection 설계 | [PdM Evidence/Report UI 통합 계획](../mvp/pdm-evidence-report-ui-integration-plan.md), [`contracts/schemas/evidence-package.schema.json`](../../contracts/schemas/evidence-package.schema.json), [`contracts/schemas/event-evidence-projection.schema.json`](../../contracts/schemas/event-evidence-projection.schema.json) | 판단 근거, provenance, limitation을 report/UI 소비 형태로 투영하는 계약 |
| AssetDetailViewModel 설계 | [AssetDetailViewModel API MVP Slice](../plans/2026-08-23-001-feat-asset-detail-viewmodel-api-plan.md), [MVP 공통 스키마 정의](../mvp/schema-definition.md), [`contracts/schemas/asset-detail-view-model.schema.json`](../../contracts/schemas/asset-detail-view-model.schema.json) | UI가 raw source를 재조합하지 않고 소비하는 화면용 read model |
| AI Review Packet / Summary 설계 | [AI Context Orchestration Adapter Plan](../plans/ai-workflow/2026-08-29-001-ai-context-orchestration-adapter-plan.md), [`contracts/schemas/agent-review-packet.schema.json`](../../contracts/schemas/agent-review-packet.schema.json), [`contracts/schemas/agent-review-summary.schema.json`](../../contracts/schemas/agent-review-summary.schema.json) | 검증된 evidence를 read-only AI 설명 입력과 저장 가능한 summary로 제한하는 계약 |
| Agent Review Summary 저장 / 재사용 / 실행 기록 | [`agent_review_summary_materialization.py`](../../systems/backend/app/mvp/agent_review_summary_materialization.py), [`agent_review_summary_workflow.py`](../../systems/backend/app/mvp/agent_review_summary_workflow.py), [`mvp_audit_repository.py`](../../systems/backend/app/infra/db/mvp_audit_repository.py), [`0038_agent_review_summary_materialization.sql`](../../systems/backend/migrations/sqlite/0038_agent_review_summary_materialization.sql), [`0040_agent_review_summary_runtime.sql`](../../systems/backend/migrations/postgresql/0040_agent_review_summary_runtime.sql) | UI 조회와 LLM 생성을 분리하고, summary key 기준 저장본 재사용과 workflow run 추적을 제공하는 저장 계약 |
| Watcher / retry / stale recovery | [`watch_agent_review_summaries.py`](../../scripts/watch_agent_review_summaries.py), [`agent_review_summary_workflow.py`](../../systems/backend/app/mvp/agent_review_summary_workflow.py), [`mvp_audit_repository.py`](../../systems/backend/app/infra/db/mvp_audit_repository.py), [`test_agent_review_summary_watcher_cli.py`](../../tests/test_agent_review_summary_watcher_cli.py) | summary key 기반 stale detection, bounded retry, stale running-run 만료, watcher 실행 모드 검증 |
| API 권한 / 감사 조회 경계 | [`router.py`](../../systems/backend/app/mvp/router.py), [`identity_schema.py`](../../systems/backend/app/identity/identity_schema.py), [`permissions.ts`](../../systems/frontend/src/features/mvp/permissions.ts), [`MvpShell.tsx`](../../systems/frontend/src/features/mvp/shell/MvpShell.tsx) | 저장본 조회, 명시 생성, workflow run 감사 조회를 서로 다른 권한과 scope guard로 분리한다. 시스템 관리자 탭은 discoverability를 위해 노출하되 로그 본문/API 데이터는 관리자 감사 권한으로 보호한다. |
| Closed-loop snapshot guard | [Evidence Snapshot Consistency Guard 계획](../plans/ai-workflow/2026-08-29-003-evidence-snapshot-consistency-guard-plan.md), [`maintenance/service.py`](../../systems/backend/app/maintenance/service.py), [`maintenance/api_schema.py`](../../systems/backend/app/maintenance/api_schema.py), [`test_maintenance_loop_application.py`](../../tests/test_maintenance_loop_application.py) | 사용자가 본 evidence snapshot과 mutation 시점 서버 projection의 mismatch를 거부하고 side effect를 막는 guard |
| 공유 Schema 관리 | [`contracts/README.md`](../../contracts/README.md), [`contracts/schemas/README.md`](../../contracts/schemas/README.md) | Producer와 Consumer가 함께 검증하는 기계 판독 계약의 정본 위치 |

`docs/plans/ai-workflow/`는 AI 요약만의 폴더가 아니다. 현재는 Product Result / Evidence
materialization, snapshot guard, Agent Review context orchestration처럼 AI와 인접한 신뢰 경계 계획을
묶어둔 위치다. 다만 기계 판독 Schema의 정본은 `contracts/schemas/`이며, MVP 제품 계약의 읽는 순서는
[`docs/mvp/README.md`](../mvp/README.md)를 따른다.

관련 결정 문서:

- [ADR-003: Generator Runtime Prediction Result 및 Backend Decision 소유권 결정](../architecture-decisions/ADR-003-generator-runtime-prediction-result-and-backend-decision-ownership.md)
- [ADR-004: Product Result / Evidence / ViewModel 신뢰 경계](../architecture-decisions/ADR-004-product-result-evidence-viewmodel-trust-boundary.md)
- [AI Context Orchestration Adapter Plan](../plans/ai-workflow/2026-08-29-001-ai-context-orchestration-adapter-plan.md)
- [Product Result / Evidence 신뢰 경계 구현 계획](../plans/ai-workflow/2026-08-29-002-product-result-evidence-materialization-plan.md)
- [Evidence Snapshot Consistency Guard 계획](../plans/ai-workflow/2026-08-29-003-evidence-snapshot-consistency-guard-plan.md)

## 4. Merged PR 근거

PR #150은 위 경계가 구현과 리뷰 산출물에 반영된 근거다.

- PR: [#150 feat(mvp): 근거 패킷 기반 AI 검토 워크플로우 추가](https://github.com/Biz-CollabCraft/ontology_dashboard/pull/150)
- 확인 상태: 2026-08-31 기준 merged
- 주요 근거:
  - read-only Agent Review Packet
  - grounded Agent Review Summary validation
  - stored summary materialization and reuse
  - summary와 Closed-loop mutation의 권한 분리
  - snapshot basis 노출과 stale-view guard
  - grounding, packet coverage, workflow output, permission boundary 테스트

구현 근거를 설명할 때는 다음 축으로 나누어 읽는다.

| 축 | 구현된 내용 | 대표 근거 |
| --- | --- | --- |
| Product Result 승격 | Generator Prediction Batch item을 Product Result Artifact, PredictionResult, Evidence Projection으로 승격하고 source SHA-256을 계산한다. | `systems/backend/app/diagnosis/materialization.py` |
| 저장본 조회 분리 | GET summary API는 저장본만 조회하고, 없으면 생성하지 않고 pending 상태를 반환한다. | `systems/backend/app/mvp/router.py`, `systems/backend/app/mvp/service.py` |
| 명시 생성 권한 | POST summary API는 `agent.review.materialize` 권한, CSRF, rate limit, project/workspace scope guard를 통과해야 한다. | `systems/backend/app/mvp/router.py`, `systems/backend/app/identity/identity_schema.py` |
| Summary materialization | snapshot, prompt, schema, model, context checksum으로 summary key를 만들고, 동일 key는 저장본을 재사용한다. | `systems/backend/app/mvp/agent_review_summary_materialization.py` |
| Fallback 저장 | LLM provider가 없거나 후보 summary validation이 실패하면 deterministic fallback을 같은 저장 계약으로 남긴다. | `systems/backend/app/mvp/agent_review_summary_materialization.py`, `tests/test_agent_review_summary_contract.py` |
| Workflow run 기록 | summary 생성 시 workflow run을 시작/완료/실패 상태로 기록하고 admin audit view에서 조회한다. | `systems/backend/app/infra/db/mvp_audit_repository.py`, `systems/backend/app/mvp/router.py` |
| Retry / watcher | watcher CLI는 `summary_key` stale policy, watch/once mode, bounded attempts를 노출하고 테스트가 실행 계약을 검증한다. | `scripts/watch_agent_review_summaries.py`, `tests/test_agent_review_summary_watcher_cli.py` |
| Stale reservation recovery | running workflow run이 오래 남은 경우 lease 만료로 failed 처리해 같은 summary key의 후속 생성을 막지 않는다. | `systems/backend/app/infra/db/mvp_audit_repository.py`, `tests/test_mvp.py` |
| DB 계약 | SQLite와 PostgreSQL에 summary/run 테이블을 두고, PostgreSQL은 organization/project RLS policy를 적용한다. | `systems/backend/migrations/sqlite/0037_agent_review_summary_runtime.sql`, `systems/backend/migrations/sqlite/0038_agent_review_summary_materialization.sql`, `systems/backend/migrations/postgresql/0039_agent_review_summary_materialization.sql`, `systems/backend/migrations/postgresql/0040_agent_review_summary_runtime.sql` |
| Snapshot guard | stale client snapshot basis로 inspection request가 들어오면 WorkOrder side effect 없이 거부한다. | `systems/backend/app/maintenance/service.py`, `tests/test_maintenance_loop_application.py` |
| Domain context 확장 | operation, SOP, inspection, ontology를 domain section으로 나누되 public packet은 하나로 유지한다. | `systems/backend/app/mvp/context_providers.py`, `systems/backend/app/mvp/agent_review_packet.py`, `tests/test_agent_review_packet_golden.py` |

## 5. PR #150 이후 보강 후보

PR #150 이후 다음 보강 작업이 이어졌다. 이 항목은 별도 PR 또는 merge 상태를 확인한 뒤 외부 설명에
사용한다.

| 커밋 | 내용 | 근거 |
| --- | --- | --- |
| `bdd3642` | Closed-loop 정비 이력을 Agent Review context adapter로 투영한다. | `systems/backend/app/mvp/context_providers.py`, `tests/test_agent_review_packet_golden.py` |
| `9bfbb34` | 정비 이력 context가 role summary와 summary validation 경로에 반영되도록 보강한다. | `systems/backend/app/mvp/service.py`, `tests/test_mvp.py`, `tests/test_agent_review_summary_contract.py` |

## 6. 외부 설명 문장

이 기여 범위를 외부에서 설명할 때는 다음 문장을 기준으로 사용한다.

```text
MVP 워크플로우 작업에서 업무 착수 전 역할·권한 경계를 먼저 나누고, AI 요약은 검증된
근거만 읽도록 제한했으며, 상태 변경 권한은 Closed-loop 흐름과 분리했습니다. 리뷰 중
발견한 반례는 테스트와 리뷰 기준으로 다시 고정해, 저장된 AI 요약·권한 분리·근거 검증
흐름으로 연결했습니다.
```

## 7. 문서 분할 기준

현재 문서는 개인 기여 근거의 요약본으로 유지한다. 상세 결정과 구현 근거는 기존 ADR, plan, PR로 연결한다.

분할이 필요한 기준은 다음과 같다.

- 권한 경계가 변경되면 ADR 또는 contract 문서로 분리한다.
- 구현 순서나 미완료 항목이 늘어나면 `docs/plans/ai-workflow/` 아래 계획 문서로 분리한다.
- 검증 결과가 반복해서 쌓이면 별도 verification note 또는 PR 본문으로 남긴다.
- 외부 설명 문장은 이 문서에 짧게 유지하고, 세부 근거는 PR과 관련 문서 링크로 연결한다.

## 8. 주장 범위

이 문서는 다음 범위 안에서만 기여를 설명한다.

- 구현 완료 여부는 병합된 PR, 테스트, migration, runtime check가 있는 항목으로 제한한다.
- Agent Review는 read-only 설명 지원이며 작업 요청 승인이나 시스템 상태 변경 권한과 분리한다.
- 누락된 evidence는 summary text로 보완하지 않고 gap, limitation, fallback 상태로 표현한다.
- local verification과 deployed production behavior는 별도 근거로 구분한다.

구현 또는 runtime verification이 필요한 주장은 해당 PR, test, migration, runtime check를 함께 연결한다.
