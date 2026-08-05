# Adaptive Modeling release and recovery runbook

이 문서는 governed Adaptive Modeling 기능을 로컬 검증에서 운영 환경으로 옮길 때 필요한
설정, 실행 순서, 승인 경계, 복구와 backup/restore 절차를 정의한다.

## 1. Release 상태의 의미

- **local release pass**: 계약, SQLite/PostgreSQL repository, RLS, controlled E2E,
  frontend typecheck/build와 Canonical v3.1 불변성 검증이 통과했다.
- **strict release pass**: local pass에 더해 production PostgreSQL, artifact root,
  Project 3/Neo4j endpoint와 필요한 optional model/explanation dependency가 실제 환경에서
  준비됐다.
- 외부 환경변수나 credential이 없으면 `blocked`이며 성공으로 간주하지 않는다.

검증:

```bash
.venv/bin/python scripts/verify_adaptive_modeling_release.py \
  --root . \
  --canonical-package-root /absolute/path/to/predictive_maintenance_canonical_v3.1 \
  --project3-root /absolute/path/to/mvp-프로젝트3 \
  --run-tests \
  --output artifacts/release/adaptive-modeling-release.json
```

strict 판정이 필요한 환경에서는 `--strict`를 추가한다.

## 2. 필수 환경

```bash
export ONTOLOGY_DASHBOARD_DATABASE_URL='postgresql://...'
export ONTOLOGY_DASHBOARD_MODELING_ARTIFACT_ROOT='/durable/modeling-artifacts'
export ONTOLOGY_DASHBOARD_DATA_ROOTS='/approved/intake/root-1:/approved/intake/root-2'
export ONTOLOGY_DASHBOARD_PROJECT3_URL='http://project3:8000'
export ONTOLOGY_DASHBOARD_NEO4J_URI='neo4j://neo4j:7687'
```

`ONTOLOGY_DASHBOARD_MODELING_ARTIFACT_ROOT`는 API와 worker가 동일하게 읽고 쓸 수 있는
durable filesystem이어야 한다. 임시 디렉터리나 컨테이너 ephemeral layer를 사용하지
않는다.

LightGBM, XGBoost, SHAP은 optional capability다. 설치되지 않은 알고리즘은 후보에
`blocked`로 나타나고 해당 Model Version의 promotion/activation이 거부된다. Dummy,
Logistic Regression, Random Forest baseline은 optional dependency 없이 동작한다.

### 2.1 Local PostgreSQL과 Canonical V3.1 bootstrap

기존 PostgreSQL 설치·container·volume이 유효하면 삭제하지 않는다. 새 환경은 공식
Compose profile을 사용할 수 있다.

```bash
cd infra
docker compose --profile polyglot up -d postgres
```

ignored `.env`에 loopback 전용 URL과 artifact root를 설정한다. 실제 password는 문서나
Git tracked 파일에 기록하지 않는다.

```dotenv
ONTOLOGY_DASHBOARD_DATABASE_URL=postgresql://<user>:<password>@127.0.0.1:5432/ontology_dashboard
ONTOLOGY_DASHBOARD_MODELING_ARTIFACT_ROOT=/absolute/durable/path
```

migration과 idempotent demo 적재:

```bash
export PYTHONPATH="$PWD/api:$PWD/ml/src"
.venv/bin/python -m ontology_dashboard.migrations
.venv/bin/python scripts/bootstrap_predictive_maintenance_v3_1_demo.py \
  --package-root "/absolute/path/to/predictive_maintenance_canonical_v3.1" \
  --organization-id org-ontology-demo \
  --project-id manufacturing-demo-project \
  --workspace-id manufacturing-demo \
  --database-url "$ONTOLOGY_DASHBOARD_DATABASE_URL" \
  --skip-graph
```

검증만 다시 수행할 때는 `--verify-only`, materialization을 명시적으로 재생성할 때만
`--force-rematerialize`를 추가한다. 정상 출력은 Dataset
`dsv-9fc144c7-d3f8-5b37-8465-04248165b7ce`, source
`canonical-ai4i-physics-v3.1`, model `independent-logreg-v3.1`, 100 Result Artifacts,
68,208 timeline rows, relational `ready`를 포함한다.

기본 선택 정책은 (1) 현재 project/workspace의 published·release-ready V3.1,
(2) 같은 scope의 최신 published predictive-maintenance version, (3) Gold Fixture
fallback 순이다. 사용자의 명시 선택은 별도 RLS table에 유지된다. Neo4j/Project 3이
없거나 인증에 실패해도 graph만 `pending/blocked`로 표시하고 relational API를 500으로
실패시키지 않는다.

production build 후 표준 pid/log로 재시작한다.

```bash
npm --prefix web run build
bash scripts/restart_local_services.sh
```

