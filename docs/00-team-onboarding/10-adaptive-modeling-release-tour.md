# Ontology Dashboard 전체 프로젝트 화면 투어

> 최신 통합 인터랙티브 Story: `https://dashboard.oosu.dev/team-share-adaptive`
>
> 독립 HTML: `https://dashboard.oosu.dev/team-share-adaptive.html`
>
> 실제 ML Validator: `https://dashboard.oosu.dev/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/modeling`
>
> 2026-08-04 이전 Story 기록: `https://dashboard.oosu.dev/team-share`

이 문서는 **Ontology Dashboard의 기존 선행 프로토타입 전체와 이후 추가된 Predictive Maintenance Canonical V3.1·Adaptive Modeling을 하나의 제품 흐름으로 설명하는 최신 통합 화면 투어**다.

이 문서와 `/team-share-adaptive`만 읽어도 다음을 파악할 수 있도록 구성한다.

- 프로젝트를 왜 만들었는지
- 조직 가입과 승인 방식
- 역할별 첫 화면과 업무 순서
- Dataset에 따라 Dashboard가 달라지는 방식
- 사용자별 개인화
- Analysis와 Ontology의 역할
- Predictive Maintenance V3.1 Dataset Version과 Result Artifact
- Historical replay의 의미
- ML 실험, threshold, lineage와 Model Registry
- release 요청·승인·활성화·rollback의 역할 분리
- 현재 완료 범위와 production 전 추가 작업

최신 통합 Story의 검증 태그:

```text
team-share-adaptive-complete-integrity-20260805
```

## 프로젝트 한 문장

Ontology Dashboard는 다음 전체 흐름을 조직·Project·Workspace·역할·사용자 권한에 따라 연결하는 운영 의사결정 플랫폼 프로토타입이다.

```text
Identity & Role
→ Dataset Version
→ Ontology Object · Link · Action
→ Analysis · Experiment · Lineage
→ Dashboard · Report
→ Evidence · Governance
→ Approved Action · Audit · Rollback
```

단순 제조 Dashboard가 아니다. Dataset과 역할이 바뀌면 첫 화면과 시각화 구성이 달라지고, 실무자가 분석한 근거를 보고서·모델 결과·승인 가능한 Action으로 연결하는 제품 구조를 검증한다.

## 전체 Story

### 데스크톱

![Ontology Dashboard 전체 프로젝트 통합 Story](../../web/public/team-share-adaptive-assets/00-team-share-adaptive-story.png)

### 모바일

![Ontology Dashboard 전체 프로젝트 모바일 Story](../../web/public/team-share-adaptive-assets/00-team-share-adaptive-story-mobile.png)

통합 Story는 기존 Story의 기능을 삭제하거나 링크로만 넘기지 않는다. 아래 내용을 페이지 본문에서 직접 설명하고 스크린샷으로 보여준다.

1. Governed onboarding과 Tenant Admin 승인
2. Report-first Manager와 Dashboard-first Engineer
3. 사용자별 Dashboard·Display preference
4. Factory·Fleet·Compressor Dataset 적응형 UI
5. Analysis Canvas·Dependency Graph
6. Ontology ObjectSet과 linked traversal
7. Canonical V3.1 runtime과 Result Artifact replay
8. ML Validator와 Model release governance
9. 완료·검토·추가 작업

## 캡처 신뢰성 기준

Playwright는 다음 조건을 모두 만족한 후에만 신규 이미지를 저장한다.

- `.route-loading`이 보이지 않음
- `.role-report-loading`과 `.role-report-refresh`가 보이지 않음
- `.loading-panel`이 보이지 않음
- `.fd-state.state-loading`과 `.fd-state.state-refreshing`이 보이지 않음
- `.visualization-switcher-skeleton`이 보이지 않음
- `.mlv-loading`이 보이지 않음
- 보이는 `aria-busy="true"` 요소가 없음
- 웹폰트 로딩 완료
- 모든 이미지가 `complete`이고 `naturalWidth > 0`
- 최소 3회의 `requestAnimationFrame` 완료
- animation, transition과 caret 비활성화

따라서 아래 이미지는 route loader, skeleton이나 refreshing 상태가 잠시 나타난 중간 화면을 저장한 자료가 아니다.

---

## 1. 조직 가입과 역할 승인

### 구성원이 희망 역할을 요청한다

![가입 역할 요청](./assets/screenshots/01-signup-role-request.png)

가입 단계에서 입력하는 항목:

