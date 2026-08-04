# Predictive Maintenance Adaptive Modeling — 단계별 실행 프롬프트

- 작성일: 2026-08-04
- 대상 프로젝트: `/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2`
- 기준 데이터: `/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1`
- 참고 구현: `/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/prototype_share`
- 선행 작업: `docs/60-development-prompts/predictive-maintenance-canonical-v3.1/phase-08-governance-release.md`
- 전체 계획: `docs/30-implementation/predictive-maintenance-adaptive-modeling-integration-plan.md`

## 시작 조건

Phase 9는 다음 조건을 모두 충족한 후 시작한다.

1. V3.1 Phase 0~8이 코드·DB·API·UI·Git 이력에서 완료됐다.
2. V3.1 Dataset Version과 bundle checksum이 release report에 고정됐다.
3. Result Artifact, replay, semantic visualization, 역할별 Dashboard가 실제 V3.1
   데이터를 사용한다.
4. PostgreSQL과 Project 3/Neo4j readiness 또는 명확한 degraded/blocked evidence가 있다.
5. V2/V3.1 immutable lineage와 rollback이 검증됐다.

Phase 8이 완료되지 않았으면 Phase 9 구현을 시작하지 않는다. Phase 8의 미완료 항목을
모델링 트랙에서 우회하거나 재해석하지 않는다.

## 실행 순서

| 순서 | 파일 | 목표 |
|---:|---|---|
| 9 | `phase-09-contract-foundation.md` | Adaptive Modeling 계약과 persistence foundation |
| 10 | `phase-10-dataset-intake.md` | source profiling과 approved manifest draft |
| 11 | `phase-11-ontology-mapping-approval.md` | ontology mapping 승인과 capability prerequisite |
| 12 | `phase-12-feature-recipe-registry.md` | time-safe Feature Recipe Registry |
| 13 | `phase-13-experiment-evaluation.md` | multi-model temporal experiment와 평가 |
| 14 | `phase-14-model-registry-promotion.md` | governed model registry, promotion, explanation |
| 15 | `phase-15-ml-validator-workbench.md` | 실제 ML Validator Workbench |
| 16 | `phase-16-governance-release.md` | adaptive modeling end-to-end release |

## 공통 실행 규칙

1. 실제 checkout에서 작업한다.
2. 프로젝트별 `open_workspace`는 한 번만 호출하고 workspaceId를 재사용한다.
3. 시작 전에 branch, working tree, 최근 commit, remote tracking을 확인한다.
4. 다른 세션의 미커밋 변경을 삭제·덮어쓰기·stage하지 않는다.
5. `prototype_share`와 V3.1 package는 참고용으로 읽고 수정하지 않는다.
6. 프로토타입 코드를 통째로 복사하지 않고 프로젝트2의 기존 contract와 namespace에
   맞춰 재구현한다.
7. 현재 단계와 직접 관련된 파일만 stage한다.
8. additive migration을 사용하고 이미 적용된 migration을 수정하지 않는다.
9. targeted test를 먼저 실행하고, 전체 release gate는 Phase 16에서 수행한다.
10. 검증 완료 후 단계별 commit과 `git push origin HEAD`를 수행한다.
11. push 실패 시 reset/rebase/force push 없이 오류와 로컬 commit hash를 보고한다.
12. 외부 dependency나 credential이 없으면 성공으로 꾸미지 않고 capability를
    `blocked`로 기록한다.

## 절대 유지할 경계

- V3.1 canonical Dataset Version은 immutable이다.
- evaluation truth와 hidden truth는 training/evaluation policy가 명시적으로 허용한
  evaluator-only 경로 밖으로 노출하지 않는다.
- Project 3 graph/RAG/Text-to-Cypher 책임을 프로젝트2에 복제하지 않는다.
- long-running training을 synchronous FastAPI request에서 실행하지 않는다.
- LLM은 등록된 후보의 분류·재정렬·설명만 수행하고 임의 SQL/Python/feature/ontology를
  생성하지 않는다.
- model probability, calibrated confidence, policy threshold를 서로 다른 의미로 유지한다.
- recommended action을 승인·실행된 WorkOrder로 표시하지 않는다.
- LightGBM/XGBoost가 환경에서 지원되지 않아도 baseline experiment는 정상 동작한다.

## 최종 완료 상태

```text
Dataset Intake Profile
→ approved Manifest Draft
→ immutable Dataset Version
→ approved Ontology Mapping
→ Feature Dataset Version
→ queued Experiment Run
→ validation-based model and threshold selection
→ governed Model Version promotion
→ Prediction Result + Explanation Artifact
→ ML Validator and role Dashboard
```
