# Week 1 프로토타입 구현·검증 보고

## 1. 격리 작업 방식

- 원본 프로젝트: `mvp-프로젝트2`
- 기준 커밋: `05a4d495dc3811e63cef35299111b2bbf49baf6f`
- 격리 브랜치: `experiment/week1-streamlit-plotly-framework-comparison`
- 방식: DevSpace managed Git worktree
- 기존 원본 checkout의 미커밋 변경은 복사하거나 수정하지 않았다.
- 기존 `api/`, `web/`, Canonical V3.1 생성기에는 변경을 가하지 않았다.

## 2. Streamlit·Plotly 구현

Canonical V3.1 패키지를 읽기 전용으로 연결하고, Streamlit 화면에 Plotly
시각화를 추가했다.

### 구현한 차트

| # | 차트 | Plotly 표현 | 목적 |
|---:|---|---|---|
| 1 | 최신 설비 위험도 순위 | Horizontal bar | 고위험 압축기·CNC 우선순위 확인 |
| 2 | 선택 설비 고장 확률 Replay | Line | 시간에 따른 위험 변화 확인 |
| 3 | 최신 상태 등급 구성 | Donut | normal·attention·warning·critical 비중 확인 |
| 4 | 실제 고장 유형 분포 | Horizontal bar | Ground truth 고장 모드 구성 확인 |
| 5 | CNC RPM–토크 관계 | Scatter | AI4I 물리 관계 및 제품 유형 비교 |
| 6 | CNC 공기·공정 온도 | Multi-line | 두 온도 신호의 결합 관계 확인 |
| 7 | 압축기 압력·진동 | Dual-axis line | Azure PdM 계열 센서 추세 비교 |
| 8 | 모델 설명 변수 기여도 | Diverging bar | 위험 상승·하락 요인 확인 |
| 9 | 압축기 상대 진동–압력 | Scatter | 압축기 센서 관계 탐색 |

선택한 설비 유형에 따라 CNC 또는 압축기 전용 차트가 교체된다. 따라서 한 화면
실행에서는 Plotly 차트 7개가 렌더링되고, 전체 구현 유형은 9개이다.

### 데이터 처리

- `asset_master.csv`, `prediction_snapshot.jsonl`, failure truth 파일은 전체 로드
- 45MB 센서 CSV는 `chunksize` 기반으로 선택 설비만 필터링
- 45MB prediction timeline JSONL은 줄 단위로 읽어 선택 설비만 추출
- 긴 시계열은 최대 2,000~2,500개 포인트로 down-sampling
- Streamlit `cache_data`로 반복 로드 최소화
- Canonical 원본은 수정하지 않음

### Streamlit 검증 결과

`streamlit.testing.v1.AppTest`로 실제 Canonical V3.1 경로를 연결해 확인했다.

```text
exceptions: 0
title: Canonical V3.1 · Streamlit + Plotly Lab
assets: 100
prediction snapshots: 100
failure truth events: 76
metrics: 5
tabs: 4
plotly_chart elements: 7
```

Streamlit runtime health도 `HTTP 200`, 본문 `ok`로 확인했다.

## 3. FastAPI·Flask 전체 MVP API 표면 비교

초기에는 두 프레임워크에 동일한 `/health` 한 개를 구현해 기본 계약 기능을
비교했다. 이후 현재 MVP 구현량을 반영하기 위해 Adaptive Modeling 최신
브랜치를 병합하고, FastAPI OpenAPI 전체를 기준으로 비교 범위를 확장했다.

### 전체 전수 범위

```text
OpenAPI paths: 162
HTTP operations: 172
GET: 93
POST: 66
PUT: 7
PATCH: 4
DELETE: 2
```

주요 범주는 Modeling 38, Dashboard 18, Admin 13, Predictive Maintenance
Runtime 13, Ontology 12, Dataset 11, Manufacturing 11, Analysis 10,
Authentication 10개 작업이다.

### FastAPI 실제 Runtime 전수 probe

비인증 상태와 Tenant Admin 인증 상태에서 172개 작업을 각각 호출했다. 쓰기
작업은 격리 SQLite DB에 contract probe payload를 보내 요청 Schema·CSRF·권한
계약을 확인했다.

```text
비인증: 200 3건 · 401 165건 · 403 2건 · 422 2건
인증:   200 34건 · 403 36건 · 404 9건 · 422 83건 · 503 10건
처리되지 않은 HTTP 500: 0건
```

인증 probe의 503 10건은 오류 은폐가 아니라 SQLite 격리 환경에서 PostgreSQL
전용 Canonical V3.1 Runtime이 명시적으로 반환한 degraded contract다.

### 전체 표면의 계약 자동화 비교

| 항목 | FastAPI 실제 앱 | bare Flask route mirror |
|---|---:|---:|
| 등록 HTTP 작업 | 172 | 172 |
| 실제 business handler | 172 | 0 |
| 자동 OpenAPI 작업 | 172 | 0 |
| 자동 요청·파라미터 검증 대상 | 147 | 0 |
| JSON 성공 응답 Schema·런타임 검증 | 168 | 0 |
| 필드 수준 JSON 성공 응답 Schema | 167 | 0 |
| binary·SSE 성공 응답 계약 | 2 | 0 |
| 명시적 no-content 성공 계약 | 2 | 0 |
| 전체 성공 응답 계약 | 172 | 0 |
| 수동 business port 필요 | 0 | 172 |

