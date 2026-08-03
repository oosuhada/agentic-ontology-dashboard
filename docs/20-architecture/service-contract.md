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
| POST | `/api/auth/refresh` | current token·CSRF revoke 후 새 session token으로 rotation |
| GET | `/api/auth/sessions` | 현재 사용자의 active session 목록 |
| DELETE | `/api/auth/sessions/others` | 현재 token을 제외한 다른 active session revoke |
| POST | `/api/auth/logout` | 현재 session revoke와 cookie 삭제 |
| GET | `/api/workspaces` | 현재 사용자가 접근 가능한 workspace 목록 |

회원가입 요청은 역할을 입력받지 않는다. Session은 12시간 absolute expiry, 60분 idle timeout과 user-agent hash binding을 사용한다. Login·refresh·session revoke에는 rate limit이 적용된다.

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
    "permissions": ["app.access", "dashboards.personalize", "dashboards.read", "dashboards.share", "events.decision", "events.read", "ontology.objects.read", "ontology.registry.read"],
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
| GET | `/api/ontology/objects` | workspace 범위 내 ObjectRecord 검색·페이지 조회 |
| GET | `/api/ontology/objects/{object_id}` | 단일 ObjectRecord 조회 |
| GET | `/api/ontology/objects/{object_id}/links` | 방향·깊이·link type 기반 relation traversal |
| GET | `/api/ontology/objects/{object_id}/action-invocations` | 객체에 실행된 Action 이력 조회 |
| POST | `/api/ontology/actions/invoke` | permission 검증 후 idempotent Action 실행 |

현재 첫 pack은 `manufacturing-predictive-maintenance`이며 `manufacturing-demo` workspace에 연결된다. 모든 object query와 traversal은 `ontology.objects.read` permission과 해당 workspace scope를 함께 검사한다.

객체 ID는 `<object_type>:<source-id>` 형식이다.

```text
equipment:M-014
risk_event:EVT-GS-002
evidence_package:EVD-EVT-GS-002
inspection:EVT-GS-002
maintenance_action:<record-id>
```

Action 요청 예시:

```json
{
  "action_type": "record_operational_decision",
  "object_id": "risk_event:EVT-GS-002",
  "workspace_id": "manufacturing-demo",
  "parameters": {
    "decision": "request_inspection",
    "note": "베어링과 공구 상태 확인"
  },
  "idempotency_key": "manager-decision-20260801-001"
}
```

동일 사용자·workspace에서 같은 `idempotency_key`와 같은 payload를 다시 보내면 기존 성공 결과를 `replayed: true`로 반환한다. 같은 key에 다른 payload를 보내면 `409 idempotency_key_conflict`다. Action은 registry의 대상 object type, parameter schema, required permission을 서버에서 검사하며 성공 결과는 운영 `audit_log`와 `ontology_action_invocations`에 함께 남긴다.

## Dashboard platform API

모든 Dashboard API는 `workspace_id` scope를 검사한다. 일반 사용자는 자기 역할의 resolved template만 사용하며 FDE와 tenant admin만 다른 역할 template을 preview·publish할 수 있다.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/dashboards/resolved` | 역할 template과 사용자 override를 병합한 Dashboard 조회 |
| GET | `/api/dashboard-templates/{role_code}` | 현재 역할 template snapshot 조회 |
| GET | `/api/dashboard-templates/{role_code}/versions` | template version history 조회 |
| GET | `/api/dashboard-templates/{role_code}/preview` | 특정 version 또는 현재 template preview |
| POST | `/api/dashboard-templates/{role_code}/publish` | Tenant admin의 새 template version 게시 |
| POST | `/api/dashboard-templates/{role_code}/publish-requests` | FDE의 template 변경 승인 요청 |
| GET | `/api/boards/catalog` | 현재 역할에 허용된 Board Catalog 검색·category 필터 |
| PUT | `/api/dashboards/preferences` | 개인 tab·board·parameter override 저장 |
| POST | `/api/dashboards/preferences/restore` | 역할 기본 template으로 복원 |
| GET·POST | `/api/dashboards/saved-views` | 개인 Saved View 조회·생성 |
| GET·DELETE | `/api/dashboards/saved-views/{view_id}` | 개인 Saved View 조회·삭제 |
| POST | `/api/dashboards/shares` | 현재 tab·parameter 상태 공유 token 생성 |
| GET | `/api/dashboards/shares/{token}` | 공유 상태 복원, 현재 사용자 scope 재검사 |

개인 설정 저장은 `base_revision`을 사용한다. 서버 revision과 다르면 `409 dashboard_revision_conflict`를 반환해 다른 세션의 변경을 덮어쓰지 않는다.

```json
{
  "workspace_id": "manufacturing-demo",
  "base_revision": 1,
  "active_tab_id": "process_manager:operations",
  "tabs": [],
  "parameter_state": {
    "selected_event_id": "EVT-GS-002",
    "selected_equipment_id": "M-014",
    "status_filter": "warning",
    "intent": "overview"
  }
}
```

Board 저장 시 서버는 다음을 검증한다.

- catalog에 등록된 definition
- 역할별 `allowed_roles`
- `4 | 6 | 12` layout width와 catalog min/max
- binding key와 value type
- mandatory board 존재와 visible 상태
- title·text·settings에 HTML, script, `javascript:` 또는 inline event handler 없음

사용자 변경은 stable tab·board ID 기준 override로 저장한다. template version이 올라가면 새 template board를 유지하면서 기존 사용자 override를 병합하고 `merge_notices`를 제공한다.

Board의 `emits`와 `accepts`로 dependency graph를 생성한다. 선택 변경은 등록된 downstream board에만 전달되며 공유 token 원문은 DB에 저장하지 않고 SHA-256 hash만 저장한다. 공유 링크로도 현재 사용자의 workspace와 selected RiskEvent object permission을 우회할 수 없다.

## Ontology Planner API

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/api/planner/object-query` | `planner.object_query` | 자연어를 registered Object query intent로 변환하고 preview 실행 |
| POST | `/api/planner/board-recommendations` | `planner.board_recommend` | 역할·현재 Dashboard·개인 preference signal 기반 Board 제안 |
| POST | `/api/planner/dashboard-drafts` | `planner.dashboard_draft` | FDE·admin의 target-role Dashboard draft preview |
| POST | `/api/planner/grounded-narrative` | `planner.narrative` | Evidence reference를 포함한 grounded narrative 생성 |

