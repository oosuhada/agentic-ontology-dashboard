# Phase 05 — V3.1 Result Artifact and Replay Vertical

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

V3.1 데이터 패키지의 replay와 Result Artifact 구현을 읽기 전용으로 확인해줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1

Phase 5의 기준 Dataset은 다음 V3.1 immutable version이다. API 구현에서는 ID를
하드코딩하지 말고 Project/Dataset Version context로 선택하되, 검증에서는 이 기준과
실제 package checksum이 일치하는지 확인해.

```text
source version          canonical-ai4i-physics-v3.1
bundle checksum         12734b1eec67ae5ccf322221967d5628ba5cf1ecb0401e6daef5c3dd7a855682
Dataset Version         dsv-1914858a-cc17-57d8-819c-d8a2435fd805
model                   independent-logreg-v3.1
Result Artifact schema  result-artifact-v1.0
prediction task         binary_failure_within_horizon
```

먼저 다음을 읽어줘.

- docs/30-implementation/predictive-maintenance-canonical-v3-upgrade-plan.md
- docs/20-architecture/predictive-maintenance-projection-contract.md
- Phase 0~4 구현과 커밋
- schemas/prediction-result.schema.json
- api/ontology_dashboard/adapters/models.py의 PredictionResult
- api/ontology_dashboard/adapters/prediction_repository.py
- Phase 3에서 추가한 Result Artifact repository/table
- Phase 2/3 predictive maintenance fact tables
- predictive_maintenance_canonical_v3.1/RESULT_ARTIFACT_SCHEMA.md
- predictive_maintenance_canonical_v3.1/api/replay_server.py
- predictive_maintenance_canonical_v3.1/dashboard/README.md
- predictive_maintenance_canonical_v3.1/canonical/model_outputs/model_contract.json
- predictive_maintenance_canonical_v3.1/canonical/model_outputs/result_artifact.jsonl
- V3.1 Dataset Version `profile_json.release_gates`
- Phase 4 graph readiness/degraded status API

git status --short --branch, 최근 커밋, remote tracking을 확인하고 다른 세션의
미커밋 변경을 보존해. 현재 단계 관련 파일만 stage해.

이번 목표는 V3.1 Result Artifact를 제품의 최신 결과 계약으로 연결하고,
snapshot/factor/timeline과 canonical observations를 PostgreSQL 기반 replay API로
제공하는 것이다.

Phase 4 graph projection이 ready면 graph context를 함께 제공하고, Project 3 또는
Neo4j가 degraded여도 replay와 Result Artifact API는 PostgreSQL에서 정상 동작해야
한다. Phase 5를 위해 완료된 V3.1 Dataset Version을 다시 적재하거나 materialize하지 마.

구현 범위:

1. Result Artifact converter와 API
   - `pm_result_artifacts` → governed product result DTO/API
   - artifact_id, asset, observed_at, horizon, task, probability, status_grade,
     confidence, top_factors, recommended_action, provenance 보존
   - Dataset Version, bundle checksum, model version, schema version 포함
   - tool-wear continuity와 agent maintenance-evidence release gate는 governance
     provenance로만 노출하고 prediction label로 변환하지 않음
   - 100개 자산 coverage
2. 기존 PredictionResult와 연결
   - Result Artifact provenance.prediction_id와 기존 PredictionResult identity 연결
   - latest product API는 Result Artifact를 우선 사용
   - snapshot/factor API는 backward-compatible drill-down으로 유지
   - V2 Dataset Version은 기존 snapshot/factor 경로로 계속 조회 가능
3. prediction 의미 제한
   - `prediction_task=binary_failure_within_horizon`
   - `predicted_failure_type=failure_risk|no_significant_risk`
   - PWF/HDF/OSF/TWF multiclass prediction으로 변환·표시하지 않기
4. recommended action 의미
   - `recommended_action`은 정책 기반 추천
   - 승인·실행 상태가 아님
   - WorkOrder 생성 endpoint를 자동 호출하지 않음
