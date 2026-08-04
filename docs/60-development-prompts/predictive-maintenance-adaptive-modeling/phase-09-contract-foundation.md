# Phase 09 — Adaptive Modeling Contract and Persistence Foundation

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

다음 두 경로는 참고용으로만 열고 수정하지 마.

V3.1 package:
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1

team prototype:
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/prototype_share

각 경로를 한 번씩만 open_workspace하고 workspaceId를 구분해 재사용해.

이번 Phase는 반드시 Predictive Maintenance Canonical v3.1 Phase 8 완료 후 실행한다.
먼저 프로젝트2의 코드, DB artifact, release report, Git 이력을 확인해 Phase 0~8이
실제로 완료됐는지 검증해. Phase 8이 완료되지 않았으면 Adaptive Modeling 구현을
시작하거나 우회하지 말고, 정확한 미완료 항목과 마지막 정상 commit을 보고하고
중단해.

먼저 다음을 읽어줘.

- docs/30-implementation/predictive-maintenance-adaptive-modeling-integration-plan.md
- docs/60-development-prompts/predictive-maintenance-adaptive-modeling/README.md
- docs/60-development-prompts/predictive-maintenance-canonical-v3.1/phase-08-governance-release.md
- Phase 8에서 생성한 release report와 commit
- docs/20-architecture/system-architecture.md
- docs/20-architecture/architecture-decisions.md
- docs/20-architecture/predictive-maintenance-projection-contract.md
- docs/20-architecture/project3-adapter-contract.md
- docs/10-product/dataset-strategy.md
- docs/10-product/model-baseline-results.md
- schemas/dataset-manifest.schema.json
- schemas/dataset-bundle-manifest.schema.json
- schemas/prediction-result.schema.json
- schemas/evidence-package.schema.json
- api/ontology_dashboard/datasets/
- api/ontology_dashboard/adapters/
- api/ontology_dashboard/ontology_planner_models.py
- api/ontology_dashboard/ontology_planner_service.py
- api/ontology_dashboard/role_workflow_models.py
- api/ontology_dashboard/role_workflow_service.py
- api/ontology_dashboard/governance/
- api/migrations/postgresql/
- ml/README.md
- ml/src/factory_signal_ml/
- prototype_share의 extraction planner, mapping store/agent, capability detector,
  feature catalog, label builder, model registry, training, prediction, SHAP 구현

프로젝트2에서 `git status --short --branch`, `git log -12 --oneline`, remote tracking을
확인해. 다른 세션의 미커밋 변경을 삭제·덮어쓰기·stage하지 마. 현재 Phase 파일만
stage해.

이번 목표는 prototype_share 코드를 복사하는 것이 아니라, 향후 Dataset Intake,
Ontology Mapping, Feature Recipe, Experiment Run, Model Registry, Explanation Artifact가
공통으로 사용할 typed contract와 persistence foundation을 프로젝트2에 추가하는 것이다.

구현 범위:

1. Modeling bounded context
   - `api/ontology_dashboard/modeling/` 또는 현재 구조에 맞는 단일 canonical namespace
   - models, repository, service, router의 책임 분리
   - Dataset/Adapter/Ontology/Prediction/Role Workflow 기존 책임을 중복 구현하지 않음
   - Project 3 graph/RAG/Text-to-Cypher 로직을 추가하지 않음
2. JSON Schema 계약
   - Dataset Intake Profile
   - Manifest Draft
   - Ontology Mapping Candidate/Decision
   - Capability Requirement Evaluation
   - Feature Recipe와 Feature Recipe Set
   - Feature Dataset Version
   - Experiment Run과 Candidate Result
   - Model Version과 Threshold Policy
   - Explanation Artifact
   - schema version, organization/project/workspace scope, Dataset Version lineage 포함
3. Typed domain model
   - immutable identity와 status transition
   - draft/approved/rejected/superseded
   - queued/running/succeeded/failed/cancelled
   - candidate/approved/active/retired/rejected
   - unknown status 문자열 금지