Flask route mirror는 172개 경로가 Flask에서도 등록 가능한지와 이식 대상 규모를
측정한다. 제품 business logic을 FastAPI로 proxy하거나 Flask 구현으로 가장하지
않는다. 동일 기능의 Flask 제품을 만들려면 172개 handler와 validation·문서화
계약을 별도로 이식해야 한다.

### `/health` 기준선 마이크로 비교

두 프레임워크에 아래와 같은 계약을 각각 구현했다.

```http
GET /health
```

```json
{
  "status": "ok",
  "service": "ontology-dashboard-week1",
  "mode": "framework-comparison"
}
```

### 비교 조건

- 동일 URL과 JSON payload
- 각 프레임워크의 기본 test client 사용
- 자동 OpenAPI 제공 여부 확인
- 응답 schema 선언 여부 확인
- 최소 endpoint 구현 코드량 비교
- 500회 인프로세스 요청 지연시간 측정

### 실제 결과

| Framework | `/health` | Payload | Auto OpenAPI | Response schema | Endpoint LOC | p50 ms* | p95 ms* | 계약 점수 |
|---|---:|---|---|---|---:|---:|---:|---:|
| FastAPI | 200 | 일치 | 제공 | 선언·검증 | 3 | 0.7603 | 1.7285 | 5/5 |
| Flask | 200 | 일치 | 기본 미제공 | 수동 처리 | 3 | 0.0766 | 0.1235 | 3/5 |

\* 지연시간은 TestClient 기반 인프로세스 참고값이며, 운영 서버 성능 비교가 아니다.

### 해석

Flask는 단일 `/health` 요청의 인프로세스 지연시간이 더 짧고 최소 구현도
간결했다. 따라서 이번 실험으로 **FastAPI가 Flask보다 실행 속도가 빠르다**고
결론 내릴 수 없다.

반면 FastAPI는 별도 extension 없이 다음 결과물을 동시에 생성했다.

- Pydantic 기반 `HealthResponse` 응답 계약
- 반환값 schema 검증
- `/openapi.json` 자동 생성
- Swagger UI에 사용할 수 있는 API 명세
- 이후 데이터셋·예측 결과 endpoint로 확장 가능한 typed router 구조

Flask에서도 extension과 별도 schema 코드를 추가하면 같은 기능을 구현할 수
있지만, 동일한 최소 실험 범위에서는 제공되지 않았다. 따라서 **속도가 아니라
계약·문서·검증·확장성을 포함한 결과물 완성도**를 기준으로 FastAPI를
선정했다.

### 발표·보고용 선정 문장

> 초기에는 FastAPI와 Flask로 동일한 `/health` API를 구현해 기준선을
> 비교했습니다. 이후 현재 MVP의 OpenAPI 전체를 기준으로 162개 경로·172개
> HTTP 작업을 전수 수집하고, 인증 전·후 runtime probe와 Flask route mirror를
> 실행했습니다. FastAPI는 172개 실제 business handler, 자동 OpenAPI, 147개
> 요청 검증 대상과 168개 JSON 응답 런타임 검증을 제공했고, binary·SSE 2개와
> no-content 2개도 별도 성공 계약으로 문서화했습니다. 처리되지 않은 HTTP
> 500은 0건이었습니다.
> 반면 bare Flask는 172개 route를 등록할 수 있었지만 실제 handler와 계약을
> 모두 별도로 이식해야 했기 때문에 전체 MVP 결과물 기준으로 FastAPI를 최종
> 선택했습니다.

## 4. 자동 테스트

```text
전체 백엔드: 259 passed, 2 skipped
Week 1 실험: 11 passed
```

검증 범위:

- FastAPI·Flask `/health` HTTP 200
- 양쪽 JSON payload 완전 일치
- FastAPI OpenAPI response schema 생성
- Flask 기본 구성에서 `/openapi.json` 404
- 162개 OpenAPI 경로·172개 HTTP 작업 inventory
- 172개 FastAPI 작업 비인증 runtime probe
- 172개 FastAPI 작업 Tenant Admin 인증 runtime probe
- 처리되지 않은 HTTP 500 0건
- JSON 성공 응답 빈 Schema 0건·문자열 오표시 Schema 0건
- 168개 JSON 성공 응답 런타임 검증
- Flask 172개 route mirror 등록 parity
- 전체 API 표면 기준 FastAPI 선정
- Canonical package path 탐색
- JSONL timeline 선택 설비 필터링
- DevSpace worktree에서도 Canonical V2/V3.1 외부 패키지 경로 복원

## 5. 로컬 확인 주소

기존 제품 서버와 충돌하지 않도록 전용 포트를 사용했다.

| 대상 | 주소 |
|---|---|
| Streamlit + Plotly | `http://127.0.0.1:8511` |
| FastAPI health | `http://127.0.0.1:8111/health` |
| FastAPI OpenAPI | `http://127.0.0.1:8111/docs` |
| 전체 API 비교 JSON | `http://127.0.0.1:8111/full-comparison.json` |
| Flask health | `http://127.0.0.1:5111/health` |

