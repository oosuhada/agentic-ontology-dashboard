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

- 검증되지 않은 arbitrary SQL/Cypher/React 실행 금지
- parameterized query compiler와 Project 3의 project-scoped read-only validation workflow를 통과한 Cypher는 실행 가능
- generated query는 timeout, row/depth limit, statement hash, source version, audit trace를 가져야 함
- recommendation과 draft 자동 persistence 금지
- Evidence 없는 narrative claim 금지
- provider failure 시 deterministic fallback 또는 명시적 degraded mode

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

## ADR-013 — Project 2 and Project 3 Form One Integrated Product

### Context

Project 2와 Project 3은 회사의 하나의 실제 업무를 구현 과제상 두 부분으로 나눈 것이다. Project 3에는 Neo4j graph ingestion, validated Text-to-Cypher LangGraph, graph exploration, LlamaIndex RAG가 구현돼 있다. Project 2는 이를 단순 checklist와 문자열 source reference로만 소비하고 있어 실제 제품 통합 수준에 도달하지 못했다.

### Decision

- Project 3은 graph/RAG knowledge capability를 소유한다.
- Project 2는 Project 3을 typed service client와 query tool로 사용한다.
- Project 2는 Project/Workspace/RBAC/Governance, Analysis, Dashboard, Ontology, Dataset, Action delivery를 소유한다.
- 현재 runtime에서 Project 2의 Neo4j driver 사용은 connectivity health probe로 제한한다. deterministic graph board와 ontology explorer의 업무 조회도 우선 Project 3 typed graph API를 사용한다.
- 향후 Project 2 direct read-only template port를 추가하더라도 등록된 query ID와 typed parameter만 허용하며 자연어 Text-to-Cypher는 Project 3의 검증 workflow를 재사용한다.
- 동일 agent, ETL, RAG 구현을 두 저장소에 복제하지 않는다.
- Project 3 장애 시 relational 운영 화면은 degraded mode로 유지한다.

### Consequences

- `project3-adapter-contract.md`의 flat context contract는 compatibility contract가 된다.
- Project 2에 Project 3 health/query/RAG/graph client가 필요하다.
- 두 저장소의 project identity, schema version, source reference contract를 맞춰야 한다.
- 통합 contract test와 degraded-mode E2E가 release gate에 추가된다.

## ADR-014 — Polyglot Persistence with PostgreSQL, Neo4j, and Vector Retrieval

### Context

표·거버넌스·운영 트랜잭션, 관계 경로, 문서 유사도 검색은 서로 다른 query 특성을 가진다. 한 저장소로 모든 문제를 해결하거나 동일 데이터를 무분별하게 복제하면 모델과 운영 복잡도가 커진다.

### Decision

- PostgreSQL은 operational source of truth다.
- Neo4j는 relationship, lineage, impact, root-cause path projection이다.
- PostgreSQL `pgvector` schema와 projection target을 local vector infrastructure로 준비한다. 현재 runtime semantic retrieval은 Project 3 RAG typed API를 사용하며, Project 2 local pgvector retrieval은 writer·role/project-filtered search port가 구현되기 전까지 완료 기능으로 간주하지 않는다.
- raw file과 materialized dataset은 filesystem/Parquet에서 시작해 S3-compatible object storage로 확장한다.
- PostgreSQL transaction과 outbox가 Neo4j/vector/object storage projection을 구동한다.
- 모든 projection은 `organization_id`, `project_id`, `dataset_id`, `dataset_version`, `object_id`, `source_sha256`를 공유한다.
- 세 저장소의 결과를 합치는 작업은 Project 2의 typed checkpointed multi-store orchestrator가 담당한다. 현재 직접 구현한 state/checkpoint/trace가 요구사항을 충족하므로 LangGraph 라이브러리는 필수 dependency가 아니다.
- runtime import와 writer/search port가 없는 `langgraph`, `langgraph-checkpoint-postgres`, `pgvector` Python client, `llama-index-vector-stores-postgres`는 설치 extras에 선반영하지 않는다. 실제 소비 vertical과 contract test가 생길 때만 다시 추가한다.

