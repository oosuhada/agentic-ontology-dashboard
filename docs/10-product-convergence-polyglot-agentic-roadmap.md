# Ontology Dashboard Product Convergence, Polyglot Data, and Agentic Delivery Plan

- 작성일: 2026-08-02
- 상태: 실행 기준 문서
- 제품명: Ontology Dashboard
- Canonical Python namespace: `ontology_dashboard`
- 대상 저장소: `mvp-프로젝트2`
- 연계 저장소: `mvp-프로젝트3`
- 목적: 현재 누적된 기능·아키텍처·화면 간 불균형을 바로잡고, Project 2와 Project 3을 하나의 실제 업무 제품으로 수렴시키기 위한 상세 실행 계획

---

## 1. 이 문서가 해결하려는 문제

현재 프로젝트에는 실제 구현 진전이 있다. React Grid Layout, ECharts, TanStack Table, React Flow, Analysis API, Dashboard query API, Ontology object/link API, RBAC, audit, approval, adapter, PostgreSQL migration 등은 단순 문서가 아니라 코드로 존재한다.

그러나 사용자가 체감하는 제품 완성도는 그보다 낮다.

핵심 이유는 다음과 같다.

1. 아키텍처 기반 작업과 실제 사용 화면 작업의 완료 기준이 분리돼 있었다.
2. `Frontend 89%` 같은 수치는 파일·구조·흐름 기반의 성숙도를 나타냈을 뿐, Palantir 수준의 시각 밀도·작업 흐름·완결된 메뉴를 뜻하지 않았다.
3. `Ontology`, `Datasets`, `Governance`가 실제 메뉴에 노출되지만 `enabled: false`와 `SOON` 상태다.
4. `palantir-contour-ui-reference.md`와 4개 분석 문서는 주로 컴포넌트·상태·데이터 흐름을 다뤘고, 디자인 토큰·타이포그래피·밀도·패널 규격·시각 회귀 기준은 정의하지 않았다.
5. Project 3을 단순 선택적 Context Provider로만 보는 초기 가정이 실제 업무 관계를 충분히 반영하지 못했다.
6. Project 3에는 이미 Neo4j, 검증된 Text-to-Cypher, LangGraph, LlamaIndex RAG가 존재하지만 Project 2에서는 이를 평탄화된 `source_refs`와 checklist 수준으로만 소비하고 있다.
7. canonical namespace는 `ontology_dashboard`로 선언됐지만 다수 핵심 서비스가 여전히 `api/factory_signal_board`에 물리적으로 남아 있고, `ontology_dashboard.__init__`이 legacy 디렉터리를 `__path__`에 추가해 import를 우회하고 있다.
8. 기능이 늘면서 코드 복잡도는 높아졌지만, 각 단계가 반드시 사용자에게 보이는 route와 화면으로 끝나도록 하는 실행 규칙이 없었다.

이 문서는 위 문제를 하나의 수정 로드맵으로 통합한다.

---

## 2. 최종 결론

### 2.1 Project 2와 Project 3의 관계를 다시 정의한다

Project 2와 Project 3은 서로 무관한 별도 제품이 아니다. 회사의 하나의 실제 업무 흐름을 구현 과제상 두 부분으로 나눈 것이다.

- Project 3: 데이터 적재, 지식그래프 구성, 문서 검색, 관계 추론, Text-to-Cypher 안전 실행에 초점
- Project 2: 여러 데이터 소스와 분석 결과를 역할별 Dashboard, Analysis, Ontology, Dataset, Governance, Action으로 전달하는 운영 제품에 초점

따라서 Project 2는 Neo4j와 Vector Store를 몰라도 되는 단순 소비자가 아니라, 다음을 수행하는 **governed delivery and orchestration layer**가 되어야 한다.

```text
Project 3
- Neo4j graph ingestion
- graph schema and project readiness
- validated read-only Text-to-Cypher
- LangGraph correction/validation loop
- LlamaIndex document RAG

Project 2
- Project/Workspace/RBAC/Governance
- relational operational data
- graph and vector query orchestration
- Analysis and Dashboard generation
- Ontology/Dataset/Governance Workbench
- Evidence, Action, Approval, Audit, Export
```

### 2.2 Project 2도 Neo4j를 사용한다

Project 2는 다음 두 방식으로 Neo4j를 정식 사용한다.

1. **결정적 graph query**: Ontology Workbench, object relationship board, lineage, root-cause path, connected object count처럼 query spec이 고정된 기능은 Project 2 backend가 parameterized read query로 실행한다.
2. **자연어 graph query**: LLM이 Cypher를 생성해야 하는 요청은 Project 3의 기존 LangGraph Text-to-Cypher workflow를 typed service contract로 호출한다.

Project 3의 agent 코드를 Project 2에 복사하지 않는다. 검증된 기능을 API 또는 공유 패키지 계약으로 재사용한다.

### 2.3 RDB, Neo4j, Vector Store를 함께 사용한다

같은 업무 데이터는 세 저장소에 무작정 동일한 byte 형태로 복제하지 않는다. 동일한 `organization_id`, `project_id`, `dataset_id`, `dataset_version`, `object_id`, `source_sha256`를 공유하면서 저장소 목적에 맞는 projection을 가진다.

- PostgreSQL: 정규화된 운영 레코드, 권한, 버전, audit, action, analysis metadata, tabular aggregate
- Neo4j: object relationships, lineage, impact path, root-cause path, cross-domain traversal
- Vector Store: manual, SOP, report, note, incident narrative, similar case, semantic retrieval
- Object Storage/Parquet: 원본 파일과 materialized dataset payload

초기 Vector Store 구현은 현재 PostgreSQL 전략과 운영 복잡도를 고려해 `pgvector`를 권장한다. LlamaIndex는 `PGVectorStore` 계열 adapter를 사용하고, 추후 Qdrant 등으로 교체할 수 있도록 port를 둔다.

### 2.4 LangGraph를 Project 2에도 도입한다

