# Stage 45 — Adaptive Modeling governance and release summary

- 검증일: 2026-08-05
- 대상: `feature/predictive-maintenance-adaptive-modeling`
- 선행 release: Predictive Maintenance Canonical v3.1
- 결과: **local release pass / strict production release blocked**

## Phase 완료 감사

| Phase | 결과 | 실제 closure evidence |
|---:|---|---|
| 9 | 완료 | typed contracts, generated Draft 2020-12 schema, SQLite/PostgreSQL additive migration, scope/idempotency/artifact foundation |
| 10 | 완료 | CSV/TSV/XLSX full-checksum profile, bounded/redacted preview, allowed-root/symlink guard, Manifest Draft approval |
| 11 | 완료 | registry-bound mapping, critical-field human approval, datatype/unit/grain validation, capability prerequisites |
| 12 | 완료 | group/time-safe recipes, boundary reset, future leakage test, immutable Feature Dataset artifact |
| 13 | 완료 | queued run, worker/CLI, group chronological split, Dummy baseline, validation-only selection, held-out test, cancel/retry/stale recovery |
| 14 | 완료 | portable Model Version, promotion gate, tenant-admin approval, atomic activation/rollback, Prediction Result and Explanation |
| 15 | 완료 | 실제 Experiment/Model API, leaderboard, PR/ROC, threshold/calibration, lineage, release/rollback UI, empty/error/blocked states, role flow Playwright와 desktop/tablet/mobile pixel baseline |
| 16 | local 완료 | controlled source-to-serving E2E, PostgreSQL RLS runtime, Canonical v3.1 invariance, release verifier와 runbook. Production endpoints/dependencies는 blocked |

## Controlled E2E evidence

한 번의 release evidence run에서 다음이 확인됐다.

| 항목 | 값 |
|---|---:|
| Source rows | 360 |
| Adapter accepted rows | 360 |
| Quarantined rows | 0 |
| Feature Dataset rows | 360 |
| Equipment groups | 3 |
| Derived features | 4 |
| Candidate models | 3 |
| Persisted Prediction Results | 1 |

후보 결과:

| Algorithm | Validation AP | ROC-AUC | Brier | Selected | Held-out test AP |
|---|---:|---:|---:|---|---:|
| Dummy prior | 0.2917 | 0.5000 | 0.2160 | No | unavailable |
| Logistic Regression | 0.5882 | 0.8824 | 0.1667 | **Yes** | 0.5003 |
| Random Forest | 0.2917 | 0.5000 | 0.2917 | No | unavailable |

운영 threshold는 0.33이며 validation recall은 0.9524다. Candidate table의 default 0.5
confusion matrix precision/recall이 0인 것과 운영 threshold 평가는 다른 scope다. UI는 이를
별도 panel로 표시한다.

## E2E identity chain

```text
source SHA-256
→ Dataset Intake cache checksum
→ approved Manifest Draft revision
→ immutable Dataset Version
→ approved Mapping Set checksum
→ approved Feature Recipe Set checksum
→ Feature Dataset Version checksum
→ Label Policy
→ Experiment Run and chronological split
→ validation-selected candidate and held-out metrics
→ Model Version artifact checksum
→ threshold policy
→ Prediction Result
→ Explanation Artifact checksum
```

실행 evidence는 `ADAPTIVE_MODELING_EVIDENCE_OUTPUT`을 설정하고
`tests/test_adaptive_modeling_e2e.py`를 실행해 JSON으로 재생성할 수 있다.

## Prototype closure matrix

