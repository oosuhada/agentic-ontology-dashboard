# Week 2 MVP 프론트엔드 통합·재구성 실행 계획

- 문서 상태: `execution plan`
- 기준일: `2026-08-06`
- 담당: `우수 · 팀원1`
- 기준 데이터: `UCI AI4I 2020 Manufacturing Predictive Maintenance — Physics & Maintenance Canonical V3.1`
- 연관 문서:
  - [MVP 범위 및 4개 화면 명세서](./mvp-scope-and-screen-specification.md)
  - [MVP API 명세서](./mvp-api-specification.md)
  - [MVP 데이터 계약서](./mvp-data-contract.md)
  - [Week 2 역할 분담 및 산출물 정의](./week2-team-role-and-deliverables.md)
  - [다음 구현 세션 명령 프롬프트](../../60-development-prompts/next-session-week2-mvp-frontend-convergence-prompt.md)

## 1. 계획 목적

지금까지 V1·V2·V3·V4는 제품 방향을 탐색하기 위한 브레인스토밍 성격으로 확장되었다. 각 버전에는 유효한 아이디어가 있지만, 현재 멘토링에서 확정된 MVP 범위보다 기능과 역할이 넓고 화면 간 목적도 서로 다르다.

이번 작업의 목적은 새로운 버전을 다시 확장하는 것이 아니다. 기존 버전에서 검증된 화면과 상호작용을 선별해 다음 네 화면으로 구성된 하나의 MVP 흐름으로 재구성하는 것이다.

```text
Overview
→ Objects
→ Operations
→ Executive Report View
```

핵심 사용자도 다음 두 그룹으로 제한한다.

- 생산 관리자
- 현장 담당자

`Analysis`, 시스템 관리자, MLOps, 배포 운영, 거버넌스, 자동화 플랫폼 전체 기능은 이번 MVP 완료 조건에 포함하지 않는다.

## 2. 구현 원칙

### 2.1 기존 V1·V2·V3·V4 보존

아래 기존 경로는 비교·회귀 검증용으로 유지한다.

| 버전 | 현재 경로 | 이번 작업 원칙 |
|---|---|---|
| V1 · 기존 Dashboard | `/app/projects/:projectId` | 임원 보고서 레이아웃을 참고하되 기존 화면은 수정하지 않음 |
| V2 · Blueprint 1차 | `/app/projects/:projectId/blueprint` | MVP 정보구조의 기준으로 사용 |
| V3 · Blueprint 2차 | `/app/projects/:projectId/blueprint-v2` | Object Table·Inspector·Operations 밀도 개선 요소를 선별 |
| V4 · Commercial | `/app/projects/:projectId/blueprint-v4` | Shell·Context·오류 격리 등 제품 안정성 요소만 선별 |

기존 경로를 최종 MVP로 덮어쓰거나 Redirect하지 않는다. 기존 버전의 시각 회귀 테스트도 유지한다.

### 2.2 독립 MVP 경로

최종 조합 화면은 별도의 경로에 구현한다.

```text
/app/projects/:projectId/mvp
```

권장 직접 진입 Query:

```text
/mvp?view=overview
/mvp?view=objects&asset_id=CNC-S01-L02-03
/mvp?view=operations&event_id=EVENT-001
/mvp?view=executive-report
```

새 경로를 사용하는 이유:

- V1~V4의 비교 가능성을 보존한다.
- 멘토 피드백 기준 MVP를 명확히 구분한다.
- 기존 실험 기능이 발표 동선에 섞이지 않는다.
- 문제가 생겨도 기존 버전으로 즉시 돌아갈 수 있다.

### 2.3 V4 채택 기준

V4가 최신 버전이라는 이유만으로 가져오지 않는다. 아래 조건 중 하나 이상을 충족할 때만 MVP에 반영한다.

1. 사용자가 핵심 정보를 더 빨리 찾을 수 있다.
2. 클릭 수 또는 화면 이동 수가 줄어든다.
3. Project·Dataset·Role 문맥이 더 명확해진다.
4. 부분 API 실패가 전체 흰 화면으로 이어지는 것을 방지한다.
5. 모바일 또는 작은 발표 화면에서 더 안정적으로 동작한다.
6. 기존 V2 구현보다 유지보수와 테스트가 단순해진다.

채택할 때에는 소스 버전과 이유를 코드 주석 또는 본 문서의 결정표에 남긴다.