Project 2의 현재 planner는 단일 모듈에서 deterministic keyword mapping과 optional JSON generation을 수행한다. 이는 간단한 object query와 board recommendation에는 적합하지만, 여러 저장소를 선택하고 결과를 검증·병합해 Dashboard를 만드는 작업에는 부족하다.

Project 2에는 다음 목적의 LangGraph workflow를 추가한다.

```text
request guard
→ project/workspace scope resolution
→ intent classification
→ multi-store query planning
→ relational / graph / vector execution
→ evidence merge
→ claim validation
→ typed answer or DashboardSpec compilation
→ approval/publish boundary
```

Project 3의 Text-to-Cypher LangGraph는 graph tool 내부 workflow로 유지하고, Project 2의 LangGraph는 상위 orchestration workflow가 된다.

### 2.5 UI 완성도를 별도 deliverable로 관리한다

앞으로 UI는 backend 연결이 끝났다는 이유만으로 완료 처리하지 않는다. route, empty/loading/error state, interaction, visual density, screenshot baseline, accessibility, responsive state까지 완료 기준에 포함한다.

---

## 3. 현재 코드에서 확인된 사실

### 3.1 실제 구현된 기반

- React 19 + Vite 8 frontend
- FastAPI application factory와 feature routers
- Organization → Project → Workspace 기반
- Authentication, session, CSRF, RBAC
- Project membership foundation
- Dashboard template, preference, saved view, share
- react-grid-layout 기반 x/y/w/h grid
- ECharts, TanStack Table, React Flow
- Analysis create/update/publish/run/node result API
- Filter, Group, Aggregate, Join, Chart, Verify Table path
- Dashboard server board query와 server selection filter
- Ontology object/list/detail/link/traverse/aggregate API
- role-specific workspaces
- audit, approval, export
- adapter, dataset manifest, prediction result foundation
- SQLite migrations and PostgreSQL migrations/RLS foundation

### 3.2 실제 미구현 제품 화면

현재 `web/src/features/dashboard/DashboardShell.tsx`의 메뉴 상태는 다음과 같다.

```text
Dashboards  enabled
Analysis    enabled
Ontology    disabled / SOON
Datasets    disabled / SOON
Governance  disabled / SOON
```

전용 route도 없다.

- `/app/ontology` 없음
- `/app/datasets` 없음
- `/app/governance` 없음

### 3.3 실제 architecture debt

`api/ontology_dashboard/__init__.py`는 다음 방식으로 legacy package를 canonical namespace 아래에 노출한다.

```python
_LEGACY_MODULE_PATH = Path(__file__).resolve().parent.parent / "factory_signal_board"
__path__.append(str(_LEGACY_MODULE_PATH))
```

따라서 `from .ontology_planner_service import OntologyDashboardPlannerService`가 canonical import처럼 보여도 실제 파일은 다음에 있다.

```text
api/factory_signal_board/ontology_planner_service.py
```

현재 legacy physical directory에는 analysis, dashboard, ontology, planner, identity, workflow, export, security, service 등 핵심 모듈 대부분이 남아 있다.

### 3.4 Project 3에서 이미 존재하는 기능

Project 3 실제 저장소에는 다음이 구현돼 있다.

- `backend/app/agent/workflow.py`
  - LangGraph `generate_cypher → validate_cypher → correct_cypher → execute_cypher`
  - read-only validation
  - project scope validation
  - timeout
  - statement hash
  - checkpoints and resume
- `backend/app/agent/graph.py`
  - Neo4j read graph
- `backend/app/security/read_only.py`
  - write clause와 multiple statement 차단
- `backend/app/rag/service.py`
  - LlamaIndex document ingestion, persistence, retrieval
- `backend/app/projects/connectors.py`
  - Neo4j connection validation and schema introspection
- Project 3 API
  - `/api/v1/query`
  - `/api/v1/rag/search`
  - `/api/v1/rag/query`
  - `/api/v1/agent/runs/{run_id}`
  - `/api/v1/agent/runs/{run_id}/resume`
  - `/api/v1/graph/schema`
  - `/api/v1/graph/search`
  - `/api/v1/graph/subgraph`
  - project upload, mapping, graph load, connector validation, readiness API

이 기능을 Project 2에서 다시 작성하면 리소스 낭비다. Project 2는 typed client와 orchestration, governance, delivery UI를 구현해야 한다.

---

## 4. 기존 판단 중 유지할 것과 수정할 것

### 4.1 유지할 판단

다음 원칙은 유지한다.

- LLM이 arbitrary React 코드를 생성·실행하지 않는다.
- LLM이 검증 없이 arbitrary SQL/Cypher를 직접 실행하지 않는다.
- Dashboard는 catalog 기반 typed `BoardDefinition`과 `RenderSpec`으로 생성한다.
- 권한과 project scope를 모든 query에서 재검증한다.
- graph query 결과와 RAG 결과는 Evidence로 남긴다.
- Project 3 장애가 전체 운영 Dashboard를 중단시키지 않도록 degraded mode를 둔다.

### 4.2 수정할 판단

기존 ADR-010의 “arbitrary SQL/Cypher 실행 금지”를 다음처럼 정확하게 해석한다.

```text
금지:
- 모델 출력 문자열을 검증 없이 DB에 실행
- write Cypher/SQL
- multi statement
- project scope 없는 query
- schema에 없는 label/property/table/column
- timeout/row limit 없는 query

허용:
- typed query compiler가 생성한 parameterized SQL
- catalog template 기반 parameterized Cypher
- Project 3 LangGraph가 read-only, schema, project scope, semantic validation을 통과시킨 Cypher
- 실행 statement hash, run ID, source version, row count, elapsed time이 audit에 남는 query
```

즉, **생성형 query 자체가 금지되는 것이 아니라 검증되지 않은 query 실행이 금지된다.**

### 4.3 Project 3 optionality 재정의

기존 `project3-adapter-contract.md`의 “Project 2는 Project 3 없이 완전히 실행” 원칙은 다음처럼 바꾼다.