| Prototype 진단 | Product closure | 상태 |
|---|---|---|
| preview cache identity가 filename/부분 내용 | full source SHA-256 + parser version | 완료 |
| 직접 auto-exclusion | Manifest Draft revision과 human approval | 완료 |
| tiny string ontology | registry-bound Object Type/Property + datatype/unit/grain | 완료 |
| high-confidence critical auto mapping | identifier/timestamp/label human approval 강제 | 완료 |
| single-node capability | prerequisite bundle과 missing reason | 완료 |
| ungrouped rolling | equipment group/order/boundary reset | 완료 |
| unversioned feature config | Feature Recipe version/checksum | 완료 |
| whole-data/random training | group chronological train/validation/test | 완료 |
| baseline/metrics 부족 | Dummy baseline, AP/ROC/precision/recall/F1/Brier/confusion/calibration | 완료 |
| fixed 0.5 threshold | validation recall/cost policy | 완료 |
| duplicated explanation parsing | provider abstraction과 common Explanation Artifact | 완료 |
| JSON/Windows-path registry | SQL registry + portable `artifact://` URI/checksum | 완료 |
| synchronous training API | queued Experiment + one-shot worker CLI | 완료 |
| static model cards | actual ML Validator Workbench | 완료 |
| no tests/docs | 53 targeted tests, controlled E2E, verifier, runbook | 완료 |
| false MCP naming | Dataset Intake/Adapter terminology | 완료 |

## 발견하고 보완한 주요 결함

1. Phase 12 test fixture가 필수 recipe contract를 누락해 허위 실패했다.
2. Pandas datetime resolution 차이로 horizon label이 잘못 계산될 수 있었다.
3. PostgreSQL 환경에서 Modeling dependency가 즉시 RuntimeError를 발생시켰다.
4. PostgreSQL repository가 JSONB/RLS transaction scope를 지원하지 않았다.
5. release/activate/rollback API가 `governance.read` permission만 요구했다.
6. frontend POST가 API base/CSRF를 사용하지 않아 실제 클릭이 실패했다.
7. ML Validator route와 navigation이 없어 component가 제품에서 접근 불가능했다.
8. Model activation이 retire와 activate 두 transaction으로 분리돼 concurrent active 2개가
   생길 수 있었다.
9. worker cancel/stale recovery가 없었다.
10. Model promotion이 succeeded status만 보고 baseline/recall/test/lineage/runtime을 충분히
    재검증하지 않았다.
11. scoring이 existing Prediction Result repository에 저장되지 않았다.
12. Experiment report에 PR/ROC curve가 없었다.
13. JSON Schema가 실제 Pydantic 계약보다 오래돼 Model Version 필드를 거부했다.
14. approved Manifest Draft에서 기존 Adapter와 Dataset Version으로 이어지는 경로가 없었다.
15. File Adapter가 optional approved alias를 누락해 측정값을 빈 문자열로 만들었다.
16. CSV delimiter와 XLSX sheet가 profile에는 있었지만 ingestion에는 적용되지 않았다.

모두 코드와 regression test로 보완했다.

## Verification results

- Canonical v3.1 verifier: 65 pass, 0 blocked, 0 fail
- Adaptive source-to-serving targeted suite: 53 pass
- Project 2 backend full suite: 255 pass
- Project 3 graph/scope/readiness/Text-to-Cypher regression: 40 pass + 8 subtests
- Controlled E2E: pass
- PostgreSQL JSONB/idempotency/RLS runtime: pass
- ML Validator component: 3 pass
- ML Validator Playwright/visual: 6 pass
- TypeScript: pass
- Frontend production build: pass
- General release gate: 13/13 pass
- Adaptive release verifier local result: pass, fail 0

## Blocked production capabilities

- LightGBM
- XGBoost
- SHAP
- production PostgreSQL URL
- durable production modeling artifact root
- Project 3 endpoint
- Neo4j endpoint

이 항목들은 현재 shell에 설정되지 않아 strict release에서 blocked다. 로컬 disposable
PostgreSQL 검증 통과를 production credential readiness로 오해하지 않는다.

## 실제 남은 작업

1. ML Validator 안에서 source/mapping/recipe를 직접 authoring하는 통합 UI
2. worker daemon/scheduler와 heartbeat registry
3. S3/GCS artifact-store adapter와 disaster-recovery exercise
4. calibration artifact와 confidence policy
5. operational drift/outcome artifact
6. production environment variable/credential 구성 후 strict verifier 재실행
