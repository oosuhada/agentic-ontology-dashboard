---
title: Product Result Evidence Materialization Plan
status: draft
created: 2026-08-29
type: plan
scope: Generator 산출물에서 Product Result Artifact, Evidence Projection, AssetDetailViewModel, 화면까지 이어지는 검증/승격/소비 경계
positioning: AI 솔루션 엔지니어 관점의 제품화/통합 계획. DB 플랫폼 전체 재설계가 아니라, AI 결과가 업무 화면에서 신뢰 가능한 판단 근거로 쓰이도록 하는 최소 경계 정리.
---

# Product Result / Evidence 신뢰 경계 구현 계획

## 1. 목적

현재 프로젝트의 제품 흐름은 다음 경계를 유지한다.

```text
Generator 산출
  -> Backend Diagnosis 검증/승격
  -> Product Result Artifact
  -> Evidence Projection / Evidence Package
  -> AssetDetailViewModel
  -> 화면
```

이 계획의 목적은 Spring의 `@Transactional` / `@EventListener`에 해당하는 책임을 FastAPI 코드 구조에 맞게 해석하고, AI 예측 결과가 화면에 표시되기 전 어떤 검증 경계를 통과해야 하는지 명시하는 것이다.

핵심은 프레임워크 이벤트 리스너를 새로 붙이는 것이 아니다. Generator의 raw 산출물을 바로 화면이나 Closed-loop 조치로 연결하지 않고, Backend Diagnosis가 검증 가능한 Product Result와 Evidence로 승격한 뒤 ViewModel을 통해 소비하게 하는 것이다.

이 문서는 AI 요약 전용 파이프라인이 아니다. Product Result/Evidence materialization은 UI, Report, Closed-loop, AI consumer가 공통으로 읽는 하단 신뢰 경계다. `docs/plans/ai-workflow/2026-08-29-001-ai-context-orchestration-adapter-plan.md`는 이 경계 위에서 adapter 기반 맥락 수집, SOP/온톨로지 탐색, LLM 요약, optional watcher materialization을 다룬다.

## 1.1 AI 솔루션 엔지니어 관점의 적정 범위

이 계획은 다음 역량을 보여주는 범위로 제한한다.

- AI/ML 결과를 실제 업무 화면과 의사결정 흐름에 연결한다.
- raw prediction과 product-facing 판단 결과를 분리한다.
- checksum, schema, lineage, validation status로 데이터 신뢰성을 설명한다.
- 화면은 raw payload가 아니라 typed ViewModel을 소비하게 한다.
- 결측/근거 부족은 정상값으로 보정하지 않고 사용자에게 드러낸다.

반대로 다음은 전면 구현 범위로 주장하지 않는다.

- 대규모 DB 플랫폼 재설계
- 범용 ingestion framework 구축
- Kafka/Debezium 기반 CDC 운영 전환
- exactly-once delivery 보장
- 모든 read source의 완전 동일 시점 snapshot 보장

따라서 이 문서는 “DB 트랜잭션 전문가의 시스템 재설계”가 아니라 “AI 결과를 업무 사용자가 신뢰할 수 있는 제품 화면으로 전달하기 위한 통합 경계 설계”로 읽혀야 한다.

## 1.2 JD 대응 관점의 개선사항

최근 AI Solutions Engineer / AI Data Integration / MLOps 계열 JD는 공통적으로 데이터 파이프라인, API 통합, 운영화, 모니터링, 이해관계자 커뮤니케이션을 요구한다. 이 계획은 이를 대규모 플랫폼 구현으로 확장하지 않고, 제조 AI 대시보드의 현재 범위에서 다음처럼 적용한다.