- Local demo와 degraded operations는 Project 3 없이 실행 가능
- Integrated production mode에서는 Project 3 graph/RAG capability가 정식 dependency
- dependency 장애 시 relational Dashboard와 이미 materialized된 결과는 유지
- graph path, semantic retrieval, natural-language graph query는 unavailable badge와 fallback을 표시

---

## 5. 목표 제품 흐름

```text
Source Files / API / Events / Documents
                │
                ▼
Dataset Intake and Versioning
- validation
- schema mapping
- checksum
- quarantine
                │
                ▼
Canonical Data Product
- project_id
- dataset_id/version
- object identity
- source lineage
                │
       ┌────────┼──────────┬──────────────┐
       ▼        ▼          ▼              ▼
 PostgreSQL   Neo4j     Vector Store   Object Storage
 operational graph     semantic       raw/parquet
 records     projection projection    materialization
       └────────┼──────────┴──────────────┘
                ▼
Multi-Store Query Orchestrator — LangGraph
- choose tools
- execute safely
- merge evidence
- validate claims
- compile typed result
                │
       ┌────────┼──────────────┬──────────────┐
       ▼        ▼              ▼              ▼
 Analysis   Dashboard      Ontology       Dataset/Governance
 Workbench  Delivery       Workbench      Workbenches
                │
                ▼
Evidence → Action → Approval → Audit → Export
```

---

## 6. 저장소별 책임

### 6.1 PostgreSQL

PostgreSQL을 operational source of truth로 사용한다.

주요 데이터:

- organization, project, workspace
- user, membership, role, policy
- dataset catalog metadata와 dataset versions
- ontology schema versions
- object canonical identifiers와 주요 properties
- risk events, predictions, inspections, work orders, actions
- analysis definitions, analysis runs, dashboard definitions
- approval, audit, export, agent run metadata
- projection status and outbox
- vector metadata와 pgvector embedding

주요 query:

- filter, sort, pagination
- group by, aggregate
- time window
- KPI
- tabular joins with approved relationships
- governance and audit

### 6.2 Neo4j

Neo4j는 relationship and path source로 사용한다.

주요 projection:

- Equipment
- Component/Part
- Sensor
- RiskEvent
- FailureMode
- Inspection
- WorkOrder
- MaintenanceAction
- Evidence
- Document
- DatasetVersion
- AnalysisRun
- Dashboard

대표 관계:

```text
Equipment-[:HAS_COMPONENT]->Component
Equipment-[:HAS_SENSOR]->Sensor
RiskEvent-[:AFFECTS]->Equipment
RiskEvent-[:SUPPORTED_BY]->Evidence
RiskEvent-[:SIMILAR_TO]->RiskEvent
Inspection-[:INSPECTS]->Equipment
WorkOrder-[:CREATED_FOR]->Equipment
MaintenanceAction-[:FULFILLS]->WorkOrder
Document-[:DESCRIBES]->FailureMode
DatasetVersion-[:PRODUCED]->RiskEvent
AnalysisRun-[:READ_FROM]->DatasetVersion
Dashboard-[:REFERENCES]->AnalysisRun
```

주요 query:

- N-hop traverse
- shortest/weighted path
- root-cause candidate path
- downstream impact
- lineage
- connected object discovery
- relationship distribution

### 6.3 Vector Store

초기 target은 PostgreSQL `pgvector`다.

주요 문서:

- SOP
- maintenance manuals
- inspection notes
- work-order notes
- incident reports
- evidence narratives
- model cards
- dataset descriptions
- dashboard annotations

각 chunk metadata:

```text
organization_id
project_id
workspace_id
dataset_id
dataset_version
document_id
document_version
object_ids
security_classification
allowed_roles
source_sha256
chunk_index
embedding_model
created_at
```

주요 query:

- similar incident
- relevant manual section
- semantic document search
- recommendation evidence retrieval
- natural-language project search

### 6.4 Object Storage / Parquet

현재 Save Dataset snapshot을 실제 materialization으로 확장한다.

저장 대상:

- uploaded raw files
- normalized parquet
- analysis result parquet
- report snapshot artifacts
- export files

초기 local/demo에서는 filesystem + Parquet, production에서는 S3-compatible object storage를 사용한다.

---

## 7. 데이터 동기화와 일관성

### 7.1 canonical identity

모든 store가 다음 key를 공유한다.

```text
organization_id
project_id
workspace_id
dataset_id
dataset_version
object_id
object_type
source_record_id
source_sha256
schema_version
```

### 7.2 write flow

모든 업무 write는 PostgreSQL transaction에서 시작한다.

```text
PostgreSQL transaction
→ canonical row write
→ outbox event write
→ commit
→ projection worker
   ├─ Neo4j projection
   ├─ vector indexing
   └─ object storage materialization
→ projection status update
```

Neo4j와 Vector Store에 직접 먼저 쓰지 않는다.

### 7.3 projection status

새 테이블을 둔다.

```text
store_projections
- projection_id
- organization_id
- project_id
- dataset_id
- dataset_version
- target_store: neo4j | vector | object_storage
- status: pending | running | ready | failed | stale
- source_sha256
- target_version
- record_count
- error_code
- started_at
- completed_at
```

Dataset UI와 Governance UI가 이 상태를 표시한다.

### 7.4 consistency model

- PostgreSQL: strong consistency
- Neo4j/vector: asynchronous projection, eventual consistency
- 화면은 `fresh`, `stale`, `indexing`, `failed` badge를 표시
- Dashboard run은 사용한 projection version을 저장
- stale graph/vector 결과를 최신 relational 결과처럼 표현하지 않는다

---

## 8. Multi-Store Query Orchestrator

### 8.1 query intent

```text
relational
- 표, 필터, 집계, KPI, 기간별 추이

graph
- 관계, 경로, 영향, 연결, 원인 후보, lineage

vector
- 유사 사례, 문서, SOP, 설명 검색

hybrid
- 관계 경로 + 관련 문서
- 위험 이벤트 집계 + 유사 사례
- 설비 상세 + work order + manual section
```

