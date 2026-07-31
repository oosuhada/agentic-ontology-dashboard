# Ontology Dashboard Service Contract

## 서비스 경계

```text
Identity + Role + Workspace Scope
→ Ontology Dashboard Platform
→ Manufacturing Predictive Maintenance Pack adapter
→ Evidence Package
→ grounded report agent
→ governed layout planner
→ React role landing / administrator control plane
```

React는 모델 모듈을 import하지 않는다. Report와 Layout은 Evidence Package만 참조한다. 사용자 role, permission과 workspace scope는 클라이언트 표시 여부와 무관하게 API에서 다시 검사한다.

## 공개 API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | 서비스, offline-capable 상태와 첫 domain pack 확인 |
| POST | `/api/auth/register` | `pending_approval` 가입 요청 생성 |
| POST | `/api/auth/login` | Argon2id 검증 후 HttpOnly session cookie 발급 |
| GET | `/api/openapi-contract` | OpenAPI 문서 JSON |

## 인증 API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/auth/me` | 현재 session의 역할, permission, workspace scope 조회 |
| POST | `/api/auth/logout` | 현재 session revoke와 cookie 삭제 |
| GET | `/api/workspaces` | 현재 사용자가 접근 가능한 workspace 목록 |

회원가입 요청은 역할을 입력받지 않는다.

```json
{
  "display_name": "신규 엔지니어",
  "email": "new.engineer@example.com",
  "password": "NewEngineer!2026",
  "organization_name": "New Factory",
  "terms_accepted": true
}
```

로그인 성공 principal 예시:

```json
{
  "user": {
    "user_id": "...",
    "email": "manager@ontology.local",
    "display_name": "김현우",
    "status": "active",
    "roles": ["process_manager"],
    "permissions": ["app.access", "events.decision", "events.read", "ontology.registry.read"],
    "workspace_scopes": ["manufacturing-demo"],
    "is_admin": false,
    "default_path": "/app",
    "landing_key": "process_manager"
  }
}
```

## Ontology foundation API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/domain-packs` | 허용된 domain pack metadata |
| GET | `/api/ontology/registry` | ObjectType·LinkType·ActionType registry |
| GET | `/api/ontology/object-types` | Object type 정의 |
| GET | `/api/ontology/link-types` | Link type 정의 |
| GET | `/api/ontology/action-types` | Action type 정의 |

현재 첫 pack은 `manufacturing-predictive-maintenance`이며 `manufacturing-demo` workspace에 연결된다. 객체 instance query와 relation traversal은 19단계 범위다.

## Manufacturing Predictive Maintenance Pack API

