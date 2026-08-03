# Palantir Contour Dashboard 벤치마크 분석

- 대상 제품: Palantir Foundry Contour Dashboard
- 분석 목적: Ontology Dashboard의 탭·보드·파라미터·편집·개인화·권한 구조 설계
- 기준일: 2026-08-01
- 참고 자료:
  - Palantir Contour 대시보드 시작하기
  - Palantir Contour 보드 추가
  - Palantir Foundry Ontology 개요
  - Palantir Action Types와 permission 문서
  - 사용자가 첨부한 Contour 편집·보기 화면 4개

> 이 문서는 Palantir UI를 그대로 복제하기 위한 문서가 아니다. 검증된 상호작용 패턴을 적극적으로 벤치마킹하되, Ontology Dashboard의 역할 기반 기본 화면과 사용자별 영구 저장 요구에 맞게 확장한다.

---

# 1. 핵심 결론

Palantir Contour에서 가장 중요한 개념은 차트의 디자인보다 다음 구조다.

```text
Analysis path
→ reusable boards
→ dashboard tabs
→ parameters
→ downstream filtering
→ viewer/editor permission separation
→ share/export
```

Ontology Dashboard에 적용할 핵심:

1. 화면을 하나의 거대한 React 페이지가 아니라 재사용 가능한 `Board` 집합으로 구성한다.
2. 대시보드는 상단 `Tab`으로 업무 맥락을 구분한다.
3. 좌측 패널은 프로젝트 목록보다 parameter·filter·saved view·ontology context에 사용한다.
4. 보기 모드와 편집 모드를 명확히 분리한다.
5. Board 순서·크기·탭 이동은 기반 데이터·분석 로직과 분리한다.
6. 차트 선택이 연결된 Board에 전파되는 cross-filter 구조를 만든다.
7. 역할 default view 위에 사용자 personal override를 저장한다.
8. 조직 template과 개인 설정을 versioned data로 관리한다.
9. Board는 ontology object·link·action에 binding한다.
10. 권한은 dashboard visibility뿐 아니라 object, property, action 단위로 적용한다.

---

# 2. 첨부 화면 분석

## 2.1 화면 1 — 분석 편집과 Dashboard Preview

첨부 화면에서 확인되는 구성:

- 상단 breadcrumb와 분석 이름
- `Open dashboard`와 파란색 `Dashboard` 버튼
- 좌측 `Dashboard preview`
- 좌측 preview 안에 text·chart·distribution·time-series board 목록
- 중앙 분석 canvas
- 우측 chart 설정 inspector
- board별 `Add to dashboard`

### 제품적으로 중요한 점

분석 화면과 대시보드 화면이 분리돼 있다.

- 분석가는 데이터를 가공하고 시각화를 만든다.
- 대시보드는 검증된 결과 Board를 선별해 사용자에게 제공한다.
- Dashboard preview는 게시 전 결과를 즉시 확인하는 bridge다.

### Ontology Dashboard 적용

현재 앱은 API가 즉시 layout을 반환하고 React가 렌더링한다. 이를 다음 구조로 확장한다.

```text
Ontology Query / Analysis
→ Board Definition
→ Board Instance
→ Dashboard Template
→ User Dashboard Instance
```

FDE와 데이터 사이언티스트는 Board를 만들고, 관리자·FDE는 dashboard template에 배치한다. 일반 사용자는 자신의 역할에 게시된 template을 사용한다.

### 우측 Inspector 적용

Palantir 화면은 원시 column과 aggregation을 설정한다. Ontology Dashboard에서는 이를 다음처럼 바꾼다.

```text
Data tab
- Object type
- Object set query
- Linked object traversal
- Property
- Aggregation
- Time property
- Grouping

Interaction tab
- Parameters
- Cross-filter output
- Cross-filter targets
- Drill-down target
- Action binding

Access tab
- Visible roles
- Resource scope
- Sensitive property masking
- Export policy
```

---

## 2.2 화면 2 — Add to Dashboard Dropdown

첨부 화면에서 `Add to dashboard` dropdown으로 다음이 가능하다.

- 기존 dashboard tab에 추가
- 새 tab 생성 후 추가

### 제품적으로 중요한 점

Board는 특정 페이지에 하드코딩된 컴포넌트가 아니라 dashboard와 tab 사이를 이동할 수 있는 독립 단위다.

### Ontology Dashboard 적용

Board 추가 UX:

```text
Add board
├── 현재 tab에 추가
├── 기존 tab 선택
├── 새 tab 생성
├── 개인 dashboard에 추가
└── 역할 template draft에 추가 — 권한 필요
```

Board 추가 시 저장해야 하는 값:

- dashboard ID
- tab ID
- board definition ID
- query binding
- parameter binding
- order
- width·height
- visibility policy
- required 여부

---

## 2.3 화면 3 — Dashboard Viewer와 Parameter Panel

첨부 화면에서 확인되는 구성:

- 상단 안내 영역
- 좌측 parameter panel
- 중앙 dashboard canvas
- parameter 값 변경 후 Apply
- board마다 현재 parameter 값 표시
- 전체화면 진입

### 제품적으로 중요한 점

Viewer는 dashboard 구조를 변경하지 않고도 parameter를 통해 데이터를 탐색한다.

### Ontology Dashboard 적용

좌측 sidebar는 다음 contextual panel로 사용한다.

```text
Parameters
Filters
Saved Views
Selected Object
Linked Objects
My Tasks
```

현재 좌측 설비 사건 목록은 다음 중 하나로 이동한다.

- `Object Priority List` Board
- 선택된 object context panel
- global object search result

즉, 프로젝트·사건 목록을 항상 좌측 navigation에 고정하지 않는다.

---

## 2.4 화면 4 — Multi-board Dashboard와 Inline Insert

첨부 화면에서 확인되는 구성:

- 여러 Board가 grid에 배치
- 2열 layout
- Board footer에 `Affects N boards`
- Board 사이 hover 영역에 파란색 `+`
- drag handle
- 상단 tab-like dashboard structure

### 제품적으로 중요한 점

Board 간 관계가 화면에서 설명된다.

`Affects 3 boards`는 사용자가 chart selection의 영향 범위를 이해하게 한다. cross-filter가 마법처럼 작동하지 않고 dependency를 설명한다.

### Ontology Dashboard 적용

각 Board는 interaction metadata를 가진다.

```json
{
  "emits": ["object_selection", "date_range"],
  "affects": ["board-2", "board-3"],
  "selection_scope": "tab"
}
```

Board footer:

```text
이 선택이 3개 보드에 영향을 줍니다.
```

사용자가 hover하면 대상 Board 목록을 표시한다.

---

# 3. Palantir 공식 문서에서 확인한 핵심 기능

## 3.1 Dashboard 생성

Contour 분석 하나는 하나의 dashboard와 연결되며, Visualize Board를 dashboard에 추가할 수 있다. Dashboard preview에서 이름을 지정하고 drag-and-drop으로 순서를 바꿀 수 있다.

Ontology Dashboard 적용:

- 분석 결과와 게시된 dashboard 분리
- Board preview
- template draft
- publish workflow

공식 문서:

- https://www.palantir.com/docs/kr/foundry/contour/dashboards-getting-started

## 3.2 탭

Palantir는 dashboard를 tab으로 구성하고 tab 이름·순서를 바꾸며 Board와 text를 tab 사이에서 이동할 수 있게 한다.

Ontology Dashboard 적용:

- top tab navigation
- 역할별 tab template
- 개인 tab order
- tab별 parameter scope
- tab별 board catalog context

## 3.3 Board 순서 변경

Palantir는 dashboard의 시각적 순서와 기반 분석 경로를 분리한다.

Ontology Dashboard 적용:

- semantic query와 layout 분리
- 사용자가 Board를 이동해도 Evidence·query logic은 변경되지 않음
- personal override는 layout layer에만 기록

## 3.4 Text와 inline parameter

Palantir는 dashboard text, Board title, tab title, dashboard title에서 parameter 값을 사용할 수 있다.

Ontology Dashboard 적용:

```text
${organization.name}의 ${date_range} 위험 현황
${selected_object.display_name} 점검 요약
```

Text Board도 permission-aware하게 렌더링하며 민감 property를 노출하지 않는다.

## 3.5 Board 크기

Palantir는 2개 Board 행에서 2/3-1/3, 3개 행에서 1/2-1/4-1/4 같은 제한된 layout을 제공한다.

Ontology Dashboard 적용:

초기 MVP에서는 완전 자유 좌표보다 제한된 12-column grid를 사용한다.

허용 width:

```text
3 / 4 / 6 / 8 / 9 / 12 columns
```

이유:

- responsive 안정성
- PDF export 예측 가능성
- role template consistency
- 사용자 설정 migration 단순화

## 3.6 Viewer 임시 Override

Palantir viewer의 parameter 변경과 Board selection은 reload 후 유지되지 않고 다른 사용자에게 영향을 주지 않는다.