Planner는 임의 query language를 실행하지 않는다. Object query는 registered Object type과 해당 property만 사용하고 `OntologyService.query_objects`로 preview한다. Board recommendation과 Dashboard draft는 target role의 Board Catalog ID만 사용할 수 있다.

```text
LLM output
→ Pydantic contract
→ Object registry / Board Catalog / role / mandatory Board / Evidence reference 검증
→ preview response
→ persisted=false
```

Provider 미설정·timeout·schema·Catalog·grounding 실패 시 `deterministic_fallback`으로 전환한다. 기존 Dashboard는 바뀌지 않으며 Dashboard draft를 Canvas에 적용한 뒤에도 별도 personal save 또는 FDE template approval request가 필요하다.

Grounded narrative의 모든 claim은 하나 이상의 `evidence_field_ids`를 포함해야 한다. unknown reference, 자동 제어 완료, 확정된 근본 원인·고장 단정은 거부한다.

## Export API

| Method | Path | Permission | Purpose |
|---|---|---|---|
| POST | `/api/exports` | `exports.create` | permission-scoped JSON·CSV·PDF artifact 생성 |
| GET | `/api/exports/checkpoints` | `exports.read_own` | 본인 또는 admin의 workspace export checkpoint 조회 |

지원 scope는 `dashboard | event | role_workspace`다.

```text
permission·workspace scope
→ canonical snapshot
→ snapshot SHA-256
→ artifact generation
→ content SHA-256
→ export_checkpoints
→ export.created audit
```

Artifact 응답은 `Content-Disposition`, `X-Export-Checkpoint-ID`, `X-Content-SHA256`, `X-Snapshot-SHA256` header를 제공한다. CSV는 UTF-8 BOM을 사용하고 PDF는 snapshot hash와 검증된 field summary를 포함한다. 일반 사용자는 자신의 checkpoint만 보고 tenant admin은 workspace 전체 checkpoint를 조회한다.

## Role workspace API

역할 전용 API는 일반 Event API와 별도의 permission을 검사한다.

| Method | Path | Permission | Purpose |
|---|---|---|---|
| GET | `/api/role-workspaces/executive` | `executive.overview.read` | 조직·workspace 위험, 영향, 추세와 미조치 중요 사건 집계 |
| GET | `/api/role-workspaces/audit` | `audit.reconstruction.read` | Input→Evidence→Report→Action 사건 재구성 |
| POST | `/api/role-workspaces/audit/export-checkpoints` | `audit.export.checkpoint` | snapshot SHA-256 export checkpoint 기록 |
| GET | `/api/role-workspaces/field` | `field.tasks.read` | 모바일 현장 task, 안전, 위치, checklist, measurement schema |
| GET | `/api/role-workspaces/fde` | `fde.workbench.read` | customer workspace, ontology, integration, diagnostic, approval queue |
| GET | `/api/role-workspaces/ml` | `ml.console.read` | model·dataset·policy, threshold cost, slice, drift, Gold regression |
| POST | `/api/role-workspaces/ml/release-requests` | `ml.release.request` | model release candidate 승인 요청 |

### Executive

Executive aggregate는 세부 sensor history를 반환하지 않는다. Business impact는 fixture의 `estimated_downtime_minutes` 합계이며 생산 단가가 없으므로 금액 영향은 `null`이다. 모든 추정에는 `assumptions`를 포함한다.

### Audit reconstruction

감사 재구성은 다음 snapshot을 반환한다.

- 원본 fixture input과 schema version
- model·policy·context·Evidence·Report version
- Report section별 `evidence_field_ids`
- decision·note·Ontology Action·Field Action history
- export checkpoint metadata

