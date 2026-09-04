---
title: Evidence Snapshot Consistency Guard Plan
status: draft
created: 2026-08-29
type: plan
scope: Product Result/Evidence에서 파생되는 UI ViewModel, Report, Closed-loop Recommendation Input, Agent Review Packet의 snapshot 일관성 검증과 mismatch retry
positioning: AI/Closed-loop가 같은 판단 근거를 소비하도록 막는 최소 backend 계약. ViewModel을 Closed-loop 입력으로 승격하지 않고, 동일 Evidence Snapshot에서 형제 projection을 생성한다.
---

# Evidence Snapshot Consistency Guard 계획

## 1. 목적

이 계획의 목적은 화면, Report, Closed-loop, AI 요약이 서로 다른 시점의 판단 근거를 소비하는 문제를
막는 것이다.

단, guard와 retry를 먼저 구현하지 않는다. 먼저 현재 코드에서 실제로 다른 시점의 근거를 소비할 수 있는
엣지케이스를 찾고, 재현 가능한 경우에만 Level 0 guard를 추가한다.

중요한 결정은 다음과 같다.

- `AssetDetailViewModel`은 UI용 read model이다.
- `Closed-loop Recommendation Input`은 ViewModel을 직접 소비하지 않는다.
- UI ViewModel, Report Projection, Recommendation Input, Agent Review Packet은 같은
  `Product Result / Evidence Snapshot`에서 파생되는 형제 projection이다.
- Closed-loop mutation 진입 전에는 `snapshot_basis` mismatch를 검증하고, 필요한 경우 1회 재조회 후
  재생성한다.

즉 목표는 “모든 소비자가 ViewModel을 먹는다”가 아니라 “모든 소비자가 같은 Evidence Snapshot을 기준으로
각자의 projection을 만든다”이다.

## 2. 용어 계약

| 이름 | 의미 | 저장/조합 성격 |
| --- | --- | --- |
| `EvidenceSnapshotBasis` | 같은 판단 근거에서 파생되었는지 비교하기 위한 최소 식별자 묶음 | 모든 projection에 포함되는 계약 |
| `EvidenceSnapshot` | Product Result Artifact와 Evidence Projection을 함께 읽은 신뢰 입력 | backend read/use-case 입력 |
| `AssetDetailViewModel` | UI 표시용 projection | 요청 시 조합 |
| `ReportProjection` | 보고서/증빙용 projection. ViewModel 표현을 일부 재사용할 수 있으나 provenance는 Evidence에서 가져온다 | 요청 시 조합 또는 후속 저장 가능 |
| `RecommendationInput` | Closed-loop 정책/승인 후보 생성 입력 | mutation 전 검증 대상 |
| `AgentReviewPacket` | LLM/AI 요약 입력용 read-only packet | 요청 시 조합 또는 후속 저장 가능 |

`Materialization`은 Product Result/Evidence 또는 Summary처럼 저장/조회 가능한 산출물로 굳히는 경우에만
사용한다. 현재 ViewModel composer 자체에는 사용하지 않는다.

## 3. 기준 흐름

```text
Prediction Result Batch
  -> Backend validation / promotion
  -> Product Result Artifact
  -> Evidence Projection
  -> EvidenceSnapshot
      -> AssetDetailViewModel -> UI
      -> ReportProjection / EvidencePackage -> Report
      -> RecommendationInput -> Closed-loop guard -> state transition
      -> AgentReviewPacket -> AgentReviewSummary
```

금지되는 흐름은 다음과 같다.

```text
Prediction Result Batch -> UI
Prediction Result Batch -> Closed-loop
AssetDetailViewModel -> Closed-loop RecommendationInput
AgentReviewSummary -> Closed-loop approval
```

## 4. EvidenceSnapshotBasis 계약

Level 0에서는 새 저장소를 크게 만들지 않고, projection들이 다음 식별자를 공유하도록 한다.

```text
EvidenceSnapshotBasis
- artifact_reference
- evidence_payload_reference 또는 evidence_ref
- asset_id
- event_id
- observed_at
- model_version
- dataset_version
- source_sha256
```

필수성:

- `AssetDetailViewModel`은 `snapshot_basis`를 노출한다.
- `RecommendationInput`은 `snapshot_basis`를 필수로 가진다.
- `AgentReviewPacket`은 `snapshot_basis` 또는 동일한 `source_refs`를 통해 같은 basis를 추적할 수 있어야 한다.
- Report는 ViewModel 문구를 재사용하더라도 `artifact_reference`와 `provenance`를 Evidence에서 유지한다.

## 5. Guard와 retry 정책

Closed-loop mutation entrypoint는 RecommendationInput을 받은 뒤 다음 순서로 검증한다.

```text
1. 요청에 포함된 snapshot_basis 확인
2. 현재 asset/event의 최신 EvidenceSnapshotBasis 재조회
3. basis match:
     - 정책 평가와 상태 전이 후보 생성 진행
4. basis mismatch:
     - 같은 Product Result/Evidence Snapshot 기준으로 RecommendationInput 1회 재생성
     - 재생성 후 재검증
5. 재검증 mismatch 또는 data_quality_hold:
     - 상태 전이 거부
     - stale_snapshot 또는 snapshot_mismatch 응답
```

