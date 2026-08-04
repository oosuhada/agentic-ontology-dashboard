# Phase 13 — Time-Aware Multi-Model Experiment and Evaluation

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

다음 두 경로는 참고용으로만 열고 수정하지 마.

V3.1 package:
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1

prototype:
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/prototype_share

각 프로젝트는 한 번씩만 open_workspace하고 반환된 workspaceId를 재사용해.

먼저 다음을 읽어줘.

- docs/30-implementation/predictive-maintenance-adaptive-modeling-integration-plan.md
- docs/60-development-prompts/predictive-maintenance-adaptive-modeling/README.md
- Phase 9~12 구현과 commit
- Phase 12 Feature Dataset Version, Feature Recipe Set, Label Policy contract
- docs/10-product/model-baseline-results.md
- ml/src/factory_signal_ml/training.py
- ml/src/factory_signal_ml/dataset.py
- ml/src/factory_signal_ml/contracts.py
- ml/config/threshold_policy.json
- ml/config/trained_model_policy.json
- api/ontology_dashboard/role_workflow_models.py
- api/ontology_dashboard/role_workflow_service.py의 model release workflow
- prototype_share/models/
- prototype_share/models/registry.py
- prototype_share/training/train_all_models.py
- prototype_share/prediction/label_builder.py
- prototype_share/models_store/registry.json

git status, 최근 commit, remote tracking을 확인하고 다른 세션의 미커밋 변경을 보존해.
현재 단계 관련 파일만 stage해.

이번 목표는 Feature Dataset Version을 입력으로 받아 설비별 시간 순서를 보존한
multi-model Experiment Run을 비동기적으로 실행하고, validation 기준으로 모델과
threshold를 선택한 뒤 untouched held-out test 결과를 저장하는 것이다.

구현 범위:

1. Experiment Run orchestration
   - submit, queued, running, succeeded, failed, cancelled 상태
   - long-running training은 worker/CLI에서 실행
   - FastAPI request thread에서 전체 모델 학습 금지
   - idempotency key와 retry policy
   - worker crash 후 stale run recovery
   - progress와 candidate별 상태
2. Split Policy
   - 기본값: equipment/group별 chronological split
   - train/validation/test cutoff를 명시적으로 저장
   - 필요 시 gap/embargo
   - 동일 equipment가 각 split에 존재하더라도 시간 순서가 역전되지 않음
   - group holdout mode도 계약으로 지원 가능
   - random row split은 명시적 benchmark mode 외 기본값 금지
3. Candidate registry
   - 필수 후보:
     - Dummy prior baseline
     - Logistic Regression
     - Random Forest
   - capability 기반 선택 후보:
     - LightGBM
     - XGBoost
   - candidate spec에 hyperparameter, seed, dependency capability, input contract 포함
   - arbitrary class import나 user-provided Python 실행 금지
4. Optional dependency handling
   - LightGBM/XGBoost가 현재 Python/runtime에서 설치·지원되지 않으면
     `blocked_dependency`로 기록
   - optional candidate가 blocked/failed여도 baseline candidate와 Experiment Run은 계속
   - dependency version과 platform compatibility 기록
5. Imbalance policy
   - class weight, sample weight 또는 명시적 approved strategy
   - validation/test 분포를 변경하는 oversampling 금지
   - accuracy를 primary selection metric으로 사용하지 않음
6. Evaluation metrics
   - Average Precision / PR-AUC
   - ROC-AUC
   - Precision
   - Recall
   - F1
   - confusion matrix
   - positive prediction rate
   - Brier score와 calibration summary
   - sample count, positive count/rate
   - undefined metric은 임의 0으로 꾸미지 않고 reason과 함께 unavailable 처리
7. Slice evaluation
   - equipment/site/product type/criticality 등 approved low-cardinality dimension
   - minimum slice size
   - small slice suppression
   - evaluation truth나 hidden truth를 user-facing slice field로 사용하지 않음