## 3. 버전별 재사용 판단

### 3.1 V1에서 가져올 요소

#### 필수 후보

- Executive Report의 보고서형 정보 구조
- 임원 의사결정 요약
- 위험 현황과 생산 영향 서술
- 대응 조치와 처리 상태
- A4·인쇄·PDF에 적합한 레이아웃
- Narrative를 중심으로 읽는 흐름

#### 가져오지 않을 요소

- 보고서 중심으로 모든 업무 화면을 구성하는 방식
- 설비 탐색과 Action이 보고서 안에 과도하게 숨겨지는 구조
- 현재 MVP와 관계없는 기존 Dashboard 메뉴 전체

### 3.2 V2에서 가져올 요소

V2는 최종 MVP의 기본 정보구조다.

#### 필수 채택

- Overview·Objects·Operations 3개 메뉴
- 역할별 첫 질문과 정보 우선순위
- Overview KPI와 위험 Event 목록
- Objects의 Object Set·필터·Inspector 흐름
- Operations의 Inbox·상세 판단·Activity 구조
- Blueprint 기반 상태 Tag·Button·Callout 사용

#### 제거 또는 비활성화

- Analysis 메뉴
- Graph·Canvas 진입 버튼
- MVP 사용자와 관계없는 역할 전환
- 구현되지 않은 확장 기능을 실제 기능처럼 보이게 하는 버튼

### 3.3 V3에서 가져올 요소

V3는 V2보다 도구형 UI가 정교하므로 화면별로 필요한 부분만 사용한다.

#### Objects 후보

- 고밀도 Object Table
- 가상화된 긴 목록
- 고정 Inspector
- Properties·Actions·History 중 MVP에 필요한 Tab
- 선택 행과 Inspector의 명확한 연결
- Table Header·정렬·Filter 배치

#### Operations 후보

- Dense Queue
- 선택 Event 상세
- Action 중심 Inspector
- 상태와 우선순위의 한눈에 보이는 표현

#### 제한

- V3 전체 Shell을 그대로 사용하지 않는다.
- Analysis Tab은 가져오지 않는다.
- 신규 사용자가 이해하기 어려운 약어·아이콘만 있는 UI는 그대로 복사하지 않는다.
- 정보 밀도가 높아져 핵심 조치가 묻히면 V2 구성을 유지한다.

### 3.4 V4에서 가져올 요소

V4는 상용화 Control Plane 성격이 강하므로 기능 Surface가 아니라 제품 안정성 패턴을 선별한다.

#### 채택 후보

1. **Application Shell 구조**
   - 명확한 Header·Navigation·Main·Inspector 영역
   - Project 문맥을 잃지 않는 구조

2. **Project·Dataset·Role Context Line**
   - 현재 Project
   - Workspace
   - Canonical V3.1 Dataset Version
   - 현재 사용자 역할

3. **Compact Navigation**
   - 데스크톱에서 접기 가능
   - 모바일에서는 가로 Navigation으로 전환

4. **Panel 단위 실패 격리**
   - 한 API가 실패해도 다른 KPI·목록·Inspector를 유지
   - 실패한 Panel에만 오류와 재시도 표시

5. **Deep Link와 Version-scoped State 원칙**
   - 선택 화면·설비·Event가 URL에 유지됨
   - 다른 버전의 Local Storage와 충돌하지 않음

6. **명확한 Loading·Blocked·Not configured 상태**
   - 무한 Loader 대신 현재 상태와 재시도 가능 여부 표시

7. **Responsive Navigation Pattern**
   - 1366×768 발표 화면과 모바일에서 Navigation이 콘텐츠를 덮지 않음

#### 가져오지 않을 요소

- Identity & Access Surface
- Deployment Surface
- Distributed Runtime
- Artifact Governance
- SLO·Observability 운영 화면
- Connector·Ingestion 운영 화면
- MLOps·Model Operations
- Branching·Lineage Control Plane
- Automation·Application Settings 전체 Surface

이 기능들은 제품 확장 백로그로 보존하되 MVP Navigation에는 노출하지 않는다.

## 4. 최종 MVP 화면 조합

### 4.1 공통 MVP Shell

권장 조합:

```text
V2의 단순한 3개 업무 메뉴
+ V4의 Project·Dataset·Role Context
+ V4의 Compact·Responsive Navigation
+ V4의 Panel 단위 오류 격리
```

공통 상단 정보:

- 제품명: `Ontology Dashboard · Predictive Maintenance MVP`
- Project 이름
- Dataset Version: Canonical V3.1
- 기준 시각 또는 마지막 갱신 시각
- 현재 역할
- 데이터 상태

공통 Navigation:

1. Overview
2. Objects
3. Operations
4. Executive Report

`Analysis`는 숨긴다. URL로 직접 접근하더라도 MVP 경로에서는 지원하지 않는 화면이라는 안내를 표시하거나 Overview로 이동한다.

### 4.2 화면 1 · Overview

#### 기준

- 기본: V2 Overview
- 보강: V4 Context·Panel State
- 필요 시: V3의 고밀도 Table 표현 일부

#### 필수 구성

- Critical·Warning 수
- 평균 위험도
- 예상 Downtime 영향
- 라인별 위험 현황
- 고위험 설비 Top N
- 판단 대기 Event 목록
- 마지막 갱신 시각
- Dataset Version

#### 주요 Action

- 설비를 Objects에서 열기
- Event를 Operations에서 열기
- Executive Report 열기
- 데이터 새로고침

#### 제외

- Analysis 열기
- 모델 재학습
- 관리자 설정
- 자동 정지

### 4.3 화면 2 · Objects

#### 기준

- 정보구조: V2 Objects
- Table·Inspector: V3 장점 선별
- 상태·문맥: V4 패턴 선별

#### 목록 필드

- 설비 ID·설비명
- 설비 유형
- 라인·셀
- 상태 등급
- 고장 확률
- 신뢰도
- 설비 중요도
- 담당자

#### MVP Filter

- 검색
- 라인
- 위험 상태
- 담당자

복잡한 Object Set 합집합·교집합·고급 Query Builder는 제외한다.

#### Inspector

- 설비 기본 속성
- 핵심 센서값
- Top factors
- 예상 고장 유형
- 권장 조치
- Dataset·Model provenance
- Operations 열기

### 4.4 화면 3 · Operations

#### 기준

- Workflow 구조: V2 Operations
- Queue·Action Inspector: V3 장점 선별
- 상태 격리와 오류 처리: V4 패턴

#### 지원 결정

- `continue_monitoring`
- `request_inspection`
- `review_shutdown`
- `hold_for_data_check`

`review_shutdown`은 실제 설비 정지 명령이 아니라 사람의 검토 요청이다.

#### 필수 구성

- Event Queue
- 설비·위험·신뢰도
- 예상 고장 유형
- 권장 결정과 근거
- 담당자
- 처리 상태
- Activity·Audit
- Executive Report 반영 상태

#### API 미완성 시 처리

- 읽기 API는 실제 데이터를 우선 사용한다.
- 쓰기 API가 준비되지 않았으면 버튼을 숨기거나 `Demo only`로 표시한다.
- Local-only Action을 실제 저장된 Action처럼 표현하지 않는다.

### 4.5 화면 4 · Executive Report View

#### 기준

- 기본 레이아웃: V1 임원 보고서
- 입력: 동일 Result Artifact·Operations 상태
- 보강: V4 Context와 Provenance 표현

#### 필수 섹션

1. 보고서 제목·발행일·Revision
2. 임원 의사결정 요약
3. Critical·Warning 현황
4. 주요 위험 설비·라인
5. 예상 생산 영향과 Downtime
6. 진행·완료된 대응 조치
7. 미결정 사항
8. 데이터 품질과 불확실성
9. Dataset·Model·Report provenance

#### 출력

- 화면 보기
- A4 인쇄 CSS
- PDF 저장이 가능한 브라우저 인쇄

호범의 LLM 리포트 API가 준비되기 전에는 검증된 고정 템플릿으로 표시한다. LLM 응답이 실패하거나 검증을 통과하지 못해도 템플릿 Fallback으로 보고서가 유지돼야 한다.

## 5. 화면 간 상태 연결

공통 선택 문맥을 별도 상태 계약으로 둔다.

```ts
interface MvpSelectionContext {
  projectId: string;
  workspaceId: string;
  assetId: string | null;
  eventId: string | null;
  view: "overview" | "objects" | "operations" | "executive-report";
  role: "process_manager" | "field_operator";
}
```

우선순위:

1. URL Query
2. 현재 Session State
3. 화면 기본 선택값

규칙:

- Overview에서 선택한 설비가 Objects에서 유지된다.
- Overview 또는 Objects에서 선택한 Event가 Operations에서 유지된다.
- Operations 상태가 Executive Report에 반영된다.
- 새로고침 후에도 URL Query로 같은 화면을 재현할 수 있다.
- 잘못된 Asset·Event ID는 안전한 Empty State로 처리한다.

## 6. 데이터·API 연결 원칙

프론트엔드는 Canonical CSV·JSONL 파일을 직접 해석하지 않는다. 성민이 제공하는 API 또는 현재 프로젝트의 정규화된 API Adapter만 사용한다.

```text
Canonical V3.1
→ Prediction Result Artifact
→ MVP API
→ Frontend View Model
→ Four MVP Screens
```

### 6.1 Adapter 경계

권장 파일:

```text
web/src/features/mvp/
├── api/
│   ├── mvpApi.ts
│   ├── mvpAdapters.ts
│   └── mvpContracts.ts
```

화면 Component가 API 원본 구조를 직접 해석하지 않도록 한다.

### 6.2 API 준비 전 Mock

- 실제 API와 같은 Type을 사용한다.
- Mock 여부를 화면 상단에 명확히 표시한다.
- 임의의 새로운 설비·수치보다 Repository에 있는 Canonical V3.1 Sample을 사용한다.
- 실제 API가 준비되면 Adapter만 교체해 화면 코드 변경을 최소화한다.

### 6.3 오류 격리

각 화면은 최소 다음 상태를 지원한다.

- Loading
- Partial loading
- Empty
- Error
- Low confidence
- Data quality hold
- Stale data

KPI API가 실패해도 Object 목록이 로드되면 해당 영역은 표시한다. 반대로 목록이 실패해도 보고서나 기존 선택 Event가 있으면 전체 페이지를 숨기지 않는다.

## 7. 권장 디렉터리 구조

```text
web/src/features/mvp/
├── MvpApplication.tsx
├── MvpRouteBoundary.tsx
├── mvp.css
├── api/
│   ├── mvpApi.ts
│   ├── mvpAdapters.ts
│   └── mvpContracts.ts
├── context/
│   └── MvpSelectionContext.tsx
├── shell/
│   ├── MvpShell.tsx
│   ├── MvpHeader.tsx
│   └── MvpNavigation.tsx
├── overview/
│   └── MvpOverviewPage.tsx
├── objects/
│   └── MvpObjectsPage.tsx
├── operations/
│   └── MvpOperationsPage.tsx
├── report/
│   └── MvpExecutiveReportPage.tsx
└── components/
    ├── MvpPanelBoundary.tsx
    ├── MvpStateGrade.tsx
    ├── MvpProvenance.tsx
    └── MvpWorkbenchState.tsx
```

기존 V2·V3·V4 Component를 직접 Import하면 버전 간 결합이 커질 수 있다. 재사용 가치가 명확한 작은 Component는 공통 영역으로 추출하되, 기존 화면의 동작과 시각 회귀가 유지되는지 확인한다.

## 8. 구현 단계

### Phase 0 · 기준선 확인

- 원격 브랜치 최신화
- 기존 미커밋 변경 보존
- 별도 worktree 생성
- V1~V4 실제 화면 직접 확인
- 관련 MVP 문서 읽기
- 현재 API와 화면 Type 비교
- V4에서 가져올 요소를 스크린샷과 코드 기준으로 기록

완료 조건:

- 채택·제외 Matrix가 작성됨
- 기존 V1~V4 변경 금지 범위가 확인됨

### Phase 1 · 독립 MVP Route와 Shell

- `mvpProjectPath()`와 Route Matcher 추가
- `/app/projects/:projectId/mvp` Lazy Route 추가
- MVP 전용 Shell 구현
- Overview·Objects·Operations·Executive Report Navigation 추가
- Analysis 미노출
- Project·Dataset·Role Context 표시

완료 조건:

- 기존 네 버전과 별도로 MVP Route가 열림
- 직접 진입과 새로고침이 동작함
- 1366×768에서 Navigation과 핵심 영역이 보임

### Phase 2 · 공통 선택 문맥

- `asset_id`, `event_id`, `view` Query 지원
- 화면 전환 시 선택 상태 유지
- 잘못된 Query 안전 처리
- Version-scoped Local Storage가 필요하면 MVP Namespace 사용

완료 조건:

- Overview → Objects → Operations → Report 흐름에서 같은 설비·Event 유지