retry는 최대 1회로 제한한다. 이 retry는 transport/idempotency retry와 다르다.

- `Idempotency-Key`: 같은 mutation 요청이 중복 적용되는 것을 막는다.
- `snapshot retry`: mutation 요청의 판단 근거가 현재 Evidence와 일치하는지 맞춰보는 절차다.

snapshot이 바뀌었다면 같은 승인 요청의 replay로 처리하지 않는다. 기존 요청은 stale 처리하고, 사용자가
새 판단 근거를 확인하도록 해야 한다.

## 6. 구현 단위

### U0. Edge case discovery

- **Status:** Implemented as a discovery regression. `tests/test_maintenance_loop_application.py::test_inspection_request_uses_current_server_projection_without_client_snapshot_guard` shows that Closed-loop correctly resolves lineage server-side, but it cannot compare that lineage with the UI snapshot the user saw because the command carries no client snapshot basis.
- **Goal:** ViewModel과 Closed-loop가 실제로 서로 다른 Product Result/Evidence 기준을 소비할 수 있는지 코드와 테스트로 확인한다.
- **Current Findings:**
  - `MaintenanceLoopService.request_inspection()`은 ViewModel을 직접 소비하지 않고 `EventEvidenceProjectionQueryPort.event_evidence_projection()`을 서버에서 조회한다.
  - `InspectionWorkOrderCreateRequest`는 `event_id`만 받으며, caller가 본 `artifact_reference`, `evidence_id`, `observed_at`, `dataset_version`, `source_sha256`는 받지 않는다.
  - Closed-loop `WorkOrderAuthorization`과 `OperationalRecommendedAction`은 `source_product_result_id`, `source_evidence_id`, `source_schema_version`, `source_policy_version`을 저장한다.
  - `AssetDetailViewModel.evidence`는 `artifact_id`, `evidence_payload_reference`, `model_version`, `dataset_version`, `source_kind`를 노출하지만 full `snapshot_basis`는 없다.
  - runtime `event_evidence_projection()`은 `artifact_id=event_id`로 단일 Product Result row를 조회하므로, event id가 artifact id로 고정된 경로에서는 단순 latest drift 가능성이 낮다.
- **Candidate Edges:**
  - UI가 오래된 `AssetDetailViewModel`을 본 뒤, 같은 asset의 새 Product Result가 만들어졌지만 Closed-loop 요청은 `event_id`만 보내는 경우.
  - Operations fixture 경로처럼 요청마다 artifact를 재계산하는 consumer가 있을 때, 같은 event/asset이라도 predictor/config/fallback 정책 변경으로 artifact content가 달라지는 경우.
  - Report가 ViewModel 표현을 재사용하는 동안 Closed-loop는 별도 Evidence Projection을 조회해, 사용자에게 보인 문구와 저장된 authorization lineage가 같은 basis인지 증명할 수 없는 경우.
  - event id가 artifact id가 아닌 legacy event id 또는 compatibility id로 들어오는 경로가 섞일 경우.
- **Non-Edges / Already Guarded:**
  - Closed-loop가 ViewModel-only 표시 필드를 직접 정책 입력으로 쓰는 경로는 현재 확인되지 않았다.
  - Maintenance는 caller-supplied lineage를 신뢰하지 않고 서버에서 Evidence Projection을 조회한다.
  - scope mismatch, event id mismatch, replay session mismatch, idempotency conflict는 기존 테스트가 이미 검증한다.
- **Verification:**
  - 현재 ViewModel과 Closed-loop projection의 lineage 필드가 어디까지 겹치는지 golden/assertion으로 기록한다.
  - stale UI scenario를 테스트로 만들 수 있는지 먼저 확인한다.
  - 재현되었으므로 U1 이후 guard는 future risk가 아니라 Level 0 구현 후보로 승격한다.

### U1. Snapshot basis 타입 추가

- **Status:** Implemented. `AssetDetailViewModel` and `AgentReviewPacket` now expose the same `snapshot_basis` object derived from Product Result/Evidence, and golden tests assert equality for the current Operations service path.
- **Goal:** Product Result/Evidence에서 공통 basis를 추출하는 작은 타입을 만든다.
- **Files:**
  - `systems/backend/app/diagnosis/evidence_projection.py`
  - `systems/backend/app/operations/asset_detail_view_model.py`
  - `systems/backend/app/operations/agent_review_packet.py`
  - `contracts/schemas/asset-detail-view-model.schema.json`
  - `contracts/schemas/agent-review-packet.schema.json`
  - `tests/test_asset_detail_view_model_contract.py`
  - `tests/test_agent_review_packet_golden.py`
- **Verification:**
  - GS-002/GS-004/GS-007 Agent Review Packet이 `snapshot_basis`를 포함한다.
  - `test_agent_review_packet_uses_same_snapshot_basis_as_view_model`이 ViewModel과 Agent Review Packet의 basis 동등성을 검증한다.
  - 현재 fixture 경로에서 `source_sha256`은 아직 null이며, U2/U3에서 mutation guard 입력으로 쓰기 전 결측 정책을 다시 확정한다.

