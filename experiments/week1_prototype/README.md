# Week 1 — Streamlit·Plotly / FastAPI·Flask 비교 프로토타입

이 디렉터리는 기존 React/FastAPI 제품 코드와 충돌하지 않도록 분리한 실험용
프로토타입이다. 두 가지 작업을 같은 데이터 계약으로 검증한다.

1. `Predictive Maintenance Canonical V3.1` 데이터를 Streamlit에서 읽어 Plotly
   차트로 렌더링한다.
2. FastAPI와 Flask에 동일한 `GET /health` 계약을 구현한 기준선 실험과 함께,
   현재 Ontology Dashboard MVP의 전체 OpenAPI 표면을 수집해 162개 경로·172개
   HTTP 작업의 개발 구조·계약 자동화·검증 안정성·경량성을 비교한다.

## 디렉터리 구성

```text
experiments/week1_prototype/
├── data_access.py
├── streamlit_app.py
├── framework_comparison/
│   ├── contracts.py
│   ├── fastapi_app.py
│   ├── flask_app.py
│   └── compare.py
├── tests/
├── requirements.txt
├── run_streamlit.sh
└── run_framework_comparison.sh
```

## 설치

기존 프로젝트 가상환경을 변경하지 않고 별도 환경을 만든다.

```bash
python3 -m venv .venv-week1
.venv-week1/bin/python -m pip install -r experiments/week1_prototype/requirements.txt
```

## Streamlit + Plotly 실행

Canonical V3.1 패키지 경로를 환경 변수로 지정한다.

```bash
export CANONICAL_V3_1_ROOT="/absolute/path/to/predictive_maintenance_canonical_v3.1"
bash experiments/week1_prototype/run_streamlit.sh
```

기본 주소는 `http://127.0.0.1:8511`이다.

대시보드는 다음 Plotly 시각화를 제공한다.

1. 최신 설비 위험도 순위 — horizontal bar
2. 선택 설비 고장 확률 시계열 — line
3. 상태 등급 구성 — donut
4. 실제 고장 유형 분포 — bar
5. CNC 회전 속도·토크 물리 관계 — scatter
6. CNC 공기·공정 온도 추세 — multi-line
7. 압축기 압력·진동 추세 — dual-axis line
8. 예측 설명 변수 기여도 — diverging horizontal bar

## FastAPI·Flask 비교 실행

공개 비교 화면:

```text
https://fastapi-flask.oosu.dev
```

공개 화면은 두 비교 층을 구분한다.

1. 제조 Dashboard 대표 API 1개를 FastAPI와 Flask에 동일하게 실제 구현한
   기능·성능 대칭 비교
2. FastAPI 전체 제품 162개 OpenAPI 경로·172개 HTTP 작업의 구현 현황과
   Flask route mirror 범위 분석

- 실제 Ontology Dashboard 162경로 Swagger: `https://dashboard.oosu.dev/docs`
- 비교 화면 자체 Swagger: `https://fastapi-flask.oosu.dev/docs`

- FastAPI 실제 제품 handler: 172개 작업
- 인증 전·후 전수 runtime probe: 각 172개 작업
- 처리되지 않은 HTTP 500: 0건
- SQLite 격리 환경에서 PostgreSQL 전용 Runtime의 명시적 503: 10건
- FastAPI 자동 요청·파라미터 검증 대상: 147개 작업
- FastAPI JSON 성공 응답 Schema와 런타임 검증: 168개 작업
- 필드 수준 JSON 성공 응답 Schema: 167개 작업
- binary·SSE 성공 응답 계약: 2개 작업
- 명시적 no-content 성공 계약: 2개 작업
- 전체 성공 응답 계약: 172개 작업
- Flask route mirror: 172개 작업 등록
- Flask 전체 제품 business handler: 0개
- Flask 대표 제조 Dashboard business handler: 1개 실제 구현

Flask route mirror는 bare Flask의 기본 제공 범위와 라우팅 가능성을 확인하기 위한
비교 계층이며, Ontology Dashboard의 전체 business logic이 Flask에도 구현됐다고
주장하지 않는다.

### 동일 제조 Dashboard API 실제 비교

`/app/projects/manufacturing-demo-project` 첫 화면을 대표하는 다음 API를 양쪽에
동일하게 구현했다.

```text
GET /benchmark/manufacturing-dashboard?risk_threshold=0.0&limit=8
```

- 같은 GS-001~GS-008 제품 fixture
- 같은 product risk snapshot
- 같은 집계 함수와 Pydantic 응답 모델
- 위험 이벤트 8개, 센서 시계열 31개
- 정상 JSON 응답 완전 일치
- 잘못된 `limit=0` 요청은 양쪽 모두 422
- FastAPI adapter 15 LOC
- Flask adapter와 수동 query parser 33 LOC

실제 별도 HTTP 프로세스를 실행하고, 프레임워크 실행 순서를 번갈아가며 순차
300회와 동시성 10의 300회를 각각 3라운드 측정했다. 아래 값은 라운드 중앙값이다.

