# Ontology Dashboard API

FastAPI 서비스는 identity, hardened cookie session, RBAC·workspace scope, ontology registry, idempotent Action, persistent Dashboard, 역할 workspace, 검증된 자연어 Planner와 JSON·CSV·PDF export를 제공한다.

## 실행

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8100
```

- Swagger: `http://127.0.0.1:8100/docs`
- Health: `http://127.0.0.1:8100/health`

개발·데모 환경에서는 8개 test account를 idempotent하게 seed한다. `APP_ENV=production`에서는 seed를 허용하지 않는다.

## 도메인 및 구조

제품 Backend Python 패키지의 유일한 Source of Truth는 `app/`이다.

- `app/identity`: IAM bounded context (User, Session, Role, Permission, Organization, ProjectMembership, WorkspaceScope, OIDC, SCIM, MFA)
- `app/project`: Project 메타데이터 및 라이프사이클 관리
- `app/equipment`: 설비 마스터 데이터 및 운영 상태 관리
- `app/ontology`: Object, Link, Action 온톨로지 레지스트리 및 인스턴스 그래프
- `app/dataset`: 데이터셋 소스 및 프로젝션
- `app/diagnosis`: 런타임 추론 및 제품 Result Artifact / Evidence 최종 생성
- `app/maintenance`: Closed-loop 추천, 운영 결정, 점검/정비 작업지시, 정비 이벤트 및 이력 (구 closed_loop)
- `app/dashboard`: 여러 public query와 read model을 조합하는 application/read-model composition 영역
- `app/report`: 결정론적 엔지니어/매니저 보고서 및 내보내기 관리
- `app/planner`: 등록된 온톨로지 및 UI Block 기반 안전한 자연어 플래너
- `app/governance`: 모델 릴리즈, 템플릿 승인 및 거버넌스 감사
- `app/common`: 도메인 중립적 cross-cutting 유틸리티 및 기본 예외
- `app/infra`: 순수 기술 구현 (DB 연결, Storage, 외부 API, LLM 프로바이더, 메시징, Observability)

> `systems/backend/ontology_dashboard`는 정식 compatibility architecture가 아니라 제거 대상 legacy migration source다. Migration 완료 전까지 한시적으로 존재할 수 있으나 신규 기능 또는 신규 파일 추가는 금지한다.

레거시 파일별 `MOVE | SPLIT | REPLACE | REMOVE | DEFER` 처분과 담당 Phase는
[`docs/backend-migration-map.md`](../../docs/backend-migration-map.md)를 따른다. 현재 import되거나
테스트된다는 사실만으로 새 구조에 자동 이관하지 않는다.

Phase 0.5에서는 160개 legacy Python Source 전체의 처분을 최종화했고 `DEFER=0`을
gate로 고정한다. Analysis/Agent/Modeling Workbench, generic Platform automation/branching/
durable runtime/MLOps/pipeline은 존재 여부와 무관하게 제품 Target 근거가 없어 제거 대상으로
분류한다. 반대로 PdM ontology materialization, Project 3 typed integration, artifact/dataset/
ontology capability처럼 유지 근거가 있는 기능은 해당 owner domain/Infra로만 분해한다.

Migration Ledger는 다음 deterministic check로 검증한다.

```bash
python3 scripts/check_backend_migration_ledger.py
```

이 검사는 모든 `systems/backend/ontology_dashboard/**/*.py`가 ledger에 정확히 한 번 포함되는지,
처분 enum이 유효한지, 중복/누락이 없는지, `UNDECIDED`/`DEFER`가 남지 않는지를 확인하며
`systems/verify_architecture.py`에도 연결된다.

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
