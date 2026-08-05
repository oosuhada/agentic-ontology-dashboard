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

## 3. FastAPI·Flask 동일 조건 비교

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

> FastAPI와 Flask로 동일한 `/health` API를 각각 구현해 비교했습니다. Flask는
> 단일 endpoint 구현과 인프로세스 응답이 더 가벼웠지만, FastAPI는 별도
> extension 없이 응답 schema 검증과 OpenAPI 문서를 함께 생성했습니다. 이후
> 데이터셋과 예측 결과 API 확장까지 고려했을 때 결과물 완성도가 더 높아
> FastAPI를 최종 선택했습니다.

## 4. 자동 테스트

```text
6 passed
```

검증 범위:

- FastAPI·Flask `/health` HTTP 200
- 양쪽 JSON payload 완전 일치
- FastAPI OpenAPI response schema 생성
- Flask 기본 구성에서 `/openapi.json` 404
- 비교 rubric에서 FastAPI 선정
- Canonical package path 탐색
- JSONL timeline 선택 설비 필터링

## 5. 로컬 확인 주소

기존 제품 서버와 충돌하지 않도록 전용 포트를 사용했다.

| 대상 | 주소 |
|---|---|
| Streamlit + Plotly | `http://127.0.0.1:8511` |
| FastAPI health | `http://127.0.0.1:8111/health` |
| FastAPI OpenAPI | `http://127.0.0.1:8111/docs` |
| Flask health | `http://127.0.0.1:5111/health` |

