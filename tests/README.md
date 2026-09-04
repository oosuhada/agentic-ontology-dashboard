# Tests

현재 backend test suite는 53개 계약·통합·인증·RBAC·Ontology·Dashboard·Planner·Export·Session·성능·안전 검사를 포함한다.

## `test_operations.py`

기존 Gold 제조 기능과 회귀 안전성:

- 8개 fixture와 의도된 GS-007 오류
- target/failure-mode 누수 차단
- Gold 상태·결정·신뢰도·고장 유형
- Evidence JSON Schema
- 역할별 grounded report 차이
- LLM·Planner offline fallback
- 역할·데이터 품질별 UI 순서
- 미등록 UI Block/data field 차단
- 인증된 API 조회·판단·메모·감사
- 일반 사용자 reset API 미노출과 내부 reset 동작
- 후속 질문 재구성과 injection형 요청 거부
- Project 3 장애 fallback
- 구조화 404 오류

## `test_auth_rbac.py`

16~18단계 foundation:

- 8개 demo account login
- Argon2id hash와 평문 미저장
- signup `pending_approval`
- tenant admin approval, role, workspace scope와 audit
- pending·disabled·logout 차단
- FDE admin 403과 tenant-admin 허용
- workspace scope 밖 제조 API 403
- cookie mutation CSRF
- ontology registry
- production demo seed 금지

## `test_ontology_stage19.py`

19단계 Ontology instance와 Action:

- object type·검색 기반 ObjectRecord query
- Equipment → RiskEvent → Evidence·Inspection 2-hop traversal
- Action parameter·target type·permission 검증
- Action idempotent replay와 payload conflict 409
- Action result와 명시적 operational audit persistence
- virtual Inspection note materialization
- workspace scope 밖 object query 403
- 기존 decision·note API의 Ontology Action 전환

## `test_dashboard_stages20_24.py`

20~24단계 persistent Dashboard 플랫폼:

- 역할별 default template·tab·board와 version·preview
- resolved dashboard JSON Schema와 dependency graph
- 개인화 저장·재로그인 복원·사용자 격리·기본값 복원
- mandatory board 삭제·숨김 차단
- 역할별 Board Catalog와 binding·plain text 보안 검증
- saved view와 share parameter 복원
- 공유 조회 workspace scope 차단
- FDE template publish 승인과 기존 사용자 override merge

## `test_role_workspaces_stages25_29.py`

25~29단계 역할 전용 workspace:

- Executive 조직·workspace 위험 집계, 영향 가정과 drill-down
- Audit 입력·model·policy·Evidence·Report·Action 재구성과 export checkpoint
- Field 모바일 task, 안전·측정·사진 metadata와 idempotent Ontology Action
- FDE credential 비노출, diagnostic과 template four-eyes approval
- Model Console의 training·operational scope 분리, Gold 8/8과 release approval
- `role-workspaces.schema.json` 응답 계약 검증

## `test_ontology_planner_stage30.py`

- 자연어 → registered Object query intent
- 역할·사용자 preference 기반 Board recommendation
- FDE Dashboard draft의 Catalog·mandatory·role 검증
- grounded narrative Evidence reference
- 악성 provider의 credential Object, 임의 Board, secret citation 차단
- provider 장애 시 deterministic fallback과 non-persistence
- `ontology-planner.schema.json` 응답 계약 검증

## `test_export_security_stage31.py`

- JSON·CSV·PDF artifact와 snapshot·content hash
- 사용자 checkpoint 격리와 admin review
- session rotation, idle timeout, client binding, 다른 session revoke
- login rate limit과 security headers
- 8개 역할 permission regression matrix
- FDE·tenant admin 분리
- 10+ Board mean·p95 performance budget
- `export.schema.json` snapshot·checkpoint 계약 검증

```bash
export PYTHONPATH="$PWD/api:$PWD/ml/src"
pytest -q tests
```

전체 Gold·frontend·browser 검증은:

```bash
python scripts/release_gate.py --with-e2e
```
