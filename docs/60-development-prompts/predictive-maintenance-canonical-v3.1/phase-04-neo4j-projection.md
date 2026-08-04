# Phase 04 — V3.1 Neo4j Projection via Project 3

````text
@devspace-codex

다음 두 프로젝트를 각각 실제 checkout 모드로 열어줘.

프로젝트2:
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

프로젝트3:
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트3

V3.1 데이터 패키지는 읽기 전용으로 확인해줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1

각 프로젝트를 한 번씩만 open_workspace하고 반환된 workspaceId를 구분해 재사용해.

프로젝트2의 Phase 4 진입 기준은 다음과 같다. 실제 코드와 DB artifact가 이 기준과
다르면 Phase 4 구현을 시작하기 전에 원인을 보고하고, 완료된 Phase 3 데이터를
무단 재생성하거나 기존 Dataset Version을 덮어쓰지 마.

```text
required commits        1a15af1, 6534aa5
source version          canonical-ai4i-physics-v3.1
bundle checksum         12734b1eec67ae5ccf322221967d5628ba5cf1ecb0401e6daef5c3dd7a855682
Dataset Version         dsv-1914858a-cc17-57d8-819c-d8a2435fd805
mapping version         predictive-maintenance-v3.1
materialized objects    1,984
materialized links      2,160
graph projection        pending
phase4 payload ready    true
```

프로젝트2에서 먼저 다음을 읽어줘.

- docs/30-implementation/predictive-maintenance-canonical-v3-upgrade-plan.md
- docs/20-architecture/predictive-maintenance-projection-contract.md
- docs/20-architecture/project3-adapter-contract.md
- docs/20-architecture/architecture-decisions.md의 ADR-013, ADR-014
- Phase 3 V3.1 compatibility/materialization 구현과 커밋 `1a15af1`
- V3.1 release contract 정합성 보강 커밋 `6534aa5`
- V3.1 source contract와 Result Artifact contract
- schemas/project3-graph-projection.schema.json
- api/ontology_dashboard/integrations/project3/
- api/ontology_dashboard/outbox.py
- api/ontology_dashboard/datasets/projection.py
- api/ontology_dashboard/orchestration/ports.py
- api/ontology_dashboard/domain_packs/predictive_maintenance/materialization.py
- `ontology.materialization.completed` outbox payload와 graph Store Projection row

프로젝트3에서는 README, graph ingestion, Neo4j repository, API router,
tenant/project scope, Text-to-Cypher validation 관련 문서를 먼저 찾아 읽어줘.

두 저장소 각각에서 git status --short --branch, git log -7 --oneline, remote
tracking을 확인해. 다른 세션의 미커밋 변경을 삭제·덮어쓰기·stage하지 마.

이번 목표는 프로젝트2의 approved V3.1 Ontology projection을 Project 3의 typed
endpoint로 전달하고 Neo4j에 idempotent하게 반영하는 것이다. 동일 graph ingestion,
Text-to-Cypher, RAG 로직을 프로젝트2에 복제하지 마.

Phase 3의 PostgreSQL COPY, Result Artifact 적재, Ontology materialization은 이미
완료됐다. 기존 Dataset Version을 다시 만드는 것이 아니라, pending 상태의 graph
Store Projection과 `ontology.materialization.completed` outbox를 처리한다.

구현 범위:

1. Project 3 typed graph batch endpoint
   - `schemas/project3-graph-projection.schema.json`과 Project2 typed model을 기준으로
     Project3 request/response contract를 동일하게 구현
   - organization/project/workspace/dataset/version/source checksum scope
   - dataset source version `canonical-ai4i-physics-v3.1`
   - materialization checksum과 role별 source checksum
   - Result Artifact schema `result-artifact-v1.0`
   - model `independent-logreg-v3.1`
   - prediction task `binary_failure_within_horizon`
   - V3.1 release gate와 governance artifact checksum
   - topology semantics와 excluded source 목록
   - nodes와 relationships allowlist 및 schema validation
   - idempotent MERGE key
2. V3.1 Neo4j projection scope
   - materialized domain objects 1,984건:
     - Site 4
     - ProductionCell 20
     - Equipment 100
     - RiskEvent/RiskAssessment 100
     - PredictionResult 100
     - WorkOrder 790
     - MaintenanceAction 790
     - ProductionCycle summary 80
   - materialized relationships 2,160건
   - DatasetVersionReference는 request envelope metadata로 유지하거나 정확히 1개
     reference node로 projection한다. node로 만들면 domain object와 별도로 count를 보고한다.
   - 원본 PostgreSQL object/link identity와 Dataset Version lineage를 보존
3. Result Artifact semantics
   - probability, status_grade, confidence, recommended_action을 result provenance와 함께 projection
   - recommended_action은 recommendation property이며 WorkOrder/Action node로 자동 승격 금지
   - `predicted_failure_type`은 binary generic class
   - PWF/HDF/OSF/TWF prediction node/label을 만들지 않음