### 8.2 LangGraph state

```python
class QueryOrchestrationState(TypedDict, total=False):
    request_id: str
    organization_id: str
    project_id: str
    workspace_id: str
    user_id: str
    roles: list[str]
    question: str
    requested_output: str
    intent: str
    query_plan: dict
    relational_result: dict
    graph_result: dict
    vector_result: dict
    evidence: list[dict]
    warnings: list[str]
    validation: dict
    dashboard_spec: dict | None
    status: str
    trace: list[dict]
```

### 8.3 nodes

1. `guard_request`
   - write request 차단
   - prompt injection 검토
   - maximum request size
2. `resolve_scope`
   - organization/project/workspace/role 재검증
3. `classify_intent`
   - relational, graph, vector, hybrid
4. `plan_queries`
   - typed tool plan 생성
   - raw query string이 아니라 registered tool과 parameters 생성
5. `execute_relational`
   - query compiler 또는 approved repository method
6. `execute_graph`
   - deterministic graph template 또는 Project 3 query API
7. `execute_vector`
   - project/role filtered vector retrieval
8. `merge_evidence`
   - source identity, version, score, path 병합
9. `validate_claims`
   - answer claim이 evidence에 존재하는지 검증
10. `compile_output`
   - AnswerContract 또는 DashboardSpec 생성
11. `approval_boundary`
   - publish/action 요청은 자동 확정하지 않음
12. `finalize_run`
   - run metadata, usage, latency, cache, warnings 저장

### 8.4 tool ports

```python
class RelationalQueryPort(Protocol):
    def execute(self, plan: RelationalQueryPlan, scope: Scope) -> TabularResult: ...

class GraphQueryPort(Protocol):
    def execute_template(self, plan: GraphTemplatePlan, scope: Scope) -> GraphResult: ...
    def execute_natural_language(self, request: GraphAgentRequest, scope: Scope) -> GraphAgentResult: ...

class VectorRetrievalPort(Protocol):
    def search(self, request: VectorSearchRequest, scope: Scope) -> RetrievalResult: ...

class MaterializationPort(Protocol):
    def materialize(self, request: DatasetMaterializationRequest, scope: Scope) -> MaterializationResult: ...
```

### 8.5 Project 3 client

Project 2에 다음 canonical client를 추가한다.

```text
api/ontology_dashboard/integrations/project3/client.py
api/ontology_dashboard/integrations/project3/models.py
api/ontology_dashboard/integrations/project3/health.py
api/ontology_dashboard/integrations/project3/adapters.py
```

초기 연계 대상:

- query: `/api/v1/query`
- RAG: `/api/v1/rag/search`
- run inspect/resume
- graph schema/search/subgraph
- project readiness

기존 `/api/maintenance-context` 평탄 계약은 compatibility endpoint로 남기되 새 구현의 중심으로 사용하지 않는다.

---

## 9. Dashboard 생성 계약

LLM 또는 LangGraph는 React나 ECharts option 전체를 임의로 생성하지 않는다.

출력은 typed `DashboardSpec`이다.

```json
{
  "title": "설비 위험과 정비 근거",
  "project_id": "manufacturing-demo-project",
  "workspace_id": "manufacturing-demo",
  "tabs": [
    {
      "id": "risk-overview",
      "title": "Risk Overview",
      "boards": [
        {
          "board_type": "metric",
          "data_source": {
            "kind": "relational",
            "query_id": "risk-event-count",
            "parameters": {"status": "critical"}
          },
          "render_spec": {"value_field": "count"}
        },
        {
          "board_type": "relationship_graph",
          "data_source": {
            "kind": "graph",
            "query_id": "equipment-risk-subgraph",
            "parameters": {"depth": 2}
          }
        },
        {
          "board_type": "evidence_list",
          "data_source": {
            "kind": "vector",
            "query_id": "related-maintenance-documents",
            "parameters": {"top_k": 5}
          }
        }
      ]
    }
  ]
}
```

서버는 다음을 검증한다.

- board catalog 등록 여부
- role permission
- data source kind 허용 여부
- query ID whitelist
- field/property 존재 여부
- graph depth와 row limit
- vector role filter
- parameter type
- project/workspace scope

---

## 10. 전용 Workbench 계획

## 10.1 Ontology Workbench

### Route

```text
/app/projects/:projectId/workspaces/:workspaceId/ontology
```

### 화면 구조

```text
Global header
├─ Project / Workspace
├─ Ontology version
├─ Search
└─ View switch: Explorer | Schema | Mapping | Lineage

Left rail
├─ Object Types
├─ Link Types
├─ Action Types
└─ Saved graph views

Center
├─ graph explorer
├─ object table
└─ schema canvas

Right inspector
├─ object/link properties
├─ source dataset/version
├─ linked records
├─ evidence
├─ available actions
└─ query/runtime metadata
```

### 기능

- Object Type catalog
- Link Type catalog
- Action Type catalog
- object list/search/server pagination
- object detail
- real Neo4j subgraph depth 1~3
- linked PostgreSQL operational record detail
- relationship path explanation
- schema version comparison
- dataset-to-ontology mapping
- lineage from DatasetVersion to AnalysisRun/Dashboard
- natural-language graph query panel
- validated Cypher display for FDE/Data Scientist only
- graph result “Add as Board”

### 완료 기준

- `SOON` 제거
- route deep link 가능
- Neo4j unavailable 시 relational object view는 동작하고 graph section은 degraded 표시
- graph node 선택이 inspector와 Evidence에 연결
- project isolation negative E2E 통과

## 10.2 Dataset Catalog

### Route

```text
/app/projects/:projectId/workspaces/:workspaceId/datasets
```

### 화면

- Dataset list
- Dataset detail
- Versions
- Schema
- Data profile
- Lineage
- Materializations
- Projection health
- Access policy

### 기능