| JD 요구 | 우리 프로젝트 적용 | 과하지 않게 제한한 범위 |
| --- | --- | --- |
| Data Pipeline | Generator raw 산출물을 Backend 검증 후 Product Result/Evidence로 승격한다. | 범용 ETL 플랫폼이나 대규모 ingestion framework 구축은 제외한다. |
| API Integration | 화면은 raw batch가 아니라 `AssetDetailViewModel` API를 소비하고, Closed-loop는 Product Result/Evidence를 기준으로 진입한다. | 프론트엔드가 raw JSONL, raw score, fixture를 직접 조합하지 않는다. |
| MLOps / LLMOps | `model_version`, `dataset_version`, `source_sha256`, `evidence_payload_reference`로 어떤 모델/데이터/근거가 화면 판단에 쓰였는지 추적한다. | 모델 학습 플랫폼, registry, 배포 자동화 전체를 재구축하지 않는다. |
| Operational Monitoring | `validation_status`, `rejection_reason`, `data_status`, `evidence.gaps`, fallback/unavailable reason으로 운영 상태를 드러낸다. | Prometheus/Grafana 같은 full observability stack 구축은 후속 범위로 둔다. |
| Stakeholder Communication | 확률/feature 기여도를 그대로 노출하지 않고 위험도, 확인 이유, 권장 조치, 근거 부족 상태로 화면 언어화한다. | 내부 DB/outbox/idempotency 용어를 사용자 화면의 주 메시지로 노출하지 않는다. |

따라서 외부 설명에서는 “DB 적재 파이프라인을 크게 설계했다”보다 다음 메시지를 우선한다.

```text
AI 예측 결과가 업무 화면과 조치 흐름에 들어가기 전, 데이터/모델/근거 lineage를 검증하고 사용자가 이해할 수 있는 ViewModel로 전달하는 통합 경계를 설계했다.
```

## 2. 현재 코드 근거

### 2.1 Product Result Artifact 생성

현재 Product Result Artifact 생성 진입점은 `systems/backend/app/diagnosis/evidence.py`의 `build_product_result_artifact()`다.

이 함수는 다음을 수행한다.

- predictor 실행
- `failure_probability`, `predicted_failure_type`, `status_grade`, `top_factors` 산출
- `recommended_action` 산출
- `evidence_payload` 생성
- `provenance.evidence_payload_reference` 기록
- Product Result Artifact schema 검증

즉 Product Result의 판단값과 Evidence payload는 이미 같은 producer 흐름에서 생성된다.

### 2.2 Evidence Projection

현재 Event Evidence Projection은 `systems/backend/app/diagnosis/evidence_projection.py`의 `product_result_artifact_to_event_evidence_projection()`가 담당한다.

이 함수는 Product Result Artifact를 입력으로 받아 다음 화면/보고서용 구조를 만든다.

- `artifact_reference`
- `assessment`
- `report_projection`
- `provenance`
- `limitations`

또한 `evaluation_truth`, `hidden_truth` 같은 평가 전용 필드를 제거하고, `provenance.canonical_source_mutated=false`를 요구한다.

### 2.3 Runtime Result 조회

`systems/backend/app/diagnosis/runtime_service.py`는 저장된 runtime row를 `GovernedProductResult`로 복원한다. 특히 `_stored_producer_artifact()`는 row의 `prediction_result_payload` 안에 `evidence_payload`가 있는지 확인하고 Product Result Artifact schema를 다시 검증한다.

`event_evidence_projection()`은 저장된 Product Result Artifact를 다시 Evidence Projection으로 변환해 Maintenance나 화면에서 읽을 수 있는 canonical evidence를 만든다.

### 2.4 AssetDetailViewModel 조합

`systems/backend/app/operations/asset_detail_view_model.py`의 `AssetDetailViewModelService.detail_view()`는 다음 read source를 모아 `compose_asset_detail_view_model()`에 넘긴다.

- asset summary
- latest result artifact
- feature series
- runtime prediction history
- equipment history
- data status

composer는 raw gen_data 파일이나 raw Generator batch를 직접 읽지 않는다. `result_artifact.evidence_payload`를 근거로 화면용 `risk`, `features`, `evidence.gaps`, `review_priority`, `inspection_targets` 등을 만든다.

### 2.5 Closed-loop의 기존 Transactional Outbox 패턴

