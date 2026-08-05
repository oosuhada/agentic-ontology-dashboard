# Week 1 — Streamlit·Plotly / FastAPI·Flask 비교 프로토타입

이 디렉터리는 기존 React/FastAPI 제품 코드와 충돌하지 않도록 분리한 실험용
프로토타입이다. 두 가지 작업을 같은 데이터 계약으로 검증한다.

1. `Predictive Maintenance Canonical V3.1` 데이터를 Streamlit에서 읽어 Plotly
   차트로 렌더링한다.
2. FastAPI와 Flask에 동일한 `GET /health` 계약을 구현하고 결과물 완성도를
   비교한다.

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

```bash
bash experiments/week1_prototype/run_framework_comparison.sh
```

동일한 `/health` 응답을 대상으로 다음 항목을 비교한다.

- HTTP 200 및 JSON 계약 일치
- 자동 OpenAPI 문서 제공 여부
- 응답 스키마 명시·검증 여부
- 테스트 클라이언트 사용 가능 여부
- 최소 구현 코드량
- 인프로세스 요청 지연시간 참고치

지연시간은 로컬 개발 환경의 참고값이며 운영 성능 결론으로 사용하지 않는다.
최종 선정 근거는 API 계약, 자동 문서화, 검증, 테스트와 확장성이다.

## 테스트

```bash
PYTHONPATH=experiments/week1_prototype \
  .venv-week1/bin/python -m pytest experiments/week1_prototype/tests -q
```

## 실험 범위

- 기존 `api/`, `web/`, 데이터셋 생성기 코드는 수정하지 않는다.
- Flask는 비교용 최소 구현이며 제품 백엔드로 병행 운영하지 않는다.
- Canonical V3.1 원본 파일은 읽기 전용으로 사용한다.

