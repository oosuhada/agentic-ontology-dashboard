# Phase 08 — V3.1 Governance and Release Verification

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

Project 3 변경과 통합 검증이 필요하면 다음 프로젝트도 실제 checkout 모드로 열되,
먼저 현재 연결 contract와 health 상태를 확인해.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트3

V3.1 데이터 패키지는 읽기 전용 기준 artifact로 확인해줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1

먼저 아래를 읽고 Phase 0~7의 실제 완료 상태를 코드·DB·API·UI·Git 이력으로
검증해줘.

- docs/30-implementation/predictive-maintenance-canonical-v2-integration-plan.md
- docs/30-implementation/predictive-maintenance-canonical-v3-upgrade-plan.md
- docs/60-development-prompts/predictive-maintenance-canonical-v3.1/README.md
- Phase 0~7 prompt와 관련 커밋
- 최소 완료 기준 커밋 `1aa0251`, `4b4d46f`, `01a4a9b`, `1a15af1`, `6534aa5`
- docs/20-architecture/predictive-maintenance-projection-contract.md
- docs/20-architecture/architecture-decisions.md
- docs/10-product/dataset-strategy.md
- docs/30-implementation/product-convergence-roadmap.md
- predictive_maintenance_canonical_v3.1/README.md
- predictive_maintenance_canonical_v3.1/FINAL_AUDIT_REPORT.md
- predictive_maintenance_canonical_v3.1/V3_1_RELEASE_VERIFICATION.md
- predictive_maintenance_canonical_v3.1/canonical/validation/package_validation.json
- predictive_maintenance_canonical_v3.1/experiments/connected_air_supply/experiment_manifest.json
- scripts/release_gate.py
- scripts/verify_production_environment.py
- Dataset/Governance/Outbox/Backup 관련 코드와 runbook

각 저장소에서 git status --short --branch, git log -12 --oneline, remote tracking을
확인하고 다른 세션의 미커밋 변경을 보존해. 이번 단계 수정만 stage해.

이번 목표는 V3.1 domain pack의 운영·거버넌스·복구·release 기준을 완성하고, V2에서
V3.1로의 immutable upgrade와 V3.1 end-to-end vertical을 검증하는 것이다.

현재 V3.1 baseline identity는 다음과 같다. 최종 release에서는 실제 DB/API 결과가
이 기준과 일치하는지 확인하되, 다른 Project나 재생성 seed의 값으로 임의 대체하지 마.

```text
source version          canonical-ai4i-physics-v3.1
bundle checksum         12734b1eec67ae5ccf322221967d5628ba5cf1ecb0401e6daef5c3dd7a855682
Dataset Version         dsv-1914858a-cc17-57d8-819c-d8a2435fd805
model                   independent-logreg-v3.1
Result Artifact schema  result-artifact-v1.0
mapping version         predictive-maintenance-v3.1
```

구현 범위:

1. V2/V3.1 lineage
   - V2 generation/package/bundle/Dataset Version 보존
   - V3.1 generation run
   - V3.1 package validation, ai4i_physics, tool_wear_continuity gate
   - V3.1 bundle checksum
   - ingestion run과 Dataset Version
   - ontology mapping/materialization
   - PostgreSQL/Neo4j projection
   - Result Artifact/prediction/replay
   - visualization query/board
   - V2와 V3가 같은 Dataset의 다른 immutable version인지 확인
   - V3.1 Dataset Version profile에 package-validation 및 agent-evaluation checksum,
     release identity, tool-wear continuity, maintenance-evidence summary가 보존됐는지 확인
2. Governance UI/API
   - source version, schema/source-contract/checksum diff
   - V2/V3.1 row-count diff
   - AI4I contract와 physical validation summary
   - Result Artifact schema/model task/coverage
   - PostgreSQL ready와 Neo4j ready/degraded
   - projection attempt/error/retry history
   - 사용한 Dataset Version과 source reference
   - package validation 상세 truth row는 숨기고 안전한 집계 gate만 표시
3. retry/recovery
   - failed V3.1 ingestion은 partial ready가 아님
   - failed graph projection 재시도
   - V3.1 re-ingestion idempotency
   - V2 rollback/select 가능
   - backup/restore 또는 V3.1 package에서 재생성 가능한 runbook
4. security and semantics negative controls
   - tenant/project/workspace isolation
   - evaluation truth leakage 차단
   - experiment hidden truth leakage 차단
   - stale/wrong Dataset Version projection 차단
   - unauthorized action/export/query 차단
   - binary predicted type을 failure-mode multiclass로 오표시하지 않음
   - recommended action을 승인/실행된 WorkOrder로 오표시하지 않음
   - topology edge를 causal confirmation으로 오표시하지 않음
   - `CAUSES`, `ROOT_CAUSE_OF` graph projection 요청 거부
   - package validation의 `event_condition_details`, `condition_variant`, failure timestamp
     비노출
5. Agent benchmark
   - optional experiment는 production source와 분리
   - positive_upstream_relation 16건
   - negative_local_only 4건
   - `NO_UPSTREAM_RELATION`, `claim_status=unlikely`, null upstream 채점
   - negative rejection accuracy
   - false upstream claim rate
   - smoke example case IDs를 formal benchmark score에서 제외
   - hidden_truth는 evaluator-only