`systems/backend/app/infra/db/maintenance_repository.py`는 Closed-loop mutation에서 이미 트랜잭션 경계를 구현한다.

대표 흐름은 다음과 같다.

```text
BEGIN IMMEDIATE
  -> idempotency reserve
  -> 상태 전이 검증
  -> work_order / maintenance_action 갱신
  -> activity 기록
  -> transactional_outbox insert
  -> idempotency finish
COMMIT
```

이 패턴은 Product Result / Evidence 저장에도 참고할 수 있다. 단, 화면용 ViewModel 조회에는 그대로 적용하지 않는다. AI 솔루션 엔지니어 관점에서는 이 패턴을 상세 구현 자체보다 “상태 변경과 후속 이벤트를 분리해 신뢰성을 확보한 예시”로 설명하는 것이 적절하다.

## 3. 이전 구조와 비교

### 이전 구조

이전 구조는 Product Result Artifact 생성, Evidence Projection, ViewModel composition이 각자 존재하지만, “Product Result가 Evidence와 함께 원자적으로 materialize 되었다”는 저장 경계가 명시적으로 분리되어 있지 않다.

```text
runtime row
  -> Product Result 복원
  -> producer artifact 검증
  -> Evidence Projection 생성
  -> ViewModel 조합
```

장점:

- 읽기 경로가 단순하다.
- fixture/runtime compatibility를 유지하기 쉽다.
- ViewModel이 raw source를 직접 읽지 않는 원칙은 이미 지켜진다.

문제:

- Product Result 저장과 Evidence 저장/참조의 원자성 경계가 코드 이름으로 드러나지 않는다.
- Generator batch 수신, 검증, 승격, Product Result 생성, Evidence 생성, latest index 갱신이 하나의 명확한 use case로 묶여 있지 않다.
- 실패 시 “검증 실패”, “승격 실패”, “ViewModel 조합 실패”, “화면 표시 실패”를 운영적으로 구분하기 어렵다.

### 제안 구조

Product Result 승격 단위를 별도 service와 repository method로 분리하는 것을 제안한다. 다만 첫 구현은 DB 내부 구조를 크게 바꾸는 것이 아니라, 현재 runtime/evidence 흐름에 검증과 상태 기록을 추가하는 얇은 gate로 시작한다.

```text
Generator Prediction Batch / Runtime Prediction Row
  -> ProductResultMaterializationService
      -> schema / scope / lineage / checksum 검증
      -> build_product_result_artifact()
      -> product_result_artifact_to_event_evidence_projection()
      -> ProductResultRepository.materialize_product_result()
  -> AssetDetailViewModel read path
  -> UI
```

변경의 핵심은 ViewModel을 저장하거나 event listener로 갱신하는 것이 아니다. Product Result와 Evidence가 생성되는 지점에 검증 가능한 승격 경계를 두고, 저장 원자성은 필요한 범위에서만 적용하는 것이다.

## 4. 구현 계획

구현은 한 번에 DB 플랫폼을 바꾸지 않고, AI 제품화에 필요한 최소 단위부터 진행한다.

```text
1차: 검증 상태와 lineage를 명시한다.
2차: Product Result / Evidence 승격 단위를 service로 분리한다.
3차: 저장 원자성과 outbox는 필요한 경우에만 적용한다.
4차: 화면은 ViewModel 소비 경계를 유지한다.
```

### Step 1. 승격 command/result 타입 추가

위치 후보:

- `systems/backend/app/diagnosis/materialization.py`
- 또는 `systems/backend/app/diagnosis/materialization_service.py`

추가 타입:

```python
class ProductResultMaterializationCommand(BaseModel):
    organization_id: str
    project_id: str
    workspace_id: str
    dataset_version_id: str
    source_event_id: str
    source_payload_sha256: str
    source_contract: str
    source_payload: dict[str, Any]
    request_fingerprint: str


class ProductResultMaterializationResult(BaseModel):
    artifact_id: str
    evidence_id: str
    event_id: str
    materialized: bool
    replayed: bool
    outbox_event_id: str | None = None
```

