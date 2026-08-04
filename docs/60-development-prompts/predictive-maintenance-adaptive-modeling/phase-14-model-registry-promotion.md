# Phase 14 — Governed Model Registry, Promotion, Prediction and Explanation

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

다음 경로는 참고용으로만 열고 수정하지 마.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/prototype_share

먼저 다음을 읽어줘.

- docs/30-implementation/predictive-maintenance-adaptive-modeling-integration-plan.md
- Phase 9~13 구현과 commit
- Phase 13 Experiment Run과 selected candidate artifact
- schemas/prediction-result.schema.json
- schemas/evidence-package.schema.json
- Phase 5 Result Artifact/Prediction Result 구현
- api/ontology_dashboard/adapters/prediction_repository.py
- api/ontology_dashboard/role_workflow_models.py
- api/ontology_dashboard/role_workflow_service.py
- api/ontology_dashboard/governance/
- ml/src/factory_signal_ml/predictor.py
- ml/src/factory_signal_ml/evidence.py
- prototype_share/prediction/output_schema.py
- prototype_share/prediction/predict_all.py
- prototype_share/models/lightgbm/__init__.py
- prototype_share/models/xgboost/__init__.py
- prototype_share/models/random_forest/__init__.py
- prototype_share/report/generator.py

git status, 최근 commit, remote tracking을 확인하고 다른 세션의 미커밋 변경을 보존해.
현재 단계 관련 파일만 stage해.

이번 목표는 selected Experiment candidate를 portable immutable Model Version으로
등록하고, release request와 tenant-admin 승인을 거쳐 active serving model로 승격하며,
Prediction Result와 공통 Explanation Artifact를 생성하는 것이다.

구현 범위:

1. Model Version Registry
   - model version identity
   - experiment id와 candidate id
   - Dataset Version, Mapping Set, Feature Recipe Set, Feature Dataset Version, Label Policy
   - artifact URI, SHA-256, media type, size
   - input feature schema/checksum
   - library/runtime versions
   - calibration method/artifact
   - threshold policy/version
   - explanation provider/version
   - limitations
   - candidate/approved/active/retired/rejected status
2. Portable artifact loading
   - artifact root/object store port
   - checksum 검증 후 load
   - local OS separator를 identity로 사용하지 않음
   - `models_store\\random_forest\\model.joblib` 같은 registry 값 금지
   - untrusted pickle/joblib artifact를 arbitrary upload로 실행하지 않음
3. Promotion workflow
   - ml_validator가 release request 생성
   - tenant-admin이 approve/reject
   - 승인 전 active serving 불가
   - project/workspace별 active model 하나 또는 명시된 policy
   - concurrent activation transition guard
   - previous active model retire/rollback 가능
   - audit event와 approver rationale
4. Promotion gate
   - Experiment succeeded
   - selected candidate artifact checksum valid
   - held-out test metrics 존재
   - baseline improvement policy
   - minimum recall/quality gate
   - Feature Dataset/recipe/mapping compatibility
   - calibration/threshold artifact compatibility
   - optional dependency runtime capability
   - unresolved governance blocker 없음
5. Serving contract
   - approved active Model Version만 scoring 가능
   - request Dataset Version/feature schema compatibility
   - training과 inference Feature Recipe engine/version parity
   - idempotent scoring identity
   - model unavailable/incompatible/degraded 상태
6. Prediction Result integration
   - existing Prediction Result/Result Artifact 경계를 재사용
   - probability
   - calibrated probability 또는 별도 calibration field
   - threshold와 decision policy
   - binary task `binary_failure_within_horizon`
   - `failure_risk|no_significant_risk` 의미 유지
   - Dataset/model/recipe/policy provenance
   - recommended action은 policy recommendation이며 WorkOrder 아님
7. Confidence semantics
   - `max(probability, 1-probability)`를 confidence로 자동 저장하지 않음
   - calibrated probability를 confidence라고 이름만 바꾸지 않음
   - ensemble agreement, calibration quality, explanation stability 등 별도 근거가 없으면
     confidence unavailable 가능
   - UI/API가 unavailable을 지원
8. Explanation Provider abstraction
   - 공통 provider interface
   - tree model: Tree SHAP compatible provider
   - linear model: coefficient contribution provider
   - unsupported model: unavailable reason
   - 모델별 중복 SHAP parsing 코드를 제거
   - explanation 계산 실패가 prediction 자체를 허위 성공/실패로 바꾸지 않음
9. Explanation Artifact
   - prediction/result identity
   - model version
   - explanation provider/version
   - Feature Recipe lineage
   - top factors
   - direction/contribution
   - observed value, unit, reference range 또는 availability
   - checksum/generated_at
   - input row/feature contract hash
10. Explanation safety
   - 마지막 한 행이라는 이유만으로 time context를 잃지 않음
   - explanation 대상 observation identity와 timestamp 명시
   - feature importance와 local contribution을 구분
   - contribution을 causal proof로 표현하지 않음
11. Prediction/release API
   - model versions list/detail
   - release request/approve/reject/rollback
   - active model status
   - governed scoring endpoint 또는 existing path integration
   - explanation 조회
12. Degraded mode
   - explanation provider unavailable이어도 prediction 결과와 reason 반환
   - optional LightGBM/XGBoost runtime unavailable 시 해당 model activation 차단 또는
     명확한 blocked state
   - 이전 approved active model rollback 가능

중요:

- model release approval과 WorkOrder/action approval을 연결하지 마.
- binary model을 PWF/HDF/OSF/TWF classifier로 표시하지 마.
- feature importance와 SHAP/local explanation을 같은 의미로 합치지 마.
- model artifact checksum mismatch를 warning만 남기고 load하지 마.
- 승인되지 않은 candidate를 demo 편의를 위해 active로 만들지 마.
- user-supplied arbitrary pickle을 load하지 마.

필수 검증:

- model artifact URI/checksum portability
- Windows/Linux/macOS separator 독립성
- checksum mismatch와 missing artifact 거부
- unapproved model scoring/activation 거부
- ml_validator release request와 tenant-admin approval 권한
- concurrent activation guard
- active model rollback과 audit
- held-out metrics/baseline/policy gate 실패 거부
- cross-project model/feature/Dataset Version 참조 거부
- training/inference feature schema parity
- raw/calibrated probability/threshold/confidence field 구분
- confidence unavailable contract
- tree/linear explanation provider contract
- unsupported/failed explanation degraded result
- local contribution과 global importance 구분
- explanation artifact checksum/idempotency
- predicted type binary semantics negative test
- recommended action이 WorkOrder를 생성하지 않는 negative test
- evaluation truth/hidden truth를 explanation factor로 사용하지 않는 test
- existing V3.1 Result Artifact/Prediction Result regression
- targeted ml/backend tests
- git diff --check

ML Validator 전체 UI는 Phase 15에서 구현하므로 이번 단계에서는 release API의 필요한
최소 workflow test만 수행해.

검증 완료 후 이번 단계 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: govern model promotion and explanations"
- git push origin HEAD

push 실패 시 이력 재작성 없이 오류와 commit hash를 보고해.

마지막 보고:

- Model Version identity와 lineage
- promotion/approval/rollback 결과
- serving compatibility와 degraded mode
- probability/calibration/threshold/confidence 의미
- Explanation Artifact와 provider 구조
- Prediction Result 연결 방식
- 변경 파일과 테스트
- commit hash와 push 결과
- Phase 15 UI가 사용할 API 목록
````
