# Ontology Dashboard — Remaining Work Execution Plan

- 작성일: 2026-08-02
- 목적: 새로운 ChatGPT 앱/DevSpace 세션이 현재 완료 상태를 정확히 이어받아 남은 작업을 우선순위대로 실행하기 위한 상세 계획
- 프로젝트 경로: `/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2`
- canonical product: `Ontology Dashboard`
- canonical Python namespace: `ontology_dashboard`
- 현재 branch baseline: `main`
- 현재 기준 HEAD: `37c9481655a3df18b95b13765251655bd738ba1f`

---

## 0. 이 문서의 사용법

새로운 작업 세션은 반드시 이 문서를 먼저 읽고, 한 세션에서 무리하게 전체 항목을 동시에 구현하지 않는다.

권장 방식:

1. 현재 working tree와 실행 환경을 확인한다.
2. 아래 Decision Gate에 따라 이번 세션의 실행 가능한 최우선 Phase를 고른다.
3. 해당 Phase의 완료 조건까지 구현·검증·문서화한다.
4. 다음 Phase에 필요한 blockers와 입력물을 명확하게 남긴다.
5. Git commit/push는 사용자가 별도로 명시적으로 요청하지 않으면 수행하지 않는다.

이 계획은 이미 완료된 기능을 다시 만드는 문서가 아니다. 특히 Palantir/Foundry UI 전면 개편 UI-00~UI-08, Analysis lifecycle, Dataset materialization, Project 3 typed boundary, Dashboard recovery, server-first cross-filter, Project tombstone, WorkOrder canonicalization을 반복 구현하지 않는다.

---

## 1. 현재 완료 상태

### 1.1 구현 성숙도

```text
Backend        98%
Frontend       98%
Architecture   97%
PostgreSQL     88%
Project Layer  96%
Adapter Layer  84%
```

이 수치는 코드·자동 테스트·로컬 검증 성숙도다. Managed infrastructure, production credentials, 외부 IdP, 실제 connector endpoint가 준비됐다는 의미는 아니다.

### 1.2 사용자 화면

다음 주요 제품 화면은 연결 및 자동 검증이 끝난 상태다.

```text
Project Home   CONNECTED
Dashboards     CONNECTED / SERVER-FIRST CROSS-FILTER
Analysis       CONNECTED / JOB LIFECYCLE / MATERIALIZATION
Agent          CONNECTED EVIDENCE WORKBENCH
Ontology       CONNECTED WORKBENCH / DEGRADED GRAPH SAFE
Datasets       CONNECTED CATALOG / IMMUTABLE VERSION DETAIL
Governance     CONNECTED PROJECT WORKBENCH
Admin          CONNECTED MEMBERSHIP / APPROVAL CONTROL PLANE
```

### 1.3 UI 개편 완료 범위

완료된 범위:

- UI-00 shared token and Foundry primitives
- UI-01 product shell and navigation
- UI-02 Project Home
- UI-03 Dashboard resource chrome/runtime
- UI-04 shared Workbench runtime
- UI-05 Object Explorer
- UI-06 Analysis authoring
- UI-07 Agent evidence terminal
- UI-08 Dataset/Governance detail polish
- 1440x1000, 1728x1117, 720x500 세 viewport
- baseline 24장 + final 24장 = 전용 manifest 관리 48장
- candidate visual diff와 release gate 연결

다음 파일군은 이미 구현된 UI의 핵심이므로 새로운 기능 요구 없이 전면 재작성하지 않는다.

```text
web/src/ui/foundry/
web/src/features/dashboard/
web/src/features/analysis/
web/src/features/ontology/
web/src/features/agent/
web/src/features/datasets/
web/src/features/governance/
docs/ui/palantir-overhaul/
web/e2e/workbench-final-overhaul.spec.ts
scripts/check_palantir_overhaul_visuals.py
```

### 1.4 자동 검증 baseline

2026-08-02 기준 확인된 결과:

```text
Backend pytest                           122 PASS
Gold scenarios                           8/8 PASS
Frontend Vitest                          6 PASS
TypeScript                               PASS
Production build                         PASS
Initial JavaScript                       228.07 KiB / 300 KiB PASS
Largest deferred JavaScript              443.24 KiB / 500 KiB PASS
Playwright E2E                           49 PASS / 3 INTENTIONAL SKIP
Final overhaul acceptance                8 PASS
48-image committed visual manifest       PASS
Candidate raw pixel max                  0.0618% / 0.15% PASS
Candidate changed pixels max             0.2074% / 0.75% PASS
Candidate structural delta max           0.0079% / 0.10% PASS
Release gate                             13/13 PASS
```

### 1.5 현재 working tree 보호 규칙

현재 checkout에는 UI-00~UI-08 관련 미커밋 변경과 기존 문서 변경이 함께 존재한다.

작업 시작 시 반드시:

```bash
git status --short --branch
git diff --stat
git diff --check
```

을 실행한다.

특히 다음 문서는 UI 작업 시작 전부터 수정 또는 생성돼 있던 파일이므로, 내용을 읽지 않고 덮어쓰거나 삭제하지 않는다.

```text
docs/next-session-master-prompt.md
docs/next-session-palantir-ui-overhaul-prompt.md
docs/palantir-ui-overhaul-master-plan.md
```

새 세션은 기존 변경을 되돌리지 않고 additive 또는 targeted edit 방식으로 작업한다.

---