핵심 필드는 `artifact_id`, `evidence_id`, `source_payload_sha256`, `request_fingerprint`다. 이 값들은 사용자가 보는 결과가 어떤 입력에서 왔는지 설명하기 위한 근거이며, 재처리/conflict 판단에도 사용할 수 있다.

### Step 2. ProductResultMaterializationService 추가

책임:

1. Generator batch 또는 runtime prediction row를 입력으로 받는다.
2. contract, scope, lineage, timestamp, checksum을 검증한다.
3. `build_product_result_artifact()`로 Product Result Artifact를 만든다.
4. `product_result_artifact_to_event_evidence_projection()`으로 화면/Closed-loop 소비 가능성을 검증한다.
5. repository에 저장을 위임한다.

의사 코드:

```python
class ProductResultMaterializationService:
    def materialize(self, command: ProductResultMaterializationCommand) -> ProductResultMaterializationResult:
        self._validate_source(command)

        artifact = build_product_result_artifact(
            command.source_payload,
            predictor=self.predictor,
            context_provider=self.context_provider,
        )
        projection = product_result_artifact_to_event_evidence_projection(artifact)

        return self.repository.materialize_product_result(
            command=command,
            artifact=artifact,
            evidence_projection=projection,
        )
```

### Step 3. Diagnosis repository에 저장 경계 추가

위치 후보:

- `systems/backend/app/infra/db/diagnosis_runtime_repository.py`

추가 메서드:

```python
def materialize_product_result(
    self,
    *,
    command: ProductResultMaterializationCommand,
    artifact: dict[str, Any],
    evidence_projection: dict[str, Any],
) -> ProductResultMaterializationResult:
    ...
```

필요한 경우 한 트랜잭션에서 묶을 항목:

- Product Result Artifact payload 저장
- Evidence payload 또는 Evidence Projection reference 저장
- latest result index 갱신
- materialization audit/activity 저장
- source fingerprint record 저장
- 후속 projection이 필요한 경우 `transactional_outbox` 기록

의사 코드:

```python
with self._connection(command.organization_id, command.project_id) as connection:
    with connection.transaction():
        existing = self._find_materialization(
            connection,
            source_event_id=command.source_event_id,
            source_payload_sha256=command.source_payload_sha256,
        )
        if existing:
            return self._replay_or_conflict(existing, command.request_fingerprint)

        self._insert_product_result_artifact(connection, artifact)
        self._insert_evidence_projection(connection, evidence_projection)
        self._upsert_latest_result_index(connection, artifact)
        outbox_event_id = self._enqueue_product_result_materialized(...)  # optional
        return ProductResultMaterializationResult(...)
```

### Step 4. Outbox event는 후속 처리용으로만 제한

Event type 후보:

```text
diagnosis.product_result.materialized
```

payload 후보:

```json
{
  "event_type": "diagnosis.product_result.materialized",
  "artifact_id": "RESULT#...",
  "event_id": "EVT-RESULT#...",
  "evidence_id": "EVD-EVT-RESULT#...",
  "asset_id": "CNC-S01-L04-03",
  "dataset_version_id": "canonical-ai4i-physics-v3.1",
  "observed_at": "2026-08-29T00:00:00+09:00",
  "source_payload_sha256": "...",
  "evidence_payload_reference": "..."
}
```

이 event는 UI를 직접 갱신하기 위한 listener가 아니다. 검색 인덱스, 집계, audit, 외부 projection이 나중에 필요해질 때 안정적으로 소비할 수 있도록 남기는 후속 처리 신호다.

1차 구현에서는 outbox를 반드시 추가하지 않는다. Product Result/Evidence 저장 경계와 화면 소비 경계가 먼저 안정화된 뒤, 후속 처리 요구가 생기면 적용한다.

### Step 5. Runtime service 연결