5. 최신 상태와 이력 분리
   - latest Result Artifact/PredictionResult: 100건
   - snapshot factors: 300건
   - historical timeline: 68,208건
   - replay prediction은 timeline source를 사용
6. PostgreSQL time-window query API
   - asset/site/cell/type/time range
   - sensor observation과 nearest prediction
   - 안전한 limit/grain
   - query-time derived measure allowlist:
     - `power_w = torque_nm * rotational_speed_rpm * 2*pi/60`
     - `temperature_gap_k = process_temperature_k - air_temperature_k`
     - `overstrain_load = tool_wear_min * torque_nm`
   - derived measure는 source CSV에 역기입하지 않음
7. replay session/cursor
   - start, pause, resume, reset, speed, seek
   - simulation time과 source freshness 분리
   - seek 시 가장 가까운 사전 계산 prediction 사용
   - model retraining 없음
8. SSE adapter
   - cursor state, canonical sensor snapshot, nearest timeline prediction 제공
   - 필요하면 latest Result Artifact reference 함께 제공
   - disconnect/cleanup과 project/workspace/dataset-version scope
   - graph readiness는 부가 상태이며 SSE sensor/replay 전달의 필수 의존성이 아님
9. 최소 UI vertical
   - 기존 Dashboard source binding 또는 작은 panel로 API 동작 확인
   - Phase 7의 전체 UX 개편은 하지 않음

중요:

- canonical CSV에 없는 센서값을 생성하지 마.
- seek 또는 speed 변경 시 모델을 다시 학습하지 마.
- live current time과 simulation time을 혼동하지 마.
- evaluation truth와 optional experiment hidden truth를 prediction evidence로 사용하지 마.
- V3.1 package의 `ai4i_physics`와 `tool_wear_continuity` validation 결과는 governance provenance이며 실시간
  prediction label이 아니다.
- `maintenance_evidence_accuracy=1.0`은 release evidence이며 개별 prediction의
  정확도나 실행 완료 상태로 표시하지 마.

필수 검증:

- Result Artifact 100건 변환과 PredictionResult identity 연결
- snapshot 100건, factor 300건, timeline 68,208건 parity
- Result Artifact required field/schema/provenance 검증
- source version, bundle checksum, model/schema/task provenance parity
- V3.1 release gate 조회와 truth-detail 비노출 검증
- binary predicted type semantics negative test
- recommended action이 WorkOrder를 자동 생성하지 않는 negative test
- 특정 simulation time의 compressor/CNC observation이 V3.1 source row와 일치
- nearest prediction 선택이 V3.1 prediction_timeline과 일치
- derived power/temperature gap/overstrain 계산 정확성
- pause 후 cursor 정지, resume 후 진행
- speed 변경에 따른 cursor 진행
- start/end boundary와 seek validation
- seek가 model training function을 호출하지 않는 negative test
- SSE project/workspace/dataset-version isolation
- Neo4j/Project 3 down 상태에서도 PostgreSQL replay와 Result Artifact API 정상
- latest Result Artifact와 replay prediction API 구분
- V2 Dataset Version backward-compatible 조회
- 관련 backend tests와 필요한 최소 frontend test
- git diff --check

전체 visual regression은 아직 실행하지 마. Result Artifact/replay vertical의 API와
contract를 우선 검증해.

검증 완료 후 이번 단계 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: add v3.1 result artifact replay vertical"
- git push origin HEAD

push 실패 시 이력 재작성 없이 오류와 commit hash를 보고해.

마지막 보고:

- Result Artifact와 PredictionResult mapping
- latest/replay API 구분
- replay API와 SSE endpoint
- AI4I derived measure query contract
- source parity와 no-retraining 증거
- recommended action 비자동실행 증거
- 변경 파일과 테스트 결과
- commit hash와 push 결과
- Phase 6 planner가 사용할 semantic query capability
````
