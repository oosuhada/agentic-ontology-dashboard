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

- [ ] 전체 pytest 통과
- [ ] FastAPI OpenAPI 생성 가능
- [ ] router path 충돌 없음
- [ ] permission negative test 통과
- [ ] tenant isolation test 통과
- [x] Project list/detail API tenant/project negative test 통과
- [ ] Ontology·Dashboard·Action 전체 repository의 project isolation test 통과
- [ ] migration idempotency 통과
- [ ] transaction rollback test 통과
- [ ] outbox 기록이 domain write와 같은 transaction에 저장됨

## 4. PostgreSQL

- [ ] migration SQL이 실제 PostgreSQL에서 실행됨
- [ ] 필수 table과 index 존재
- [ ] RLS 활성화 확인
- [ ] non-superuser tenant query에서 다른 tenant 행 차단
- [x] `app.project_id` 기반 Project/Workspace/Ontology project RLS 차단 검증
- [ ] psycopg repository contract test 통과
- [ ] connection pool과 timeout 설정 검증
- [ ] backup·restore runbook 존재

현재 상태:

- migration/RLS 실서버 검증: 완료
- Ontology PostgreSQL repository foundation: 완료
- 전체 repository PostgreSQL runtime: 미완료

## 5. Frontend

- [ ] TypeScript strict check 통과
- [ ] production build 통과
- [ ] unit tests 통과
- [x] Manufacturing Demo Project selector foundation 동작
- [x] `/app/projects/:projectId` route 초기 복원
- [x] workspace selector가 Project별 Workspace API를 따른다.
- [x] invalid Project route를 접근 가능한 Project로 복원하는 E2E
- [ ] deleted Project route와 다중 Project switch E2E
- [ ] role dashboard가 project별 template을 사용한다.
- [ ] error/loading/empty 상태 존재
- [ ] unsaved dashboard edit 경고 또는 복구 존재

## 6. End-to-End

필수 E2E:

- [ ] manager와 engineer의 역할별 화면 차이
- [ ] data-quality hold
- [ ] LLM/provider fallback
- [ ] tenant admin과 FDE 권한 차이
- [ ] registration pending approval
- [ ] dashboard edit persistence
- [ ] mandatory board protection
- [ ] saved view/share parameter state
- [ ] executive drill-down
- [ ] audit reconstruction/export checkpoint
- [ ] field mobile action
- [ ] FDE template approval request
- [ ] planner draft non-persistence
- [ ] model release approval queue
- [ ] project selector and project isolation
- [ ] Azure와 두 번째 Project 전환

## 7. Dataset and Adapter

- [ ] dataset license와 source 기록
- [ ] dataset manifest 존재
- [ ] version·checksum 기록
- [ ] adapter validation 통과
- [ ] invalid rows quarantine
- [ ] derived metrics 계산 코드와 test 존재
- [ ] 발표 숫자가 코드로 재현 가능
- [ ] Prediction Result Contract schema validation 통과
- [ ] source lineage를 AnalysisRun에서 추적 가능

## 8. Security

- [ ] production demo seed 비활성
- [ ] HTTPS origin allowlist
- [ ] Secure, HttpOnly, SameSite cookie 검증
- [ ] CSRF 검증
- [ ] session revoke 검증
- [ ] trusted proxy 설정
- [ ] `X-Forwarded-For` spoof 방지
- [ ] secret이 repository나 export에 포함되지 않음
- [ ] force push나 destructive operation과 무관
- [ ] share token이 permission을 우회하지 않음

## 9. Accessibility and UX

- [ ] keyboard-only 주요 flow
- [ ] modal focus 관리
- [ ] form label
- [ ] contrast
- [ ] 200% zoom
- [ ] mobile field flow
- [ ] axe critical violation 0
- [ ] 한국어 용어 일관성

## 10. Documentation

- [ ] `00-project-charter.md`가 현재 방향과 일치
- [ ] architecture 업데이트
- [ ] domain model 업데이트
- [ ] roadmap 상태 업데이트
- [ ] dataset strategy 업데이트
- [ ] project catalog 업데이트
- [ ] implementation status와 실제 test 결과 일치
- [ ] next-session master prompt의 다음 우선순위 업데이트

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

2026-08-01 기준:

```text
Canonical naming: 84 files, 0 violations
PostgreSQL organization/project migration/RLS: PASS
Backend: 65 PASS
Gold scenarios: 8/8 PASS
Frontend unit: 1 PASS
TypeScript: PASS
Production build: PASS
Playwright: 14 PASS
Release gate: 12/12 PASS
```
