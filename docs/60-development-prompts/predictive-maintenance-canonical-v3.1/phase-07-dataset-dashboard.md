# Phase 07 — V3.1 Dataset-Driven Dashboard

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

V3.1 schema와 Result Artifact 계약은 읽기 전용으로 확인해줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1

현재 V3.1 기준 identity는 다음과 같다. UI에서 값을 하드코딩하지 말고 API가
반환하는 Project/Dataset Version context를 사용하되, 검증 fixture와 E2E에서는 이
identity와 package checksum을 기준으로 parity를 확인해.

```text
source version          canonical-ai4i-physics-v3.1
bundle checksum         12734b1eec67ae5ccf322221967d5628ba5cf1ecb0401e6daef5c3dd7a855682
Dataset Version         dsv-1914858a-cc17-57d8-819c-d8a2435fd805
mapping version         predictive-maintenance-v3.1
Result Artifact         100
Ontology objects        1,984
Ontology links          2,160
```

먼저 다음을 읽고 현재 실행 화면과 실제 V3.1 데이터를 함께 확인해줘.

- docs/30-implementation/predictive-maintenance-canonical-v3-upgrade-plan.md
- docs/40-ui-ux/reference/palantir-contour-dashboard-benchmark.md
- docs/40-ui-ux/plans/chart-intelligence-color-system-uiux-plan.md
- predictive_maintenance_canonical_v3.1/RESULT_ARTIFACT_SCHEMA.md
- predictive_maintenance_canonical_v3.1/V3_1_RELEASE_VERIFICATION.md
- docs/20-architecture/predictive-maintenance-projection-contract.md
- Phase 3~6 구현과 API contract
- web/src/features/dashboard/
- web/src/features/datasets/
- web/src/features/ontology/
- web/src/features/role-workspaces/
- web/src/features/replay/가 있으면 해당 구현
- 현재 dashboard visual baseline/manifest

git status --short --branch와 최근 커밋을 확인하고 다른 세션의 미커밋 변경을
보존해. 특히 다른 UI 세션의 변경과 현재 web/vite.config.ts를 무단으로 정리하거나
이번 커밋에 포함하지 마.

이번 목표는 기존 fixture 하드코딩을 우회하지 않고 PostgreSQL에 적재된 V3.1 Dataset
Version, Ontology, Result Artifact, Prediction, Replay API를 실제 역할별 Dashboard에
연결하는 것이다.

구현 범위:

1. Project/Dataset Version context
   - Predictive Maintenance Project 선택
   - V2와 V3.1 Dataset Version 명시적 선택
   - 기본은 ready 상태의 최신 approved V3.1 version
   - V2/V3.1 checksum, source version, store readiness 표시
   - model `independent-logreg-v3.1`, Result Artifact schema
     `result-artifact-v1.0`, binary prediction task 표시
   - Project/Workspace/Dataset Version scope가 모든 board query에 전달
2. Manager/Executive Dashboard
   - status_grade별 자산 수
   - failure_probability 상위 자산
   - site/cell별 위험 집중도
   - recommended_action과 priority
   - 정비 이력과 검토가 필요한 설비
   - recommendation을 실행 완료된 action이나 승인된 WorkOrder로 표시하지 않음
3. Engineer/Technician Dashboard
   - canonical 센서 추세
   - power_w, temperature_gap_k, overstrain_load
   - prediction factor와 Result Artifact provenance
   - 실제 WorkOrder/MaintenanceAction
   - replay controls와 simulation time
4. Data Scientist Dashboard
   - AI4I physical profile와 validation summary
   - sensor 분포와 correlation
   - model task/version, ROC-AUC/PR-AUC, confidence
   - factor contribution과 dataset/model lineage
   - 현재 model이 binary failure-within-horizon임을 명시
5. FDE/Admin Dashboard
   - V2/V3.1 schema/source-contract/checksum diff
   - mapping approval와 projection readiness
   - PostgreSQL ready, Neo4j ready/degraded
   - Result Artifact schema/version/coverage
   - package validation과 AI4I physics gate
   - tool-wear continuity 731 replacement / 731 aligned reset
   - maintenance evidence accuracy와 false-upstream-claim rate를 release evidence로 표시
   - release evidence의 상세 truth row는 일반 사용자에게 노출하지 않음