- dataset registration
- upload/ingestion status
- checksum and source provenance
- version comparison
- row/column/null/duplicate profile
- quarantine records
- PostgreSQL/Neo4j/vector/object storage projection status
- source documents and vector index readiness
- Analysis result “Save as Dataset” materialization
- Parquet download/export policy
- downstream Analysis/Dashboard references

### 완료 기준

- `SOON` 제거
- 실제 dataset version이 목록과 상세에 표시
- Analysis result가 Parquet materialization과 catalog version으로 생성
- store별 freshness와 record count가 보임
- projection failure retry가 governance permission으로 가능

## 10.3 Governance Workbench

### Route

```text
/app/projects/:projectId/workspaces/:workspaceId/governance
```

### 화면

- Overview
- Access and Roles
- Approvals
- Audit
- Agent Runs
- Data Lineage
- Projection Health
- Export Policy

### 기능

- role/project membership
- dashboard publish approvals
- model release approvals
- action approvals
- agent run trace
- generated/validated Cypher hash와 execution metadata
- RAG source documents
- evidence claim validation
- dataset lineage
- store projection health
- policy violations
- export checkpoints

### 완료 기준

- `SOON` 제거
- 기존 Admin UI와 중복되는 계정 관리와 project governance를 명확히 분리
- quality auditor가 query/run/evidence를 재구성 가능
- FDE가 projection과 schema 상태를 보되 tenant admin 권한을 갖지 않음

---

## 11. Palantir형 화면이 지금까지 어려웠던 이유와 수정 방식

### 11.1 reference repository는 완성 제품 template이 아니다

현재 clone된 repository들은 각각 일부 문제만 해결한다.

- `openfoundry-emulator`: Contour 구조와 widget registry
- `mini_foundry_public`: Dashboard canvas, data binding, ontology graph
- `palantir-blueprint`: component system
- `contour-translation`: structured render spec
- `palantir-demo`, `Gods_Eye`: 시각 아이디어

이들을 clone했다고 현재 도메인 모델, RBAC, API, Analysis state에 자동 결합되는 것은 아니다.

### 11.2 visual specification이 없었다

앞으로 `docs/palantir-contour-ui-reference.md`를 기능 명세로만 사용하지 않고 별도 visual acceptance를 추가한다.

추가할 문서:

```text
docs/ui/visual-language.md
docs/ui/workbench-layout-spec.md
docs/ui/component-density-spec.md
docs/ui/reference-screen-index.md
```

정의할 항목:

- type scale
- spacing scale
- panel widths
- header heights
- table row density
- card border/shadow
- neutral and semantic colors
- selected/hover/focus state
- graph node/edge style
- chart typography and grid
- empty/loading/error state
- dark/light theme

### 11.3 benchmark-first 구현 방식

각 화면 구현 전에 다음을 만든다.

1. reference screenshot index
2. 현재 화면 screenshot
3. target wireframe
4. component mapping
5. Playwright screenshot baseline
6. 완료 후 diff review

참조 파일:

```text
../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/openfoundry-emulator/apps/app-console/src/pages/Contour.tsx
../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/frontend/components/dashboards/DashboardCanvas.tsx
../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/mini_foundry_public/frontend/components/ontology/OntologyGraph.tsx
../레퍼런스-프로젝트2/P5-팔란티어-Foundry-UI/openfoundry-emulator/apps/app-console/src/components/DataTable.tsx
```

코드 복사는 라이선스 확인 후 최소화하고, interaction과 information architecture를 우선 참고한다.

---

## 12. canonical namespace 기술부채 청산

### 12.1 목표 구조

```text
api/ontology_dashboard/
├─ analysis/
│  ├─ models.py
│  ├─ repository.py
│  ├─ service.py
│  └─ executor.py
├─ dashboards/
├─ ontology/
├─ datasets/
├─ governance/
├─ planner/
├─ agent/
├─ integrations/project3/
├─ identity/
├─ workflows/
├─ exports/
├─ manufacturing/
├─ routers/
├─ projects/
└─ infrastructure/
```

### 12.2 이동 순서

1. planner models/service를 canonical package로 이동
2. analysis models/repository/service 이동
3. dashboard catalog/models/repository/service 이동
4. ontology registry/models/repository/service 이동
5. role workflow/export/identity 이동
6. manufacturing compatibility service 이동 및 rename
7. tests와 routers import 갱신
8. legacy package에는 temporary re-export shim만 유지
9. import violation check 추가
10. `ontology_dashboard.__init__`의 `__path__.append` 제거
11. `factory_signal_board` package 제거
12. setuptools package 목록에서 제거

### 12.3 즉시 해결해야 하는 planner debt

현재 단일 `ontology_planner_service.py`를 다음처럼 분리한다.

```text
ontology_dashboard/planner/
├─ models.py
├─ deterministic.py
├─ validators.py
├─ board_recommender.py
├─ narrative.py
├─ service.py
└─ ports.py
```

LangGraph orchestration은 별도 위치에 둔다.

```text
ontology_dashboard/agent/
├─ state.py
├─ workflow.py
├─ tools.py
├─ checkpoints.py
├─ policies.py
└─ audit.py
```

planner가 모든 역할을 수행하지 않게 한다.

### 12.4 완료 기준

```bash
rg "factory_signal_board" api tests scripts
```

결과는 migration compatibility test 외 0건이어야 한다.

자동 검사:

- canonical import check
- no path extension check
- no router importing legacy service check
- package build/install check

---

## 13. 현재 현실적 제한사항과 보완 작업 매핑

