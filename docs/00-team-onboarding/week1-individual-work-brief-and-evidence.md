# Week 1 개인 작업 Brief 및 검토 링크

이 문서는 장우수 담당 구현·실험 결과를 팀 검토용 링크와 함께 정리한
증빙 인덱스다. 팀 공통 표준을 확정하는 문서가 아니라, 구현한 프로토타입과
데이터 패키지, 비교 실험을 재현·검토하기 위한 자료다.

## 1. Palantir 기반 리포트·대시보드 UX/UI 벤치마킹 및 통합 프로토타입 구현

### 구현 내용

- Palantir Foundry·Contour의 Dashboard, Object Explorer, Analysis, Filter,
  Inspector와 역할별 Workspace 패턴을 벤치마킹했다.
- Organization → Project → Workspace → Role Dashboard 흐름으로 화면을 구성했다.
- Dataset, Ontology, Analysis, Dashboard, Report, Model과 Result Artifact를
  하나의 제품 흐름에서 확인하도록 통합했다.
- 예측 결과, provenance, historical replay, graph readiness와 역할별
  governed action을 함께 확인하는 프로토타입을 구현했다.
- 데스크톱·모바일·다크모드 화면과 팀 검토용 통합 Story를 구성했다.

### 실행 화면

- 통합 Story: <https://dashboard.oosu.dev/team-share-adaptive>
- 실제 Project Dashboard: <https://dashboard.oosu.dev/app/projects/manufacturing-demo-project>
- ML Validator: <https://dashboard.oosu.dev/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/modeling>

### GitHub

- 구현 브랜치: <https://github.com/oosuhada/agentic-ontology-dashboard/tree/feature/predictive-maintenance-adaptive-modeling>
- 통합 Story 구현: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-adaptive-modeling/web/src/features/teamshare/AdaptiveTeamShareStory.tsx>
- UI/UX 계획: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-adaptive-modeling/docs/40-ui-ux/plans/chart-intelligence-color-system-uiux-plan.md>
- Release Tour: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-adaptive-modeling/docs/00-team-onboarding/10-adaptive-modeling-release-tour.md>

## 2. Azure PdM / AI4I 데이터 기반 압축기–CNC Canonical V3.1 합성 데이터셋 생성 및 검증

### 구현 내용

- Microsoft Azure Predictive Maintenance sample dataset의 압축기 센서·열화
  특성을 참고해 전압, 회전, 압력, 진동과 고장·정비 이력을 합성했다.
- AI4I 2020 Predictive Maintenance Dataset의 CNC 물리 관계, 공구 마모와
  PWF·HDF·OSF·TWF·RNF 고장 조건을 반영했다.
- 두 원본 CSV를 단순 병합하지 않고 Asset, Sensor Observation, Production
  Cycle, Maintenance Event, Failure Truth, Prediction과 Result Artifact의
  공통 Canonical 계약으로 생성했다.
- Schema, Manifest, checksum, 재현성, 센서·공구 마모 연속성, 고장 Truth,
  정비 이력과 Result Artifact provenance를 검증했다.
- 압축기와 CNC는 설비 유형별 독립 Logistic Regression 모델로 예측한다.

### GitHub Release — 전체 데이터·코드 패키지

- Release 페이지: <https://github.com/oosuhada/agentic-ontology-dashboard/releases/tag/predictive-maintenance-canonical-v3.1-20260805>
- 전체 ZIP 다운로드: <https://github.com/oosuhada/agentic-ontology-dashboard/releases/download/predictive-maintenance-canonical-v3.1-20260805/predictive_maintenance_canonical_v3.1.zip>
- SHA-256 파일: <https://github.com/oosuhada/agentic-ontology-dashboard/releases/download/predictive-maintenance-canonical-v3.1-20260805/predictive_maintenance_canonical_v3.1.zip.sha256>

```text
ZIP SHA-256
7f60ff5e8e921d66e009441877c02c61eb0ad1ba18a4a10ffc871b4b9731f7c6
```

Release ZIP에는 다음 항목이 포함된다.

- 압축기·CNC 전체 합성 데이터
- 데이터 생성기와 예측 Pipeline
- Package·reproducibility validator
- Schema와 Result Artifact 계약
- Validation JSON과 구현·감사 보고서
- Agent evidence 평가 예제

### GitHub 구현·검증 문서

- 통합 브랜치: <https://github.com/oosuhada/agentic-ontology-dashboard/tree/feature/predictive-maintenance-canonical-v3.1-complete>
- V3.1 업그레이드 계획: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/docs/30-implementation/predictive-maintenance-canonical-v3-upgrade-plan.md>
- Release 검증 요약: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/docs/30-implementation/stage-history/stage44-predictive-maintenance-v3.1-release-summary.md>
- 운영·복구 Runbook: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/docs/50-operations/predictive-maintenance-v3.1-release-runbook.md>
- 전용 Release verifier: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/scripts/verify_predictive_maintenance_v3_1_release.py>
- Package contract test: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/tests/test_predictive_maintenance_bundle_contract.py>

### 실행 화면

