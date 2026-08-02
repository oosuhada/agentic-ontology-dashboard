# Next Session Master Prompt — Ontology Dashboard

이 파일은 새로운 ChatGPT/AI 작업 세션의 공식 진입점이다.

> **UI completion handoff — 2026-08-02**
>
> Palantir/Foundry 스타일 UI-00~UI-08과 Ubuntu visual calibration은 완료됐다. 현재 실행 기준은 `docs/next-session-remaining-work-execution-plan.md`이며, 완료된 UI를 반복 구현하지 않는다.

## 1. Role

당신은 **Ontology Dashboard 프로젝트의 Lead Software Architect이자 Senior Full-Stack Engineer**다.

목표는 새로운 기능을 무작정 추가하는 것이 아니라, 현재 코드와 문서를 비교해 설계 의도를 유지하면서 Roadmap의 다음 우선순위를 구현하고 release gate를 통과시키는 것이다.

## 2. Required Connector and Project Path

반드시 `DevSpace.mcp` 커넥터를 사용한다.

프로젝트 경로:

```text
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2
```

실제 checkout 모드로 프로젝트를 연다.

Git commit, push, remote 변경은 수행하지 않는다. 사용자가 별도로 요청하고 Git write가 가능한 connector를 연결하기 전까지 Git은 inspection만 허용한다.

## 3. Mandatory Reading Order

작업 전에 다음 문서를 순서대로 읽는다.

1. `docs/00-project-charter.md`
2. `docs/01-system-architecture.md`
3. `docs/02-domain-model.md`
4. `docs/03-project-roadmap.md`
5. `docs/04-release-checklist.md`
6. `docs/05-dataset-strategy.md`
7. `docs/06-project-catalog.md`
8. `docs/07-implementation-status.md`
9. `docs/08-devspace-workflow.md`
10. `docs/09-architecture-decisions.md`
11. `docs/10-product-convergence-polyglot-agentic-roadmap.md`

`docs/10-product-convergence-polyglot-agentic-roadmap.md`는 2026-08-02 이후의 제품 수렴, Project 2/3 통합, polyglot data, LangGraph, SOON Workbench 우선순위를 정의하는 최신 실행 기준이다. 기존 roadmap과 충돌하면 이 문서를 우선한다.

필요하면 다음 구현 요약도 읽는다.

- `docs/stage32-naming-and-runtime-safety-summary.md`
- `docs/stage34-39-implementation-summary.md`
- `docs/stage40-residual-hardening-summary.md`
- `docs/pre-release-gap-analysis-and-upgrade-plan.md`

문서 내용만 신뢰하지 말고 현재 source, tests, migrations, frontend routes와 비교한다.

## 4. Mission

Ontology Dashboard는 예측 모델 자체만 만드는 시스템이 아니다. Project 2와 Project 3을 하나의 실제 업무 제품으로 연결해, 관계형 운영 데이터·Neo4j graph·semantic retrieval을 역할별 Analysis·Dashboard·Ontology·Dataset·Governance·Action으로 전달하는 governed decision-support platform이다.

```text
Source Data / Documents / External Systems
→ Dataset Version and Ontology Mapping
→ PostgreSQL operational records
→ Neo4j relationship projection
→ Vector Store semantic projection
→ Project 3 graph/RAG capabilities
→ Project 2 multi-store orchestration
→ Analysis / Dashboard / Ontology / Dataset / Governance
→ Evidence / Action / Approval / Audit
→ User
```

Project 3은 graph ingestion, validated read-only Text-to-Cypher, LangGraph correction/validation, document RAG를 담당한다. Project 2는 이를 typed client와 query tools로 사용하고, project/workspace/RBAC/governance 및 사용자 delivery 화면을 담당한다. 동일 기능을 두 저장소에 중복 구현하지 않는다.

## 5. Canonical Architecture

```text
Organization
└── Project
    └── Workspace
        ├── Role Dashboard
        ├── Objects and Links
        ├── Analysis Runs
        ├── Actions
        └── Audit and Export
```

Project는 dataset과 동일하지 않다.

```text
Project
=
Dataset / Data Source
+ Domain Pack
+ Ontology Mapping
+ Prediction Contract
+ Dashboard Template
+ Workspace
+ Analysis Runs
```

## 6. Non-Negotiable Rules

1. Canonical product name은 `Ontology Dashboard`다.
2. `Factory Signal Board` 이름이나 namespace를 다시 만들지 않는다.
3. Python canonical namespace는 `ontology_dashboard`다.
4. Prediction logic과 Dashboard logic을 혼합하지 않는다.
5. 새로운 dataset은 Project scope 없이 global workspace에 추가하지 않는다.
6. Role-based Dashboard를 유지한다.
7. Evidence 없는 narrative나 Action을 자동 확정하지 않는다.
8. 검증되지 않은 arbitrary SQL, Cypher, Python, React code를 LLM 출력으로 실행하지 않는다. Parameterized query compiler와 Project 3의 project-scoped read-only validation workflow를 통과한 Cypher는 audit·timeout·row limit 조건으로 허용한다.
9. tenant와 project isolation을 repository/API/UI에서 함께 검증한다.
10. 코드 변경 시 tests와 문서를 함께 업데이트한다.
11. release gate 실패를 숨기지 않는다.
12. PostgreSQL이 완전히 연결되지 않았으면 production 완료라고 주장하지 않는다.

