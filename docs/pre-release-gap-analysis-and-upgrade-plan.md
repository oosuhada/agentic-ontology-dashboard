# Ontology Dashboard 배포 전 종합 Gap 분석 및 업그레이드 계획

- 작성일: 2026-08-01
- 분석 대상 브랜치: `feat/ontology-dashboard-foundation`
- 기준 문서: `docs/next-session-ontology-dashboard-prompt.md`, `docs/ontology-dashboard-additional-implementation-plan.md`
- 분석 관점: 기능 존재 여부가 아니라 로직 완결성, 아키텍처 경계, 실제 데이터 전환성, 사용자 사용성, 보안, 운영, 배포 가능성

---

# 1. 결론

현재 프로젝트는 **발표·데모용 vertical slice로는 높은 완성도**를 갖췄다.

검증 결과:

- Gold fixture 8/8 통과
- Backend test 53건 통과
- Playwright E2E 13건 통과
- TypeScript strict check 통과
- React production build 통과
- Python package consistency 통과
- npm production dependency audit 취약점 0건

그러나 문서의 16~31단계가 모두 `완료`로 표시된 것과 달리, 제품 성숙도는 다음처럼 구분해야 한다.

| 수준 | 현재 평가 | 설명 |
|---|---:|---|
| 발표·데모 readiness | 85% | 역할별 화면, 인증, RBAC, Dashboard 편집, 승인, Planner, export가 하나의 시나리오로 작동한다. |
| 내부 파일럿 readiness | 60% | 실제 사용자와 제한된 실제 데이터를 연결하려면 persistence, tenant isolation, 운영 설정, UX 보완이 필요하다. |
| 외부 production readiness | 35~45% | 현재 ontology와 역할 workspace가 fixture 중심이며, 단일 SQLite·single process·개발 설정에 의존한다. |

가장 중요한 판단은 다음과 같다.

> 16~31단계는 “범용 Ontology Dashboard 제품이 완성되었다”기보다, 그 제품의 API·UI·권한·workflow를 검증하는 **제조 domain 기반 executable prototype**이 완성된 상태다.

다음 단계는 기능 수를 늘리는 작업보다 **실데이터·실운영 전환과 구조 안정화**여야 한다.

---

# 2. 현재 실행·저장소 상태

## 2.1 Git

현재 상태:

- 브랜치: `feat/ontology-dashboard-foundation`
- 마지막 commit:
  - `7b0c587 feat: add ontology dashboard auth rbac and admin foundation`
  - `47eefeb feat: complete Factory Signal Board MVP`
- 수정 파일: 26개
- untracked 파일: 32개
- tracked diff: 약 3,536 insertions / 251 deletions
- `git diff --check`: 통과
- Git 사용자:
  - name: `oosuhada`
  - email: `185910926+oosuhada@users.noreply.github.com`
- Git remote: **설정되어 있지 않음**

즉, 19~31단계의 대부분이 아직 commit되지 않은 하나의 큰 작업 묶음이다. 배포 전에는 기능별 commit으로 분리하고, remote를 설정한 뒤 PR 또는 release branch로 보존해야 한다.

## 2.2 실행 중 서비스

현재 Mac에서 확인된 listener:

```text
127.0.0.1:3100  Node/Vite frontend
127.0.0.1:8100  Python/FastAPI backend
```

두 서비스 모두 localhost에만 bind되어 있으므로 LAN 또는 Tailscale IP로 직접 접근할 수는 없다. SSH local port forwarding을 사용하면 소스 수정 없이 안전하게 외부 tailnet 기기에서 접근할 수 있다.

## 2.3 검증 한계

- 현재 DevSpace shell에는 `docker` 명령이 없어 `docker compose config`, image build, container healthcheck는 검증하지 못했다.
- E2E는 Chromium 한 종류, 단일 worker, 임시 SQLite, 로컬 프로세스 기준이다.
- Frontend unit test는 1건뿐이다.
- 실제 provider, 실제 production data, PostgreSQL, Redis, object storage, reverse proxy 환경은 검증하지 않았다.

---

# 3. 16~31단계 실질 구현 성숙도

아래 비율은 코드 존재량이 아니라 **배포 가능한 제품 기능으로서의 완성도 추정치**다.

