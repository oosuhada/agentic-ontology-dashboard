# Ontology Dashboard DevSpace Workflow

- Last updated: 2026-08-01
- Purpose: 새로운 ChatGPT 세션이 같은 절차와 기준으로 프로젝트를 이어가도록 한다.

## 1. Required Connector

현재 로컬 프로젝트 작업에는 `DevSpace.mcp`를 사용한다.

프로젝트 경로:

```text
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2
```

반드시 실제 checkout 모드로 연다.

```text
mode: checkout
```

Git commit·push는 현재 작업 범위에서 제외한다. 사용자가 명시적으로 별도 Git connector를 연결하기 전에는 Git write를 시도하지 않는다.

## 2. New Session Startup Sequence

새로운 세션은 반드시 다음 순서를 따른다.

```text
1. DevSpace로 프로젝트 열기
2. docs/next-session-master-prompt.md 읽기
3. 00-project-charter.md 읽기
4. 01-system-architecture.md 읽기
5. 02-domain-model.md 읽기
6. 03-project-roadmap.md 읽기
7. 04-release-checklist.md 읽기
8. 05-dataset-strategy.md 읽기
9. 06-project-catalog.md 읽기
10. 07-implementation-status.md 읽기
11. 현재 코드와 문서 차이 분석
12. release gate baseline 확인
13. Roadmap의 NEXT 작업 수행
14. 관련 문서 업데이트
15. release gate 재실행
```

문서만 읽고 완료했다고 판단하지 않는다. 현재 코드, test, migration, UI 구조와 비교한다.

## 3. Working Rules

### Before Editing

- 현재 branch와 working tree는 Git inspection으로만 확인한다.
- 관련 source와 tests를 읽는다.
- 기존 feature와 release gate 영향을 파악한다.
- 변경 범위를 명확히 정한다.

### During Editing

- 새 제품명은 `Ontology Dashboard`만 사용한다.
- Project scope를 우회하는 dataset-specific 전역 상태를 추가하지 않는다.
- Prediction logic을 Dashboard UI에 넣지 않는다.
- adapter와 contract를 통해 입력한다.
- tenant와 project scope를 repository query에서 적용한다.
- migration 없이 persistence schema를 암묵적으로 변경하지 않는다.
- handler, service, repository 책임을 분리한다.
- 큰 파일에 모든 책임을 다시 모으지 않는다.

### After Editing

- targeted tests 실행
- TypeScript/build 실행
- 전체 release gate 실행
- implementation status 업데이트
- roadmap 상태 업데이트
- architecture/domain model 변경 시 관련 문서 업데이트
- 새 Project나 dataset이면 catalog와 dataset strategy 업데이트

## 4. DevSpace Tool Usage

### Read

직접 파일 내용을 확인할 때 사용한다.

### Write

새 파일 또는 전체 재작성에 사용한다.

### Edit

기존 파일의 정확한 부분을 수정할 때 사용한다.

### Bash

다음 용도로만 사용한다.

- tests
- build
- compile
- release gate
- read-only search
- file discovery
- Git inspection

Bash redirection이나 script를 이용해 파일을 작성하지 않는다.

## 5. Test Commands

### Backend

```bash
PYTHONPATH=api:ml/src .venv/bin/python -m pytest -q tests
```

### Canonical Naming

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/check_canonical_naming.py
```

### PostgreSQL Migration and RLS

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/check_postgresql_migration.py
```

### Frontend

```bash
npm --prefix web test
npm --prefix web run lint
npm --prefix web run build
```

### Full Gate

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/release_gate.py --with-e2e
```

## 6. Documentation Update Matrix

| 변경 종류 | 업데이트할 문서 |
|---|---|
| 프로젝트 목적/원칙 | 00-project-charter |
| 구조·layer·flow | 01-system-architecture |
| entity/relation/scope | 02-domain-model |
| stage·priority | 03-project-roadmap |
| gate·acceptance | 04-release-checklist |
| dataset·adapter 전략 | 05-dataset-strategy |
| Project 추가/상태 | 06-project-catalog |
| 구현률·리스크 | 07-implementation-status |
| 작업 절차 변경 | 08-devspace-workflow |
| 다음 세션 지시 | next-session-master-prompt |

## 7. Decision Rules

### Project Layer Before Dataset Feature

새 dataset 기능을 구현하기 전 Project scope가 준비되어 있는지 확인한다.

준비되지 않았다면 Project Layer를 먼저 구현한다.

### Contract Before Transport

파일, API, Kafka 중 무엇을 사용할지 결정하기 전에 Prediction Result Contract를 정의한다.

### Evidence Before Narrative

리포트 문장을 먼저 만들지 않는다. 계산 가능한 Evidence와 lineage를 먼저 만든다.

### PostgreSQL Honesty

DDL과 migration이 존재하더라도 모든 repository가 PostgreSQL에서 작동하지 않으면 production PostgreSQL 완료라고 표시하지 않는다.

### No Silent Scope Expansion

사용자가 요청하지 않은 범용 ERP/MES platform이나 graph database 전환을 임의로 추진하지 않는다.

## 8. Completion Report Format

작업 종료 시 다음 형식으로 보고한다.

```text
1. 수행한 작업
2. 주요 파일
3. 아키텍처 영향
4. 테스트와 release gate 결과
5. 구현률 변화
6. 남은 작업
7. 다음 추천 단계
8. 문서 업데이트 내역
```

실패한 test나 구현하지 못한 작업을 숨기지 않는다.

## 9. Current Preferred Next Work

```text
Project Layer phase 2: operational repository project scope
→ Dashboard key migration과 Project selector E2E
→ Prediction Result Contract
→ Dataset Manifest/File Adapter
→ Azure Fleet Maintenance Project
```

다음 세션은 별도 지시가 없다면 위 순서를 따른다.
