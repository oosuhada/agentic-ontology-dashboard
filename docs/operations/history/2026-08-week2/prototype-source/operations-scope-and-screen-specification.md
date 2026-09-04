# Ontology Dashboard Operations 범위 및 4개 화면 명세서

- 문서 상태: `Operations baseline`
- 기준일: `2026-08-06`
- 근거: 2026년 8월 멘토링 결과
- 대상 데이터: `UCI AI4I 2020 Manufacturing Predictive Maintenance — Physics & Maintenance Canonical V3.1`
- 기준 구현:
  - V2 · Blueprint 1차: `/app/projects/manufacturing-demo-project/blueprint`
  - V1 · 기존 Dashboard: `/app/projects/manufacturing-demo-project`

## 1. 문서 목적

이 문서는 현재까지 확장된 전체 제품 기능 중 발표와 Operations 검증에 필요한 최소 범위를 다시 고정한다. 목표는 많은 메뉴를 구현하는 것이 아니라, Canonical V3.1의 설비 위험 정보를 이용해 생산 관리자와 현장 담당자가 하나의 사건을 확인하고 조치하며, 결과를 임원 보고서로 전달하는 흐름을 네 화면 안에서 완결하는 것이다.

```text
위험 현황 파악
→ 대상 설비 확인
→ 현장 조치 결정·기록
→ 임원 보고
```

이 문서가 승인된 이후 Operations 관련 신규 구현은 아래 네 화면의 완성도와 연결성을 우선한다.

## 2. 멘토링 결정사항 반영

| 주제 | 결정 | Operations 반영 방식 |
|---|---|---|
| 데이터셋 | Canonical V3.1 사용 가능 | 데이터 교체 없이 Canonical V3.1을 단일 기준 데이터로 사용 |
| 화면 범위 | V2 Overview·Objects·Operations + V1 임원 보고서 | 총 4개 화면만 발표 핵심 범위로 지정 |
| Analysis | Operations에서 제외 | 메뉴 숨김 또는 비활성 처리, 발표 동선과 완료 조건에서 제거 |
| 사용자 범위 | 현장 화면 + 생산 관리 화면에 집중 | 핵심 사용자 그룹을 생산 관리자와 현장 담당자로 축소 |
| 모델링 | 미탐·오탐 최적값은 산업·고객에 따라 다름 | 단일 절대 임계값을 정답으로 주장하지 않고 비용 가정별 권장값 제안 |
| 1주차 | 데이터 확보, 프레임워크·LLM 테스트 | 데이터 계약과 기술 실험 결과를 화면 개발 입력으로 사용 |
| 2주차 | 요구사항 정의서, Operations 설계안, 화면 공유 | 본 문서를 요구사항 기준선으로 사용하고 4개 화면을 공유 가능 상태로 완성 |

## 3. Operations 한 문장 정의

> Canonical V3.1 기반 설비 위험 정보를 생산 관리자가 우선순위로 확인하고, 현장 담당자가 대상 설비와 근거를 검토해 점검·조치 상태를 기록하며, 그 결과를 임원 보고서로 전달하는 제조 예지보전 의사결정 지원 Operations.

## 4. 핵심 사용자 범위

### 4.1 생산 관리자

시스템 역할 매핑:

- 주 역할: `process_manager`
- 발표 시 포함 가능한 읽기 전용 상위 관점: `executive_viewer`

핵심 과업:

- 현재 위험 설비와 생산 영향 파악
- 먼저 확인할 설비 결정
- 현장 점검 요청 또는 정지 검토 판단
- 조치 진행 상태 확인
- 임원에게 상황과 대응을 요약 보고

성공 기준:

- 첫 화면에서 30초 안에 가장 위험한 설비와 대응 필요성을 파악한다.
- 상세 모델 지식 없이도 위험, 영향, 권장 조치를 이해한다.
- 임원 보고서에 들어갈 핵심 숫자와 조치 상태가 화면 간 일치한다.

### 4.2 현장 담당자

Operations에서는 아래 기존 역할을 하나의 사용자 그룹으로 묶는다.

- `process_engineer`
- `maintenance_technician`

핵심 과업:

- 배정되거나 선택된 설비 확인
- 주요 속성, 위험도, 예상 고장 유형과 데이터 상태 확인
- 점검 요청을 확인하고 조치 상태 기록
- 현장 메모와 결과를 생산 관리자에게 전달