PID는 `/tmp/ontology-dashboard-{api,web}.pid`, 로그는
`/tmp/ontology-dashboard-{api,web}.log`에 기록된다.

## 3. Source onboarding

### 3.1 Dataset Intake Profile

허용된 root 안의 CSV/TSV/XLSX만 profile한다. symlink traversal과 root 밖 파일은
거부된다. cache identity는 filename이 아니라 전체 source SHA-256과 parser version이다.

```text
POST /api/modeling/intake/profile
```

bounded preview에는 민감값 redaction이 적용된다. profile은 Dataset Version이 아니며
기존 Dataset Catalog를 수정하지 않는다.

### 3.2 Manifest Draft 승인

```text
POST  /api/modeling/intake/{profile_id}/manifest-draft
PATCH /api/modeling/manifest-drafts/{draft_id}
POST  /api/modeling/manifest-drafts/{draft_id}/decision
```

identifier, timestamp, group key, label과 제외 필드를 사람이 검토한다. 승인 전에는
ingestion endpoint가 Dataset Version을 만들 수 없다.

### 3.3 기존 Adapter를 통한 Dataset Version 생성

```text
POST /api/modeling/manifest-drafts/{draft_id}/ingest
```

승인된 field alias 전체를 `governed-tabular` adapter가 적용한다. CSV delimiter와 XLSX
sheet가 Manifest에 고정된다. Adapter는 임의 semantic inference나 Python/SQL 표현식을
실행하지 않는다. 결과는 기존 Dataset Catalog의 immutable Dataset Version이다.

## 4. Mapping과 Feature Recipe

### 4.1 Ontology Mapping

Mapping candidate는 현재 Ontology Registry에 존재하는 Object Type/Property만 target으로
사용한다. identifier, timestamp와 label은 confidence가 높아도 자동 승인되지 않는다.

```text
POST /api/modeling/mapping-sets
POST /api/modeling/mapping-sets/{id}/candidates/{candidate_id}/decision
POST /api/modeling/mapping-sets/{id}/decision
GET  /api/modeling/mapping-sets/{id}/capabilities
```

`predictive_training` readiness에는 group key, timestamp, measure와 label이 모두 필요하다.

### 4.2 Feature Recipe Set

각 recipe에는 version/checksum, ontology property, operation, group/order, source grain,
null/boundary/leakage policy와 output datatype/unit을 기록한다.

지원되는 계산은 allowlist operation만 가능하며 arbitrary expression은 실행하지 않는다.
rolling, lag와 diff 상태는 equipment boundary에서 초기화된다. label은 observation time과
horizon policy로 계산하며 `evaluation_truth`와 `hidden_truth`는 금지된다.

```text
POST /api/modeling/feature-recipe-sets
POST /api/modeling/feature-recipe-sets/{id}/decision
POST /api/modeling/feature-datasets/materialize
```

Feature Dataset Version은 source Dataset과 별도 immutable artifact/checksum을 갖는다.

## 5. Experiment worker

HTTP는 Experiment Run을 queue할 뿐 학습하지 않는다.

```text
POST /api/modeling/experiments
```

worker 실행:

```bash
.venv/bin/python scripts/run_modeling_experiment_worker.py \
  --database "$ONTOLOGY_DASHBOARD_DATABASE_URL" \
  --artifact-root "$ONTOLOGY_DASHBOARD_MODELING_ARTIFACT_ROOT" \
  --organization-id ORG_ID \
  --project-id PROJECT_ID \
  --workspace-id WORKSPACE_ID \
  --experiment-id EXPERIMENT_ID \
  --worker-id modeling-worker-1
```

split은 group chronological train/validation/test이며 test는 candidate/threshold 선택에
사용하지 않는다. Dummy baseline은 항상 포함된다. 선택 기준은 validation Average
Precision이고 held-out test는 selected candidate에만 계산된다.

운영 threshold는 validation curve에서 recall constraint 또는 FN/FP cost policy로
선택한다. 기본 0.5 confusion matrix와 운영 threshold 결과는 서로 다른 해석이므로 UI와
보고서에서 혼합하지 않는다.

### 취소와 worker crash 복구

```text
POST /api/modeling/experiments/{id}/cancel
POST /api/modeling/experiments/{id}/recover-stale
POST /api/modeling/experiments/{id}/retry
```

`recover-stale`는 `updated_at`이 정책 시간을 초과한 `running` run만 failed로 전환한 뒤
동일 identity를 queue 상태로 되돌린다. 현재 별도 heartbeat registry는 없으므로 worker
supervisor가 stale recovery를 호출해야 한다.

## 6. Model release와 rollback

Model Version 등록 시 다음 gate를 모두 다시 검증한다.