`PredictiveMaintenanceRuntimeService`의 현재 Product Result 복원 경로를 유지하되, 신규 ingest/promotion 경로에서는 `ProductResultMaterializationService`를 거치게 한다.

원칙:

- receive-only 단계는 Product Result를 만들지 않는다.
- validation 통과 후 promotion 단계에서만 Product Result Artifact/Evidence를 만든다.
- ViewModel/API는 promoted artifact만 읽는다.

### Step 6. AssetDetailViewModel 경계 유지

`AssetDetailViewModelService`와 `compose_asset_detail_view_model()`은 저장 대상이 아니다. 계속 read model composer로 둔다.

유지할 규칙:

- raw Generator batch를 읽지 않는다.
- raw JSONL을 파싱하지 않는다.
- missing context를 0/normal로 보정하지 않는다.
- `risk.status_grade`, `asset.criticality`, `review_priority`를 섞지 않는다.
- unavailable 값은 `null`, `gap`, `warning`, `근거 부족`으로 표현한다.

## 5. 개선점

### 5.1 AI 결과의 제품 신뢰 경계 명확화

raw prediction이 곧바로 화면의 판단값이 되지 않는다. 검증된 Product Result와 Evidence를 거쳐 화면에 전달되므로, 사용자가 보는 위험도와 권장 조치의 출처를 설명하기 쉬워진다.

### 5.2 원자성 향상

Product Result만 저장되고 Evidence가 빠지는 상태, 또는 Evidence는 있는데 latest index가 갱신되지 않는 상태를 줄일 수 있다.

### 5.3 실패 원인 분리

다음 실패를 운영적으로 구분할 수 있다.

- source contract validation 실패
- lineage/checksum/scope mismatch
- Product Result Artifact 생성 실패
- Evidence Projection 생성 실패
- DB materialization 실패
- outbox enqueue 실패
- ViewModel composition 실패

단, 포트폴리오/면접에서는 모든 내부 failure mode를 나열하기보다 “검증 실패와 화면 표시 실패를 구분했다” 정도로 압축한다.

### 5.4 화면 신뢰성 향상

화면은 promoted Product Result와 typed ViewModel만 소비한다. 따라서 frontend가 raw source를 조합하거나 없는 값을 임의로 만드는 위험이 줄어든다.

### 5.5 Closed-loop 연결 안정성 향상

Closed-loop는 raw score나 Generator batch가 아니라 Product Result/Evidence/RecommendationDecision을 기준으로 움직인다. Materialization boundary가 명확하면 작업 요청/승인/정비 mutation의 source lineage도 더 안정적으로 검증할 수 있다.

### 5.6 확장성 확보

`diagnosis.product_result.materialized` outbox event를 기준으로 다음 확장이 가능하다.

- 검색 인덱스 갱신
- role-specific aggregate projection
- report cache invalidation
- audit timeline
- 운영 알림

## 6. 한계

### 6.1 직무 관점에서 과도한 구현으로 보일 수 있다

`transactional_outbox`, `advisory lock`, `dead-letter`, `latest index`를 모두 전면에 내세우면 AI 솔루션 엔지니어보다 백엔드 플랫폼 엔지니어 포지션으로 보일 수 있다. 외부 설명에서는 DB 내부 세부보다 “AI 결과가 업무 화면에 도달하기 전 검증과 근거 경계를 둔 것”을 중심으로 말한다.

### 6.2 Exactly-once 보장은 아니다

Outbox는 at-least-once delivery에 가깝다. 중복 소비 가능성을 전제로 consumer idempotency와 delivery log가 필요하다. 운영 문서나 PR 설명에서 exactly-once라고 주장하면 안 된다.

### 6.3 ViewModel consistency는 snapshot 설계가 필요하다

Product Result/Evidence 저장을 원자화해도, ViewModel은 feature history, equipment history, maintenance context 같은 여러 read source를 조합한다. 따라서 완전한 동일 시점 snapshot을 보장하려면 별도의 `snapshot_id` 또는 `as_of` 기준이 필요하다.

### 6.4 receive-only와 promotion은 분리해야 한다