| 현재 제한 | 보완 작업 | 완료 기준 |
|---|---|---|
| Ontology aggregate가 application layer 계산 | PostgreSQL query compiler와 native GROUP BY | aggregate query가 DB 실행계획과 rows scanned를 반환 |
| Analysis source 최대 5,000 rows | cursor pagination, projection, async materialization | preview와 full run 분리, full run은 worker 실행 |
| Dashboard filter/chart 최대 5,000 scan | server query plan과 pushdown | client 전체 스캔 제거 |
| Analysis Run 동기 실행 | job table + worker + status polling/SSE | queued/running/succeeded/failed/cancelled |
| Save Dataset이 JSON snapshot | Parquet/object storage materialization + DatasetVersion | catalog에서 재사용 가능 |
| WorkOrder Object Type 없음 | canonical WorkOrder type/link/action 추가 | Equipment↔WorkOrder가 실제 object/link로 조회 |
| PostgreSQL live integration 미검증 | Docker Compose/Testcontainers integration gate | migration, RLS, repositories, concurrency PASS |
| bundle 약 1.35MB | route lazy loading, ECharts/React Flow split | initial route chunk budget 충족 |
| resize pointer E2E 제외 | stable helper 또는 browser matrix | 실제 drag/resize gesture 최소 Chromium PASS |
| Ontology SOON | Ontology Workbench | 실제 route와 graph explorer |
| Datasets SOON | Dataset Catalog | version/profile/materialization UI |
| Governance SOON | Governance Workbench | policy/audit/agent/projection UI |
| Project 3 flat context adapter | typed Project 3 graph/RAG client | query/RAG/subgraph/run contract 사용 |
| Neo4j가 Project 2 architecture에 없음 | GraphQueryPort + Neo4j projection | dashboard/ontology graph가 real Neo4j 사용 |
| VectorDB 없음 | pgvector + LlamaIndex adapter | project-scoped semantic retrieval |
| LangGraph 없음 | MultiStoreQueryOrchestrator | hybrid request trace와 checkpoint |
| legacy package path hack | physical relocation | `factory_signal_board` 제거 |

---

## 14. 세부 실행 단계

## Stage 44 — Rebaseline and Decision Freeze

### 목적

문서와 실제 코드의 차이를 정리하고 잘못된 우선순위를 중단한다.

### 작업

- 본 문서를 공식 roadmap override로 등록
- ADR 추가
  - Polyglot persistence
  - Project 2/3 integrated boundary
  - validated generated query execution
  - UI visual acceptance
- 기존 maturity percentage 재계산
- `SOON` 메뉴를 명시적 feature flag로 전환
- current architecture debt inventory test 추가

### 결과물

- updated `03-project-roadmap.md`
- updated `07-implementation-status.md`
- updated `09-architecture-decisions.md`
- updated `project3-adapter-contract.md`
- updated `next-session-master-prompt.md`

### 완료 기준

- 다음 세션이 old Project Layer 순서를 자동으로 따르지 않음
- Project 2의 Neo4j/Vector/LangGraph target이 공식 문서에 존재

## Stage 45 — Planner Canonical Migration + Project 3 Typed Client

### 목적

가장 큰 architecture debt와 Project 3 integration entrypoint를 동시에 해결한다.

### backend

- planner physical relocation
- `Project3Client`
- health/readiness models
- query/RAG/subgraph client methods
- timeout/retry/circuit breaker
- project mapping configuration
- contract tests against recorded responses

### frontend visible slice

- Ontology menu 활성화 전 preview route 추가
- Project 3 status badge
- graph schema summary
- subgraph preview

### 완료 기준

- planner router가 legacy path를 사용하지 않음
- Project 3 실제 API 또는 fixture contract로 schema/subgraph 표시
- 장애 시 degraded state 표시

## Stage 46 — PostgreSQL + pgvector + Neo4j Local Infrastructure

### 목적

세 저장소를 동일 local stack으로 재현한다.

### infra

- Docker Compose profiles
  - postgres + pgvector
  - neo4j
  - optional redis
- health checks
- environment variables
- secrets-safe configuration
- migration bootstrap
- local seed

### dependencies

- `neo4j` Python driver
- `pgvector`
- LlamaIndex vector store adapter
- LangGraph and checkpoint backend

### tests

- store health
- PostgreSQL RLS
- Neo4j project-scope negative query
- vector role filter

### 완료 기준

- 한 명령으로 세 저장소 실행
- release gate에 polyglot integration profile 존재

## Stage 47 — Unified Dataset Version and Projection Pipeline

### 목적

한 Dataset Version이 세 저장소에 일관된 identity로 projection되게 한다.

### schema

- datasets
- dataset_versions
- dataset_files
- store_projections
- ontology_mappings
- materializations

### worker

- outbox consume
- Neo4j upsert
- vector chunk/index
- projection status
- retry and dead-letter

### visible slice

- Dataset Catalog 첫 화면
- store별 ready/indexing/failed badge
- record count와 source version

### 완료 기준

- fixture dataset 1개가 PostgreSQL, Neo4j, vector에 projection
- 같은 object ID와 dataset version으로 교차 조회

## Stage 48 — Ontology Workbench Vertical Slice

### 목적

첫 번째 완성된 `SOON` 메뉴를 제거한다.

### 기능

- object types and link types
- object search/table
- Neo4j subgraph
- object inspector
- source dataset/version
- relational detail + graph relationships
- Add Graph Board

### UI

- three-pane high-density layout
- Blueprint components selective use
- React Flow graph
- server pagination
- route restore

### 완료 기준

- `/ontology` 실제 업무 흐름 end-to-end
- screenshot baseline
- project isolation E2E

## Stage 49 — Project 2 LangGraph Multi-Store Orchestrator

### 목적

자연어 요청을 적합한 저장소로 routing한다.

### 구현

- state and checkpoint
- intent classifier
- relational tool
- Project 3 graph tool
- vector tool
- evidence merge
- claim validation
- typed answer/dashboard compile
- audit trace

### 안전장치

- no write query
- project/role scope
- row/depth/top-k limits
- timeout
- source version
- query hash

### visible slice

Ontology Workbench에 Ask panel 추가.

예:

```text
“M-014와 연결된 최근 위험 사건, 관련 부품, 유사 정비 사례와 SOP를 보여줘.”
```

결과:

- relational event rows
- Neo4j path
- vector documents
- evidence badges
- Add to Analysis/Dashboard

### 완료 기준