성공 기준:

- 대상 설비를 목록에서 빠르게 찾는다.
- 위험 상태와 점검에 필요한 최소 근거를 한 화면에서 확인한다.
- 수행한 조치가 Operations와 임원 보고서에 반영된다.

### 4.3 이번 Operations에서 사용자로 다루지 않는 역할

아래 역할은 계정과 기존 화면을 삭제하지 않지만 Operations 시나리오·화면 요구사항·발표 동선의 핵심 사용자에서 제외한다.

- Tenant Admin
- Quality Auditor
- Data Scientist / ML Validator
- FDE
- 별도 권한 설계가 필요한 외부 협력사

관리자, 감사, 모델 운영 기능은 시스템 유지용 기존 기능으로 남기되 이번 Operations 완료 판단에는 포함하지 않는다.

## 5. Operations 화면 구성

| # | 화면 | 기준 버전 | 주 사용자 | 핵심 질문 |
|---:|---|---|---|---|
| 1 | Overview | V2 · Blueprint 1차 | 생산 관리자 | 지금 무엇을 먼저 봐야 하는가? |
| 2 | Objects | V2 · Blueprint 1차 | 현장 담당자, 생산 관리자 | 어떤 설비이며 현재 상태와 근거는 무엇인가? |
| 3 | Operations | V2 · Blueprint 1차 | 생산 관리자, 현장 담당자 | 어떤 조치를 누가 수행하고 있으며 상태는 무엇인가? |
| 4 | Executive Report View | V1 · 기존 Dashboard | 생산 관리자, 임원 | 현재 위험과 대응 상황을 어떻게 보고할 것인가? |

## 6. 전체 사용자 흐름

### 6.1 기본 흐름

```text
[Overview]
생산 관리자가 위험 현황과 우선 설비 확인
        ↓ 설비 또는 Event 선택
[Objects]
현장 담당자가 설비 속성·위험·근거 확인
        ↓ 점검 또는 판단 업무로 이동
[Operations]
점검 요청·정지 검토·담당자·활동 기록 관리
        ↓ 보고서 갱신
[Executive Report View]
임원 의사결정 요약과 대응 상태 공유
```

### 6.2 안전한 실패 흐름

```text
데이터 품질 이상 또는 낮은 신뢰도
→ 고장 확정 표현 금지
→ hold_for_data_check 또는 추가 점검 권고
→ Operations에 확인 업무 기록
→ 임원 보고서에 불확실성과 확인 중 상태 표시
```

## 7. 화면 1 · Overview 명세

### 7.1 목적

생산 관리자가 공장 또는 라인 단위의 위험 현황을 빠르게 파악하고, 상세 확인이 필요한 설비를 선택하는 첫 화면이다.

### 7.2 기준 구현

- V2 Blueprint `Overview`
- 기존 구성 요소 중 `Analysis 열기` 동선은 제거하거나 Operations에서 비활성화한다.

### 7.3 필수 정보

1. Critical 설비 또는 Event 수
2. Warning 설비 또는 Event 수
3. 평균 위험도
4. 예상 Downtime 영향
5. 설비별 고장 확률 비교 차트
6. 판단 대기 Event 목록
7. 선택 Event의 상태, 예상 고장 유형, 위험도
8. 마지막 데이터 갱신 시점과 Dataset Version

### 7.4 우선순위 규칙

목록은 기본적으로 아래 순서를 사용한다.

1. `data_quality_hold`는 별도 경고 그룹으로 분리
2. `critical`
3. `warning`
4. 높은 `failure_probability`
5. 높은 설비 `criticality`
6. 긴 `estimated_downtime_minutes`

단순 확률 순위만으로 생산 우선순위를 결정하지 않는다.

### 7.5 필수 상호작용

- Event 또는 설비 선택
- 위험 상태 필터
- 라인 필터
- 선택 설비를 Objects 화면에서 열기
- 선택 Event를 Operations 화면에서 열기
- 임원 보고서로 이동
- 데이터 새로고침

### 7.6 상태 처리

