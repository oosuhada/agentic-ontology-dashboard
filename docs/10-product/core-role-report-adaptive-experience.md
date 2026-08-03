# Role Report · Adaptive Workspace · Personal Preference

## 이 문서의 목적

이 문서는 Ontology Dashboard의 핵심 제품 경험 세 가지를 설명한다.

1. 역할에 따라 첫 화면과 업무 흐름이 달라진다.
2. 프로젝트와 데이터셋의 성격에 따라 Dashboard 구성 자체가 달라진다.
3. 같은 역할이라도 사용자별 화면 설정은 독립적으로 저장되고 다음 로그인에 복원된다.

이 기능들은 단순한 UI 변형이 아니라 다음 제품 흐름을 구현하기 위한 것이다.

```text
실무자가 데이터와 근거를 검토
→ 공유 보고서를 작성·수정
→ 운영 매니저와 임원이 보고서를 읽고 판단
→ 필요할 때 상세 Dashboard와 Analysis로 내려감
```

## 1. 역할별 첫 화면

### 보고서가 기본인 역할

다음 역할은 로그인 후 `Reports`를 기본 업무 화면으로 사용한다.

- 임원 Viewer
- 운영 매니저
- 품질·감사 Viewer

보고서 화면은 다음을 함께 보여준다.

- 업무 설명과 판단 요약
- 섹션별 서술형 보고 내용
- 각 문단이 참조하는 Evidence field ID
- 시계열 근거
- 주요 기여 요인
- 운영 영향과 권고 결정
- 선택 사건과 전체 위험 현황
- 상세 Dashboard로 이동하는 drill-down

보고서 독자는 보고서 내용을 수정하지 않고 공유 revision을 읽는다.

### Dashboard가 기본인 역할

다음 역할은 로그인 후 `Dashboards`를 기본 업무 화면으로 사용한다.

- 도메인 엔지니어
- 현장 작업자
- 데이터 사이언티스트
- Forward Deployed Engineer

이 역할들은 세부 데이터, 객체, Evidence, Analysis와 작업 상태를 직접 다룬다. `Reports` 메뉴로 이동하면 보고서 편집 권한이 있는 사용자는 다음 내용을 수정할 수 있다.

- 보고서 제목
- 전체 요약
- 섹션 제목
- 섹션 본문

저장된 보고서는 사용자 개인 메모가 아니라 `workspace + event` 범위의 공유 보고서 revision이다. 따라서 엔지니어가 저장한 보고서를 운영 매니저와 임원이 같은 내용으로 읽는다.

### 역할 설정 위치

```text
web/src/features/manufacturing/roleLanding.ts
```

각 역할은 다음 값을 갖는다.

```ts
defaultWorkspaceView: "report" | "dashboard"
reportMode: "reader" | "editor"
```

실제 편집 가능 여부는 `reportMode`와 서버 권한 `events.note`를 모두 확인한다.

## 2. 공유 보고서 저장 계약

보고서 draft는 다음 범위로 저장된다.

```text
organization
└── project
    └── workspace
        └── event
            └── shared report revision
```

저장 필드:

- headline
- summary
- sections
- evidence field references
- revision
- updated by
- updated at

API:

```text
GET /api/reports/draft
PUT /api/reports/draft
```

권한:

- 읽기: `events.read`
- 수정: `events.note`

동시에 다른 사용자가 저장한 경우 `report_revision_conflict`를 반환한다.

관련 코드:

```text
api/ontology_dashboard/dashboard_models.py
api/ontology_dashboard/dashboard_repository.py
api/ontology_dashboard/dashboard_service.py
api/ontology_dashboard/routers/dashboards.py
web/src/features/reports/RoleReportWorkbench.tsx
```

## 3. 프로젝트·데이터셋 적응형 화면

동일한 Board 템플릿에 데이터만 교체하지 않는다. 프로젝트 이름, Domain Pack과 Dataset Catalog metadata를 분석해 적응형 프로필을 결정한다.

현재 프로필:

### Factory Reliability

```text
Equipment · Line · Failure Risk
```

- 설비 위험과 생산 라인 영향 중심
- 7:5 비율의 주요 분석과 의사결정 화면
- 위험 분포, 라인 비교, 이벤트 테이블 중심

### Fleet Maintenance