### Phase 3 · Overview 재구성

- V2 Overview 기반으로 필수 KPI와 Event 목록만 유지
- Analysis 진입 제거
- V4 Panel State와 Context 적용
- 고위험 설비·Event Deep Link 연결

완료 조건:

- 생산 관리자가 30초 안에 우선 설비를 찾을 수 있음
- Partial API Failure가 전체 화면 실패로 이어지지 않음

### Phase 4 · Objects 재구성

- V2 정보구조 유지
- V3 Table·Inspector의 유효한 패턴 선별
- 필수 Filter 4개만 제공
- Operations 연결
- Provenance 표시

완료 조건:

- 설비 검색·선택·상세 확인이 한 화면에서 가능
- 선택 설비가 URL과 Operations에 유지

### Phase 5 · Operations 재구성

- V2 Workflow를 기본으로 사용
- V3 Queue·Action 표현 선별
- 읽기·쓰기 기능 상태 명확화
- Activity·Audit 표시
- Report 반영 연결

완료 조건:

- Event 선택 → 근거 확인 → 조치 검토 → 보고서 확인 흐름 동작

### Phase 6 · Executive Report 통합

- V1 보고서 View를 MVP Component로 재구성
- 동일 API View Model 사용
- Operations 상태 반영
- LLM API Adapter와 Template Fallback 구현
- A4 Print CSS 구현

완료 조건:

- 보고서 숫자가 Overview·Operations와 일치
- LLM 실패 시에도 보고서가 표시됨
- 인쇄 미리보기에서 레이아웃이 깨지지 않음

### Phase 7 · UX·반응형·접근성 마감

- Desktop 1440×900
- 발표 화면 1366×768
- Tablet 1024×768
- Mobile 390×844
- 색상 + 텍스트 + 아이콘 상태 표현
- Keyboard Navigation
- Focus State
- 긴 설비 ID·Dataset Version 줄바꿈
- Loading·Empty·Error·Low confidence·Data quality hold

### Phase 8 · 검증·문서·배포

- Unit Test
- API Adapter Test
- Playwright E2E
- Visual Regression
- Production Build
- 초기 Bundle Budget
- 기존 V1~V4 Smoke Test
- 공개 주소 검증
- 화면 캡처 4종
- 기능 설명과 사용자 흐름 문서 갱신
- Commit·Push·서버 재시작

## 9. 테스트 시나리오

### 시나리오 A · 생산 관리자 기본 흐름

1. MVP Overview를 연다.
2. Critical 설비와 예상 Downtime을 확인한다.
3. 설비를 Objects에서 연다.
4. Top factor와 권장 조치를 확인한다.
5. Operations에서 `request_inspection` 또는 `review_shutdown` 상태를 확인한다.
6. Executive Report에서 동일 설비와 대응 상태를 확인한다.

### 시나리오 B · 현장 담당자 흐름

1. Operations에서 담당 Event를 선택한다.
2. Objects에서 설비 상세와 핵심 센서를 확인한다.
3. 점검 요청·메모·처리 상태를 확인한다.
4. 생산 관리자 Report에 결과가 반영되는지 확인한다.

### 시나리오 C · 데이터 품질 보류

1. `data_quality_hold` Event를 연다.
2. Overview와 Objects가 고장 확정 표현을 사용하지 않는지 확인한다.
3. Operations가 `hold_for_data_check`를 표시하는지 확인한다.
4. Report가 불확실성과 확인 중 상태를 표시하는지 확인한다.

### 시나리오 D · 부분 API 실패

1. KPI 요청만 실패시킨다.
2. Object 목록과 Navigation이 유지되는지 확인한다.
3. 실패 Panel에 재시도 버튼이 표시되는지 확인한다.
4. 전체 페이지가 흰 화면이 되지 않는지 확인한다.

### 시나리오 E · 직접 링크

1. `?view=objects&asset_id=...` 주소를 새 브라우저에서 연다.
2. 해당 설비가 선택된 상태로 열리는지 확인한다.
3. 새로고침 후에도 선택 상태가 유지되는지 확인한다.

## 10. MVP 완료 기준

아래 조건을 모두 충족해야 완료로 판단한다.