## 2. Non-Negotiable Architecture Rules

1. 제품명은 `Ontology Dashboard`다.
2. 새로운 코드에 `Factory Signal Board` 제품명을 다시 도입하지 않는다.
3. canonical Python namespace는 `ontology_dashboard`다.
4. `Organization → Project → Workspace → Role Dashboard` 구조를 유지한다.
5. Project는 Dataset과 동일한 개념이 아니다.
6. Dataset, Ontology Mapping, Prediction Contract, Dashboard Template, Workspace, Analysis Run은 Project 안에서 연결된다.
7. Prediction logic과 Dashboard presentation logic을 혼합하지 않는다.
8. Project 3의 Text-to-Cypher, Neo4j, LangGraph correction/validation, RAG를 Project 2에 중복 구현하지 않는다.
9. Project 2는 Project 3을 typed HTTP client 경계로 호출한다.
10. arbitrary SQL/Cypher/Python/React 코드를 LLM 출력만으로 실행하지 않는다.
11. organization/project/workspace scope를 API, repository, worker, UI에서 함께 검증한다.
12. Evidence 없는 narrative나 Action을 자동 확정하지 않는다.
13. 외부 인프라나 credentials가 없으면 `blocked`로 보고하며 완료라고 주장하지 않는다.
14. 코드 변경과 관련 tests/docs를 함께 업데이트한다.
15. 기존 release gate 실패를 숨기거나 skip으로 우회하지 않는다.

---

## 3. Decision Gate — 이번 세션에서 무엇부터 할 것인가

새 세션 시작 즉시 다음 명령을 실행한다.

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/verify_production_environment.py
```

그 결과에 따라 분기한다.

### Case A — Docker와 managed credentials가 준비됨

다음 순서로 진행한다.

1. Phase 1 visual CI 상태 확인
2. Phase 2 production environment runbook
3. Phase 9 full production drill/evidence
4. 남는 시간에 Phase 3 namespace relocation

### Case B — 현재 Mac처럼 external capability가 blocked

다음 순서로 진행한다.

1. Phase 1 visual evidence 정리
2. Phase 3 physical namespace relocation
3. 승인된 원본 데이터가 있으면 Phase 4 full ingestion
4. connector endpoint/credentials가 있으면 Phase 5 REST connector

### Case C — Azure/MetroPT 전체 원본 파일이 제공됨

Phase 4를 Phase 3 다음 또는 사용자 지시 우선순위에 따라 바로 수행한다.

### Case D — 사용자가 특정 IdP, S3 endpoint, OTLP collector를 제공함

해당 외부 입력이 준비된 Phase를 앞당길 수 있다. 다만 tenant/project isolation과 현재 auth/permission 경계를 우회하지 않는다.

---

# Phase 0 — Current Change Set Stabilization

## 목표

현재 UI-00~UI-08 변경을 잃지 않고, 이후 backend/infra 작업의 안정적인 출발점을 만든다.

## 작업

1. branch, HEAD, remote divergence, working tree를 기록한다.
2. 현재 48-image manifest와 candidate capture가 일치하는지 확인한다.
3. frontend/backend 전체 baseline을 가능한 범위에서 재실행한다.
4. 기존 문서 변경과 이번 세션 변경을 구분한다.
5. 서버가 필요한 경우 공식 포트로 최신 소스를 재기동한다.

공식 local runtime:

```text
Frontend  http://127.0.0.1:3100/
API       http://127.0.0.1:8100/
Health    http://127.0.0.1:8100/health
```

권장 실행:

```bash
PYTHONPATH=api:ml/src .venv/bin/python -m uvicorn ontology_dashboard.main:app \
  --host 127.0.0.1 --port 8100

cd web
npm run dev
```

## 검증

```bash
git diff --check
cd web && npm run lint
cd web && npm run build
PYTHONPATH=api:ml/src .venv/bin/python -m pytest -q
PYTHONPATH=api:ml/src .venv/bin/python scripts/release_gate.py
```

전체 Playwright까지 실행할 여유가 있으면:

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/release_gate.py --with-e2e
```

## 완료 조건

- 기존 UI 변경이 보존됨
- release gate의 실패가 없음
- baseline 차이가 있으면 코드 문제, 환경 차이, fixture 차이를 구분해 보고함
- Git write는 사용자 요청 없이는 수행하지 않음

---

# Phase 1 — Final UI Review and Ubuntu Visual Calibration

## 목표

macOS에서 승인된 48장 baseline/final 증거를 Ubuntu CI에서도 안정적으로 검증하고, 현재 임시 cross-platform threshold를 실제 관측값에 맞게 조인다.

## 관련 파일

```text
.github/workflows/ci.yml
scripts/check_palantir_overhaul_visuals.py
scripts/release_gate.py
web/e2e/workbench-final-overhaul.spec.ts
web/e2e/palantir-overhaul-baseline.spec.ts
docs/ui/palantir-overhaul/visual-manifest.json
docs/ui/palantir-overhaul/scorecard.md
docs/ui/palantir-overhaul/README.md
docs/ui/palantir-overhaul/baseline/
docs/ui/palantir-overhaul/final/
```

## 작업 절차

### 1. Local integrity 확인

```bash
python3 scripts/check_palantir_overhaul_visuals.py
```

candidate가 존재하면:

```bash
python3 scripts/check_palantir_overhaul_visuals.py \
  --candidate-root web/test-results/palantir-overhaul-candidate \
  --require-candidate
```