| Framework | 순차 p50 | 순차 p95 | 순차 RPS | 동시 p50 | 동시 p95 | 동시 RPS | 오류율 | 성능 점수 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FastAPI | 4.4392ms | 6.8936ms | 207.34 | 13.3380ms | 28.1913ms | 626.24 | 0% | 4.78/5 |
| Flask | 4.5172ms | 6.3509ms | 197.14 | 12.2540ms | 27.0817ms | 662.36 | 0% | 4.94/5 |

FastAPI는 순차 p50과 순차 처리량이 근소하게 높았고, Flask는 순차 p95와 동시
p50·p95·처리량에서 앞섰다. 네 성능 지표를 동일 비중으로 정규화한 결과 Flask가
성능 항목에서 근소하게 높은 점수를 받았다. 이 값은 로컬 Mac loopback과 각
프레임워크의 로컬 server stack을 포함하며 운영 환경 성능을 보장하지 않는다.

### 가중 평가 결과

이번 평가는 모든 프로젝트에 적용되는 보편 점수가 아니라 현재 MVP의 우선순위를
반영한 의사결정 점수다.

| 평가 요소 | 가중치 | FastAPI | Flask |
|---|---:|---:|---:|
| 개발 완성도와 구현 생산성 | 25% | 5/5 | 3/5 |
| API 계약과 문서 자동화 | 25% | 5/5 | 2/5 |
| 요청·응답 검증과 오류 안전성 | 25% | 5/5 | 4/5 |
| 대표 업무 API 성능과 경량성 | 25% | 4.78/5 | 4.94/5 |
| **가중 합계** | **100%** | **98.9점** | **69.7점** |

Flask는 실제 대표 업무 API 성능에서 근소하게 앞섰다. FastAPI는 동일 기능의
adapter 코드량, 계약 자동화와 검증 안정성에서 앞섰다. 네 항목은 각각 25%로
동일하게 계산했고, 성능 우위를 Flask에 반영한 뒤에도 FastAPI가 최종 선택됐다.
이 결론은 기존 코드를 옮기는 비용이 아니라 새 제품을 구축할 때의 개발 방식과
기본 제공 기능을 기준으로 한 판단이다.

```bash
bash experiments/week1_prototype/run_framework_comparison.sh
bash experiments/week1_prototype/run_representative_dashboard_benchmark.sh
bash experiments/week1_prototype/run_full_surface_comparison.sh
```

전체 비교는 다음 세 층으로 나뉜다.

### 1. 동일 제조 Dashboard API

- FastAPI·Flask에 같은 업무 API 실제 구현
- 동일 JSON 응답과 오류 응답 검증
- 별도 로컬 HTTP 프로세스 성능 측정
- adapter 코드량과 검증 방식 비교

### 2. 동일 `/health` 기준선

동일한 `/health` 응답을 대상으로 다음 항목을 비교한다.

- HTTP 200 및 JSON 계약 일치
- 자동 OpenAPI 문서 제공 여부
- 응답 스키마 명시·검증 여부
- 테스트 클라이언트 사용 가능 여부
- 최소 구현 코드량
- 인프로세스 요청 지연시간 참고치

지연시간은 로컬 개발 환경의 참고값이며 운영 성능 결론으로 사용하지 않는다.
최종 선정 근거는 이 단일 endpoint가 아니라 아래 전체 API 표면 결과다.

### 3. 전체 162개 경로·172개 작업

- FastAPI OpenAPI에서 모든 path·method·request body·parameter·response schema 수집
- 비인증 상태에서 172개 작업의 인증·검증 경계 전수 probe
- Tenant Admin 인증 상태에서 172개 작업의 handler·권한·Schema 경계 전수 probe
- 168개 JSON 응답에 Pydantic 런타임 응답 검증 적용
- binary·SSE 2개와 no-content 2개를 JSON과 분리해 문서화
- bare Flask에 172개 route mirror를 생성해 route 등록 parity 검증
- FastAPI 자동 계약과 Flask 수동 업무 구성 필요량 비교
- 프레임워크별 테스트 결과·장점·단점과 5점 척도 가중 평가

공개 JSON:

- `/full-comparison.json`: 전체 API 표면 결과
- `/representative-benchmark.json`: 대표 제조 Dashboard 실제 성능 결과
- `/comparison.json`: 대표 API, `/health` 기준선과 전체 API 표면 통합 결과

## 테스트

```bash
PYTHONPATH=experiments/week1_prototype \
  .venv-week1/bin/python -m pytest experiments/week1_prototype/tests -q
```

## 실험 범위

- 기존 `api/`, `web/`, 데이터셋 생성기 코드는 수정하지 않는다.
- Flask는 비교용 최소 구현이며 제품 백엔드로 병행 운영하지 않는다.
- Canonical V3.1 원본 파일은 읽기 전용으로 사용한다.

## Canonical V3.1 데이터셋 설명 페이지

데이터셋 변경 배경, Azure PdM 분석 결과, Canonical V3.1 구조, 검증 결과와
남은 제약을 설명하는 독립 HTML은 다음 경로에 있습니다.

- 소스: `experiments/week1_prototype/canonical_v3_1_story/index.html`
- 공개 주소: <https://canonical-v3-1.oosu.dev>