1. `/app/projects/:projectId/mvp` 독립 경로가 존재한다.
2. 기존 V1·V2·V3·V4 경로가 그대로 동작한다.
3. Overview·Objects·Operations·Executive Report 네 화면만 MVP Navigation에 보인다.
4. Analysis 없이 기본 사용자 흐름이 완결된다.
5. Canonical V3.1이 모든 화면의 동일 기준 데이터다.
6. 선택 Asset·Event 문맥이 화면 간 유지된다.
7. 보고서 숫자와 Operations 상태가 다른 화면과 일치한다.
8. LLM API 실패 시 Template Fallback이 동작한다.
9. Loading·Empty·Error·Low confidence·Data quality hold를 구분한다.
10. 한 API 실패가 전체 흰 화면으로 이어지지 않는다.
11. 1366×768 발표 화면에서 핵심 정보가 첫 화면에 보인다.
12. 모바일 문서 가로 Overflow가 없다.
13. 임원 보고서를 브라우저에서 A4 PDF로 저장할 수 있다.
14. 기존 버전 Smoke Test와 MVP E2E가 통과한다.
15. Git Commit·Push·공개 서버 반영과 실제 URL 검증이 완료된다.

## 11. 명시적 제외 범위

- Analysis Workbench
- 시스템 관리자 전체 화면
- Model Training·MLOps Console
- Commercial V4의 배포·Runtime·Artifact·Connector·SLO Surface
- 자동 설비 정지
- 완전 자율형 Agent
- 신규 데이터셋 생성
- 모델 성능 개선 자체
- 모든 역할별 Dashboard
- 복잡한 Object Set Builder
- 실시간 Push Notification Infrastructure

## 12. 협업 경계

### 우수가 직접 담당

- MVP Route·Shell
- 네 화면 조합과 재구성
- Frontend View Model·Adapter
- API 연결
- 화면 간 Context
- UX·반응형·접근성
- E2E·화면 공유

### 광우에게 받는 것

- 요구사항·기능·Schema·API·MVP 설계 명세
- 화면 필드 이름과 Enum
- 리포트 구조와 금지 표현
- 완료 기준과 Traceability

### 성민에게 받는 것

- Prediction 목록·상세 API
- Result Artifact Sample
- Filter·정렬 계약
- Dataset·Model Version
- 오류 응답과 OpenAPI

### 호범에게 받는 것

- 리포트 생성 API
- 입력·출력 Schema
- Prompt Version
- 성공·실패 응답
- Template Fallback 조건

타 담당자의 API가 준비되지 않았다는 이유로 화면 구조를 임의 데이터 계약에 고정하지 않는다. Adapter와 Mock을 사용하되 실제 계약으로 교체 가능한 형태를 유지한다.

## 13. Git·작업 환경 원칙

- 새로운 세션에서는 반드시 최신 원격 브랜치에서 별도 worktree를 만든다.
- 기존 Checkout의 미커밋 변경을 삭제·덮어쓰기·Stash하지 않는다.
- 작업 시작과 각 Commit 전 원격 브랜치 변경을 확인한다.
- 다른 세션이 같은 파일을 변경하면 최신 원격 위로 Rebase하고 양쪽 변경을 보존한다.
- Phase 단위로 작고 설명 가능한 Commit을 만든다.
- V1~V4 파일을 수정해야 할 경우 이유와 회귀 검증 결과를 기록한다.
- 최종 Push 후 실제 공개 서비스 Checkout과 서버를 최신 Commit으로 맞춘다.

## 14. 권장 Commit 구분

```text
feat: add mentoring-aligned mvp application route
feat: connect mvp selection context and deep links
feat: compose mvp overview and object workflow
feat: compose mvp operations and executive report
fix: isolate mvp panel failures and responsive states
test: cover mvp four-screen workflow
docs: publish mvp screen guide and verification result
```

Commit 수는 실제 변경 범위에 따라 조정하되, 한 Commit에 계획·구현·배포 변경을 모두 섞지 않는다.

## 15. 다음 세션 최종 보고 형식

작업 완료 후 다음을 보고한다.

1. 사용한 기준 Commit과 Worktree
2. V1~V4에서 채택한 요소와 제외한 요소
3. 새 MVP 경로
4. 구현한 네 화면
5. API 연결 상태와 Mock·Fallback 여부
6. 주요 변경 파일
7. Unit·E2E·Build·Visual Test 결과
8. 기존 V1~V4 회귀 확인 결과
9. Commit과 Push 결과
10. 공개 URL과 실제 브라우저 검증 결과
11. 남은 Blocker와 다음 우선순위

