# Ontology Dashboard Dataset Strategy

- Last updated: 2026-08-01
- Principle: 여러 데이터셋을 하나의 화면에 억지로 합치지 않고 Project 단위로 운영한다.

## 1. 핵심 원칙

`Project != Dataset`이다.

```text
Project
=
Dataset / Data Source
+ Domain Pack
+ Ontology Mapping
+ Prediction Contract
+ Dashboard Template
+ Workspace
+ Analysis Runs
```

하나의 데이터셋은 여러 Project에서 다른 목적으로 사용할 수 있고, 하나의 Project는 여러 데이터 소스와 여러 dataset version을 포함할 수 있다.

## 2. 왜 여러 Project인가

데이터셋마다 다음이 다르다.

- 분석 단위
- 시간 축
- target
- event 의미
- model output
- 비교 기준
- 권장 Action
- 적합한 역할 화면

예:

```text
Azure PdM      → fleet 비교와 정비 이력
MetroPT-3      → 고밀도 시계열과 누출 구간
AI4I           → 고장 유형 분류
C-MAPSS        → RUL 예측
CiP-DMD        → 실린더 품질·이상 분석
```

이를 하나의 고정 제조 schema에 넣으면 domain 의미가 흐려지고 화면도 dataset-specific 조건문으로 오염된다.

## 3. Azure PdM 선정 평가

Azure Predictive Maintenance dataset은 대표 showcase Project에 적합하다.

주요 이유:

### 비교 가능성

- 약 100대 machine
- 여러 model
- age 정보
- 동일 model·유사 age peer cohort 구성 가능

따라서 "같은 조건의 다른 설비 대비" 판단을 역할별 리포트에 제공할 수 있다.

### 조치 근거

- maintenance history 존재
- component 단위 교체 기록
- preventive와 corrective 구분 가능
- 실제 계산으로 다음 교체 간격과 사후 결과를 비교 가능

### 위험도 등급화

- error history와 failure history 연결 가능
- 특정 시간 window 내 error-to-failure conversion을 계산 가능
- manager priority를 데이터로 설명 가능

주의:

- "유일한 데이터셋"이라고 표현하지 않는다.
- 전환율, 중앙값, 정비 건수 등 숫자는 ingestion 이후 코드로 재계산하고 artifact와 test로 고정한다.
- Kaggle mirror와 원본 provenance를 모두 기록한다.

## 4. Candidate Comparison

| Dataset | 주 분석 목적 | 설비/단위 | 장점 | 한계 | 권장 Project 역할 |
|---|---|---:|---|---|---|
| Azure PdM | Fleet failure risk | 약 100 machines | telemetry, errors, failures, maintenance, metadata | synthetic/simulated 특성 검토 필요 | 대표 showcase |
| MetroPT-3 | Air leak anomaly | 단일 compressor 중심 | 고밀도 real-world time series | fleet 비교 약함 | 추상화 검증 2차 Project |
| AI4I 2020 | Failure classification | product cycles | 간단하고 재현 쉬움 | 실제 fleet·정비 workflow 약함 | ML validation/교육 |
| NASA C-MAPSS | RUL | engine units | RUL 연구 표준 | 실제 maintenance/error log 부족 | RUL Project |
| CiP-DMD | Cylinder anomaly/quality | 제한된 설비 | 실제 산업 시나리오 | fleet 비교 축 제한 | 품질·현장 Project |

## 5. Dataset Onboarding Contract

각 dataset은 다음 산출물을 가져야 한다.

```text
project manifest
dataset manifest
license/source note
schema snapshot
adapter
validation report
ontology mapping
prediction contract mapping
analysis metrics
role dashboard templates
E2E scenario
```

## 6. Dataset Manifest

예시:

```yaml
project_id: azure-fleet-maintenance
dataset_id: microsoft-azure-pdm
version: v1
source:
  mirror: kaggle
  canonical_status: archived
files:
  - machines.csv
  - telemetry.csv
  - errors.csv
  - failures.csv
  - maint.csv
join_keys:
  - machineID
timezone: UTC
license_review_status: pending-verification
checksums: {}
```

## 7. Adapter Strategy

공통 interface:

```text
inspect source
→ validate manifest
→ read records
→ normalize records
→ validate Prediction Result Contract
→ persist DatasetVersion and AnalysisRun
→ materialize Objects, Links, Evidence
```

우선순위:

1. File Adapter
2. REST Adapter
3. Kafka Adapter
4. MQTT Adapter
5. OPC-UA Adapter

MVP에서는 file-based automatic analysis를 먼저 지원한다.

```text
Raw Files
→ Automatic Analyzer
→ prediction_result.json
→ File Adapter
→ Ontology Dashboard
```

## 8. Prediction Result Contract

입력 transport와 무관한 공통 envelope를 사용한다.

```json
{
  "contract_version": "1.0",
  "project_id": "azure-fleet-maintenance",
  "analysis_run_id": "run-20260801-001",
  "asset_id": "machine-42",
  "analysis_type": "failure-risk",
  "observed_at": "2026-08-01T08:00:00Z",
  "status": "warning",
  "score": 0.73,
  "score_unit": "probability",
  "model": {
    "name": "fleet-risk-baseline",
    "version": "v1"
  },
  "evidence": [],
  "recommended_actions": []
}
```

Project-specific extension은 별도 properties namespace에 둔다.

## 9. Derived Metrics Governance

발표와 Dashboard에서 사용하는 모든 숫자는 다음을 가져야 한다.

- calculation code
- input dataset version
- time window definition
- null/missing handling
- output artifact
- unit test 또는 snapshot test

예:

- error type별 24시간 내 failure conversion
- preventive/corrective maintenance interval median
- model·age peer percentile
- RUL threshold distribution

## 10. Rollout Plan

### Phase A — PARTIAL COMPLETE

- 현재 Gold fixture를 `manufacturing-demo-project`로 등록 완료
- 기존 `manufacturing-demo` Workspace를 Project 하위로 migration 완료
- Project list/detail, Project별 Workspace, selector와 invalid route 복원 E2E 검증 완료
- Dashboard·Ontology operational record의 명시적 `project_id` runtime 전환과 다중 Project switch E2E는 잔여

### Phase B

- Azure Fleet Maintenance Project
- 실제 5개 CSV ingestion
- 역할별 dashboard

### Phase C

- MetroPT Project
- time-series adapter와 anomaly interval

### Phase D

- AI4I, C-MAPSS, CiP-DMD 순차 추가

## 11. Dataset Selection Rule

새 dataset은 다음 질문을 통과해야 한다.

- 어떤 사용자 판단을 개선하는가?
- 어떤 역할 화면이 필요한가?
- 어떤 Evidence를 제공하는가?
- 다른 Project와 다른 abstraction을 검증하는가?
- licensing과 provenance가 명확한가?
- 결과가 공통 Prediction Contract로 mapping 가능한가?

단지 모델 정확도가 높거나 유명하다는 이유만으로 추가하지 않는다.