```text
Vehicle · Service · Route Impact
```

- 12-column 전사 요약이 첫 Board
- 차량군 비교와 정비 백로그 중심
- 상태 구성은 stacked bar, 추세는 area 중심

### Compressor Monitoring

```text
Telemetry · Pressure · Anomaly Window
```

- 8:4 비율의 대형 시계열과 상태 카드
- 연속 센서 추세와 이상 구간 중심
- 주요 시각화는 line chart 중심

### Generic Operations

알 수 없는 데이터셋도 다음 정보를 이용해 일반 운영 구성을 만든다.

- 데이터셋 개수
- 레코드 수
- source type
- 프로젝트와 Domain Pack 이름

적응형 기본값은 개인 preference가 아직 없는 사용자에게만 적용된다. 사용자가 저장한 구성이 있다면 프로젝트 프로필이 개인 구성을 덮어쓰지 않는다.

관련 코드:

```text
web/src/features/manufacturing/adaptiveExperience.ts
```

## 4. 사용자별 Personal Preference

서버 Dashboard preference의 식별 범위:

```text
user_id + workspace_id + template_id
```

따라서 같은 `process_engineer` 역할이어도 사용자 A와 사용자 B는 서로 다른 다음 정보를 저장할 수 있다.

- Tab 순서와 활성 Tab
- Board 위치와 크기
- Board 숨김과 즐겨찾기
- 개인 Board
- Parameter state
- 시각화 설정

Dashboard 편집 후 1.4초 동안 추가 변경이 없으면 자동 저장한다. 저장 상태는 상단에 다음과 같이 표시한다.

```text
Role default
Saving personal layout
Personalized for this user
```

브라우저에 저장되는 역할과 첫 화면 선택도 사용자 ID를 포함한다.

```text
active role key
= user_id + project_id

workspace view key
= user_id + project_id + role
```

로그아웃 후 다른 사용자가 같은 브라우저에서 로그인해도 이전 사용자의 역할 선택이나 첫 화면 선택이 섞이지 않는다.

## 5. 좌측 Navigation 정렬

좌측 Navigation은 두 레이어로 구성된다.

```text
Dark platform rail
+
Light resource navigation
```

두 영역의 같은 Workbench 아이콘과 행 중심선이 맞도록 다음을 통일했다.

- Platform shortcut 시작 위치
- Resource navigation row 높이
- Active icon 중심선
- Active left border 중심선

브라우저 검증에서는 두 active item 중심 차이를 3px 이하로 확인한다.

## 6. 확인 시나리오

### 운영 매니저

```text
manager@ontology.local
Manager!2026
```

1. 로그인하면 Report가 먼저 열린다.
2. 서술형 보고서와 근거 차트를 읽는다.
3. `Open detailed dashboard`로 상세 화면에 진입한다.

### 도메인 엔지니어

```text
engineer@ontology.local
Engineer!2026
```

1. 로그인하면 Dashboard가 먼저 열린다.
2. Reports로 이동한다.
3. 보고서를 수정하고 공유 revision을 저장한다.
4. 로그아웃한다.
5. 운영 매니저로 로그인하면 수정된 보고서를 읽을 수 있다.

### 데이터 프로필 변경

FDE 계정으로 Project를 다음 순서로 변경한다.

```text
Manufacturing Demo Project
→ Azure Fleet Maintenance
→ MetroPT Compressor Monitoring
```

화면의 프로필 문구뿐 아니라 Board 배치와 시각화 기본값이 변경된다.

### 개인 설정 복원

1. 엔지니어 계정에서 Board 즐겨찾기나 배치를 수정한다.
2. 자동 저장 상태를 확인한다.
3. 새로고침 또는 재로그인한다.
4. 같은 구성이 복원된다.
5. 다른 엔지니어 계정에서는 역할 기본값이 표시된다.

## 7. 검증

자동 검증 파일:

```text
tests/test_dashboard_stages20_24.py
web/e2e/role-report-adaptive-preferences.spec.ts
```

캡처 자산:

```text
docs/ui/core-experience/final/
├── manager-report-landing.png
├── manager-dashboard-drilldown.png
├── engineer-report-editor.png
├── engineer-report-saved.png
├── fleet-adaptive-dashboard.png
└── compressor-adaptive-dashboard.png
```
