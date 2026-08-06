# Ontology Dashboard — Predictive Maintenance MVP

제조 설비의 예지보전 결과를 두 역할이 확인하고 기록하는 현재 제품 버전입니다. 저장소는 더 이상 V1~V4 프로토타입, 비교 화면, 범용 Analysis·Agent·Governance Workbench를 포함하지 않습니다.

## 현재 제품

- 공개 경로: `/app/projects/:projectId/mvp`
- 역할: `관리자·임원`, `실무 엔지니어`
- 업무 흐름: `Overview → Objects → Operations → Executive Report`
- 데이터 우선순위: PostgreSQL Canonical V3.1 Result Artifact → Gold Fixture fallback
- Action 원칙: 모델 권고와 실제 사람의 판단을 분리하며 자동 설비 정지를 실행하지 않음

## 저장소 구성

```text
api/       FastAPI 인증, Project, Canonical Runtime, Evidence/Report, Action API
data/      Gold Fixture와 Canonical V3.1 적재 입력
docs/      현재 제품·아키텍처·계약·운영 문서
ml/        Gold Fixture 예측·Evidence 생성과 Canonical 적재 지원
schemas/   현재 데이터 교환 JSON Schema
scripts/   실행, 적재, 검증, 백업·복원 도구
tests/     현재 MVP와 Canonical V3.1 계약 검증
web/       두 역할 로그인과 네 화면 React 애플리케이션
```

## 로컬 실행

```bash
./scripts/run_local.sh
```

- 로그인: `http://127.0.0.1:3100/login`
- MVP: `http://127.0.0.1:3100/app/projects/manufacturing-demo-project/mvp`
- API: `http://127.0.0.1:8100/docs`

데모 역할은 로그인 화면의 두 카드로 선택합니다.

## 검증

```bash
PYTHONPATH=api:ml/src .venv/bin/pytest -q \
  tests/test_mvp.py \
  tests/test_predictive_maintenance_runtime_capability.py \
  tests/test_predictive_maintenance_v3_compatibility.py

npm --prefix web run verify
```

상세 범위와 계약은 [`docs/README.md`](docs/README.md)를 기준으로 합니다.
