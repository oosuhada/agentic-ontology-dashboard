# Predictive Maintenance Adaptive Modeling Engine Integration Plan

- 작성일: 2026-08-04
- 대상 프로젝트: `/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2`
- 선행 완료 조건: `predictive-maintenance-canonical-v3.1` Phase 0~8 완료
- 기준 데이터 패키지: `/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1`
- 참고 프로토타입: `/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/prototype_share`
- 실행 프롬프트: `docs/60-development-prompts/predictive-maintenance-adaptive-modeling/`

---

## 1. 포지셔닝

두 구현은 경쟁 MVP가 아니라 다음 두 계층으로 결합한다.

### Ontology Dashboard

`agentic-ontology-dashboard` / `mvp-프로젝트2`는 다음을 담당한다.

- Dataset Version과 Ontology governance
- 역할별 Dashboard와 Analysis Workbench
- Prediction Result와 Evidence 소비
- 의사결정, 승인, WorkOrder, 보고서
- tenant/project/workspace 격리
- PostgreSQL 운영 원장과 Project 3 graph capability 연결

제품 포지셔닝:

> **온톨로지 기반 운영 대시보드·의사결정 플랫폼**

### Adaptive Modeling Engine

`prototype_share`의 장점은 제품 UI가 아니라 데이터 분석과 모델링 파이프라인의 아이디어다.
이를 프로젝트2의 계약과 governance에 맞게 다시 구현한다.

권장 포지셔닝:

> **데이터 적응형 예지보전 모델링 엔진**

확장 설명:

> 데이터 구조 프로파일링, 온톨로지 매핑 승인, 의미 기반 특성 생성, 시간 인지형 모델
> 실험·평가, 모델 승격과 설명 산출물을 제공하는 governed predictive-maintenance
> modeling pipeline.

`prototype_share` 코드를 별도 제품으로 병합하거나 UI를 이식하지 않는다. 개념적으로
가치가 있는 요소를 프로젝트2의 기존 Dataset, Ontology, Prediction Result, RBAC,
PostgreSQL, Dashboard 경계 안에서 재구현한다.

---

## 2. Phase 8 이후에 시작해야 하는 이유

Phase 0~8은 V3.1 immutable Dataset Version을 제품에 안전하게 연결하는 vertical이다.

```text
V3.1 bundle
→ PostgreSQL ingestion
→ Ontology materialization
→ Project 3 / Neo4j projection
→ Result Artifact / replay
→ semantic visualization
→ role dashboard
→ governance release
```

Adaptive Modeling Engine은 이 vertical 위에서 새 모델과 feature를 생성하는 producer다.
Phase 8 이전에 모델링 트랙을 병행하면 다음 경계가 계속 변해 중복 구현과 lineage 손상이
발생할 수 있다.

- Dataset Version identity
- Result Artifact와 Prediction Result 의미
- binary prediction task
- ontology property와 semantic field catalog
- V2/V3.1 rollback과 release evidence
- model release approval workflow

따라서 Phase 8에서 위 경계를 고정한 후 Phase 9부터 확장한다.

---

## 3. 프로토타입 진단과 통합 대응

| 프로토타입 요소 | 잘한 점 | 현재 결함 | 프로젝트2 통합 방식 |
|---|---|---|---|
| 2단계 extraction planner | 파일 구조 판별과 컬럼 선택을 분리 | preview fingerprint, 약한 JSON 검증, 자동 제외 | 전체 checksum 기반 Dataset Intake Profile과 Manifest Draft Assistant |
| mapping cache | 반복 LLM 호출 감소 | ontology vocabulary가 작고 잘못된 high-confidence 자동 매핑 | registry-bound 후보, datatype/unit/grain, 중요 키 승인 workflow |
| capability detector | 데이터에 따라 기능을 활성화하려는 방향 | node 하나만 있으면 capability 활성화 | identifier/time/relation/measure prerequisite bundle 검증 |
| YAML feature catalog | 원본 컬럼 대신 의미 개념으로 feature recipe 적용 | 설비 경계 혼합, 시간 정렬 부재, version 없음 | group/order/leakage 정책을 가진 versioned Feature Recipe Registry |
| 24시간 label builder | horizon 기반 예지보전 label 개념 | event boundary와 split leakage 검증 없음 | label policy version, temporal cutoff, embargo, audit artifact |
| LightGBM/XGBoost/RF registry | 공통 모델 인터페이스와 후보 비교 방향 | 기본 파라미터 전체 학습, baseline·validation·선택 기준 없음 | Experiment Run, temporal/group split, baseline, calibration, threshold policy |
| SHAP output | 결과 설명을 계약에 넣으려는 방향 | 중복 구현, 마지막 행만 설명, version·UI 연결 없음 | Explanation Artifact provider와 ML Validator drill-down |
| JSON model registry | 모델 artifact와 metadata를 분리 | OS 종속 경로, checksum·환경·승격 상태 없음 | PostgreSQL governed Model Registry와 immutable artifact identity |
| synchronous `/api/train` | 데모 흐름이 단순 | 장시간 HTTP 요청, 격리·retry·audit 없음 | queued experiment run과 worker/CLI execution boundary |
| 3-model cards | 모델별 결과 비교가 직관적 | metric 없이 확률만 비교 | PR-AUC, Recall, calibration, threshold, slice를 비교하는 ML Validator UI |
| `mcp_tools` 명칭 | source connector 의도를 표현 | 실제 MCP protocol/server가 아님 | 프로젝트2 Adapter/Intake namespace를 사용하고 MCP라고 주장하지 않음 |