| 단계 | 문서 상태 | 실질 성숙도 | 판단 |
|---|---|---:|---|
| 16 제품 reframe | 완료 | 80% | 표시명·계약·domain pack 개념은 반영됐다. 내부 package와 런타임은 여전히 제조 fixture 중심이다. |
| 17 인증 | 완료 | 75% | Argon2id, cookie session, CSRF, pending/disabled가 작동한다. 이메일 검증, 초대, reset, MFA/SSO, production cookie/domain 정책은 없다. |
| 18 RBAC/admin | 완료 | 70% | 서버 permission과 workspace scope는 있다. organization 경계가 실질적으로 단일 demo 조직이며 multi-role UX와 tenant별 admin isolation이 미완성이다. |
| 19 Ontology adapter | 완료 | 55% | Object·Link·Action projection은 작동한다. Registry와 instance가 static Python/fixture projection이며 범용 persistent ontology runtime은 아니다. |
| 20 persistence | 완료 | 70% | Template·preference·saved view·share가 SQLite에 저장된다. migration framework, FK 완결성, production DB locking/backup 전략은 없다. |
| 21 Dashboard shell | 완료 | 75% | shell 구조는 구현됐다. 계획된 deep route가 실제 resource route로 분리되지 않고 `/app/*`가 동일 앱으로 귀결된다. |
| 22 personalization | 완료 | 70% | override와 optimistic revision이 있다. 실시간 multi-session conflict UX, undo, draft autosave, template merge 시각화가 부족하다. |
| 23 Board catalog | 완료 | 65% | 역할별 catalog와 안전 검증이 있다. 실제 grid resize/drag UX는 HTML5 drag 기반이며 복잡한 대시보드 편집기 수준은 아니다. |
| 24 parameter/cross-filter/share | 완료 | 60% | parameter와 dependency graph가 있다. 일부 cross-filter는 실제 query recomputation보다 선택 상태·영향 표시 중심이다. |
| 25 Executive | 완료 | 65% | fixture aggregate와 가정 표시는 좋다. 조직·기간·실제 비용 데이터, drill path, KPI 정의 governance가 없다. |
| 26 Audit | 완료 | 70% | snapshot·hash·trace가 있다. tamper-evident append-only storage, retention, legal hold, signed artifact는 없다. |
| 27 Field | 완료 | 55% | 모바일 action은 작동한다. 실제 사진 upload, offline queue, sync conflict, device permission, 현장 오류 복구는 없다. |
| 28 FDE | 완료 | 60% | preview·diagnostic·approval 경계가 있다. 실제 datasource connector lifecycle, schema diff, deployment promotion은 없다. |
| 29 ML Console | 완료 | 55% | model/policy scope 분리는 명확하다. 실제 experiment tracking, registry, drift job, deployment 연결은 없다. |
| 30 Planner | 완료 | 45% | 안전한 typed planner shell은 있다. provider 품질·latency·cost·prompt regression과 실제 데이터 평가가 없다. |
| 31 release hardening | 완료 | 50% | 로컬 gate는 강하다. production infra, distributed rate limit, migration, observability, backup/restore는 미구현이다. |

---

# 4. 잘 구현된 부분

## 4.1 회귀 안전성

- 기존 manager·engineer Gold flow를 유지하면서 새 역할과 Dashboard 플랫폼을 확장했다.
- 기존 Evidence·Report·Layout 계약을 한 번에 폐기하지 않고 adapter로 감쌌다.
- 53개 backend test와 13개 E2E가 핵심 시나리오를 고정한다.

## 4.2 권한 경계

- 일반 사용자와 tenant admin route/API가 분리되어 있다.
- FDE가 직접 template publish를 할 수 없고 승인 요청을 거친다.
- workspace scope는 API에서 재검사한다.
- share token이 object scope를 우회하지 않도록 조회 시 권한을 다시 계산한다.
- Action은 permission, target ObjectType, parameter, idempotency를 서버에서 검증한다.

## 4.3 안전한 LLM 경계

- arbitrary SQL, Cypher, React code 실행 대신 typed intent와 catalog whitelist를 사용한다.
- provider 장애 시 기존 Dashboard를 유지한다.
- recommendation과 draft가 자동 persistence되지 않는다.
- narrative claim에 Evidence reference를 요구한다.

## 4.4 Dashboard platform foundation