Ontology Dashboard 적용 차이:

```text
Session override — 기본
Saved View — 명시적 저장
User Default — 로그인 후 자동 복원
Role Template — 관리자·FDE 게시
```

이 부분이 Ontology Dashboard의 핵심 차별점이다.

## 3.7 Chart-to-chart Filtering

Palantir는 상류 Board의 선택이 분석 경로의 하류 Board에 전파되도록 한다.

Ontology Dashboard 적용:

- raw analysis path 대신 explicit dependency graph
- object selection·link traversal·time range event
- affected boards 표시
- cycle validation
- permission-aware target query

## 3.8 Share Link

Palantir는 현재 parameter 값이 포함된 공유 링크를 생성한다.

Ontology Dashboard 적용:

- dashboard ID
- saved view token
- active tab
- parameter values
- selected object
- expiration

공유 링크 자체가 접근 권한을 부여해서는 안 된다.

## 3.9 Fullscreen

Palantir는 Board 단위 전체화면과 Board 간 이동을 지원한다.

Ontology Dashboard 적용:

- Board presentation mode
- 좌우 navigation
- 현재 parameter 유지
- masked property 유지
- role-specific title·description 유지

## 3.10 Export와 Checkpoint

Palantir는 현재 parameter·selection 상태를 반영한 PDF export를 제공하고, 관리자가 export 전에 근거 입력을 요구할 수 있다.

Ontology Dashboard 적용:

- PDF·CSV·JSON export
- export reason
- incident·audit reference
- generated by·generated at
- dashboard template version
- Evidence reference
- export audit event

---

# 4. Board 추가 방식 분석

Palantir Contour toolbar는 Board를 기능별 category로 제공한다.

공식 category:

- Suggested
- Filter
- Visualize
- Join
- Transform
- Edit Columns

검색 mode와 action mode도 제공한다.

공식 문서:

- https://www.palantir.com/docs/kr/foundry/contour/boards-add/

## Ontology Dashboard category 변환

Palantir category는 분석 builder 중심이다. Ontology Dashboard는 분석과 운영을 함께 지원해야 하므로 다음으로 확장한다.

| Palantir | Ontology Dashboard |
|---|---|
| Suggested | Suggested |
| Filter | Filter / Parameter |
| Visualize | Observe / Explore |
| Join | Relate / Linked Objects |
| Transform | Build / Derive |
| Edit Columns | Schema / Property — FDE·DS only |
| 없음 | Explain |
| 없음 | Act |
| 없음 | Audit |

## Board search

검색 index:

- Board 이름
- category
- supported ObjectType
- supported ActionType
- role
- keyword
- description

예:

```text
"설비 추세" → Time Series
"감사" → Lineage, Activity Timeline, Export
"담당자 배정" → Assignment Action Board
"연결된 주문" → Linked Object List
```

## Suggested logic

```text
role
+ active tab
+ selected object type
+ current parameters
+ available actions
+ usage popularity
= suggested boards
```

LLM은 Suggested ranking을 보조할 수 있지만 최종 후보는 Board Registry whitelist에서만 가져온다.

---

# 5. Ontology와 Dashboard 연결

Palantir Ontology는 object type, link type, action type을 실제 조직 데이터와 연결하고, 이를 user-facing analytical·operational tool에 통합한다.

공식 문서:

- https://www.palantir.com/docs/foundry/ontology/overview
- https://www.palantir.com/docs/foundry/ontology/applications/index.html

## Ontology Dashboard binding model

### Object binding

```json
{
  "object_type": "RiskEvent",
  "object_set": {
    "status": ["warning", "critical"],
    "workspace_id": "$workspace"
  }
}
```

### Link binding

```json
{
  "source": "RiskEvent",
  "link_type": "assigned_to",
  "target": "User"
}
```

### Action binding

```json
{
  "action_type": "AssignInspection",
  "object_parameter": "$selected_object",
  "visible_when": "permission.can_apply"
}
```

## 중요한 설계 원칙

- Board가 원시 DB table 이름에 직접 의존하지 않게 한다.
- Board는 ObjectType·Property·LinkType·ActionType ID에 의존한다.
- domain pack이 바뀌어도 Board renderer는 재사용한다.
- object property permission을 query와 UI 모두에서 적용한다.

---

# 6. Permission 벤치마크

Palantir는 ontology resource와 object data permission을 분리하며, Action 실행 권한도 별도로 검사한다.

공식 문서:

- https://www.palantir.com/docs/foundry/object-permissioning/overview
- https://www.palantir.com/docs/foundry/object-permissioning/ontology-permissions
- https://www.palantir.com/docs/foundry/action-types/permissions

## Ontology Dashboard 적용

### Resource permission

- ObjectType schema 조회
- LinkType schema 조회
- ActionType 조회
- BoardDefinition 조회
- DashboardTemplate 편집

### Data permission

- object instance 조회
- property 조회
- link traversal
- export

### Action permission

- Action 보이기
- Action form 열기
- Action 적용
- parameter submission criteria

### UI rule

클라이언트에서 버튼을 숨기는 것은 UX일 뿐 보안이 아니다. 모든 permission은 API에서 다시 검증한다.

---

# 7. FDE 역할 벤치마크

Palantir는 FDE를 고객 현장과 기술 사이에서 문제를 end-to-end로 소유하고, 고객 workflow에 맞는 custom application·LLM workflow·production solution을 구축하는 역할로 설명한다.

참고:

- Palantir Forward Deployed Engineer 채용 설명
- https://jobs.lever.co/palantir/2e6b0ac8-83e9-4be5-a3aa-cf319f751728

## Ontology Dashboard FDE Workspace

FDE는 다음을 하나의 화면에서 연결한다.

```text
Customer objective
→ Workflow
→ Source systems
→ Object types
→ Link types
→ Actions
→ Role templates
→ Board configuration
→ Deployment status
→ Usage feedback
```

## FDE에게 필요한 Board

- customer workflow map
- object·link schema inventory
- data mapping health
- unmapped field queue
- integration latency·error
- role template preview
- action submission failures
- LLM trace·fallback
- feature flags
- deployment checklist
- user feedback queue

## FDE와 데이터 사이언티스트 차이

| 구분 | FDE | 데이터 사이언티스트 |
|---|---|---|
| 기준 | 고객 outcome | 모델·데이터 품질 |
| 주요 대상 | workflow·ontology·application | dataset·model·threshold |
| 화면 | customer workspace | model console |
| 쓰기 | template·mapping draft | model candidate·evaluation |
| 배포 | customer validation·publish request | model release request |

---

# 8. 적극적으로 가져올 패턴

## 그대로 채택할 수준

- 상단 Tab
- Board 단위 구성
- Add to dashboard
- 특정 Tab 또는 새 Tab에 추가
- drag-and-drop 순서
- 제한된 grid size
- Text Board
- inline parameter
- 좌측 parameter panel
- Board 전체화면
- 현재 상태 공유 링크
- cross-filter와 affected board 표시
- view/edit mode 분리
- export checkpoint

## 확장해서 채택

### Viewer override

Palantir:

- session 임시 상태

Ontology Dashboard:

- session override
- Saved View
- User Default
- Role Template

### Board data binding

Palantir Contour:

- analysis dataset·column 중심

Ontology Dashboard:

- ObjectType·LinkType·ActionType 중심
- 필요 시 underlying dataset adapter

### Dashboard editor

Palantir:

- analysis builder와 dashboard editor

Ontology Dashboard:

- Personal editor
- Template editor
- FDE workbench
- Admin governance

---

# 9. 그대로 복제하지 않을 부분

## 9.1 분석 경로에 강하게 결합

우리 제품의 일반 사용자는 분석 path를 이해할 필요가 없다. dependency graph는 내부 구조로 관리하고 UI에는 영향 관계만 설명한다.

## 9.2 모든 사용자를 분석가로 취급

임원·작업자·감사 담당에게 Join·Transform·Edit Columns를 노출하지 않는다.

## 9.3 개인화가 session에만 머무름

우리 핵심 가치는 계정별 layout·tab·filter의 영구 저장이다.

## 9.4 원시 column 중심 설정

Ontology property와 relation을 우선하고, column mapping은 FDE·data scientist 영역으로 제한한다.

## 9.5 대시보드만으로 workflow 종료

우리 Board는 Action을 수행하고 object 상태·관계를 변경할 수 있어야 한다. 단, permission·validation·audit를 거친다.

---

# 10. 권장 Target UI

## View mode

```text
┌────────────────────────────────────────────────────────────────────┐
│ Logo | Workspace | Global Search | Notifications | User           │
├────────────────────────────────────────────────────────────────────┤
│ Overview | Analysis | Tasks | Audit | My View +                    │
├───────────────┬────────────────────────────────────────────────────┤
│ Parameters    │ Board 1              │ Board 2                     │
│ Filters       ├───────────────────────┼─────────────────────────────┤
│ Saved Views   │ Board 3 full width                                  │
│ Object Context├─────────────────────────────────────────────────────┤
│ Related       │ Board 4              │ Board 5                     │
└───────────────┴────────────────────────────────────────────────────┘
```

