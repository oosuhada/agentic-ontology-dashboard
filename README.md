# Agentic Ontology Dashboard

설비 이상 발견부터 현장 점검, 운영 판단, 정비, 경영 보고까지 걸리는 시간을 줄이는
**Predictive Maintenance Decision Workspace**입니다.

이 프로젝트는 고장 확률을 보여주는 대시보드에 머물지 않습니다. 지속적으로 들어오는
관측과 모델 결과를 하나의 Decision Case로 묶고, 같은 사건을 엔지니어에게는 점검 근거로,
운영 관리자에게는 판단 자료로, 경영진에게는 KPI와 보고 언어로 제공합니다.

제품 방향의 정본은 [제품 방향](./docs/product-direction.md)입니다.

## 해결하려는 문제

제조 현장의 병목은 고장을 예측하지 못하는 것만이 아닙니다. 설비 이상이 발견된 뒤
기술 근거가 운영 판단과 경영 보고로 바뀌는 과정에서 시간차와 맥락 손실이 발생합니다.

- 엔지니어의 센서 분석이 운영 판단 자료로 정리되기까지 시간이 걸립니다.
- 생산 영향과 정비 비용을 다시 계산하고 설명해야 합니다.
- 보고서가 원본 Event와 Evidence에서 분리되기 쉽습니다.
- 최신 관측이 과거 판단의 근거 snapshot을 덮으면 책임성과 추적성이 깨집니다.
- 정비 완료와 실제 위험 감소가 혼동될 수 있습니다.

이 프로젝트는 하나의 설비 사건을 다음 흐름으로 연결합니다.

```text
Observation
→ Prediction Result
→ Evidence
→ Decision
→ Inspection
→ Maintenance
→ Post-maintenance Observation / Prediction
→ Outcome
→ Role-aware Report
```

## 제품 원칙

1. **데이터는 하나, 화면과 언어는 역할별로 다르게 제공한다.**
2. **선택한 Event와 Evidence snapshot은 최신 관측이 들어와도 자동 교체하지 않는다.**
3. **위험도와 생산·재무 영향 추정치를 실제 고장이나 회계 실적으로 표현하지 않는다.**
4. **AI는 근거를 설명하고 보고 초안을 만들지만 사람의 승인과 Action을 대신하지 않는다.**
5. **정비 완료는 작업 사실이며, 정상화는 후속 관측과 재예측 결과로 확인한다.**
6. **Frontend는 Result를 생성하지 않고 실제 runtime 결과를 조회하고 표현한다.**

## 역할별 경험

### 엔지니어

“어떤 설비를 왜 점검해야 하는가?”에 답합니다.

- 공장 설비 상태맵과 위험 알림
- 핵심 센서의 실시간 변화
- 원인 후보와 Evidence
- 점검 checklist와 현장 기록
- 정비 이력과 Before/After
- 현재 workflow의 다음 Action

### 운영 관리자

“지금 무엇을 판단하고 승인해야 하는가?”에 답합니다.

- 판단 대기 Decision Case
- 생산 영향, 비용, 지연 리스크
- 점검 요청과 정비 승인
- 담당자, SLA, backlog
- 보고 초안과 경영 보고 전환

### 경영진

“운영 리스크와 조직 병목이 성과에 어떤 영향을 주는가?”에 답합니다.

- Executive Brief
- 운영 리스크와 생산·재무 영향
- Decision/Report lead time
- backlog와 handoff 병목
- 정비 효과와 주요 Case drill-down
- 근거 snapshot이 보존된 보고서

## 현재 아키텍처

### Offline model lifecycle

```text
Source / Protocol Data
→ Extraction
→ Feature / Label Dataset
→ Training / Evaluation
→ Versioned Model Artifact
```

### Online operational runtime

```text
gen_data live source
→ live-ingestor
→ Backend observation tables
→ Generator Runtime Queue
→ Runtime Feature / Prediction
→ Prediction Result Batch
→ Backend validation / promotion
→ PostgreSQL Product Result Artifact
→ Event / Evidence / Decision Case / Report ViewModel
→ Role-aware Frontend
```

정비 이후에도 같은 경로를 사용합니다.

```text
Maintenance completed
→ Runtime replay overlay observation
→ Generator re-prediction
→ New Product Result Artifact
→ Before/After outcome
```

Backend는 Generator가 만든 prediction batch의 scope, schema, 중복과 제품 계약을 검증해
Product Result로 승격합니다. Frontend가 Backend에 임의의 demo Result를 주입하는 경로는
기본 제품 흐름으로 사용하지 않습니다.

