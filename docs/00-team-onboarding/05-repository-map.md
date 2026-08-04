# Repository map

## 전체 구조

```text
mvp-프로젝트2/
├── api/ontology_dashboard/     FastAPI 제품 백엔드
├── web/src/                    React 제품 프론트엔드
├── ml/src/                     Dataset audit·model·evidence
├── schemas/                    JSON Schema와 계약
├── data/fixtures/              결정론적 Gold demo
├── tests/                      Backend contract·integration tests
├── web/e2e/                    Playwright 사용자 흐름
├── scripts/                    실행·seed·검증·정리 도구
├── infra/                      Docker·배포 구성
└── docs/                       제품·아키텍처·UI·운영 문서
```

## 기능별 코드 위치

| 기능 | Frontend | Backend·저장소 | 검증 |
|---|---|---|---|
| 회원가입·로그인 | `web/src/features/auth/` | `identity_models.py`, `identity_repository.py`, `routers/auth.py` | `tests/test_auth_rbac.py` |
| 관리자 승인·권한 | `web/src/features/admin/` | `routers/admin.py`, `user_permission_overrides`, `admin_notifications` | `signup-admin-confirmation.spec.ts` |
| 역할별 Landing | `roleLanding.ts`, `ManufacturingApp.tsx` | Principal roles·permissions | `role-report-adaptive-preferences.spec.ts` |
| 보고서 | `web/src/features/reports/` | Report draft router·repository | Report E2E와 backend tests |
| Dashboard | `web/src/features/dashboard/` | `dashboard_service.py`, catalog·preference repository | Dashboard stage tests·E2E |
| ECharts 렌더 완료 상태 | `EChartCanvas.tsx`, `EChartRuntime.tsx` | 해당 없음 | `team-share-captures.spec.ts` Canvas pixel 검증 |
| Dataset 적응형 구성 | `adaptiveExperience.ts` | Dataset Catalog API | Adaptive profile E2E |
| Analysis | `web/src/features/analysis/` | Analysis routers·execution·materialization | Analysis tests·E2E |
| Ontology | `web/src/features/ontology/` | Ontology registry·query·action·traversal | Ontology tests·E2E |
| Dataset Catalog | `web/src/features/datasets/` | `api/ontology_dashboard/datasets/` | Dataset projection tests |
| Agent Evidence | `web/src/features/agent/` | orchestration·evidence·Project3 client | Agent E2E·backend tests |
| Governance | `web/src/features/governance/` | `api/ontology_dashboard/governance/` | Governance E2E |
| 공통 Foundry UI | `web/src/ui/foundry/` | 해당 없음 | Vitest·visual E2E |

## 요청이 들어왔을 때 찾는 순서

### 역할별 첫 화면을 변경한다

```text
roleLanding.ts
→ ManufacturingApp.tsx
→ DashboardShell.tsx
→ role-report-adaptive-preferences.spec.ts
```

### Dataset별 화면 종류를 변경한다

```text
adaptiveExperience.ts
→ dashboard_catalog.py
→ DashboardBoardRenderer.tsx
→ EChartRuntime.tsx render completion state
→ Dataset Catalog types
→ adaptive profile E2E
```

### 사용자별 저장을 변경한다

```text
dashboard_service.py
→ dashboard preference repository
→ ManufacturingApp auto-save
→ displayPreferences.tsx
→ preference isolation tests
```

### 권한을 변경한다

```text
identity_models.py ROLE_PERMISSIONS
→ identity_repository.py overrides
→ API dependency permission checks
→ AdminApp UI
→ auth/RBAC tests
```

## 코드 경계

- Project 2는 Project 3에 직접 Cypher를 제출하지 않는다.
- Dataset Version과 Project를 동일시하지 않는다.
- Dashboard Presentation과 Analysis Definition을 분리한다.
- 역할 기본 Template과 사용자 Preference를 분리한다.
- UI 자동 구성은 검증된 Board Catalog 안에서 수행한다.

