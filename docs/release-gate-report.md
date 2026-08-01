# Ontology Dashboard Release Gate Report

- 실행일: 2026-08-01
- Gate: `ontology-dashboard-v0.6`
- 구현 범위: 16단계 제품 reframe부터 31단계 Ontology Planner·Export·보안·성능 hardening까지
- 결과: **PASS**
- 필수 검사: 10
- 통과: 10
- 실패: 0
- 브라우저 E2E 실제 실행: 예

## 검사 결과

| # | 검사 | 결과 |
|---:|---|---|
| 1 | 8개 Gold fixture envelope·품질 계약 | PASS |
| 2 | Python 단위·통합·인증·RBAC·Ontology·Dashboard·Planner·Export·Security 테스트 53건 | PASS |
| 3 | Gold 요구사항 평가 8/8 | PASS |
| 4 | Python compileall | PASS |
| 5 | 고정된 frontend 의존성 설치 | PASS |
| 6 | Vitest UI 단위 테스트 | PASS |
| 7 | TypeScript strict type check | PASS |
| 8 | Vite production build | PASS |
| 9 | Playwright Chromium 준비 | PASS |
| 10 | FastAPI+React Playwright E2E 13건 | PASS |

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

## Ontology instance·Action 검증

- Equipment·RiskEvent·Evidence·Inspection·MaintenanceAction ObjectRecord projection: PASS
- Equipment → RiskEvent → Evidence·Inspection 2-hop traversal: PASS
- object query의 `ontology.objects.read`와 workspace scope 검사: PASS
- Action target type·parameter·required permission 검사: PASS
- 동일 idempotency key + 동일 payload replay: PASS
- 동일 idempotency key + 다른 payload: 409
- virtual Inspection note materialization: PASS
- 기존 decision·note route의 Ontology Action 전환: PASS
- 성공 Action별 explicit operational audit와 audit ID persistence: PASS
- 데모 운영 초기화 시 Action invocation 제거·identity 보존: PASS

## Dashboard platform 검증

- 8개 역할별 default template·tab·board: PASS
- immutable template version과 preview API: PASS
- FDE 다른 역할 template preview·편집·승인 요청: PASS
- FDE direct publish: 403 차단
- Tenant admin 승인 시 immutable template publish: PASS
- resolved Dashboard JSON Schema: PASS
- mandatory board 삭제·숨김: 409 차단
- 개인 tab·board·parameter 저장과 재로그인 복원: PASS
- 사용자별 preference 격리와 role default restore: PASS
- template v3 seed와 이전 사용자 override merge: PASS
- Board Catalog 역할 필터·binding 검증: PASS
- HTML·script text board: 422 차단
- saved view와 parameter 복원: PASS
- cross-filter dependency graph와 affected board 표시: PASS
- share token hash 저장과 현재 사용자 workspace scope 재검사: PASS
- board fullscreen과 responsive shell: Playwright PASS

## Role workspace 검증

- Executive: 조직·workspace 위험·영향·추세 집계, 미조치 사건 drill-down: PASS
- Executive 응답의 세부 sensor history 비노출과 추정 가정: PASS
- Audit: input·model·policy·context·Evidence·Report version snapshot: PASS
- Evidence → Report section field trace와 Action history: PASS
- Export checkpoint SHA-256 hash와 explicit audit: PASS
- Field: 390px 모바일 task·안전·위치·checklist·측정·사진 metadata: PASS
- `complete_inspection` idempotent replay와 engineer handoff persistence: PASS
- Offline queue 미구현·future contract 명시: PASS
- FDE: customer workspace·ontology registry·deployment checklist·diagnostics: PASS
- FDE 응답의 credential·session·provider secret 비노출: PASS
- Model Console: training scope와 operational threshold scope 분리: PASS
- Threshold cost·slice·drift/schema·Gold 8/8 regression: PASS
- Model release pending request와 tenant-admin approve: PASS
- Role workspace JSON Schema: PASS

## Ontology Planner 검증

- 자연어 → registered Object query intent와 permission-scoped preview: PASS
- 역할·현재 Dashboard·hidden·wide preference signal Board recommendation: PASS
- FDE Dashboard draft의 target-role Catalog·mandatory Board·schema 검증: PASS
- Planner response JSON Schema: PASS
- credential Object·`password_hash` property 생성 시도: 차단
- Catalog 밖 arbitrary code Board 생성 시도: 차단
- unknown Evidence reference와 자동 제어·확정 원인 claim: 차단
- Provider 미설정·invalid 응답: deterministic fallback, persistence 없음
- Canvas preview 적용 후 별도 승인 요청 경계: Playwright PASS

