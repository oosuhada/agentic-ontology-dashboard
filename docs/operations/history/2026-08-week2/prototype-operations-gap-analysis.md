# 프로토타입과 멘토링 Operations 차이 분석

## 1. 목적

이 문서는 `oosuhada/agentic-ontology-dashboard`의
`codex/current-operations-repository-convergence-20260806` 브랜치를 실행 가능한
프로토타입으로 보고, 멘토링 Operations 기준과의 차이를 팀이 결정할 수 있게 정리한다.

확인된 코드 계약은 [현행 Operations 구현 계약 기준선](../../current-operations-implementation-baseline.md)을
따른다. 현행과 다른 목표는 `변경 제안`이며 단순 미결정이나 미구현으로 해석하지 않는다.

판정의 의미는 다음과 같다.

- `유지`: 현재 구현과 방향이 일치한다.
- `수정`: 구현 자산은 사용하되 제품 계약을 변경해야 한다.
- `제외`: Operations에서 비활성화하거나 후속 범위로 이동한다.
- `확인 필요`: 담당자 합의 전 확정하지 않는다.

## 2. 핵심 차이

| 영역 | 멘토링 기준 | 프로토타입 현재 상태 | 잠정 판정 | 결정할 내용 |
|---|---|---|---|---|
| 개발 기반 | 새 `ontology_dashboard` | FastAPI·React 통합 Operations가 이미 구현됨 | 유지 | 해당 브랜치를 공식 개발 기준으로 채택할지 |
| 사용자 | 현장 담당자, 생산 관리자 | 실무 엔지니어, 관리자·임원 | 수정 | 역할명과 실제 업무 권한 대응 |
| 화면 | 기간·가동·생산·정비 집계 기반 네 화면 | 위험 KPI·Event·Inspector 기반 네 화면 | 수정 | 화면별 현행과 V2 기능 분리 |
| Analysis/Admin | Operations 제외 | 현재 진입점에서는 제외 | 유지 | 종료된 기능을 재활성화하지 않음 |
| Operations | 생산·정비 현황 조회 | Event Queue, Decision, Note Activity 중심 | 변경 제안 | 현행 유지 또는 생산·정비 중심으로 제품 흐름 재설계 |
| 쓰기 기능 | 점검 입력·정비 요청은 Operations 이후 | Decision과 Note 저장·권한·감사 구현 | 변경 제안 | 현행 유지 또는 기존 기능 제거 |
| 인증·권한 | Operations 이후 확장 | 두 역할 로그인, session, RBAC, CSRF 구현 | 확인 필요 | 데모 필수 기능으로 유지할지 |
| API | 화면별 API 초안 | `/dashboard`, `/results/latest`, Event API | 수정 | 현행 API 유지 후 누락 필드만 보강할지 |
| Canonical | V3.1 사용 | PostgreSQL Canonical V3.1 Runtime | 유지 | 공식 ZIP 적재 및 버전 표시 검증 |
| Fallback | 미정 | Canonical 장애 시 Gold Fixture와 warning | 현행 확인 | 발동 조건·표시 문구를 공통 계약으로 채택할지 |
| Result Artifact | 공통 예측 계약 | 최신 결과 조회와 Event/Evidence로 확장 | 수정 | 공식 Artifact와 API 확장 필드 경계 |
| 보고서 | 기간 기반 V2 Executive Report | 선택 Event 역할별 report와 fallback | 수정 | 현행 유지, mock V2 계약 우선 검증 |
| 자동 실행 | 설비 자동 정지·자동 발주 제외 | 권고와 사람 판단 분리 | 유지 | 자동 실행 금지 테스트 유지 |
| 평가 truth | 일반 화면 비노출 | 비노출 계약 존재 | 유지 | 운영 API 노출 금지 유지 |

## 3. 확인된 정합성 이슈

### 3.1 역할 정의

