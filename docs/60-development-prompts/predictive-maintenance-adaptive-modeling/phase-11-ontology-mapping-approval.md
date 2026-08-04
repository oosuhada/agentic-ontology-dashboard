# Phase 11 — Ontology Mapping Approval and Capability Preconditions

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

다음 경로는 참고용으로만 열고 수정하지 마.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/prototype_share

먼저 다음을 읽어줘.

- docs/30-implementation/predictive-maintenance-adaptive-modeling-integration-plan.md
- Phase 9~10 구현과 commit
- Phase 10 Dataset Intake Profile과 Manifest Draft contract
- api/ontology_dashboard/ontology.py
- api/ontology_dashboard/ontology_repository.py
- api/ontology_dashboard/ontology_service.py
- api/ontology_dashboard/ontology_planner_models.py
- api/ontology_dashboard/ontology_planner_service.py
- api/ontology_dashboard/governance/
- api/ontology_dashboard/datasets/materialization.py
- predictive-maintenance domain pack mapping/materialization
- prototype_share/ontology/mapping_agent.py
- prototype_share/ontology/mapping_store.py
- prototype_share/ontology/capability_detector.py
- prototype_share/ontology/mapping_cache.json은 품질 문제 사례로만 확인

git status, 최근 commit, remote tracking을 확인하고 다른 세션의 미커밋 변경을 보존해.
현재 단계 관련 파일만 stage해.

이번 목표는 source column을 단순 문자열 라벨로 자동 매핑하는 구현을, registry-bound
Ontology Mapping Candidate와 사람 승인 workflow로 대체하고 실제 modeling capability의
필수 조건을 평가하는 것이다.

구현 범위:

1. Mapping Candidate generator
   - Phase 10 field profile을 입력으로 사용
   - canonical object/property registry 안에서만 후보 생성
   - field name, datatype, unit, cardinality, sample pattern, source role 근거
   - deterministic alias/rule 후보 우선
   - optional LLM은 등록된 후보 재정렬과 rationale만 수행
2. Mapping dimension
   - target object type
   - target property
   - datatype
   - physical unit
   - grain
   - semantic role: identifier/timestamp/dimension/measure/status/text
   - group key와 join key
   - source field와 canonical field
3. Confidence and provenance
   - rule, manifest metadata, unit metadata, LLM suggestion, user confirmation 분리
   - confidence는 근거와 함께 저장
   - high-confidence라도 중요 identifier/time/unit mismatch면 auto approval 금지
   - unknown은 오류가 아니라 unresolved 상태
4. Critical-field policy
   - equipment/asset identifier
   - observation timestamp
   - label/event timestamp
   - source grouping key
   - maintenance join key
   - 중요 필드는 승인 없이 feature/training에 사용 불가
5. Approval workflow
   - candidate 생성/조회
   - approve/reject/edit/supersede
   - mapping set version/checksum
   - 승인자, rationale, audit event
   - Dataset Version scope
   - 기존 approved version immutable
6. Mapping validation
   - duplicate canonical property conflict
   - incompatible datatype/unit
   - identifier cardinality와 timestamp parseability
   - grain mismatch
   - source field 없음
   - 다른 Dataset Version mapping 재사용 시 compatibility check
7. Capability Requirement evaluator
   - predictive_training
   - predictive_scoring
   - maintenance_context
   - replay_time_series
   - explanation
   - 각 capability를 prerequisite bundle로 평가
   - ready/degraded/blocked와 missing prerequisite 반환
8. Predictive training 최소 prerequisite
   - approved equipment identifier
   - approved ordered timestamp
   - numeric sensor measure 1개 이상
   - label/event policy 또는 approved target source
   - group/time continuity validation 가능
9. API와 Governance UI 최소 vertical
   - mapping candidate list/detail
   - approve/reject/edit
   - capability readiness summary
   - 전체 ML Validator UI는 Phase 15에서 구현
10. Existing ontology materialization boundary
   - mapping approval이 곧 object materialization 완료를 의미하지 않음
   - V3.1 기존 mapping/materialization을 무단 변경하지 않음
   - 새 source는 기존 Dataset/Ontology service를 통해 별도 version으로 처리

prototype_share에서 발견된 다음 사례가 재발하지 않게 해.

```text
datetime → Unknown, confidence 0.9, auto_mapped
model → Equipment, confidence 0.9, auto_mapped
```

중요:

- vocabulary를 Voltage/Pressure 등 소수 문자열 집합으로 축소하지 마.
- LLM이 새 ontology property를 즉석에서 만들 수 없게 해.
- capability는 관련 node 하나만 있다고 active가 되면 안 된다.
- user-confirmed mapping과 LLM suggestion을 같은 provenance로 저장하지 마.
- mapping cache file 하나를 system of record로 사용하지 마.

필수 검증:

- V3.1 known fields의 deterministic candidate
- timestamp/equipment/unit candidate 정확성
- unknown field unresolved 상태
- `model` 같은 ambiguous field가 Equipment로 자동 승인되지 않음
- incompatible datatype/unit 거부
- high-confidence critical field도 approval 필요
- LLM unknown object/property/field 반환 시 fallback
- mapping version/checksum immutability
- approve/edit/reject/supersede audit
- cross-Dataset-Version compatibility
- predictive_training prerequisite ready/blocked cases
- FailureEvent 하나만으로 predictive capability가 ready가 되지 않는 test
- maintenance identifier/time/join-key 누락 blocked test
- tenant/project/workspace isolation
- existing Ontology and V3.1 materialization regression
- backend targeted tests와 필요한 최소 frontend test
- git diff --check

검증 완료 후 이번 단계 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: govern ontology mapping approvals"
- git push origin HEAD

마지막 보고:

- mapping candidate와 approval contract
- critical-field 보호 방식
- confidence/provenance 구분
- capability prerequisite 결과
- 기존 V3.1 mapping과의 경계
- 변경 파일과 테스트
- commit hash와 push 결과
- Phase 12에서 사용할 approved mapping set identity
````
