# START HERE — Ontology Dashboard 팀 온보딩

이 폴더는 프로젝트를 처음 전달받은 팀원이 제품의 목적, 구현 범위, 사용자 흐름과 코드 위치를 빠르게 파악하기 위한 공식 시작점이다.

## 브라우저에서 시각적으로 보기

로컬 서버가 실행 중이면 다음 공개 route를 먼저 연다.

```text
http://127.0.0.1:3100/team-share
```

이 화면은 로그인 없이 User Flow, 역할별 화면, Dataset 적응형 구성, Analysis·Ontology와 구현 상태를 클릭하며 볼 수 있는 HTML Story다.

![Team share story](./assets/screenshots/00-team-share-story.png)

## 프로젝트 한 문장

Ontology Dashboard는 **Dataset → Ontology Object → Analysis → Report/Dashboard → Evidence → Governance → Action**을 조직·Project·Workspace·역할·사용자 권한에 따라 연결하는 운영 의사결정 플랫폼 프로토타입이다.

단순한 제조 Dashboard가 아니라, Dataset과 역할이 달라지면 화면 구성과 첫 업무 화면이 달라지고, 실무자가 만든 근거 기반 보고서를 운영 매니저와 임원이 검토하는 업무 흐름을 검증한다.

## 5분 읽기 순서

1. [`01-product-overview.md`](./01-product-overview.md) — 왜 만들었고 무엇이 핵심인가
2. [`02-feature-tour.md`](./02-feature-tour.md) — 실제 화면 15장과 구현 설명
3. [`03-user-flow.md`](./03-user-flow.md) — 가입부터 역할별 업무와 개인화까지
4. [`06-implementation-status.md`](./06-implementation-status.md) — API·DB 연결과 프로토타입 경계

## 직접 실행할 때

1. [`04-demo-guide.md`](./04-demo-guide.md) — 15분 데모 순서와 계정
2. [`05-repository-map.md`](./05-repository-map.md) — 수정할 기능의 코드 위치
3. [`07-team-review-checklist.md`](./07-team-review-checklist.md) — 팀이 결정할 범위
4. [`08-share-message.md`](./08-share-message.md) — 팀 채팅·Draft PR에 사용할 문안

## 핵심 차별점

### 역할에 따라 첫 화면이 다르다

```text
임원 Viewer / 운영 매니저 / 품질·감사 Viewer
→ Reports가 메인

도메인 엔지니어 / 현장 작업자 / 데이터 사이언티스트 / FDE
→ Dashboards가 메인

조직 관리자
→ 별도의 Admin Control Plane
```

### 보고서와 Dashboard가 하나의 근거 체계로 연결된다

실무자는 Dashboard, Analysis와 Ontology에서 근거를 확인하고 보고서를 수정한다. 운영 매니저와 임원은 텍스트 설명과 연결된 시각화 근거를 먼저 읽고, 필요할 때 상세 Dashboard로 내려간다.

### Dataset에 따라 화면 종류가 달라진다

Dataset schema, 시간·수치·범주·관계·문서 신호와 projection 상태를 분석해 Board definition, Tab, 배치와 기본 시각화를 결정한다.

### 동일 역할도 사용자별 화면이 달라진다

같은 역할의 초기 Template은 같지만 Board 위치, 즐겨찾기, Filter, 시각화와 Display 설정은 사용자 ID별로 저장된다.

## 현재 기준 버전

```text
Commit  064fb49
Tag     complete-user-flow-20260803
Web     http://127.0.0.1:3100/
API     http://127.0.0.1:8100/
```

## 공유할 때 권장 표현

> 프로젝트를 시작하기 전에 요구사항과 업무 흐름의 해석 차이를 줄이기 위해 실제로 동작하는 선행 프로토타입을 만들었습니다. 전체를 그대로 채택하자는 의미가 아니라, 구현된 흐름을 기준으로 초기 MVP 범위와 역할별 경험, 데이터 구성 방식을 함께 결정하기 위한 저장소입니다.


