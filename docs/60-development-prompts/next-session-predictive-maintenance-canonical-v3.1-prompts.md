# Predictive Maintenance Canonical v3.1 — 다른 세션용 단계별 프롬프트

세부 프롬프트는 다음 디렉터리에 단계별 파일로 분리되어 있다.

`docs/60-development-prompts/predictive-maintenance-canonical-v3.1/`

진행 상태와 실행 순서:

1. `phase-00-contract-freeze.md` — 완료 (`1aa0251`)
2. `phase-01-bundle-adapter.md` — 완료 (`4b4d46f`)
3. `phase-02-postgresql-ingestion.md` — 완료 (`01a4a9b`)
4. `phase-03-ontology-materialization.md` — 완료 (`1a15af1`)
5. V3.1 release contract 정합성 보강 — 완료 (`6534aa5`)
6. `phase-04-neo4j-projection.md` — 완료 (`cada45c`)
7. `phase-05-prediction-replay.md` — 완료 (`3ce7069`)
8. `phase-06-semantic-visualization.md` — 완료 (`5bc5bee`)
9. `phase-07-dataset-dashboard.md` — 완료 (`05d6d9d`)
10. `phase-08-governance-release.md` — 완료 (`feature/predictive-maintenance-canonical-v3.1-complete`)

현재 배포 기준은 `predictive_maintenance_canonical_v3.1`이다. Phase 0~8 파일은
모두 완료 기록이므로 재실행하지 않는다. 후속 세션은 Adaptive Modeling Phase 9부터
시작한다.

최종 release 기준:

```text
source version          canonical-ai4i-physics-v3.1
bundle checksum         12734b1eec67ae5ccf322221967d5628ba5cf1ecb0401e6daef5c3dd7a855682
Dataset Version         dsv-1914858a-cc17-57d8-819c-d8a2435fd805
mapping version         predictive-maintenance-v3.1
phase4 payload ready    true
```

검증 결과:

```text
V3.1 package verifier      65 pass / 0 fail
Project2 backend tests     208 pass
Project3 targeted tests     37 pass + 8 subtests
PostgreSQL migration       pass
PostgreSQL runtime         pass
frontend unit/lint/build   pass
production capabilities   credential/service 미설정 항목 blocked
```

V3.1 전환의 세부 영향은 다음 문서를 먼저 확인한다.

`docs/30-implementation/predictive-maintenance-canonical-v3-upgrade-plan.md`

자세한 목차와 공통 규칙은 아래 파일을 참고한다.

`docs/60-development-prompts/predictive-maintenance-canonical-v3.1/README.md`

Phase 8 완료 후 후속 작업은 아래 진입점으로 전환한다.

`docs/60-development-prompts/next-session-predictive-maintenance-adaptive-modeling-prompts.md`