- hybrid query가 실제 세 tool을 사용
- run trace가 Governance에서 조회 가능

## Stage 50 — Dataset Catalog Completion

### 기능

- list/detail/version/schema/profile
- ingestion/quarantine
- projection health
- lineage
- document index readiness
- materializations
- Save Analysis Result as Dataset

### materialization

- preview run과 full materialization 분리
- Parquet write
- checksum
- dataset version registration
- downstream reference

### 완료 기준

- `Datasets SOON` 제거
- analysis result를 다시 Analysis source로 사용 가능

## Stage 51 — Governance Workbench Completion

### 기능

- access/policies
- approvals
- audit
- agent runs
- validated Cypher metadata
- RAG evidence sources
- lineage
- projection health/retry
- export policy

### 완료 기준

- `Governance SOON` 제거
- quality auditor가 하나의 Dashboard claim을 source dataset, graph path, document chunk, agent run까지 추적

## Stage 52 — Server-Scale Analysis and Dashboard

### backend

- relational query compiler
- native aggregate pushdown
- cursor pagination
- async analysis jobs
- cache
- cancellation
- progress
- graph/vector board data bindings

### frontend

- job status
- rows scanned
- elapsed
- cache hit
- source freshness
- pagination
- retry/cancel

### 완료 기준

- 5,000-row hard scan 제거
- preview limit와 full run을 명시적으로 구분
- Dashboard cross-filter가 server re-query

## Stage 53 — WorkOrder and Operational Ontology Completion

### 작업

- WorkOrder Object Type
- Equipment↔WorkOrder
- WorkOrder↔Action
- WorkOrder↔Evidence
- Project 3 graph mapping alignment
- role workflows

### 완료 기준

- Join Board가 inspection alias를 사용하지 않음
- Ontology graph, Dashboard, Action flow에서 같은 WorkOrder ID 사용

## Stage 54 — Visual Convergence and Frontend Performance

### visual

- design tokens
- high-density shell
- consistent inspector
- table density
- graph styling
- chart typography
- loading/empty/error states
- light/dark consistency

### performance

- route-level lazy loading
- ECharts lazy import
- React Flow lazy import
- vendor chunk strategy
- virtual table
- memoized Board rendering

### quality

- screenshot regression
- keyboard navigation
- accessibility gate
- pointer drag/resize E2E

### 완료 기준

- initial bundle budget
- three Workbench reference screenshots approved
- no `SOON` item

## Stage 55 — Production Integration and Release Gate

### integration

- live PostgreSQL
- Neo4j
- pgvector
- Project 3 service
- worker
- backup/restore
- observability

### test gate

- unit
- PostgreSQL repository integration
- Neo4j integration
- vector retrieval integration
- Project 3 contract
- LangGraph checkpoint/resume
- tenant/project negative
- Playwright
- visual regression
- performance smoke
- degraded mode

### 완료 기준

- production-like compose stack에서 전체 E2E
- graph/RAG unavailable degraded mode E2E
- documented rollback

---

## 15. 테스트 전략

### 15.1 unit

- query intent classifier
- typed query validation
- projection mapper
- DashboardSpec validator
- planner deterministic fallback
- source reference merge

### 15.2 integration

- PostgreSQL migration/RLS/repository
- pgvector project and role filtering
- Neo4j schema and path query
- outbox projection
- materialization
- Project 3 HTTP contract
- LangGraph checkpoint and resume

### 15.3 security negative tests

- tenant A cannot query tenant B graph
- project A vector chunks excluded from project B
- generated write Cypher blocked
- project scope predicate missing query blocked
- unknown label/property blocked
- unauthorized document excluded
- dashboard query cannot bypass role field mask

### 15.4 E2E

- Ontology explorer
- Dataset ingest/version/projection
- hybrid Ask query
- Add result to Analysis
- Add board to Dashboard
- Governance trace
- Save Dataset materialization
- role-specific visibility

### 15.5 visual regression

대표 viewport:

- 1440×900 desktop
- 1280×800 compact laptop
- 390×844 field/mobile

대표 route:

- Dashboard
- Analysis
- Ontology
- Datasets
- Governance

---

## 16. 성능 목표

초기 목표이며 실데이터 baseline 후 조정한다.

- Dashboard initial shell: 2초 이내 local warm load
- relational preview: p95 1.5초 이내
- graph depth 2 subgraph: p95 1.5초 이내, node/edge limit 적용
- vector top 5 search: p95 1.5초 이내 local baseline
- hybrid query: tool별 timeout과 partial result 지원
- initial route JavaScript: 500KB warning 해소를 목표
- table: server pagination + visible rows virtualization
- query metadata: elapsed, rows, cache, source version 표시

---

## 17. 리소스 낭비 방지 규칙

1. 새로운 추상화는 실제 route 또는 두 번째 구현 사용처가 없으면 추가하지 않는다.
2. Project 3의 Text-to-Cypher/LangGraph/RAG를 Project 2에 복제하지 않는다.
3. architecture-only stage는 한 단계를 넘기지 않는다.
4. 모든 단계는 사용자에게 보이는 route, panel, badge, interaction 중 하나로 끝나야 한다.
5. `SOON` 메뉴보다 새로운 역할별 보드를 먼저 늘리지 않는다.
6. 문서 분석 파일을 추가로 여러 개 만들지 않고 본 문서를 통합 source of truth로 사용한다.
7. frontend 완료율은 화면별 acceptance 기준으로 계산한다.
8. backend 완료율은 live store integration과 negative isolation test를 포함한다.
9. feature flag 뒤에 숨겨진 기능은 완료로 계산하지 않는다.
10. mock/fixture 결과와 실제 store 결과를 UI에서 구분한다.
11. natural-language answer는 source evidence가 없으면 확정 표현을 사용하지 않는다.
12. visual 변경은 screenshot baseline 없이 완료 처리하지 않는다.

---

## 18. 우선 구현 순서

다음 순서를 권장한다.