- 이름
- 업무 이메일
- 조직
- 희망 역할
- 비밀번호

계정은 즉시 활성화되지 않고 `pending_approval`로 저장된다. 사용자가 `tenant_admin` 역할을 스스로 요청할 수는 없다.

### Tenant Admin이 역할·Scope·권한을 확정한다

![관리자 역할 권한 확인](./assets/screenshots/04-admin-role-permission-confirmation.png)

관리자는 다음을 결정한다.

- 실제 역할
- 접근 가능한 Project
- 접근 가능한 Workspace
- 역할 기본 권한
- 사용자별 permission allow override
- 사용자별 permission deny override

제품의 권한 구조:

```text
Organization
└─ Project
   └─ Workspace
      └─ Role policy
         └─ User permission override
```

승인과 권한 변경은 감사 가능한 기록으로 남는다.

---

## 2. 역할별 첫 화면과 업무 흐름

### 운영 매니저·임원·감사 역할은 Report-first

![매니저 보고서 메인](./assets/screenshots/05-manager-report-home.png)

보고서에는 다음이 함께 표시된다.

- 임원 의사결정 요약
- 위험·영향·조치
- Evidence field ID
- Primary metric 추세
- contributing evidence
- 담당자와 confidence
- revision과 상태
- A4 Print/PDF 레이아웃

업무 흐름:

```text
Report
→ Evidence
→ Detailed Dashboard
→ Human Decision
```

### 엔지니어·실무자·FDE 역할은 Dashboard-first

![엔지니어 Dashboard](./assets/screenshots/07-engineer-dashboard-home.png)

엔지니어는 다음 순서로 근거를 확장한다.

```text
Dashboard
→ Ontology
→ Analysis
→ Shared Report revision
```

역할은 단순 메뉴 권한이 아니라 첫 질문과 정보 우선순위를 결정한다.

### ML Validator 역할

데이터 사이언티스트는 일반 운영 Dashboard가 아니라 Experiment·Threshold·Model Registry를 검증하는 별도 Workbench를 사용한다. Model release를 요청할 수 있지만 자신이 요청한 Model Version을 스스로 승인하거나 활성화할 수 없다.

---

## 3. Dataset 적응형 Dashboard와 개인화

### 같은 역할에서도 사용자별 화면이 저장된다

![개인화 Dashboard 설정](./assets/screenshots/09-personalized-dashboard-display-settings.png)

서버에 저장되는 Dashboard preference:

- Tab과 Board 구성
- Board 위치와 크기
- 숨김과 즐겨찾기
- Parameter와 Filter
- 시각화 종류와 설정

계정 단위 Display preference:

- Text size
- Density
- 기술 메타데이터 표시

### Factory Reliability Dataset

![Factory adaptive Dashboard](./assets/screenshots/10-factory-adaptive-dashboard.png)

대표 Board:

- Operations KPI
- Interactive Risk Trend
- Factor Contribution
- Priority List
- Event Data Grid
- Ontology Relationship
- Recommended Actions

### Fleet Maintenance Dataset

![Fleet adaptive Dashboard](./assets/screenshots/11-fleet-adaptive-dashboard.png)

제조 설비 화면의 이름만 바꾸지 않는다. 차량·정비·운행 관계에 맞게 다음 화면을 선택한다.

- Impact Summary
- Maintenance Priority
- Fleet Event Grid
- Activity Stream
- Route·Service 영향

### Compressor Telemetry Dataset

![Compressor adaptive Dashboard](./assets/screenshots/12-compressor-adaptive-dashboard.png)

연속 센서 Dataset은 다음 시각화를 우선한다.

- Sensor Line Chart
- Anomaly Timeline
- Model Details
- Evidence Table
- Data Quality Warning
- Preventive Action

적응형 구성 흐름:

```text
Dataset schema
→ Semantic signals
→ Board Catalog selection
→ Role layout
→ Personal preference
```

---

## 4. Analysis와 Ontology Workbench

### Analysis 자유 Canvas

![Analysis Canvas](./assets/screenshots/13-analysis-canvas.png)

지원 범위:

- Typed DataPill
- Compatible next action
- Multiple Canvas
- 카드 이동·크기 조절
- 계산용 노드 숨김
- 계산 정의와 표현 배치 분리

### Dependency Graph

![Analysis Dependency Graph](./assets/screenshots/14-analysis-dependency-graph.png)

