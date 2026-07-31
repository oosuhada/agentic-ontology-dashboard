# Tests

현재 backend test suite는 23개 계약·통합·인증·RBAC·안전 검사를 포함한다.

## `test_mvp.py`

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

```bash
export PYTHONPATH="$PWD/api:$PWD/ml/src"
pytest -q tests
```

전체 Gold·frontend·browser 검증은:

```bash
python scripts/release_gate.py --with-e2e
```