- role template → user override → session state 구분이 코드에 반영되어 있다.
- mandatory board를 서버에서도 보호한다.
- template version과 stable board ID 기반 merge가 있다.
- saved view와 share를 별도 개념으로 분리했다.

---

# 5. 핵심 Gap 분석

# 5.1 P0 — 배포를 막는 항목

## P0-1. Docker/production 실행 설정이 fail-safe하지 않음

`infra/docker-compose.yml`은 현재 다음을 API container에 전달하지 않는다.

```text
APP_ENV
SEED_DEMO_ACCOUNTS
production CORS origin
cookie/domain/proxy 설정
```

현재 코드의 기본값은 `APP_ENV=development`다. 따라서 Compose를 그대로 서버에 올리면:

- demo account가 자동 seed될 수 있음
- session cookie가 Secure가 아님
- HSTS가 적용되지 않음
- CORS가 localhost origin만 허용됨

### 개선

- `APP_ENV` 기본값을 production image에서는 명시적으로 `production`으로 설정
- production 시작 시 아래 조건을 검사하고 하나라도 잘못되면 프로세스 종료
  - `SEED_DEMO_ACCOUNTS != 1`
  - HTTPS/proxy 인식 설정 존재
  - production origin allowlist 존재
  - DB URL이 SQLite local path가 아님
  - secret/config validation 통과
- development compose와 production compose를 분리

## P0-2. 실제 Ontology instance store가 없음

현재 Ontology는 다음 형태다.

```text
static ObjectType/LinkType/ActionType constants
+ Gold fixture
+ legacy operational SQLite records
→ request마다 ObjectRecord/LinkRecord snapshot projection
```

이 구조는 adapter 검증에는 적합하지만 다음이 어렵다.

- 새 domain pack runtime 등록
- 수십만 object 검색
- incremental ingestion
- relation update
- schema version migration
- datasource lineage
- object-level policy

### 개선

PostgreSQL 기준으로 최소 다음 저장 계층을 도입한다.

```text
ontology_schemas
object_types
property_types
link_types
action_types
objects
object_properties 또는 JSONB
links
source_mappings
ingestion_runs
schema_versions
```

초기에는 graph DB를 바로 도입하지 않고 PostgreSQL + indexed JSONB + relation table로 시작한다. graph traversal 요구가 명확해진 뒤 Neo4j 또는 graph extension을 평가한다.

## P0-3. SQLite와 idempotency/action transaction 경계

Ontology Action은 현재 다음 순서로 서로 다른 DB connection을 사용한다.

```text
invocation reserve
→ legacy side effect 기록
→ audit 기록
→ invocation succeed
```

중간 단계에서 실패하면 side effect는 이미 저장됐지만 invocation은 failed가 될 수 있다. 같은 idempotency key 재시도도 `prior_action_failed`로 차단되므로 운영자가 복구하기 어렵다.

### 개선

- PostgreSQL transaction 안에서 Action state, domain write, audit/outbox를 원자적으로 저장
- 외부 side effect는 transactional outbox로 분리
- Action state에 `retryable`, `compensation_required`, `reconciled` 추가
- stuck `running` invocation을 감지하는 reconciliation job 추가

## P0-4. 실질적인 multi-tenant isolation이 없음

schema에는 organization이 있지만 현재 동작은 단일 demo organization과 단일 manufacturing workspace를 중심으로 한다.

위험:

- tenant admin이 모든 workspace와 user를 조회하는 구조
- admin query가 organization_id로 제한되지 않음
- email과 workspace slug가 global unique
- tenant boundary test가 없음
- tenant-scoped encryption/retention 정책이 없음

### 개선

- 모든 principal에 `organization_id` 포함
- 모든 user/workspace/template/audit/export query에 organization predicate 강제
- repository 호출 시 `TenantContext`를 필수 인자로 사용
- PostgreSQL Row Level Security 또는 최소 repository-level tenant guard 도입
- cross-tenant negative test를 별도 matrix로 추가

## P0-5. production observability·backup·restore가 없음

현재 health endpoint는 process 응답 여부만 확인한다.

필요 항목:

- structured JSON logging
- request/correlation ID
- authentication·permission denial metrics
- DB health, migration version, provider health
- OpenTelemetry trace
- error tracking
- PostgreSQL backup 및 restore drill
- export artifact retention
- audit retention과 legal hold

## P0-6. 저장소 변경량이 하나의 미커밋 묶음임