## Export·보안·성능 검증

- JSON·CSV·PDF permission-scoped artifact: PASS
- snapshot SHA-256와 artifact SHA-256: PASS
- export checkpoint·`export.created` audit: PASS
- 사용자별 checkpoint 격리와 admin review: PASS
- session rotation과 old token revoke: PASS
- 60분 idle timeout·user-agent binding·다른 session revoke: PASS
- login rate limit·429·Retry-After: PASS
- security header·민감 route no-store: PASS
- 8개 역할 Planner·Export·Admin·FDE permission regression matrix: PASS
- 10+ Board resolve 120회 mean <30ms, p95 <60ms: PASS
- Planner·Export JSON Schema: PASS

## Frontend route와 기능 분리

```text
web/src/App.tsx                         route/auth orchestration only
web/src/features/auth/                 login, register, pending, AuthContext
web/src/features/manufacturing/        domain data orchestration and governed renderer adapter
web/src/features/dashboard/            shell, tabs, context, canvas, inspector, catalog and personalization
web/src/features/roles/                Executive·Audit·Field·FDE·Model contracts and renderers
web/src/features/planner/              Object query·Board recommendation·grounded narrative·Dashboard draft
web/src/features/admin/                tenant administrator and workflow approval control plane
web/src/features/ontology/types.ts     TypeScript ontology contracts
```

검증 route:

- `/login`
- `/register`
- `/pending`
- protected `/app`
- tenant-admin-only `/admin`

Playwright 13건:

1. manager와 engineer 계정의 서로 다른 Gold 화면
2. 인증 후 data-quality와 provider fallback
3. FDE admin 403과 tenant admin Users 화면
4. 회원가입 후 pending 화면
5. edit mode, mandatory 보호, catalog text board, 저장·reload, fullscreen
6. cross-filter, saved view와 share
7. Executive aggregate 이해와 unresolved drill-down
8. Audit reconstruction과 export checkpoint
9. 390px 모바일 Field task 완료
10. FDE Workbench와 template 승인 요청 경계
11. FDE Planner Object query와 non-persisted Dashboard draft
12. JSON artifact download와 export checkpoint
13. Model release 요청과 관리자 approval queue

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
- CSS: 약 50.10 kB, gzip 9.52 kB
- JavaScript: 약 299.55 kB, gzip 87.39 kB

## 재실행 명령

```bash
PYTHONPATH=api:ml/src python scripts/release_gate.py --with-e2e
```

새 Python 환경에서는 `pip install -e ml -e api`로 `argon2-cffi`를 포함한 API dependencies를 설치한다.

## 남아 있는 제한

- Ontology object query, relation traversal과 Action adapter는 제조 fixture projection 기반이다. 외부 datasource와 범용 domain pack adapter는 후속 범위다.
- persistent Dashboard는 SQLite와 stable-ID override merge를 사용한다. production PostgreSQL·Alembic migration은 후속 범위다.
- drag-and-drop은 HTML5 pointer interaction 기반이며 다중 사용자 실시간 공동 편집은 제공하지 않는다.
- 공유 링크는 tab·parameter 상태를 복원하지만 전체 개인 board layout snapshot 공유는 후속 범위다.
- 관리자 화면은 Users, Roles, Overview, Audit와 Template·Model Workflow Approvals를 제공한다. organization/integration control plane은 후속 단계다.
- Field photo는 binary upload가 아니라 검증된 metadata만 저장한다.
- Offline field queue는 실행 구현이 아니라 future contract만 정의한다.
- Executive 금액 영향은 실제 생산 단가 데이터가 없어 계산하지 않는다.
- Model training run metric artifact는 연결되지 않아 임의 metric을 생성하지 않는다.
- SQLite idempotent initialization을 사용한다. production PostgreSQL·Alembic 전환은 후속 범위다.
- login rate limit과 session rotation은 구현했지만 multi-instance shared limiter는 Redis로 교체해야 한다.
- enterprise SSO와 조직별 session policy는 아직 구현하지 않았다.
- 실제 제조 시계열·CMMS·MES 데이터로 검증하지 않았다.
- 실제 LLM provider 품질·비용·latency 벤치마크는 Vertex AI 설정 후 별도 수행해야 한다.
- Export artifact는 즉시 응답하며 object storage·retention policy는 후속 범위다.
- 실제 설비 제어와 자동 작업 지시는 의도적으로 제공하지 않는다.
