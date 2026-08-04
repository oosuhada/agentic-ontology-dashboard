# Phase 16 — Adaptive Modeling Governance and Release Verification

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

Project 3 통합 regression이 필요하면 다음 프로젝트도 실제 checkout 모드로 열되,
Adaptive Modeling 기능을 Project 3에 새로 구현하지 마.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트3

다음 두 경로는 읽기 전용 기준 artifact로 확인해.

V3.1 package:
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1

prototype:
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/prototype_share

각 workspace를 한 번씩만 open_workspace하고 반환된 workspaceId를 재사용해.

먼저 다음을 읽어줘.

- docs/30-implementation/predictive-maintenance-adaptive-modeling-integration-plan.md
- docs/60-development-prompts/predictive-maintenance-adaptive-modeling/README.md
- Phase 9~15 prompt, 구현, commit
- V3.1 Phase 8 final release report
- docs/20-architecture/system-architecture.md
- docs/20-architecture/architecture-decisions.md
- docs/20-architecture/predictive-maintenance-projection-contract.md
- docs/10-product/dataset-strategy.md
- docs/10-product/model-baseline-results.md
- scripts/preflight.py
- scripts/verify_production_environment.py
- scripts/release_gate.py
- backup/restore, outbox, governance, artifact-store 관련 runbook
- 현재 Dataset Intake, Mapping, Feature Recipe, Experiment, Model Registry,
  Prediction/Explanation, ML Validator 구현

각 저장소에서 git status, 최근 commit, remote tracking을 확인하고 다른 세션의
미커밋 변경을 보존해. 이번 단계 수정만 stage해.

이번 목표는 `prototype_share` 진단에서 확인된 모든 개선 항목이 프로젝트2의 governed
Adaptive Modeling capability로 실제 closure되었는지 검증하고, source onboarding부터
모델 승격·설명·Dashboard까지 end-to-end release evidence를 남기는 것이다.

구현·검증 범위:

1. Phase 9~15 completion audit
   - contract foundation
   - Dataset Intake
   - Ontology Mapping approval
   - Feature Recipe/Feature Dataset
   - Experiment evaluation
   - Model Registry/promotion
   - Prediction/Explanation
   - ML Validator Workbench
2. End-to-end scenario
   - controlled source file 또는 approved test source
   - Dataset Intake Profile
   - Manifest Draft review/approval
   - existing Adapter ingestion
   - 새 immutable Dataset Version
   - Ontology Mapping Candidate approval
   - capability readiness
   - Feature Recipe Set publish
   - Feature Dataset Version materialization
   - Experiment Run submit/worker execution
   - validation model/threshold selection
   - held-out test report
   - Model Release Request
   - tenant-admin approval/activation
   - governed prediction
   - Explanation Artifact
   - ML Validator and role Dashboard consumption
3. V3.1 lineage preservation
   - 기존 V3.1 Dataset Version, checksum, row count, Result Artifact를 수정하지 않음
   - adaptive modeling test/run은 별도 Dataset/Feature/Experiment/Model identity
   - V2/V3.1 rollback과 기존 Dashboard regression
4. Prototype closure matrix
   - preview cache → full checksum/parser version
   - direct auto-exclusion → Manifest Draft approval
   - tiny string ontology → registry-bound mapping with datatype/unit/grain
   - bad high-confidence auto mapping → critical-field approval
   - single-node capability → prerequisite bundles
   - ungrouped rolling → group/order/leakage gates
   - unversioned YAML → Feature Recipe Version/checksum
   - whole-data training → chronological train/validation/test
   - no baseline/metrics → Dummy baseline and full metrics
   - fixed 0.5 threshold → validation recall/cost policy
   - duplicated SHAP → Explanation Provider abstraction
   - JSON/Windows-path registry → PostgreSQL registry and portable artifact URI
   - synchronous train API → queued worker/CLI
   - static 3-model cards → governed ML Validator Workbench
   - no tests/docs → release tests/runbook/evidence
   - false MCP naming → Dataset Intake/Adapter terminology
5. Security and isolation
   - file allowed-root/symlink traversal
   - tenant/project/workspace isolation
   - Dataset/Feature/Experiment/Model cross-project references
   - approval permissions
   - arbitrary artifact/code/expression execution 차단
   - sensitive preview redaction
