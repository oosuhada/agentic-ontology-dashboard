# Ontology Dashboard Release Gate Report

- 실행일: 2026-08-02
- Gate: `ontology-dashboard-v0.7`
- Stage: 56 — Project hardening, editing recovery and environment-aware completion
- 결과: **PASS**
- 비브라우저 release gate: **12/12 PASS**
- 별도 전체 Playwright: **34/34 PASS**
- 외부 production capability: 현재 host에서 **BLOCKED**로 명시적 보고

## 검증 요약

```text
Canonical naming                         PASS · 197 files · 0 violations
Architecture debt guard                 PASS
Visual baseline manifest                PASS · 6 PNG artifacts
PostgreSQL migration/RLS/runtime        PASS
Backend pytest                          122 PASS
Gold evaluation                         8/8 PASS
Frontend Vitest                         6 PASS
TypeScript                              PASS
Production build                        PASS
Initial JavaScript                      214.48 KiB / 300 KiB
Largest deferred JavaScript             443.24 KiB / 500 KiB
Playwright                              34 PASS
Release gate                            12/12 PASS
```

Backend test suite의 유일한 warning은 Starlette TestClient가 향후 `httpx2` 설치를 권고하는 deprecation warning이다. 기능 실패는 아니다.

## Stage 56 주요 acceptance

### Dataset Catalog

- 기본 Product Navigation에서 활성화
- `SOON` 표시 제거
- Project Home, Governance, sidebar에서 접근 가능
- project permission과 route boundary 적용

### Project routing and isolation

- archived/deleted Project deep link에 tombstone 표시
- unauthorized와 mismatched Project/Workspace route 차단
- 마지막으로 검증된 Project로 안전하게 복귀
- active Project session persistence와 Project switch reload 복원
- Dashboard, Ontology Action, Workflow, Export repository isolation matrix 통과

### Dashboard editing recovery

- undo/redo와 `Cmd/Ctrl+Z`, `Cmd/Ctrl+Shift+Z`
- user/workspace/role-scoped local autosave
- dashboard/template/revision compatibility 확인 후 recovery 제안
- reload recovery와 draft discard
- unsaved navigation 및 browser unload 경고
- persisted save/default restore 시 stale recovery 제거

### Multi-project showcase

- Manufacturing Gold regression은 GS-001~GS-008 8건 유지
- Azure Fleet Maintenance:
  - AZ-001 tool-wear warning
  - AZ-002 power/overstrain critical
  - `azure-showcase-v1` Evidence lineage
- MetroPT Compressor:
  - MPT-001 thermal warning
  - `metropt-showcase-v1` Evidence lineage
- Azure/MetroPT는 Project별 Action mapping이 게시되기 전까지 조회 전용
- complete public Azure/MetroPT dataset ingestion은 현재 fixture showcase와 구분

### Canonical namespace

- executable ASGI composition root를 `api/ontology_dashboard/main.py`로 이동
- `api/factory_signal_board/main.py`는 compatibility re-export만 유지
- remaining physical legacy modules와 `ontology_dashboard.__path__` extension은 별도 controlled relocation debt로 유지

### Accessibility and responsive verification

주요 Workbench를 720×500 viewport에서 검증했다.

- Dashboard
- Analysis
- Project Home
- Agent
- Ontology
- Dataset Catalog
- Governance

검사 항목:

- interactive control accessible name
- 단일 `main` landmark
- duplicate DOM ID 없음
- image alt 존재
- document-level horizontal overflow 없음

검사 중 발견한 모바일 메뉴, React Flow ID, Agent/Ontology/Dataset/Governance form label 문제를 수정했다.

## Visual baseline

다음 artifact의 크기, dimension과 SHA-256가 `baseline-manifest.json`에 고정되어 있다.

- `dashboard.png`
- `analysis.png`
- `agent.png`
- `governance.png`
- `datasets.png`
- `comparison-sheet.png`

`scripts/check_visual_baselines.py`가 release gate에서 누락 또는 비의도적 변경을 차단한다.

## Production environment capability

다음 명령으로 외부 환경 가용성을 판정한다.

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/verify_production_environment.py
```

현재 host의 결과:

- Docker Compose: blocked — Docker CLI 미설치
- managed PostgreSQL: blocked — URL 미설정
- Redis: blocked — URL 미설정
- Neo4j: blocked — current shell credentials 미설정
- Project 3: blocked — current shell URL 미설정
- OIDC: blocked — provider credentials 미설정
- production connector: blocked — endpoint 미선택
- object storage: blocked — endpoint/bucket 미설정
- observability: blocked — OTLP endpoint 미설정

이 항목은 코드 실패가 아니라 외부 환경·자격증명 의존이다. 실행 절차는 `docs/production-environment-completion-runbook.md`에 고정했다.

## Preflight note

코드·dependency·필수 파일·Gold fixture preflight 항목은 통과했다. 다만 검사 시점에 다음 개발 서버가 이미 실행 중이어서 고정 포트 availability 항목만 실패했다.

```text
127.0.0.1:8100 · Python process
127.0.0.1:3100 · Node process
```

사용자 개발 서버일 수 있으므로 자동 종료하지 않았다. Release gate와 Playwright는 별도 또는 동적 포트에서 정상 통과했다.

## 재실행 명령

```bash
.venv/bin/python -m pytest
cd web && npm run test && npm run build && npm run test:e2e
cd ..
.venv/bin/python scripts/check_visual_baselines.py
.venv/bin/python scripts/release_gate.py
.venv/bin/python scripts/verify_production_environment.py
```

외부 staging에서는 다음 strict verifier를 먼저 사용한다.

```bash
.venv/bin/python scripts/verify_production_environment.py \
  --strict \
  --require compose \
  --require postgresql \
  --require redis \
  --require neo4j \
  --require project3
```

## 남은 제한

- complete Azure five-file dataset과 complete MetroPT time-series source는 checkout에 없다.
- production IdP, connector, object storage와 OTLP collector는 선택·자격증명이 필요하다.
- managed PostgreSQL/Redis 장기 부하, failover와 restore evidence는 외부 environment에서 실행해야 한다.
- remaining `api/factory_signal_board` physical modules는 compatibility slice별로 이동해야 한다.
- Palantir 비교 artifact의 최종 미적 승인과 cross-platform pixel-diff CI는 후속 운영 작업이다.
