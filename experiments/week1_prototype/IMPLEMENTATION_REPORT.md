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
| 전체 제품 business handler | 172 | 0 |
| 대표 제조 Dashboard business handler | 1 | 1 |
| 자동 OpenAPI 작업 | 172 | 0 |
| 자동 요청·파라미터 검증 대상 | 147 | 0 |
| JSON 성공 응답 Schema·런타임 검증 | 168 | 0 |
| 필드 수준 JSON 성공 응답 Schema | 167 | 0 |
| binary·SSE 성공 응답 계약 | 2 | 0 |
| 명시적 no-content 성공 계약 | 2 | 0 |
| 전체 성공 응답 계약 | 172 | 0 |
| 수동 business port 필요 | 0 | 172 |

Flask route mirror는 172개 경로가 bare Flask에서도 등록 가능한지와 기본 제공
범위를 확인한다. 제품 business logic을 FastAPI로 proxy하거나 Flask 구현으로
가장하지 않는다. 동일 수준의 Flask 제품을 새로 구축하려면 handler 구조,
validation, OpenAPI와 문서화 규칙을 별도로 선택하고 연결해야 한다.

### 동일 제조 Dashboard API 실제 대칭 비교

`/app/projects/manufacturing-demo-project` 첫 화면을 대표하는 API를 FastAPI와
Flask에 동일하게 구현했다.

```http
GET /benchmark/manufacturing-dashboard?risk_threshold=0.0&limit=8
```

두 adapter는 GS-001~GS-008 fixture, product risk snapshot, 집계 함수와 Pydantic
응답 모델을 공유한다. 정상 응답은 위험 이벤트 8개와 센서 시계열 31개를
포함하며 파싱된 JSON과 canonical SHA-256이 완전히 일치했다. `limit=0`은 양쪽
모두 422를 반환했다.

| 항목 | FastAPI | Flask |
|---|---:|---:|
| Adapter 코드량 | 15 LOC | 33 LOC |
| Query 검증 | `Query` constraint 자동 적용 | 수동 parser |
| 응답 검증 | Pydantic `response_model` | 공유 Pydantic payload 후 `jsonify` |
| 자동 OpenAPI | 제공 | 기본 미제공 |

각 서버를 별도 프로세스로 실행하고 실행 순서를 번갈아가며 순차 300회와
동시성 10의 300회를 각각 3라운드 측정했다. 아래 값은 라운드 중앙값이다.

| Framework | 순차 p50 | 순차 p95 | 순차 RPS | 동시 p50 | 동시 p95 | 동시 p99 | 동시 RPS | 오류율 | 성능 점수 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FastAPI | 4.4392ms | 6.8936ms | 207.34 | 13.3380ms | 28.1913ms | 32.3406ms | 626.24 | 0% | 4.78/5 |
| Flask | 4.5172ms | 6.3509ms | 197.14 | 12.2540ms | 27.0817ms | 33.9609ms | 662.36 | 0% | 4.94/5 |

FastAPI는 순차 p50과 순차 처리량이 근소하게 높았고, Flask는 순차 p95와 동시
p50·p95·처리량에서 앞섰다. 순차 p95·처리량과 동시 p95·처리량을 동일 비중으로
정규화한 결과 Flask가 성능 항목에서 근소하게 높은 점수를 받았다. 이 측정은
로컬 Mac loopback과 Uvicorn·Werkzeug server stack을 포함하며 운영 환경
벤치마크가 아니다.

### 동일 가중치 평가표

이번 점수는 프레임워크의 절대 우열이 아니라 새 Ontology Dashboard MVP를
구축할 때의 개발 방식과 기본 제공 기능을 비교한 결과다. 네 항목을 각각 25%로
동일하게 계산했다.

