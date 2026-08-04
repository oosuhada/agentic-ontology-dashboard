# Predictive Maintenance Canonical v3.1 — 단계별 실행 프롬프트

- 작성일: 2026-08-04
- 대상 프로젝트: `/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2`
- 현재 배포 기준 패키지: `/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1`
- V2 패키지: backward compatibility와 immutable lineage 회귀 검증에만 사용
- 기존 계획: `docs/30-implementation/predictive-maintenance-canonical-v2-integration-plan.md`
- V3.1 전환 계획: `docs/30-implementation/predictive-maintenance-canonical-v3-upgrade-plan.md`
- V3.1 graph projection 계약: `docs/20-architecture/predictive-maintenance-projection-contract.md`

Phase 0~8은 모두 완료 기록이다. 이 디렉터리의 프롬프트를 다시 실행하지 말고,
회귀 검증 또는 구현 근거 확인에만 사용한다. 후속 개발은 Adaptive Modeling
Phase 9 진입점으로 전환한다.

| 순서 | 파일 | 목표 |
|---:|---|---|
| 0 | `phase-00-contract-freeze.md` | 완료 기록 — Bundle Manifest와 identity 계약 |
| 1 | `phase-01-bundle-adapter.md` | 완료 기록 — V2/V3.1 version-aware Bundle Adapter |
| 2 | `phase-02-postgresql-ingestion.md` | 완료 기록 — PostgreSQL COPY 원자적 적재 |
| 3 | `phase-03-ontology-materialization.md` | 완료 기록 — V3.1 compatibility, Result Artifact, Ontology materialization |
| 4 | `phase-04-neo4j-projection.md` | 완료 — V3.1 Project 3/Neo4j projection과 degraded mode |
| 5 | `phase-05-prediction-replay.md` | 완료 — Result Artifact 우선 API, timeline query, replay/SSE |
| 6 | `phase-06-semantic-visualization.md` | 완료 — AI4I-aware Semantic Field Catalog와 typed chart query planner |
| 7 | `phase-07-dataset-dashboard.md` | 완료 — V3.1 Dataset 기반 역할별 Dashboard와 chart controls |
| 8 | `phase-08-governance-release.md` | 완료 — V2/V3.1 lineage와 최종 release 검증 |

## 공통 실행 규칙

각 프롬프트에는 아래 규칙이 포함되어 있다.

1. 실제 checkout에서 작업한다.
2. 시작 전에 현재 branch, working tree, 최근 커밋을 확인한다.
3. 다른 세션의 미커밋 변경을 삭제·덮어쓰기·커밋하지 않는다.
4. 현재 단계와 직접 관련된 파일만 stage한다.
5. 단계별 targeted test를 먼저 실행한다.
6. 최종 단계 전까지 불필요한 전체 visual regression이나 release gate를 반복하지 않는다.
7. 검증 통과 후 현재 branch에 commit하고 `git push origin HEAD`를 실행한다.
8. push가 인증·권한·네트워크 문제로 실패하면 이력을 재작성하지 말고 정확한 오류와 로컬 commit hash를 보고한다.

## 현재 진행 상태

```text
Phase 0  완료  1aa0251
Phase 1  완료  4b4d46f
Phase 2  완료  01a4a9b
Phase 3  완료  1a15af1
V3.1 정합성 보강  완료  6534aa5
Phase 4  완료  cada45c
Phase 5  완료  3ce7069
Phase 6  완료  5bc5bee
Phase 7  완료  05d6d9d
Phase 8  완료  feature/predictive-maintenance-canonical-v3.1-complete
```

V3.1 immutable release 기준 상태:

```text
source version          canonical-ai4i-physics-v3.1
bundle checksum         12734b1eec67ae5ccf322221967d5628ba5cf1ecb0401e6daef5c3dd7a855682
Dataset Version         dsv-1914858a-cc17-57d8-819c-d8a2435fd805
mapping version         predictive-maintenance-v3.1
Ontology objects        1,984
Ontology links          2,160
graph projection        typed Project 3 contract 완료
Result Artifact         100
prediction timeline     68,208
tool wear gate          731 replacement / 731 aligned reset
```

최종 local release gate는 backend 208 tests, PostgreSQL migration/runtime, visual
baseline, frontend unit/lint/build를 모두 통과했다. 실제 production credential이 필요한
Docker Compose, Redis, Neo4j, Project 3 URL, OIDC, object storage, observability는 별도
environment gate에서 blocked로 유지한다.

## 데이터 연결 완료 기준

Phase 0~4가 완료되면 V3.1 데이터는 다음 경로로 제품에 연결된 상태다.

```text
V3.1 canonical bundle + Result Artifact
→ checksum validation
→ PostgreSQL Dataset Version 및 fact tables
→ Ontology objects/links
→ V3.1 release evidence를 포함한 outbox
→ Project 3
→ Neo4j projection
```

V2 Dataset Version은 삭제하거나 V3.1로 덮어쓰지 않는다. V3.1 release 검증은
`scripts/verify_predictive_maintenance_v3_1_release.py`와
`docs/50-operations/predictive-maintenance-v3.1-release-runbook.md`를 사용한다.

## Phase 8 이후 후속 트랙

Phase 8 완료 후에는 `prototype_share`의 데이터 구조 분석, ontology-aware feature
catalog, multi-model 비교, SHAP 아이디어를 프로젝트2의 governance 경계에 맞게
재구현하는 Adaptive Modeling 트랙으로 이어간다.

- 계획: `docs/30-implementation/predictive-maintenance-adaptive-modeling-integration-plan.md`
- 프롬프트: `docs/60-development-prompts/predictive-maintenance-adaptive-modeling/`
- 다음 단계: `phase-09-contract-foundation.md`

Phase 8 release가 완료됐으므로 다음 실행 단계는 `phase-09-contract-foundation.md`다.
