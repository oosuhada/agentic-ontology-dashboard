# Phase 02 — PostgreSQL Bulk Ingestion

> **완료 기록 — 재실행하지 않음.** 완료 커밋: `01a4a9b`. V3.1 Result Artifact와
> release metadata 보강은 Phase 3 및 정합성 수정 커밋에서 additive하게 적용됐다.

```text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

데이터 패키지도 읽기 전용으로 확인해줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v2

먼저 다음을 읽어줘.

- docs/30-implementation/predictive-maintenance-canonical-v2-integration-plan.md
- Phase 0~1 prompt와 실제 구현 커밋
- infra/docker-compose.yml
- api/migrations/postgresql/0008_dataset_projection_pipeline.sql
- api/ontology_dashboard/postgresql_pool.py
- api/ontology_dashboard/postgresql_compat.py
- api/ontology_dashboard/datasets/repository.py
- api/ontology_dashboard/adapters/service.py
- Phase 1 Bundle Adapter와 tests

git status --short --branch, git log -7 --oneline, remote tracking을 확인하고 다른 세션의 미커밋 변경을 보존해. 이번 단계 관련 파일만 수정·stage·commit해.

이번 목표는 검증된 bundle을 PostgreSQL에 원자적으로 적재하는 production 경로를 구현하는 것이다.

구현 범위:

1. PostgreSQL migration
   - pm_assets
   - pm_asset_relations
   - pm_compressor_observations
   - pm_cnc_observations
   - pm_production_cycles
   - pm_maintenance_events
   - pm_prediction_snapshots 또는 기존 prediction_results와 명확한 연계
   - pm_prediction_timeline
   - pm_prediction_factors
   - organization_id, project_id, workspace_id, dataset_version_id, source_sha256
   - 적절한 PK, FK, index, RLS
2. 대량 적재
   - row-by-row INSERT가 아니라 PostgreSQL COPY 또는 psycopg copy protocol
   - role별 staging table
   - staging validation 후 version-scoped target merge
   - 한 bundle transaction 안에서 catalog/version/files/facts/outbox 처리
3. idempotency
   - 같은 bundle checksum은 기존 Dataset Version을 재사용
   - 중복 fact row를 만들지 않음
   - 다른 checksum은 새 Dataset Version
4. 실패 처리
   - 한 role 실패 시 전체 transaction rollback
   - ingestion run과 오류 원인은 남기되 partial ready 상태를 만들지 않음
5. CLI와 서비스 연결
   - scripts/ingest_predictive_maintenance_bundle.py가 PostgreSQL URL을 지원
   - SQLite 경로와 섞어서 production 완료로 표시하지 않기
6. 검증 스크립트
   - source와 DB row count parity
   - FK, time range, dataset version isolation, RLS negative check

관측 테이블 설계 시 모든 sensor row를 ontology_objects나 JSONB mega table로 넣지 마. compressor와 CNC의 typed wide schema를 유지하고 observed_at 범위 조회에 적합한 index/partition 전략을 사용해. 현재 30일 데이터가 확실히 동작해야 하며, 향후 기간 확장을 막지 않아야 한다.

검증 환경은 infra/docker-compose.yml의 PostgreSQL 서비스를 우선 사용해. 기존 개발 데이터가 있다면 별도 test database/schema 또는 disposable container를 사용하고 파괴적 reset을 하지 마.

필수 검증:

- PostgreSQL migration 적용과 재적용 안전성
- 실제 bundle ingestion 성공
- source와 다음 row count 일치
  - assets 100
  - relations 80
  - compressor observations 86,400
  - CNC observations 345,600
  - production cycles 170,860
  - maintenance events 795
  - prediction snapshots 100
  - prediction factors 300
  - prediction timeline 68,211
- asset/relation/fact FK parity
- 같은 bundle 재실행 시 version·row 중복 없음
- 다른 project context에서 RLS 조회 불가
- transaction 중간 오류 시 partial row 없음
- tests/test_predictive_maintenance_postgresql.py
- scripts/check_postgresql_migration.py 또는 해당 migration targeted check
- scripts/verify_predictive_maintenance_ingestion.py
- git diff --check

전체 visual regression은 실행하지 마. PostgreSQL 관련 targeted test를 우선하고, 필요한 범위의 기존 dataset/project isolation tests만 실행해.

검증 완료 후 이번 단계 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: ingest predictive maintenance bundle into postgresql"
- git push origin HEAD

push 실패 시 force push나 reset 없이 오류와 로컬 commit hash를 보고해.

마지막 보고:

- 실제 적재된 Dataset/Version identity
- 테이블별 row count
- COPY와 transaction 구조
- RLS 및 idempotency 결과
- 변경 파일과 migration 번호
- 테스트 결과
- commit hash와 push 결과
- Phase 3 materialization 입력 contract
```