- succeeded Experiment와 immutable report identity
- selected candidate artifact checksum
- validation metrics와 held-out test metrics
- Dummy baseline 대비 validation Average Precision 개선
- validation-only selection과 최소 recall threshold
- approved Mapping/Feature Recipe
- Feature Dataset lineage/checksum
- algorithm runtime capability
- evaluator-only truth 비노출
- unresolved recipe governance blocker 없음

흐름:

```text
POST /api/modeling/model-versions
POST /api/modeling/model-versions/{id}/release-requests   # ml_validator
POST /api/modeling/release-requests/{id}/decision         # tenant_admin
POST /api/modeling/model-versions/{id}/activate           # tenant_admin
POST /api/modeling/model-versions/{id}/rollback           # tenant_admin
```

activation은 transaction 안에서 동일 prediction task의 기존 active model을 retired로
전환하고 target을 active로 만든다. PostgreSQL에서는 `FOR UPDATE`, SQLite에서는
`BEGIN IMMEDIATE`로 concurrent activation을 막는다.

rollback target은 approved 또는 retired Model Version이어야 하고 동일한 atomic activation
경로를 사용한다.

## 7. Scoring과 Explanation

active Model Version만 scoring할 수 있다. request의 input feature set과 schema checksum이
training artifact와 일치해야 한다.

```text
POST /api/modeling/model-versions/{id}/score
GET  /api/modeling/explanations/{explanation_id}
```

scoring은 Adaptive Model Score와 Explanation Artifact뿐 아니라 기존 Prediction Result
repository에도 결과를 저장한다.

- probability: 모델의 failure probability
- threshold: 승인된 operational decision policy
- confidence: calibration/agreement 근거가 없으면 `null`
- predicted label: `failure_risk | no_significant_risk`
- recommended action: 승인 필요 policy recommendation이며 WorkOrder를 만들지 않음
- local contribution: 해당 observation의 local explanation이며 causal proof가 아님

Explanation provider가 실패해도 prediction은 유지되고 explanation status/reason이
`unavailable`로 반환된다.

## 8. Backup과 restore

### PostgreSQL metadata

backup:

```bash
pg_dump "$ONTOLOGY_DASHBOARD_DATABASE_URL" \
  --format=custom \
  --file adaptive-modeling-metadata.dump \
  --table 'modeling_*' \
  --table prediction_results \
  --table datasets \
  --table dataset_versions \
  --table dataset_files
```

restore 전 migration을 동일 version까지 적용한 뒤:

```bash
pg_restore --dbname "$ONTOLOGY_DASHBOARD_DATABASE_URL" \
  --clean --if-exists adaptive-modeling-metadata.dump
```

### Artifact root

artifact root를 metadata DB와 동일 checkpoint에서 snapshot한다.

```bash
tar --xattrs --acls -czf adaptive-modeling-artifacts.tgz \
  -C "$(dirname "$ONTOLOGY_DASHBOARD_MODELING_ARTIFACT_ROOT")" \
  "$(basename "$ONTOLOGY_DASHBOARD_MODELING_ARTIFACT_ROOT")"
```

restore 후 Model Version, Feature Dataset Version과 Experiment artifact의 SHA-256을
repository 값과 대조한다. checksum mismatch artifact는 절대 load하지 않는다.

restore 순서는 Dataset metadata → modeling metadata → artifact root → worker/API다.

## 9. Known production limitations

아래는 local release를 실패시키지 않지만 production readiness에서 명시적으로 확인해야
하는 항목이다.

1. ML Validator Workbench는 experiment/model validation과 release UI를 제공한다. Source
   upload, mapping 편집과 recipe authoring은 현재 API와 Dataset/Governance 화면을 함께
   사용한다.
2. worker는 one-shot CLI이며 daemon scheduler와 heartbeat registry는 별도 운영 구성이
   필요하다. stale recovery endpoint는 제공된다.
3. 현재 artifact store 구현은 durable local/shared filesystem이다. S3/GCS object-store
   adapter는 구현되지 않았다.
4. LightGBM, XGBoost와 SHAP은 설치되지 않으면 blocked다. baseline algorithms은 동작한다.
5. governed calibration artifact가 없으면 confidence는 unavailable이다.
6. operational drift/outcome artifact가 연결되지 않았으며 offline metric을 대신 표시하지
   않는다.
7. synthetic controlled E2E는 production predictive quality를 보증하지 않는다.
8. 현재 공유 개발 서버의 graph projection은 Neo4j credential 불일치와 Project 3 미실행으로
   pending이다. relational V3.1 runtime은 ready다.
9. 현재 ML Validator에는 live intake/mapping/recipe/feature Dataset이 없어 5개 prerequisite
   missing으로 blocked다. Controlled E2E metric을 live 상태로 해석하지 않는다.
