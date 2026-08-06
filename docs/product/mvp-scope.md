# Predictive Maintenance MVP 범위

## 제품 목적

Canonical V3.1 예측 결과를 단순 차트가 아니라 실제 업무 판단 흐름으로 연결합니다. 사용자는 위험 설비를 찾고, 근거를 확인하고, 사람의 판단 또는 현장 메모를 기록한 뒤 임원 보고 형태로 결과를 확인합니다.

## 사용자

### 관리자·임원

- 전체 위험 현황과 우선순위를 확인
- 위험 Event의 모델 권고와 근거를 검토
- `request_inspection`, `review_shutdown`, `defer` 등의 실제 판단을 기록
- Executive Report를 A4 인쇄/PDF 형태로 확인

### 실무 엔지니어

- 설비 목록과 Inspector에서 센서·기여 요인·출처를 확인
- Operations에서 현장 점검 결과와 전달 사항을 메모
- 관리자 판단과 모델 권고를 읽되 판단 기록 권한은 갖지 않음

## 화면

1. **Overview** — KPI, 라인별 위험 분포, 고위험 설비, 판단 대기열, 데이터 신선도
2. **Objects** — 검색·필터·가상화 Table, 설비 Inspector, 요인·센서·Provenance
3. **Operations** — Event Queue, 권고와 실제 판단 분리, Decision/Note Activity
4. **Executive Report** — 경영 요약, KPI, 주요 설비, 판단 이력, 한계와 출처

URL query의 `view`, `asset_id`, `event_id`, `role`, `workspace_id`가 현재 선택 상태의 기준입니다. 유효하지 않은 ID는 임의로 다른 설비를 선택하지 않고 안전한 empty state를 표시합니다.

## 완료 범위

- 두 역할 로그인 카드
- 네 화면 간 선택 문맥 유지
- Canonical Runtime 우선 조회와 Gold Fixture fallback
- 패널별 loading, empty, error, stale, permission 상태
- 실제 Decision·Note API 기록
- LLM Report 실패 시 deterministic report, 최종 template fallback
- 390px 모바일 화면과 A4 print layout

## 제외 범위

- V1, V2, V3, V4 및 비교 화면
- 범용 Analysis authoring, Agent Workbench, Governance·Admin·Modeling Console
- 회원가입과 다역할 사용자 관리 화면
- 자동 설비 정지, 자동 Work Order 생성, 모델 권고의 자동 실행
- 평가용 정답 라벨을 운영 화면에 노출하는 기능
