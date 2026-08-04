# Phase 00 — Contract Freeze

> **완료 기록 — 재실행하지 않음.** 완료 커밋: `1aa0251`. 이 파일은 V2에서
> 시작한 immutable contract의 역사적 근거로만 보존한다.

아래 전체를 새 세션에 붙여넣는다.

```text
@devspace-codex

다음 로컬 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

데이터 패키지도 읽기 전용으로 함께 확인해줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v2

가장 먼저 아래 문서를 처음부터 끝까지 읽어줘.

- docs/30-implementation/predictive-maintenance-canonical-v2-integration-plan.md
- docs/10-product/dataset-strategy.md
- docs/20-architecture/system-architecture.md
- docs/20-architecture/architecture-decisions.md의 ADR-013, ADR-014, ADR-017 관련 부분
- schemas/dataset-manifest.schema.json
- schemas/prediction-result.schema.json
- api/ontology_dashboard/adapters/models.py
- api/ontology_dashboard/datasets/models.py

작업 시작 전에 반드시 다음을 확인해줘.

- git status --short --branch
- git log -5 --oneline
- 현재 branch와 remote tracking 상태
- 다른 세션의 미커밋 변경 파일

다른 세션의 미커밋 변경은 삭제하거나 덮어쓰거나 이번 커밋에 포함하지 마. 특히 현재 단계와 관계없는 web/vite.config.ts 변경이 남아 있다면 그대로 보존해.

이번 세션의 목표는 구현 전 계약을 고정하는 것이다. 다음 내용을 실제 schema, typed model, 문서와 테스트로 확정해줘.

1. Dataset Bundle Manifest v2
   - 하나의 Dataset Version에 여러 파일을 role로 묶기
   - manifest_version, manifest_id, organization_id, project_id, workspace_id
   - adapter_code, dataset_name, dataset_version
   - bundle_checksum_sha256
   - files[].role, uri, format/media_type, checksum_sha256, size_bytes, schema/version metadata
   - source_contract와 generator/schema version
2. bundle checksum canonicalization
   - 로컬 절대 경로와 파일 순서에 영향받지 않기
   - dataset version, role별 checksum, generator version, schema version, source-contract flag를 정렬해 계산
3. identity 규칙
   - Project, Workspace, Dataset, Dataset Version
   - PostgreSQL object identity
   - Neo4j projection identity
   - source reference 형식
4. runtime source와 evaluation truth 분리
   - canonical/evaluation_truth가 runtime files 목록에 들어갈 수 없게 validation
   - truth leakage negative test
5. Project 3 graph projection request/response 계약 초안
   - 아직 구현하지 말고 프로젝트2가 기대하는 typed payload와 상태·오류 contract를 문서/schema로 고정

권장 산출물:

- schemas/dataset-bundle-manifest.schema.json
- api/ontology_dashboard/adapters/bundle_models.py 또는 기존 models.py의 명확한 확장
- docs/20-architecture/predictive-maintenance-projection-contract.md
- tests/test_predictive_maintenance_bundle_contract.py
- 필요한 README/schema registry 갱신

이번 단계에서는 PostgreSQL fact table, COPY ingestion, Ontology materialization, Neo4j write, Dashboard UI를 구현하지 마.

검증은 현재 단계에 맞게 수행해줘.

- 새 schema JSON 파싱 및 기존 schema 검사
- Pydantic model validation test
- 같은 내용·다른 파일 순서·다른 절대 경로의 bundle checksum 동일성 test
- checksum, seed, 기간, schema가 바뀌면 다른 bundle checksum이 되는 test
- evaluation truth가 runtime manifest에 포함되면 실패하는 negative test
- python scripts/preflight.py
- git diff --check

검증 실패는 원인을 수정한 후 다시 실행해. 현재 단계와 무관한 전체 visual regression이나 전체 release gate는 실행하지 마.

검증 완료 후 다음 Git 작업까지 직접 수행해줘.

1. git diff와 git status를 다시 확인
2. 이번 단계 관련 파일만 git add
3. 커밋 메시지: feat: freeze predictive maintenance bundle contracts
4. git commit
5. git push origin HEAD

다른 세션의 변경은 stage하지 마. push 실패 시 rebase, reset, force push를 하지 말고 정확한 오류와 로컬 commit hash를 보고해.

마지막 보고에는 다음을 포함해줘.

- 확정한 계약과 identity 규칙
- 추가·수정 파일
- 실행한 검증과 결과
- commit hash와 push 결과
- Phase 1에서 바로 구현해야 할 항목
```