Generator batch를 받는 즉시 Product Result를 만들면 raw handoff와 product judgment가 섞인다. 첫 단계는 receive-only validation으로 두고, promotion은 별도 gate로 두는 것이 안전하다.

### 6.5 기존 runtime compatibility를 깨면 안 된다

현재 fixture/demo/runtime 경로는 `prediction_snapshot_compatibility`와 `result_artifact`를 모두 다룬다. 신규 materialization 도입 시 기존 demo 화면과 회귀 fixture를 깨지 않도록 adapter를 additive하게 붙여야 한다.

### 6.6 Frontend 문제를 모두 해결하지는 않는다

이 계획은 Backend materialization 경계 계획이다. 화면의 loading/empty/error/stale/permission/fallback 상태 설계, polling/refetch 전략, 사용자 문구는 별도 UI 작업으로 남는다.

### 6.7 PR #142/#143과의 병렬 작업 경계

현재 열린 PR #142와 PR #143은 Maintenance/Closed-loop 쪽의 비용 지원 흐름을 다룬다.

- PR #142: `maintenance-cost-scenario-v1.0` 계약, Maintenance 비용 시나리오 schema/model/test
- PR #143: `TOOL_REPLACEMENT` 결정론적 비용 계산기

이 materialization 계획은 Diagnosis/Product Result/Evidence 승격 경계를 다루므로 직접 파일 충돌 가능성은 낮다. 다만 세 PR은 모두 “Closed-loop가 어떤 근거를 신뢰하고 소비하는가”라는 상위 제품 경계에서 맞닿는다.

따라서 이 계획의 구현 PR은 다음 파일/책임을 건드리지 않는다.

- `contracts/schemas/maintenance-cost-scenario.schema.json`
- `systems/backend/app/maintenance/cost_analysis_schema.py`
- `systems/backend/app/maintenance/cost_calculator.py`
- 비용 option 선택, `TOOL_REPLACEMENT` cost input mapping, Operations manual Recommendation lineage

반대로 이 계획이 소유하는 범위는 다음으로 제한한다.

- Diagnosis Product Result Artifact 생성/검증 경계
- Event Evidence Projection 생성/검증 경계
- receive-only와 promotion/materialized 상태 용어
- Product Result/Evidence가 ViewModel, Report, Agent Review, Closed-loop guard에서 같은 lineage로 소비될 수 있도록 하는 하단 신뢰 경계

PR #142/#143이 머지되면, 비용 계산 입력은 이 materialization 결과를 직접 mutation source로 쓰지 않고 별도 `maintenance-cost-scenario` input adapter에서 읽는다. 즉 Product Result/Evidence는 “근거 source”이고, 비용 계산 결과는 “read-only decision support”이며, 둘 다 WorkOrder/Action을 자동 생성하지 않는다.

#### Closed-loop 담당자 작업요청 코멘트

```md
PR #142/#143과 현재 Product Result/Evidence materialization 작업의 경계를 맞추기 위한 확인 요청입니다.

제가 진행할 materialization 작업은 `systems/backend/app/diagnosis` 중심으로 Generator/Runtime 결과를 Product Result Artifact + Event Evidence Projection으로 승격하는 하단 신뢰 경계를 만드는 범위로 제한하겠습니다.

PR #142/#143의 Maintenance 비용 시나리오/TOOL_REPLACEMENT 계산기 파일은 건드리지 않겠습니다.

확인 부탁드릴 경계는 세 가지입니다.

1. Cost Scenario/Calculator는 Product Result/Evidence를 직접 mutation source로 보지 않고, 별도 input adapter를 통해 read-only 근거로만 소비한다.
2. `asset_id == equipment_id` invariant는 Cost Scenario 쪽 계약을 존중하고, materialization에서는 Diagnosis 정본 asset lineage를 훼손하지 않는다.
3. WorkOrder/Action 생성은 계속 Closed-loop command 경계가 소유하며, Product Result materialized event나 Evidence Projection만으로 자동 생성하지 않는다.

이 기준이면 PR #142/#143과 병렬 진행해도 파일 충돌은 작고, 머지 후에는 Cost input adapter를 붙이는 후속 PR로 연결할 수 있을 것 같습니다.
```