| 상태 | 표현 |
|---|---|
| Loading | KPI와 목록 영역에 레이아웃을 유지하는 Skeleton 표시 |
| Empty | 정상 상태인지 데이터 미연결인지 구분해 설명 |
| Error | 전체 흰 화면 대신 실패한 패널과 재시도 버튼 표시 |
| Low confidence | 확률과 함께 낮은 신뢰도·추가 확인 필요 표시 |
| Data quality hold | 고장 수치 대신 데이터 확인 필요 상태를 우선 표시 |

### 7.7 완료 조건

- 생산 관리자가 가장 위험한 설비를 30초 안에 식별할 수 있다.
- 차트와 Event 목록의 위험 값이 같은 데이터 계약을 사용한다.
- 선택한 설비가 Objects와 Operations 화면에서도 유지된다.
- Analysis 화면을 거치지 않고 다음 업무를 수행할 수 있다.
- 데스크톱과 발표용 1366×768 이상 화면에서 핵심 정보가 첫 화면에 보인다.

## 8. 화면 2 · Objects 명세

### 8.1 목적

선택된 설비의 정체성, 운영 속성, 위험 상태, 담당자와 데이터 출처를 확인하고 현장 업무의 대상을 명확히 하는 화면이다.

### 8.2 기준 구현

- V2 Blueprint `Objects`
- 복잡한 ObjectSet 합집합·교집합 기능보다 설비 검색, 필터, 상세 확인을 우선한다.

### 8.3 필수 정보

#### 목록 영역

- 설비명과 설비 ID
- 생산 라인
- 현재 위험 상태
- 고장 확률
- 설비 중요도
- 담당 엔지니어 또는 현장 담당자

#### 상세 Inspector

- 설비 기본 정보
- 제품 유형 또는 운전 조건
- 현재 센서 핵심값
- 예상 고장 유형
- 위험도와 Confidence
- 데이터 품질 상태
- Dataset Version과 Source reference
- 현재 점검·조치 상태

### 8.4 필수 필터

- 설비명 또는 ID 검색
- 생산 라인
- 위험 상태
- 고장 유형
- 위험 임계값 이상
- 담당자
- 부품 확보 여부

모든 필터를 한 번에 구현하기 어렵다면 2주차 Operations 필수 필터는 `검색`, `라인`, `위험 상태`, `담당자` 네 가지로 제한한다.

### 8.5 필수 상호작용

- 목록 행 선택
- Overview에서 전달된 설비 자동 선택
- 위험 설비만 보기
- 상세 속성 확인
- 선택 설비의 Operations 업무 열기
- 현장 메모 작성 진입

### 8.6 명시적 제외

- Analysis graph 편집
- 복잡한 관계 탐색 알고리즘
- 임의 Cypher·SQL 실행
- 대량 객체 편집
- 3D 설비 시각화

### 8.7 완료 조건

- Overview에서 선택한 설비가 Objects에서 동일하게 열려야 한다.
- 현장 담당자가 설비 ID, 상태, 고장 유형, 담당자, 데이터 품질을 한 화면에서 확인한다.
- 데이터가 없는 속성은 `0`이나 정상으로 오해되지 않게 `—`와 설명을 표시한다.
- 1,000개 이상 목록에서도 스크롤과 선택이 사용 가능하다.
- 상세 화면의 위험 값이 Overview 및 Operations와 일치한다.

## 9. 화면 3 · Operations 명세

### 9.1 목적

생산 관리자와 현장 담당자가 동일한 Event를 기준으로 점검 요청, 정지 검토, 담당자 배정과 수행 결과를 공유하는 업무 화면이다.

### 9.2 기준 구현

- V2 Blueprint `Operations`
- 기존 Role Workspace, Decision, Activity 구성을 유지하되 두 사용자 그룹의 업무 차이에 집중한다.

### 9.3 사용자별 기본 관점

#### 생산 관리자 관점

- 운영 판단 Inbox
- 위험·생산 영향·권장 결정
- 점검 요청
- 정지 검토
- 담당자 배정
- 미완료 조치와 기한 확인

#### 현장 담당자 관점

- 내 담당 설비 점검 목록
- 점검 우선순위와 기한
- 설비 및 Event 근거 확인
- 작업 시작·완료·문제 발견·작업 불가 기록
- 현장 메모와 측정값 기록

### 9.4 지원 결정

- `continue_monitoring`
- `request_inspection`
- `review_shutdown`
- `hold_for_data_check`

