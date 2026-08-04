# Predictive Maintenance Canonical v2 Integration Plan

> **상태 안내 — 2026-08-04**
>
> 이 문서는 Phase 0~2를 구현할 때 사용한 V2 기준 계획이다. Phase 0~2의 계약과
> 커밋은 그대로 유지한다. Phase 3부터는 데이터 패키지를
> `predictive_maintenance_canonical_v3.1`로 전환하므로 다음 문서를 우선 기준으로
> 사용한다.
>
> `docs/30-implementation/predictive-maintenance-canonical-v3-upgrade-plan.md`
>
> 특히 V3.1 source contract의 추가 필드, `result_artifact.jsonl`, 변경된 row count,
> AI4I 물리 계약, tool-wear continuity, maintenance evidence,
> negative-local-only benchmark를 반영하지 않고 아래 V2 수치를
> 그대로 Phase 3 이후 완료 조건으로 사용하면 안 된다.

- 작성일: 2026-08-04
- 대상 애플리케이션: `mvp-프로젝트2` / Ontology Dashboard
- 연결 데이터 패키지: `predictive_maintenance_canonical_v2`
- 목표: checksum으로 고정된 다중 파일 데이터셋을 PostgreSQL과 Neo4j에 안전하게 연결하고, 데이터 의미와 사용자 목적에 따라 적절한 시각화를 추천·변경할 수 있는 온톨로지 기반 실행 경로를 만든다.

---

## 1. 현재 상태 확인

### 1.1 데이터 패키지

현재 로컬 패키지에는 이미 30일 기준 생성 산출물이 존재한다.

| 리소스 | 현재 행 수 | 역할 |
|---|---:|---|
| `asset_master.csv` | 100 | 압축기 20대, CNC 80대의 기준정보 |
| `asset_relation.csv` | 80 | 압축기와 CNC의 공급 관계 |
| `compressor_sensor_observation.csv` | 86,400 | 압축기 10분 단위 시계열 |
| `cnc_sensor_observation.csv` | 345,600 | CNC 10분 단위 시계열 |
| `cnc_production_cycle.csv` | 170,860 | 제품 생산 cycle |
| `maintenance_event.csv` | 795 | 예방·고장복구 정비 이벤트 |
| `prediction_snapshot.jsonl` | 100 | 최신 자산별 예측 snapshot |
| `prediction_factor.jsonl` | 300 | 예측 기여 요인 |
| `prediction_timeline.jsonl` | 68,211 | replay용 시간별 예측 |

`dataset_manifest.json`에는 dataset version, 생성 기간, seed, 관측 간격, 파일별 SHA-256이 들어 있다. 따라서 이후 다시 생성하더라도 같은 경로의 파일을 덮어쓴 것으로 취급하면 안 되고, checksum이 다른 새 Dataset Version으로 등록해야 한다.

### 1.2 프로젝트2에 이미 있는 기반

프로젝트2에는 다음 기반이 존재한다.

- Project → Workspace → Role Dashboard 경계
- Dataset, Dataset Version, Dataset File, Ontology Mapping, Store Projection 모델
- PostgreSQL migration과 organization/project RLS
- File Adapter, ingestion run, quarantine, checksum 검증
- Ontology object/link persistence
- Prediction Result Contract와 prediction repository
- transactional outbox
- Project 3 typed client와 multi-store orchestrator
- field profiler와 deterministic visualization recommender
- metric, table, bar, stacked bar, line, area, pie, histogram, scatter, heatmap registry
- LLM이 deterministic 후보 밖의 chart나 field를 만들지 못하게 막는 planner 경계

### 1.3 현재 부족한 부분

1. 현재 File Adapter manifest는 한 번에 단일 파일만 처리한다.
2. 현재 CLI는 PostgreSQL ingestion을 거부하고 SQLite 전용이다.
3. Dataset Projection 모델은 object 중심이며 link와 대용량 fact/time-series 적재 계약이 부족하다.
4. PostgreSQL에 predictive maintenance 전용 대용량 시계열 적재 경로가 없다.
5. Neo4j writer가 프로젝트2에 없고, 현재 설계상 graph capability는 Project 3가 소유한다.
6. 현재 visualization recommender는 row shape 기반 추천이다. ontology 의미, 단위, 분석 목적, aggregation/window까지 자동 설계하는 수준은 아니다.
7. LLM은 이미 만들어진 후보의 순서를 바꿀 수 있을 뿐, 안전한 typed query plan을 만들지는 않는다.