58개 변경 파일이 한 번에 남아 있다. 이 상태로 추가 작업을 이어가면 회귀 원인 추적과 rollback이 어렵다.

### 개선

다음 단위로 commit을 분리한다.

1. Stage 19 Ontology adapter
2. Stage 20~24 Dashboard platform
3. Stage 25~29 Role workspaces
4. Stage 30 Planner
5. Stage 31 Export/security/release gate
6. 종합 분석·문서

이미 working tree에서 단계가 섞여 있으므로 `git add -p` 또는 파일 그룹별 staging 후 각 commit마다 release gate를 최소 backend/build 수준으로 다시 실행한다.

## P0-7. `Factory Signal Board` 레거시 명칭이 제품 경계를 왜곡함

현재 제품 표시명은 `Ontology Dashboard`로 바뀌었지만, 레거시 명칭이 단순 설명 문구가 아니라 내부 namespace와 배포 계약에 남아 있다.

확인된 범위:

```text
Python package            api/factory_signal_board/
Python distribution       factory-signal-board-api
Service class             FactorySignalService
Environment variable      FACTORY_SIGNAL_DB
SQLite filename           factory_signal_board.db
Uvicorn import path        factory_signal_board.main:app
CI workflow name          factory-signal-board-ci
Git bootstrap repo name   factory-signal-board
ML package/docstring      factory_signal_ml / Factory Signal Board ML package
JSON Schema $id/title     factory-signal-board.local
Gold evaluation suite     factory-signal-board-mvp-gold-v1
문서 제목·로그 경로        Factory Signal Board / factory-signal-board-api.log
```

이 명칭을 계속 유지하면 사용자는 제조 예지보전 제품이 중심이고 Ontology Dashboard가 그 위에 덧붙은 기능이라고 오해하게 된다. 실제 제품 방향은 반대다.

```text
Ontology Dashboard Platform
└── Manufacturing Predictive Maintenance Pack
```

### 원칙

- 제품·플랫폼의 canonical name과 namespace는 `Ontology Dashboard` / `ontology_dashboard`로 통일한다.
- 제조 관련 명칭은 `manufacturing`, `predictive_maintenance`, `manufacturing_pack` 경계 안에서만 사용한다.
- `Factory Signal Board`를 새 코드·schema·환경변수·로그·배포 자산에 추가하지 않는다.
- 과거 설명이 필요한 migration note와 Git history 외에는 최종적으로 제거한다.
- 기존 import와 DB 경로를 즉시 깨뜨리는 일괄 치환은 하지 않는다.

### 단계적 migration

1. **외부 canonical naming 고정**
   - README, API title, OpenAPI, Docker service label, CI, log, schema title을 `Ontology Dashboard`로 변경
   - `Factory Signal Board`는 migration 문서의 과거 명칭 설명에만 허용
2. **새 내부 namespace 추가**
   - `api/ontology_dashboard/`
   - distribution name `ontology-dashboard-api`
   - canonical import `ontology_dashboard.*`
   - DB env `ONTOLOGY_DASHBOARD_DB_URL` 또는 `ONTOLOGY_DASHBOARD_DB`
3. **compatibility shim 제공**
   - 한 release 동안 `factory_signal_board.*`가 `ontology_dashboard.*`를 re-export
   - `FACTORY_SIGNAL_DB`가 설정된 경우 deprecation warning과 함께 새 설정으로 변환
   - 기존 `factory_signal_board.db`를 발견하면 migration 또는 명시적 rename 수행
4. **제조 domain code 분리**
   - `ontology_dashboard/domain_packs/manufacturing/`
   - `FactorySignalService`를 플랫폼 service가 아니라 `ManufacturingPredictiveMaintenanceService` 또는 adapter로 축소
   - `factory_signal_ml`은 `manufacturing_predictive_maintenance_ml` 또는 domain pack 내부 package로 이동
5. **legacy 제거 release**
   - old import·env·schema ID alias 제거
   - repository 전체 금지어 검사 gate 추가

### 완료 조건

- 사용자에게 노출되는 화면·API·로그·export·schema에 `Factory Signal Board`가 없음
- canonical Python import가 `ontology_dashboard`임
- 제조 기능은 domain pack 경로로만 존재함
- 이전 DB와 import 사용자는 migration warning 후 정상 기동 가능
- release gate에 legacy-name allowlist 검사가 포함됨

