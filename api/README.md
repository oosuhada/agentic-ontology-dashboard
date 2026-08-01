# Ontology Dashboard API

FastAPI 서비스는 identity, hardened cookie session, RBAC·workspace scope, ontology registry, idempotent Action, persistent Dashboard, 역할 workspace, 검증된 자연어 Planner와 JSON·CSV·PDF export를 제공한다.

## 실행

```bash
export PYTHONPATH="$PWD/api:$PWD/ml/src"
uvicorn ontology_dashboard.app:app --host 127.0.0.1 --port 8100
```

- Swagger: `http://127.0.0.1:8100/docs`
- Health: `http://127.0.0.1:8100/health`

개발·데모 환경에서는 8개 test account를 idempotent하게 seed한다. `APP_ENV=production`에서는 seed를 허용하지 않는다.

## 모듈

- `identity_models.py`: identity request model, principal, role·permission definitions
- `identity_repository.py`: SQLite users, Argon2id credentials, sessions, workspace scopes, admin audit
- `identity.py`: authentication, CSRF and permission policy facade
- `ontology.py`: domain-neutral Object·Link·Action·Evidence·Dashboard·Board contract와 manufacturing registry
- `ontology_adapter.py`: manufacturing fixture·Evidence·activity의 ObjectRecord·LinkRecord projection
- `ontology_repository.py`: Action idempotency state와 persisted result
- `ontology_service.py`: object query, traversal, Action validation·execution·audit
- `dashboard_models.py`: strict Dashboard template·tab·board·preference·share contract
- `dashboard_catalog.py`: 역할별 Board Catalog와 default template seed
- `dashboard_repository.py`: template version, user preference, saved view, share persistence
- `dashboard_service.py`: resolved dashboard, override merge, mandatory policy, dependency graph와 보안 검증
- `role_workflow_models.py`: 역할 workspace, export checkpoint, field task와 승인 request contract
- `role_workflow_repository.py`: audit checkpoint, field Action, template·model approval persistence
- `role_workflow_service.py`: 역할 집계·재구성·diagnostic·release workflow orchestration
- `ontology_planner_models.py`: typed Object query·Board recommendation·Dashboard draft·grounded narrative contract
- `ontology_planner_service.py`: registry·Catalog·Evidence whitelist와 provider fail-closed planning
- `security.py`: login·Planner·Export·session fixed-window rate limit
- `export_models.py`: export request·checkpoint contract
- `export_repository.py`: snapshot·artifact hash와 export checkpoint persistence
- `export_service.py`: permission-scoped JSON·CSV·PDF generation과 operational audit
- `service.py`: 기존 manufacturing domain pack orchestration
- `reports.py`: deterministic manager/engineer reports
- `llm.py`: OpenAI-compatible/Vertex AI provider와 grounding fallback
- `planner.py`: 등록된 UI Block 전용 Planner
- `context.py`: Project 3 HTTP Adapter와 fallback
- `repository.py`: SQLite decision/note/conversation/operational audit
- `conversation.py`: 제한된 intent와 안전한 후속 질문
- `main.py`: auth, ontology, manufacturing, admin routes와 server-side permission 검사

## 보안 경계

- session token은 HttpOnly SameSite cookie로 전달하고 DB에는 SHA-256 hash만 저장한다.
- session은 12시간 absolute expiry, 60분 idle timeout, user-agent binding, explicit rotation과 다른 세션 revoke를 지원한다.
- login·Planner·Export·session 관리 endpoint는 rate limit을 적용한다.
- API는 nosniff, frame deny, no-referrer, Permissions Policy, CSP와 no-store header를 적용한다.
- state-changing cookie 요청은 CSRF cookie/header를 검증한다.
- 모든 `/api/admin/*` route는 tenant-admin permission을 검사한다.
- 기존 제조 API와 ontology object API는 `manufacturing-demo` workspace scope를 검사한다.
- object 조회는 `ontology.objects.read`, Action 실행은 registry의 required permission을 검사한다.
- Action은 같은 사용자·workspace의 idempotency key를 선점하고 성공 결과와 audit ID를 저장한다.
- Dashboard 개인 설정은 optimistic revision으로 동시 변경 충돌을 차단한다.
- Board Catalog 밖 definition, 역할에 허용되지 않은 board, 잘못된 binding, HTML·script text를 서버에서 거부한다.
- 공유 링크 조회 시 현재 사용자의 workspace scope와 selected object 접근을 다시 검사한다.
- FDE는 template 초안을 편집하고 승인 요청할 수 있지만 직접 publish하거나 credential·session·secret을 조회할 수 없다.
- 현장 완료·문제·blocked 상태는 Ontology Action idempotency와 audit를 사용한다.
- Audit export checkpoint는 snapshot SHA-256 hash와 요청자를 저장한다.
- Model release와 template publish는 tenant-admin 승인 전 운영 상태를 변경하지 않는다.
- 자연어 Planner는 registered Object·property·Board·Evidence reference만 사용하며 결과를 자동 저장하지 않는다.
- Export는 permission-scoped snapshot과 artifact hash를 보존하며 일반 사용자는 자신의 checkpoint만 조회한다.
- 요청 body의 actor나 role만 신뢰하지 않는다.
- 공개 reset endpoint와 설비 제어 endpoint는 제공하지 않는다.