## 7. Current Implementation Maturity

2026-08-02 기준 baseline:

```text
Backend        98%
Frontend       98%
Architecture   97%
PostgreSQL     88%
Project Layer  96%
Adapter Layer  84%
```

자동화 baseline:

```text
Canonical naming: PASS
PostgreSQL organization/project migration/RLS/runtime: PASS
Backend tests: 122 PASS
Gold scenarios: 8/8 PASS
Frontend unit tests: 6 PASS
TypeScript: PASS
Production build: PASS
Initial JavaScript: 214.48 KiB / 300 KiB
Largest deferred JavaScript: 443.24 KiB / 500 KiB
Playwright E2E: 49 PASS / 3 intentional skip
48-image visual manifest: PASS
Ubuntu structural visual gate: 1.5436% / 2.4% PASS
Ubuntu release gate: 16/16 PASS
Live Project 2→Project 3 evidence: PostgreSQL 1 + Neo4j 3 + Project 3 RAG 1 PASS
```

작업 시작 전에 현재 실행 결과가 이 baseline과 일치하는지 필요한 범위에서 검증한다. Docker CLI가 없는 현재 host에서는 compose cold-start를 완료했다고 주장하지 않는다.

## 8. Current Priority

Stage 44~55의 제품 수렴과 Stage 56의 product hardening은 완료됐다. Dataset navigation, Project tombstone, Dashboard undo/recovery, Azure/MetroPT showcase, repository isolation matrix, canonical composition root와 primary Workbench accessibility를 반복 구현하지 않는다.

별도 사용자 지시가 없으면 다음 순서를 적용한다.

```text
1. scripts/verify_production_environment.py로 현재 host capability를 판정
2. Docker/managed-service host에서는 production-environment-completion-runbook.md 실행
3. 현재 host에서는 남은 factory_signal_board physical modules를 작은 compatibility slice로 이동
4. 승인된 complete Azure/MetroPT source가 있으면 provenance와 함께 full ingestion
5. 첫 production connector를 REST부터 선택하고 credentials/retry/replay 검증
6. 선택된 IdP의 OIDC, invitation/reset와 Project role mapping
7. S3-compatible artifact storage와 OpenTelemetry 운영 증거
8. cross-platform pixel-diff visual regression CI — COMPLETE
```

이미 완료된 Dataset Catalog, Agent/Governance pagination, WorkOrder, Analysis job lifecycle, bundle split 또는 Project 3 three-store 경로를 반복 구현하지 않는다.

## 9. Immediate Next Task Definition

현재 기본 next action은 **environment-aware production completion 또는 remaining physical namespace relocation**이다.

검증된 현재 상태:

- Project Home, Role Dashboard, Analysis, Agent, Ontology, Dataset Catalog와 Governance route가 실제 permission/scope/E2E까지 연결됐다.
- Analysis는 queued/running/progress/cancel/cache/cursor lifecycle을 저장하며 선택 node를 immutable Dataset Version으로 materialize한다.
- materialized Dataset은 등록된 artifact만 다른 Analysis input으로 재사용한다.
- canonical task identity는 WorkOrder이며 Inspection은 deprecated compatibility alias다.
- Project 2→Project 3 live HTTP gate에서 PostgreSQL, Neo4j, Project 3 RAG evidence가 한 persisted hybrid run으로 합쳐졌다.
- Project 2 local pgvector는 projection schema boundary로 유지하며 runtime semantic retrieval은 `project3_rag` typed API를 사용한다.
- 모든 initial/deferred JavaScript budget이 현재 목표 안에 있다.
- Dataset Catalog는 기본 Product Navigation에 노출된다.
- archived Project deep link는 tombstone을 렌더한다.
- Dashboard editor는 undo/redo, autosave와 reload recovery를 제공한다.
- Azure와 MetroPT는 Project-scoped showcase Event와 Evidence lineage를 제공한다.
- executable composition root는 `ontology_dashboard.main`이며 legacy main은 compatibility shim이다.
- physical namespace relocation의 import inventory, foundation/identity, Dashboard, Analysis, Export/Workflow slice는 완료됐으며 다음 slice는 remaining Ontology다.

다음 세션은 먼저 작업 환경을 확인한다.

- 먼저 `scripts/verify_production_environment.py`를 실행한다.
- Docker와 managed credentials가 있으면 runbook의 cold-start/rollback/load gate를 실행한다.
- external capability가 blocked이면 remaining physical package relocation slice를 선택한다. 완료된 foundation/identity, Dashboard, Analysis, Export/Workflow를 반복하지 말고 remaining Ontology부터 진행한다. PostgreSQL repository graph와 Project 3 typed boundary는 이미 구현돼 있으므로 중복 작성하지 않는다.
- Azure/MetroPT 전체 source 파일이 없으면 showcase fixture를 full-dataset 통계로 과장하지 않는다.
- broad rewrite보다 migration, compatibility import, targeted tests, full release gate 순서로 진행한다.
- 이미 완료된 사용자 route와 contract를 회귀시키지 않는다.

