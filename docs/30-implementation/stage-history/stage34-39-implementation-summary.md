# 34~39단계 구현 요약

- 구현일: 2026-08-01
- Git 작업: 수행하지 않음
- Release gate: 11/11 PASS
- Backend tests: 62 PASS
- Playwright E2E: 13 PASS

## Application factory와 router

- `ontology_dashboard.application.create_app()` 추가
- CORS, security headers, production validation을 application factory로 이동
- service composition과 auth dependency를 `ontology_dashboard.dependencies`로 이동
- HTTP path registration을 다음 router로 분리
  - system
  - auth
  - ontology
  - dashboards
  - exports
  - planner
  - role workspaces
  - manufacturing domain pack
  - admin
- 기존 handler 모듈에는 `@app.*` route decorator가 남아 있지 않음

## Frontend orchestration

- 역할 landing metadata를 `roleLanding.ts`로 분리
- workspace/event/domain-pack bootstrap을 `useWorkspaceCatalog`로 분리
- evidence/report/layout loading을 `useEventDetail`로 분리
- role-specific data loading을 `useRoleWorkspace`로 분리
- `ManufacturingApp.tsx`는 971줄에서 약 806줄로 감소

추가로 dashboard editor command와 persistence command를 별도 hook으로 더 분리할 여지가 있다.

## Migration과 transaction foundation

- ordered SQL migration runner 추가
- SQLite migration `0001_platform_core.sql` 추가
- PostgreSQL migration `0001_platform_core.sql` 추가
- PostgreSQL optional dependency `psycopg[binary]` 추가
- transactional outbox schema 추가
- field action과 outbox event를 같은 SQLite transaction에 기록
- migration idempotency test 추가

현재 모든 기존 repository가 PostgreSQL driver로 전환된 것은 아니다. PostgreSQL DDL과 migration 실행 기반은 구현됐지만 production runtime은 안전을 위해 계속 fail-fast한다.

## Tenant isolation

- Principal에 `organization_id` 추가
- tenant admin workspace scope를 자신의 organization으로 제한
- admin users/workspaces/audit/overview query를 organization으로 제한
- 다른 tenant의 user update를 404로 차단
- 미할당 pending signup만 onboarding queue에 포함
- 두 번째 organization을 생성하는 cross-tenant negative test 추가

## Persistent Ontology instance store

- `ontology_objects`
- `ontology_links`
- `ontology_ingestion_runs`

저장소를 추가했다. 제조 domain adapter snapshot은 transaction으로 materialize되고 object query, object detail, link traversal은 persistent instance store를 통해 조회한다.

PostgreSQL schema에는 JSONB index, relation FK, RLS policy를 포함했다.

## Legacy namespace removal

- 신규 runtime, test, script, Docker, docs는 canonical namespace 사용
- `factory_signal_board` import는 명시적 ImportError
- `factory_signal_ml` import는 명시적 ImportError
- legacy ML CLI entrypoint 제거
- canonical naming gate 75개 파일, 위반 0건

현재 canonical package가 migration 중인 구현 source directory를 module search path로 사용하므로 물리적 source file은 아직 `api/factory_signal_board`와 `ml/src/factory_signal_ml`에 남아 있다. 외부 import compatibility는 제거됐지만, 물리적 directory 삭제는 모든 source file을 canonical directory로 이동하는 마지막 consolidation 작업으로 남는다.

## 검증

```text
Canonical naming: 75 files, 0 violations
Backend: 62 PASS
Gold: 8/8 PASS
Frontend unit: PASS
TypeScript: PASS
Production build: PASS
Playwright: 13 PASS
Release gate: 11/11 PASS
```
