# Ontology Dashboard

조직의 Object, Link, Evidence와 Action을 역할·권한·workspace 범위에 맞는 업무 화면으로 구성하는 온톨로지 기반 운영 애플리케이션 MVP다. 초기 제조 예지보전 vertical slice는 첫 번째 **Manufacturing Predictive Maintenance Pack**으로 유지한다.

## Why I Built It / 만든 이유

Engineers need raw numbers and evidence, managers need priorities, executives need conclusions — but one fixed dashboard can't serve all three. I built a dynamic dashboard where an LLM reshapes the same manufacturing data for each role.

엔지니어는 수치와 근거를, 매니저는 우선순위를, 임원은 결론을 필요로 하는데, 하나의 고정된 대시보드로는 이 니즈가 동시에 충족되지 않는 문제가 있었습니다. 같은 제조 데이터를 각 역할에 맞게 LLM이 다시 구성하는 동적 대시보드를 만들었습니다.

## 구현 상태

2단계 데이터 계약부터 31단계 Ontology Planner·Export·보안·성능 릴리스 hardening까지 구현했다.

- AI4I 2020 데이터 검증·누수 방지·재현 가능한 모델 학습
- 모델 버전별 운영 임계값 정책
- Evidence Package, Report, UI Block JSON Schema
- 규칙 기반 역할별 리포트와 선택적 LLM Adapter
- 미등록 컴포넌트를 차단하는 governed UI Planner
- FastAPI, SQLite 감사 기록, 제한된 후속 질문
- React 역할별 Ontology Dashboard와 Manufacturing Predictive Maintenance Pack
- 기능별 frontend 분리: `features/auth`, `features/manufacturing`, `features/dashboard`, `features/roles`, `features/planner`, `features/admin`, `features/ontology`
- `/login`, `/register`, `/pending`, protected `/app`, tenant-admin-only `/admin`
- SQLite identity/session/RBAC/resource scope, Argon2id, HttpOnly cookie, CSRF, 관리자 audit
- 8개 개발·데모 test account와 production seed 차단
- domain-neutral Object·Link·Action·Evidence·Dashboard·Board contract foundation
- 제조 fixture·Evidence·activity의 ObjectRecord·LinkRecord projection
- workspace-scoped object query와 최대 5-hop relation traversal
- permission-aware, idempotent Ontology Action과 explicit operational audit
- 기존 decision·note API의 Ontology Action 전환
- SQLite 역할별 Dashboard template·version·tab·board persistence
- 상단 workspace·tabs, 좌측 context, 12-column canvas, 우측 inspector 기반 새 shell
- drag order·resize·hide/show·custom tab·saved view·role default restore
- 역할별 Board Catalog, plain text board, FDE template 승인 요청과 tenant-admin publish
- parameter dependency graph, affected board 표시, fullscreen, permission-aware share link
- 임원 조직 위험·영향 집계, 미조치 중요 사건과 가정 기반 drill-down
- 품질·감사 사건 재구성, Evidence→Report trace, export checkpoint hash
- 390px 모바일 현장 task, 안전·측정·사진 metadata와 idempotent 완료·문제·blocked Action
- FDE customer workspace·ontology·deployment·diagnostic Workbench와 four-eyes template approval
- 데이터 사이언티스트 model·dataset·threshold·slice·drift·Gold regression Console과 release approval
- 검증된 자연어 Object query, preference-aware Board 추천, grounded narrative와 FDE Dashboard draft preview
- Catalog·role·Evidence reference 위반 또는 provider 장애 시 deterministic fail-closed fallback
- permission-scoped JSON·CSV·PDF export, snapshot·artifact SHA-256와 export checkpoint audit
- login·Planner·Export rate limit, 60분 idle timeout, session rotation·client binding·다른 세션 revoke
- security header와 10+ Board mean·p95 성능 budget
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

- Web login: `http://127.0.0.1:3100/login`
- User app: `http://127.0.0.1:3100/app`
- Admin app: `http://127.0.0.1:3100/admin`
- API docs: `http://127.0.0.1:8100/docs`

개발 환경에서는 8개 demo account가 idempotent하게 seed된다. `APP_ENV=production`에서는 demo seed가 강제로 차단된다. API 키가 없어도 deterministic fallback으로 전체 Gold 데모가 동작한다.

### 개발·데모 계정

| 역할 | ID | Password |
|---|---|---|
| 관리자 | `admin@ontology.local` | `OntologyAdmin!2026` |
| 임원 Viewer | `executive@ontology.local` | `Executive!2026` |
| 운영 매니저 | `manager@ontology.local` | `Manager!2026` |
| 도메인 엔지니어 | `engineer@ontology.local` | `Engineer!2026` |
| 현장 작업자 | `technician@ontology.local` | `Technician!2026` |
| 품질·감사 | `quality@ontology.local` | `Quality!2026` |
| 데이터 사이언티스트 | `datascientist@ontology.local` | `DataScience!2026` |
| FDE | `fde@ontology.local` | `FDE!2026` |

DB에는 Argon2id hash만 저장한다. 개발 DB에 계정이 없다면 `PYTHONPATH=api:ml/src python scripts/seed_demo_accounts.py`를 실행한다.