6. chart intelligence UI
   - Phase 6 추천 chart 기본 적용
   - chart switcher
   - field/aggregation inspector
   - 추천 이유와 fallback/provenance panel
   - schema incompatible 상태 명시
   - AI4I derived measure의 수식·unit 표시
7. graph + relational interaction
   - Equipment 선택이 topology graph와 시계열/Result Artifact board에 cross-filter
   - `SUPPLIES_AIR_TO`를 causal confirmation으로 표현하지 않음
   - graph가 degraded여도 relational board 유지
   - graph node/edge count와 DatasetVersionReference 처리 방식을 readiness detail에 표시
8. replay UI
   - start/pause/resume/reset/speed/seek
   - simulation time과 source freshness 분리
   - nearest historical prediction과 latest Result Artifact를 구분
9. loading/empty/error/degraded states
   - Dataset Version 없음
   - V3.1 compatibility/ingestion 실패
   - mapping 미승인
   - projection pending/failed
   - Result Artifact 없음 또는 schema incompatible
   - Neo4j degraded
   - query invalid/unsupported derived measure
10. 사용자 저장
   - chart kind, field mapping, aggregation, selection/filter
   - Dataset Version과 semantic catalog version을 함께 저장
   - V2 설정을 V3에 무검증 재사용하지 않고 compatibility 확인

중요:

- 기존 static fixture 값을 V3.1 데이터처럼 표시하지 마.
- API 결과가 없으면 허위 sample을 채우지 말고 empty/degraded 상태를 보여줘.
- `predicted_failure_type`을 PWF/HDF/OSF/TWF로 표시하지 마.
- evaluation truth와 experiment hidden truth를 일반 사용자 Dashboard에 노출하지 마.
- package validation의 `event_condition_details`, `condition_variant`, failure timestamp도
  일반 사용자 Dashboard payload와 client state에 전달하지 마.
- recommended action 버튼을 자동 정지·자동 WorkOrder 실행처럼 보이게 만들지 마.
- UI만 비슷하고 클릭이 동작하지 않는 상태로 완료하지 마.
- 현재 제품의 색상·타이포그래피·Workbench 패턴을 유지해.

필수 검증:

- 실제 PostgreSQL V3.1 Dataset Version을 사용한 role별 Dashboard 렌더
- V2/V3.1 version 변경 시 row count, result, board state가 올바르게 교체
- Project 변경 시 다른 Project 데이터가 남지 않음
- Manager, Engineer, Data Scientist, FDE 핵심 board 데이터 확인
- Result Artifact 100개 coverage와 API 값 parity
- V3.1 source/model/schema/task/release-gate provenance 표시 parity
- chart 추천 변경과 저장 후 reload 복원
- V2 설정을 V3로 적용할 때 compatibility validation
- graph selection → relational chart cross-filter
- topology relation이 causal wording을 만들지 않음
- replay controls 실제 API 연동
- latest Result Artifact와 historical replay prediction 구분
- recommended action과 WorkOrder 상태 구분
- binary model task 표기
- evaluation truth/hidden truth UI leakage negative test
- Neo4j down 상태의 degraded UI
- graph degraded 중에도 Manager/Engineer/Data Scientist relational board가 정상 유지
- desktop/tablet/mobile 핵심 viewport
- frontend typecheck/build
- 관련 Playwright E2E
- 이 단계에서 변경한 화면의 visual regression/baseline 갱신
- backend targeted tests
- git diff --check

검증용 서버를 실행했다면 완료 후 상태와 확인 URL을 보고하고 불필요한 중복
프로세스는 정리해. 기존 사용자가 실행 중인 프로세스를 무단 종료하지 마.

검증 완료 후 이번 단계 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: render predictive maintenance v3.1 dashboards"
- git push origin HEAD

push 실패 시 이력 재작성 없이 오류와 commit hash를 보고해.

마지막 보고:

- V2/V3.1 Dataset Version 선택 동작
- 역할별 실제 V3.1 데이터 화면
- Result Artifact, AI4I measure, chart/replay/cross-filter 동작
- binary model/recommended-action/topology 의미 보호 결과
- empty/error/degraded 상태
- 확인 URL과 viewport 검증
- 변경 파일과 테스트 결과
- commit hash와 push 결과
- Phase 8에 남은 운영·release 항목
````
