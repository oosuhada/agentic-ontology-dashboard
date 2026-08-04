# Phase 03 — V3.1 Compatibility Bridge and Ontology Materialization

> **완료 기록 — 재실행하지 않음.** 구현 커밋: `1a15af1`, V3.1 release contract
> 정합성 보강 커밋: `6534aa5`. 다음 실행 단계는 Phase 4다.

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

새 데이터 패키지는 읽기 전용으로 확인해줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1

V2 패키지는 backward compatibility 검증에 필요한 경우에만 읽기 전용으로 확인해.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v2

먼저 다음을 읽고 Phase 0~2가 현재 branch에 완료됐는지 확인해줘.

- docs/30-implementation/predictive-maintenance-canonical-v2-integration-plan.md
- docs/30-implementation/predictive-maintenance-canonical-v3-upgrade-plan.md
- Phase 0~2 prompt와 관련 커밋 `1aa0251`, `4b4d46f`, `01a4a9b`
- schemas/dataset-bundle-manifest.schema.json
- api/ontology_dashboard/adapters/bundle_models.py
- api/ontology_dashboard/adapters/predictive_maintenance_v2.py
- api/ontology_dashboard/adapters/postgresql_bundle_ingestion.py
- api/migrations/postgresql/0011_predictive_maintenance_domain_pack.sql
- tests/test_predictive_maintenance_bundle_contract.py
- tests/test_predictive_maintenance_bundle_adapter.py
- tests/test_predictive_maintenance_postgresql.py
- api/ontology_dashboard/ontology.py
- api/ontology_dashboard/ontology_service.py
- api/ontology_dashboard/postgresql_ontology_repository.py
- api/ontology_dashboard/datasets/projection.py
- api/ontology_dashboard/datasets/models.py
- api/ontology_dashboard/ontology_adapter.py
- 기존 WorkOrder, RiskEvent, MaintenanceAction, PredictionResult object/link 계약
- predictive_maintenance_canonical_v3.1/README.md
- predictive_maintenance_canonical_v3.1/SCHEMA.md
- predictive_maintenance_canonical_v3.1/RESULT_ARTIFACT_SCHEMA.md
- predictive_maintenance_canonical_v3.1/V3_1_CHANGELOG.md
- predictive_maintenance_canonical_v3.1/V3_1_RELEASE_VERIFICATION.md
- predictive_maintenance_canonical_v3.1/canonical/dataset/dataset_manifest.json
- predictive_maintenance_canonical_v3.1/canonical/model_outputs/model_contract.json
- predictive_maintenance_canonical_v3.1/canonical/validation/package_validation.json

git status --short --branch, git log -7 --oneline, remote tracking을 확인하고 다른
세션의 미커밋 변경을 보존해. 현재 working tree의 web/vite.config.ts 등 이번 단계와
관계없는 변경을 수정·stage·commit하지 마.

이번 Phase는 두 Gate를 순서대로 완료해야 한다. Gate A가 통과하기 전에 Ontology
materialization을 시작하지 마.

## Gate A — V3.1 Compatibility Bridge

현재 V2 Adapter로 V3.1 manifest를 build하면 source contract의 다음 필드가
`extra_forbidden`으로 실패하는 상태를 먼저 재현해.

```text
cnc_ai4i_physical_relations
failure_modes_satisfy_sensor_conditions
asset_variability_policy
```

구현 범위:

1. V2/V3.1 source contract 호환
   - 기존 V2 필드는 계속 필수
   - 위 V3.1 필드를 version-aware optional field로 추가
   - 선언된 V3.1 값의 타입과 의미 검증
   - 알 수 없는 임의 필드는 계속 거부
   - V3.1 source contract 값이 bundle checksum canonicalization에 포함
   - 기존 V2 package의 bundle checksum과 validation regression 유지
2. V3.1 Result Artifact bundle role
   - role: `result_artifact`
   - path: `canonical/model_outputs/result_artifact.jsonl`
   - schema version: `result-artifact-v1.0`
   - V3.1에서는 필수, V2에서는 없는 것이 허용되는 version-aware role set
   - model_contract.output_sha256와 checksum 일치
   - 100개 asset coverage
   - artifact_id와 asset_id 유일성
   - prediction snapshot의 prediction_id/provenance 연결
   - status_grade, probability, confidence 범위
   - top_factors Top-3와 recommended_action 구조 검증
3. additive PostgreSQL migration
   - 이미 적용된 `0011_predictive_maintenance_domain_pack.sql`을 수정하지 않기
   - 새 migration 번호 사용
   - `pm_result_artifacts` 또는 동일 책임의 typed table/repository 추가
   - organization/project/workspace/dataset_version scope, RLS, PK/FK/index
   - top_factors, recommended_action, provenance는 계약을 보존하는 JSONB 가능
   - 핵심 조회 필드 asset/status/probability/time은 typed column 유지
4. V3.1 COPY ingestion
   - 기존 V2 Dataset Version을 삭제하거나 덮어쓰지 않기
   - V3.1 `canonical-ai4i-physics-v3.1`을 새 checksum의 새 Dataset Version으로 적재
   - package validation summary와 SHA-256을 ingestion/governance metadata에 기록하되
     `canonical/validation` 파일을 runtime source fact로 취급하지 않기
   - 같은 V3.1 bundle 재실행은 idempotent
5. V3.1 row-count parity
   - assets 100
   - relations 80
   - compressor observations 86,400
   - CNC observations 345,600
   - production cycles 170,875
   - maintenance events 790
   - prediction snapshots 100
   - prediction factors 300
   - prediction timeline 68,208
   - result artifacts 100

Gate A 완료 조건:

- V3.1 manifest build와 bundle validation 성공
- V2 package validation regression 성공
- V2와 V3.1이 서로 다른 Dataset Version과 checksum을 가짐
- V2 row가 변경되지 않음
- V3.1 Result Artifact 100건이 DB에 적재됨
- package validation의 `tool_wear_continuity.pass=true`
- `running_reset_count=0`, replacement/reset 731/731 정렬이 ingestion artifact에 기록됨
- evaluation truth와 experiment hidden truth는 runtime role에 없음
- transaction 중간 실패 시 V3.1 partial ready가 없음

## Gate B — V3.1 Ontology Materialization

Gate A로 적재한 V3.1 Dataset Version에서 업무 의미가 있는 Ontology Object와 Link를
materialize해.

구현 범위:

1. predictive maintenance domain pack
   - Site
   - ProductionCell
   - Equipment
   - RiskAssessment 또는 기존 RiskEvent
   - 기존 canonical PredictionResult
   - WorkOrder
   - MaintenanceAction
   - 필요한 범위의 ProductionCycle
2. Result Artifact 우선 mapping
   - latest risk/status/action/factor는 `pm_result_artifacts`를 우선 소비
   - PredictionResult identity와 provenance를 연결
   - `prediction_task=binary_failure_within_horizon` 보존
   - `predicted_failure_type`은 `failure_risk|no_significant_risk` 의미만 허용
   - PWF/HDF/OSF/TWF multiclass prediction처럼 materialize하지 않기
3. recommended action 의미
   - Result Artifact의 recommended_action은 정책 추천
   - 자동 승인, 자동 정지, 실제 WorkOrder 또는 MaintenanceAction으로 변환하지 않기
   - 실제 WorkOrder/MaintenanceAction은 canonical maintenance_event에서만 materialize
4. link types
   - site_contains_cell
   - cell_contains_equipment
   - equipment_supplies_air_to_equipment
   - equipment_has_risk_assessment 또는 기존 risk link
   - equipment_has_prediction_result
   - equipment_has_work_order
   - work_order_has_maintenance_action
   - 필요 시 equipment_completed_production_cycle
5. identity와 lineage
   - organization + project + workspace + dataset + dataset_version + object type + source identity
   - source_refs에 Dataset Version, role checksum, Result Artifact schema/model version 포함
   - V2/V3.1 object가 version scope 없이 충돌하지 않음
   - 같은 V3.1 version 재실행 시 object/link 중복 없음
6. AI4I metadata와 sensor evidence
   - AI4I 물리 계약은 Dataset Version/schema/profile metadata로 등록
   - query-time derived measure contract: power_w, temperature_gap_k, overstrain_load
   - 원시 10분 observation을 Ontology Object로 만들지 않기
   - asset/time-window 기반 registered source reference 생성
   - Risk/Prediction evidence에 selected summary와 factor provenance 연결
7. mapping approval
   - V3.1 기본 mapping draft
   - approved mapping만 materialization/projection 가능
   - mapping 변경과 reprojection 상태 기록
8. API surface
   - Ontology Explorer가 V3.1 Project/Workspace/Dataset Version scope로 query/traversal
   - V2와 V3.1 Dataset Version을 명시적으로 선택 가능

중요:

- `canonical/evaluation_truth`의 failure_mode, condition_variant, failure timestamp를
  runtime object property/source ref/evidence로 노출하지 마.
- optional experiment와 hidden_truth를 production Ontology에 materialize하지 마.
- `SUPPLIES_AIR_TO`는 topology이며 causal edge가 아니다.
- 432,000개 sensor row와 68,208개 prediction timeline point를 ontology_objects로
  만들지 마.

필수 검증:

- V3.1 manifest strict compatibility test
- V2 manifest/checksum regression test
- result artifact 누락/checksum/schema/cross-file negative tests
- additive migration 적용과 재적용 안전성
- V3.1 ingestion row count parity, RLS, idempotency, rollback
- tool-wear continuity 결과가 ingestion/governance metadata에 보존되는 test
- Site → Cell → Equipment traversal
- Compressor → SUPPLIES_AIR_TO → CNC traversal
- Equipment → RiskAssessment/PredictionResult traversal
- Equipment → WorkOrder → MaintenanceAction traversal
- Result Artifact recommended_action이 WorkOrder를 자동 생성하지 않는 negative test
- binary predicted type이 AI4I failure mode로 변환되지 않는 negative test
- object/link가 V3.1 Dataset Version lineage를 가짐
- 같은 V3.1 Dataset Version 재실행 시 object/link count 불변
- V2/V3.1 object identity가 version scope로 분리됨
- 다른 project/workspace에서 object 조회 불가
- raw sensor/timeline object가 생성되지 않음
- evaluation truth/hidden truth property/source ref가 노출되지 않음
- tests/test_predictive_maintenance_v3_compatibility.py
- tests/test_predictive_maintenance_projection.py 또는 명확히 분리된 ontology test
- 기존 ontology/project isolation targeted tests
- python scripts/preflight.py
- git diff --check

현재 단계에서 Neo4j write, replay API, Dashboard UI는 구현하지 마.

검증 완료 후 이번 단계 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: upgrade predictive maintenance v3.1 materialization"
- git push origin HEAD

push 실패 시 이력 재작성 없이 오류와 commit hash를 보고해.

마지막 보고:

- V3.1 compatibility blocker와 해결 방식
- V2/V3.1 Dataset Version identity와 bundle checksum
- V3.1 table별 실제 row count
- Result Artifact 저장·mapping 계약
- object/link type과 실제 count
- recommended action과 실제 WorkOrder 분리 증거
- raw observation/timeline 비-materialization 증거
- truth/hidden-truth 비노출 증거
- 변경 파일, migration 번호, 테스트 결과
- commit hash와 push 결과
- Phase 4 graph projection payload 준비 상태
````