### Consequences

- eventual consistency와 projection status를 UI에 표시해야 한다.
- Dataset Catalog와 Governance Workbench가 store readiness/failure를 노출해야 한다.
- graph/vector query에도 tenant/project/role filtering이 적용돼야 한다.
- health endpoint는 local pgvector infrastructure와 Project 3 semantic retrieval을 별도 capability로 표시해야 한다.
- query run은 사용한 store, source version, elapsed, rows/nodes/chunks, cache, warning을 audit해야 한다.

## ADR-015 — User-Visible Vertical Slice Is the Unit of Progress

### Decision

아키텍처 또는 backend 작업은 실제 route, panel, badge, interaction 중 하나로 끝나야 한다. `Ontology`, `Datasets`, `Governance` Workbench가 완성되기 전에는 새로운 비핵심 역할 보드 확장을 후순위로 둔다.

### Consequences

- architecture-only stage는 한 단계를 넘기지 않는다.
- frontend maturity는 화면별 acceptance와 screenshot baseline을 포함한다.
- feature flag 뒤의 구현은 완료율에 포함하지 않는다.
- 각 Stage는 사용자에게 시연 가능한 URL을 completion report에 포함한다.

## ADR-016 — WorkOrder Is the Canonical Operational Task

### Context

초기 제조 demo는 현장 작업 identity를 `inspection:<event_id>`로 표현했다. 그러나 점검, 정비, 부품 교체, 안전 차단과 후속 조치를 모두 Inspection으로 모델링하면 Ontology Action과 업무 lineage가 특정 workflow 이름에 종속된다.

### Decision

- canonical object identity는 `work_order:<event_id>`다.
- Equipment → WorkOrder, RiskEvent → WorkOrder, WorkOrder → MaintenanceAction link를 사용한다.
- 현장 complete/issue/blocked action은 WorkOrder를 대상으로 실행한다.
- 기존 `inspection` object, links와 actions는 외부 호출과 저장 데이터 호환을 위한 deprecated alias로 유지한다.
- adapter snapshot은 canonical WorkOrder와 legacy Inspection alias를 함께 materialize하되 신규 Dashboard, Analysis, Planner와 field UI는 WorkOrder를 사용한다.

### Consequences

- 기존 API와 E2E는 깨지지 않는다.
- 신규 domain pack은 Inspection이라는 제조 전용 용어 없이 task/work-order interface를 재사용할 수 있다.
- legacy alias 제거는 별도 migration과 소비자 확인 후에만 수행한다.

## ADR-017 — Analysis Runs Are Durable Jobs and Results Become Dataset Versions

### Context

동기 preview 실행과 browser sample만으로는 장시간 Analysis, 취소, 재시도, cache, lineage와 downstream 재사용을 표현할 수 없다. Dashboard가 임시 row를 직접 복사하면 동일 결과를 재현하거나 audit하기 어렵다.

### Decision

- 기존 동기 `/run`은 compatibility preview API로 유지한다.
- production lifecycle은 queued → running → succeeded/failed/cancelled durable run contract를 사용한다.
- run은 node progress, current node, partial result, cancel flag, cache key/hit, rows scanned와 cursor page를 저장한다.
- “Save dataset”은 선택 node 결과를 immutable Dataset Version과 registered materialization artifact로 만든다.
- materialized Dataset만 다른 Analysis의 `dataset:<dataset_id>` input source로 재사용할 수 있다. 임의 filesystem path는 허용하지 않는다.
- Parquet가 기본이며 pyarrow가 없는 개발 환경에서는 동일 checksum/lineage contract의 JSONL artifact로 안전하게 폴백한다.

### Consequences

