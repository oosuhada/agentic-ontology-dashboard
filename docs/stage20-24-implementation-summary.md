# 20~24단계 구현 요약 — Persistent Dashboard Platform

구현일: 2026-08-01

## 목표

19단계에서 연결한 Object·Link·Action foundation 위에 역할별 Dashboard template, tab, board를 영속화하고 사용자가 안전하게 편집·개인화·공유할 수 있는 Dashboard 플랫폼 shell을 구현한다.

## 20단계 — Template·Tab·Board persistence

### SQLite 모델

- `dashboard_templates`
- `dashboard_template_versions`
- `dashboard_user_preferences`
- `dashboard_saved_views`
- `dashboard_shares`

8개 역할마다 서로 다른 기본 template을 seed한다.

- tenant_admin
- executive_viewer
- process_manager
- process_engineer
- maintenance_technician
- quality_auditor
- ml_validator
- fde

각 template은 안정적인 tab ID와 board ID, mandatory board 목록, parameter definition, version을 가진다.

### 주요 API

- `GET /api/dashboards/resolved`
- `GET /api/dashboard-templates/{role_code}`
- `GET /api/dashboard-templates/{role_code}/versions`
- `GET /api/dashboard-templates/{role_code}/preview`
- `POST /api/dashboard-templates/{role_code}/publish`

FDE와 tenant admin만 다른 역할 template을 preview·publish할 수 있다. 일반 사용자는 자기 역할 template만 조회할 수 있다.

## 21단계 — 새 Dashboard shell UI

`web/src/features/dashboard/`로 shell 기능을 분리했다.

- `DashboardShell.tsx`
- `ContextPanel.tsx`
- `BoardCanvas.tsx`
- `BoardInspector.tsx`
- `BoardCatalogPanel.tsx`
- `DashboardBoardRenderer.tsx`
- `utils.ts`
- `types.ts`

화면 구조:

```text
Global header
├── Workspace selector
├── Domain pack·template version
└── User menu

Dashboard tabs + View/Edit toolbar

Context panel | 12-column Board canvas | Inspector
```

지원 layout 폭:

- 12/12: full width
- 6/12: 1/2
- 4/12: 1/3

1250px, 980px, 700px 구간에서 inspector·context panel·board canvas를 재배치한다.

## 22단계 — 개인화 저장과 복원

지원 기능:

- tab drag order
- board drag order
- 다른 tab으로 board 이동
- board 폭 변경
- hide/show
- board 복제·삭제
- custom tab
- active tab 저장
- parameter state 저장
- role default restore
- saved view

사용자 변경은 template 전체 복사본이 아니라 안정적인 ID 기준 override로 정규화해 저장한다. template version이 갱신되면 다음 원칙으로 병합한다.

- 새 template board는 자동 추가
- 기존 사용자 tab·board override 유지
- 삭제된 template ID override는 무시
- 병합이 발생하면 `merge_notices` 제공

optimistic `preference_revision`을 사용해 다른 세션의 변경 덮어쓰기를 `409 dashboard_revision_conflict`로 차단한다.

## 23단계 — Board catalog와 편집 UX

Board category:

- Suggested
- Observe
- Explore
- Explain
- Act
- Audit
- Build

지원 기능:

- 역할별 허용 catalog
- 검색·category 필터
- 특정 tab에 inline 추가
- 새 tab 생성
- plain text board
- board inspector
- FDE·admin template editor

서버 안전 검증:

- catalog 밖 definition 차단
- role에 허용되지 않은 board 차단
- width 범위 검증
- binding key·value type 검증
- HTML, script, `javascript:` 및 inline event handler 차단
- mandatory board 삭제·숨김 차단

## 24단계 — Parameter·Cross-filter·공유

기본 parameter:

- `selected_event_id`
- `selected_equipment_id`
- `status_filter`
- `intent`

Board catalog의 `emits`와 `accepts` 계약으로 dependency graph를 생성한다. Risk Event 선택 시 등록된 downstream board만 강조하며 영향 board 수를 context panel에 표시한다.

지원 기능:

- dashboard parameter state
- status filter
- intent 변경
- selection event
- affected board 표시
- saved view parameter 복원
- board fullscreen
- parameter share link

공유 token 원문은 DB에 저장하지 않고 SHA-256 hash만 저장한다. 공유 링크 조회 시에도 현재 로그인 사용자의 workspace scope와 selected RiskEvent object 접근 권한을 다시 검사하므로 공유 링크가 권한을 우회하지 않는다.

## 역할별 권한

추가 permission:

- `dashboards.read`
- `dashboards.personalize`
- `dashboards.share`
- `dashboards.templates.manage`

일반 역할은 read·personalize·share를 가진다. FDE는 template manage를 추가로 가지며 tenant admin은 전체 permission을 가진다.

## 테스트

`tests/test_dashboard_stages20_24.py` 6건:

1. 역할별 template 차이, version·preview, dependency graph, JSON Schema
2. 사용자별 개인화 저장·재로그인 복원·격리·기본값 복원
3. mandatory board 삭제 차단
4. 역할별 catalog와 HTML·script 차단
5. saved view·share parameter 복원과 workspace scope 차단
6. FDE template publish와 기존 사용자 override 병합

Playwright 6건:

1. manager·engineer governed view 차이
2. data quality·provider fallback
3. FDE admin 차단과 tenant admin
4. 회원가입 pending
5. edit mode, mandatory 보호, catalog text board, 저장·reload, fullscreen
6. cross-filter, saved view, share

## 주요 계약 파일

- `schemas/dashboard-platform.schema.json`
- `api/factory_signal_board/dashboard_models.py`
- `web/src/features/dashboard/types.ts`

## 남은 단계

25~31단계:

- 임원 Viewer 고도화
- 품질·감사 Viewer 고도화
- 현장 작업자 모바일 workflow
- FDE Workbench 고도화
- 데이터 사이언티스트 Console
- LLM·Ontology Planner
- Export·보안·성능·릴리스 hardening