4. Additive PostgreSQL foundation
   - 현재 migration 번호를 확인한 후 다음 unused 번호 사용
   - 이미 적용된 migration 수정 금지
   - profile/draft/recipe/feature-dataset/experiment/model/explanation metadata를 저장할
     테이블 또는 기존 repository extension
   - JSONB만 던져 넣지 말고 identity, scope, checksum, status, timestamps, version,
     foreign key를 query 가능한 column으로 보존
   - large model binary나 feature matrix를 DB JSONB에 저장하지 않음
   - artifact URI/checksum metadata만 저장
5. Repository와 tenant isolation
   - organization_id, project_id, workspace_id가 모든 root aggregate에 존재
   - Dataset Version, recipe, experiment, model 간 cross-project reference 금지
   - idempotency key와 unique identity
   - optimistic revision 또는 명시적 transition guard
6. Permission boundary
   - 기존 `ml.console.read`, `ml.release.request`, `datasets.read`, `datasets.ingest`,
     `governance.read`를 우선 재사용
   - 필요한 경우 최소 권한만 additive하게 추가
   - model activation과 release approval은 tenant-admin 경계를 유지
7. Artifact store port
   - local filesystem path를 canonical identity로 쓰지 않음
   - portable artifact URI, SHA-256, media type, size, created_at
   - local implementation은 configured artifact root 밖 접근 금지
   - object storage가 없으면 capability를 blocked로 표시할 수 있는 port
8. Architecture documentation
   - Adaptive Modeling bounded context와 기존 Dataset/Ontology/Prediction 경계
   - prototype_share에서 concept만 채택하고 복사하지 않는 항목
   - synchronous `/api/train`을 만들지 않는 이유
   - `mcp_tools` 명칭을 사용하지 않는 이유
   - LLM deterministic-first/registry-bound 원칙

이번 Phase에서는 실제 파일 profiling, mapping 추천, feature 계산, 모델 학습, SHAP
계산, 새 UI를 구현하지 마. 이후 Phase의 계약과 저장소 기반만 완성해.

계약에서 반드시 지킬 의미:

- probability, calibrated confidence, threshold policy는 다른 field다.
- model artifact local path는 model identity가 아니다.
- Dataset Version은 immutable하다.
- Feature Dataset Version은 source Dataset Version을 수정하지 않는다.
- recommended action은 승인·실행된 WorkOrder가 아니다.
- binary model task를 AI4I failure mode multiclass로 확장하지 않는다.
- evaluation truth/hidden truth는 user-facing contract에 포함하지 않는다.

필수 검증:

- 모든 신규 JSON Schema Draft 2020-12 validation
- Pydantic/domain model과 JSON Schema example parity
- status transition positive/negative tests
- additive migration apply와 rollback-safe schema inspection
- repository idempotency와 duplicate identity test
- tenant/project/workspace cross-reference 차단
- 다른 Dataset Version의 recipe/experiment/model 연결 차단
- artifact root traversal 차단
- unknown fields/status/schema version 거부
- existing V2/V3.1 Dataset, Prediction Result, governance tests regression
- docs structure check
- git diff --check

전체 frontend build, Playwright, visual regression은 실행하지 마. 이번 Phase는 backend
contract foundation만 검증해.

검증 완료 후 이번 단계 관련 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: add adaptive modeling contract foundation"
- git push origin HEAD

push 실패 시 reset/rebase/force push 없이 오류와 로컬 commit hash를 보고해.

마지막 보고:

- Phase 8 완료 근거
- 신규 bounded context와 책임 경계
- schema와 table 목록
- status transition과 isolation 결과
- artifact identity 방식
- prototype_share에서 채택/비채택한 개념
- 변경 파일과 테스트 결과
- commit hash와 push 결과
- Phase 10이 사용할 service/repository contract
````
