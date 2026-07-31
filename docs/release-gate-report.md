# Factory Signal Board Release Gate Report

- 실행일: 2026-08-01
- Gate: `factory-signal-board-v1`
- 결과: **PASS**
- 필수 검사: 10
- 통과: 10
- 실패: 0
- 브라우저 E2E 실제 실행: 예
- 새 환경 원커맨드 실행 smoke: PASS

## 검사 결과

| # | 검사 | 결과 |
|---:|---|---|
| 1 | 8개 Gold fixture envelope·품질 계약 | PASS |
| 2 | Python 단위·통합·안전 테스트 14건 | PASS |
| 3 | Gold 요구사항 평가 8/8 | PASS |
| 4 | Python compileall | PASS |
| 5 | 고정된 frontend 의존성 설치 | PASS |
| 6 | Vitest UI 단위 테스트 | PASS |
| 7 | TypeScript strict type check | PASS |
| 8 | Vite production build | PASS |
| 9 | Playwright Chromium 준비 | PASS |
| 10 | FastAPI+React Playwright E2E 2건 | PASS |

## Gold 평가 요약

- 시나리오: 8
- 통과: 8
- 실패: 0
- 역할: manager, engineer
- 금지 운영 단정: 0
- Evidence 추적 불가 Report section: 0
- GS-008 LLM·Planner fallback: PASS

시나리오별 첫 블록:

| Scenario | Manager | Engineer |
|---|---|---|
| GS-001 정상 | `StatusSummary` | `StatusSummary` |
| GS-002 공구 마모 | `StatusSummary` | `SensorLineChart` |
| GS-003 열 방출 | `StatusSummary` | `SensorLineChart` |
| GS-004 동력·과부하 | `StatusSummary` | `SensorLineChart` |
| GS-005 복합 이상 | `StatusSummary` | `FactorContribution` |
| GS-006 저신뢰 | `DataQualityWarning` | `DataQualityWarning` |
| GS-007 데이터 오류 | `DataQualityWarning` | `DataQualityWarning` |
| GS-008 LLM offline | `StatusSummary` | `SensorLineChart` |

## 모델 검증 요약

UCI AI4I 2020 10,000행, 고장률 3.39%에서 Random Forest가 validation Average Precision 0.8529로 선택됐다.

Held-out test, Recall-constrained threshold 0.20:

- Average Precision: 0.8739
- Precision: 0.6591
- Recall: 0.8529
- F1: 0.7436
- Confusion matrix: `[[1902, 30], [10, 58]]`

이 결과는 공개 synthetic benchmark 재현성 검증이며 실제 공장 배포 성능을 의미하지 않는다.

## Production build

- HTML: 약 0.51 kB
- CSS: 약 10.69 kB, gzip 2.98 kB
- JavaScript: 약 208.18 kB, gzip 65.82 kB

## 새 환경 실행 검증

프로젝트를 임시 디렉터리에 복제하고 `.venv`, `node_modules`, cache가 없는 상태에서 다음 동작을 검증했다.

- `scripts/run_local.sh`가 Python 가상환경 생성
- editable ML·API package 설치
- frontend package 설치
- preflight 통과
- FastAPI 실제 기동
- React 실제 기동
- API `/health` 응답 확인
- Web HTML 응답 확인
- 종료 신호 시 child process 정리

결과: `RUN_LOCAL_SMOKE_PASS`

## 재실행 명령

```bash
PYTHONPATH=api:ml/src python scripts/release_gate.py --with-e2e
```

새 환경에서는 가상환경을 활성화하고 `pip install -e ml -e api`를 먼저 수행한다.

## 남아 있는 제한

- 실제 제조 시계열·CMMS·MES 데이터로 검증하지 않았다.
- 현재 Gold 제품 흐름은 deterministic predictor로 offline 재현성을 보장한다.
- 실제 LLM provider를 사용한 품질 벤치마크는 API 키 설정 후 별도 수행해야 한다.
- Project 3 연결은 HTTP Adapter와 fallback 계약까지 구현했으며 실제 Project 3 endpoint 통합 테스트는 미수행이다.
- 실제 설비 제어와 자동 작업 지시는 의도적으로 제공하지 않는다.