Export checkpoint는 실제 파일 생성과 독립된 감사 행위다. 재구성 snapshot을 canonical JSON으로 직렬화해 SHA-256 hash, 요청자, 형식, 목적과 시각을 저장하고 `audit.export.checkpoint` operational audit를 남긴다.

### Field task Action

현장 작업자는 일반 상태 update API 대신 Ontology Action을 실행한다.

```text
complete_inspection
report_inspection_issue
mark_inspection_blocked
```

Action 대상은 `inspection:<event_id>`다. `complete_inspection`에는 하나 이상의 checklist가 필요하고 issue·blocked에는 note가 필요하다. 측정값과 사진 metadata를 기록할 수 있지만 사진 binary는 받지 않는다. 모든 요청은 idempotency key와 `field.tasks.update` permission을 검증한다.

Offline queue는 현재 `implemented: false`이며 future option, client action ID, server status 우선 conflict policy만 계약으로 정의한다.

### FDE template approval

FDE는 `dashboards.templates.manage`와 `dashboards.templates.request`를 가지지만 `dashboards.templates.approve`는 없다.

```text
FDE template draft
→ server-side board·binding·mandatory validation
→ pending_approval request
→ Tenant admin approve 또는 reject
→ approve일 때만 새 immutable template version publish
```

FDE Workbench 응답에는 password hash, session token, provider secret이 포함되지 않는다.

### Model release approval

학습 지표와 운영 threshold는 서로 다른 scope로 반환한다.

```text
training_metrics.scope = training_or_offline_evaluation
operational_thresholds.scope = production_decision_policy
```

현재 fixture heuristic은 학습 run artifact가 없으므로 training metric을 임의 생성하지 않고 `available: false`와 이유를 반환한다. Model release request는 pending 상태로 저장되고 Tenant admin 승인 전 실제 모델·정책을 변경하지 않는다.

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
| POST | `/api/events/{event_id}/decision` | `record_operational_decision` Ontology Action으로 판단 기록 |
| POST | `/api/events/{event_id}/notes` | `record_inspection_note` Ontology Action으로 점검·전달 메모 기록 |
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
| GET | `/api/admin/workflow-approvals` | Template·Model pending·approved·rejected 요청 |
| POST | `/api/admin/template-publish-requests/{id}/decision` | Template 게시 승인·반려 |
| POST | `/api/admin/model-release-requests/{id}/decision` | Model release 승인·반려 |

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
idempotency_key_conflict
action_in_progress
prior_action_failed
dashboard_revision_conflict
mandatory_board_required
board_role_denied
not_found
```

Provider 오류는 사용자 요청 실패로 전파하기보다 검증된 결정론적 fallback으로 처리한다. 내부 자격 증명과 상세 예외는 응답에 포함하지 않는다.

## persistence와 감사 계약

기존 운영 audit:

- `decisions`
- `notes`
- `conversations`
- `audit_log`
- `ontology_action_invocations`

`ontology_action_invocations`는 Action 요청 hash, actor, 상태, 성공 결과, audit ID를 저장한다. 성공한 Action은 대응하는 `ontology.action.<action_type>` 운영 감사 레코드를 반드시 가진다.

Dashboard persistence:

- `dashboard_templates`
- `dashboard_template_versions`
- `dashboard_user_preferences`
- `dashboard_saved_views`
- `dashboard_shares`

Template은 immutable version snapshot으로 저장하고 `dashboard_templates.current_version`이 현재 published version을 가리킨다. 사용자 preference는 template version과 optimistic revision을 함께 기록한다. Saved View는 사용자 소유이며 share는 만료 시각과 token hash만 저장한다.

Role workflow persistence:

- `audit_export_checkpoints`
- `field_task_actions`
- `template_publish_requests`
- `model_release_requests`
- `export_checkpoints`

Audit export checkpoint는 사건 재구성 hash를, generic export checkpoint는 permission-scoped snapshot hash와 artifact content hash를 보존한다. Field task는 actor·상태·측정·사진 metadata를 저장한다. Template·model request는 요청자, payload, 승인자, 승인 메모와 상태 전이를 보존한다.

identity와 RBAC foundation:

- `organizations`
- `workspaces`
- `users`
- `password_credentials`
- `sessions` (`last_seen_at`, user-agent·IP hash, `rotated_from`, revoke state)
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
- 개발자는 `scripts/reset_demo.py`로 decision·note·conversation·ontology Action invocation·operational audit만 초기화한다.
- identity, credential, administrator audit, Dashboard template·개인화·saved view·share를 일반 운영 초기화로 삭제하지 않는다.
- 설비 제어 API가 없다.
- 미등록 UI Block과 data field는 legacy UI Planner validation에서 차단된다.
- Ontology Planner의 unknown Object·property·Board·Evidence reference는 deterministic fallback 또는 validation failure로 차단된다.
- Login 12/min, Planner 30/min, Export 20/min, session management 20/min fixed-window rate limit을 적용한다.
- API 응답은 nosniff, frame deny, no-referrer, Permissions Policy, CSP와 민감 route no-store를 적용한다.
- 후속 질문은 허용된 intent만 지원한다.
- prompt injection 또는 실제 제어 요청은 지원 범위 밖으로 처리한다.
