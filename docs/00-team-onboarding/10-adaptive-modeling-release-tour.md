# Predictive Maintenance V3.1 · Adaptive Modeling 화면 투어

> 최신 인터랙티브 Story: `https://dashboard.oosu.dev/team-share-adaptive`
>
> 독립 HTML: `https://dashboard.oosu.dev/team-share-adaptive.html`
>
> 실제 ML Validator: `https://dashboard.oosu.dev/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/modeling`
>
> 기존 2026-08-04 Story: `https://dashboard.oosu.dev/team-share`

이 문서는 기존 [`02-feature-tour.md`](./02-feature-tour.md)를 대체하지 않는다. 기존 문서는 가입·역할·Dashboard·Analysis·Ontology의 선행 프로토타입을 설명하고, 이 문서는 그 이후 추가된 **Predictive Maintenance Canonical V3.1 runtime과 governed Adaptive Modeling release flow**를 별도로 설명한다.

최신 Story의 검증 태그는 다음과 같다.

```text
team-share-adaptive-capture-integrity-20260805
```

## 전체 Story

### 데스크톱

![Predictive Maintenance V3.1과 Adaptive Modeling 전체 Story](../../web/public/team-share-adaptive-assets/00-team-share-adaptive-story.png)

### 모바일

![Predictive Maintenance V3.1과 Adaptive Modeling 모바일 Story](../../web/public/team-share-adaptive-assets/00-team-share-adaptive-story-mobile.png)

최신 Story는 다음 내용을 한 페이지에서 비교할 수 있도록 구성한다.

- Canonical V3.1 Dataset Version과 이전 V2 snapshot
- Result Artifact 기반 현재 위험 결과
- PostgreSQL prediction timeline replay
- Feature Recipe와 Feature Dataset materialization
- Validation-only model·threshold selection
- held-out test 분리
- Model Registry와 역할 분리 승인
- local release와 strict production readiness 구분

## 캡처 신뢰성 기준

신규 이미지는 Playwright가 다음 조건을 모두 확인한 뒤 생성한다.

- `.route-loading`이 화면에 보이지 않음
- `.loading-panel`이 화면에 보이지 않음
- `.fd-state.state-loading`과 `.fd-state.state-refreshing`이 보이지 않음
- `.visualization-switcher-skeleton`이 보이지 않음
- `.mlv-loading`이 보이지 않음
- 보이는 `aria-busy="true"` 요소가 없음
- 웹폰트 로딩 완료
- 모든 이미지가 `complete`이고 `naturalWidth > 0`
- 최소 3회의 `requestAnimationFrame` 완료
- animation, transition과 caret 비활성화

위 조건을 만족하지 않으면 screenshot 파일을 갱신하지 않는다. 따라서 이 문서의 이미지는 route loader나 skeleton이 잠깐 표시된 중간 상태를 캡처한 자료가 아니다.

## 1. Canonical V3.1 운영 Dashboard

![Predictive Maintenance V3.1 runtime Dashboard](../../web/public/team-share-adaptive-assets/01-v3-runtime-dashboard.png)

화면에서 확인할 수 있는 계약:

- `canonical-ai4i-physics-v3.1` Dataset Version
- immutable version selector와 V2 호환 snapshot
- bundle checksum
- `independent-logreg-v3.1` Model Version
- `binary_failure_within_horizon` Prediction Task
- `result-artifact-v1.0` Result schema
- Result Artifact 기반 최신 위험 설비
- `critical`, `warning`, `attention`, `normal` 상태 집계
- recommended action과 실제 WorkOrder 실행 상태 분리
- Project 3 graph projection readiness

의미상 주의할 점:

```text
failure_risk / no_significant_risk
```

이 binary 결과는 AI4I의 `PWF`, `HDF`, `OSF`, `TWF` failure mode를 직접 예측하는 class가 아니다. 또한 추천 조치는 승인·실행된 WorkOrder를 의미하지 않는다.

핵심 파일:

- `web/src/features/predictive-maintenance/PredictiveMaintenanceReplayPanel.tsx`
- `api/ontology_dashboard/predictive_maintenance_runtime/service.py`
- `api/ontology_dashboard/routers/predictive_maintenance_runtime.py`

## 2. Result Artifact replay

![Predictive Maintenance Result Artifact replay](../../web/public/team-share-adaptive-assets/02-v3-result-replay.png)

Replay는 새 센서값이나 새 prediction을 브라우저에서 만들어내지 않는다.

- canonical observation timestamp 사용
- PostgreSQL `pm_prediction_timeline` 사용
- precomputed prediction timeline 재생
- speed 변경
- pause·resume
- seek
- reset
- source freshness 표시
- nearest prediction timestamp 표시

