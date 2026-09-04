# Operations 설계 명세서

## 1. 목표

Canonical V3.1과 Result Artifact를 사용해 매니저와 엔지니어가 위험 설비를
찾고, 근거와 생산·정비 현황을 확인하고, 같은 데이터로 Executive Report를 보는
조회 중심 Operations를 구성한다.

## 1.1 현재 저장소와 실행 기준

- 제품·계약 문서: `oosuhada/agentic-ontology-dashboard`
- 현행 실행 코드: `oosuhada/agentic-ontology-dashboard`의 `main`
- 배포 기준: Mac mini production runtime

현행 역할·API·Operations·Report 계약은
[현행 Operations 구현 계약 기준선](./current-operations-implementation-baseline.md)을 따른다.

## 2. 범위

- 화면: Overview, Objects, Operations, Executive Report
- 데이터: Canonical V3.1 원천 6종
- 예측: `result-artifact-v1.0`
- 보고서: 근거 기반 LLM과 deterministic/template fallback
- 현행 포함: Event Queue, Decision·Note 저장, Activity 감사 이력
- 제외: Analysis, Admin, 모델 재학습, 자동 정지·발주·생산계획 변경, truth 노출

## 3. 구성

```text
Canonical V3.1 files
        ↓
Data/Prediction pipeline
        ↓
Result Artifact
        ↓
FastAPI query/report API
        ↓
React Overview / Objects / Operations / Executive Report
```

원천 CSV, 파생 Artifact와 애플리케이션 저장값을 별도 책임으로 유지한다.

## 4. 데이터 흐름

1. manifest와 checksum을 검증한다.
2. Asset·Observation·Production·Maintenance를 적재하거나 읽는다.
3. 모델이 자산별 최신 Result Artifact를 생성한다.
4. API는 같은 snapshot에서 Asset와 Artifact를 결합한다.
5. 화면은 API 응답을 ViewModel로 정규화한다.
6. Report API는 화면과 동일한 집계와 Artifact를 입력으로 사용한다.
7. 생성 결과의 근거와 provenance를 보존한다.

## 5. 화면 흐름

```text
Overview 위험 현황
→ Objects 설비·센서·Top-3 근거
→ Operations 생산·정비 연관 현황
→ Executive Report 동일 집계 요약
```

화면 이동 시 `asset_id`, 기간과 필터 조건을 유지한다.

## 6. 책임 분리

| 영역 | 책임 |
|---|---|
| gen_data | raw/simulation/synthetic sensor data, Canonical V3.1 물리·생성 기준, source/reference fixture, 원천 생성 재현성 |
| Generator | Protocol Extraction/Parsing 및 승인 Mapping 적용, Preprocessing Plan, Feature Schema/Recipe 기반 Feature Dataset Bundle, Model Training 및 versioned Model Artifact 발행, source-to-artifact provenance |
| Backend Diagnosis·Query API | Prediction Result 검증·승격, Product Result Artifact/Evidence, Prediction 조회, 목록·상세·집계 API 및 runtime provenance |
| Frontend | 역할별 화면, ViewModel, 상태·이동·접근성 |
| Report API | 리포트 endpoint, ReportInput/Output, deterministic·LLM·template, 근거 추적 |
| Documentation | 요구사항·스키마·기능·API·보고서·추적성 |

## 7. 구현 순서

1. 시스템 계약 체크리스트 결정
2. 스키마와 API 경로 확정
3. 목록·상세·집계 API 구현
4. Overview·Objects 연결
5. Operations 연결
6. Report API와 Executive Report 연결
7. 오류·stale·fallback 처리
8. 추적성 테스트와 데모 검증

## 8. 안전·신뢰 원칙

- 예측을 실제 고장으로 단정하지 않는다.
- factor와 topology를 확정 원인으로 표현하지 않는다.
- 권고와 사람의 판단·실행을 분리한다.
- 데이터 없음과 오류에서 임의 값을 만들지 않는다.
- evaluation truth를 운영 화면/API/LLM에 전달하지 않는다.
- 버전, 기준시각, source와 warning을 노출한다.

## 9. 완료 기준

- 네 화면이 동일 자산·snapshot·필터를 사용한다.
- API와 LLM이 같은 Result Artifact 계약을 사용한다.
- 집계 불변식과 화면 간 수치가 일치한다.
- LLM 실패 시에도 구조화 보고서를 표시한다.
- 요구사항부터 테스트까지 추적 가능하다.
- 미합의·후속 기능은 명확히 표시된다.
