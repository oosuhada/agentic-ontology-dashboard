# 다음 세션 명령 프롬프트 · Week 2 MVP 프론트엔드 통합·재구성

아래 내용을 새 ChatGPT 개발 세션에 그대로 붙여넣는다.

---

@devspace-codex

다음 로컬 프로젝트를 **기존 Checkout과 분리된 새 worktree 모드**로 열어줘.

```text
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2
```

기준 브랜치:

```text
feature/predictive-maintenance-adaptive-modeling
```

이번 작업은 분석이나 계획 작성으로 끝내지 말고, 멘토링에서 확정된 Week 2 MVP 프론트엔드를 실제로 구현하고 검증한 뒤 Commit·Push·공개 서버 반영까지 완료하는 작업이다.

## 1. 가장 먼저 지켜야 할 작업 격리 원칙

1. 실제 프로젝트 Checkout의 `git status`를 먼저 확인한다.
2. 기존 미커밋 변경은 다른 세션 작업일 수 있으므로 절대 삭제·덮어쓰기·Stash·Reset하지 않는다.
3. 최신 원격 `origin/feature/predictive-maintenance-adaptive-modeling` 기준 새 worktree를 사용한다.
4. 작업 시작 시 Local 기준 Commit과 Remote 기준 Commit을 기록한다.
5. 작업 중 원격 브랜치가 이동하면 변경 파일을 비교하고 최신 원격 위로 Rebase한다.
6. 충돌이 발생하면 다른 세션 변경과 이번 변경을 모두 보존한다.

## 2. 필수로 읽을 문서

다음 문서를 순서대로 처음부터 끝까지 읽어줘.

```text
docs/10-product/mentoring-mvp-2026-08/README.md
docs/10-product/mentoring-mvp-2026-08/mvp-scope-and-screen-specification.md
docs/10-product/mentoring-mvp-2026-08/mvp-api-specification.md
docs/10-product/mentoring-mvp-2026-08/mvp-data-contract.md
docs/10-product/mentoring-mvp-2026-08/week2-team-role-and-deliverables.md
docs/10-product/mentoring-mvp-2026-08/week2-mvp-frontend-convergence-plan.md
```

필요한 경우 다음 구현도 확인한다.

```text
web/src/App.tsx
web/src/routing.ts
web/src/features/manufacturing/
web/src/features/blueprint/
web/src/features/blueprint-v2/
web/src/features/commercial-v4/
web/src/features/blueprint-compare/
web/src/platform/application/applicationRegistry.ts
web/e2e/
```

## 3. 이번 작업의 제품 목표

지금까지 만든 V1·V2·V3·V4는 브레인스토밍과 확장 실험 결과다. 이번에는 새로운 버전을 더 확장하지 말고, 멘토링에서 확정된 범위에 맞춰 유효한 부분을 하나의 MVP로 조합·재구성한다.

최종 사용자 흐름:

```text
Overview
→ Objects
→ Operations
→ Executive Report View
```

핵심 사용자:

- 생산 관리자
- 현장 담당자

MVP에서 제외:

- Analysis
- 시스템 관리자 화면
- 모델 재학습·MLOps
- 자동 설비 정지
- V4 Control Plane 전체
- 완전 자율형 LLM Agent

## 4. 기존 버전 보존 규칙

아래 기존 경로는 수정하거나 덮어쓰지 말고 비교·회귀 화면으로 보존한다.

```text
V1  /app/projects/:projectId
V2  /app/projects/:projectId/blueprint
V3  /app/projects/:projectId/blueprint-v2
V4  /app/projects/:projectId/blueprint-v4
```

기존 경로를 새 MVP로 Redirect하지 않는다.

최종 MVP는 아래 독립 경로에 구현한다.

```text
/app/projects/:projectId/mvp
```

권장 Query:

```text
?view=overview
?view=objects&asset_id=...
?view=operations&event_id=...
?view=executive-report
```

## 5. 버전별 채택 기준

### V1

가져올 것:

- Executive Report 정보 구조
- 임원 의사결정 요약
- 위험·생산 영향·대응 상태 Narrative
- A4 Print Layout

가져오지 않을 것:

- 보고서 중심 전체 Navigation
- 기존 Dashboard 전체 메뉴

### V2

기본 정보구조로 사용:

- Overview
- Objects
- Operations
- 역할별 첫 질문
- KPI·Object Set·Inbox·Activity