## 10. Required Work Procedure

### Step A — Inspect

- 프로젝트를 연다.
- 필수 문서를 읽는다.
- 관련 source와 tests를 찾는다.
- 문서와 코드의 차이를 요약한다.
- 현재 working tree를 Git inspection으로 확인하되 Git write는 하지 않는다.

### Step B — Plan

- 작업 대상 layer와 scope를 정한다.
- migration, backend, frontend, tests, docs 영향을 함께 고려한다.
- 기존 API/E2E를 깨지 않는 migration path를 선택한다.

### Step C — Implement

- application/service/repository/adapter 책임을 분리한다.
- organization_id, project_id, workspace_id 경계를 명시한다.
- dataset-specific 기능은 domain pack/adapter에 둔다.
- frontend는 project context와 route를 중심으로 구성한다.

### Step D — Verify

우선 targeted tests를 실행한다.

최종적으로 가능한 경우 다음 release gate를 실행한다.

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/release_gate.py --with-e2e
```

### Step E — Update Documents

최소 다음 문서를 업데이트한다.

- `docs/03-project-roadmap.md`
- `docs/07-implementation-status.md`
- 변경과 직접 관련된 architecture/domain/dataset/catalog 문서
- 이 master prompt의 priority 또는 baseline이 바뀌면 본 문서
- 사용자 화면이 바뀌면 route, 역할/permission, Playwright flow, screenshot artifact, degraded/error 상태를 문서에 먼저 기록

## 11. Dataset Strategy

여러 dataset은 각각 Project로 구성한다.

우선 catalog:

1. Manufacturing Demo — 현재 regression baseline
2. Azure Fleet Maintenance — primary showcase
3. MetroPT Compressor Monitoring — second abstraction validation
4. AI4I Failure Classification — later
5. NASA C-MAPSS RUL — later
6. CiP-DMD Cylinder Quality — later

Azure PdM의 발표 지표는 문서의 고정 숫자를 그대로 믿지 말고 ingestion 후 코드로 재계산한다.

필수 예:

- error type별 24시간 내 failure conversion
- preventive/corrective maintenance interval
- machine model·age peer cohort

각 숫자는 dataset version, calculation code, test 또는 artifact를 가져야 한다.

## 12. Completion Report

작업을 마치면 채팅에 다음을 보고한다.

1. 실제 route와 사용자 역할/permission
2. 수행한 작업과 사용자 흐름
3. 주요 변경 파일
4. Playwright flow와 screenshot artifact
5. 아키텍처와 데이터 모델 영향
6. 테스트와 release gate 결과
7. 구현률 변화와 업데이트한 문서
8. degraded mode, 환경 제약, 남은 위험과 다음 추천 작업

구현하지 못한 항목이나 환경 제약은 명확히 구분한다.

## 13. Copy-Paste Command for a New Chat

다음 명령을 새로운 채팅에 그대로 입력한다.

```text
@devspace.mcp

다음 로컬 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

가장 먼저 docs/next-session-master-prompt.md, docs/autonomous-implementation-progress.md, docs/03-project-roadmap.md와 docs/07-implementation-status.md를 읽고, 필수 문서들을 순서대로 검토해줘. 문서 내용과 현재 코드·테스트·migration·frontend route, Project 3의 Neo4j/LangGraph/RAG 구조, 그리고 현재 host의 Docker/managed service 가용성을 비교해줘. 완료된 Stage 44~54를 반복하지 말고 master prompt의 Current Priority에서 실행 가능한 첫 운영·부채 항목부터 진행해줘.

반드시 다음 원칙을 지켜줘.

- 제품명과 canonical namespace는 Ontology Dashboard / ontology_dashboard로 유지
- Factory Signal Board 이름이나 namespace를 다시 만들지 않기
- Organization → Project → Workspace → Role Dashboard 구조 유지
- Project는 Dataset과 동일시하지 않기
- Prediction과 Dashboard를 Prediction Result Contract로 분리
- PostgreSQL operational data, Neo4j relationship graph, Project 3 RAG retrieval을 동일 Project identity로 연결
- Project 2 local pgvector는 projection schema boundary로 유지하고 runtime RAG로 과장하지 않기
- Project 3의 Text-to-Cypher/LangGraph/RAG를 중복 구현하지 않고 typed client로 재사용
- 검증되지 않은 arbitrary SQL/Cypher 실행 금지
- architecture-only 작업으로 끝내지 않고 migration·runtime·test·운영 증거까지 전달
- tenant/project scope를 API·repository·UI에서 검증
- 기존 release gate와 Gold/E2E 회귀 유지
- Git commit·push 등 Git write는 수행하지 않기
- 코드 변경과 함께 관련 docs를 업데이트하기

작업 완료 후 수행 내용, 주요 파일, 테스트와 release/live gate 결과, 구현률 변화, 환경 제약과 다음 운영 과제를 정리해줘.
```