6. documentation
   - V3.1 생성/검증 → manifest → PostgreSQL → Ontology → Neo4j → Replay → Dashboard
   - V2에서 V3로 새 Dataset Version 등록 절차
   - Result Artifact 소비 계약
   - 환경 변수와 로컬 Docker Compose 절차
   - 실패 복구와 V3.1 재생성 절차
   - demo limitation: synthetic canonical data, replay not live sensor server,
     binary model not failure-mode classifier
7. release readiness
   - 완료 기능과 외부 환경 때문에 blocked인 기능 구분
   - 성공하지 않은 검증을 통과했다고 표시하지 않기
   - V3.1 package audit 숫자와 프로젝트2 DB/API 숫자 parity
   - Phase 4 outbox payload와 Project3 graph request의 source/model/schema/release-gate
     provenance parity

최종 V3.1 E2E 시나리오:

1. V3.1 package의 `validate_package.py`, `ai4i_physics.pass`, `tool_wear_continuity.pass` 확인
2. V3.1 bundle manifest/checksum 검증
3. V2와 다른 새 V3.1 Dataset Version ingestion
4. 정확한 V3.1 row count와 Result Artifact 100건 확인
5. Site/Cell/Equipment/Risk/Prediction/WorkOrder Ontology materialization
6. Project 3를 통한 Neo4j projection
   - materialized domain object 1,984건과 relationship 2,160건 parity
   - DatasetVersionReference를 node로 만들었다면 별도 1건으로 구분
7. topology graph relation query와 causality semantics 확인
8. latest Result Artifact와 prediction/replay query
9. AI4I-aware planner가 목적에 맞는 chart 선택
10. 역할별 Dashboard 렌더
11. 사용자 chart override 저장·reload
12. V2/V3.1 Dataset Version 전환과 rollback
13. 모든 결과에서 Dataset Version/source/model/schema provenance 확인
14. positive/negative Agent benchmark 실행
15. maintenance evidence canonical matching과 invalid evidence rejection 확인

V3.1 기준 row count:

```text
assets                    100
relations                  80
compressor observations 86400
CNC observations        345600
production cycles       170875
maintenance events         790
prediction snapshots       100
prediction factors         300
prediction timeline      68208
result artifacts            100
```

V3.1 release gate 기준:

```text
running reset                         0
tool replacement events             731
aligned reset transitions           731
reset without maintenance             0
replacement without reset             0
positive upstream accuracy           1.0
negative rejection accuracy          1.0
false upstream claim rate            0.0
maintenance evidence accuracy        1.0
```

필수 검증:

- Phase별 targeted tests 전체
- V2/V3.1 manifest compatibility와 checksum regression
- additive PostgreSQL migration/runtime checks
- V3.1 row-count parity와 Result Artifact contract
- V3.1 package AI4I physics와 tool-wear continuity summary parity
- Dataset Version profile/outbox/Project3 request의 V3.1 release evidence checksum parity
- Agent maintenance evidence canonical matching과 invalid evidence rejection
- Project 3 contract/degraded-mode tests
- graph projected domain node 1,984 / relationship 2,160 parity 또는 명확한
  DatasetVersionReference 추가 count 설명
- evaluation truth/hidden truth leakage negative tests
- negative local-only rejection과 false-upstream-claim test
- binary/recommended-action/topology semantics negative tests
- `CAUSES`, `ROOT_CAUSE_OF`, raw sensor/timeline graph payload 거부 test
- backend full pytest 또는 합리적으로 분리된 전체 test suite
- frontend typecheck/build
- 핵심 Playwright E2E
- 최종 visual regression manifest와 baseline check
- python scripts/preflight.py
- python scripts/verify_production_environment.py
- python scripts/release_gate.py
- git diff --check

외부 credential, Docker, Project 3 endpoint 등으로 일부 gate가 실행 불가능하면 임의로
성공 처리하지 말고 blocked 이유와 이미 통과한 local 검증을 정확히 분리해. 고칠 수
있는 코드·설정 문제는 이 세션에서 수정하고 다시 검증해.

최종 문서와 검증 artifact를 추가·갱신하고 이번 단계 관련 파일만 stage해서 다음을
수행해줘.

- git commit -m "chore: finalize predictive maintenance v3.1 release"
- git push origin HEAD

Project 3에 별도 수정이 있다면 저장소별로 별도 commit/push하고 hash를 구분해.
push 실패 시 reset/rebase/force push 없이 오류와 로컬 commit hash를 보고해.

마지막 보고에는 반드시 다음을 포함해줘.

- Phase 0~8 완료 여부 표
- V2/V3.1 Dataset Version identity와 checksum
- V3.1 데이터 row count와 Result Artifact coverage
- AI4I physics gate 결과
- PostgreSQL/Neo4j readiness
- 최종 E2E 결과
- Agent positive/negative benchmark와 false-upstream-claim 결과
- security/semantics negative test 결과
- release gate 결과와 blocked 항목
- 주요 URL과 실행 명령
- 변경 파일
- 저장소별 commit hash와 push 결과
- 실제로 남은 작업이 있다면 우선순위 순 목록
````