## LLM과 보고

구조화된 Artifact가 사실의 기준이며 LLM은 표현 계층입니다.

```text
Canonical Result Artifact
→ deterministic presentation dictionary
→ role-specific presentation facts
→ grounded LLM composition
→ artifact_id + dictionary_version + prompt_version cache
```

- 사용자 화면에는 현장·업무 언어를 우선 표시합니다.
- 내부 ID와 모델·schema version은 접힌 기술 정보에 보존합니다.
- 근거가 부족하면 추측하지 않고 한계를 표시합니다.
- LLM이 실패해도 deterministic report를 생성할 수 있어야 합니다.
- 보고서는 별도 문서가 아니라 Decision Case 업무 흐름의 산출물입니다.

## 저장소 구조

```text
systems/
├── generator/       # extraction, feature/label, training, runtime prediction
├── backend/         # Product Result, Evidence, workflow, report API
└── frontend/        # 역할별 Reliability Operations UI

contracts/           # 시스템 간 versioned schema와 test vector
docs/                # 제품 방향, 아키텍처, 운영·API 계약, 실행 가이드
evaluation/          # grounded assistant/report 평가 결과
infra/               # PostgreSQL, Mac mini, production runtime
ml/                  # ML compatibility adapter
scripts/             # 로컬 runtime, migration, 운영 도구
```

## 로컬 실행

Python 3.11+와 Node.js 환경이 필요합니다.

기본 실행:

```bash
bash scripts/run_local.sh
```

PostgreSQL 기반 live runtime:

```bash
bash scripts/run_local_live.sh
```

관측 생성부터 Generator prediction, Backend 승격, closed-loop replay와 Frontend 갱신까지
연결하는 통합 실행:

```bash
.venv/bin/python scripts/run_local_realtime.py \
  --history-hours 168 \
  --simulation-hours 336 \
  --speed 60
```

- 모델 최소 이력은 36개의 10분 Tick입니다.
- 기본 history backfill은 168시간입니다.
- 실행 session과 live dataset을 구분해 다른 simulation window가 섞이지 않게 합니다.
- 정비 후 replay는 대상 설비의 branch-local warm-up과 후속 관측을 사용합니다.
- 로컬 runtime 상태와 대용량 원천 데이터는 Git에 커밋하지 않습니다.

## 개발 명령

Architecture boundary:

```bash
python3 systems/verify_architecture.py
```

Backend:

```bash
cd systems/backend
pip install -e ../../ml -e '.[dev]'
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd systems/frontend
npm ci
npm run lint
npm run build
```

## 배포

현재 공개 서비스는 Mac mini의 containerized runtime과 로컬 PostgreSQL을 사용합니다.

```text
personal main
→ release checkout
→ Docker Compose build
→ frontend / backend / generator-runtime / live-ingestor / redis / postgres
→ Cloudflare Tunnel
→ https://dashboard.oosu.dev/
```

운영 DB와 runtime cache는 Git 저장소와 분리하며, 외부 공유 DB를 제품의 필수 의존성으로
사용하지 않습니다. 자세한 운영 절차는 [Mac mini production](./docs/operations/macmini-production.md)을
참고합니다.

## 문서

- [제품 방향](./docs/product-direction.md)
- [개인 발표·제품 데모 흐름](./docs/presentation-demo-flow.md)
- [프로젝트 보고서](./docs/submission-report.md)
- [문서 인덱스](./docs/README.md)
- [시스템 아키텍처](./docs/architecture.md)
- [Architecture Decision Records](./docs/architecture-decisions/README.md)
- [Operations 문서](./docs/operations/README.md)
- [Closed-loop Domain Contract](./docs/closed-loop-domain-contract.md)
- [Runtime Ownership](./docs/operations/runtime-ownership-integration.md)

## 완료 기준

프로젝트 완료는 화면이 움직이는 것만으로 판단하지 않습니다. 다음 흐름이 동일한 Event와
Evidence lineage를 유지하며 실제 runtime에서 닫혀야 합니다.

```text
Live Observation
→ Generator Prediction
→ Product Result / Evidence
→ Inspection Request / Acceptance / Result
→ Cost Decision / Maintenance Approval
→ Maintenance Action / Completion
→ Post-maintenance Observation / Prediction
→ Before/After Outcome
→ Operations Decision / Executive Report
```

최종 목표는 AI가 사람의 판단을 대신하는 것이 아니라, 현장의 기술 근거가 운영 판단과
경영 보고로 전환되는 시간을 줄이고 그 과정 전체를 추적 가능하게 만드는 것입니다.