---

## 4. 목표 아키텍처

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Dataset Intake Plane                                                 │
│ source profile → manifest draft → human approval → existing Adapter │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ immutable Dataset Version
┌────────────────────────────────▼─────────────────────────────────────┐
│ Semantic & Feature Plane                                             │
│ ontology mapping candidates → approval → feature recipes → feature  │
│ dataset version                                                     │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ governed training matrix
┌────────────────────────────────▼─────────────────────────────────────┐
│ Experiment Plane                                                     │
│ split policy → candidate training → metrics → calibration/threshold │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ selected candidate
┌────────────────────────────────▼─────────────────────────────────────┐
│ Registry & Serving Plane                                             │
│ model artifact → release request → approval → Prediction Result     │
│                                            → Explanation Artifact    │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
┌────────────────────────────────▼─────────────────────────────────────┐
│ Product Experience & Governance                                     │
│ ML Validator → Dashboard/Evidence → audit → rollback/reproducibility │
└──────────────────────────────────────────────────────────────────────┘
```

### 책임 경계

| 영역 | 소유자 |
|---|---|
| source checksum, manifest, Dataset Version | 프로젝트2 Dataset/Adapter layer |
| ontology registry와 mapping approval | 프로젝트2 Ontology/Governance layer |
| feature recipe execution | `ml/` package와 typed backend orchestration |
| experiment training/evaluation | `ml/` package, queued worker/CLI |
| experiment/model metadata | 프로젝트2 PostgreSQL repository |
| graph/RAG/Text-to-Cypher | 프로젝트3, 기존 typed boundary 유지 |
| operational prediction contract | 프로젝트2 Prediction Result/Result Artifact |
| 모델 비교·승격 UI | 프로젝트2 ML Validator role workspace |

Project 3에 training, feature engineering, model registry를 추가하지 않는다. 프로젝트2에
Neo4j ingestion이나 Text-to-Cypher 로직을 복제하지 않는다.

---

## 5. 핵심 계약

## 5.1 Dataset Intake Profile

처음 보는 source를 바로 ingest하지 않고 안전한 profile을 생성한다.

필수 항목:

- source identity와 full SHA-256
- media type, encoding, delimiter, sheet
- header row와 structure type
- row/column count 또는 bounded estimate
- field name, inferred datatype, null ratio, distinct estimate
- timestamp/identifier/group-key 후보
- unit 후보와 sample value summary
- parser version과 profile checksum
- excluded/sensitive field 후보
- deterministic result와 optional LLM suggestion을 분리

profile cache key는 preview가 아니라 `source_checksum + parser_version`이다.

## 5.2 Manifest Draft

- 기존 `DatasetManifest`로 변환 가능한 초안
- source field와 canonical field 후보
- required field 누락과 quality rule suggestion
- confidence와 rationale
- `draft`, `approved`, `rejected`, `superseded` 상태
- 승인 전 ingest 금지
- 승인자, 승인 시각, audit event

## 5.3 Ontology Mapping Candidate

- source field identity
- target object/property identity
- datatype, unit, grain
- identifier/time/group role
- source: rule, metadata, LLM suggestion, user confirmation
- confidence와 evidence
- mapping status와 mapping version
- Dataset Version scope

LLM은 등록되지 않은 object/property를 생성할 수 없다.

## 5.4 Capability Requirement

capability는 단일 node가 아니라 prerequisite bundle로 평가한다.

예시:

```text
predictive_training
  equipment identifier
  ordered timestamp
  numeric sensor measure >= 1
  label/event policy
  group/time continuity validation

