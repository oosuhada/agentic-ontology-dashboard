# Week 1 개인 작업 Brief 및 검토 링크

팀원 장우수의 담당 구현·실험 결과를 팀 검토용 링크와 함께 정리한 증빙
인덱스입니다. 팀 공통 표준을 확정하는 문서가 아니라, 구현한 프로토타입과
데이터 패키지, 비교 실험을 재현하고 검토하기 위한 자료입니다.

## 1. Palantir 기반 리포트·대시보드 UX/UI 벤치마킹 및 통합 프로토타입 구현

Palantir Foundry·Contour의 Dashboard, Object Explorer, Analysis, Filter,
Inspector 및 역할별 Workspace 패턴을 조사했습니다.

조사한 UX/UI 패턴을 참고해 Dataset, Ontology, Analysis, Dashboard, Report,
Model과 Result Artifact를 하나의 업무 흐름으로 연결한 예지보전 통합
프로토타입을 구현했습니다. 조직·프로젝트·워크스페이스·역할에 따라 첫 화면과
정보 우선순위가 달라지도록 구성했으며, 예측 결과, 근거 데이터, 권장 조치와
Historical Replay를 함께 확인할 수 있도록 연결했습니다.

### 실행 화면

- [기존 Team Share](https://dashboard.oosu.dev/team-share)
- [최신 통합 프로토타입 Story](https://dashboard.oosu.dev/team-share-adaptive)
- [독립 HTML 공유본](https://dashboard.oosu.dev/team-share-adaptive.html)
- [실제 Project Dashboard](https://dashboard.oosu.dev/app/projects/manufacturing-demo-project)
- [ML Validator](https://dashboard.oosu.dev/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/modeling)
- [Ontology Dashboard API 문서](https://dashboard.oosu.dev/docs)

### GitHub

- [Adaptive Modeling 구현 브랜치](https://github.com/oosuhada/agentic-ontology-dashboard/tree/feature/predictive-maintenance-adaptive-modeling)
- [통합 Story 화면 코드](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-adaptive-modeling/web/src/features/teamshare/AdaptiveTeamShareStory.tsx)
- [Chart Intelligence·Color System UI/UX 계획](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-adaptive-modeling/docs/40-ui-ux/plans/chart-intelligence-color-system-uiux-plan.md)
- [Adaptive Modeling Release Tour](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-adaptive-modeling/docs/00-team-onboarding/10-adaptive-modeling-release-tour.md)

## 2. Azure PdM / AI4I 데이터 기반 “압축기–CNC Canonical V3.1” 합성 데이터셋 생성 및 검증

Microsoft Azure Predictive Maintenance sample dataset의 압축기 센서·고장·정비
패턴과 AI4I 2020 Predictive Maintenance Dataset의 CNC 물리 관계·공구 마모·고장
조건을 참고했습니다.

두 원본 데이터의 행을 단순히 합친 것이 아니라, 압축기와 CNC를 공통
Asset·Observation·Failure·Maintenance·Prediction 계약으로 분석할 수 있도록
새로운 Canonical V3.1 합성 데이터셋을 생성했습니다.

Schema, Manifest, Checksum, 재현성, 센서 연속성, Tool wear 초기화, 정비 이력,
Failure Truth, Prediction Timeline과 Result Artifact 연결을 검증했습니다.

### 전체 데이터·코드 패키지

- [Canonical V3.1 GitHub Release](https://github.com/oosuhada/agentic-ontology-dashboard/releases/tag/predictive-maintenance-canonical-v3.1-20260805)
- [전체 ZIP 다운로드](https://github.com/oosuhada/agentic-ontology-dashboard/releases/download/predictive-maintenance-canonical-v3.1-20260805/predictive_maintenance_canonical_v3.1.zip)
- [SHA-256 검증 파일](https://github.com/oosuhada/agentic-ontology-dashboard/releases/download/predictive-maintenance-canonical-v3.1-20260805/predictive_maintenance_canonical_v3.1.zip.sha256)

ZIP 크기는 약 21MB이며 압축을 해제하면 다음 항목을 확인할 수 있습니다.

- 압축기·CNC 전체 합성 데이터
- Compressor·CNC Sensor Observation
- CNC Production Cycle
- Asset Relation
- Maintenance Event와 Failure Truth
- Prediction Snapshot·Timeline·Factor
- Result Artifact
- 데이터 생성기와 예측 Pipeline
- Package·재현성 검증기
- Schema와 Result Artifact 계약
- 구현·검증·감사 보고서
- Agent evidence 평가 예제

SHA-256 값은 다음과 같습니다.

```text
7f60ff5e8e921d66e009441877c02c61eb0ad1ba18a4a10ffc871b4b9731f7c6
```

### GitHub 구현·검증 자료

- [Canonical V3.1 통합 브랜치](https://github.com/oosuhada/agentic-ontology-dashboard/tree/feature/predictive-maintenance-canonical-v3.1-complete)
- [V3.1 업그레이드 계획](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/docs/30-implementation/predictive-maintenance-canonical-v3-upgrade-plan.md)
- [Release 검증 결과](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/docs/30-implementation/stage-history/stage44-predictive-maintenance-v3.1-release-summary.md)
- [운영·복구 Runbook](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/docs/50-operations/predictive-maintenance-v3.1-release-runbook.md)
- [V3.1 Release 검증기](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/scripts/verify_predictive_maintenance_v3_1_release.py)
- [Package 계약 테스트](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/tests/test_predictive_maintenance_bundle_contract.py)

### 실행 화면

- [V3.1 Project Dashboard](https://dashboard.oosu.dev/app/projects/manufacturing-demo-project)
- [V3.1 통합 Story](https://dashboard.oosu.dev/team-share-adaptive)
- [V3.1 독립 HTML](https://dashboard.oosu.dev/team-share-adaptive.html)

독립 HTML 배포본에서는 다음 식별 정보를 확인할 수 있습니다.

```text
UCI AI4I 2020 Manufacturing Predictive Maintenance
canonical-ai4i-physics-v3.1
dsv-9fc144c7-d3f8-5b37-8465-04248165b7ce
```

## 3. FastAPI 서버 기동 및 `/health` 엔드포인트 구현·검증

FastAPI와 Flask에 동일한 `GET /health` API와 JSON 응답 계약을 각각
구현했습니다.

두 프레임워크의 HTTP 응답, Payload 일치, 최소 코드량, 테스트 방식, OpenAPI
자동 생성, Swagger 제공 여부와 응답 Schema 검증을 비교했습니다.

Flask는 단일 API의 최소 실행과 로컬 인프로세스 응답에서 더 가벼웠습니다.
반면 FastAPI는 별도 확장 없이 Pydantic 응답 Schema, 데이터 검증, OpenAPI와
Swagger를 함께 제공했습니다.

따라서 단순 응답 속도가 아니라 계약, 문서화, 테스트 및 향후
Dataset·Prediction API 확장성을 기준으로 FastAPI를 최종 프레임워크로
선정했습니다.

### 실행 화면

- [FastAPI vs Flask 비교 결과](https://fastapi-flask.oosu.dev)
- [FastAPI `/health`](https://fastapi-flask.oosu.dev/health)
- [Flask `/health` 비교 응답](https://fastapi-flask.oosu.dev/flask-health)
- [FastAPI Swagger](https://fastapi-flask.oosu.dev/docs)
- [비교 결과 JSON](https://fastapi-flask.oosu.dev/comparison.json)

### GitHub

- [비교 실험 브랜치](https://github.com/oosuhada/agentic-ontology-dashboard/tree/experiment/week1-streamlit-plotly-framework-comparison)
- [FastAPI 구현](https://github.com/oosuhada/agentic-ontology-dashboard/blob/experiment/week1-streamlit-plotly-framework-comparison/experiments/week1_prototype/framework_comparison/fastapi_app.py)
- [Flask 구현](https://github.com/oosuhada/agentic-ontology-dashboard/blob/experiment/week1-streamlit-plotly-framework-comparison/experiments/week1_prototype/framework_comparison/flask_app.py)
- [비교 실행 코드](https://github.com/oosuhada/agentic-ontology-dashboard/blob/experiment/week1-streamlit-plotly-framework-comparison/experiments/week1_prototype/framework_comparison/compare.py)
- [비교 테스트](https://github.com/oosuhada/agentic-ontology-dashboard/blob/experiment/week1-streamlit-plotly-framework-comparison/experiments/week1_prototype/tests/test_framework_comparison.py)
- [구현 보고서](https://github.com/oosuhada/agentic-ontology-dashboard/blob/experiment/week1-streamlit-plotly-framework-comparison/experiments/week1_prototype/IMPLEMENTATION_REPORT.md)

## 4. Plotly/Streamlit 조사 및 Streamlit 대시보드에 Plotly 차트 3종 이상 연동·렌더링

Streamlit의 Dashboard UI 구성 기능과 Plotly의 인터랙티브 시각화 기능을
조사했습니다.

기존 Streamlit 대시보드의 기본 `st.bar_chart` 중심 시각화를 Plotly Figure로
전환했으며, Figure 생성 코드를 화면 코드와 분리해 단위 테스트가 가능하도록
구성했습니다.

Brief의 최소 요구사항은 차트 3종이었지만 실제로는 다음 9개 Plotly 시각화를
연동했습니다.

1. 노드 유형별 규모
2. 관계 유형별 규모
3. 장비별 공정 실행
4. 이상 유형 분포
5. 품질 불합격 상위 항목
6. 질의 상태 Donut
7. Provider별 질의량
8. 최근 질의 응답시간
9. Blind 평가 Variant별 품질 비교

Plotly 단위 테스트와 기존 Dashboard·Architecture 테스트를 실행했으며,
Streamlit AppTest에서 예외 없이 9개의 Plotly 차트가 렌더링되는 것을
확인했습니다.

### 실행 화면

- [Plotly 연동 Streamlit Dashboard](https://plotly-streamlit.oosu.dev/dashboard)
- [Streamlit Health](https://plotly-streamlit.oosu.dev/_stcore/health)

### GitHub

- [Plotly·Streamlit 실험 브랜치](https://github.com/oosuhada/text2cypher-factory-rca/tree/experiment/streamlit-plotly-dashboard)
- [Plotly Figure Builder](https://github.com/oosuhada/text2cypher-factory-rca/blob/experiment/streamlit-plotly-dashboard/frontend/dashboard_plotly.py)
- [Streamlit Dashboard 연동 코드](https://github.com/oosuhada/text2cypher-factory-rca/blob/experiment/streamlit-plotly-dashboard/frontend/pages/dashboard.py)
- [Plotly 단위 테스트](https://github.com/oosuhada/text2cypher-factory-rca/blob/experiment/streamlit-plotly-dashboard/tests/test_dashboard_plotly.py)
- [실험 결과 문서](https://github.com/oosuhada/text2cypher-factory-rca/blob/experiment/streamlit-plotly-dashboard/docs/streamlit-plotly-dashboard-experiment.md)

## 빠른 검토 링크

| 작업 | 실행 화면 | GitHub |
|---|---|---|
| Palantir UX/UI 통합 프로토타입 | [통합 Story](https://dashboard.oosu.dev/team-share-adaptive) | [구현 브랜치](https://github.com/oosuhada/agentic-ontology-dashboard/tree/feature/predictive-maintenance-adaptive-modeling) |
| Canonical V3.1 데이터 패키지 | [Project Dashboard](https://dashboard.oosu.dev/app/projects/manufacturing-demo-project) | [GitHub Release](https://github.com/oosuhada/agentic-ontology-dashboard/releases/tag/predictive-maintenance-canonical-v3.1-20260805) |
| FastAPI vs Flask | [비교 화면](https://fastapi-flask.oosu.dev) | [실험 브랜치](https://github.com/oosuhada/agentic-ontology-dashboard/tree/experiment/week1-streamlit-plotly-framework-comparison) |
| Plotly·Streamlit | [Dashboard](https://plotly-streamlit.oosu.dev/dashboard) | [실험 브랜치](https://github.com/oosuhada/text2cypher-factory-rca/tree/experiment/streamlit-plotly-dashboard) |

