# Stage 2–15 Implementation Summary

## 완료 범위

| 단계 | 구현 결과 | 주요 파일 |
|---:|---|---|
| 2 | AI4I 출처·라이선스·checksum·컬럼·누수·data gap, 8개 Gold fixture | `docs/data-dictionary.md`, `schemas/input-event.schema.json`, `data/fixtures/` |
| 3 | Dummy·Logistic·Random Forest 재현 학습·평가 | `ml/src/factory_signal_ml/training.py`, `docs/model-baseline-results.md` |
| 4 | Recall 제약·비용 임계값과 모델별 정책 분리 | `ml/config/*.json`, `docs/risk-threshold-policy.md` |
| 5 | Evidence Package와 개별 근거·lineage | `schemas/evidence-package.schema.json`, `ml/.../evidence.py` |
| 6 | 결정론적 매니저·엔지니어 리포트 | `api/.../reports.py`, `schemas/report.schema.json` |
| 7 | OpenAI-compatible LLM Adapter·grounding·fallback | `api/.../llm.py`, `prompts/` |
| 8 | 등록된 Block 전용 동적 Planner | `api/.../planner.py`, `schemas/ui-block.schema.json` |
| 9 | FastAPI·SQLite·오류·감사 계약 | `api/.../main.py`, `service.py`, `repository.py` |
| 10 | 매니저 결정 중심 React 화면 | `web/src/App.tsx`, `components.tsx` |
| 11 | 엔지니어 Evidence·차트·체크리스트 화면 | `web/src/components.tsx` |
| 12 | 제한 intent 후속 질문·화면 재구성 | `api/.../conversation.py`, React conversation block |
| 13 | 프로젝트 3 Context HTTP Adapter·fallback | `api/.../context.py`, `docs/project3-adapter-contract.md` |
| 14 | Gold·회귀·안전·frontend·browser release gate | `tests/test_mvp.py`, `scripts/evaluate_gold.py`, `release_gate.py` |
| 15 | preflight·원커맨드·reset·Docker·CI·runbook | `scripts/run_local.sh`, `infra/`, `.github/workflows/ci.yml` |

## 검증 결과

- AI4I audit: 10,000행, 결측 0, 중복 0, failure 339
- Random Forest held-out test: AP 0.8739, Precision 0.6591, Recall 0.8529, F1 0.7436
- Gold product evaluation: 8/8 PASS
- Python test: 15 PASS
- Frontend unit test: 1 PASS
- TypeScript strict check: PASS
- Production build: PASS
- Playwright E2E: 2 PASS
- Release gate: 10/10 PASS
- 새 환경 `run_local.sh` smoke: PASS
- 금지 운영 단정: 0
- 추적 불가 Report section: 0

## 구현 중 발견하고 수정한 주요 문제

1. 고중요도 보정이 warning을 critical로 과도하게 올리는 문제
   - critical 경계에는 중요도 보정을 적용하지 않도록 수정했다.
2. 상세 사건 화면에서 `PriorityList`가 매니저 첫 정보였던 문제
   - Gold 계약에 따라 `StatusSummary`를 첫 블록으로 변경했다.
3. 엔지니어 화면이 사건 종류와 무관하게 같은 블록으로 시작한 문제
   - 공구·열·부하 사건은 센서 차트, 복합 사건은 기여 요인, 저신뢰·데이터 오류는 경고를 먼저 보여준다.
4. 후속 질문 intent 변경이 답변을 즉시 덮어쓰던 React effect 문제
   - event/role 기본 load와 intent 재구성을 분리했다.
5. Vitest가 Playwright spec을 수집하던 문제
   - unit test include 범위를 `src/**/*.test.*`로 제한했다.
6. 고정 포트 때문에 E2E가 빠지고도 gate가 통과할 수 있던 문제
   - E2E에 동적 빈 포트를 사용하고 미실행이면 release 실패하도록 수정했다.
7. 프로젝트 3 등 다른 서비스와 API 8000 충돌
   - 프로젝트 2 기본 API를 8100으로 변경했다.

## 의도적으로 남긴 범위 밖 항목

- Git 저장소 초기화·원격 push·태그
- 실제 공장 데이터와 temporal validation
- 실제 CMMS·MES·ERP write integration
- 실제 설비 제어
- 실제 Project 3 endpoint 통합 실행
- 실제 LLM provider별 품질 benchmark
- PDF export와 다중 사용자 인증