### U2. RecommendationInput projection 추가

- **Status:** Not implemented. U1 exposed the common basis, and U3a introduced a command-side stale-view guard for inspection work-order requests before a dedicated RecommendationInput projection exists.
- **Goal:** Closed-loop가 ViewModel이 아니라 EvidenceSnapshot에서 별도 입력을 만들게 한다.
- **Files:**
  - `systems/backend/app/maintenance/service.py`
  - `systems/backend/app/operations/service.py`
  - `contracts/schemas/recommendation-input.schema.json`
  - `tests/test_operations.py`
- **Verification:**
  - RecommendationInput과 AssetDetailViewModel의 `snapshot_basis`가 동일하다.
  - ViewModel 표시 필드가 RecommendationInput의 필수 정책 입력으로 섞이지 않는다.

### U3. Closed-loop snapshot guard

- **Status:** Partially implemented for `InspectionWorkOrderCreateRequest`. The request may carry optional `snapshot_basis`; if supplied, non-empty fields must match the server-resolved Event Evidence Projection before an inspection work order is created.
- **Goal:** Closed-loop mutation 직전에 basis mismatch를 막는다.
- **Files:**
  - `systems/backend/app/maintenance/api_schema.py`
  - `systems/backend/app/maintenance/service.py`
  - `tests/test_maintenance_loop_application.py`
- **Verification:**
  - `test_inspection_request_accepts_matching_client_snapshot_basis` keeps the existing request path open when basis matches.
  - `test_inspection_request_rejects_stale_client_snapshot_basis` rejects stale basis with `snapshot_basis mismatch`.
  - reject 시 WorkOrder side effect count가 증가하지 않는다.

### U4. 1회 재조회/재생성 retry

- **Goal:** mismatch가 단순 stale read이면 최신 EvidenceSnapshot으로 RecommendationInput을 한 번 재생성한다.
- **Files:**
  - `systems/backend/app/maintenance/service.py`
  - `systems/backend/app/diagnosis/runtime_service.py`
  - `tests/test_operations.py`
- **Verification:**
  - 1회 재생성 후 match되면 진행한다.
  - 1회 후에도 mismatch면 reject한다.
  - data quality hold로 바뀌면 자동 승인/상태 전이를 진행하지 않는다.

### U5. Report/Agent Review sibling projection 검증

- **Goal:** Report와 Agent Review가 ViewModel 또는 Summary를 신뢰 원본으로 착각하지 않게 한다.
- **Files:**
  - `systems/backend/app/operations/agent_review_packet.py`
  - `systems/backend/app/operations/service.py`
  - `tests/test_agent_review_packet_golden.py`
  - `tests/test_operations.py`
- **Verification:**
  - AgentReviewPacket의 source refs가 ViewModel 표시값만이 아니라 Evidence/Product Result basis를 포함한다.
  - Report는 ViewModel 문구 재사용 여부와 별개로 Evidence provenance를 유지한다.

## 7. 최소 테스트 계약

Level 0에서 필요한 테스트는 다음 네 축이면 충분하다.

1. **Sibling derivation test**
   - 같은 event/asset에서 ViewModel과 RecommendationInput을 만들고 `snapshot_basis` 동등성을 검증한다.

2. **No ViewModel-to-Closed-loop test**
   - RecommendationInput 생성 함수가 ViewModel-only 필드를 요구하지 않는지 검증한다.

3. **Mismatch reject test**
   - stale `artifact_reference`나 `source_sha256`로 mutation을 시도하면 상태 전이가 일어나지 않는다.

4. **Single retry test**
   - stale basis mismatch가 1회 재조회로 해소되면 진행하고, 해소되지 않으면 reject한다.

## 8. 범위 제한

이번 계획에서 하지 않는 것:

- Kafka/Debezium 같은 운영 CDC 도입
- knowledge graph 전면 도입
- RAG 기반 SOP ingest pipeline 구현
- exactly-once delivery 보장
- ViewModel materialized table 생성
- Agent가 Closed-loop approval을 직접 실행하는 구조

이 계획은 하단 신뢰 경계의 Level 0 계약이다. KG/RAG/LangGraph는 이 계약이 지켜진 뒤, SOP/운영 도메인
탐색이 실제로 다중 hop 문제로 커질 때 도입 여부를 다시 판단한다.

## 9. 다음 결정

우선순위는 다음과 같다.

1. 현재 ViewModel, Report, Closed-loop가 소비하는 Product Result/Evidence lineage를 코드 경로로 추적한다.
2. 서로 다른 시점 snapshot을 쓸 수 있는 edge case를 테스트로 재현한다.
3. 재현되면 `EvidenceSnapshotBasis`를 `AssetDetailViewModel`과 RecommendationInput에 추가한다.
4. snapshot mismatch reject 테스트를 먼저 작성한다.
5. 1회 재조회 retry를 service 레벨에서 구현한다.
6. 재현되지 않으면 guard/retry는 future risk로 남기고 sibling projection 명명 계약만 유지한다.
