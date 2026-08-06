# 시스템 아키텍처

## 실행 구성

```text
Browser
  └─ React MVP
      ├─ Auth session
      ├─ Project / Workspace scope
      ├─ Canonical Runtime adapter
      └─ Gold Fixture fallback adapter
            │
            ▼
FastAPI
  ├─ /api/auth
  ├─ /api/projects
  ├─ /api/.../predictive-maintenance
  └─ /api/events/{event_id}
            │
            ├─ PostgreSQL Canonical V3.1 facts and Result Artifacts
            └─ local Gold Fixture + audit repository fallback
```

## 프론트엔드 경계

- `web/src/App.tsx`: 로그인과 현재 MVP 경로만 조립
- `web/src/features/auth`: 두 역할 세션 시작
- `web/src/features/mvp`: 네 화면, selection context, ViewModel/Adapter
- `web/src/features/predictive-maintenance/types.ts`: Canonical Runtime 응답 타입
- `web/src/api.ts`: 현재 화면이 사용하는 최소 API client

프론트엔드는 API payload를 화면에 직접 흩뿌리지 않습니다. `features/mvp/api/mvpAdapters.ts`에서 `MvpAsset`, `MvpEvent`, `MvpMetrics`, `MvpEventDetailModel`로 정규화합니다.

## 백엔드 경계

`api/ontology_dashboard/main.py`는 다음 Router만 등록합니다.

- `system`: liveness/readiness와 OpenAPI contract
- `auth`: login, logout, current user
- `projects`: Project, Workspace, Project Event
- `predictive_maintenance_runtime`: Canonical V3.1 조회·replay
- `manufacturing`: Evidence, Report, Decision, Note, Activity

과거 기능 모듈이 파일로 남아 있더라도 Router에 등록되지 않으면 제품 계약이 아닙니다. 저장소 정리 기준은 활성 import graph와 현재 테스트입니다.

## 데이터 선택 순서

1. Project와 Workspace 조회
2. Canonical dashboard와 latest Result Artifact를 병렬 조회
3. Canonical dashboard 실패 시 Project Event Gold Fixture 조회
4. Result Artifact와 Event를 `asset_id` 기준으로 병합하고 최신 관측만 유지
5. 상세 화면에서 Canonical selected detail, Evidence, Report, Activity를 독립 조회
6. 각 요청 실패는 해당 패널 warning으로 격리

## 보안 경계

- HttpOnly session cookie와 별도 CSRF cookie/header
- Project scope, Workspace scope, permission을 서버에서 재검증
- Decision은 `events.decision`, Note는 `events.note` 필요
- actor 이름은 요청 본문이 아니라 인증 Principal에서 결정
- 모델 권고는 실행 명령이 아니며 `review_shutdown`도 자동 정지를 의미하지 않음
