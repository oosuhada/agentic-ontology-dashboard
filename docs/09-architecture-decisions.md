# Ontology Dashboard Architecture Decisions

- Last updated: 2026-08-01
- Format: lightweight Architecture Decision Record

## ADR-001 — Canonical Product Name

### Decision

제품 canonical name은 `Ontology Dashboard`로 한다.

### Context

초기 임시 명칭이 제조 예지보전 하나의 use case를 제품 전체 정체성으로 오해하게 만들었다.

### Consequences

- 신규 code, API, docs, CI, schema는 Ontology Dashboard naming 사용
- 제조 기능은 domain pack 또는 Project 이름에만 존재
- 과거 명칭은 migration history 외 사용 금지

## ADR-002 — Prediction and Dashboard Separation

### Decision

Prediction Module과 Dashboard Platform을 분리하고 Prediction Result Contract를 경계로 사용한다.

### Context

자동 감지는 API 호출, 파일 전달, message broker 등 다양한 방식으로 결과를 전달할 수 있다.

### Consequences

- Dashboard는 모델 구현에 직접 의존하지 않음
- File Adapter부터 시작 가능
- transport를 바꿔도 Dashboard contract 유지
- model version과 analysis run lineage 기록 필요

## ADR-003 — Project-Centered Architecture

### Decision

여러 dataset을 하나의 global workspace에 합치지 않고 Project 단위로 구성한다.

### Context

Azure PdM, MetroPT, AI4I, C-MAPSS, CiP-DMD는 분석 단위와 event 의미가 다르다.

### Consequences

- Project selector 필요
- Project별 dataset, ontology mapping, dashboard template, analysis profile 관리
- persistence record에 project_id 필요
- project isolation test와 RLS 필요

## ADR-004 — Project Is Not Dataset

### Decision

Project는 dataset보다 큰 application aggregate로 정의한다.

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

### Consequences

- dataset version과 Project lifecycle 분리
- 하나의 Project가 여러 data source를 가질 수 있음
- 같은 dataset으로 다른 목적의 Project를 만들 수 있음

## ADR-005 — Azure PdM as Primary Showcase

### Decision

Azure Predictive Maintenance dataset을 fleet maintenance showcase Project의 우선 후보로 사용한다.

### Rationale

- machine fleet 비교
- telemetry/error/failure/maintenance 연결
- 역할 기반 우선순위와 조치 근거 제공 가능

### Caveat

숫자와 지표는 ingestion 후 코드로 재현하고, license/provenance를 검증해야 한다.

## ADR-006 — MetroPT as Second Abstraction Test

### Decision

두 번째 Project 후보로 MetroPT-3를 우선 검토한다.

### Rationale

Azure의 fleet history 구조와 달리 고밀도 time-series 구조이므로 platform abstraction 재사용성을 검증하기 좋다.

## ADR-007 — Ontology Core and Project Domain Mapping

### Decision

공통 Ontology Core와 Project-specific Domain Schema를 분리한다.

### Core

- Asset
- Observation
- Event
- AnalysisRun
- Evidence
- Recommendation
- Action

### Consequences

- dataset-specific 속성을 Core에 무분별하게 추가하지 않음
- Project adapter가 Core mapping 담당
- enterprise ontology가 불필요한 dataset에서도 최소 domain model 유지

## ADR-008 — Modular Monolith Before Distributed Services

### Decision

현재는 modular monolith를 유지한다.

### Rationale

- 팀과 MVP 규모
- transaction과 authorization 경계 단순화
- 빠른 회귀 검증

### Consequences

feature module과 repository 경계를 명확히 유지하고, 분산 서비스는 실제 scaling requirement 이후 평가한다.

## ADR-009 — PostgreSQL as Production Target

### Decision

SQLite는 local/demo compatibility, PostgreSQL은 production target으로 사용한다.

### Consequences

- migration runner
- JSONB
- RLS
- connection pool
- transactional outbox
- backup/restore

전체 repository 전환 전에는 PostgreSQL production 완료라고 표시하지 않는다.

## ADR-010 — Safe Planner Boundary

### Decision

LLM 또는 planner는 typed intent와 catalog 기반 결과만 생성한다.

### Consequences

- arbitrary SQL/Cypher/React 실행 금지
- recommendation과 draft 자동 persistence 금지
- Evidence 없는 narrative claim 금지
- provider failure 시 deterministic fallback

## ADR-011 — Documentation as Session Entry Point

### Decision

`docs/next-session-master-prompt.md`를 모든 새로운 AI 작업 세션의 공식 진입점으로 사용한다.

### Consequences

- 새 세션은 charter, architecture, domain, roadmap, release, dataset, catalog, status, workflow 문서를 순서대로 읽음
- 작업 후 코드와 문서를 함께 업데이트
- 반복 설명을 줄이고 설계 의도 유지

## ADR-012 — Project Context Is Explicit and Workspace Is Subordinate

### Decision

Frontend route와 Project API는 Project를 먼저 선택하고, Workspace는 선택된 Project 아래에서만 조회한다.

PostgreSQL session context는 `app.organization_id`와 선택적 `app.project_id`를 사용한다. Workspace scope는 기존 호환 경계로 유지하지만 Project aggregate를 대체하지 않는다.

### Consequences

- canonical route foundation은 `/app/projects/:projectId`다.
- `workspaces.project_id`가 필수 관계의 migration target이다.
- Project 접근 목록과 Workspace 목록은 organization/project predicate를 사용한다.
- Project membership은 현재 Workspace scope에서 backfill하지만, target은 독립적인 project-level role assignment다.
- Dashboard·Ontology·Action repository가 project_id를 직접 저장하기 전까지 Project Layer 완료로 표시하지 않는다.
