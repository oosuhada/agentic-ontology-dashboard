# Week 1 구현·실험 작업 정리

팀원 장우수가 2026년 7월 30일부터 8월 5일까지 진행한 구현·실험 작업과
결과를 실행 화면, 시각화 자료, GitHub 링크와 함께 정리했습니다. 이번 주에
무엇을 만들고 확인했는지 한눈에 살펴볼 수 있도록 작업별 구현 내용과 관련
자료를 모았습니다.

## 1. Palantir 기반 리포트·대시보드 UX/UI 벤치마킹 및 통합 프로토타입 구현

Palantir Foundry·Contour의 Dashboard, Object Explorer, Analysis, Filter,
Inspector 및 역할별 Workspace 패턴을 조사했습니다.

조사한 UX/UI 패턴을 참고해 Dataset, Ontology, Analysis, Dashboard, Report,
Model과 Result Artifact를 하나의 업무 흐름으로 연결한 예지보전 통합
프로토타입을 구현했습니다. 조직·프로젝트·워크스페이스·역할에 따라 첫 화면과
정보 우선순위가 달라지도록 구성했으며, 예측 결과, 근거 데이터, 권장 조치와
Historical Replay를 함께 확인할 수 있도록 연결했습니다.

### 실행 화면

- [실제 Project Dashboard](https://dashboard.oosu.dev/app/projects/manufacturing-demo-project)
- [최신 통합 프로토타입 Story](https://dashboard.oosu.dev/team-share-adaptive)
- [기존 Team Share](https://dashboard.oosu.dev/team-share)
- [독립 HTML 공유본](https://dashboard.oosu.dev/team-share-adaptive.html)
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

- [Canonical V3.1 데이터셋 Story HTML](https://github.com/oosuhada/agentic-ontology-dashboard/blob/experiment/week1-streamlit-plotly-framework-comparison/experiments/week1_prototype/canonical_v3_1_story/index.html)
- [Canonical V3.1 통합 브랜치](https://github.com/oosuhada/agentic-ontology-dashboard/tree/feature/predictive-maintenance-canonical-v3.1-complete)
- [V3.1 업그레이드 계획](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/docs/30-implementation/predictive-maintenance-canonical-v3-upgrade-plan.md)
- [Release 검증 결과](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/docs/30-implementation/stage-history/stage44-predictive-maintenance-v3.1-release-summary.md)
- [운영·복구 Runbook](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/docs/50-operations/predictive-maintenance-v3.1-release-runbook.md)
- [V3.1 Release 검증기](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/scripts/verify_predictive_maintenance_v3_1_release.py)
- [Package 계약 테스트](https://github.com/oosuhada/agentic-ontology-dashboard/blob/feature/predictive-maintenance-canonical-v3.1-complete/tests/test_predictive_maintenance_bundle_contract.py)

### 실행 화면

- [Canonical V3.1 데이터셋 변경·검증 Story](https://canonical-v3-1.oosu.dev)

독립 HTML 배포본에서는 다음 식별 정보를 확인할 수 있습니다.

```text
UCI AI4I 2020 Manufacturing Predictive Maintenance
canonical-ai4i-physics-v3.1
dsv-9fc144c7-d3f8-5b37-8465-04248165b7ce
```

## 3. FastAPI·Flask 전체 MVP API 표면 비교 및 전수 계약 검증

초기 기준선으로 FastAPI와 Flask에 동일한 `GET /health` API와 JSON 응답
계약을 각각 구현했습니다. 여기에 머물지 않고 현재 Ontology Dashboard MVP의
FastAPI OpenAPI 전체를 수집해 162개 경로·172개 HTTP 작업을 전수 비교했습니다.

비인증 상태와 Tenant Admin 인증 상태에서 172개 작업을 각각 호출해 라우팅,
인증, CSRF, 권한, 요청 Schema와 예외 계약을 확인했습니다. 처리되지 않은 HTTP
500은 0건이었고, SQLite 격리 환경에서 PostgreSQL 전용 Predictive Maintenance
Runtime 10개 작업은 의도된 503 degraded contract를 반환했습니다.

FastAPI는 172개 실제 business handler와 OpenAPI를 제공하며, 147개 작업에서
요청 Body 또는 Parameter 검증을 자동 적용합니다. 성공 응답은 168개 JSON
Schema와 런타임 응답 검증, binary·SSE 계약 2개, no-content 계약 2개로 구성되어
전체 172개 작업의 성공 계약이 명시됩니다. JSON 성공 응답 중 167개는 필드
수준 Schema를 제공하고, OpenAPI 문서 자체를 반환하는 1개 작업만 동적 문서
객체 계약입니다. Flask에는 동일 172개 route mirror를 생성해 등록 parity를
확인했지만 실제 business handler, 자동 OpenAPI와 Schema 검증은 기본 제공되지
않았습니다. 동일 수준으로 새로 구축하려면 Flask 확장 도구와 프로젝트 규칙을
별도로 선택하고 연결해야 합니다.

Flask는 단일 API의 최소 실행과 로컬 인프로세스 응답에서 더 가벼웠습니다.
반면 FastAPI는 별도 확장 없이 Pydantic 응답 Schema, 데이터 검증, OpenAPI와
Swagger를 함께 제공했습니다.

따라서 최종 선정은 `/health` 한 개의 결과가 아니라 Dataset, Ontology,
Analysis, Dashboard, Modeling, Predictive Maintenance Runtime을 포함한 전체
162개 경로·172개 작업의 개발 구조, 계약 자동화, 검증 안정성과 경량성을
기준으로 했습니다.

네 평가 요소는 각각 25%로 동일하게 계산했습니다.

| 평가 요소 | 가중치 | FastAPI | Flask |
|---|---:|---:|---:|
| 개발 완성도와 구현 생산성 | 25% | 5/5 | 3/5 |
| API 계약과 문서 자동화 | 25% | 5/5 | 2/5 |
| 요청·응답 검증과 오류 안전성 | 25% | 5/5 | 2/5 |
| 최소 API 경량성과 단순 응답 속도 | 25% | 2/5 | 5/5 |
| **가중 합계** | **100%** | **85점** | **60점** |

Flask는 단순 `/health` 응답과 가벼운 시작에서 더 높은 점수를 받았습니다.
FastAPI는 큰 API 구조화, 계약 자동화, 요청·응답 검증에서 앞섰습니다. 기존
코드의 이식 비용은 평가에서 제외했고, 새 제품을 구축할 때 어떤 개발 방식이
현재 요구사항에 더 적합한지를 기준으로 FastAPI를 최종 선택했습니다.

### 프레임워크 비교·검증 화면

- [FastAPI vs Flask 비교 결과](https://fastapi-flask.oosu.dev)
- [전체 162개 경로·172개 작업 비교 JSON](https://fastapi-flask.oosu.dev/full-comparison.json)
- [실제 Ontology Dashboard 162경로 Swagger](https://dashboard.oosu.dev/docs)
- [비교 화면 Swagger](https://fastapi-flask.oosu.dev/docs)
- [FastAPI `/health`](https://fastapi-flask.oosu.dev/health)
- [Flask `/health` 비교 응답](https://fastapi-flask.oosu.dev/flask-health)
- [비교 결과 JSON](https://fastapi-flask.oosu.dev/comparison.json)

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

### 시각화 구현·검증 화면

- [Plotly Express·Graph Objects·React + ECharts 비교](https://plotly-streamlit.oosu.dev/?compare=plotly-ui)
- [Plotly 기반 Streamlit Dashboard 구현 결과](https://plotly-streamlit.oosu.dev/?workspace=dashboard)

## 빠른 검토 링크

| 작업 | 구현·검증 화면 | 보조 자료 |
|---|---|---|
| Palantir UX/UI 통합 프로토타입 | [통합 Story](https://dashboard.oosu.dev/team-share-adaptive) | [구현 브랜치](https://github.com/oosuhada/agentic-ontology-dashboard/tree/feature/predictive-maintenance-adaptive-modeling) |
| Canonical V3.1 데이터 패키지 | [데이터셋 변경·검증 Story](https://canonical-v3-1.oosu.dev) | [GitHub Release](https://github.com/oosuhada/agentic-ontology-dashboard/releases/tag/predictive-maintenance-canonical-v3.1-20260805) |
| FastAPI vs Flask | [프레임워크 비교·검증](https://fastapi-flask.oosu.dev) | [전체 비교 JSON](https://fastapi-flask.oosu.dev/full-comparison.json) |
| Plotly Express·Graph Objects·React + ECharts | [시각화 구현·검증](https://plotly-streamlit.oosu.dev/?compare=plotly-ui) | [Streamlit Dashboard 구현 결과](https://plotly-streamlit.oosu.dev/?workspace=dashboard) |

