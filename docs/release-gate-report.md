# Ontology Dashboard Release Gate Report

- 실행일: 2026-08-01
- Gate: `ontology-dashboard-v0.2`
- 구현 범위: 16단계 제품 reframe, 17단계 인증, 18단계 RBAC·관리자 foundation
- 결과: **PASS**
- 필수 검사: 10
- 통과: 10
- 실패: 0
- 브라우저 E2E 실제 실행: 예

## 검사 결과

| # | 검사 | 결과 |
|---:|---|---|
| 1 | 8개 Gold fixture envelope·품질 계약 | PASS |
| 2 | Python 단위·통합·인증·RBAC·안전 테스트 23건 | PASS |
| 3 | Gold 요구사항 평가 8/8 | PASS |
| 4 | Python compileall | PASS |
| 5 | 고정된 frontend 의존성 설치 | PASS |
| 6 | Vitest UI 단위 테스트 | PASS |
| 7 | TypeScript strict type check | PASS |
| 8 | Vite production build | PASS |
| 9 | Playwright Chromium 준비 | PASS |
| 10 | FastAPI+React Playwright E2E 4건 | PASS |

## 인증·권한 검증

- 8개 development demo account 로그인: PASS
- DB password 저장 형식 Argon2id, 평문 미저장: PASS
- 잘못된 비밀번호: 차단
- 회원가입 결과 `pending_approval`: PASS
- pending 로그인: 차단
- tenant admin 승인 후 역할·workspace scope 반영: PASS
- disabled 로그인: 차단
- logout 후 protected API: 401
- state-changing cookie request CSRF: PASS
- 일반 사용자와 FDE의 `/api/admin/*` 접근: 403
- FDE에 admin permission 없음: PASS
- workspace scope 제거 후 제조 사건 조회: 403
- 관리자 변경 before/after audit: PASS
- `APP_ENV=production` demo seed: 강제 차단
- 공개 `/api/demo/reset`: 없음

## Frontend route와 기능 분리

```text
web/src/App.tsx                         route/auth orchestration only
web/src/features/auth/                 login, register, pending, AuthContext
web/src/features/manufacturing/        existing Gold dashboard domain pack
web/src/features/admin/                tenant administrator foundation
web/src/features/ontology/types.ts     TypeScript ontology contracts
```

검증 route:

- `/login`
- `/register`
- `/pending`
- protected `/app`
- tenant-admin-only `/admin`

Playwright 4건:

1. manager와 engineer 계정의 서로 다른 Gold 화면
2. 인증 후 data-quality와 provider fallback
3. FDE admin 403과 tenant admin Users 화면
4. 회원가입 후 pending 화면

## Gold 평가 요약

- 시나리오: 8
- 통과: 8
- 실패: 0
- legacy planner 역할: manager, engineer
- 금지 운영 단정: 0
- Evidence 추적 불가 Report section: 0
- GS-008 LLM·Planner fallback: PASS

시나리오별 첫 블록:

| Scenario | Manager | Engineer |
|---|---|---|
| GS-001 정상 | `StatusSummary` | `StatusSummary` |
| GS-002 공구 마모 | `StatusSummary` | `SensorLineChart` |
| GS-003 열 방출 | `StatusSummary` | `SensorLineChart` |
| GS-004 동력·과부하 | `StatusSummary` | `SensorLineChart` |
| GS-005 복합 이상 | `StatusSummary` | `FactorContribution` |
| GS-006 저신뢰 | `DataQualityWarning` | `DataQualityWarning` |
| GS-007 데이터 오류 | `DataQualityWarning` | `DataQualityWarning` |
| GS-008 LLM offline | `StatusSummary` | `SensorLineChart` |

## Production build

- HTML: 약 0.52 kB
- CSS: 약 20.37 kB, gzip 4.78 kB
- JavaScript: 약 232.01 kB, gzip 71.51 kB

## 재실행 명령

```bash
PYTHONPATH=api:ml/src python scripts/release_gate.py --with-e2e
```

새 Python 환경에서는 `pip install -e ml -e api`로 `argon2-cffi`를 포함한 API dependencies를 설치한다.

## 남아 있는 제한

- Ontology registry는 ObjectType·LinkType·ActionType foundation이다. object instance query, relation traversal과 Action execution adapter는 19단계 범위다.
- 역할별 landing은 서로 다르지만 persistent dashboard template·tab·board 모델은 20단계 이후 범위다.
- 관리자 화면은 Users, Roles, Overview와 Audit foundation이다. organization/template/integration control plane은 후속 단계다.
- SQLite idempotent initialization을 사용한다. production PostgreSQL·Alembic 전환은 후속 범위다.
- 로그인 rate limit, session rotation, enterprise SSO는 아직 구현하지 않았다.
- 실제 제조 시계열·CMMS·MES 데이터로 검증하지 않았다.
- 실제 LLM provider 품질 벤치마크는 Vertex AI 설정 후 별도 수행해야 한다.
- 실제 설비 제어와 자동 작업 지시는 의도적으로 제공하지 않는다.
