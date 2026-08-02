# Ontology Dashboard Release Checklist

- Last updated: 2026-08-01
- Current automated release gate: 12 checks

## 1. Automated Gate

반드시 다음 명령이 통과해야 한다.

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/release_gate.py --with-e2e
```

현재 gate 구성:

- canonical naming check
- PostgreSQL migration and RLS check
- fixture validation
- backend tests
- Gold evaluation
- Python compile
- frontend install
- frontend unit test
- TypeScript check
- production build
- Chromium install
- Playwright E2E

## 2. Naming and Architecture

- [ ] 사용자 노출 영역에 `Factory Signal Board`가 없다.
- [ ] 신규 Python import는 `ontology_dashboard`를 사용한다.
- [ ] 신규 ML import는 `ontology_dashboard_manufacturing_ml`을 사용한다.
- [ ] Project scope 없이 신규 dataset을 global workspace에 추가하지 않았다.
- [ ] Prediction logic이 Dashboard UI나 presentation service에 들어가지 않았다.
- [ ] Project, workspace, role 경계가 문서와 코드에서 일치한다.

## 3. Backend

- [x] 전체 pytest 통과
- [x] FastAPI OpenAPI 생성 가능
- [x] router path 충돌 없음
- [x] permission negative test 통과
- [x] tenant isolation test 통과
- [x] Project list/detail API tenant/project negative test 통과
- [ ] Ontology·Dashboard·Action 전체 repository의 project isolation test 통과
- [x] migration idempotency 통과
- [x] transaction rollback/retry test 통과
- [x] outbox 기록이 domain write와 같은 transaction에 저장됨

## 4. PostgreSQL

- [x] migration SQL이 ephemeral PostgreSQL에서 실행됨
- [x] 필수 table과 index 존재
- [x] RLS 활성화 확인
- [x] non-superuser tenant query에서 다른 tenant 행 차단
- [x] `app.project_id` 기반 Project/Workspace/Ontology project RLS 차단 검증
- [x] psycopg repository contract test 통과
- [x] connection pool과 timeout 설정 검증
- [x] backup·restore runbook과 SQLite round-trip/tamper test 존재

현재 상태:

- migration/RLS 실서버 검증: 완료
- Ontology PostgreSQL repository foundation: 완료
- 전체 repository PostgreSQL runtime: 미완료

## 5. Frontend

- [x] TypeScript strict check 통과
- [x] production build 통과
- [x] unit tests 통과
- [x] Manufacturing Demo Project selector foundation 동작
- [x] `/app/projects/:projectId` route 초기 복원
- [x] workspace selector가 Project별 Workspace API를 따른다.
- [x] invalid Project route를 접근 가능한 Project로 복원하는 E2E
- [ ] deleted Project tombstone UX
- [x] 다중 Project switch와 resource isolation E2E
- [x] role dashboard가 project별 template과 active role context를 사용한다.
- [x] error/loading/empty 상태 존재
- [ ] unsaved dashboard edit 경고 또는 복구 존재

## 6. End-to-End

필수 E2E:

- [x] manager와 engineer의 역할별 화면 차이
- [x] data-quality hold
- [x] LLM/provider fallback
- [x] tenant admin과 FDE 권한 차이
- [x] registration pending approval
- [x] dashboard edit persistence
- [x] mandatory board protection
- [x] saved view/share parameter state
- [x] executive drill-down
- [x] audit reconstruction/export checkpoint
- [x] field mobile WorkOrder action
- [x] FDE template approval request
- [x] planner draft non-persistence
- [x] model release approval queue
- [x] project selector and project isolation
- [x] Azure와 두 번째 Project 전환
- [x] Project Home과 active role context
- [x] Dataset materialization과 reusable Analysis input
- [x] Agent persisted run/claim/evidence restore
- [x] live PostgreSQL+Neo4j+Project 3 RAG hybrid gate

## 7. Dataset and Adapter

- [x] dataset license와 source 기록
- [x] dataset manifest 존재
- [x] version·checksum 기록
- [x] adapter validation 통과
- [x] invalid rows quarantine
- [x] derived metrics 계산 코드와 test 존재
- [x] 발표 숫자가 코드로 재현 가능
- [x] Prediction Result Contract schema validation 통과
- [x] source lineage를 AnalysisRun/Dataset Version에서 추적 가능

## 8. Security

- [x] production demo seed 비활성/fail-fast
- [x] HTTPS origin allowlist
- [x] Secure, HttpOnly, SameSite cookie 검증
- [x] CSRF 검증
- [x] session revoke 검증
- [x] trusted proxy network 설정
- [x] `X-Forwarded-For` spoof 방지
- [x] secret이 repository나 export에 포함되지 않음
- [x] force push나 destructive operation과 무관
- [x] share token이 permission을 우회하지 않음

## 9. Accessibility and UX

- [x] keyboard focus-visible과 주요 flow
- [x] modal focus 관리
- [x] form label
- [x] light/dark semantic contrast baseline
- [ ] 200% zoom 전 route 수동 점검
- [x] mobile field flow
- [x] axe critical violation 0 baseline
- [x] canonical WorkOrder/한국어 용어 일관성

## 10. Documentation

- [ ] `00-project-charter.md`가 현재 방향과 일치
- [x] architecture 업데이트
- [x] domain model/ADR 업데이트
- [x] roadmap 상태 업데이트
- [x] dataset strategy와 Catalog contract 업데이트
- [x] project catalog/Project Home 반영
- [x] implementation status와 실제 test 결과 일치
- [x] next-session master prompt의 다음 우선순위 업데이트

## 11. Release Decision

Release candidate로 표시하려면:

- P0 issue 0건
- automated gate 전체 통과
- 알려진 P1 defer 항목에 owner와 목표 단계 존재
- tenant/project isolation 검증
- migration 및 rollback 계획 존재
- 실제 데이터 project 최소 1개 동작
- 두 번째 project로 abstraction 검증 또는 명시적 defer

## 12. Current Baseline

2026-08-02 기준:

```text
Canonical naming: PASS
PostgreSQL organization/project migration/RLS/runtime: PASS
Backend: 118 PASS
Gold scenarios: 8/8 PASS
Frontend unit: 3 PASS
TypeScript: PASS
Production build: PASS
Initial JavaScript: 213.87 KiB / 300 KiB
Largest deferred JavaScript: 443.24 KiB
Playwright: 28 PASS
Live three-store Agent gate: PASS
```
