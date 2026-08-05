# Week 1 — Streamlit·Plotly / FastAPI·Flask 비교 프로토타입

이 디렉터리는 기존 React/FastAPI 제품 코드와 충돌하지 않도록 분리한 실험용
프로토타입이다. 두 가지 작업을 같은 데이터 계약으로 검증한다.

1. `Predictive Maintenance Canonical V3.1` 데이터를 Streamlit에서 읽어 Plotly
   차트로 렌더링한다.
2. FastAPI와 Flask에 동일한 `GET /health` 계약을 구현한 기준선 실험과 함께,
   현재 Ontology Dashboard MVP의 전체 OpenAPI 표면을 수집해 162개 경로·172개
   HTTP 작업의 계약·검증·이식 비용을 비교한다.

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

공개 화면에서 FastAPI·Flask의 동일 `/health` 기준선뿐 아니라 현재 MVP의
162개 OpenAPI 경로·172개 HTTP 작업 전수 비교 결과를 확인할 수 있다.

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
- Flask 실제 business handler: 0개 — 전체 이식 시 172개를 별도 구현해야 함

Flask route mirror는 라우팅 가능성과 수동 이식량을 측정하기 위한 비교 계층이며,
Ontology Dashboard의 business logic이 Flask로도 구현됐다고 주장하지 않는다.

```bash
bash experiments/week1_prototype/run_framework_comparison.sh
bash experiments/week1_prototype/run_full_surface_comparison.sh
```

전체 비교는 다음 두 층으로 나뉜다.

### 1. 동일 `/health` 기준선

동일한 `/health` 응답을 대상으로 다음 항목을 비교한다.

- HTTP 200 및 JSON 계약 일치
- 자동 OpenAPI 문서 제공 여부
- 응답 스키마 명시·검증 여부
- 테스트 클라이언트 사용 가능 여부
- 최소 구현 코드량
- 인프로세스 요청 지연시간 참고치

지연시간은 로컬 개발 환경의 참고값이며 운영 성능 결론으로 사용하지 않는다.
최종 선정 근거는 이 단일 endpoint가 아니라 아래 전체 API 표면 결과다.

### 2. 전체 162개 경로·172개 작업

- FastAPI OpenAPI에서 모든 path·method·request body·parameter·response schema 수집
- 비인증 상태에서 172개 작업의 인증·검증 경계 전수 probe
- Tenant Admin 인증 상태에서 172개 작업의 handler·권한·Schema 경계 전수 probe
- 168개 JSON 응답에 Pydantic 런타임 응답 검증 적용
- binary·SSE 2개와 no-content 2개를 JSON과 분리해 문서화
- bare Flask에 172개 route mirror를 생성해 route 등록 parity 검증
- FastAPI 자동 계약과 Flask 수동 port 필요량 비교

공개 JSON:

- `/full-comparison.json`: 전체 API 표면 결과
- `/comparison.json`: `/health` 기준선과 전체 API 표면 통합 결과

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