Replay가 움직이는 동안에도 최신 운영 결과는 Result Artifact와 구분해 표시한다. History replay를 현재의 실시간 재학습 결과처럼 표현하지 않는다.

## 3. ML Validator 실험 평가

![ML Validator desktop experiment evaluation](../../web/public/team-share-adaptive-assets/03-ml-validator-desktop.png)

ML Validator는 단순한 모델 점수 표가 아니라 다음 governance identity를 함께 표시한다.

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

주요 평가 화면:

- Dummy prior baseline
- Logistic Regression
- optional dependency가 없는 후보의 `blocked` 상태
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

Controlled release evidence의 대표 값:

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

이 값은 synthetic controlled E2E의 pipeline 검증 수치다. 실제 고객 설비에서의 production predictive quality를 보증하는 수치로 사용하지 않는다.

## 4. Model Registry와 release governance

![Model Registry와 release governance](../../web/public/team-share-adaptive-assets/04-model-release-governance.png)

Model Version 상태 흐름:

```text
candidate → approved → active → retired
```

역할 분리:

- ML Validator는 release request를 생성할 수 있음
- ML Validator는 자신의 request를 승인할 수 없음
- Tenant Admin이 승인 또는 거절
- 승인된 Model Version만 active 전환 가능
- 기존 active model은 같은 transaction에서 retired
- 이전 Model Version으로 rollback 가능

승격 전 확인하는 주요 gate:

- Experiment succeeded
- selected candidate identity 일치
- Candidate Result artifact checksum 일치
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

## 5. 모바일 ML Validator

![ML Validator mobile layout](../../web/public/team-share-adaptive-assets/05-ml-validator-mobile.png)

390×844 viewport 기준으로 다음을 검증했다.

- 가로 overflow 없음
- Dataset·Mapping·Feature readiness 표시
- Experiment 선택
- 평가 Tab 전환
- leaderboard의 세로 재배치
- plot과 metric card 가독성
- loading·empty·error·blocked 상태
- Model Registry action의 모바일 배치

## 현재 완료 상태

| 영역 | 상태 |
|---|---|
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

### 제품 추가 작업

- Source upload·Mapping·Recipe를 한 화면에서 수행하는 Modeling Studio
- daemon worker와 heartbeat registry
- S3 또는 GCS artifact store
- calibration artifact와 confidence policy
- operational drift와 delayed ground truth
- maintenance outcome·false alarm 비용 연결
- LightGBM·XGBoost·SHAP optional capability 설치
- production PostgreSQL·Redis·Neo4j·Project 3·OIDC·observability 구성

## 공유 주소

| 용도 | 주소 |
|---|---|
| 기존 선행 프로토타입 | `https://dashboard.oosu.dev/team-share` |
| 최신 인터랙티브 Story | `https://dashboard.oosu.dev/team-share-adaptive` |
| 독립 HTML | `https://dashboard.oosu.dev/team-share-adaptive.html` |
| 실제 ML Validator | `https://dashboard.oosu.dev/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/modeling` |
| API 문서 | 로컬 `http://127.0.0.1:8100/docs` |

## 로컬 주소

```text
http://127.0.0.1:3100/team-share
http://127.0.0.1:3100/team-share-adaptive
http://127.0.0.1:3100/team-share-adaptive.html
http://127.0.0.1:3100/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/modeling
```

## 캡처 재생성

기능 화면 5장:

```bash
cd web
npm run capture:team-share-adaptive
```

전체 Story desktop·mobile:

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
- 새 `/team-share-adaptive` 렌더
- 독립 `/team-share-adaptive.html` 렌더
- 신규 이미지 7개 로딩
- desktop·tablet·mobile 기존 Team Share 회귀
- TypeScript
- frontend unit tests
- production build

## 관련 문서

- [`02-feature-tour.md`](./02-feature-tour.md) — 기존 가입·역할·Dashboard·Analysis·Ontology 투어
- [`09-verification-report.md`](./09-verification-report.md) — 기존 Story 검증 보고서
- [`../30-implementation/stage-history/stage44-predictive-maintenance-v3.1-release-summary.md`](../30-implementation/stage-history/stage44-predictive-maintenance-v3.1-release-summary.md)
- [`../30-implementation/stage-history/stage45-adaptive-modeling-release-summary.md`](../30-implementation/stage-history/stage45-adaptive-modeling-release-summary.md)
- [`../50-operations/adaptive-modeling-release-runbook.md`](../50-operations/adaptive-modeling-release-runbook.md)