내부 enum `manager`, `engineer`와 권한은 유지한다. Week 2 UI는 `매니저`,
`엔지니어`를 사용하고 표시 매핑을 분리해 후속 사용자 검증 후 변경 가능하게 한다.

### 3.2 Operations 목적

Week 2 Current는 Event Queue와 사람의 판단·메모 이력을 유지한다. 생산 작업과 정비
이력 중심 흐름은 Target으로 남기고 별도 결정 없이 이번 주 구현 범위를 늘리지 않는다.

### 3.3 Result Artifact 확장 필드

공식 V3.1 Result Artifact 원문에는 `site_id`, `cell_id`가 없다. 화면/API에서 이
필드를 반환한다면 `asset_master.csv` 결합값으로 정의해야 한다. Event, Evidence,
approval/execution 상태도 공식 Artifact 원천 필드와 구분한다.

### 3.4 쓰기 기능

프로토타입의 Decision과 Note는 인증, 권한, CSRF, 감사 이력을 포함한다. 기능을
제외하더라도 코드를 즉시 삭제하지 않고 진입점과 Operations 범위에서 비활성화할지
판단해야 한다.

### 3.5 Fallback

Gold Fixture는 화면 흐름 검증에는 유용하지만 실제 Canonical 조회 결과로 오해될
수 있다. 유지할 경우 응답과 화면에 `fallback`, 원인, 신선도, 데이터 한계를
명시해야 한다.

## 4. 권장 결정안

| 결정 ID | 권장안 | 이유 |
|---|---|---|
| DEC-01 | 해당 브랜치를 개발 기준으로 채택 | 이미 V3.1 Runtime, 네 화면, API, 테스트가 존재 |
| DEC-02 | 제품 문서가 프로토타입 구현보다 우선 | 구현에서 요구사항을 역으로 확정하는 오류 방지 |
| DEC-03 | 현행 API 경로를 우선 유지하고 응답 계약을 보강 | 불필요한 화면별 API 재작성 방지 |
| DEC-04 | Result Artifact 원문과 API/ViewModel 확장을 분리 | provenance와 필드 출처 보존 |
| DEC-05 | Gold Fixture는 명시적 fallback으로만 유지 | 데모 복원력과 데이터 오인 방지를 함께 확보 |
| DEC-06 | 자동 실행 금지와 truth 비노출 계약 유지 | 멘토링 범위 및 안전 원칙과 일치 |
| DEC-07 | Decision/Note와 인증은 현행 기능으로 기록하고 제거 여부를 별도 결정 | 저장·권한·감사·테스트가 이미 구현됨 |

## 5. 팀원별 확인 사항

### 팀원1 — 화면

- 두 역할의 최종 사용자 명칭
- 네 화면별 실제 표시 필드
- Operations에서 생산·정비와 Event/Activity의 우선순위
- 검색·필터·정렬·상세 이동
- 상태 문구·색상과 loading/empty/error/stale/permission 화면

### 팀원3 — 데이터·조회·집계 API

- 공식 V3.1 패키지 적재 결과와 최신 Artifact 조회
- 위험등급 enum과 임계값 산출 책임
- `/dashboard`, `/results/latest` 응답의 공식/결합/계산 필드 구분
- 목록 pagination, 기준시각, stale 기준
- Event/Evidence와 Artifact의 ID 연결 방식

### 팀원4 — 리포트 API·생성

- 보고서 입력 JSON과 Result Artifact 연결
- 출력 JSON과 화면 표시 필드
- 확정 원인·비용 효과·자동 실행을 암시하지 않는 문장 규칙
- LLM 실패 시 deterministic/template fallback
- provenance와 보고서 생성시각 보존

## 6. 완료 조건

- 표의 모든 `확인 필요` 항목에 합의자와 결정일이 기록된다.
- 결정 결과가 요구사항과 공통 스키마에 반영된다.
- 유지·수정·제외 판정이 코드 영향 분석으로 연결된다.
- 팀원이 추가 해석 없이 화면·API·LLM 구현을 시작할 수 있다.