maintenance_context
  equipment identifier
  maintenance timestamp
  maintenance type/action
  equipment-event join key
```

각 결과에는 `ready`, `degraded`, `blocked`와 누락 prerequisite를 반환한다.

## 5.5 Feature Recipe

- recipe id/version/checksum
- ontology property input
- operation: rolling, lag, diff, EMA, derived expression 등
- group_by
- order_by
- window/period/minimum history
- null and boundary policy
- allowed source grain
- leakage policy
- output datatype/unit
- training/serving parity version

rolling/lag 연산은 equipment 단위로 정렬한 후 수행한다. 서로 다른 설비의 observation이
같은 window에 포함되면 release gate 실패다.

## 5.6 Feature Dataset Version

- source Dataset Version
- mapping version
- feature recipe set version/checksum
- label policy version
- materialization checksum
- row/feature count
- time range와 equipment coverage
- leakage/continuity validation summary

원본 Dataset Version을 수정하지 않고 별도 immutable artifact로 관리한다.

## 5.7 Experiment Run

- experiment id, project/workspace scope
- Dataset Version과 Feature Dataset Version
- split policy, seed, cutoff, embargo
- candidate specification과 dependency capability
- metrics와 confusion matrix
- calibration metrics
- threshold curve와 cost assumptions
- slice metrics
- artifact checksum과 environment lock
- queued/running/succeeded/failed/cancelled 상태

기본 시계열 split은 equipment별 chronological holdout이다. random row split은 명시적
benchmark 목적 외 기본값으로 사용하지 않는다.

## 5.8 Model Version

- selected experiment candidate
- model artifact checksum과 portable URI
- library/runtime versions
- input feature contract
- Dataset/Feature Recipe/Label Policy lineage
- calibration method
- threshold policy
- explanation method/version
- candidate, approved, active, retired, rejected 상태
- release request/approval/audit

모델 파일의 로컬 OS 경로를 canonical identity로 사용하지 않는다.

## 5.9 Explanation Artifact

- prediction/result identity
- model version과 explanation provider/version
- feature recipe lineage
- top factors와 direction/contribution
- observed value, unit, reference range
- generated timestamp와 checksum
- explanation availability/failure reason

Tree SHAP, linear coefficient contribution 등 모델별 구현을 provider 뒤에 감추고
Prediction Result 소비자는 공통 계약만 사용한다.

---

## 6. 모델 평가 정책

### 필수 후보

- Dummy prior baseline
- Logistic Regression baseline
- Random Forest

### capability 기반 후보

- LightGBM
- XGBoost

LightGBM/XGBoost dependency가 현재 Python/runtime에서 지원되지 않으면 platform 전체를
실패시키지 않는다. 해당 후보를 `blocked_dependency`로 기록하고 baseline 후보의 실험은
계속 수행한다. 지원 환경에서는 동일 계약으로 실행한다.

### 필수 평가 지표

- PR-AUC / Average Precision
- ROC-AUC
- Precision
- Recall
- F1
- confusion matrix
- positive prediction rate
- calibration curve 또는 Brier score
- equipment/site/product type 등 허용 slice metrics

Accuracy는 희소 고장 데이터의 primary selection metric으로 사용하지 않는다.

### threshold 정책

- validation set에서만 선택
- minimum recall constraint
- false-negative/false-positive cost policy
- threshold curve artifact
- final held-out test는 선택에 사용하지 않음

### confidence 의미

`max(probability, 1 - probability)`를 무조건 confidence로 저장하지 않는다.

- calibrated probability가 있으면 calibration provenance와 함께 사용
- explanation stability 또는 ensemble agreement를 confidence로 사용할 경우 별도 field
- 값이 없으면 `unavailable`로 명시

---

## 7. 단계별 구현

| Phase | 파일 | 목표 | 주요 산출물 |
|---:|---|---|---|
| 9 | `phase-09-contract-foundation.md` | 경계·schema·repository foundation | contracts, additive migration, ADR |
| 10 | `phase-10-dataset-intake.md` | 안전한 source profiling과 manifest draft | intake API, parser, approval-ready draft |
| 11 | `phase-11-ontology-mapping-approval.md` | governed mapping과 capability prerequisites | mapping workflow, capability evaluator |
| 12 | `phase-12-feature-recipe-registry.md` | ontology-aware time-safe feature generation | recipes, feature dataset version, leakage gates |
| 13 | `phase-13-experiment-evaluation.md` | time-aware multi-model experiments | worker, metrics, calibration, threshold artifacts |
| 14 | `phase-14-model-registry-promotion.md` | model registry, promotion, serving/explanation | approved model, Prediction Result integration |
| 15 | `phase-15-ml-validator-workbench.md` | 실제 experiment/model 기반 ML Validator UI | leaderboard, curves, lineage, release UI |
| 16 | `phase-16-governance-release.md` | end-to-end governance와 release | E2E evidence, runbook, final release report |

Phase 9~16은 번호 순서대로 실행한다. 각 단계는 이전 단계의 commit과 schema version을
검증하고 현재 단계 변경만 commit/push한다.

---

## 8. 단계별 완료 기준

## Phase 9

- Phase 0~8 release가 실제로 완료됐음을 확인
- 신규 계약이 기존 Dataset/Prediction/Ontology 계약을 덮어쓰지 않음
- additive migration과 typed repository foundation
- prototype의 `mcp_tools` 또는 JSON registry를 제품 namespace로 복사하지 않음

## Phase 10

- CSV와 XLSX의 bounded profile
- full checksum cache identity
- deterministic-first, registry-bound LLM suggestion
- 승인 전 ingest negative test
- file-root, tenant/project/workspace isolation

## Phase 11

- 잘못된 high-confidence auto mapping 방지
- datetime/equipment key 필수 보존
- datatype/unit/grain validation
- mapping approval/supersede/audit
- capability prerequisite bundle과 missing reason

## Phase 12

- equipment별 group/order 연산
- cross-equipment rolling contamination 0
- future leakage 0
- recipe/version/checksum lineage
- training/serving transform parity

## Phase 13

- baseline 포함 candidate evaluation
- chronological/group holdout
- validation-only model/threshold selection
- held-out test report
- failed/blocked candidate가 전체 run을 손상시키지 않음
- synchronous long-running train API 없음

## Phase 14

- portable model artifact identity
- approved model만 active serving 가능
- release request와 tenant-admin approval
- rollback 가능
- Explanation Artifact 공통 계약
- recommended action은 승인/실행된 WorkOrder가 아님

## Phase 15

- fixture heuristic 대신 실제 Experiment Run과 Model Version 표시
- 모델 비교, PR/threshold/calibration/slice/SHAP drill-down
- Dataset/Feature Recipe/Model/Policy lineage
- loading/empty/error/blocked dependency 상태
- desktop/tablet/mobile와 visual regression

## Phase 16

- source → approved manifest → Dataset Version → mapping → feature → experiment → model
  promotion → prediction/explanation → Dashboard 전체 E2E
- V3.1 immutable lineage 보존
- tenant isolation, permission, leakage negative tests
- backup/restore/reproduce runbook
- prototype 진단 항목 closure matrix

---

## 9. 명시적 비범위

- Phase 9~16에서 V3.1 canonical package를 재생성하지 않음
- evaluation truth/hidden truth를 feature 또는 user evidence로 사용하지 않음
- topology edge를 causal label로 사용하지 않음
- binary failure model을 PWF/HDF/OSF/TWF classifier로 오표시하지 않음
- approved mapping 없이 feature generation을 실행하지 않음
- long-running training을 synchronous request thread에서 수행하지 않음
- 모델 수가 많다는 이유만으로 최종 모델을 선택하지 않음
- LLM이 Python, SQL, feature expression, ontology type을 임의 생성하지 않음
- model release approval이 WorkOrder approval을 의미하지 않음
- prototype frontend를 제품 Dashboard에 병합하지 않음

---

## 10. 최종 제품 흐름

```text
새 고객 파일/DB source
→ Dataset Intake Profile
→ Manifest Draft와 사용자 승인
→ 기존 Adapter를 통한 immutable Dataset Version
→ Ontology Mapping Candidate와 승인
→ Feature Recipe Set
→ Feature Dataset Version
→ queued Experiment Run
→ temporal validation + candidate comparison
→ threshold/calibration selection
→ Model Release Request
→ tenant-admin approval
→ active Model Version
→ Prediction Result + Explanation Artifact
→ 역할별 Dashboard / ML Validator / Evidence / Action
```

이 구조가 완료되면 팀원 프로토타입은 별도 저품질 UI MVP가 아니라, 프로젝트2 안에서
실제로 사용 가능한 **governed adaptive predictive-maintenance modeling capability**로
재해석된다.