동일한 서버 `nodes/edges`를 Path, Canvas, Graph로 투영한다. upstream·downstream, focus chain과 결과의 생성 근거를 추적한다.

### Ontology ObjectSet

![Ontology ObjectSet Selection](./assets/screenshots/15-ontology-objectset-selection.png)

지원 집합 연산:

- Replace
- Union
- Intersection
- Difference

선택한 여러 객체를 root로 linked traversal을 수행하고 중복 Object와 Edge를 병합한다.

---

## 5. Predictive Maintenance Canonical V3.1 Runtime

### Dataset Version과 Result Artifact

![Predictive Maintenance V3.1 runtime Dashboard](../../web/public/team-share-adaptive-assets/01-v3-runtime-dashboard.png)

화면에서 확인하는 계약:

- `canonical-ai4i-physics-v3.1` Dataset Version
- immutable version selector와 V2 compatibility snapshot
- bundle checksum
- `independent-logreg-v3.1` Model Version
- `binary_failure_within_horizon` Prediction Task
- `result-artifact-v1.0` Result schema
- Result Artifact 기반 최신 위험 설비
- `critical`, `warning`, `attention`, `normal` 상태 집계
- recommended action과 실제 WorkOrder 실행 상태 분리
- Project 3 graph projection readiness

의미상 주의:

```text
failure_risk / no_significant_risk
```

이 binary 결과는 AI4I의 `PWF`, `HDF`, `OSF`, `TWF` failure mode를 직접 예측하는 class가 아니다. 추천 조치도 승인·실행된 WorkOrder를 뜻하지 않는다.

### Historical Result Artifact replay

![Predictive Maintenance Result Artifact replay](../../web/public/team-share-adaptive-assets/02-v3-result-replay.png)

Replay는 브라우저에서 새 센서값이나 prediction을 생성하지 않는다.

- canonical observation timestamp 사용
- PostgreSQL `pm_prediction_timeline` 사용
- precomputed prediction timeline 재생
- speed 변경
- pause·resume
- seek
- reset
- source freshness 표시
- nearest prediction timestamp 표시

현재 운영 결과와 history replay는 화면에서 분리해 표현한다.

---

## 6. Governed Adaptive Modeling

### ML Validator 실험 평가

![ML Validator desktop experiment evaluation](../../web/public/team-share-adaptive-assets/03-ml-validator-desktop.png)

ML Validator lineage:

```text
Dataset Version
→ Mapping Set
→ Feature Recipe Set
→ Feature Dataset Version
→ Experiment Run
→ Candidate Model
→ Threshold Policy
→ Model Version
```

평가 화면:

- Dummy prior baseline
- Logistic Regression
- optional dependency 후보의 `blocked` 상태
- Average Precision
- ROC-AUC
- Precision·Recall·F1
- Brier Score
- confusion matrix
- precision-recall curve
- ROC curve
- calibration
- slice metrics
- validation과 held-out test 분리

Controlled release evidence 대표 값:

| Candidate | Validation AP | ROC-AUC | Brier | Held-out AP |
|---|---:|---:|---:|---:|
| Dummy prior | 0.2917 | 0.5000 | 0.2160 | unavailable |
| Logistic Regression | 0.5882 | 0.8824 | 0.1667 | 0.5003 |
| Random Forest | 0.2917 | 0.5000 | 0.2917 | unavailable |

운영 threshold 예시:

```text
selected threshold: 0.33
validation recall: 0.9524
```

이 값은 synthetic controlled E2E pipeline 검증 수치다. 실제 고객 설비의 production predictive quality를 보증하지 않는다.

### Model Registry와 release governance

![Model Registry와 release governance](../../web/public/team-share-adaptive-assets/04-model-release-governance.png)

Model Version 상태:

```text
candidate → approved → active → retired
```

역할 분리:

- ML Validator가 release request 생성
- ML Validator의 self-approval 차단
- Tenant Admin이 승인 또는 거절
- 승인된 Model Version만 active 전환
- 기존 active model은 같은 transaction에서 retired
- 이전 Model Version으로 rollback 가능

승격 전 주요 gate:

- Experiment succeeded
- selected candidate identity 일치
- Candidate artifact checksum 일치
- Dummy baseline 대비 validation AP 개선
- held-out test 존재
- test set이 selection에 사용되지 않음
- validation threshold 존재
- recall policy 충족
- Mapping Set 승인
- Feature Recipe Set 승인
- Feature Dataset lineage와 checksum 일치
- runtime dependency 준비
- evaluator-only truth 비노출