- Analysis 결과와 Dashboard rendering이 분리된다.
- Dataset Catalog가 schema, profile, file, checksum, materialization, lineage와 projection readiness를 설명할 수 있다.
- 취소된 run도 partial result와 audit metadata를 유지한다.
- 동일 version/config/parameters/limit 조합은 cache hit로 재사용할 수 있다.

## ADR-018 — Canonical Composition Root Precedes Physical Module Relocation

### Decision

- executable ASGI composition root는 `ontology_dashboard.main`이 소유한다.
- `factory_signal_board.main`은 compatibility re-export만 허용하며 router registration이나 exception handler를 소유하지 않는다.
- remaining physical module relocation은 service/repository slice별 compatibility import와 full gate를 유지하며 진행한다.
- 모든 module 이동이 끝난 뒤에만 `ontology_dashboard.__path__` legacy extension을 제거한다.

### Consequences

- deployment entrypoint와 tests는 canonical namespace를 사용한다.
- composition root debt와 physical module debt를 별개로 추적한다.
- 대규모 일괄 이동으로 runtime singleton이나 import identity가 중복되는 위험을 피한다.

### Completion note — 2026-08-03

모든 compatibility slice가 canonical package로 이동했고, architecture/import identity 검증 후 `api/factory_signal_board/`, setuptools legacy package discovery와 `ontology_dashboard.__path__` extension을 제거했다.

## ADR-019 — Project Showcase Fixtures Do Not Expand the Manufacturing Gold Set

### Decision

- `self.fixtures`는 GS-001..GS-008 manufacturing Gold regression만 의미한다.
- Azure와 MetroPT showcase fixture는 project-scoped fixture collection과 API를 통해 제공한다.
- manufacturing Ontology projection, FDE diagnostics와 ML Gold regression은 Gold 8건을 유지한다.
- showcase Evidence는 `project_id`와 `dataset_version` lineage를 포함한다.
- complete public dataset 통계가 없는 showcase fixture를 full-dataset metric으로 표현하지 않는다.

### Consequences

- Project selector와 Dashboard abstraction은 실제 데이터로 시연 가능하다.
- Gold regression 수치와 제조 workflow는 변하지 않는다.
- 전체 Azure/MetroPT ingestion은 provenance와 source approval이 있는 별도 단계로 남는다.

## ADR-020 — Project-Specific Actions Default to Read-Only

### Decision

Project-scoped Event와 Evidence가 존재하더라도 해당 Project의 Action mapping, permission policy와 audit contract가 게시되기 전까지 Decision/Note/WorkOrder mutation은 비활성화한다.

### Consequences

- Azure와 MetroPT showcase는 조회·분석·Dashboard에 사용할 수 있다.
- Manufacturing Action handler를 다른 Project에 암묵적으로 재사용하지 않는다.
- UI는 조회 전용 상태를 명시하고 backend도 `project_action_not_configured`로 방어한다.

## ADR-021 — Dashboard Draft Recovery Is Local, Scoped, and Revision-Bound

### Decision

- unsaved Dashboard draft는 user/workspace/role key로 local storage에 autosave한다.
- recovery payload는 dashboard ID, template version과 base preference revision이 일치할 때만 제안한다.
- undo/redo history는 browser session memory에 제한하고 최대 50개 snapshot을 유지한다.
- persisted save, default restore 또는 incompatible template change는 recovery를 제거한다.

### Consequences

- accidental refresh와 navigation에서 개인 편집을 복구할 수 있다.
- stale draft가 새 template revision을 덮어쓰지 않는다.
- 서버의 optimistic preference revision contract는 그대로 authoritative하다.

## ADR-022 — Environment-Dependent Completion Must Be Machine-Verifiable

### Decision

Docker, managed stores, IdP, production connector, object storage와 observability 항목은 `scripts/verify_production_environment.py`의 capability state와 실행 evidence가 있어야 완료로 표시한다.

### Consequences