## 7. 검증 계획

### Unit / Contract

- `build_product_result_artifact()`가 `evidence_payload`와 `evidence_payload_reference`를 포함하는지 검증
- `product_result_artifact_to_event_evidence_projection()`이 Product Result Artifact만 입력으로 받는지 검증
- hidden/evaluation-only field가 projection에 남지 않는지 검증
- `failure_probability`, `status_grade`, `top_factors`, `recommended_action` ownership이 Diagnosis에 유지되는지 검증

### Repository

- Product Result + Evidence Projection + latest index가 필요한 저장 경계 안에서 함께 처리되는지 검증
- outbox를 추가하는 경우 insert 실패 시 Product Result/Evidence 저장도 rollback 되는지 검증
- 같은 `source_event_id + source_payload_sha256` 재처리는 replay 처리되는지 검증
- 같은 source event에 다른 payload hash가 오면 conflict 처리되는지 검증

### Service

- invalid source contract는 Product Result를 만들지 않는지 검증
- receive-only 상태에서는 `product_result_created=false`인지 검증
- promotion 성공 시 `product_result_created=true`와 artifact/evidence id가 반환되는지 검증

### API / ViewModel

- AssetDetailViewModel이 materialized Product Result Artifact만 소비하는지 검증
- Evidence gap이 missing context를 0/normal로 보정하지 않는지 검증
- frontend adapter가 raw Generator batch나 raw JSONL을 직접 읽지 않는지 검증

## 8. 단계별 PR 단위

### PR 1. 신뢰 경계 contract skeleton

- command/result 타입 추가
- repository port 추가
- receive-only와 promotion 상태 용어 정리
- contract test 추가

### PR 2. Product Result / Evidence 저장 경계

- diagnosis repository에 `materialize_product_result()` 추가 또는 기존 저장 경로 wrapping
- Product Result/Evidence/latest pointer 저장 경계 정리
- source fingerprint conflict 처리
- rollback 테스트 추가

### PR 3. Runtime promotion service 연결

- `ProductResultMaterializationService` 추가
- runtime service 또는 inbox promotion path 연결
- 기존 fixture/demo compatibility 유지

### PR 4. ViewModel/API 회귀 정리

- AssetDetailViewModel이 promoted artifact를 기준으로 읽는지 테스트
- missing evidence/context 표시 회귀 테스트
- 화면 raw-source 미소비 검증

### 후속 후보. Outbox / projection 확장

- `diagnosis.product_result.materialized` event 추가
- report cache invalidation 또는 aggregate projection 연결
- consumer idempotency와 delivery log 검증

이 단계는 처음부터 포함하지 않는다. 실제 후속 소비자가 생긴 뒤 별도 PR로 다룬다.

## 9. 최종 원칙

이 파이프라인에서 transaction boundary는 화면 갱신을 위한 장치가 아니라 Product Result와 Evidence의 신뢰 경계를 지키는 장치다.

```text
저장/승격:
  Product Result + Evidence + lineage + outbox를 원자화한다.

조회/화면:
  AssetDetailViewModel composer가 canonical read source를 조합한다.

후속 조치:
  Closed-loop mutation만 Idempotency-Key와 transactional outbox를 사용한다.
```

따라서 구현의 최종 목표는 “이벤트 리스너 기반 자동 반응”이 아니라 “제품 판단 산출물의 검증 가능한 승격과 화면 소비 경계”를 만드는 것이다.

외부 설명에서는 다음 한 문장으로 압축한다.

```text
AI 예측 결과를 바로 화면에 표시하지 않고, 검증 가능한 Product Result와 Evidence로 승격한 뒤 ViewModel을 통해 전달해 현장 사용자가 위험도와 조치 근거를 추적할 수 있게 했다.
```
