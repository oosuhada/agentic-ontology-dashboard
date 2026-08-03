# Ontology Dashboard API

FastAPI 서비스는 identity, cookie session, RBAC·workspace scope, ontology registry와 기존 Manufacturing Predictive Maintenance Pack의 Evidence·Report·Layout·사용자 활동을 제공한다.

## 실행

```bash
export PYTHONPATH="$PWD/api:$PWD/ml/src"
uvicorn factory_signal_board.main:app --host 127.0.0.1 --port 8100
```

- Swagger: `http://127.0.0.1:8100/docs`
- Health: `http://127.0.0.1:8100/health`

개발·데모 환경에서는 8개 test account를 idempotent하게 seed한다. `APP_ENV=production`에서는 seed를 허용하지 않는다.

## 모듈

- `identity_models.py`: identity request model, principal, role·permission definitions
- `identity_repository.py`: SQLite users, Argon2id credentials, sessions, workspace scopes, admin audit
- `identity.py`: authentication, CSRF and permission policy facade
- `ontology.py`: domain-neutral Object·Link·Action·Evidence·Dashboard·Board contract와 manufacturing registry
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
- state-changing cookie 요청은 CSRF cookie/header를 검증한다.
- 모든 `/api/admin/*` route는 tenant-admin permission을 검사한다.
- 기존 제조 API는 `manufacturing-demo` workspace scope를 검사한다.
- 요청 body의 actor나 role만 신뢰하지 않는다.
- 공개 reset endpoint와 설비 제어 endpoint는 제공하지 않는다.
