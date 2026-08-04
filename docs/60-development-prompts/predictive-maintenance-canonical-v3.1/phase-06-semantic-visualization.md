# Phase 06 — AI4I-Aware Semantic Visualization Planner

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

V3.1 schema와 Result Artifact 계약을 읽기 전용으로 확인해줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1

먼저 다음을 읽어줘.

- docs/30-implementation/predictive-maintenance-canonical-v3-upgrade-plan.md
- docs/40-ui-ux/plans/chart-intelligence-color-system-uiux-plan.md
- predictive_maintenance_canonical_v3.1/SCHEMA.md
- predictive_maintenance_canonical_v3.1/RESULT_ARTIFACT_SCHEMA.md
- predictive_maintenance_canonical_v3.1/canonical/dataset/dataset_manifest.json의 ai4i_contract
- V3.1 Dataset Version의 release_gates, Result Artifact provenance, graph readiness
- api/ontology_dashboard/visualizations/models.py
- api/ontology_dashboard/visualizations/profiler.py
- api/ontology_dashboard/visualizations/recommender.py
- api/ontology_dashboard/planner/models.py
- api/ontology_dashboard/planner/service.py
- api/ontology_dashboard/dashboard_service.py
- web/src/features/dashboard/visualization/
- Phase 3와 Phase 5의 Result Artifact/aggregate/time-window query API

git status --short --branch, 최근 커밋, remote tracking을 확인하고 다른 세션의
미커밋 변경을 보존해. 현재 단계 관련 파일만 stage해.

이번 목표는 row shape만 보는 추천을 넘어, V3.1의 AI4I 물리 의미·단위·grain,
Result Artifact 의미, 사용자 목적에 따라 안전한 typed query와 chart를 선택하는
Semantic Visualization Planner를 구현하는 것이다.

구현 범위:

1. V3.1 Semantic Field Catalog
   - field_id
   - semantic_role: identifier/dimension/measure/timestamp/status/text
   - domain_concept
   - physical_type와 unit
   - allowed aggregations
   - grain/timezone
   - allowed filters와 cardinality constraints
   - source role과 Dataset Version
   - source version, bundle checksum, model version, Result Artifact schema version
   - graph readiness와 relational fallback capability
2. canonical sensor fields와 unit
   - air_temperature_k, process_temperature_k: K
   - rotational_speed_rpm: rpm
   - torque_nm: N·m
   - tool_wear_min: minute
   - compressor voltage/rotation/pressure/vibration의 현재 source unit metadata
3. allowlisted AI4I derived measures
   - power_w
   - temperature_gap_k
   - overstrain_load
   - product-type overstrain threshold/margin
   - derived expression을 server registry에 고정
   - LLM이 임의 수식이나 SQL을 만들 수 없음
4. Result Artifact semantic fields
   - failure_probability: probability measure
   - status_grade: ordered status dimension
   - confidence: probability-like measure
   - recommended_action.action
   - recommended_action.priority
   - top_factors feature/direction/contribution
   - model/schema/dataset provenance
   - release gate는 governance/status panel field로만 허용하고 일반 예측 measure로
     자동 집계하지 않음
5. prediction semantics guard
   - `predicted_failure_type`은 binary generic class
   - runtime에서 PWF/HDF/OSF/TWF category로 프로파일링하거나 chart dimension으로
     자동 변환하지 않음
   - evaluation truth 기반 failure mode chart는 기본 runtime planner에서 금지
6. Typed Visualization Query Plan
   - governed source/dataset/version/object type
   - intent
   - dimensions
   - measures와 aggregation
   - time field/grain/window
   - filters/order/limit
   - chart kind와 channel mapping
   - source/derived/result field provenance
7. validator/compiler
   - 존재하는 field만 허용
   - catalog에서 허용한 aggregation만 허용
   - AI4I derived expression allowlist
   - tenant/project/workspace/dataset-version scope
   - time range와 row/cardinality limit
   - parameterized PostgreSQL query
   - SQL 문자열을 LLM이 직접 생성하지 않음
8. recommendation scoring
   - intent, semantic role, unit, time grain, cardinality 반영
   - trend/comparison/distribution/relationship/composition/detail/summary
   - 기존 deterministic candidate registry 유지
9. LLM 경계
   - deterministic query/chart 후보의 재정렬과 설명만 허용
   - candidate 밖 field/chart/aggregation/derived expression 생성 불가
   - provider 실패 시 deterministic fallback
10. provenance와 override
   - 선택 이유, fallback 이유, query plan, Dataset Version, profile hash 표시
   - chart kind, field mapping, aggregation 변경
   - compatibility validation과 저장 가능한 setting
   - V2/V3.1 catalog version이 다르면 저장 설정을 자동 재사용하지 않고 migration
     또는 incompatibility 상태를 반환

필수 시나리오:

- risk timeline의 시간 추세 → line
- 설비별 현재 status/probability 비교 → sorted bar
- failure probability 분포 → histogram
- torque와 RPM 관계 → scatter
- process/air temperature gap 추세 → line 또는 area
- power threshold excursion → line + threshold annotation 또는 compatible range chart
- tool wear와 torque/overstrain 관계 → scatter
- site × status_grade 집중도 → heatmap
- recommended action priority composition → bar/stacked bar
- 세부 원본 확인 → table

다음 V2 시나리오는 V3.1 runtime 의미상 그대로 사용하지 마.

```text
site × PWF/HDF/OSF/TWF failure type heatmap
```

현재 모델은 failure-mode multiclass가 아니므로 위 chart는 evaluation truth를 노출하지
않는 한 runtime에서 만들 수 없다.

필수 검증:

- 존재하지 않는 field 거부
- 허용되지 않은 aggregation 거부
- allowlist 밖 derived expression 거부
- registry 밖 chart 거부
- LLM이 후보 밖 선택 시 deterministic fallback
- time range/row limit 초과 거부 또는 안전한 clamp
- 다른 Project/Dataset Version 참조 거부
- query 결과 profile과 chart channel compatibility
- unit이 다른 field를 잘못 합산하지 않는 test
- binary predicted type을 AI4I failure mode로 확장하지 않는 negative test
- evaluation truth field를 runtime plan에서 참조하지 못하는 negative test
- package validation의 `event_condition_details`, `condition_variant`, hidden truth를
  Semantic Field Catalog에 등록하지 않는 negative test
- tool-wear 731/731 정렬과 maintenance evidence 결과를 prediction accuracy chart로
  오해하지 않는 negative test
- graph degraded 상태에서 relational chart candidate가 계속 생성되는 test
- 사용자 override 저장·복원 contract
- tests/test_predictive_maintenance_visualization_planner.py
- 기존 visualization/planner/dashboard targeted tests
- frontend typecheck/build 중 관련 범위
- git diff --check

전체 screenshot baseline 갱신은 Phase 7에서 수행하므로 이번 단계에서는 불필요한
visual regression을 실행하지 마.

검증 완료 후 이번 단계 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: add ai4i semantic visualization planner"
- git push origin HEAD

push 실패 시 reset/rebase/force push 없이 오류와 commit hash를 보고해.

마지막 보고:

- V3.1 Semantic Field Catalog 구조
- AI4I derived measure와 unit 계약
- Result Artifact semantic mapping
- typed query plan과 SQL 안전 경계
- 목적별 추천 결과
- binary/failure-mode 의미 보호 결과
- fallback/override 동작
- 변경 파일과 테스트
- commit hash와 push 결과
- Phase 7 Dashboard에서 사용할 API와 UI contract
````