---

# 5.2 P1 — 내부 파일럿 전에 필요한 항목

## P1-1. 백엔드 application composition 분리

`api/factory_signal_board/main.py`는 약 1,263줄이며 route, middleware, dependency, service composition을 한 파일에 포함한다.

권장 구조:

```text
ontology_dashboard/
├── app.py                 # create_app
├── settings.py            # typed environment config
├── dependencies.py
├── middleware/
├── routers/
│   ├── auth.py
│   ├── admin.py
│   ├── ontology.py
│   ├── dashboards.py
│   ├── role_workspaces.py
│   ├── planner.py
│   ├── exports.py
│   └── manufacturing_legacy.py
├── domains/
└── infrastructure/
```

FastAPI global singleton과 `lru_cache`는 app factory와 lifespan container로 교체한다. 테스트마다 dependency override를 쉽게 하고 startup validation/migration을 명확히 한다.

## P1-2. Frontend orchestration 분리

`ManufacturingApp.tsx`는 약 971줄이며 다음 책임이 혼합되어 있다.

- workspace bootstrap
- event detail loading
- role workspace loading
- dashboard edit state
- personalization persistence
- share/export
- FDE template workflow
- field action
- model release
- rendering orchestration

권장 분리:

```text
features/workspace/
features/event-context/
features/dashboard-editor/
features/dashboard-runtime/
features/template-workflow/
features/field-actions/
features/model-release/
hooks/useResolvedDashboard.ts
hooks/useEventContext.ts
hooks/useRoleWorkspace.ts
```

서버 상태와 편집 draft 상태를 분리하고, request cancellation과 stale response 방지를 추가한다.

## P1-3. Route가 계획된 resource URL을 실제로 표현하지 않음

현재 `/app`와 `/app/*`는 모두 동일한 `ManufacturingApp`을 렌더링한다.

계획된 다음 route가 실제 resource state와 연결되어야 한다.

```text
/app/workspaces/:workspaceId
/app/dashboards/:dashboardId
/app/objects/:objectType/:objectId
/app/tasks/:taskId
/app/fde
/admin/users
/admin/templates
/admin/audit
```

개선 효과:

- deep link와 browser back/forward 정상화
- 공유 URL의 의미 명확화
- route-level code split
- role별 허용 route 선언
- 특정 object/task를 바로 열 수 있음

## P1-4. multi-role 사용자의 역할 선택 모델이 불명확함

현재 frontend는 `user.roles[0]`을 primary role로 사용한다. Backend는 role을 code 순으로 정렬하므로 관리자가 여러 역할을 할당하면 사용자가 예상하지 않은 landing을 받을 수 있다.

### 개선

- `primary_role`을 명시적으로 저장하거나
- active role/session context를 도입
- workspace별 role assignment 지원
- role switch 시 permission은 union이 아니라 active role + explicit elevated permission으로 계산
- admin과 일반 role을 동시에 가진 사용자의 route 정책 정의

## P1-5. Dashboard 편집 UX

현재 구현은 기능적으로 작동하지만 전문 편집기 수준에서 다음이 부족하다.

- pointer/touch 기반 안정적 drag
- 실제 2D grid x/y 배치
- 자유로운 resize handle
- keyboard 이동
- undo/redo
- unsaved draft recovery
- board loading/error boundary
- large dashboard virtual rendering
- edit history와 template diff preview

`react-grid-layout` 또는 동급 grid engine을 검토하되, server contract는 현재 12-column 모델을 유지한다.

## P1-6. 접근성·국제화·사용성 테스트

현재 명시적 accessibility gate가 없다.

필요 항목:

- keyboard-only task flow
- focus trap과 modal semantics
- screen reader label
- color contrast
- reduced motion
- 200% zoom
- axe 기반 automated check
- 한국어/영어 message catalog
- date/time/timezone formatting
- destructive action confirmation UX 통일

## P1-7. 인증 lifecycle

현재 없는 항목:

- 이메일 소유 확인
- invitation flow
- password reset
- password change
- first-login password change
- MFA
- SSO/OIDC/SAML
- device/session naming
- security event notification
- compromised password check

내부 파일럿에서는 최소 invitation, password reset, first-login change, session revoke를 구현한다.

## P1-8. proxy와 client IP trust