## Personal edit mode

```text
Top Tabs + Save / Cancel / Restore Role Default
Left: Board Catalog
Center: Grid Canvas
Right: Board Inspector
```

## Template edit mode

```text
Role selector
Template version
Preview as user
Mandatory board policy
Publish / Rollback
```

## Admin app

```text
/admin
Users | Roles | Scopes | Templates | Boards | Ontology | Integrations | Audit
```

---

# 11. 개인 설정 저장 핵심 설계

## 역할 default와 사용자 instance

```text
Executive Template v3
├── Executive A override
│   ├── Risk Trend first
│   ├── 30-day default
│   └── Saved View: Board Meeting
└── Executive B override
    ├── Business Impact first
    └── 7-day default
```

## 로그인 복원 순서

1. session 확인
2. user role·scope 확인
3. 마지막 workspace 조회
4. published role template 조회
5. user override merge
6. user default parameters 적용
7. last active tab 적용
8. mandatory policy 검증
9. resolved dashboard 반환

## 저장 API

```text
PUT /api/dashboards/{id}/preferences
POST /api/dashboards/{id}/saved-views
POST /api/dashboards/{id}/restore-default
```

## 동시성

- preference version
- optimistic concurrency
- `updated_at`
- 다른 기기 충돌 시 최신 변경 확인

---

# 12. 사용자 경험 시나리오

## 임원

1. 로그인
2. Executive Overview 자동 표시
3. 기본 30일 추세 복원
4. `한국 공장` parameter 선택
5. 특정 위험 막대 선택
6. 영향받는 3개 Board 갱신
7. Board Meeting Saved View 저장
8. 다음 로그인 시 동일 view 복원

## 품질·감사

1. 로그인
2. Audit Queue tab 표시
3. 사건 선택
4. timeline·Evidence·Action history cross-filter
5. export reason 입력
6. PDF 생성
7. export audit 기록

## FDE

1. 고객 workspace 선택
2. Ontology tab에서 object mapping 확인
3. Templates tab에서 `process_manager` preview
4. Board catalog에서 Linked Object Board 추가
5. role preview
6. draft 저장
7. 관리자에게 publish request

## 데이터 사이언티스트

1. Model Health tab
2. model version parameter 변경
3. false negative slice 선택
4. downstream error table·feature distribution 갱신
5. Saved View 생성
6. release candidate Action 요청

---

# 13. 공식 출처

## Contour Dashboard

- 대시보드 생성·탭·순서·텍스트·크기·viewer override·cross-filter·share·fullscreen·export
  - https://www.palantir.com/docs/kr/foundry/contour/dashboards-getting-started

## Contour Boards

- Board toolbar·category·검색·삽입
  - https://www.palantir.com/docs/kr/foundry/contour/boards-add/

## Ontology

- Object·Link·Action과 user-facing application 통합
  - https://www.palantir.com/docs/foundry/ontology/overview
  - https://www.palantir.com/docs/foundry/ontology/applications/index.html

## Permission

- ontology resource와 object data permission
  - https://www.palantir.com/docs/foundry/object-permissioning/overview
  - https://www.palantir.com/docs/foundry/object-permissioning/ontology-permissions

## Action

- object·property·link를 일관된 workflow로 변경
  - https://www.palantir.com/docs/foundry/action-types/overview
  - https://www.palantir.com/docs/foundry/action-types/permissions

## FDE

- 고객 문제·기술·application delivery를 end-to-end로 연결하는 역할
  - https://jobs.lever.co/palantir/2e6b0ac8-83e9-4be5-a3aa-cf319f751728

---

# 14. 최종 벤치마크 원칙

```text
Palantir의 Board·Tab·Parameter·Action 개념은 적극적으로 채택한다.
Palantir 화면을 픽셀 단위로 복제하지 않는다.
Ontology Dashboard의 차별점은 역할 기본값과 사용자 영구 개인화의 결합이다.
```

최종 목표:

```text
각 사용자는 같은 조직 Ontology를 보지만,
자신의 역할에 맞는 default dashboard로 시작하고,
허용된 범위에서 자신만의 tab·board·filter를 저장하며,
모든 질문·분석·행동은 동일한 object·link·action·evidence에 연결된다.
```