4. topology와 causality 분리
   - `SUPPLIES_AIR_TO`는 topology edge
   - topology edge만으로 `CAUSES`, `ROOT_CAUSE_OF`, confirmed causal claim 생성 금지
   - request model과 JSON Schema가 `CAUSES`, `ROOT_CAUSE_OF`를 거부하는지 유지
   - graph query 결과에 relation semantics와 source provenance 반환
5. 비-projection 범위
   - 모든 10분 sensor observation
   - 모든 prediction timeline point
   - V3.1 evaluation_truth
   - optional experiment hidden_truth
   - optional experiment public case를 production graph에 혼합하지 않음
6. 프로젝트2 delivery adapter
   - transactional outbox event 소비
   - Project3Client typed method
   - V2/V3.1 Dataset Version별 projection identity
   - status pending/indexing/ready/failed
   - retryable/non-retryable error 구분
   - 성공 시 graph Store Projection의 record_count, completed_at, provider run ID 기록
   - 실패 시 relational projection과 Ontology object/link는 그대로 유지
   - outbox retry는 동일 idempotency key를 재사용
7. degraded mode
   - Project 3 또는 Neo4j 장애 시 PostgreSQL Dataset/Ontology/Result Artifact/Replay 경로 정상
   - graph readiness badge/status만 degraded
8. graph query provenance
   - organization/project/workspace/dataset_version/source reference
   - result artifact schema/model task
   - topology relation semantics
   - release gate summary와 governance checksum

Project2 outbox payload에서 다음 필드를 누락하거나 재해석하지 마.

```text
organization_id
project_id
workspace_id
dataset_id
dataset_version_id
source_version
bundle_checksum_sha256
materialization_checksum_sha256
mapping_id
mapping_version
role_checksums
object_counts
link_counts
result_contract
release_gates
governance_artifacts
topology_semantics
excluded_sources
graph_projection_status
```

현재 V3.1 release gate 기준:

```text
running_reset_count                       0
tool_replacement_event_count            731
aligned_reset_transition_count          731
reset_without_matching_maintenance        0
replacement_without_reset                 0
maintenance_evidence_accuracy            1.0
false_upstream_claim_rate                0.0
```

필수 검증:

- 두 프로젝트 간 V3.1 contract test
- 프로젝트2 outbox payload가 Project3 request로 손실 없이 변환되는 contract test
- V3.1 Dataset Version batch ingestion 성공
- 1,984 domain node와 2,160 relationship parity
- DatasetVersionReference를 node로 추가하면 별도 1건으로 정확히 보고
- V2와 V3.1 graph namespace가 version scope로 분리
- compressor → CNC 공급 topology query
- equipment → RiskAssessment/PredictionResult → WorkOrder/MaintenanceAction path query
- recommended action이 실제 WorkOrder로 잘못 projection되지 않음
- binary predicted type이 PWF/HDF/OSF/TWF label로 변환되지 않음
- 동일 V3.1 batch 재전송 시 node/edge 중복 없음
- 다른 project_id로 graph query/ingestion 불가
- malformed/unknown node/link type 거부
- `CAUSES`, `ROOT_CAUSE_OF` 관계 거부
- evaluation truth/hidden truth payload 거부
- raw sensor observation과 prediction timeline payload 거부
- Result Artifact schema/model/task 또는 V3.1 release gate 불일치 거부
- Project 3 down 상태에서 프로젝트2 relational API 정상, graph failed/degraded 표시
- outbox retry가 같은 projection을 중복 생성하지 않음
- graph answer가 topology만으로 causal confirmation을 만들지 않는 negative test
- 각 저장소의 관련 targeted tests
- git diff --check

불필요한 프로젝트2/3 전체 UI visual regression은 실행하지 마. Neo4j와 contract
vertical을 검증하는 테스트를 우선해.

검증 완료 후 저장소별로 변경을 분리해 commit/push해.

프로젝트3에 변경이 있으면:

- git commit -m "feat: ingest v3.1 ontology graph batches"
- git push origin HEAD

프로젝트2에 변경이 있으면:

- git commit -m "feat: project v3.1 ontology batches to neo4j"
- git push origin HEAD

한 저장소의 변경을 다른 저장소 커밋에 섞지 마. push 실패 시 reset/rebase/force
push 없이 저장소별 오류와 로컬 commit hash를 보고해.

마지막 보고:

- 두 저장소에서 구현한 V3.1 경계
- 실제 projected domain node/edge count와 DatasetVersionReference 처리 방식
- Result Artifact와 recommended action projection 방식
- release gate와 governance provenance 전달 결과
- topology/causality 분리 증거
- idempotency, V2/V3.1 version isolation, tenant isolation 결과
- degraded mode 결과
- 저장소별 변경 파일, commit hash, push 결과
- Phase 5에서 재사용할 graph/relation API
````
