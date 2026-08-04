# Predictive Maintenance Adaptive Modeling — 다른 세션용 단계별 프롬프트

이 트랙은 `predictive-maintenance-canonical-v3.1` Phase 8 완료 후 시작한다.

전체 작업 계획:

`docs/30-implementation/predictive-maintenance-adaptive-modeling-integration-plan.md`

세부 프롬프트 디렉터리:

`docs/60-development-prompts/predictive-maintenance-adaptive-modeling/`

실행 순서:

1. `phase-09-contract-foundation.md`
2. `phase-10-dataset-intake.md`
3. `phase-11-ontology-mapping-approval.md`
4. `phase-12-feature-recipe-registry.md`
5. `phase-13-experiment-evaluation.md`
6. `phase-14-model-registry-promotion.md`
7. `phase-15-ml-validator-workbench.md`
8. `phase-16-governance-release.md`

현재는 V3.1 Phase 4가 다음 실행 단계다. Phase 4~8을 완료하기 전에는 위 Phase 9를
실행하지 않는다. Phase 8 완료 보고에 실제 commit hash, V3.1 Dataset Version,
PostgreSQL/Neo4j readiness, Result Artifact coverage, release gate 결과가 남아 있어야 한다.

Phase 9부터는 다음 방향으로 팀원 `prototype_share`를 흡수한다.

```text
prototype_share의 아이디어
  구조 분석
  온톨로지 기반 feature catalog
  multi-model 비교
  SHAP 설명

프로젝트2의 제품 경계
  Dataset Version
  mapping approval
  Feature Recipe Version
  Experiment Run
  Model Registry와 promotion
  Prediction Result / Explanation Artifact
  ML Validator Workbench
```

각 파일을 새 개발 세션에 하나씩 전체 복사해 사용한다. 한 세션에서 여러 Phase를
임의로 합치지 않는다.
