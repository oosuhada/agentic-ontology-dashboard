# Ontology Dashboard 16~18단계 구현 요약

- 구현일: 2026-08-01
- 범위: 제품 reframe, 인증·회원가입·로그인, RBAC·resource scope·관리자 foundation
- Git commit·push: 수행하지 않음
- 최종 release gate: **10/10 PASS**

## 16단계 — 제품 reframe와 domain-neutral foundation

완료:

- 화면·API·문서 표시명을 `Ontology Dashboard`로 변경
- 기존 제조 예지보전 기능을 `Manufacturing Predictive Maintenance Pack`으로 표시
- `manufacturing-demo` workspace foundation
- Pydantic Object·Link·Action·Evidence·Dashboard·Board contract
- TypeScript ontology contract
- `schemas/ontology-core.schema.json`
- ObjectType·LinkType·ActionType registry API
- 기존 Evidence·Report·Layout·Gold 8개 유지

주요 파일:

```text
api/factory_signal_board/ontology.py
web/src/features/ontology/types.ts
schemas/ontology-core.schema.json
```

## 17단계 — 인증·회원가입·로그인

완료:

- SQLite `users`, `password_credentials`, `sessions`, `organizations`, `workspaces`
- Argon2id password hash
- session 원본 대신 SHA-256 token hash 저장
- HttpOnly·SameSite cookie session
- CSRF cookie/header 검증
- register·login·logout·me API
- signup `pending_approval`
- pending·disabled login 차단
- protected `/app`
- `/login`, `/register`, `/pending`
- 8개 development demo account
- `APP_ENV=production` demo seed 강제 차단
- idempotent `scripts/seed_demo_accounts.py`

주요 파일:

```text
api/factory_signal_board/identity_models.py
api/factory_signal_board/identity_repository.py
api/factory_signal_board/identity.py
web/src/features/auth/AuthContext.tsx
web/src/features/auth/LoginPage.tsx
web/src/features/auth/RegisterPage.tsx
web/src/features/auth/PendingPage.tsx
```

## 18단계 — RBAC·resource scope·관리자 foundation

완료:

- role·permission·role_permission·user_role schema
- `user_scopes`와 server-side `manufacturing-demo` 검사
- tenant-admin-only `/admin`
- Overview, Users, Roles & Permissions, Audit Logs foundation
- 가입 승인·비활성화·재활성화
- 역할과 workspace scope 할당
- 관리자 before/after audit
- FDE와 tenant_admin permission 분리
- actor spoof 방지: decision·note actor를 session principal로 결정
- 일반 사용자/FDE admin API 403
- read-only 역할의 Action UI 숨김과 server-side 재검사

주요 파일:

```text
web/src/features/admin/AdminApp.tsx
api/factory_signal_board/main.py
tests/test_auth_rbac.py
```

## `App.tsx` 분리 결과

이전에는 `App.tsx`가 데이터 로딩, 역할 전환, 대시보드 렌더링과 Action 처리를 모두 담당했다.

현재:

```text
App.tsx
└── route/auth orchestration only
    ├── features/auth
    ├── features/manufacturing
    ├── features/admin
    └── features/ontology
```

기존 대시보드는 `web/src/features/manufacturing/ManufacturingApp.tsx`로 이동했다. 계정 role을 임의 UI switch로 바꾸지 않고 실제 session principal의 role로 landing과 허용 Action을 결정한다.

## 검증 결과

```text
Release checks: 10/10 PASS
Python tests: 23 PASS
Gold scenarios: 8/8 PASS
Vitest: 1 PASS
TypeScript: PASS
Production build: PASS
Playwright: 4 PASS
```

검증한 핵심 시나리오:

1. 8개 test account 로그인
2. Argon2id hash와 평문 비밀번호 미저장
3. signup pending과 admin 승인
4. pending·disabled·logout 차단
5. FDE admin 403, tenant admin 허용
6. workspace scope 밖 제조 API 403
7. CSRF 없는 mutation 차단
8. manager·engineer 기존 Gold 화면 유지
9. data-quality·LLM fallback 유지
10. 공개 reset API 없음

## 남은 다음 단계

다음 구현 순서는 계획 문서의 19단계다.

```text
19단계 — Ontology registry와 제조 domain adapter
```

구체적으로 남은 것:

- fixture Equipment·RiskEvent·Evidence·Inspection을 실제 `ObjectRecord`로 adapter
- Equipment → RiskEvent → Inspection relation traversal
- 기존 decision·note workflow를 ontology Action invocation으로 연결
- Action idempotency와 audit
- permission-aware object query
- workspace/domain pack isolation test 확장

20단계의 persistent Dashboard Template·Tab·Board는 아직 구현하지 않았다. 현재 역할별 landing은 code-defined foundation이며 사용자 개인화 저장도 후속 범위다.
