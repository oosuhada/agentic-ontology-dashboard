# Operations 기능 명세서

## 1. 기준

- Identity/RBAC 역할: `process_manager`, `process_engineer`, `maintenance_technician`
- 제품 표시 명칭: 생산 운영 의사결정자, 현장 엔지니어, 정비 작업자
- 기존 `manager`, `engineer` 값은 Report/UI compatibility view alias로 유지
- 화면: Overview, Objects, Operations, Executive Report
- 공통 필드: [스키마 정의서](./schema-definition.md)
- 현행 기준: [현행 Operations 구현 계약 기준선](./current-operations-implementation-baseline.md)
- Closed-loop 역할·Action 기준: [Product/API/UI 소비 계약](../closed-loop-product-consumption-contract.md)
- 상태: `초안 — 현행 기능과 변경 제안 분리`

각 화면은 `현행 구현`과 `V2 변경 제안`을 구분한다.

## 2. 공통 기능

| ID | 기능 | 입력/처리 | 출력 | 오류·완료 기준 |
|---|---|---|---|---|
| FEAT-CM-001 | 공통 필터 | 사이트·셀·유형·등급·기간을 검증 | 적용 필터 | 목록과 집계에 같은 조건 적용 |
| FEAT-CM-002 | 화면 이동 | `asset_id`와 필터 유지 | 대상 화면 | 같은 설비·조건이 열린다 |
| FEAT-CM-003 | 기준 정보 | 응답 provenance 조회 | 기준시각·버전 | 데이터·모델·schema 표시 |
| FEAT-CM-004 | 화면 상태 | 요청별 상태 분리 | loading/empty/error/stale/fallback | 임의 값으로 대체하지 않음 |
| FEAT-CM-005 | 상태 표현 | enum을 표시 규칙에 매핑 | 색상·아이콘·텍스트 | enum과 한국어 명칭 일치 |

## 3. Overview

현행 구현: 위험 KPI, 라인별 위험 분포, Downtime, 판단 대기 Event와 데이터 신선도.

아래 표는 가동·유형·생산·정비 집계를 추가하는 `V2 변경 제안`이다.

| ID | 기능 | 입력/처리 | 출력 | 완료 기준 |
|---|---|---|---|---|
| FEAT-OV-001 | 설비 현황 | 최신 관측과 자산 집계 | 전체·가동·비가동 수 | 가동+비가동=전체 |
| FEAT-OV-002 | 위험 현황 | 같은 Artifact snapshot 집계 | 등급별 수 | 4등급과 품질 보류를 분리 |
| FEAT-OV-003 | 유형 요약 | `asset_type` 집계 | Compressor/CNC 수 | 유형 합=전체 |
| FEAT-OV-004 | 상위 위험 설비 | 등급 우선, 확률 내림차순 | Top N 목록 | 중복 자산 없음 |
| FEAT-OV-005 | 운영 요약 | 기간 내 생산·정비 집계 | 작업·정비 건수 | Operations와 일치 |
| FEAT-OV-006 | 상세 이동 | 위험 설비 선택 | Objects 상세 | 선택 `asset_id` 유지 |

## 4. Objects

현행 구현: 검색·라인·상태·담당자 필터, 선택 설비 Inspector, 센서·요인·provenance.

현재 Operations는 현행 필터를 유지한다. site/cell/유형/기간 필터는 Target으로 남긴다.

아래 표의 site/cell/유형/기간 필터와 전용 history·maintenance 조회는
`V2 변경 제안`이다.

| ID | 기능 | 입력/처리 | 출력 | 오류·완료 기준 |
|---|---|---|---|---|
| FEAT-OB-001 | 설비 목록 | 필터·정렬·pagination | AssetPredictionSummary 목록 | 자산 중복 없음 |
| FEAT-OB-002 | 설비 상세 | `asset_id` 검증 후 원천·Artifact 결합 | AssetDetail | 없는 ID는 명시적 404 |
| FEAT-OB-003 | 최신 센서 | 유형별 최신 observation 선택 | Compressor/CNC 센서 | 유형별 필드가 섞이지 않음 |
| FEAT-OB-004 | 센서 추세 | 자산·기간·센서 key 검증 | 시계열 목록 | 기간 밖 데이터 없음 |
| FEAT-OB-005 | 예측 결과 | 최신 Artifact 조회 | 확률·등급·confidence·horizon | Artifact와 일치 |
| FEAT-OB-006 | 판단 근거 | Artifact Top-3 보존 | factor·값·기여·방향 | 순서·부호 변경 없음 |
| FEAT-OB-007 | 설비 관계 | 양방향 관계 탐색 | 연결 자산 | 인과관계로 표현하지 않음 |
| FEAT-OB-008 | 정비 이력 | 자산·기간 필터 | 정비 목록 | 선택 자산만 반환 |

