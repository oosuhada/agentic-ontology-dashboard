# Factory Signal Board

제조 설비의 예측·이상 탐지 결과를 추적 가능한 Evidence로 해석하고, 동일한 사건을 매니저에게는 결정·영향 중심으로, 엔지니어에게는 센서·점검 근거 중심으로 구성하는 역할 기반 예지보전 의사결정 MVP다.

## 구현 상태

2단계 데이터 계약부터 15단계 발표 패키징까지 구현했다.

- AI4I 2020 데이터 검증·누수 방지·재현 가능한 모델 학습
- 모델 버전별 운영 임계값 정책
- Evidence Package, Report, UI Block JSON Schema
- 규칙 기반 역할별 리포트와 선택적 LLM Adapter
- 미등록 컴포넌트를 차단하는 governed UI Planner
- FastAPI, SQLite 감사 기록, 제한된 후속 질문
- React 매니저·엔지니어 대시보드
- 프로젝트 3 Maintenance Context HTTP Adapter와 fallback
- Gold 평가, Vitest, TypeScript, production build, Playwright E2E 릴리스 게이트

Git 초기화와 원격 연결은 사용자 요청에 따라 범위에서 제외했다.

## 핵심 흐름

```text
AI4I-compatible sensor event
→ validation and derived features
→ trained model or deterministic Gold predictor
→ versioned threshold policy
→ Evidence Package
→ deterministic or grounded LLM Report
→ role and intent aware governed UI Layout
→ FastAPI
→ React manager/engineer dashboard
→ human decision, checklist, notes, audit
```

## 빠른 실행

필수 환경:

- Python 3.11 이상
- Node.js 22.13 이상
- npm

```bash
cd "/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2"
cp .env.example .env
bash scripts/run_local.sh
```

기본 주소:

- Web: `http://127.0.0.1:3100`
- API docs: `http://127.0.0.1:8100/docs`

API 키가 없어도 deterministic fallback으로 전체 Gold 데모가 동작한다.

## Docker 선택 실행

```bash
cd infra
docker compose up --build
```

## 검증

가상환경이 준비된 상태에서:

```bash
export PYTHONPATH="$PWD/api:$PWD/ml/src"
python scripts/release_gate.py --with-e2e
```

최종 확인 결과:

- Release checks: **10/10 PASS**
- Python unit/integration/safety tests: **14 PASS**
- Gold scenarios: **8/8 PASS**
- Vitest: **1 PASS**
- Playwright E2E: **2 PASS**
- 금지 운영 단정: **0건**
- Evidence 추적 불가 Report section: **0건**

상세 결과: [`docs/release-gate-report.md`](./docs/release-gate-report.md)

## AI4I 모델 결과

검증된 UCI AI4I 2020 CSV:

- 10,000행
- 고장 339행, 고장률 3.39%
- 결측 0, 중복 0
- failure-mode leakage column 입력 0

선택 모델: balanced Random Forest

Held-out test, Recall-constrained threshold 0.20:

| Metric | Result |
|---|---:|
| Average Precision | 0.8739 |
| Precision | 0.6591 |
| Recall | 0.8529 |
| F1 | 0.7436 |
| Confusion matrix | `[[1902, 30], [10, 58]]` |

이는 synthetic benchmark 재현성 결과이며 실제 공장 배포 성능을 뜻하지 않는다.

## 사용자 차이

| 구분 | 매니저 | 엔지니어 |
|---|---|---|
| 첫 질문 | 어떤 설비에 어떤 결정을 내려야 하는가? | 어떤 센서가 왜 비정상적인가? |
| 첫 정보 | 상태, 위험도, 영향, 권장 결정 | 시계열, 이상 구간, 주요 근거 |
| 주요 행동 | 판단, 점검 요청, 담당자 메모 | 점검, 기록, 매니저 보고 |
| 모델 상세 | 기본 접힘 | 필요 시 확인 |

## Gold 시나리오

1. 정상 설비
2. 공구 마모 위험
3. 열 방출 이상
4. 동력·토크 과부하
5. 복합 이상
6. 저신뢰 결과
7. 데이터 품질 문제
8. LLM·Planner 장애

## 폴더 구조

```text
api/          FastAPI, report/LLM/planner/context/repository services
web/          Vite React role-aware dashboard and Playwright tests
ml/           dataset audit, training, thresholding, evidence generation
schemas/      input, evidence, report, governed UI contracts
prompts/      manager, engineer, UI planner grounding rules
data/         Gold fixtures and optional local/raw data
evaluation/   accepted Gold scenarios and evaluation result location
docs/         scope, personas, data/model/policy/contracts/runbook
infra/        Docker Compose
scripts/      fetch, preflight, run, reset, evaluate, release gate
tests/        backend contract/integration/safety tests
```

## 주요 문서

- [`docs/stage2-15-implementation-summary.md`](./docs/stage2-15-implementation-summary.md)
- [`docs/mvp-scope.md`](./docs/mvp-scope.md)
- [`docs/personas.md`](./docs/personas.md)
- [`docs/data-dictionary.md`](./docs/data-dictionary.md)
- [`docs/model-baseline-results.md`](./docs/model-baseline-results.md)
- [`docs/risk-threshold-policy.md`](./docs/risk-threshold-policy.md)
- [`docs/service-contract.md`](./docs/service-contract.md)
- [`docs/project3-adapter-contract.md`](./docs/project3-adapter-contract.md)
- [`docs/demo-runbook.md`](./docs/demo-runbook.md)
- [`docs/troubleshooting.md`](./docs/troubleshooting.md)

## 안전 경계

- 실제 설비 제어 API가 없다.
- 예측 고장 유형은 현장 점검 전까지 가설이다.
- 데이터 품질 오류에서는 추론과 영향 판단을 보류한다.
- LLM은 상태·결정·수치를 바꿀 수 없다.
- LLM은 임의 React/HTML/JavaScript를 생성하지 않는다.
- 모든 추천 조치는 사람의 검토가 필요하다.
- 프로젝트 3 장애 시 로컬 context로 fallback한다.

## 라이선스와 데이터

외부 저장소는 구조와 패턴을 조사하기 위한 레퍼런스다. 라이선스가 없는 저장소의 코드는 복사하지 않았다. AI4I 원본 CSV와 재생성 가능한 모델 binary는 기본 Git 추적 대상이 아니다.