현재 `X-Forwarded-For` 첫 값을 조건 없이 신뢰한다. reverse proxy가 해당 header를 제거·재작성하지 않으면 client가 spoof하여 rate limit subject와 IP 관찰 값을 바꿀 수 있다.

### 개선

- trusted proxy CIDR 설정
- proxy middleware에서만 forwarded header 해석
- 직접 접근 시 request.client만 사용
- production ingress가 overwrite하는지 통합 테스트

## P1-9. export artifact 저장

현재 response에서 즉시 artifact를 생성해 다운로드한다.

필요 항목:

- object storage
- expiring signed URL
- retention/delete policy
- async large export job
- malware/content scanning이 필요한 upload/export 연결
- audit artifact와 user convenience export 구분

## P1-10. 실제 LLM provider 평가

현재 deterministic fallback 안전성은 좋지만 provider 품질은 미검증이다.

평가 세트:

- object query accuracy
- unknown property rejection
- role-appropriate board recommendation
- unsupported claim rate
- evidence citation completeness
- latency p50/p95
- token/cost budget
- provider timeout/failure rate
- prompt injection/adversarial request
- Korean domain terminology

---

# 5.3 P2 — product expansion 항목

- 두 번째 domain pack 구현으로 domain neutrality 검증
- connector SDK와 mapping UI
- schema diff와 migration preview
- object-level ABAC
- actual photo/file upload
- field offline queue와 conflict resolution
- notification/inbox
- scheduled report
- webhook/action integration
- model registry/experiment tracker 연결
- domain pack marketplace 또는 package contract
- real-time event stream
- collaborative dashboard editing

두 번째 domain pack은 제조와 데이터 형태가 다른 물류 또는 리테일을 권장한다. 그래야 단순 이름 변경이 아니라 실제 domain neutrality를 검증할 수 있다.

---

# 6. 권장 업그레이드 단계

# 32단계 — Product naming·namespace migration

## 구현

- canonical product name을 `Ontology Dashboard`로 고정
- `api/ontology_dashboard` package 생성
- `factory_signal_board` compatibility shim 제공
- distribution, CI, Docker, log, DB env, schema ID, evaluation suite rename
- 제조 코드를 `domain_packs/manufacturing` 경계로 이동
- legacy name inventory와 deprecation matrix 작성
- 금지어 검사 release gate 추가

## 완료 조건

- 새 코드가 `ontology_dashboard.*` import만 사용
- 사용자 노출 및 신규 deployment asset에서 `Factory Signal Board` 0건
- 기존 import/env/DB는 한 release 동안 migration compatibility 유지
- Gold 8개, backend, frontend, E2E 모두 통과

# 33단계 — Baseline 고정과 Git 정리

## 구현

- working tree를 6개 논리 commit으로 분리
- remote 설정
- release tag `ontology-dashboard-v0.6-demo`
- Architecture Decision Record 작성
- 현재 test 결과 보존

## 완료 조건

- clean working tree
- 각 commit 목적이 독립적으로 설명 가능
- remote branch push
- 동일 commit에서 release gate 재현

# 34단계 — Application modularization

## 구현

- FastAPI `create_app`와 router 분리
- typed Settings
- startup config validation
- repository/service dependency container
- `ManufacturingApp` hook·feature 분리
- route-level lazy loading

## 완료 조건

- `main.py` 250줄 이하
- 주 orchestration component 300줄 이하
- 기존 53 backend + 13 E2E 유지

# 35단계 — Production persistence

## 구현

- PostgreSQL
- Alembic migration
- transaction boundary
- outbox/reconciliation
- Redis rate limit·short-lived state
- DB connection pooling

## 완료 조건

- SQLite와 PostgreSQL contract test
- rollback/upgrade migration test
- concurrent preference/action test
- restart 후 recovery test

# 36단계 — Tenant isolation

## 구현

- organization-scoped principal
- tenant guard/RLS
- organization invitation
- workspace별 role assignment
- cross-tenant audit/export/share test

## 완료 조건

- tenant A admin이 tenant B user/workspace를 조회·수정할 수 없음
- 모든 repository query에 tenant context 존재
- negative permission matrix 통과

# 37단계 — Persistent Ontology runtime

## 구현

- schema registry persistence
- object/link persistence
- ingestion mapping
- schema version
- source lineage
- manufacturing adapter를 첫 ingestion adapter로 전환

## 완료 조건