- V3.1 통합 Story: <https://dashboard.oosu.dev/team-share-adaptive>
- V3.1 Project Dashboard: <https://dashboard.oosu.dev/app/projects/manufacturing-demo-project>

## 3. FastAPI 서버 기동 및 `/health` 엔드포인트 구현·검증

### 구현 내용

- FastAPI와 Flask에 같은 `GET /health` 경로와 JSON payload를 각각 구현했다.
- HTTP 200, payload 일치, 최소 코드량, 테스트 클라이언트, OpenAPI 자동 생성,
  응답 Schema 선언과 로컬 인프로세스 지연시간을 비교했다.
- Flask가 최소 응답에서는 더 가벼웠지만, FastAPI가 별도 확장 없이 Pydantic
  응답 검증, OpenAPI와 Swagger를 제공해 최종 프레임워크로 선정했다.

### 실행 화면

- 비교 결과: <https://fastapi-flask.oosu.dev>
- FastAPI health: <https://fastapi-flask.oosu.dev/health>
- Flask health 비교 응답: <https://fastapi-flask.oosu.dev/flask-health>
- Swagger: <https://fastapi-flask.oosu.dev/docs>
- 비교 JSON: <https://fastapi-flask.oosu.dev/comparison.json>

### GitHub

- 실험 브랜치: <https://github.com/oosuhada/agentic-ontology-dashboard/tree/experiment/week1-streamlit-plotly-framework-comparison>
- FastAPI 구현: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/experiment/week1-streamlit-plotly-framework-comparison/experiments/week1_prototype/framework_comparison/fastapi_app.py>
- Flask 구현: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/experiment/week1-streamlit-plotly-framework-comparison/experiments/week1_prototype/framework_comparison/flask_app.py>
- 비교 Runner: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/experiment/week1-streamlit-plotly-framework-comparison/experiments/week1_prototype/framework_comparison/compare.py>
- 비교 테스트: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/experiment/week1-streamlit-plotly-framework-comparison/experiments/week1_prototype/tests/test_framework_comparison.py>
- 구현 보고서: <https://github.com/oosuhada/agentic-ontology-dashboard/blob/experiment/week1-streamlit-plotly-framework-comparison/experiments/week1_prototype/IMPLEMENTATION_REPORT.md>

## 4. Plotly/Streamlit 조사 및 Streamlit 대시보드에 Plotly 차트 연동·렌더링

### 구현 내용

- 기존 Streamlit 운영·품질 Dashboard의 기본 차트를 Plotly Figure로 전환했다.
- Figure builder를 Streamlit 화면과 분리해 빈 데이터와 정상 데이터를 단위
  테스트할 수 있도록 구성했다.
- 최소 요구사항 3종을 넘어 막대, 선, Donut과 grouped bar를 포함한 Plotly
  시각화 9개를 기존 Dashboard에 연동했다.
- Streamlit AppTest에서 exception 0건과 `plotly_chart` 9개 렌더링을 확인했다.

### 실행 화면

- Plotly·Streamlit Dashboard: <https://plotly-streamlit.oosu.dev/dashboard>
- Streamlit health: <https://plotly-streamlit.oosu.dev/_stcore/health>

### GitHub

- 실험 브랜치: <https://github.com/oosuhada/text2cypher-factory-rca/tree/experiment/streamlit-plotly-dashboard>
- Plotly Figure builder: <https://github.com/oosuhada/text2cypher-factory-rca/blob/experiment/streamlit-plotly-dashboard/frontend/dashboard_plotly.py>
- Streamlit Dashboard 연동: <https://github.com/oosuhada/text2cypher-factory-rca/blob/experiment/streamlit-plotly-dashboard/frontend/pages/dashboard.py>
- Plotly 테스트: <https://github.com/oosuhada/text2cypher-factory-rca/blob/experiment/streamlit-plotly-dashboard/tests/test_dashboard_plotly.py>
- 실험 문서: <https://github.com/oosuhada/text2cypher-factory-rca/blob/experiment/streamlit-plotly-dashboard/docs/streamlit-plotly-dashboard-experiment.md>

## 빠른 검토 링크

| 작업 | 실행 화면 | GitHub |
|---|---|---|
| Palantir UX/UI 통합 프로토타입 | <https://dashboard.oosu.dev/team-share-adaptive> | <https://github.com/oosuhada/agentic-ontology-dashboard/tree/feature/predictive-maintenance-adaptive-modeling> |
| Canonical V3.1 데이터 패키지 | <https://dashboard.oosu.dev/app/projects/manufacturing-demo-project> | <https://github.com/oosuhada/agentic-ontology-dashboard/releases/tag/predictive-maintenance-canonical-v3.1-20260805> |
| FastAPI vs Flask | <https://fastapi-flask.oosu.dev> | <https://github.com/oosuhada/agentic-ontology-dashboard/tree/experiment/week1-streamlit-plotly-framework-comparison> |
| Plotly·Streamlit | <https://plotly-streamlit.oosu.dev/dashboard> | <https://github.com/oosuhada/text2cypher-factory-rca/tree/experiment/streamlit-plotly-dashboard> |