| 평가 요소 | 가중치 | FastAPI 평가 | Flask 평가 |
|---|---:|---|---|
| 개발 완성도와 구현 생산성 | 25% | **5/5 · 25점 반영**<br>typed router·Pydantic·의존성 주입으로 큰 API를 일관되게 구성 | **3/5 · 15점 반영**<br>시작은 단순하지만 큰 API의 구조와 확장 도구를 별도로 조합해야 함 |
| API 계약과 문서 자동화 | 25% | **5/5 · 25점 반영**<br>OpenAPI 172개와 전체 성공 응답 계약 자동 생성 | **2/5 · 10점 반영**<br>확장 도구로 구현 가능하지만 bare Flask 기본 구성에는 없음 |
| 요청·응답 검증과 오류 안전성 | 25% | **5/5 · 25점 반영**<br>대표 API 자동 query·응답 검증, 전체 요청 검증 147개·응답 검증 168개 | **4/5 · 20점 반영**<br>대표 API는 같은 422를 반환하지만 수동 parser가 필요 |
| 대표 업무 API 성능과 경량성 | 25% | **4.78/5 · 23.9점 반영**<br>순차 처리량 우세 | **4.94/5 · 24.7점 반영**<br>순차 p95와 동시 p95·처리량 우세 |
| **가중 합계** | **100%** | **98.9점 · 평균 4.95/5** | **69.7점 · 평균 3.49/5** |

Flask는 대표 업무 API 성능에서 근소하게 우세했다. 반면 FastAPI는 동일
adapter 코드량, 계약 자동화와 검증에서 앞섰다. Flask의 실제 성능 우위를
그대로 점수에 반영한 뒤에도 FastAPI가 98.9점, Flask가 69.7점이었고, 새 제품
구축 기준으로 FastAPI를 최종 선택했다.

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

| Framework | `/health` | Payload | Auto OpenAPI | Response schema | Endpoint LOC | p50 ms* | p95 ms* | 종합 평균* |
|---|---:|---|---|---|---:|---:|---:|---:|
| FastAPI | 200 | 일치 | 제공 | 선언·검증 | 3 | 0.7603 | 1.7285 | 4.95/5 |
| Flask | 200 | 일치 | 기본 미제공 | 수동 처리 | 3 | 0.0766 | 0.1235 | 3.49/5 |

\* 지연시간은 TestClient 기반 인프로세스 참고값이며, 운영 서버 성능 비교가 아니다.
종합 평균은 위 네 평가 요소 점수의 동일 가중치 산술평균이다.

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
있다. Flask의 단순 응답 경량성은 실제 장점으로 평가했다. 다만 네 항목을 동일
가중치로 계산해도 FastAPI가 개발 생산성·계약 자동화·검증 안정성에서 더 높은
점수를 받아 최종 선택됐다.

### 발표·보고용 선정 문장

> 초기에는 FastAPI와 Flask로 동일한 `/health` API를 구현해 기준선을
> 비교했습니다. 이후 현재 MVP의 OpenAPI 전체를 기준으로 162개 경로·172개
> HTTP 작업을 전수 수집하고, 인증 전·후 runtime probe와 Flask route mirror를
> 실행했습니다. FastAPI는 172개 실제 business handler, 자동 OpenAPI, 147개
> 요청 검증 대상과 168개 JSON 응답 런타임 검증을 제공했고, binary·SSE 2개와
> no-content 2개도 별도 성공 계약으로 문서화했습니다. 처리되지 않은 HTTP
> 500은 0건이었습니다.
> 추가로 제조 Dashboard 대표 API를 FastAPI와 Flask에 동일하게 구현하고,
> 순차·동시 HTTP 성능을 3라운드 측정했습니다. 응답과 오류 계약은 일치했고,
> 성능 점수는 FastAPI 4.78점, Flask 4.94점으로 Flask가 근소하게 앞섰습니다.
> 개발 생산성·계약 자동화·검증 안정성·대표 API 성능을 각각 25%로 계산한
> 결과는 FastAPI 98.9점, Flask 69.7점이었습니다. Flask의 성능 우위를 그대로
> 반영한 뒤에도 계약과 검증 자동화에서 FastAPI가 앞서 최종 선택했습니다.

## 4. 자동 테스트

```text
전체 백엔드: 259 passed, 2 skipped
Week 1 실험: 14 passed
```

검증 범위:

- FastAPI·Flask `/health` HTTP 200
- 양쪽 JSON payload 완전 일치
- FastAPI·Flask 대표 제조 Dashboard 정상 JSON 완전 일치
- 대표 API 잘못된 query 양쪽 422
- 실제 HTTP 3라운드 성능 snapshot 계약
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