---

## 2. 확정할 아키텍처 원칙

### 2.1 저장소 역할

```text
Canonical files
    ↓ checksum validation
PostgreSQL
    ├─ Dataset/Version/File/Manifest/Governance
    ├─ Asset master and operational events
    ├─ High-volume sensor and production facts
    ├─ Prediction results and evidence
    └─ Transactional outbox
          ↓ projection event
Project 3 graph ingestion
          ↓
Neo4j
    ├─ Asset/site/cell topology
    ├─ Maintenance and prediction relationships
    ├─ lineage/impact/root-cause traversal
    └─ graph query evidence
```

- PostgreSQL은 operational source of truth다.
- Neo4j는 관계·경로·영향 분석용 projection이다.
- raw file은 Dataset Version과 checksum으로 불변 등록한다.
- 그래프 장애 시에도 PostgreSQL 기반 Dataset, Dashboard, Analysis 화면은 동작해야 한다.

### 2.2 대용량 센서 데이터 원칙

432,000개의 sensor observation을 모두 Ontology Object 또는 Neo4j Node로 만들지 않는다.

권장 저장 방식:

- PostgreSQL의 project-scoped partitioned fact table에 적재
- Ontology에는 Asset, Site, Cell, Prediction, Maintenance, WorkOrder 등 업무 의미가 있는 entity/event만 materialize
- Dashboard용 시계열은 PostgreSQL에서 시간 window와 aggregation을 적용해 조회
- Neo4j에는 원시 센서 row 대신 asset/time-window summary와 source reference만 projection

이 원칙을 지켜야 저장 공간, graph traversal 성능, ontology 탐색 가독성을 동시에 유지할 수 있다.

### 2.3 Project 3 경계

기존 ADR을 유지한다.

- 프로젝트2가 자연어 Cypher 생성과 graph ingestion을 중복 구현하지 않는다.
- graph write는 Project 3의 typed ingestion/projection API로 전달한다.
- 프로젝트2는 outbox delivery, projection status, retry, Dataset Version identity를 소유한다.
- Project 3 API가 아직 해당 write contract를 제공하지 않으면 먼저 contract를 추가하고, 그 전까지 graph projection 상태는 `pending` 또는 `blocked`로 명시한다.

---

## 3. 데이터 패키지용 Bundle Manifest

현재 `DatasetManifest`는 단일 `source`만 갖는다. predictive maintenance package는 여러 파일의 join과 역할이 중요하므로 bundle contract가 필요하다.

### 3.1 제안 contract

```json
{
  "manifest_version": "2.0",
  "manifest_id": "predictive-maintenance-canonical-v2-20260804",
  "organization_id": "org-ontology-demo",
  "project_id": "predictive-maintenance-canonical-v2",
  "workspace_id": "predictive-maintenance-main",
  "adapter_code": "predictive-maintenance-canonical-v2",
  "dataset_name": "Predictive Maintenance Canonical v2",
  "dataset_version": "canonical-independent-v1.0",
  "bundle_checksum_sha256": "...",
  "files": [
    {
      "role": "asset_master",
      "uri": "file:///.../asset_master.csv",
      "format": "csv",
      "checksum_sha256": "..."
    },
    {
      "role": "asset_relation",
      "uri": "file:///.../asset_relation.csv",
      "format": "csv",
      "checksum_sha256": "..."
    },
    {
      "role": "compressor_sensor_observation",
      "uri": "file:///.../compressor_sensor_observation.csv",
      "format": "csv",
      "checksum_sha256": "..."
    }
  ],
  "source_contract": {
    "evaluation_truth_separate": true,
    "prediction_outputs_in_source": false
  }
}
```

### 3.2 bundle checksum

bundle checksum은 파일 경로가 아니라 다음 정렬된 값으로 계산한다.

