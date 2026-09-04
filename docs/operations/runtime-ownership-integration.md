# Operations Runtime Ownership 통합 기준

- 대상: PR #9 `feat/week2-operations-implementation-import`
- 상위 계약: PR #8 저장소 책임, PR #10 시스템 아키텍처, `gen_data` PR #2 source/reference fixture 분류
- 목적: 개인 프로토타입에서 이관한 실행 코드를 팀의 장기 책임 경계에 맞추되 현재 Operations 화면과 API 호환성을 유지한다.

## 적용한 책임 경계

```text
Biz-CollabCraft/gen_data
Source Data Producer / Canonical V3.1 source-reference baseline
        ↓
systems/generator
Extraction (protocol parsing + approved Mapping application)
→ Versioned Observation/Failure Dataset
→ Preprocessing Plan
→ Feature Schema/Label Schema execution
→ Feature Dataset Bundle
→ Training/Evaluation
→ versioned Model Artifact publish
        ↓ MODEL_ARTIFACT_URI
systems/backend/app/diagnosis
current observation + Model Artifact
→ runtime inference
→ Product Result Artifact / Evidence
        ↓
기존 FastAPI API → React/Report consumer
```

정비 후 Closed-loop Target은 위 흐름에 다음 feedback 경로를 추가한다.

```text
Closed-loop Maintenance Integration event
        ↓
gen_data 대상 설비 Runtime Overlay
Snapshot effect + branch-local Simulation Clock Fast-forward
        ↓ continuous maintenance_replay_overlay Observation availability
systems/backend/app/diagnosis
history_requirement/readiness validation
        ├─ insufficient: wait for subsequent Observation
        └─ ready: runtime inference
        ↓
새 Product Result Artifact / Evidence
```

### `gen_data`

raw/simulation/synthetic sensor data, Canonical V3.1 물리·생성 기준, source/reference/test fixture와 seed 재현성의 Source of Truth다. `model_contract`, `model_metrics`, `prediction_snapshot`, `prediction_factor`, `prediction_timeline`, `result_artifact`는 삭제하지 않지만 compatibility/regression/migration fixture로만 취급한다.

Closed-loop Target에서 `gen_data`는 Canonical을 변경하지 않고 정비 대상 설비에만
Runtime Overlay Snapshot과 branch-local clock을 적용해 source Observation을 생성한다.
이 경로는 opt-in이며 Model Artifact와 `history_requirement`을 읽거나 inference readiness,
Product Result/Evidence를 생성하지 않는다. `maintenance.replay_requested` 이후 해당
branch의 Simulation Clock 정책에 따라 Observation을 지속 append한다.

Overlay Observation은 Canonical Observation 저장소와 분리한 append-only runtime
저장소로 전달한다. Backend의 Product/Feature read model은 대상 설비·branch를 기준으로
Canonical 이전 구간과 Overlay 이후 구간을 선택하며 둘의 미래 행을 단순 합산하지 않는다.

### `systems/generator`

- protocol parsing 및 지정 Mapping 적용 기반 Observation Dataset 발행
- Authorized Truth Source 기반 Failure Dataset 발행
- Observation Dataset 구조 분석 및 불변 Preprocessing Plan 발행 (Ontology Mapping 미생성/미소비)
- Feature Schema allowlist/recipe 및 Label Schema 실행 기반 Feature Dataset Bundle 발행
- model training/evaluation 및 immutable versioned Model Artifact publish (latest.json pointer 관리)
- **책임 경계**:
  - protocol Mapping은 Extraction이 Canonical Observation을 생성할 때 적용한다.
  - Preprocessing은 Mapping을 생성하거나 소비하지 않는다.
  - Feature는 Mapping을 조회하지 않고 Feature Schema/Recipe를 실행한다.
  - Backend Diagnosis는 Feature 생성이나 모델 학습을 수행하지 않는다.
  - Generator는 runtime inference, Product Result Artifact 및 Evidence를 생성하지 않는다.

기존 확장 ML Validator/workbench가 `systems/backend/ontology_dashboard/modeling` 아래에서 직접 수행하던 semantic mapping, feature materialization, sklearn experiment/training 구현도 각각 `systems/generator/ontology_mapping`, `systems/generator/feature`, `systems/generator/model`로 이동했다. API에는 기존 화면·계약을 깨지 않기 위한 lazy compatibility port만 남겼다.

Model Artifact는 `model-artifact-v1.0` manifest로 publish하며 artifact type/schema, model/dataset/feature version, created time, training config, metrics, checksum, provenance, compatibility, artifact file 목록을 포함한다.