### 모바일 ML Validator

![ML Validator mobile layout](../../web/public/team-share-adaptive-assets/05-ml-validator-mobile.png)

390×844 viewport 기준 검증:

- 가로 overflow 없음
- Dataset·Mapping·Feature readiness
- Experiment 선택
- 평가 Tab 전환
- leaderboard 세로 재배치
- plot과 metric card 가독성
- loading·empty·error·blocked 상태
- Model Registry action 모바일 배치

---

## 현재 완료 상태

| 영역 | 상태 |
|---|---|
| 가입 승인·세션·RBAC·scope | 완료 |
| 역할별 Report-first·Dashboard-first experience | 완료 |
| Dataset 적응형 Dashboard·개인화 | 완료 |
| Analysis·Ontology Workbench | 완료 |
| Canonical V3.1 package·Result Artifact | 완료 |
| Dataset Version selector·rollback | 완료 |
| PostgreSQL runtime·prediction replay | 완료 |
| Dataset Intake·Manifest approval | 완료 |
| Ontology Mapping approval | 완료 |
| Feature Recipe·Feature Dataset | 완료 |
| Experiment worker·recovery | 완료 |
| Model Registry·activation·rollback | 완료 |
| ML Validator desktop·tablet·mobile | 완료 |
| Local release verifier | 완료 |
| Strict production infrastructure | blocked |

## 아직 검토하거나 추가해야 하는 범위

### 도메인 검토

- 목표 Recall
- False Negative 비용
- False Positive 비용
- prediction horizon
- embargo 기간
- minimum history
- 운영 threshold 승인 기준
- Feature Recipe의 실제 설비 의미

### 제품·운영 추가 작업

- Live demo Dataset·Mapping·Recipe·Experiment seed
- Source upload·Mapping·Recipe 통합 Modeling Studio
- daemon worker와 heartbeat registry
- S3 또는 GCS artifact store
- calibration artifact와 confidence policy
- operational drift와 delayed ground truth
- maintenance outcome·false alarm 비용 연결
- LightGBM·XGBoost·SHAP optional capability
- production PostgreSQL·Redis·Neo4j·Project 3·OIDC·observability

## 공유 주소

| 용도 | 주소 |
|---|---|
| 최신 전체 프로젝트 Story | `https://dashboard.oosu.dev/team-share-adaptive` |
| 독립 HTML | `https://dashboard.oosu.dev/team-share-adaptive.html` |
| 2026-08-04 이전 Story 기록 | `https://dashboard.oosu.dev/team-share` |
| 실제 ML Validator | `https://dashboard.oosu.dev/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/modeling` |
| API 문서 | 로컬 `http://127.0.0.1:8100/docs` |

## 캡처 재생성

V3.1·ML Validator 기능 화면 5장:

```bash
cd web
npm run capture:team-share-adaptive
```

기존 화면 11장과 최신 5장을 포함한 통합 Story desktop·mobile:

```bash
cd web
npm run capture:team-share-adaptive-story
```

전체 검증:

```bash
cd web
npm run verify:team-share-adaptive
```

전체 검증은 다음을 포함한다.

- 기존 `/team-share` integrity tag 보존
- 최신 `/team-share-adaptive`에 16개 feature capture 포함
- 독립 `/team-share-adaptive.html` 렌더
- 통합 Story desktop·mobile 캡처
- TypeScript
- frontend unit tests
- production build
- 문서 링크 검사

## 관련 문서

- [`01-product-overview.md`](./01-product-overview.md) — 제품 목적과 차별점
- [`02-feature-tour.md`](./02-feature-tour.md) — 2026-08-04 기능 투어 기록
- [`03-user-flow.md`](./03-user-flow.md) — 가입부터 역할별 업무와 개인화
- [`06-implementation-status.md`](./06-implementation-status.md) — 구현 경계
- [`09-verification-report.md`](./09-verification-report.md) — 이전 Story 검증 보고서
- [`../30-implementation/stage-history/stage44-predictive-maintenance-v3.1-release-summary.md`](../30-implementation/stage-history/stage44-predictive-maintenance-v3.1-release-summary.md)
- [`../30-implementation/stage-history/stage45-adaptive-modeling-release-summary.md`](../30-implementation/stage-history/stage45-adaptive-modeling-release-summary.md)
- [`../50-operations/adaptive-modeling-release-runbook.md`](../50-operations/adaptive-modeling-release-runbook.md)