```text
dataset_version
+ role별 file checksum
+ generator version
+ schema version
+ source-contract flags
```

이 값이 같으면 idempotent 재실행으로 처리하고, 다르면 새 Dataset Version을 만든다.

### 3.3 truth 격리

`canonical/evaluation_truth`는 제품 runtime source로 적재하지 않는다.

- model/evaluation pipeline만 읽을 수 있는 별도 artifact scope로 등록
- Dashboard, Agent, Ontology query에서 기본 비공개
- synthetic truth가 사용자 evidence로 노출되지 않는 negative test 추가

---

## 4. PostgreSQL 적재 모델

### 4.1 Core catalog

기존 테이블을 재사용한다.

- `datasets`
- `dataset_versions`
- `dataset_files`
- `ontology_mappings`
- `store_projections`
- `adapter_ingestion_runs`
- `quarantine_records`
- `prediction_results`
- `transactional_outbox`

### 4.2 predictive maintenance fact tables

새 PostgreSQL migration을 추가한다.

#### `pm_assets`

```text
organization_id
project_id
workspace_id
dataset_version_id
asset_id
asset_type
site_id
cell_id
source_sha256
```

Primary identity:

```text
(organization_id, project_id, dataset_version_id, asset_id)
```

#### `pm_asset_relations`

```text
from_asset_id
relation_type
to_asset_id
dataset_version_id
```

#### `pm_compressor_observations`

현재 wide schema를 유지하고 `observed_at` 기준 range partition을 사용한다.

#### `pm_cnc_observations`

현재 wide schema를 유지하고 `observed_at` 기준 range partition을 사용한다.

#### `pm_production_cycles`

`product_id`, `cnc_asset_id`, cycle time, product type, cutting/tool-wear 값을 저장한다.

#### `pm_maintenance_events`

정비 이벤트의 canonical row와 source event identity를 저장한다.

#### `pm_prediction_timeline`

replay와 historical risk chart용 시간별 예측을 저장한다.

#### `pm_prediction_factors`

prediction별 ranked factor를 저장한다.

### 4.3 왜 observation을 JSONB 하나에 넣지 않는가

- 시간 범위, asset, site, sensor 조건 조회가 핵심이다.
- typed numeric column이 aggregate와 index에 유리하다.
- compressor와 CNC는 sensor schema가 다르므로 억지로 하나의 nullable mega table로 합치지 않는다.
- 향후 다른 데이터는 domain pack별 fact table 또는 governed materialization으로 확장한다.

### 4.4 적재 방식

대량 row insert loop 대신 PostgreSQL `COPY`를 사용한다.

```text
validate file and checksum
→ create ingestion run
→ COPY into temporary staging table
→ schema/foreign-key/time-range checks
→ merge into version-scoped target table
→ rejected rows to quarantine
→ commit catalog + data + outbox atomically
```

한 파일이 실패하면 해당 Dataset Version의 전체 ingestion을 실패 처리한다. 일부 파일만 ready인 상태를 최종 성공으로 표시하지 않는다.

---

## 5. Ontology Mapping

### 5.1 Object types

| Source | Ontology object | 비고 |
|---|---|---|
| `asset_master` | `equipment` | compressor/CNC를 subtype property로 표현 |
| `site_id` | `site` | 조직 내 물리 위치 |
| `cell_id` | `production_cell` | site 하위 운영 단위 |
| `maintenance_event` | `work_order`, `maintenance_action` | 기존 canonical WorkOrder 모델 재사용 |
| prediction snapshot/timeline | `risk_event`, `prediction_result` | 최신 상태와 이력 분리 |
| `cnc_production_cycle` | `production_cycle` | 필요 범위만 ontology object로 materialize |

### 5.2 Link types

```text
site_contains_cell
cell_contains_equipment
equipment_supplies_air_to_equipment
equipment_has_risk_event
equipment_has_work_order
work_order_has_maintenance_action
equipment_completed_production_cycle
prediction_supported_by_factor
```

### 5.3 sensor evidence

원시 observation object를 만들지 않고 다음 source reference를 사용한다.

```text
dataset:<dataset_id>:version:<dataset_version_id>:asset:<asset_id>:window:<start>/<end>
```