- fixture 없이 DB object query 가능
- incremental ingestion 가능
- schema version upgrade/rollback 가능
- 10만 object 성능 budget 정의

# 38단계 — Routing·UX·Accessibility

## 구현

- resource route
- deep link
- active role selector
- grid editor
- undo/redo
- error boundary
- keyboard/a11y

## 완료 조건

- route reload 복원
- mobile/desktop 주요 task completion test
- axe critical violation 0
- keyboard-only Gold flow 통과

# 39단계 — Production identity/security

## 구현

- invitation/email verify/reset/change
- OIDC foundation
- trusted proxy
- configurable cookie/domain/origin
- server-tied CSRF/session hardening
- security event audit
- secret manager

## 완료 조건

- production startup misconfiguration fail-fast
- demo seed 불가
- HTTPS cookie test
- proxy spoof regression test
- session revocation propagation test

# 40단계 — Operations·Deployment

## 구현

- production Docker images
- non-root user
- pinned dependency build
- reverse proxy
- OpenTelemetry
- metrics/logging/error tracking
- backup/restore
- object storage
- CI/CD staging deployment

## 완료 조건

- ephemeral staging deployment
- health/readiness/liveness 분리
- backup restore drill 성공
- rollback runbook 검증

# 41단계 — Real-data pilot

## 구현

- 실제 manufacturing sample ingestion
- actual provider evaluation
- role별 user test
- KPI/threshold governance
- data retention/privacy review

## 완료 조건

- fixture가 아닌 pilot data로 핵심 flow 통과
- 사용자 task completion·오류율 측정
- LLM quality/cost/latency 기준 충족

# 42단계 — Production release candidate

## 완료 조건

- P0 0건
- P1 중 합의된 defer 항목에 owner/date 존재
- SAST/DAST/dependency scan 통과
- PostgreSQL load test 통과
- disaster recovery 검증
- tenant isolation test 통과
- accessibility gate 통과
- release rollback 절차 검증

---

# 7. 테스트 전략 업그레이드

## Backend

- repository integration test를 SQLite와 PostgreSQL 양쪽에서 실행
- permission matrix를 role × tenant × workspace × object × action으로 생성
- property-based test로 Dashboard override merge 검증
- Action crash point별 recovery test
- migration forward/backward test
- export hash reproducibility test

## Frontend

현재 Vitest 1건에서 최소 다음 영역으로 확대한다.

- dashboard utility
- preference reducer/state machine
- route guard
- active role selection
- API error mapping
- field action validation
- template diff
- planner preview non-persistence

## E2E

- Chromium + WebKit
- desktop + mobile
- fresh DB + migrated DB
- multi-user concurrent preference update
- cross-tenant denial
- session expiry during edit
- API restart recovery
- slow network/provider timeout
- accessibility scan

## Performance

현재 resolved Dashboard in-process resolve 시간 외에 다음을 측정한다.

- HTTP p50/p95/p99
- 10/50/100 board rendering
- 1만/10만 object query
- concurrent login/session
- export memory footprint
- PostgreSQL lock contention
- planner timeout/circuit breaker

---

# 8. 원격 Git commit·push 방법

# 8.1 현재 DevSpace connector의 한계

현재 대화에 연결된 DevSpace `bash` 도구는 test, build, package script, file inspection, **git inspection** 용도로 제한되어 있다. 프로젝트 파일이나 Git history/remote를 변경하는 `git add`, `git commit`, `git push`를 실행하는 도구로 사용할 수 없다.

따라서 다음을 구분해야 한다.

- 사람이 Tailscale SSH로 Mac terminal에 접속해 Git 명령 실행: **새 MCP 불필요**
- ChatGPT가 connector를 통해 commit·push까지 직접 실행: **현재 DevSpace 외에 write-capable Git MCP 또는 전용 remote agent 필요**

# 8.2 가장 단순한 방법 — Tailscale 위의 일반 SSH

다른 tailnet 기기에서:

```bash
ssh gabrieljang@gabriels-m1-macbook-air
```

접속 후:

```bash
cd '/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2'
git status --short --branch
git diff --check
```

remote가 없으므로 GitHub repository를 만든 뒤 최초 1회:

```bash
git remote add origin <GITHUB_REPOSITORY_SSH_OR_HTTPS_URL>
git remote -v
```

현재 branch push:

```bash
git push -u origin feat/ontology-dashboard-foundation
```

remote command 한 줄 실행도 가능하다.

```bash
ssh gabrieljang@gabriels-m1-macbook-air \
  "cd '/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2' && git status --short --branch"
```

commit까지 원격으로 실행할 수 있지만, 58개 변경 파일을 한 번에 commit하지 말고 먼저 interactive SSH session에서 diff와 staging을 확인하는 방식을 권장한다.

# 8.3 ChatGPT가 직접 Git write를 수행해야 할 때

새로운 MCP를 만든다면 arbitrary shell MCP보다 **Git 전용 MCP**가 안전하다.

권장 tool surface:

```text
open_repository
status
diff
diff_cached
add_paths
reset_paths
commit
list_remotes
set_remote
push_branch
create_tag
```

필수 보안:

- 허용 repository root allowlist
- force push 기본 금지
- protected branch 직접 push 금지
- commit 전 staged diff 반환
- push 전 remote/branch/commit SHA 반환
- SSH key/token 원문 비노출
- Mac Keychain/ssh-agent 사용
- command·actor·timestamp audit
- explicit user request 없이 commit/push 금지
- arbitrary shell, redirection, script execution 금지

실행 형태:

```text
ChatGPT
→ authenticated Git MCP endpoint
→ Mac의 allowlisted repository
→ local git + ssh-agent
→ GitHub
```

MCP process는 launchd로 실행하고 localhost 또는 tailnet interface에만 bind한다. public internet에 직접 노출하지 않는다.

# 8.4 대안 — GitHub 중심 workflow

가장 운영 친화적인 방식은 Mac에서 한 번 branch를 push한 뒤:

- GitHub PR
- CI release gate
- branch protection
- required review/check
- merge 후 staging deploy

로 전환하는 것이다. 이후 ChatGPT는 코드 수정과 검증을 DevSpace에서 수행하고, 사람 또는 Git 전용 MCP가 명시적으로 commit/push한다.

---

# 9. 외부에서 현재 웹 화면 접근

현재 frontend와 API가 모두 `127.0.0.1`에 bind되어 있으며, frontend API base도 `http://127.0.0.1:8100`이다.

가장 안전하고 설정 변경이 없는 방법은 SSH tunnel이다.

외부 tailnet 기기에서:

```bash
ssh -N \
  -L 3100:127.0.0.1:3100 \
  -L 8100:127.0.0.1:8100 \
  gabrieljang@gabriels-m1-macbook-air
```

그 후 외부 기기의 browser에서:

```text
http://127.0.0.1:3100
```

을 연다.

이 방식은 frontend가 기대하는 `127.0.0.1:8100` API 주소도 함께 tunnel하므로 현재 build/config를 바꾸지 않아도 된다.

Tailscale Serve를 사용할 수도 있지만 현재 frontend에 absolute API URL이 들어가 있으므로 web port만 Serve하면 원격 browser의 localhost API를 호출하게 된다. Serve를 정식 운영하려면 다음 중 하나가 필요하다.

1. frontend API base를 same-origin relative `/api`로 변경하고 reverse proxy에서 web/API를 한 origin으로 통합
2. web과 API를 각각 tailnet URL로 Serve하고 production CORS/cookie domain을 구성

정식 배포에서는 1번을 권장한다.

---

# 10. 바로 실행할 우선순위

다음 순서가 가장 안전하다.

```text
1. 현재 release gate 결과 보존
2. Git remote 생성·설정
3. 19~31단계를 논리 commit으로 분리
4. 현재 branch push/tag
5. 32단계 제품 명칭·namespace migration
6. 33단계 baseline 고정
7. 34단계 backend/frontend modularization
8. 35~36단계 PostgreSQL·transaction·tenant isolation
9. 37단계 persistent Ontology runtime
10. 38~40단계 UX·security·operations
11. 실제 데이터 pilot 후 production RC
```

새 기능을 더 추가하기 전에 최소한 32~36단계를 먼저 완료하는 것이 좋다. 특히 제품명과 namespace를 먼저 바로잡지 않으면 이후 생성되는 package, environment variable, schema ID, deployment asset까지 잘못된 레거시 이름이 계속 확산된다. 그 다음 `main.py`, `ManufacturingApp.tsx`, fixture adapter와 단일 SQLite에 결합된 부채를 줄여야 한다.