제거:

- Analysis 메뉴와 진입 버튼
- MVP와 관계없는 역할·기능

### V3

선별 후보:

- Dense Object Table
- Virtualized List
- Fixed Inspector
- Operations Queue와 Action Inspector

단, 신규 사용자가 이해하기 어렵거나 정보가 과도하면 V2 구성을 유지한다.

### V4

V4 전체 기능을 가져오지 말고 다음 제품 안정성 패턴만 검토한다.

- Project·Dataset·Role Context Line
- Compact·Responsive Navigation
- Panel 단위 오류 격리
- Deep Link와 Version-scoped State
- 명확한 Loading·Blocked·Not configured 상태
- 긴 텍스트 처리와 모바일 Navigation

다음 V4 Surface는 MVP에 포함하지 않는다.

- Identity
- Deployment
- Runtime
- Artifacts
- SLO·Observability
- Ingestion
- Models
- Lineage·Governance Control Plane
- Automation
- Settings

V4 요소는 최신이라는 이유가 아니라 사용자 흐름 단축, 가독성, 실패 격리 또는 반응형 개선 효과가 있을 때만 가져온다.

## 6. 구현할 MVP 화면

### 6.1 공통 Shell

- 제품명과 Project 표시
- Canonical V3.1 Dataset Version 표시
- 현재 역할 표시
- 마지막 갱신 시각과 데이터 상태
- Overview·Objects·Operations·Executive Report Navigation
- Analysis 미노출
- Desktop·1366×768·Tablet·Mobile 대응

### 6.2 Overview

필수:

- Critical·Warning 수
- 평균 위험도
- 예상 Downtime
- 라인별 위험
- 고위험 설비 Top N
- 판단 대기 Event
- Dataset Version과 갱신 시각

Action:

- Objects 열기
- Operations 열기
- Executive Report 열기
- 새로고침

### 6.3 Objects

필수 목록:

- 설비 ID·설비명
- 설비 유형
- 라인·셀
- 상태
- 고장 확률
- 신뢰도
- 중요도
- 담당자

필수 Filter:

- 검색
- 라인
- 상태
- 담당자

Inspector:

- 기본 속성
- 핵심 센서
- Top factors
- 예상 고장 유형
- 권장 조치
- Dataset·Model provenance
- Operations 이동

### 6.4 Operations

필수:

- Event Queue
- 위험·신뢰도·고장 유형
- 권장 결정과 근거
- 담당자
- 처리 상태
- Activity·Audit
- Report 반영 상태

지원 결정:

```text
continue_monitoring
request_inspection
review_shutdown
hold_for_data_check
```

`review_shutdown`은 실제 정지 명령이 아니라 검토 요청이다.

쓰기 API가 없으면 실제 저장되는 것처럼 위장하지 말고 읽기 전용 또는 Demo-only 상태로 표시한다.

### 6.5 Executive Report

- V1 보고서형 레이아웃 참고
- Overview·Operations와 동일한 데이터 사용
- 임원 요약
- Critical·Warning 현황
- 주요 설비·라인
- 생산 영향·Downtime
- 대응 상태
- 미결정 사항
- 불확실성·데이터 품질
- Dataset·Model·Prompt provenance
- A4 Print CSS

호범의 LLM API가 준비되지 않았거나 실패하면 검증된 템플릿 Fallback을 사용한다.

## 7. 화면 간 상태 계약

다음 선택 문맥을 유지한다.

```text
projectId
workspaceId
assetId
eventId
view
role
```

우선순위:

1. URL Query
2. Session State
3. 기본 선택값

Overview에서 선택한 설비·Event가 Objects·Operations·Report에서 유지돼야 한다. 새로고침과 Deep Link로도 같은 상태를 재현해야 한다.

## 8. 데이터·API 원칙

Frontend에서 Canonical 파일을 직접 읽지 않는다.

```text
Canonical V3.1
→ Result Artifact
→ API
→ Frontend Adapter/View Model
→ MVP Screens
```

권장 경계:

```text
web/src/features/mvp/api/mvpContracts.ts
web/src/features/mvp/api/mvpApi.ts
web/src/features/mvp/api/mvpAdapters.ts
```

현재 API와 멘토링 API 명세가 다르면:

1. 현재 동작하는 API를 조사한다.
2. Adapter에서 MVP View Model로 변환한다.
3. 계약 Gap을 문서에 기록한다.
4. Backend가 준비되면 Adapter만 교체할 수 있게 한다.