### 2. Ubuntu CI artifact 수집

CI가 실행 가능한 상황에서 다음을 보존한다.

- Ubuntu candidate screenshots
- raw mean delta
- changed-pixel ratio
- blurred structural delta
- Playwright browser/version
- Ubuntu image/version
- font package 목록 또는 설치 단계

### 3. Threshold calibration

첫 성공 Ubuntu 24.04 artifact에서 관측한 structural maximum은 `1.5436%`다. 계획의 `observed max × 1.5~2.0` 원칙에 따라 cross-platform structural ceiling은 `2.4%`로 보정됐다.

실제 Ubuntu 최대값을 기준으로 다음 원칙을 적용한다.

```text
새 threshold = observed max × 1.5~2.0 safety margin
```

예:

```text
Observed max 0.31%
Recommended threshold 0.50~0.65%
```

단, 한 장만 유독 높은 경우 threshold부터 올리지 말고 다음을 먼저 조사한다.

- font fallback
- async chart animation
- timestamp/random ID
- data ordering
- scrollbar width
- viewport/deviceScaleFactor
- 브라우저 버전 차이

### 4. Product design review

48장의 final set을 surface별로 확인한다.

검토 항목:

- Dashboard/Analysis/Agent/Ontology 간 정보 밀도 일관성
- EntityTitle, StatusPill, WorkbenchHeader hierarchy
- 720px 화면의 document overflow 여부
- dark/light contrast와 chart label 가독성
- Object Explore와 Graph의 기능적 차별성
- Analysis path의 connector insertion affordance
- Dataset/Governance inspector tab 우선순위
- empty/loading/error/degraded state

## 완료 조건

- Ubuntu artifact가 검토됨
- cross-platform threshold가 근거 있는 수치로 보정됨
- 48장 manifest integrity가 유지됨
- 디자인 변경이 있으면 final screenshot, manifest, E2E, scorecard가 함께 갱신됨
- baseline approval capture는 opt-in guard 없이 덮어쓰지 않음

---

# Phase 2 — Production Environment Preflight and Runbook

## 목표

외부 capability를 코드 완료 상태와 분리해 판정하고, 준비된 환경에서는 실제 운영 증거를 생성한다.

## 관련 파일

```text
docs/production-environment-completion-runbook.md
scripts/verify_production_environment.py
scripts/release_gate.py
scripts/check_postgresql_migration.py
scripts/check_postgresql_runtime.py
scripts/verify_live_project3_hybrid.py
scripts/backup_database.py
infra/docker-compose.yml
```

## 현재 local host의 알려진 blockers

```text
compose          Docker CLI 미설치
postgresql       ONTOLOGY_DASHBOARD_DATABASE_URL 없음
redis            ONTOLOGY_DASHBOARD_REDIS_URL 없음
neo4j            URI/credentials 없음
project3         ONTOLOGY_DASHBOARD_PROJECT3_URL 없음
oidc             issuer/client credentials 없음
connectors       production endpoint 없음
object-storage   endpoint/bucket 없음
observability    OTEL exporter 없음
```

새 세션은 동일 상태를 재확인하되, blocker를 코드 오류로 오해하지 않는다.

## 작업 절차

1. informational verifier 실행
2. 준비된 capability만 strict gate에 포함
3. Docker host이면 cold-start drill
4. managed PostgreSQL이면 migration/RLS/backup/restore
5. Redis이면 two-instance consistency test
6. Neo4j/Project 3이면 live hybrid evidence
7. 실행 결과를 timestamp와 environment ID를 포함한 evidence 문서로 저장

strict 예:

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/verify_production_environment.py \
  --strict \
  --require compose \
  --require postgresql \
  --require redis \
  --require neo4j \
  --require project3
```

## 완료 조건

- configuration 존재가 아니라 실제 command output이 저장됨
- secret 값은 log/docs에 노출되지 않음
- project isolation failure `0`
- lost/duplicated Action `0`
- restore 후 release gate 통과
- 준비되지 않은 항목은 정확히 `blocked`로 남음

---

# Phase 3 — Physical Namespace Relocation

## 목표

`api/factory_signal_board/`에 남아 있는 실제 구현 모듈을 `api/ontology_dashboard/` 아래의 canonical package로 단계적으로 이동하고, 최종적으로 `ontology_dashboard.__path__` legacy extension을 제거한다.

현재 임시 동작:

```python
# api/ontology_dashboard/__init__.py
_LEGACY_MODULE_PATH = ... / "factory_signal_board"
__path__.append(str(_LEGACY_MODULE_PATH))
```

이 방식은 runtime 호환성을 제공하지만 physical architecture debt다.

## 핵심 원칙

- 한 번에 30개 파일을 rename하는 broad rewrite를 하지 않는다.
- 작은 compatibility slice마다 tests를 통과시킨다.
- runtime object identity와 singleton repository가 이중 생성되지 않게 한다.
- canonical import를 먼저 만들고 legacy import는 thin re-export shim으로 줄인다.
- final cleanup 전까지 기존 API route와 persisted data contract를 유지한다.

## Step 3.1 — Import graph inventory

다음 항목을 조사해 문서화한다.

- `ontology_dashboard.<module>`로 import되는 legacy physical module
- 상대 import와 절대 import
- module-level singleton/repository/cache
- circular dependency
- tests가 직접 import하는 경로
- package metadata와 console entrypoint

권장 명령:

```bash
rg -n "ontology_dashboard\.|factory_signal_board\." api tests scripts
rg -n "from \.|import \w+" api/factory_signal_board
PYTHONPATH=api:ml/src .venv/bin/python -c \
  "import ontology_dashboard; print(list(ontology_dashboard.__path__))"
