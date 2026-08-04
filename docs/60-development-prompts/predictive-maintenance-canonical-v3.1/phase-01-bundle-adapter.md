# Phase 01 — Bundle Adapter

> **완료 기록 — 재실행하지 않음.** 완료 커밋: `4b4d46f`. V2 adapter 명칭은
> backward compatibility를 위한 코드 identity이며 V3.1도 version-aware하게 처리한다.

```text
@devspace-codex

다음 로컬 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

데이터 패키지도 읽기 전용으로 확인해줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v2

가장 먼저 다음을 읽고 Phase 0 계약이 실제 branch에 반영됐는지 확인해줘.

- docs/30-implementation/predictive-maintenance-canonical-v2-integration-plan.md
- docs/60-development-prompts/predictive-maintenance-canonical-v3.1/phase-00-contract-freeze.md
- schemas/dataset-bundle-manifest.schema.json
- Phase 0에서 추가한 bundle model과 tests
- api/ontology_dashboard/adapters/file_adapter.py
- api/ontology_dashboard/adapters/protocol.py
- api/ontology_dashboard/adapters/registry.py
- api/ontology_dashboard/adapters/service.py
- scripts/ingest_dataset.py
- predictive_maintenance_canonical_v2/canonical/dataset/dataset_manifest.json
- predictive_maintenance_canonical_v2/scripts/validate_package.py

시작 전에 git status --short --branch, git log -5 --oneline, remote tracking을 확인하고 다른 세션의 미커밋 변경을 보존해. 현재 단계와 관계없는 파일은 수정·stage·commit하지 마.

이번 목표는 `predictive_maintenance_canonical_v2`의 6개 canonical source와 3개 prediction artifact를 하나의 ingestion run으로 검증하는 Bundle Adapter를 구현하는 것이다.

구현 범위:

1. `PredictiveMaintenanceCanonicalV2Adapter`
   - adapter registry 등록
   - bundle role allowlist와 required role 검증
   - CSV/JSONL format 및 header/key 검증
2. multi-file Bundle File Adapter
   - 모든 파일 접근 정책과 checksum 검증
   - package-level validation을 한 run으로 처리
   - 하나라도 실패하면 bundle 전체 실패
3. cross-file validation
   - asset_master의 asset_id 유일성
   - asset_relation의 from/to asset 참조 무결성
   - observation, cycle, maintenance, prediction의 asset 참조 무결성
   - timestamp parse와 데이터 기간 범위
   - prediction snapshot ↔ factor prediction_id 연결
   - timeline identity와 중복 검증
4. validation report
   - source row count, accepted/quarantined count, role별 checksum과 schema 결과
   - Dataset ingestion artifact로 저장 가능한 typed 결과
5. PostgreSQL 실행 경로 준비
   - 기존 SQLite 전용 CLI를 무리하게 우회하지 말고, bundle 검증과 이후 PostgreSQL ingestion을 호출할 새 CLI entry point를 만든다.
   - 이 단계에서는 fact table COPY를 아직 구현하지 않는다.

권장 파일:

- api/ontology_dashboard/adapters/predictive_maintenance_v2.py
- api/ontology_dashboard/adapters/bundle_file_adapter.py
- api/ontology_dashboard/adapters/registry.py
- api/ontology_dashboard/adapters/service.py
- scripts/ingest_predictive_maintenance_bundle.py
- tests/test_predictive_maintenance_bundle_adapter.py

중요 제약:

- evaluation_truth는 Adapter runtime 입력으로 받지 않는다.
- accepted_records에 432,000개 원시 row를 메모리로 모두 복사하는 설계를 피한다.
- validation과 ingestion을 분리할 수 있는 streaming/iterator 또는 role summary 계약을 사용한다.
- 원본 canonical 파일은 수정하지 않는다.

검증:

- 실제 현재 bundle의 6개 canonical source와 3개 prediction artifact 검증 성공
- source manifest의 현재 row count 및 checksum과 결과 일치
- required file 누락 실패 test
- checksum mismatch 실패 test
- 잘못된 relation asset reference 실패 test
- observation의 unknown asset 실패 test
- prediction factor의 unknown prediction_id 실패 test
- evaluation truth 포함 실패 test
- 같은 bundle 재검증 idempotency test
- 관련 pytest 파일
- python scripts/preflight.py
- git diff --check

현재 단계와 무관한 전체 PostgreSQL runtime test, visual regression, 전체 release gate는 실행하지 마.

검증 완료 후 이번 단계 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: add predictive maintenance bundle adapter"
- git push origin HEAD

push 실패 시 이력 재작성이나 force push 없이 오류와 commit hash를 보고해.

마지막 보고:

- 검증한 bundle role과 행 수
- streaming/memory 전략
- 실패·quarantine 처리 방식
- 변경 파일
- 테스트 결과
- commit hash와 push 결과
- Phase 2에 필요한 PostgreSQL ingestion interface
```