- configuration이나 compose 파일 존재만으로 production 완료를 주장하지 않는다.
- current host의 missing Docker/credentials는 `blocked`로 보고한다.
- staging CI는 strict mode와 `docs/production-environment-completion-runbook.md`를 사용한다.

## ADR-023 — Foundry-Inspired UI Is a Shared Primitive Layer, Not a Product Clone

### Decision

- Palantir Foundry/Contour/Object Explorer는 information density, pane hierarchy, resource chrome과 interaction pattern의 reference로 사용한다.
- proprietary HTML, CSS, asset, font 또는 trademark를 복사하지 않고 Apache-2.0/MIT reference의 공개 pattern을 Ontology Dashboard 타입과 API에 맞춰 재작성한다.
- `web/src/ui/foundry/`가 token, shell, header/toolbar, board frame, metric, table, chart와 state primitive를 소유한다.
- 기존 `--od-*` 변수는 단계적 migration 동안 `--fd-*` token으로 compatibility mapping하되 새 UI의 source of truth는 `--fd-*`다.
- 모든 primary Workbench는 48px collapsed rail, 40px global topbar, border-led pane hierarchy와 compact control density를 공유한다.
- visual baseline은 starting SHA의 before evidence와 current after evidence를 분리하며, before refresh는 명시적 opt-in으로만 허용한다.

### Consequences

- Dashboard 외 Project Home, Agent, Ontology, Dataset과 Governance 화면도 동일 제품으로 인식된다.
- UI 변경은 backend contract, Project scope, permission과 audit vertical을 재구현하지 않고 composition layer에서 진행된다.
- 공통 primitive 변경은 live DOM geometry, interaction E2E, accessibility/overflow와 screenshot evidence로 검증된다.
- reference license와 adaptation 범위는 `THIRD_PARTY_NOTICES.md`에 추적된다.

## ADR-024 — Visual Regression Separates Approved Artifacts, Candidates, and Platform Profiles

### Decision

- `docs/ui/palantir-overhaul/baseline/`은 작업 시작 SHA의 historical evidence이고, `final/`은 명시적으로 승인된 현재 화면이다.
- `visual-manifest.json`은 baseline/final 48장의 dimensions, bytes, SHA-256와 24개 pair delta를 소유한다.
- 일반 Playwright 실행은 승인 파일을 수정하지 않고 `web/test-results/palantir-overhaul-candidate/`에 candidate 24장을 생성한다.
- 승인 갱신은 `CAPTURE_PALANTIR_FINAL=1`을 명시한 실행에서만 허용하고 historical baseline은 별도 clean worktree에서만 재생성한다.
- 승인 이미지와 동일 플랫폼에서는 raw mean pixel delta 0.15%, changed pixel ratio 0.75%, blurred structural delta 0.10%를 모두 적용한다.
- 다른 운영체제에서는 시스템 font rasterization 차이로 raw pixel gate를 적용하지 않고, grayscale downsample과 Gaussian blur를 거친 structural delta 2.4%를 적용한다.
- GitHub Actions의 `release_gate.py --with-e2e`는 candidate capture가 끝난 뒤 48-image checker를 실행한다.
- CI는 candidate 24장, runner/browser/font metadata와 per-image visual report를 artifact로 보존한다.

### Consequences

- 승인 이미지가 일반 test run에 의해 조용히 덮어써지지 않는다.
- 같은 플랫폼의 작은 spacing, color, text 또는 layout 회귀를 엄격하게 감지한다.
- Ubuntu CI에서는 macOS font anti-aliasing 차이를 허용하면서 pane, hierarchy, density와 주요 구조 변화는 structural diff로 감지한다.
- Ubuntu 24.04의 실제 최대값 1.5436%에 1.5배 margin을 적용한 2.4% ceiling은 font fallback 줄바꿈을 허용하면서 더 큰 pane/hierarchy 회귀를 차단한다.