```

결과를 migration matrix로 기록한다.

권장 matrix columns:

```text
legacy file
canonical destination
public symbols
inbound imports
stateful singleton 여부
compatibility shim 필요 여부
targeted tests
migration status
```

## Step 3.2 — Slice A: Foundation and Identity

Status: `DONE` on 2026-08-02. The eight implementations now live under `api/ontology_dashboard/`, their legacy files are thin re-export shims, canonical import provenance and repository object identity are tested, and `scripts/preflight.py` points to canonical source files. See `docs/physical-namespace-relocation-inventory.md`.

후보 파일:

```text
context.py
contracts.py
security.py
identity_models.py
identity_repository.py
identity.py
repository.py
service.py
```

권장 destination은 책임에 따라 결정한다.

예:

```text
ontology_dashboard/identity/
ontology_dashboard/security/
ontology_dashboard/core/
```

단순히 파일 이름을 그대로 복사하기보다 현재 `application.py`, `dependencies.py`, `projects/` 구조와 중복을 먼저 확인한다.

검증:

```bash
PYTHONPATH=api:ml/src .venv/bin/python -m pytest -q \
  tests/test_auth_rbac.py \
  tests/test_project_layer.py \
  tests/test_architecture_debt_stage44.py
```

## Step 3.3 — Slice B: Dashboard

Status: `NEXT`.

후보 파일:

```text
dashboard_models.py
dashboard_repository.py
dashboard_service.py
dashboard_catalog.py
```

권장 destination:

```text
ontology_dashboard/dashboards/
```

보존해야 할 contract:

- role template resolution
- mandatory boards
- saved view/share/export linkage
- project scope
- server-first filter contract
- Dashboard recovery compatibility

## Step 3.4 — Slice C: Analysis

후보 파일:

```text
analysis_models.py
analysis_repository.py
analysis_service.py
```

권장 destination:

```text
ontology_dashboard/analysis/
```

보존해야 할 contract:

- queued/running/succeeded/failed/cancelled
- progress checkpoint
- cache identity
- cursor pagination
- immutable Dataset Version materialization
- project/workspace scope

## Step 3.5 — Slice D: Export and Role Workflow

후보 파일:

```text
export_models.py
export_repository.py
export_service.py
role_workflow_models.py
role_workflow_repository.py
role_workflow_service.py
```

권장 destination:

```text
ontology_dashboard/exports/
ontology_dashboard/workflows/
```

보존해야 할 contract:

- permission checks
- export checkpoint
- audit linkage
- transactional outbox
- WorkOrder canonical name
- deprecated Inspection compatibility only where required

## Step 3.6 — Slice E: Ontology and Planner

후보 파일:

```text
ontology_adapter.py
ontology_planner_models.py
ontology_planner_service.py
ontology_repository.py
ontology_service.py
ontology.py
planner.py
reports.py
conversation.py
llm.py
```

이미 존재하는 다음 canonical modules와 중복 여부를 먼저 확인한다.

```text
ontology_dashboard/ontology_instance_repository.py
ontology_dashboard/planner/
ontology_dashboard/orchestration/
ontology_dashboard/integrations/project3/
```

중요:

- Project 3 Text-to-Cypher/LangGraph/RAG를 이 slice에서 재구현하지 않는다.
- `llm.py`가 legacy façade인지 실제 책임인지 확인 후, typed Project 3 client 또는 orchestration port와 중복이면 축소한다.
- ontology action permission과 project-scoped traversal을 유지한다.

## Step 3.7 — Compatibility Shims

각 legacy 파일은 필요한 기간 동안 다음 형태의 thin shim만 허용한다.

```python
from ontology_dashboard.<canonical_module> import *
```

하지만 star import가 public API를 불명확하게 만들면 명시적 symbol re-export를 사용한다.

shim에는 다음을 넣지 않는다.

- 새로운 business logic
- repository instance 생성
- side effect
- 별도 cache
- duplicated constants

## Step 3.8 — Remove Path Extension

모든 physical module 이전과 import 검증 후:

1. `api/ontology_dashboard/__init__.py`의 `__path__.append(...)` 제거
2. architecture debt test를 강화해 재도입 방지
3. package metadata/entrypoint 확인
4. `factory_signal_board.main`은 필요 시 한시적 executable shim으로만 유지
5. 더 이상 import되지 않는 legacy 구현 파일 제거
6. `.pyc`, `__pycache__`, stale egg-info는 source artifact로 취급하지 않음

최종 guard 예:

```text
- ontology_dashboard package path는 한 디렉터리만 포함
- canonical runtime import가 api/factory_signal_board 파일을 로드하지 않음
- source에서 factory_signal_board import는 승인된 compatibility test/shim 외 0건
```

## Phase 3 완료 조건

- `ontology_dashboard.__path__` extension 제거
- canonical package만으로 API boot 가능
- backend 122+ tests 회귀 없음
- architecture debt guard 통과
- release gate 통과
- migration 과정과 최종 module map을 docs에 기록
- legacy namespace가 제품명 또는 신규 code path로 재등장하지 않음

---

# Phase 4 — Full Azure and MetroPT Dataset Ingestion

## 목표

현재 showcase fixtures를 실제 공개 원본의 immutable Dataset Version, provenance, profile, projection, Dashboard/Analysis evidence로 확장한다.

## 현재 상태

존재하는 fixture:

```text
data/fixtures/adapters/azure-fleet-maintenance-fixture.csv
data/fixtures/adapters/azure-fleet-maintenance-manifest.json
data/fixtures/adapters/metropt-compressor-fixture.csv
data/fixtures/adapters/metropt-compressor-manifest.json
```

이 fixture는 multi-project 추상화와 UI flow를 검증하지만 full dataset 통계를 의미하지 않는다.

## 입력 조건

다음 없이는 full ingestion을 완료했다고 주장하지 않는다.

- 승인된 source 파일
- source URL 또는 전달 경로
- 라이선스/사용 조건
- 원본 checksum
- dataset version naming rule
- Azure five-file relation key 정의
- MetroPT timestamp/timezone/interval 정의

## Step 4.1 — Raw source staging

권장 구조:

```text
data/sources/azure-fleet/<source-version>/
data/sources/metropt/<source-version>/
data/manifests/
data/provenance/
```

원본은 변형하지 않고 read-only input으로 유지한다.

## Step 4.2 — Provenance artifact

각 source마다 저장:

```text
source name
source version
retrieved_at
license
original URI 또는 delivery reference
file size
SHA-256
row count
column list
encoding
compression
known caveats
```

## Step 4.3 — Adapter hardening

관련 파일:

```text
api/ontology_dashboard/adapters/azure_fleet.py
api/ontology_dashboard/adapters/metropt.py
api/ontology_dashboard/adapters/file_adapter.py
api/ontology_dashboard/adapters/models.py
api/ontology_dashboard/adapters/service.py
scripts/ingest_dataset.py
```

필수 기능:

- deterministic manifest
- schema validation
- invalid row quarantine
- type coercion report
- duplicate key detection
- referential integrity report
- timestamp normalization
- chunked processing
- idempotent retry
- Dataset Version immutability

## Step 4.4 — Azure five-file ingestion

관계형 source를 하나의 flat CSV처럼 취급하지 않는다.

검증 대상:

- machines
- telemetry
- errors
- maintenance
- failures

필수 join/quality evidence:

- machine ID coverage
- telemetry timestamp uniqueness
- error-to-machine relation
- maintenance component domain
- failure component domain
- orphan rows
- source별 min/max timestamp

발표 지표는 ingestion 후 코드로 재계산한다.

예:

- error type별 24시간 내 failure conversion
- preventive/corrective maintenance interval
- machine model·age peer cohort
- failure component별 lead-time distribution

## Step 4.5 — MetroPT high-density ingestion

필수 고려:

- timestamp ordering
- sampling interval drift
- missing windows
- sensor null/outlier
- pressure/temperature/current unit
- high-density pagination and profile cost
- chunk/checkpoint strategy

전체 raw rows를 frontend로 직접 내려보내지 않는다. Dataset profile, governed aggregate, time-window cursor를 사용한다.

## Step 4.6 — Projection and product linkage

각 Dataset Version에 대해:

```text
PostgreSQL operational record
Neo4j relationship projection request
Project 3 RAG/document projection where applicable
projection status
retry/dead-letter
lineage evidence
```

UI 검증:

- Dataset detail tabs
- Analysis input selection
- Dashboard server query
- Ontology object/link
- Governance projection health
- Agent evidence provenance

## 테스트

```bash
PYTHONPATH=api:ml/src .venv/bin/python -m pytest -q \
  tests/test_adapter_layer.py \
  tests/test_adapter_api.py \
  tests/test_dataset_projection_stage47.py