시스템은 실제 설비를 자동 정지하지 않는다. `review_shutdown`은 권한 있는 사람의 검토 요청 상태다.

### 9.5 필수 정보

- Event 상태와 위험도
- 예상 고장 유형
- 설비 중요도
- 예상 Downtime
- 담당자
- 부품 확보 여부
- 권장 결정과 근거 요약
- 조치 상태
- 생성자와 변경 시간
- Activity/Audit 기록

### 9.6 필수 상호작용

- Event 선택
- 점검 요청 생성
- 정지 검토 상태 등록
- 담당자 지정 또는 변경
- 현장 작업 상태 변경
- 메모 작성
- 완료 결과 기록
- 임원 보고서 갱신 또는 열기

### 9.7 감사 기록 최소 계약

모든 상태 변경은 아래 정보를 남겨야 한다.

- 사용자
- 역할
- Project와 Workspace
- Event와 Equipment ID
- 수행 Action
- 이전 상태와 변경 상태
- 작성 시각
- 사용자 메모

### 9.8 완료 조건

- 생산 관리자와 현장 담당자가 같은 Event 상태를 공유한다.
- 작업 요청 생성 후 새로고침해도 상태와 Activity가 유지된다.
- 권한이 없는 사용자는 Action 버튼이 비활성 또는 숨김 처리된다.
- 실제 설비 제어가 실행된 것처럼 표현하지 않는다.
- 완료된 조치가 임원 보고서의 대응 현황에 반영된다.

## 10. 화면 4 · Executive Report View 명세

### 10.1 목적

생산 관리자가 운영 현황과 조치 결과를 임원에게 전달할 수 있도록 위험, 영향, 대응과 근거를 문서 형태로 요약하는 화면이다.

### 10.2 기준 구현

- V1 기존 Dashboard의 `RoleReportWorkbench`
- 임원 Viewer 또는 생산 관리자 읽기 관점
- 프린트와 PDF를 고려한 A4 레이아웃

### 10.3 필수 섹션

1. 보고서 제목, 문서 번호, 발행일, Revision
2. 임원 의사결정 요약
3. 현재 Critical·Warning 현황
4. 주요 위험 설비 또는 라인
5. 예상 생산 영향과 Downtime
6. 진행 중·완료된 대응 조치
7. 미결정 사항과 요청할 의사결정
8. 불확실성 또는 데이터 품질 경고
9. 근거 데이터와 Dataset Version

### 10.4 표현 원칙

- 모델 확률을 고장 확정으로 표현하지 않는다.
- 숫자마다 출처 또는 Evidence 연결을 유지한다.
- 기술 세부보다 사업 영향과 대응 상태를 먼저 배치한다.
- 미탐·오탐 비용 가정이 정해지지 않은 상태에서 임계값을 절대 최적값으로 표현하지 않는다.
- 보고서만 인쇄해도 Project, 기간, 대상 데이터, 작성 시점이 식별되어야 한다.

### 10.5 필수 상호작용

- 기간 또는 보고 대상 선택
- 상세 Dashboard로 이동
- Print
- PDF Export 또는 브라우저 PDF 출력
- 최신 조치 상태 새로고침

### 10.6 완료 조건

- Overview와 Operations의 핵심 수치가 보고서와 일치한다.
- A4 출력에서 제목, 요약, 표와 차트가 잘리지 않는다.
- 임원은 기술 화면을 열지 않고도 현재 위험, 영향, 대응과 필요한 결정을 이해한다.
- 불확실성, 데이터 품질 문제, 미완료 대응이 숨겨지지 않는다.

## 11. 화면 간 데이터 계약

네 화면은 서로 다른 수치를 자체 계산하지 않고 동일한 Project·Dataset Version·Event 계약을 사용해야 한다.

### 11.1 공통 식별자

- `organization_id`
- `project_id`
- `workspace_id`
- `dataset_version_id`
- `equipment_id`
- `event_id`
- `prediction_id`
- `model_version`
- `threshold_policy_version`

### 11.2 공통 위험 필드

- `failure_probability`
- `risk_status`
- `predicted_failure_type`
- `confidence`
- `recommended_decision`
- `criticality`
- `estimated_downtime_minutes`
- `data_quality_state`

### 11.3 공통 업무 필드

