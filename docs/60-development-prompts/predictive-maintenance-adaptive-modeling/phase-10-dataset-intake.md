# Phase 10 — Dataset Intake Profile and Manifest Draft Assistant

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

다음 경로는 참고용으로만 열고 수정하지 마.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/prototype_share

각 workspace는 한 번만 open_workspace하고 workspaceId를 재사용해.

먼저 다음을 읽어줘.

- docs/30-implementation/predictive-maintenance-adaptive-modeling-integration-plan.md
- docs/60-development-prompts/predictive-maintenance-adaptive-modeling/README.md
- Phase 9 구현과 commit
- Phase 9 신규 schema/models/repository/migration
- api/ontology_dashboard/adapters/file_adapter.py
- api/ontology_dashboard/adapters/bundle_file_adapter.py
- api/ontology_dashboard/adapters/models.py
- api/ontology_dashboard/adapters/service.py
- api/ontology_dashboard/datasets/models.py
- api/ontology_dashboard/datasets/service.py
- api/ontology_dashboard/planner/의 deterministic-first 패턴
- api/ontology_dashboard/security.py
- prototype_share/mcp_tools/raw_preview.py
- prototype_share/mcp_tools/extraction_planner.py
- prototype_share/mcp_tools/extractor.py
- prototype_share/mcp_tools/loader.py

git status, 최근 commit, remote tracking을 확인하고 다른 세션의 미커밋 변경을 보존해.
현재 단계 관련 파일만 stage해.

이번 목표는 처음 보는 CSV/XLSX source를 바로 ingest하거나 LLM 판단으로 컬럼을 제거하지
않고, 안전한 Dataset Intake Profile과 승인 가능한 Manifest Draft를 생성하는 것이다.

구현 범위:

1. Source profile port
   - CSV와 XLSX 구현
   - 기존 connector/adapter가 DB schema metadata profiling을 안전하게 지원하면 동일 port로
     확장하되, 임의 connection string 실행 기능을 새로 만들지 않음
   - configured allowed root 또는 connector authorization 경계
2. Full source identity
   - 전체 파일 SHA-256
   - byte size, media type, encoding, delimiter, sheet
   - parser version
   - cache key = source checksum + parser version
   - preview fingerprint를 identity로 사용하지 않음
3. Bounded preview와 profile
   - bounded sample row/byte limit
   - row count 또는 명시적 estimate
   - field name과 inferred datatype
   - null ratio, distinct estimate, min/max/quantile 또는 safe summary
   - timestamp/identifier/group-key 후보
   - unit 후보와 sample value summary
   - high-cardinality text와 potential sensitive field 표시
   - raw secret/token/password-like value를 response/log에 노출하지 않음
4. Structure classifier
   - tabular_column_as_attribute
   - tabular_row_as_attribute
   - wide_pivot
   - key_value
   - multi_header
   - unsupported
   - delimiter/header/sheet 후보를 deterministic rule로 먼저 계산
5. Optional LLM boundary
   - deterministic candidate와 bounded preview만 입력
   - 위 enum과 존재하는 field name만 반환 가능
   - JSON Schema/Pydantic validation
   - provider unavailable/invalid response 시 deterministic fallback
   - LLM이 source field를 실제로 삭제하거나 ingest하지 않음
6. Essential key protection
   - timestamp/equipment identifier/join key 후보를 중요 필드로 표시
   - 사용자가 명시적으로 거부하기 전 manifest draft에서 자동 제외 금지
   - 컬럼명 alias만이 아니라 datatype/cardinality/sample pattern 근거 포함
7. Manifest Draft generation
   - 기존 DatasetManifest로 변환 가능한 typed draft
   - source fields와 canonical field alias suggestion
   - required field, quality rule, format/encoding suggestion
   - selected/excluded는 suggestion이며 rationale/confidence 포함
   - missing prerequisite와 unsupported structure 표시
8. Approval workflow
   - draft 생성, 조회, 수정, approve, reject, supersede
   - approve 권한과 audit
   - 승인 전 기존 FileAdapter/Bundle Adapter ingest 호출 금지
   - approval 후에도 기존 checksum/quality validation 경로를 우회하지 않음
9. API
   - profile 생성/조회
   - manifest draft 생성/수정/승인
   - API route naming은 기존 datasets/adapters convention 준수
   - project/workspace scope와 idempotency
10. Operational state
   - profiling, ready_for_review, unsupported, failed
   - failure reason과 retryability
   - same checksum 재요청은 idempotent

중요:

- source 파일 전체를 LLM에 보내지 마.
- preview에 secret/sensitive raw value를 그대로 포함하지 마.
- LLM이 선택한 컬럼만 남기고 원본을 덮어쓰지 마.
- profile/draft 생성만으로 Dataset Version을 만들지 마.
- `.xlsx` merged/multi-header를 일반 CSV처럼 잘못 처리하지 마.
- DB reader를 MCP라고 부르지 마. 실제 MCP server/protocol을 구현하지 않는다.

필수 검증:

- 일반 CSV, tab-delimited, quoted delimiter, encoding 사례
- XLSX multi-sheet와 explicit sheet 선택
- multi-header/wide-pivot/key-value classifier fixture
- unsupported binary 또는 malformed source
- full checksum이 다른 파일의 동일 preview를 구분
- parser version 변경 시 cache key 분리
- same checksum/profile request idempotency
- datetime/equipment key 후보 자동 제외 방지
- LLM invalid enum/unknown column/invalid JSON fallback
- provider unavailable deterministic success
- sensitive value redaction
- allowed root 밖 file 접근 거부와 symlink traversal 차단
- 승인 전 ingest negative test
- approval audit와 permission test
- tenant/project/workspace isolation
- 기존 FileAdapter/Bundle Adapter regression
- targeted backend tests
- git diff --check

UI는 최소 API contract test만 수행하고 전체 Dashboard/visual regression은 실행하지 마.

검증 완료 후 이번 단계 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: add governed dataset intake assistant"
- git push origin HEAD

마지막 보고:

- 지원 source와 structure type
- deterministic/LLM 경계
- checksum/cache 방식
- profile과 manifest draft API
- key 보호, redaction, approval 결과
- 변경 파일과 테스트
- commit hash와 push 결과
- Phase 11 mapping 후보 생성에 제공할 field profile contract
````