```

대규모 데이터 tests는 작은 deterministic fixture와 별도 opt-in integration test로 분리한다.

## 완료 조건

- source checksum/provenance 존재
- immutable Dataset Version 생성
- quarantine와 quality report 존재
- Azure/MetroPT 전체 row count가 artifact에 기록
- project scope가 분리됨
- Dashboard/Analysis/Ontology/Governance에서 동일 version identity 사용
- fixture 지표를 full-dataset 지표로 과장하지 않음

---

# Phase 5 — First Production Connector: REST

## 목표

file adapter 다음의 첫 실제 외부 protocol로 REST polling connector를 productionize한다.

REST를 먼저 선택하는 이유:

- credentials, pagination, retry, checkpoint, schema drift를 비교적 단순하게 검증 가능
- Kafka/MQTT/OPC-UA 이전에 공통 connector contract를 안정화 가능
- Governance UI와 operational health model을 먼저 완성 가능

## 관련 기존 파일

```text
api/ontology_dashboard/adapters/protocol.py
api/ontology_dashboard/adapters/registry.py
api/ontology_dashboard/adapters/models.py
api/ontology_dashboard/adapters/repository.py
api/ontology_dashboard/adapters/service.py
api/ontology_dashboard/routers/adapters.py
```

## 제안 신규 구조

```text
api/ontology_dashboard/connectors/
  __init__.py
  models.py
  protocol.py
  repository.py
  service.py
  rest.py