- `assigned_engineer`
- `inspection_status`
- `decision_status`
- `spare_part_available`
- `due_at`
- `last_action_at`
- `last_action_by`

## 12. 모델 임계값·미탐·오탐 요구사항

### 12.1 제품 원칙

미탐과 오탐의 상대 비용은 업종, 설비 중요도, 생산 계획과 고객 정책에 따라 달라진다. 따라서 Operations는 하나의 임계값을 모든 고객에게 적용되는 최적값으로 주장하지 않는다.

### 12.2 Operations 제공 수준

Operations는 아래 입력을 바탕으로 권장 임계값 또는 권장 범위를 제시한다.

- 미탐 1건의 가정 비용
- 오탐 1건의 가정 비용
- 최소 Recall 목표
- 설비 중요도
- 점검 가능 인력 또는 일일 처리 한도

출력:

- 현재 운영 임계값
- 권장 임계값 또는 범위
- 예상 Recall·Precision 변화
- 예상 미탐·오탐 건수
- 선택 근거와 적용한 가정

### 12.3 화면 반영

- Overview에는 현재 정책에 따른 위험 상태만 간단히 표시한다.
- Operations에는 권장 조치 근거로 임계값 정책 버전을 표시할 수 있다.
- Executive Report에는 “현재 운영 가정에서 선택된 임계값”이라고 표현한다.
- 별도 모델링 화면은 Operations 범위에 추가하지 않는다.

## 13. Operations 제외 범위

다음은 구현되어 있거나 향후 필요하더라도 이번 Operations 완료 조건에서 제외한다.

- V2 `Analysis` 화면
- 자유 배치 Analysis Canvas와 Dependency Graph
- V3·V4 상용화 Control Plane
- 전체 8개 역할별 독립 UX
- 다중 고객사·다중 산업 최적화
- 실시간 Streaming 인프라
- 자동 재학습과 자동 배포
- 자동 설비 정지 또는 CMMS·MES 쓰기 연동
- 복잡한 Branching·Marking·ABAC 관리 화면
- Object Storage 운영 화면
- MLOps 전용 콘솔
- 임의 생성형 UI
- 최고 성능 모델 경쟁

## 14. 기능 요구사항 목록

| ID | 요구사항 | 우선순위 |
|---|---|---|
| Operations-FR-001 | Canonical V3.1을 네 화면의 공통 데이터 기준으로 사용한다. | Must |
| Operations-FR-002 | Overview에서 위험 설비 우선순위와 생산 영향을 확인한다. | Must |
| Operations-FR-003 | Overview 선택 상태를 Objects와 Operations로 전달한다. | Must |
| Operations-FR-004 | Objects에서 설비 검색·필터·상세 확인을 제공한다. | Must |
| Operations-FR-005 | Operations에서 점검 요청과 상태 변경을 기록한다. | Must |
| Operations-FR-006 | 생산 관리자와 현장 담당자가 동일 Event 상태를 공유한다. | Must |
| Operations-FR-007 | 임원 보고서가 위험·영향·대응·근거를 요약한다. | Must |
| Operations-FR-008 | 보고서와 운영 화면의 수치가 동일한 계약에서 계산된다. | Must |
| Operations-FR-009 | 저신뢰·데이터 오류를 고장 확정으로 표현하지 않는다. | Must |
| Operations-FR-010 | V2 Analysis를 Operations 메뉴·동선에서 제외한다. | Must |
| Operations-FR-011 | 미탐·오탐 비용 가정에 따른 임계값 권장 정보를 제공한다. | Should |
| Operations-FR-012 | Executive Report를 A4 또는 PDF로 출력할 수 있다. | Should |
| Operations-FR-013 | 라인·상태·담당자 필터를 제공한다. | Should |
| Operations-FR-014 | 현장 측정값과 체크리스트를 상세 기록한다. | Could |

## 15. 비기능 요구사항

### 15.1 성능

- Overview 첫 의미 있는 화면: 로컬 데모 기준 3초 이내
- 필터 반응: 로컬 데이터 기준 500ms 이내
- 1,000개 설비 목록에서 스크롤 중 심각한 프레임 저하가 없어야 함

### 15.2 신뢰성

- 한 패널 API 실패가 전체 화면 흰 화면으로 이어지지 않아야 함
- 새로고침 후 업무 상태가 유지되어야 함
- Dataset Version과 모델 버전이 보고서까지 추적되어야 함