6. Semantics negative controls
   - evaluation truth/hidden truth leakage 차단
   - binary model을 failure-mode multiclass로 오표시하지 않음
   - topology edge를 causal label/feature로 사용하지 않음
   - local contribution을 causal proof로 표현하지 않음
   - recommended action을 승인·실행된 WorkOrder로 표시하지 않음
   - confidence/probability/threshold 혼동 금지
7. Reproducibility
   - source/Dataset/mapping/recipe/feature/label/split/seed/runtime/model/policy checksum chain
   - 동일 artifact와 seed의 재현성
   - model artifact checksum verification
   - environment lock과 dependency capability
8. Recovery
   - failed profile/materialization/experiment retry
   - worker crash recovery
   - failed model activation rollback
   - previous active model rollback
   - metadata DB backup/restore
   - artifact root/object store restore 또는 재생성 runbook
9. Operational capability
   - local worker
   - PostgreSQL
   - object/artifact storage
   - optional LightGBM/XGBoost
   - explanation provider
   - Project 3/Neo4j regression
   - unavailable external capability는 blocked로 정확히 구분
10. Documentation
   - architecture and data flow
   - source onboarding guide
   - mapping approval guide
   - Feature Recipe authoring guide
   - Experiment and metric interpretation
   - model release/rollback runbook
   - artifact backup/restore
   - demo limitations
   - synthetic data and non-production-readiness disclosure

최종 E2E에는 다음 identity chain이 모두 표시돼야 한다.

```text
source checksum
→ Dataset Intake Profile checksum
→ approved Manifest Draft revision
→ Dataset Version
→ approved Mapping Set version/checksum
→ Feature Recipe Set version/checksum
→ Feature Dataset Version/checksum
→ Label Policy
→ Experiment Run and split policy
→ selected candidate and held-out metrics
→ Model Version artifact checksum
→ calibration and threshold policy
→ Prediction Result
→ Explanation Artifact checksum
```

필수 검증:

- Phase별 targeted tests 전체
- additive PostgreSQL migration/runtime checks
- Dataset Intake format/security/idempotency tests
- Mapping approval/capability prerequisite tests
- Feature group/order/leakage/training-serving parity tests
- chronological split, baseline, metric, calibration, threshold tests
- worker submit/retry/cancel/recovery tests
- model artifact/promotion/rollback/isolation tests
- Prediction Result/Explanation Artifact contract tests
- evaluation truth/hidden truth leakage negative tests
- binary/recommended-action/topology/contribution semantics negative tests
- backend full pytest 또는 합리적으로 분리된 전체 suite
- frontend typecheck/build
- ML Validator와 release flow Playwright E2E
- 최종 visual regression manifest/baseline check
- Project 3 contract/degraded regression if connected
- python scripts/preflight.py
- python scripts/verify_production_environment.py
- python scripts/release_gate.py
- docs structure check
- git diff --check

외부 credential, Docker, object storage, optional dependency, Project 3 endpoint가 없어
일부 gate를 실행할 수 없으면 성공 처리하지 말고 blocked reason과 local pass를 분리해.
고칠 수 있는 코드·설정 문제는 이 세션에서 수정하고 다시 검증해.

최종 release report와 prototype closure matrix를 문서화하고 이번 단계 관련 파일만
stage해서 다음을 수행해줘.

- git commit -m "chore: finalize adaptive modeling engine release"
- git push origin HEAD

Project 3에 regression fix가 필요해 변경했다면 저장소별로 별도 commit/push하고 hash를
구분해. push 실패 시 reset/rebase/force push 없이 오류와 로컬 commit hash를 보고해.

마지막 보고에는 반드시 다음을 포함해줘.

- Phase 9~16 완료 여부 표
- V3.1 기존 release 불변성 검증
- Adaptive Modeling E2E identity chain
- Dataset Intake/Mapping/Feature/Experiment/Model row/artifact counts
- candidate validation/test metrics와 threshold/calibration
- active Model Version과 rollback 결과
- Prediction/Explanation parity
- prototype 진단 closure matrix
- security/semantics/leakage negative test 결과
- backup/restore/reproducibility 결과
- production capability와 blocked 항목
- 주요 URL과 실행 명령
- 변경 파일
- 저장소별 commit hash와 push 결과
- 실제로 남은 작업이 있다면 우선순위 순 목록
````