Mock이 필요하면 Repository의 Canonical V3.1 Sample만 사용하고 화면에 Mock 상태를 표시한다.

## 9. 상태와 실패 처리

모든 화면에서 다음 상태를 구현한다.

- Loading
- Partial loading
- Empty
- Error + Retry
- Low confidence
- Data quality hold
- Stale data

한 Panel API 실패가 전체 흰 화면으로 이어지지 않게 한다. V4의 오류 격리 패턴을 참고하되 V4 전체 App을 의존하지 않는다.

## 10. 권장 구현 순서

다음 순서로 멈추지 않고 진행한다.

### Phase 0

- V1~V4 직접 실행·시각 확인
- 코드와 API 확인
- 채택·제외 Matrix 작성

### Phase 1

- MVP Route·Lazy Loading·Shell
- Context Line·Navigation
- Analysis 제외

### Phase 2

- URL Query와 Selection Context
- Deep Link·새로고침 상태 유지

### Phase 3

- Overview 구현·연결

### Phase 4

- Objects Table·Filter·Inspector 구현·연결

### Phase 5

- Operations Queue·Detail·Activity 구현·연결

### Phase 6

- Executive Report·Print·LLM Adapter·Fallback 구현

### Phase 7

- Loading·Empty·Error·Low confidence·Data quality hold
- 반응형·접근성

### Phase 8

- Unit·E2E·Visual·Build·Bundle Test
- 기존 V1~V4 Smoke Test
- 문서·화면 캡처
- Commit·Push·서버 재시작·공개 URL 검증

각 Phase 완료 후 결과를 확인하고 필요한 Commit을 만든 뒤 다음 Phase로 계속 진행한다. 계획만 작성하고 중단하지 않는다.

## 11. 필수 테스트

### Unit

- API Adapter
- 상태 Grade Mapping
- Selection Query Parsing
- Report Fallback

### E2E

1. Overview → Objects → Operations → Report
2. Direct Objects Deep Link
3. Data quality hold
4. Partial API failure
5. LLM failure → Template Fallback
6. Mobile width no overflow
7. Report print layout

### Regression

- V1 Route
- V2 Route
- V3 Route
- V4 Route
- Blueprint Compare Route

기존 테스트를 삭제하거나 통과 기준을 약화하지 않는다.

## 12. 완료 조건

다음을 모두 충족해야 완료다.

1. `/app/projects/:projectId/mvp`가 존재한다.
2. 기존 V1~V4가 유지된다.
3. MVP Navigation은 네 화면만 제공한다.
4. Analysis 없이 사용자 흐름이 완결된다.
5. Canonical V3.1 실제 데이터 또는 명확히 표시된 계약형 Mock을 사용한다.
6. Asset·Event 선택이 화면 간 유지된다.
7. Report 숫자가 Overview·Operations와 일치한다.
8. LLM 실패 시 Fallback이 동작한다.
9. 부분 API 실패가 전체 화면 실패로 이어지지 않는다.
10. 1366×768과 모바일에서 가로 Overflow가 없다.
11. A4 PDF 인쇄가 가능하다.
12. Unit·E2E·Build·Regression Test가 통과한다.
13. Git Commit과 Push가 완료된다.
14. 공개 서버에서 실제 URL을 비로그인 또는 지정된 데모 접근 방식으로 검증한다.

## 13. Git·배포 규칙

- 다른 세션의 미커밋 파일을 수정하지 않는다.
- 원격 변경을 주기적으로 확인한다.
- 충돌 시 양쪽 변경을 보존한다.
- Phase별 의미 있는 Commit을 사용한다.
- Push 후 실제 서비스 Checkout을 Fast-forward한다.
- API·Frontend 프로세스를 올바른 환경으로 재시작한다.
- Cloudflare 공개 주소에서 HTTP와 실제 Browser를 모두 검증한다.

## 14. 최종 보고

작업 완료 후 다음을 정리해줘.

- 기준 Commit과 Worktree
- V1~V4 채택·제외 Matrix
- 새 MVP URL
- 구현한 네 화면과 주요 흐름
- API·Mock·LLM 연결 상태
- 주요 변경 파일
- 테스트 결과
- 기존 버전 회귀 결과
- Commit·Push 결과
- 서버 PID와 공개 검증 결과
- 남은 Blocker와 다음 우선순위

---