RiskEvent의 evidence에는 다음만 넣는다.

- asset identity
- observation time window
- selected sensor summary
- prediction factor
- registered dataset/version/checksum reference

### 5.4 mapping 승인

- domain pack이 기본 mapping draft를 제공
- FDE 또는 관리자 화면에서 identity, property, relation, unit을 검토
- approved mapping만 projection 실행
- mapping 변경 시 기존 Dataset Version을 덮어쓰지 않고 mapping version과 reprojection 기록을 남긴다.

---

## 6. Neo4j Projection

### 6.1 projection payload

프로젝트2에서 Project 3로 보내는 typed batch 예시:

```json
{
  "contract_version": "1.0",
  "organization_id": "org-ontology-demo",
  "project_id": "predictive-maintenance-canonical-v2",
  "workspace_id": "predictive-maintenance-main",
  "dataset_id": "predictive-maintenance-canonical-v2",
  "dataset_version_id": "dsv-...",
  "source_sha256": "...",
  "nodes": [],
  "relationships": []
}
```

### 6.2 Neo4j node scope

권장 node:

- `Site`
- `ProductionCell`
- `Equipment`
- `RiskEvent`
- `WorkOrder`
- `MaintenanceAction`
- 선택된 `ProductionCycle`

권장하지 않는 node:

- 모든 10분 sensor observation
- 모든 prediction timeline point
- 모든 factor value의 중복 node

### 6.3 relationship scope

```text
(Site)-[:CONTAINS]->(ProductionCell)
(ProductionCell)-[:CONTAINS]->(Equipment)
(Compressor)-[:SUPPLIES_AIR_TO]->(CNC)
(Equipment)-[:HAS_RISK_EVENT]->(RiskEvent)
(Equipment)-[:HAS_WORK_ORDER]->(WorkOrder)
(WorkOrder)-[:HAS_ACTION]->(MaintenanceAction)
(RiskEvent)-[:SUPPORTED_BY]->(DatasetVersionReference)
```

### 6.4 idempotency

Neo4j key는 최소 다음 scope를 포함한다.

```text
project_id + dataset_version_id + object_type + source_identity
```

같은 Dataset Version 재실행은 MERGE되고, 다른 Dataset Version은 lineage를 유지한다.

### 6.5 outbox event

```text
dataset.version.relational_ready
ontology.mapping.approved
graph.projection.requested
graph.projection.completed
graph.projection.failed
```

Project 3 장애 시 retryable error와 마지막 실패 사유를 `store_projections`에 남긴다.

---

## 7. Prediction Result와 Replay 연결

### 7.1 snapshot 변환

`prediction_snapshot.jsonl` 한 행을 프로젝트2 `PredictionResult`로 변환한다.

```text
asset_id                 → subject.object_id
observed_at              → subject.observed_at
failure_probability      → prediction.score
status                   → prediction.status
predicted_failure_type   → prediction.label
confidence               → prediction.confidence
prediction_horizon_hours → prediction.horizon
model_version            → model.model_version
dataset_version          → model.dataset_version
```

factor 파일을 `PredictionEvidence`로 결합하고, checksum과 timeline source reference를 evidence source에 넣는다.

### 7.2 timeline 저장

timeline은 최신 prediction repository만으로 처리하지 않는다.

- 최신 상태: `prediction_results`
- replay/history: `pm_prediction_timeline`
- 설명: `pm_prediction_factors`

### 7.3 replay API

기존 별도 Replay Server의 기능을 프로젝트2 API에 바로 복사하지 않고 adapter로 연결한다.

우선 경로:

```text
PostgreSQL time-window query
→ simulation cursor
→ sensor observations + nearest prediction
→ SSE response
```

source CSV를 다시 생성하거나 seek마다 모델을 학습하지 않는다.

---

## 8. 데이터 기반 자동 시각화

### 8.1 현재 가능한 것

현재 구현은 row profile을 보고 다음 후보를 자동 추천할 수 있다.

- 시간 + 수치 → line/area
- category + 수치 → bar/pie
- 수치 2개 → scatter
- category 2개 + 수치 → stacked bar/heatmap
- 단일 수치 → metric/histogram
- 복잡하거나 호환되지 않음 → table