```

기존 adapter layer와 별도 package가 필요한지는 먼저 책임을 비교한다. 불필요한 추상화 중복은 만들지 않는다.

## 필수 contract

```text
organization_id
project_id
dataset identity
connector identity
base URL
credential reference
pagination strategy
checkpoint/offset
retry/backoff
circuit state
schema compatibility policy
quarantine policy
freshness SLA
last success/failure
lineage metadata
```

## 보안

- raw token/password를 DB manifest나 log에 저장하지 않는다.
- secret reference만 persistence한다.
- request/response payload redaction policy를 둔다.
- SSRF 방어를 적용한다.
- redirect, timeout, response-size, content-type 제한을 둔다.
- arbitrary URL을 일반 사용자가 자유 입력해 server가 호출하게 하지 않는다.

## Runtime behavior

- cursor/page/next-link pagination
- idempotency key 또는 source record identity
- conditional request 가능 시 ETag/Last-Modified
- bounded concurrency
- exponential backoff + jitter
- retryable/non-retryable 분류
- circuit breaker
- checkpoint commit order
- replay from checkpoint
- schema drift decision
- invalid record quarantine

## API/UI

첫 protocol 확정 후에만 connector setup 화면을 추가한다.

필요 화면:

- connector list
- create/edit configuration
- secret reference 상태
- test connection
- run/replay
- checkpoint
- health/degraded
- last error redacted detail
- Governance lineage

권한:

- Organization admin 또는 승인된 FDE만 configuration 변경
- 일반 analyst는 health/read-only
- secret 값은 어느 역할에도 재표시하지 않음

## 테스트

- mocked REST server
- pagination
- 429 Retry-After
- 500 retry
- 401 non-retryable/credential state
- timeout
- malformed JSON
- schema drift
- replay duplicate prevention
- project isolation
- SSRF deny cases

## 완료 조건

- 실제 또는 승인된 staging endpoint로 end-to-end run
- checkpoint와 replay evidence
- duplicate `0`
- secret leakage `0`
- Governance health 표시
- connector-created Dataset Version과 lineage 확인

---

# Phase 6 — OIDC and Identity Lifecycle

## 목표

현재 검증된 local cookie identity/RBAC를 유지하면서 외부 IdP를 연결한다.

## 선행 입력

- IdP 선택
- issuer
- client ID/secret
- callback URLs
- logout URL
- claims mapping
- invitation/reset ownership 정책
- MFA/SCIM 필요 여부

## 설계 원칙

- IdP authentication과 application authorization을 분리한다.
- IdP role claim을 그대로 superuser 권한으로 신뢰하지 않는다.
- Organization/Project membership은 application repository에서 검증한다.
- current project role, self-lockout prevention, audit를 유지한다.
- local test users는 dev/test profile에서만 유지한다.

## 작업

1. IdP-agnostic OIDC client port
2. authorization request/state/nonce/PKCE
3. callback validation
4. subject-to-identity mapping
5. Organization/Project membership resolution
6. session rotation and revocation
7. logout
8. invitation policy
9. email verification/reset delegation 결정
10. suspended user/membership 처리
11. audit events

## 테스트

- state/nonce mismatch
- expired token
- wrong issuer/audience
- missing email
- existing subject
- same email different subject
- suspended membership
- role downgrade
- project switch
- logout/revocation
- local auth disabled production profile

## 완료 조건

- staging IdP 실제 login/logout
- invitation/reset 정책 문서화
- application permission 우회 없음
- tenant/project isolation tests 통과
- secret가 repository/log에 노출되지 않음

---

# Phase 7 — S3-Compatible Artifact Storage

## 목표

Dataset files, Analysis materialization, export, backup manifest를 local filesystem에 묶지 않고 immutable object storage에 저장한다.

## 제안 contract

```text
ArtifactStore
- put_stream
- get_stream
- head
- verify_checksum
- create_signed_download
- delete_with_audit
- list_version_artifacts
```

## Key policy

권장 key:

```text
organizations/{organization_id}/projects/{project_id}/
  datasets/{dataset_id}/versions/{version_id}/{artifact_kind}/{sha256}-{filename}