## Vertex AI 연결

Vertex AI는 OpenAI 호환 API 키가 아니라 Google Cloud 프로젝트의 인증과 결제로 연결된다.
`onjung.official@gmail.com`에서 결제/무료 크레딧이 연결된 프로젝트를 선택한 뒤, 로컬 또는 Mac mini에서 다음을 한 번 실행한다.

```bash
gcloud auth login onjung.official@gmail.com
gcloud config set project <ONJUNG_PROJECT_ID>
gcloud services enable aiplatform.googleapis.com
gcloud auth application-default login onjung.official@gmail.com
```

그 프로젝트에서 `.env`에 아래만 설정한다. Docker로 실행한다면 서비스 계정 키를
`secrets/vertex-runtime.json`처럼 Git에 포함되지 않는 경로에 두고
`GOOGLE_APPLICATION_CREDENTIALS=./secrets/vertex-runtime.json`으로 지정한다. Compose가 이를
컨테이너 안의 안전한 읽기 전용 경로로 마운트한다. 로컬 `bash scripts/run_local.sh` 실행은
`gcloud auth application-default login`으로 만든 ADC를 그대로 사용한다.

```dotenv
LLM_PROVIDER=vertex-ai
LLM_MODEL=gemini-2.5-flash
GOOGLE_CLOUD_PROJECT=<ONJUNG_PROJECT_ID>
GOOGLE_CLOUD_LOCATION=global
```

Google Cloud Console에서 해당 프로젝트에 결제 계정이 연결되어 있고, 실행 주체에
`Vertex AI User` 권한이 있어야 한다. 결제 계정/프로젝트 변경은 기존 `gabrieldiseoul@gmail.com`
로그인 여부와 무관하며, 실제 청구는 `GOOGLE_CLOUD_PROJECT`의 연결된 결제 계정으로 간다.

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
- Python unit/integration/auth/RBAC/Ontology/Dashboard/Planner/Export/Security tests: **53 PASS**
- Gold scenarios: **8/8 PASS**
- Vitest: **1 PASS**
- Playwright E2E: **13 PASS**
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

## 역할과 기본 landing

일반 사용자 역할은 `executive_viewer`, `process_manager`, `process_engineer`, `maintenance_technician`, `quality_auditor`, `ml_validator`, `fde`다. 같은 Ontology와 Evidence를 사용하지만 역할마다 `/app`의 설명, 첫 관점과 허용 Action이 다르다. `tenant_admin`은 별도 `/admin` control plane으로 이동하며, FDE는 사용자 계정·비밀번호·보안 정책을 관리할 수 없다.

기존 Gold 화면의 핵심 차이도 유지한다.

| 구분 | 운영 매니저 | 도메인 엔지니어 |
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
api/          FastAPI, identity/RBAC, ontology registry, Planner, export and security services
web/          Vite React auth, dashboard, role/planner workspaces, admin app and Playwright tests
ml/           dataset audit, training, thresholding, evidence generation
schemas/      input, Evidence, Report, Layout, ontology, dashboard, role, planner and export contracts
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
- [`docs/stage16-18-implementation-summary.md`](./docs/stage16-18-implementation-summary.md)
- [`docs/stage19-implementation-summary.md`](./docs/stage19-implementation-summary.md)
- [`docs/stage20-24-implementation-summary.md`](./docs/stage20-24-implementation-summary.md)
- [`docs/stage25-29-implementation-summary.md`](./docs/stage25-29-implementation-summary.md)
- [`docs/stage30-31-implementation-summary.md`](./docs/stage30-31-implementation-summary.md)
- [`docs/mvp-scope.md`](./docs/mvp-scope.md)
- [`docs/personas.md`](./docs/personas.md)
- [`docs/role-needs-research.md`](./docs/role-needs-research.md)
- [`docs/ontology-dashboard-additional-implementation-plan.md`](./docs/ontology-dashboard-additional-implementation-plan.md)
- [`docs/palantir-contour-dashboard-benchmark.md`](./docs/palantir-contour-dashboard-benchmark.md)
- [`docs/next-session-ontology-dashboard-prompt.md`](./docs/next-session-ontology-dashboard-prompt.md)
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

## Topics

[`adapter-pattern`](https://github.com/topics/adapter-pattern) · [`agentic-ai`](https://github.com/topics/agentic-ai) · [`fastapi`](https://github.com/topics/fastapi) · [`idempotency`](https://github.com/topics/idempotency) · [`react`](https://github.com/topics/react) · [`repository-pattern`](https://github.com/topics/repository-pattern) · [`transactional-outbox`](https://github.com/topics/transactional-outbox) · [`typescript`](https://github.com/topics/typescript) · [`manufacturing`](https://github.com/topics/manufacturing) · [`industrial-ai`](https://github.com/topics/industrial-ai) · [`llm`](https://github.com/topics/llm) · [`dashboard`](https://github.com/topics/dashboard) · [`postgresql`](https://github.com/topics/postgresql) · [`event-driven-architecture`](https://github.com/topics/event-driven-architecture) · [`domain-driven-design`](https://github.com/topics/domain-driven-design) · [`full-stack`](https://github.com/topics/full-stack)