8. Model selection
   - validation Average Precision를 기본 ranking metric으로 사용
   - recall constraint와 tie-break policy 명시
   - test split은 후보 선택과 threshold 선택에 사용하지 않음
   - Dummy baseline보다 의미 있게 낫지 않으면 no-promotion recommendation
9. Threshold selection
   - validation probabilities만 사용
   - minimum recall target
   - false-negative/false-positive cost policy
   - threshold curve artifact
   - recall-constrained threshold와 cost-minimizing threshold 분리
   - final selected threshold를 held-out test에 한 번 적용
10. Calibration
   - raw probability와 calibrated probability 구분
   - calibration 방법과 calibration split provenance
   - calibration 적용 전후 Brier score 또는 calibration error
   - calibration이 불가능하면 unavailable reason
11. Experiment artifact
   - source Dataset Version
   - Mapping Set, Feature Recipe Set, Feature Dataset Version, Label Policy
   - split policy/cutoff/embargo
   - candidate specs와 metrics
   - selected candidate와 threshold policy
   - held-out test metrics
   - random seed
   - library/runtime lock
   - artifact URI/checksum
   - limitations
12. API/CLI
   - experiment submit/list/detail/cancel/retry
   - worker entrypoint
   - candidate metrics와 artifact 조회
   - project/workspace/Dataset Version isolation

prototype_share처럼 전체 87만여 행을 학습하고 모델 파일만 저장한 뒤 완료로 처리하지 마.
다음과 같은 in-sample 점수는 release evidence가 아니다.

```text
ROC-AUC 1.0
PR-AUC 1.0
F1 nearly 1.0
```

시간순 held-out validation과 test 결과가 없는 모델은 promotion candidate가 될 수 없다.

중요:

- model 수가 많다는 이유로 우수하다고 판단하지 마.
- threshold 0.5를 모든 candidate의 운영 threshold로 고정하지 마.
- test split을 보고 hyperparameter, model, threshold를 다시 선택하지 마.
- failed candidate의 partial artifact를 성공 candidate처럼 등록하지 마.
- training artifact에 로컬 Windows path를 canonical URI로 저장하지 마.
- label horizon 이후 정보나 maintenance 결과를 feature로 누출하지 마.

필수 검증:

- equipment별 chronological ordering과 cutoff invariant
- validation/test 이전·이후 timestamp inversion 0
- embargo 적용
- random-row split default 금지
- Dummy/Logistic/RF candidate 실행
- LightGBM/XGBoost dependency available/blocked 두 경로
- optional candidate failure isolation
- Average Precision, ROC-AUC, precision, recall, F1, confusion matrix parity
- Brier/calibration artifact
- threshold가 validation에서만 선택되는 negative test
- held-out test가 selection 함수에 전달되지 않는 test
- minimum recall와 cost policy threshold 결과
- class imbalance와 zero-positive slice 처리
- small slice suppression
- same inputs/seed 재실행 reproducibility
- idempotent submit와 worker retry
- cancel/stale-run recovery
- cross-project Feature Dataset Version 참조 거부
- evaluation truth/hidden truth feature/slice leakage 거부
- synchronous train endpoint가 추가되지 않았는지 architecture test
- targeted ml/backend tests
- git diff --check

전체 frontend/visual regression은 실행하지 마. 필요한 API contract test까지만 수행해.

검증 완료 후 이번 단계 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: add time-aware model experiments"
- git push origin HEAD

push 실패 시 reset/rebase/force push 없이 오류와 로컬 commit hash를 보고해.

마지막 보고:

- Experiment Run과 worker 구조
- split/embargo 정책
- candidate별 상태와 dependency capability
- validation ranking, threshold, calibration, held-out test 결과
- baseline 대비 개선 여부
- lineage와 artifact checksum
- 변경 파일과 테스트
- commit hash와 push 결과
- Phase 14 promotion 대상으로 선택된 candidate identity
````