아래 API는 인증과 `manufacturing-demo` scope가 필요하다.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/equipment` | 설비 목록 |
| GET | `/api/equipment/{equipment_id}` | 설비와 연결 사건 |
| GET | `/api/events` | 위험 우선순위 사건 목록 |
| GET | `/api/events/{event_id}` | 원본 fixture 사건과 사용자 활동 |
| GET | `/api/events/{event_id}/evidence` | 검증된 Evidence Package |
| POST | `/api/events/{event_id}/report` | 계정 역할에 허용된 Report 생성 |
| POST | `/api/events/{event_id}/layout` | 계정 역할에 허용된 governed Layout 생성 |
| POST | `/api/events/{event_id}/decision` | `events.decision` 권한 사용자의 판단 기록 |
| POST | `/api/events/{event_id}/notes` | `events.note` 권한 사용자의 점검·전달 메모 기록 |
| POST | `/api/events/{event_id}/follow-up` | 제한된 후속 질문과 화면 재구성 |
| GET | `/api/events/{event_id}/activity` | 판단·메모·대화 이력 |

요청 body의 `actor`는 신뢰하지 않는다. 판단과 메모의 actor는 server-side principal의 `display_name`으로 덮어쓴다.

기존 planner role은 회귀 안정성을 위해 `manager | engineer`를 유지하며 계정 role을 다음처럼 adapter한다.

```text
executive_viewer, process_manager, quality_auditor → manager
process_engineer, maintenance_technician, ml_validator, fde → engineer
tenant_admin → requested manager/engineer preview
```

일반 사용자가 자기 계정 role과 다른 legacy role을 요청하면 `403 role_context_denied`다.

## 관리자 API

모든 `/api/admin/*` API는 `tenant_admin` permission을 서버에서 검사한다.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/overview` | 활성·pending·disabled 사용자와 최근 변경 요약 |
| GET | `/api/admin/users` | 가입 요청과 사용자 role·scope 조회 |
| PATCH | `/api/admin/users/{user_id}` | 승인, 비활성화, 역할과 workspace scope 변경 |
| GET | `/api/admin/roles` | role registry |
| GET | `/api/admin/workspaces` | workspace registry |
| GET | `/api/admin/audit` | 관리자 변경 audit |

관리자 변경 예시:

```json
{
  "status": "active",
  "roles": ["process_engineer"],
  "workspace_scopes": ["manufacturing-demo"]
}
```

자기 관리자 계정을 비활성화하거나 자기 계정에서 `tenant_admin` 역할을 제거하는 요청은 self-lockout 방지로 거부한다. FDE는 admin permission이 없으므로 위 API에서 403을 받는다.

## Session과 CSRF

- session token은 `ontology_session` HttpOnly cookie에 저장한다.
- DB에는 원본 token 대신 SHA-256 token hash를 저장한다.
- cookie는 `SameSite=Lax`이며 production에서 `Secure`다.
- state-changing cookie 요청은 `ontology_csrf` cookie 값과 `X-CSRF-Token` header가 일치해야 한다.
- logout은 session을 revoke한다.
- pending, disabled, expired 또는 revoked session은 protected API를 사용할 수 없다.

## 오류 계약

```json
{
  "error": {
    "code": "authentication_required",
    "message": "로그인이 필요합니다."
  }
}
```

```json
{
  "error": {
    "code": "workspace_scope_denied",
    "message": "허용된 workspace 범위를 벗어난 요청입니다."
  }
}
```

기타 주요 code:

```text
invalid_credentials
pending_approval
account_disabled
permission_denied
role_context_denied
csrf_validation_failed
email_already_registered
user_not_found
contract_validation_failed
not_found
```

Provider 오류는 사용자 요청 실패로 전파하기보다 검증된 결정론적 fallback으로 처리한다. 내부 자격 증명과 상세 예외는 응답에 포함하지 않는다.

## persistence와 감사 계약

기존 운영 audit:

- `decisions`
- `notes`
- `conversations`
- `audit_log`

identity와 RBAC foundation:

- `organizations`
- `workspaces`
- `users`
- `password_credentials`
- `sessions`
- `roles`
- `permissions`
- `role_permissions`
- `user_roles`
- `user_scopes`
- `admin_audit`

비밀번호는 Argon2id hash만 저장한다. 관리자 role·status·scope 변경은 before/after snapshot과 actor를 `admin_audit`에 남긴다.

## 개발·데모 seed

- `development`, `demo`, `test` 환경에서만 8개 demo account를 seed할 수 있다.
- `APP_ENV=production`에서 seed가 요청되면 애플리케이션이 시작을 거부한다.
- 수동 idempotent seed: `PYTHONPATH=api:ml/src python scripts/seed_demo_accounts.py`

## 초기화와 안전 경계

- 일반 사용자 UI에 발표·데모 초기화 버튼이 없다.
- 공개 `/api/demo/reset` endpoint가 없다.
- 개발자는 `scripts/reset_demo.py`로 기존 decision·note·conversation·operational audit만 초기화한다.
- identity, credential과 administrator audit를 일반 사용자 초기화로 삭제하지 않는다.
- 설비 제어 API가 없다.
- 미등록 UI Block과 data field는 Planner validation에서 차단된다.
- 후속 질문은 허용된 intent만 지원한다.
- prompt injection 또는 실제 제어 요청은 지원 범위 밖으로 처리한다.
