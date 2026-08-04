# Phase 15 — Adaptive Modeling ML Validator Workbench

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

먼저 다음을 읽고 현재 실행 화면을 직접 확인해줘.

- docs/30-implementation/predictive-maintenance-adaptive-modeling-integration-plan.md
- Phase 9~14 구현과 commit
- Phase 13 Experiment API
- Phase 14 Model Registry, promotion, Prediction Result, Explanation API
- api/ontology_dashboard/role_workflow_service.py의 현재 `model_console`
- api/ontology_dashboard/role_workflow_models.py
- api/ontology_dashboard/dashboard_catalog.py의 ml_validator boards
- api/ontology_dashboard/identity_models.py의 ml_validator permissions
- web/src/features/role-workspaces/
- web/src/features/dashboard/
- web/src/features/datasets/
- web/src/features/governance/
- web/src/features/analysis/
- 현재 shared Workbench, chart, table, inspector, loading/empty/error component
- Phase 7 V3.1 role dashboard와 visual baseline manifest

git status, 최근 commit, remote tracking을 확인하고 다른 세션의 미커밋 변경을 보존해.
특히 현재 `web/vite.config.ts` 또는 다른 UI 세션 변경을 무단으로 정리하거나 이번
커밋에 포함하지 마. 현재 단계 관련 파일만 stage해.

이번 목표는 fixture heuristic과 정적 설명 중심의 기존 model console을, 실제 Dataset
Intake, Mapping, Feature Dataset, Experiment Run, Model Version, release workflow,
Explanation Artifact를 탐색하고 검증할 수 있는 ML Validator Workbench로 확장하는 것이다.

구현 범위:

1. Workspace context
   - Project/Workspace
   - source Dataset Version
   - Feature Dataset Version
   - Experiment Run
   - Model Version
   - context 변경 시 이전 project/model 데이터가 남지 않음
2. Experiment runs panel
   - queued/running/succeeded/failed/cancelled
   - progress와 candidate status
   - split policy, cutoff, embargo
   - Dataset/recipe/label lineage
   - failure와 blocked dependency reason
3. Candidate leaderboard
   - Dummy, Logistic, RF, optional LightGBM/XGBoost
   - validation Average Precision
   - ROC-AUC
   - Precision, Recall, F1
   - Brier/calibration
   - selected/rejected/blocked status
   - 모델 수가 아니라 selection rationale 표시
4. PR/ROC evaluation
   - 희소 고장 데이터에서는 PR curve를 primary로 표시
   - ROC는 secondary
   - baseline reference
   - validation/test scope 명시
   - test 결과가 selection에 사용되지 않았음을 표시
5. Threshold Policy panel
   - threshold curve
   - recall-constrained threshold
   - cost-minimizing threshold
   - false-negative/false-positive assumptions
   - selected operational threshold와 policy version
   - slider/override가 있으면 draft이며 승인 없이 active policy 변경 금지
6. Confusion Matrix와 Calibration
   - validation/test scope 선택
   - counts와 normalized view
   - calibration summary/Brier score
   - raw probability와 calibrated probability 구분
7. Slice Metrics
   - approved dimensions만 선택
   - minimum sample와 suppressed slice 상태
   - site/equipment/product type 등
   - evaluation truth/hidden truth field 노출 금지
8. Feature and lineage inspector
   - Mapping Set
   - Feature Recipe Set
   - Label Policy
   - feature list, unit, window, group/order, leakage validation
   - Feature Dataset artifact checksum
   - source Dataset Version/checksum
9. Explanation inspector
   - selected prediction/result
   - local top factors
   - direction/contribution
   - observed value, unit, reference range
   - provider/version
   - global feature importance와 local explanation을 별도 section으로 표시
   - contribution을 causal proof라고 표현하지 않음
10. Model Registry and release
   - candidate/approved/active/retired/rejected
   - artifact checksum/runtime capability
   - release request 생성
   - tenant-admin approval 상태
   - rollback history
   - ml_validator가 직접 self-approve하지 못함
11. Intake/mapping readiness summary
   - source profile과 Manifest Draft approval
   - Mapping Set approval
   - capability ready/degraded/blocked
   - missing prerequisite
12. Operational monitoring boundary
   - offline training metric과 operational prediction/drift를 분리
   - 실제 drift artifact가 없으면 unavailable 표시
   - fixture 기반 fake training metric으로 채우지 않음
13. Loading/empty/error/degraded states
   - experiment 없음
   - worker unavailable
   - optional dependency blocked
   - model artifact missing/checksum mismatch
   - explanation unavailable
   - mapping/feature incompatible
   - permission denied
14. UI/UX
   - 기존 Foundry/Contour Workbench 패턴과 색상·타이포그래피 유지
   - dense table, detail inspector, chart switcher 사용
   - desktop/tablet/mobile
   - keyboard/focus/accessibility
   - 클릭이 실제 API/state 변화로 이어짐

중요:

- 현재 `model_console`의 fixture gold scenario 결과를 실제 training metric처럼 표시하지 마.
- training/offline evaluation, active serving, operational outcome을 같은 차트에 혼합하지 마.
- probability, confidence, threshold를 같은 숫자로 표현하지 마.
- optional model이 blocked이면 숨기지 말고 capability reason을 표시해.
- SHAP/feature contribution만 보여주고 Dataset/recipe/model lineage를 생략하지 마.
- release request 버튼을 즉시 activation 버튼으로 만들지 마.

필수 검증:

- ml_validator role에서 실제 Experiment/Model API 렌더
- 다른 Project 전환 시 stale data 0
- Dataset/Feature Dataset/Experiment/Model context 연동
- candidate leaderboard metric parity
- PR curve primary와 validation/test label
- threshold/cost curve parity
- confusion matrix count parity
- calibration/raw probability 구분
- slice suppression과 unknown dimension 거부
- feature recipe group/order/leakage metadata 표시
- local explanation/global importance 구분
- release request와 tenant-admin approval 권한
- ml_validator self-approval 차단
- rollback history
- blocked dependency/worker/explanation states
- training metric unavailable 시 fixture로 대체하지 않는 negative test
- evaluation truth/hidden truth UI leakage negative test
- binary predicted type와 recommended action semantics
- frontend typecheck/build
- 관련 unit/component tests
- Playwright role/context/release flow E2E
- desktop/tablet/mobile visual regression과 baseline 갱신
- backend targeted tests
- git diff --check

검증 서버를 실행했다면 확인 URL과 process 상태를 보고하고, 사용자가 실행 중인 기존
process를 무단 종료하지 마.

검증 완료 후 이번 단계 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: add adaptive modeling validator workbench"
- git push origin HEAD

push 실패 시 reset/rebase/force push 없이 오류와 로컬 commit hash를 보고해.

마지막 보고:

- ML Validator information architecture
- 실제 Experiment/Model/Explanation 데이터 연결
- leaderboard, PR, threshold, calibration, slice 결과
- lineage와 release workflow
- loading/empty/error/blocked 상태
- viewport/E2E/visual 결과와 확인 URL
- 변경 파일과 테스트
- commit hash와 push 결과
- Phase 16에 남은 governance/release 항목
````
