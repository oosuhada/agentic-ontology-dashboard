# 로컬 실행 및 검증

## 요구사항

- Python 3
- Node.js 22 이상
- npm
- Canonical Runtime 사용 시 PostgreSQL

## 실행

```bash
./scripts/run_local.sh
```

스크립트는 `.venv`와 `web/node_modules`가 없으면 설치하고 API 8100, Web 3100을 시작합니다.

```text
http://127.0.0.1:3100/login
http://127.0.0.1:3100/app/projects/manufacturing-demo-project/mvp
http://127.0.0.1:8100/health
```

SQLite 개발 환경에서는 Canonical Runtime API가 503을 반환하며 MVP는 Gold Fixture로 동작합니다. Canonical V3.1 전체 조회는 `ONTOLOGY_DASHBOARD_DB`에 PostgreSQL URL을 지정해야 합니다.

## 프론트엔드 검증

```bash
npm --prefix web run lint
npm --prefix web run test
npm --prefix web run build
npm --prefix web run test:e2e
```

## 백엔드 계약 검증

```bash
PYTHONPATH=api:ml/src .venv/bin/pytest -q \
  tests/test_mvp.py \
  tests/test_predictive_maintenance_runtime_capability.py \
  tests/test_predictive_maintenance_v3_compatibility.py
```

## 화면 캡처

API와 Web이 실행 중일 때:

```bash
npm --prefix web run capture:mvp
```

## 문제 확인

- API log: `/tmp/ontology-dashboard-api.log`
- Web log: `/tmp/ontology-dashboard-web.log`
- 401: session cookie 확인
- 403: 역할 permission 확인
- 409: 계정의 active Project 확인
- 503 Runtime: PostgreSQL과 Canonical V3.1 materialization 확인
