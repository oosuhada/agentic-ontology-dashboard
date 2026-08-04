# Next Session Master Prompt — Ontology Dashboard

이 파일은 새로운 ChatGPT/AI 작업 세션의 유일한 공식 진입점이다.

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

2026-08-01 기준 baseline:

```text
Backend        93%
Frontend       89%
Architecture   95%
PostgreSQL     70%
Project Layer  60%
Adapter Layer  10%
```

자동화 baseline:

```text
Canonical naming: 84 files, 0 violations
PostgreSQL organization/project migration/RLS: PASS
Backend tests: 65 PASS
Gold scenarios: 8/8 PASS
Frontend unit tests: 1 PASS
TypeScript: PASS
Production build: PASS
Playwright E2E: 14 PASS
Release gate: 12/12 PASS
```

작업 시작 전에 현재 실행 결과가 이 baseline과 일치하는지 필요한 범위에서 검증한다.

## 8. Current Priority

별도 사용자 지시가 없다면 `docs/10-product-convergence-polyglot-agentic-roadmap.md` 순서를 따른다.

```text
1. Stage 44 — 문서·ADR·우선순위 rebaseline
2. Stage 45 — planner canonical migration + Project 3 typed client + Ontology preview
3. Stage 46 — PostgreSQL + pgvector + Neo4j local stack
4. Stage 47 — Dataset Version과 multi-store projection
5. Stage 48 — Ontology Workbench 완성
6. Stage 49 — LangGraph multi-store query orchestration
7. Stage 50 — Dataset Catalog와 materialization
8. Stage 51 — Governance Workbench
9. Stage 52 — server-scale Analysis/Dashboard
10. Stage 53~55 — WorkOrder ontology, visual convergence, production release gate
```

Project Layer와 PostgreSQL 작업은 폐기하지 않는다. 새 Stage에서 multi-store identity, project isolation, Workbench delivery와 함께 완성한다.

## 9. Immediate Next Task Definition

현재 가장 우선인 작업은 **Stage 45 vertical slice — Planner Canonical Migration + Project 3 Typed Client + Ontology Workbench Preview**다.

검증된 현재 상태:

- canonical planner는 `api/ontology_dashboard/planner/`에 있고 legacy planner 파일은 compatibility re-export 경계다.
- Project 3에는 Neo4j, Text-to-Cypher LangGraph, graph schema/search/subgraph, LlamaIndex RAG가 있으며 Project 2는 typed `Project3Client`로만 접근한다.
- Ontology, Governance, Agent Evidence Workbench는 실제 project/workspace route, permission guard, degraded mode와 Playwright E2E가 연결됐다.
- Dataset Version/projection/mapping/materialization backend와 초기 Dataset Catalog route가 있다.
- Project 2 local pgvector는 health/schema/projection contract만 있으며 runtime semantic retrieval은 현재 Project 3 RAG를 사용한다.
- `api/ontology_dashboard/__init__.py`의 legacy path extension과 물리 `factory_signal_board` package 제거는 Stage 55 canonical debt로 남아 있다.

다음 최소 구현 목표:

- `docs/autonomous-implementation-progress.md`의 Next Exact Action과 첫 미완료 Stage를 기준으로 시작한다.
- 현재 우선순위는 Stage 50 Dataset Catalog completion, Stage 52 server-scale Analysis/Dashboard, Stage 53 WorkOrder, Stage 54 bundle/visual convergence다.
- architecture-only 작업으로 끝내지 않고 실제 route, permission, user journey, screenshot artifact까지 함께 전달한다.
- organization/project/workspace/role scope와 arbitrary SQL/Cypher 금지 경계를 유지한다.
- Dashboard/Analysis/Ontology/Agent/Governance 기존 회귀를 유지한다.

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

가장 먼저 docs/next-session-master-prompt.md, docs/autonomous-implementation-progress.md와 docs/10-product-convergence-polyglot-agentic-roadmap.md를 읽고, 필수 문서들을 순서대로 검토해줘. 문서 내용과 현재 코드·테스트·migration·frontend route, 그리고 Project 3의 Neo4j/LangGraph/RAG 구조를 비교해 차이를 파악한 뒤 progress 문서의 Next Exact Action과 첫 미완료 Stage부터 이어서 구현해줘.

반드시 다음 원칙을 지켜줘.

- 제품명과 canonical namespace는 Ontology Dashboard / ontology_dashboard로 유지
- Factory Signal Board 이름이나 namespace를 다시 만들지 않기
- Organization → Project → Workspace → Role Dashboard 구조 유지
- Project는 Dataset과 동일시하지 않기
- Prediction과 Dashboard를 Prediction Result Contract로 분리
- PostgreSQL operational data, Neo4j relationship graph, pgvector/LlamaIndex semantic retrieval을 동일 Project identity로 연결
- Project 3의 Text-to-Cypher/LangGraph/RAG를 중복 구현하지 않고 typed client로 재사용
- 검증되지 않은 arbitrary SQL/Cypher 실행 금지
- architecture-only 작업으로 끝내지 않고 실제 Ontology Workbench route까지 구현
- tenant/project scope를 API·repository·UI에서 검증
- 기존 release gate와 Gold/E2E 회귀 유지
- Git commit·push 등 Git write는 수행하지 않기
- 코드 변경과 함께 관련 docs를 업데이트하기

작업 완료 후 수행 내용, 주요 파일, 테스트 결과, 구현률 변화, 남은 위험과 다음 추천 작업을 정리해줘.
```