LLM은 registry에 등록된 deterministic 후보 중 하나만 선택할 수 있다. 이는 안전한 시작점이지만, 최종 목표인 “어떤 데이터를 연결해도 의미에 맞는 그래프를 스스로 구성”하려면 아래 계층이 더 필요하다.

### 8.2 Semantic Field Catalog

각 field에 물리 type뿐 아니라 의미를 등록한다.

```text
field_id
semantic_role: identifier | dimension | measure | timestamp | status | geo
domain_concept: asset | site | sensor | prediction | maintenance | product
unit
aggregation: avg | min | max | sum | count | latest | none
grain
timezone
allowed_filters
```

예:

```text
observed_at         → timestamp, 10-minute grain
failure_probability → measure, probability, avg/max/latest
asset_id            → identifier and grouping dimension
asset_type          → categorical dimension
vibration_raw       → measure with sensor unit
maintenance_type    → categorical workflow state
```

### 8.3 Typed Visualization Query Plan

에이전트가 SQL 문자열을 직접 만들지 않고 다음 contract를 만든다.

```json
{
  "source": {
    "dataset_id": "...",
    "dataset_version_id": "...",
    "object_type": "equipment"
  },
  "intent": "trend",
  "dimensions": ["asset_id"],
  "measures": [
    {"field": "failure_probability", "aggregation": "max"}
  ],
  "time": {
    "field": "observed_at",
    "grain": "hour"
  },
  "filters": [],
  "chart_kind": "line"
}
```

서버는 다음을 검증한다.

- field가 catalog에 존재하는가
- aggregation이 허용되는가
- project/workspace scope가 일치하는가
- row limit와 time range가 안전한가
- chart channel과 query result가 호환되는가

### 8.4 추천 순서

```text
사용자 질문 또는 Board goal
→ project/dataset/ontology context 선택
→ semantic field catalog 조회
→ deterministic query candidates 생성
→ deterministic chart candidates 생성
→ LLM은 후보 재정렬과 설명만 수행
→ server validation
→ query execution
→ result profile 재검증
→ Generic ECharts render
```

### 8.5 predictive maintenance 기본 추천

| 질문/목적 | 기본 시각화 |
|---|---|
| 시간에 따른 센서 변화 | multi-series line |
| 설비별 현재 위험 비교 | sorted horizontal bar |
| site × failure type 집중도 | heatmap |
| 위험도 분포 | histogram |
| torque와 tool wear 관계 | scatter |
| 정비 유형 구성 | stacked bar 또는 donut |
| 자산 관계와 upstream 영향 | ontology graph |
| 현재 KPI | metric cards + exception table |
| replay 상태 | line chart + timeline cursor |

### 8.6 사용자 변경

- 추천 chart는 default일 뿐 강제가 아니다.
- 사용자가 chart kind, aggregation, field mapping을 변경할 수 있어야 한다.
- 변경값은 user preference 또는 dashboard board version에 저장한다.
- 데이터 schema가 바뀌어 기존 설정이 깨지면 silent fallback 대신 incompatibility 이유를 표시한다.

### 8.7 확장 chart registry

현재 10종을 먼저 안정화하고 이후 아래를 추가한다.

- box plot
- gauge
- waterfall
- candlestick가 아닌 generic interval/range chart
- sankey
- network graph
- Gantt/timeline
- calendar heatmap
- geospatial map

각 chart는 required channel, cardinality limit, selection support, aggregation rule을 registry에 선언해야 한다.

---

## 9. 구현 Phase

## Phase 0 — Contract Freeze

### 작업

- canonical package의 public/runtime 파일과 evaluation truth를 구분
- bundle manifest v2 schema 확정
- Project, Workspace, Dataset identity 확정
- PostgreSQL/Neo4j object identity 규칙 확정
- Project 3 graph ingestion contract 확정

### 완료 조건

- 동일 생성 결과는 동일 bundle checksum
- 다른 seed, 기간, schema는 새 Dataset Version
- truth 파일이 runtime manifest에 포함되지 않음

## Phase 1 — Bundle Adapter