```text
1. Stage 44 — 문서/ADR/우선순위 재설정
2. Stage 45 — planner canonical 이동 + Project 3 typed client
3. Stage 46 — PostgreSQL/pgvector/Neo4j local stack
4. Stage 47 — dataset projection + Dataset Catalog 첫 화면
5. Stage 48 — Ontology Workbench 완성
6. Stage 49 — LangGraph multi-store query
7. Stage 50 — Dataset Catalog 완성/materialization
8. Stage 51 — Governance Workbench
9. Stage 52 — Analysis/Dashboard 대용량 실행
10. Stage 53 — WorkOrder ontology
11. Stage 54 — visual convergence/performance
12. Stage 55 — production release gate
```

단, 실제 체감 개선을 위해 Stage 45~49에서는 backend만 연속 구현하지 않고 각 단계마다 Ontology 또는 Dataset 화면에 결과를 노출한다.

---

## 19. 첫 다음 세션의 구체적 작업

다음 세션은 전체 roadmap을 한 번에 구현하지 않는다. 아래 첫 vertical slice를 완료한다.

### 목표

**Planner canonical migration + Project 3 graph client + Ontology Workbench read-only preview**

### 작업 파일 예상

```text
api/ontology_dashboard/planner/
api/ontology_dashboard/integrations/project3/
api/ontology_dashboard/routers/integrations.py
api/ontology_dashboard/routers/ontology.py
api/ontology_dashboard/dependencies.py
web/src/features/ontology/OntologyWorkbench.tsx
web/src/features/ontology/OntologyExplorer.tsx
web/src/features/ontology/GraphInspector.tsx
web/src/api.ts
web/src/routing.ts
web/src/features/dashboard/DashboardShell.tsx
```

### API

- Project 3 health/readiness proxy
- graph schema
- node search
- subgraph
- typed error/degraded response

### UI

- Ontology menu 활성화
- Object Types list
- object search
- subgraph preview
- source badge: `PostgreSQL`, `Neo4j`, `Fixture`, `Unavailable`
- project/workspace scope

### acceptance

- route direct access
- Project 3 connected mode
- Project 3 unavailable degraded mode
- project isolation
- canonical planner imports
- no legacy planner physical dependency
- build/test/E2E

---

## 20. 새 세션용 명령 프롬프트

```text
@devspace.mcp

다음 로컬 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

가장 먼저 docs/next-session-master-prompt.md와 docs/10-product-convergence-polyglot-agentic-roadmap.md를 읽어줘. 그 다음 필수 architecture 문서, 현재 코드, tests, migrations, frontend routes를 비교해줘.

Project 2와 Project 3은 하나의 실제 업무 제품을 두 구현 과제로 나눈 것이다. Project 2를 단순한 평탄 JSON 소비자로 제한하지 말고, PostgreSQL operational data, Neo4j relationship graph, pgvector/LlamaIndex semantic retrieval을 역할별 Analysis/Dashboard/Ontology/Dataset/Governance 화면으로 전달하는 orchestration 계층으로 구현해줘.

Project 3 저장소 경로:
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트3

Project 3에 이미 존재하는 Neo4j ETL, read-only Text-to-Cypher, LangGraph validation/correction workflow, RAG 기능을 먼저 조사하고 중복 구현하지 말아줘. Project 2에는 typed Project3 client, multi-store query ports, governance/audit, delivery UI를 구현해줘.

첫 작업은 docs/10-product-convergence-polyglot-agentic-roadmap.md의 Stage 45 vertical slice다.

- ontology_planner_service를 factory_signal_board 물리 경로에서 ontology_dashboard/planner로 이동
- ontology_dashboard.__init__의 legacy path hack 제거를 향한 단계적 migration 시작
- Project 3 health/schema/search/subgraph typed client 구현
- /app/projects/:projectId/workspaces/:workspaceId/ontology read-only Workbench 구현
- Project 3 연결 가능/불가능 상태를 실제 UI에 표시
- tenant/project scope와 read-only 안전성 검증
- 관련 tests, docs, build, E2E 수행

중요 원칙:
- 검증되지 않은 arbitrary SQL/Cypher 실행 금지
- Project 3의 검증된 read-only Cypher workflow 호출은 허용
- LLM은 typed intent와 DashboardSpec만 생성
- RDB/Neo4j/vector 결과에 source/version/evidence 표시
- architecture-only 작업으로 끝내지 말고 실제 Ontology 화면까지 완성
- 새 추상화는 실제 화면 사용처가 있어야 함
- 기존 Dashboard/Analysis 회귀 유지
- 구현하지 않은 기능을 완료라고 표시하지 않기

완료 후 변경 파일, 데이터 흐름, 테스트 결과, 실제 접속 route, 남은 위험, 다음 Stage를 보고해줘.
```

---

## 21. 최종 완료 정의

이 roadmap의 최종 완료는 파일 수나 architecture percentage가 아니다.

다음 사용자 흐름이 실제로 동작해야 한다.

```text
1. 사용자가 Project와 Workspace를 선택한다.
2. Dataset Catalog에서 데이터 버전과 세 저장소 projection 상태를 확인한다.
3. Ontology Workbench에서 object와 Neo4j 관계를 탐색한다.
4. 자연어로 질문하면 LangGraph가 relational/graph/vector tool을 선택한다.
5. 결과에는 표, graph path, 관련 문서, source version, warnings가 표시된다.
6. 사용자는 결과를 Analysis path에 추가한다.
7. Analysis는 server query와 async run으로 계산된다.
8. 결과를 Dashboard Board 또는 materialized Dataset으로 저장한다.
9. Dashboard에서 cross-filter가 server query를 재실행한다.
10. Governance에서 query plan, validated Cypher hash, document evidence, dataset lineage, approval, export를 추적한다.
11. Ontology, Datasets, Governance 메뉴에 더 이상 SOON이 없다.
12. 모든 기능이 organization/project/workspace/role scope를 지킨다.
```

이 상태에 도달해야 “온톨로지 대시보드”라는 이름과 실제 제품 경험이 일치한다.
