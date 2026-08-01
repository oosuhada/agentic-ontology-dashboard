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

필요하면 다음 구현 요약도 읽는다.

- `docs/stage32-naming-and-runtime-safety-summary.md`
- `docs/stage34-39-implementation-summary.md`
- `docs/stage40-residual-hardening-summary.md`
- `docs/pre-release-gap-analysis-and-upgrade-plan.md`

문서 내용만 신뢰하지 말고 현재 source, tests, migrations, frontend routes와 비교한다.

## 4. Mission

Ontology Dashboard는 예측 모델 자체를 만드는 시스템이 아니다.

Prediction Module 또는 외부 자동 분석 시스템이 생성한 결과를 공통 Prediction Result Contract로 받아, 역할별 Dashboard·Report·Evidence·Action으로 전달하는 Decision Support Platform이다.

```text
Source Data / External System
→ Prediction Module
→ Prediction Result Contract
→ Ontology Dashboard
→ Role Dashboard / Report / Action
→ User
```

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
8. arbitrary SQL, Cypher, Python, React code를 LLM 출력으로 실행하지 않는다.
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

별도 사용자 지시가 없다면 다음 순서로 진행한다.

```text
1. Project Layer phase 2 — operational repository와 Dashboard key의 project scope
2. 다중 Project switch E2E, deleted route handling, active project persistence
3. Prediction Result JSON Schema
4. Dataset Manifest와 File Adapter
5. Azure Fleet Maintenance Project ingestion
6. MetroPT Project로 abstraction 검증
7. PostgreSQL repository runtime 완료
8. 남은 handler와 physical legacy source 이동
9. Production operations hardening
```

## 9. Immediate Next Task Definition

현재 가장 우선인 작업은 **Project Layer phase 2**다.

완료된 foundation:

- projects persistence schema/migration
- Project model/repository/service와 list/detail/admin API
- organization-scoped Project access와 negative tests
- `workspaces.project_id`
- current Manufacturing Demo Project seed/migration
- principal `project_scopes`와 초기 `active_project_id`
- Project selector와 `/app/projects/:projectId` route foundation
- PostgreSQL organization/project RLS 검증
- 기존 Gold/E2E 회귀 유지

다음 최소 구현 목표:

- Dashboard Template/preference/saved view/share key에 project scope 추가
- Ontology object/link/action/workflow/export repository에 project_id write/query 적용
- active project session persistence 또는 명시적 context contract
- 두 번째 fixture Project를 이용한 switch/isolation E2E
- deleted Project route handling과 active project persistence

작업 규모가 크면 안전한 하위 단계로 나누되, 단순 계획만 작성하고 멈추지 말고 검증 가능한 코드까지 구현한다.

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

1. 수행한 작업
2. 주요 변경 파일
3. 아키텍처와 데이터 모델 영향
4. 테스트와 release gate 결과
5. 구현률 변화
6. 업데이트한 문서
7. 남은 제약과 위험
8. 다음 추천 작업

구현하지 못한 항목이나 환경 제약은 명확히 구분한다.

## 13. Copy-Paste Command for a New Chat

다음 명령을 새로운 채팅에 그대로 입력한다.

```text
@devspace.mcp

다음 로컬 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

가장 먼저 docs/next-session-master-prompt.md를 읽고, 그 문서에 명시된 필수 문서들을 순서대로 모두 검토해줘. 문서 내용과 현재 코드·테스트·migration·frontend 구조를 비교해서 차이를 파악한 뒤, 별도 지시가 없으면 Roadmap의 최우선 작업인 Project Layer 구현을 이어서 진행해줘.

반드시 다음 원칙을 지켜줘.

- 제품명과 canonical namespace는 Ontology Dashboard / ontology_dashboard로 유지
- Factory Signal Board 이름이나 namespace를 다시 만들지 않기
- Organization → Project → Workspace → Role Dashboard 구조 유지
- Project는 Dataset과 동일시하지 않기
- Prediction과 Dashboard를 Prediction Result Contract로 분리
- tenant/project scope를 API·repository·UI에서 검증
- 기존 release gate와 Gold/E2E 회귀 유지
- Git commit·push 등 Git write는 수행하지 않기
- 코드 변경과 함께 관련 docs를 업데이트하기

작업 완료 후 수행 내용, 주요 파일, 테스트 결과, 구현률 변화, 남은 위험과 다음 추천 작업을 정리해줘.
```