### 작업

- `PredictiveMaintenanceCanonicalV2Adapter` 추가
- multi-file manifest model과 validator 추가
- 각 role별 header, checksum, join key, time range 검증
- package validation report를 ingestion artifact로 저장
- SQLite 전용 CLI 제한 제거 또는 PostgreSQL 전용 새 CLI 추가

### 완료 조건

- 6개 canonical source와 3개 prediction artifact를 한 run으로 검증
- 누락 파일, checksum mismatch, 잘못된 relation, 잘못된 asset reference가 quarantine/failure로 보임
- 재실행이 중복 Dataset Version을 만들지 않음

## Phase 2 — PostgreSQL Bulk Ingestion

### 작업

- predictive maintenance migration 추가
- COPY 기반 staging/merge 구현
- project RLS 추가
- dataset/version/file/catalog와 fact table transaction 결합
- latest snapshot과 historical timeline 분리 저장

### 완료 조건

- current package 전체 row count가 source와 일치
- asset/relation foreign key parity 통과
- dataset version별 데이터 격리
- 다른 project context에서 조회 불가

## Phase 3 — Ontology Materialization

### 작업

- equipment/site/cell/risk/work-order/maintenance/production mapping 추가
- source identity와 Dataset Version lineage 연결
- sensor evidence window reference 생성
- mapping approval와 reprojection 상태 연결

### 완료 조건

- Ontology Explorer에서 Site → Cell → Equipment 탐색 가능
- Equipment에서 RiskEvent와 WorkOrder로 traversal 가능
- 원시 sensor row가 Ontology Explorer를 오염시키지 않음

## Phase 4 — Neo4j Projection via Project 3

### 작업

- Project 3 typed graph batch endpoint 또는 기존 ingestion contract 확장
- 프로젝트2 outbox delivery adapter 구현
- node/link batch, retry, idempotency, status 저장
- graph query 결과에 dataset version/source reference 반환

### 완료 조건

- compressor → CNC 공급 관계 탐색 가능
- equipment → prediction → maintenance path 탐색 가능
- 동일 Dataset Version 재실행 시 node/edge 중복 없음
- Project 3 장애 중 relational 화면은 정상, graph badge만 degraded

## Phase 5 — Prediction and Replay Vertical

### 작업

- prediction snapshot/factor contract 변환기
- timeline query API
- replay cursor, pause/resume/speed/seek와 SSE adapter
- Dashboard source freshness와 simulation time 분리 표시

### 완료 조건

- 특정 simulation time의 sensor와 nearest prediction이 일치
- seek가 model retraining을 유발하지 않음
- 최신 prediction과 replay prediction을 UI에서 구분

## Phase 6 — Semantic Visualization Planner

### 작업

- semantic field catalog 추가
- typed query-plan model과 validator 추가
- PostgreSQL aggregate query compiler 추가
- 기존 visualization recommender에 intent, unit, grain, cardinality score 반영
- LLM은 allowlist candidate reranking만 수행
- 선택 이유, fallback 이유, query provenance 표시

### 완료 조건

- 같은 데이터라도 “시간 추세”, “설비 비교”, “분포”, “관계” 목적에 따라 다른 chart를 선택
- 존재하지 않는 field/chart/aggregation을 에이전트가 생성할 수 없음
- 사용자가 chart를 변경하고 저장 가능

## Phase 7 — Dataset-Driven Dashboard

### 작업

- Project Home에서 Dataset Version 선택
- role별 기본 dashboard template 생성
- manager, engineer, data scientist, FDE 관점 분리
- chart switcher, field/aggregation inspector, explanation panel
- graph board와 relational chart의 cross-filter 연결

### 완료 조건

- 새 Project를 선택하면 해당 Dataset/Ontology/Prediction만 보임
- 기본 화면이 기존 fixture 하드코딩 없이 새 데이터로 렌더링
- chart selection이 다른 board에 주는 영향을 UI에서 설명

## Phase 8 — Operations and Governance

### 작업

- generation → validation → ingestion → projection run lineage
- package checksum, schema diff, mapping diff 화면
- store readiness와 retry UI
- backup/restore와 re-ingestion runbook
- source truth leakage, tenant isolation, stale projection negative tests