## 5. Operations

상태: `변경 제안`. 채택하면 현행 Event 업무 흐름과 병합하거나 교체해야 한다.

| ID | 기능 | 입력/처리 | 출력 | 완료 기준 |
|---|---|---|---|---|
| FEAT-OP-001 | 생산 요약 | 기간·위치별 cycle 집계 | 작업·완료 건수 | 목록 합계와 일치 |
| FEAT-OP-002 | 생산 목록 | cycle과 최신 Artifact 결합 | 생산 작업·위험 등급 | 결합 출처 명시 |
| FEAT-OP-003 | 정비 요약 | 기간·위치별 event 집계 | 정비 건수·시간 | 목록 합계와 일치 |
| FEAT-OP-004 | 정비 목록 | event와 Asset 결합 | 정비 이력 | 원천 필드 보존 |
| FEAT-OP-005 | 운영 영향 | 확인 가능한 자산·작업 관계만 집계 | 관련 건수 | 비용·인과 임의 생성 금지 |
| FEAT-OP-006 | 상세 이동 | 자산 선택 | Objects 상세 | `asset_id` 유지 |

Decision·Note는 이미 권한 기반 저장과 Activity 감사 이력으로 구현돼 있다. 이를
제외하려면 API·UI·권한·테스트 변경 항목으로 결정한다.

Closed-loop Action 버튼은 Frontend가 role/state를 조합해 계산하지 않고 Backend가 반환하는
`available_actions`를 사용한다. `process_engineer`와 `maintenance_technician`의 현장 책임도 별도 역할로
유지한다.

## 6. Executive Report

현행 구현: 선택 Event 단위 `ReportRequest`와 역할별 grounded report.

현재 Operations는 Event Evidence 기반 deterministic 기준선을 먼저 완성한다. 아래 표의
기간·필터 집계 기반 `ReportInput`/`ReportOutput`은 Target이며 추가 집계 API가
필요하면 후속 처리한다.

| ID | 기능 | 입력/처리 | 출력 | 오류·완료 기준 |
|---|---|---|---|---|
| FEAT-EX-001 | 보고서 생성 | 기간·필터·기준시각 검증 | ReportOutput | 입력 계약 검증 통과 |
| FEAT-EX-002 | 핵심 지표 | Overview와 동일 집계 사용 | KPI | 화면 간 수치 일치 |
| FEAT-EX-003 | 위험 설비 | 입력 Top N을 구조화 문장으로 변환 | 설비별 요약 | 입력 밖 설비 없음 |
| FEAT-EX-004 | 근거 추적 | 문장과 evidence reference 연결 | 근거 링크 | 모든 핵심 문장 역추적 가능 |
| FEAT-EX-005 | 실패 대체 | LLM→deterministic→template | 동일 ReportOutput | 생성 방식 표시 |
| FEAT-EX-006 | 한계 표시 | warnings·provenance 보존 | 한계·출처 | 항상 표시 |

## 7. 공통 오류

| 상황 | 처리 |
|---|---|
| 잘못된 필터·기간 | 400과 필드별 메시지 |
| 자산 없음 | 404 |
| snapshot 불일치 | 409 |
| 계약 검증 실패 | 422 |
| Canonical 사용 불가 | 503 또는 명시적 fallback |
| 결과 없음 | 빈 목록과 0 집계; 정상 데이터 생성 금지 |

## 8. 완료 조건

- 네 화면이 접근 가능하고 같은 자산·기준시각·필터를 사용한다.
- 원천, Artifact, 파생값과 fallback이 구분된다.
- 평가 truth와 자동 설비 제어가 노출되지 않는다.
- 각 기능 ID가 API·스키마·테스트에 연결된다.