### 15.3 사용성

- 핵심 사용자에게 Analysis 전문 용어를 기본 노출하지 않음
- 색상만으로 위험 상태를 구분하지 않음
- Loading·Empty·Error·Permission 상태를 각각 구분
- 주요 Action에는 결과와 실패 이유를 표시

### 15.4 안전성

- 무승인 자동 정지 금지
- 데이터 품질 실패 시 추론과 조치 추천을 억제
- LLM이 계산된 위험 수치나 운영 결정을 임의 변경하지 않음

## 16. 2주차 화면 공유 시나리오

### 시나리오 A · 생산 관리자

1. Overview에서 Critical 설비와 Downtime 영향을 확인한다.
2. 가장 우선순위가 높은 설비를 선택한다.
3. Objects에서 설비 정보와 위험 근거를 확인한다.
4. Operations에서 현장 점검을 요청하고 담당자를 지정한다.
5. Executive Report에서 해당 조치가 진행 중으로 반영된 것을 확인한다.

### 시나리오 B · 현장 담당자

1. Operations에서 내 담당 점검을 확인한다.
2. Objects에서 설비와 센서 핵심값을 확인한다.
3. 현장 점검 결과와 메모를 기록한다.
4. 작업 상태를 완료 또는 문제 발견으로 변경한다.
5. 생산 관리자 화면과 보고서에 결과가 반영되는지 확인한다.

### 시나리오 C · 데이터 품질 보류

1. 데이터 품질 문제가 있는 Event를 연다.
2. Overview와 Objects가 고장 확정 대신 확인 필요를 표시한다.
3. Operations에서 데이터 확인 업무를 등록한다.
4. Executive Report에서 불확실성과 확인 중 상태를 표시한다.

## 17. Operations 완료 정의

아래 조건을 모두 충족하면 2주차 Operations 화면 공유가 가능하다고 판단한다.

1. Canonical V3.1 데이터가 네 화면에서 동일하게 식별된다.
2. Overview, Objects, Operations, Executive Report 네 화면이 실제 데이터로 로드된다.
3. Analysis 없이 기본 사용자 흐름이 완결된다.
4. 생산 관리자와 현장 담당자 시나리오가 각각 재현된다.
5. 화면 간 선택한 Equipment·Event 문맥이 유지된다.
6. 점검 요청 또는 상태 변경이 저장되고 보고서에 반영된다.
7. 정상, Warning, Critical, Low confidence, Data quality hold 상태를 구분한다.
8. 임원 보고서가 출력 가능한 형태로 표시된다.
9. 미탐·오탐 최적값을 절대값으로 주장하지 않고 적용 가정을 표시한다.
10. 발표 중 치명적인 404, 권한 오류, 무한 Loading과 흰 화면이 발생하지 않는다.

## 18. 구현 우선순위

### P0 · 화면 범위 고정

- V2 메뉴에서 Analysis 제외
- Overview·Objects·Operations만 핵심 내비게이션으로 유지
- V1 Executive Report 접근 동선 연결
- 두 사용자 그룹에 맞는 용어와 첫 화면 정리

### P1 · 수직 흐름 연결

- Equipment·Event 선택 상태 전달
- Operations 상태 영속화
- 보고서 수치·조치 상태 동기화
- Loading·Empty·Error 상태 정리

### P2 · 발표 완성도

- 데스크톱 레이아웃과 A4 출력 정리
- Canonical V3.1 명칭과 버전 일관성
- 데모 시나리오와 화면 캡처
- 4개 화면 E2E 검증

### P3 · 시간 허용 시 추가

- 임계값 권장 범위 비교
- 현장 체크리스트 상세화
- 모바일 현장 화면 최적화

## 19. 변경 관리 원칙

- 네 화면 밖의 기능을 새로 추가하기 전에 이 문서의 Must 요구사항 미완료 여부를 먼저 확인한다.
- V3·V4 개발 결과는 삭제하지 않지만 이번 Operations 동선에 강제로 포함하지 않는다.
- 기존 구현을 재사용하되 화면 이름과 데이터가 다른 버전 사이에서 섞이지 않도록 한다.
- 범위 변경이 필요하면 화면 수, 사용자 수, 데이터 계약과 완료 정의를 함께 수정한다.