### 완료 조건

- Dataset Catalog 한 화면에서 PostgreSQL ready, Neo4j ready/degraded 상태 확인
- 실패 run의 파일, row, error, retry 이력 확인
- 어떤 chart와 agent answer도 사용한 Dataset Version을 추적 가능

---

## 10. 우선순위

### 지금 먼저 할 것

1. Bundle Manifest v2
2. Predictive Maintenance Adapter
3. PostgreSQL migration과 COPY ingestion
4. Project/Workspace/Dataset 등록
5. Ontology object/link materialization
6. prediction snapshot/factor/timeline 연결
7. Project 3 graph projection contract

여기까지 완료하면 데이터는 제품에 제대로 연결된 상태다.

### 그 다음 할 것

1. semantic field catalog
2. typed visualization query plan
3. 자동 chart 추천 고도화
4. replay controls와 SSE
5. role별 dashboard template

### 나중에 할 것

- 모든 chart 종류 확장
- 실시간 MQTT/Kafka/OPC-UA adapter
- managed object storage
- local pgvector retrieval
- WebSocket 기반 고빈도 stream

---

## 11. 예상 주요 변경 파일

```text
schemas/dataset-bundle-manifest.schema.json
schemas/visualization-query-plan.schema.json

api/migrations/postgresql/0011_predictive_maintenance_domain_pack.sql
api/ontology_dashboard/adapters/models.py
api/ontology_dashboard/adapters/registry.py
api/ontology_dashboard/adapters/predictive_maintenance_v2.py
api/ontology_dashboard/adapters/bundle_file_adapter.py
api/ontology_dashboard/adapters/service.py
api/ontology_dashboard/datasets/models.py
api/ontology_dashboard/datasets/projection.py
api/ontology_dashboard/domain_packs/predictive_maintenance/
api/ontology_dashboard/visualizations/models.py
api/ontology_dashboard/visualizations/profiler.py
api/ontology_dashboard/visualizations/recommender.py
api/ontology_dashboard/planner/models.py
api/ontology_dashboard/planner/service.py
api/ontology_dashboard/outbox.py

scripts/ingest_predictive_maintenance_bundle.py
scripts/verify_predictive_maintenance_ingestion.py

web/src/features/datasets/
web/src/features/dashboard/visualization/
web/src/features/ontology/
web/src/features/replay/

tests/test_predictive_maintenance_bundle_adapter.py
tests/test_predictive_maintenance_postgresql.py
tests/test_predictive_maintenance_projection.py
tests/test_predictive_maintenance_visualization_planner.py
```

---

## 12. 첫 구현 단위

첫 implementation slice는 UI보다 데이터 연결에 집중한다.

```text
predictive_maintenance_canonical_v2 생성/검증
→ bundle manifest 생성
→ PostgreSQL에 Dataset Version 등록
→ assets, relations, observations, production, maintenance COPY
→ prediction snapshot/factor/timeline 저장
→ Ontology Equipment/RiskEvent/WorkOrder materialize
→ Dataset Catalog/API로 row count와 readiness 확인
```

이 slice가 끝난 뒤 Neo4j projection과 자동 chart planner를 붙인다. 그래야 UI가 임시 fixture가 아니라 실제 적재된 Dataset Version을 기준으로 동작한다.

---

## 13. 최종 성공 기준

다음 흐름이 하나의 Project 안에서 재현되어야 한다.

```text
새 canonical dataset 생성
→ manifest/checksum 검증
→ PostgreSQL ingestion
→ Ontology mapping/materialization
→ Neo4j graph projection
→ Agent가 사용자 질문을 typed query intent로 변환
→ 서버가 안전한 query와 chart 후보를 생성
→ 적절한 chart를 기본 선택
→ 사용자가 chart/field/aggregation을 변경해 저장
→ 모든 결과가 Dataset Version과 source evidence로 추적됨
```

이 상태가 되면 predictive maintenance 데이터는 첫 번째 domain pack이 되고, 이후 다른 데이터는 같은 bundle, mapping, projection, visualization contract를 사용해 추가할 수 있다.