### `systems/backend/app/diagnosis`

- `MODEL_ARTIFACT_URI`로 주입된 Model Artifact의 manifest/checksum/compatibility 검증
- current observation runtime inference
- `result-artifact-v1.0` 의미와 호환되는 Product Result Artifact 생성
- 제품 Evidence 생성
- 정비 후 Overlay Observation의 새 history segment 로드
- Model Artifact의 `history_requirement`을 읽는 유일한 readiness owner
- 이력 부족 시 다음 Observation을 기다리며 `warming_up`/`history_insufficient` 처리
- 첫 inference-ready Observation의 신규 Product Result/Evidence 생성

기존 `systems/backend/ontology_dashboard/modeling/registry.py`가 수행하던 active model load/scoring/explanation 구현도 `systems/backend/app/diagnosis/model_registry.py`로 이동했고 API 경로에는 compatibility adapter만 남겼다.

Backend는 generator Python 구현이나 sibling `model_store` 경로를 import/탐색하지 않는다. Operations 로컬 데모에서 Artifact가 주입되지 않은 경우에만 기존 deterministic heuristic을 명시적 compatibility fallback으로 유지한다.

ML authoring compatibility port는 generator-capable 개발/통합 배포에서만 실제 generator 구현을 지연 로드한다. 일반 Backend startup과 diagnosis runtime은 generator package 없이도 import 가능하도록 유지한다.

### API / Frontend / Report

PR #11에서 기존 root `api/`와 `web/` 실행 host를 각각 `systems/backend`와 `systems/frontend`로 수렴시켰다. Backend API의 실제 Operations Evidence 경로는 `systems/backend/app/diagnosis`를 호출하며, Frontend는 backend 도메인 폴더 구조와 1:1 재배치하지 않고 사용자 workflow 중심 구조를 유지한다.

## Generator internal daemon의 허용/금지 범위

`systems/generator`의 책임 끝점은 versioned Model Artifact publish까지다. 이 경계를
구체적으로 판정하기 위해 Generator internal daemon(학습 daemon)의 허용/금지 범위를
명문화한다. 상세 아키텍처 결정과 책임 분리 근거는 `docs/architecture-decisions/ADR-002-training-runtime-prediction-ownership.md`를 따른다.

**허용**

- `GET /health`
- `POST /internal/train`
- `POST /internal/retrain`
- 학습 job 상태 또는 Model Artifact publish 상태 조회

**금지**

- 사용자 요청 기반 runtime predict (예: `/internal/predict`, `/internal/predict/file`)
- `PredictionOutput` 등 runtime 응답 형식의 외부 노출
- current telemetry를 운영 목적으로 자동 선택하는 기능
- Product prediction 파일 저장 (예: `data_preprocessed/predictions/*.json`을 제품 저장소로 사용)
- Product Result Artifact/Evidence 생성

또한 다음 용어를 명확히 분리한다.

```text
offline model evaluation           ≠ operational runtime inference
학습 후 검증/스코어링 목적           사용자 요청에 대한 실시간 응답 목적
Generator 책임                      Backend diagnosis 책임
```

이 두 개념을 같은 함수/엔드포인트에서 처리하지 않는다. `offline evaluation`의 결과를
`operational runtime inference`의 응답 형식(`PredictionOutput` 등)으로 감싸는 것도 이 분리를
어기는 것으로 간주한다.

## 기존 `ml/` 처리

기존 `ml/src/factory_signal_ml`에는 training과 runtime prediction/Evidence가 한 패키지에 섞여 있었다. 구현은 각각 `systems/generator`와 `systems/backend/app/diagnosis`로 이동했고, 기존 import와 CLI를 깨지 않기 위한 compatibility adapter만 남겼다.

## 이번 PR에서 의도적으로 유지한 것

- 역할별 PdM view
- Event 기반 Report
- decision / note / activity 흐름
- manager / engineer 역할별 workflow
- 위험 설비와 Evidence 확인 흐름
- Dataset/Governance/ML Validator/Agent 등 확장 코드 자체

확장 화면의 대형 UX 재설계와 모든 기존 대형 service 파일 분해는 이번 책임 재배치의 범위를 넘으므로 후속 작업으로 둔다.

## 회귀 기준

`gen_data` PR #2의 Canonical V3.1 `model_outputs/*`는 운영 입력이 아니라 비교 기준이다. 새 runtime Result Artifact는 binary `failure_within_horizon` 의미, model/dataset provenance, factor 방향과 같은 의미 계약을 비교할 수 있지만 제품 실행이 해당 fixture JSONL을 최신 결과처럼 직접 읽지는 않는다.