```

키에 사용자 제공 경로를 그대로 사용하지 않는다.

## 필수 기능

- multipart upload
- SHA-256 write/read verification
- immutable/versioned key
- content type
- size limit
- encryption policy
- signed URL permission check
- short expiry
- retention/legal hold 결정
- deletion audit
- orphan cleanup

## 구현 profile

- local filesystem implementation: test/dev
- S3-compatible implementation: staging/production
- MinIO 또는 cloud S3는 adapter로 교체 가능하게 구성

## 테스트

- checksum mismatch
- partial upload
- permission denial
- expired signed URL
- cross-project key access
- duplicate content
- delete audit
- restore manifest

## 완료 조건

- Dataset/Analysis/export 중 최소 한 실제 artifact flow가 S3-backed
- checksum round trip
- signed URL scope/expiry 검증
- project isolation failure `0`
- backup inventory artifact 생성

---

# Phase 8 — OpenTelemetry and Operational Observability

## 목표

API, worker, Analysis, Agent, Project 3 call을 하나의 request/run correlation으로 추적한다.

## 필수 correlation IDs

```text
request_id
organization_id
project_id
workspace_id
analysis_run_id
agent_run_id
workflow_id
outbox_event_id
project3_request_id
```

민감한 ID는 필요에 따라 hash/low-cardinality representation을 사용한다.

## Trace coverage

- HTTP request
- repository transaction
- outbox enqueue/delivery
- Analysis checkpoints
- Agent checkpoints
- Dataset projection
- Project 3 typed calls
- connector polls/retries
- object storage writes

## Metrics

- request count/error/latency
- PostgreSQL pool wait/timeout
- transaction rollback
- Redis errors
- outbox retry/dead-letter
- Analysis queue/run duration
- Agent claim validation failure
- projection failure/retry
- Project 3 circuit open
- connector freshness lag
- object-storage checksum failure

## Logging rules

- structured JSON
- secret/token/cookie 제거
- raw evidence payload 기본 비출력
- arbitrary user query masking policy
- traceback와 request ID 연결

## Alerts

최소:

- pool exhaustion
- outbox dead letter > 0
- projection failure sustained
- Project 3 circuit open
- connector freshness SLA breach
- authentication anomaly
- object storage write/checksum failure

## 완료 조건

- OTLP collector에 실제 trace 전송
- 한 Analysis run과 한 Agent run의 end-to-end trace 확인
- logs/traces 간 request/run ID 상호 검색 가능
- secret scan 통과
- alert test 또는 synthetic trigger evidence

---

# Phase 9 — Production Drill and Release Evidence

## 목표

코드가 존재한다는 것과 production-ready evidence를 구분하고, 실제 복구·부하·장애 검증 결과를 남긴다.

## 환경

최소:

- 2 API instances
- 1 outbox worker
- managed 또는 production-like PostgreSQL
- Redis
- Neo4j
- Project 3
- object storage
- OTLP collector

## Drill 9.1 — Cold start

```bash
docker compose -f infra/docker-compose.yml down -v --remove-orphans
docker compose -f infra/docker-compose.yml pull
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml ps
PYTHONPATH=api:ml/src .venv/bin/python scripts/release_gate.py --with-e2e
```

## Drill 9.2 — Migration idempotency

- empty DB migration
- restart
- migration 재실행
- current version 확인
- backward-compatible deploy 확인

## Drill 9.3 — Load

최소 30분:

- burst login
- Dashboard query
- Analysis run
- Agent query
- Action/outbox
- connector poll

측정:

```text
P50/P95/P99
pool wait/timeout
rollback rate
outbox retry/dead-letter
rate-limit consistency
cross-project isolation failures
lost/duplicated action
```

## Drill 9.4 — Failure injection

- PostgreSQL connection interruption
- Redis interruption
- Neo4j interruption
- Project 3 timeout
- object storage write failure
- worker restart

각 장애에서 사용자 화면의 degraded/error 상태와 retry 정책을 확인한다.

## Drill 9.5 — Backup/restore

- PostgreSQL backup
- object storage inventory/checksum manifest
- 새 환경 restore
- migrations
- release gate
- Project/Dashboard/Action/Dataset/Analysis/Agent scope 확인

## Drill 9.6 — Rollback

- image tag와 migration version 기록
- controlled failure
- app rollback
- 필요한 경우에만 DB restore
- data contract 확인

## Evidence 저장 규칙

각 evidence 문서는 다음을 포함한다.

```text
environment ID
git SHA
image tag
timestamp/timezone
command
exit code
sanitized output
metrics summary
artifact paths
pass/blocked/fail
follow-up
```

## 완료 조건

- 복구가 실제 새 환경에서 검증됨
- project isolation failure `0`
- lost/duplicated Action `0`
- RTO/RPO 관측값 기록
- 모든 release gate 통과
- 실패한 항목은 숨기지 않고 issue/next action으로 남김

---

# Phase 10 — Documentation and Completion Gate

## 반드시 업데이트할 문서

작업 범위에 따라 다음을 갱신한다.

```text
docs/03-project-roadmap.md
docs/04-release-checklist.md
docs/05-dataset-strategy.md
docs/06-project-catalog.md
docs/07-implementation-status.md
docs/09-architecture-decisions.md
docs/production-environment-completion-runbook.md
이 문서
```

architecture 변경이면 ADR을 추가한다.

## 최종 검증 matrix

### Backend

```bash
PYTHONPATH=api:ml/src .venv/bin/python -m pytest -q
PYTHONPATH=api:ml/src .venv/bin/python -m compileall -q api scripts
```

### Frontend

```bash
cd web
npm test
npm run lint
npm run build
```

### Visual/E2E

```bash
cd web
npm run test:e2e:overhaul
npm run test:visual:overhaul
```

전체:

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/release_gate.py --with-e2e
```

### Git quality

```bash
git diff --check
git status --short --branch
```

## 완료 보고 형식

세션 종료 시 반드시 다음을 보고한다.

1. 이번 세션에서 선택한 Phase와 선택 근거
2. 실제 구현 내용
3. 주요 변경 파일
4. API/routes/roles/permissions 영향
5. database/migration 영향
6. dataset/provenance 영향
7. 테스트와 release gate 실제 결과
8. 생성한 screenshot/evidence/report
9. 외부 blocker
10. 다음 최우선 작업
11. Git commit/push 수행 여부

---

## 11. 권장 실행 순서 요약

```text
R0  Current change set stabilization
R1  Ubuntu visual calibration + product design review
R2  Production capability preflight
R3  Physical namespace relocation
R4  Full Azure/MetroPT ingestion
R5  REST connector productionization
R6  OIDC identity lifecycle
R7  S3-compatible artifact storage
R8  OpenTelemetry observability
R9  Production cold-start/load/failure/restore/rollback evidence
R10 Documentation and release completion
```

환경이 없는 local Mac에서 실제로 바로 실행 가능한 핵심 순서는:

```text
R0 → R1(local portion) → R3 → R4(source가 있을 때)
```

외부 환경/credentials가 준비된 host에서는:

```text
R0 → R1(CI) → R2 → R9 → R5/R6/R7/R8
```

---

# 12. 새 ChatGPT 앱에 붙여넣을 실행 프롬프트

아래 내용을 새 채팅에 그대로 붙여넣는다.

```text
@devspace.mcp

다음 로컬 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

가장 먼저 docs/next-session-remaining-work-execution-plan.md를 읽고, 이어서 아래 문서를 순서대로 검토해줘.

1. docs/next-session-master-prompt.md
2. docs/00-project-charter.md
3. docs/01-system-architecture.md
4. docs/02-domain-model.md
5. docs/03-project-roadmap.md
6. docs/04-release-checklist.md
7. docs/05-dataset-strategy.md
8. docs/06-project-catalog.md
9. docs/07-implementation-status.md
10. docs/08-devspace-workflow.md
11. docs/09-architecture-decisions.md
12. docs/production-environment-completion-runbook.md

문서만 믿지 말고 현재 source, tests, migrations, frontend routes, visual artifacts, git working tree와 비교해서 실제 상태를 확인해줘.

작업 시작 시 반드시 다음을 수행해.

- git status --short --branch와 git diff --stat로 기존 미커밋 변경을 파악
- 기존 변경을 되돌리거나 덮어쓰지 않기
- PYTHONPATH=api:ml/src .venv/bin/python scripts/verify_production_environment.py 실행
- 실행 환경에 따라 remaining-work plan의 Decision Gate로 이번 세션의 최우선 Phase 선택
- 선택한 Phase를 설계 문서만 작성하고 끝내지 말고 가능한 코드, runtime, tests, evidence까지 완료

현재 Palantir/Foundry UI 전면 개편 UI-00~UI-08, Analysis lifecycle, Dataset materialization, Dashboard undo/recovery, server-first cross-filter, Dataset Catalog, Agent/Governance pagination, WorkOrder canonicalization, Project 3 typed boundary는 완료 상태이므로 반복 구현하지 마.

반드시 다음 원칙을 지켜줘.

- 제품명과 canonical namespace는 Ontology Dashboard / ontology_dashboard로 유지
- Factory Signal Board 이름이나 namespace를 새 코드에 다시 만들지 않기
- Organization → Project → Workspace → Role Dashboard 구조 유지
- Project를 Dataset과 동일시하지 않기
- Prediction과 Dashboard를 Prediction Result Contract로 분리
- PostgreSQL operational data, Neo4j relationship graph, Project 3 RAG를 동일 Project identity로 연결
- Project 3 Text-to-Cypher/LangGraph/RAG를 Project 2에 중복 구현하지 않고 typed client로 재사용
- 검증되지 않은 arbitrary SQL/Cypher/Python/React 실행 금지
- tenant/project scope를 API, repository, worker, UI에서 검증
- 외부 infrastructure나 credentials가 없으면 blocked로 정확히 보고하고 완료라고 주장하지 않기
- 코드 변경 시 tests와 관련 docs를 함께 업데이트
- release gate 실패를 skip이나 threshold 완화로 숨기지 않기
- Git commit/push는 내가 별도로 명시적으로 요청하지 않는 한 수행하지 않기

현재 host에서 Docker/managed credentials가 blocked이면 remaining-work plan의 Phase 3 Physical Namespace Relocation부터 작은 compatibility slice로 진행해. 한 번에 broad rename하지 말고 import graph inventory → foundation/identity → dashboard → analysis → export/workflow → ontology/planner → compatibility shim 제거 → ontology_dashboard.__path__ extension 제거 순서로 진행해.

2026-08-02 현재 import graph inventory, foundation/identity, Dashboard, Analysis, Export/Workflow slice는 완료됐다. 다음 세션은 완료 slice를 반복하지 말고 remaining Ontology slice부터 진행한다.

승인된 Azure/MetroPT 전체 source 파일이 확인되면 Phase 4 full ingestion을 진행하되 fixture 통계를 full dataset 통계로 과장하지 말고 source checksum, provenance, immutable Dataset Version, quarantine, projection lineage를 반드시 남겨.

작업 완료 후 다음을 보고해.

1. 선택한 Phase와 이유
2. 실제 구현 내용과 사용자 흐름
3. 주요 변경 파일
4. architecture/database/dataset 영향
5. tests, E2E, visual, release gate 실제 결과
6. 생성한 evidence 또는 screenshot
7. external blockers
8. 구현률 변화
9. 다음 최우선 작업
10. Git write 수행 여부
```

---

# 13. 특정 Phase만 지시할 때 사용하는 짧은 프롬프트

```text
@devspace.mcp

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2 를 실제 checkout 모드로 열고 docs/next-session-remaining-work-execution-plan.md를 먼저 읽어줘.

기존 working tree를 보존한 상태에서 이번 세션에는 Phase [번호/이름]만 완료 조건까지 실행해. 관련 source, tests, migrations, docs를 함께 수정하고 targeted tests 후 가능한 전체 release gate를 실행해. 이미 완료된 UI-00~UI-08 및 기존 lifecycle 기능은 반복 구현하지 마. 외부 capability가 없으면 추측하지 말고 blocked evidence를 남겨. Git commit/push는 하지 마.

마지막에 변경 파일, 실제 테스트 결과, 남은 blocker와 다음 Phase를 보고해.
```
