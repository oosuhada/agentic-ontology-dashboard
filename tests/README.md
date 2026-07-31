# Tests

`test_mvp.py`는 다음 14개 backend 계약·통합·안전 검사를 포함한다.

- 8개 fixture와 의도된 GS-007 오류
- target/failure-mode 누수 차단
- Gold 상태·결정·신뢰도·고장 유형
- Evidence JSON Schema
- 역할별 grounded report 차이
- LLM·Planner offline fallback
- 역할·데이터 품질별 UI 순서
- 미등록 UI Block/data field 차단
- API 조회·판단·메모·감사
- 후속 질문 재구성과 injection형 요청 거부
- Project 3 장애 fallback
- 구조화 404 오류

```bash
export PYTHONPATH="$PWD/api:$PWD/ml/src"
pytest -q tests/test_mvp.py
```

전체 Gold·frontend·browser 검증은:

```bash
python scripts/release_gate.py --with-e2e
```
