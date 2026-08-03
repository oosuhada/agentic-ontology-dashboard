# 30~31단계 구현 요약 — Ontology Planner와 Release Hardening

구현일: 2026-08-01

## 목표

30단계는 LLM이 직접 Object query나 Dashboard를 실행·저장하지 못하도록 typed intent, Board Catalog whitelist, Evidence grounding과 명시적 승인 경계를 추가한다.

31단계는 권한이 적용된 snapshot을 JSON·CSV·PDF로 export하고, rate limit·session rotation·security header·permission regression·template migration·Dashboard 성능·E2E role matrix를 릴리스 게이트로 고정한다.

---

## 30단계 — LLM·Ontology Planner 고도화

### 모듈

- `ontology_planner_models.py`
- `ontology_planner_service.py`
- `web/src/features/planner/types.ts`
- `web/src/features/planner/PlannerAssistantBoard.tsx`
- `schemas/ontology-planner.schema.json`

### 1. 자연어 → Object query intent

API:

```text
POST /api/planner/object-query
```

자연어를 다음 typed contract로 변환한다.

```text
object_type
search
filters[field, operator, value]
limit
rationale
source_terms
```

검증 원칙:

- 등록된 Object type만 허용
- 해당 Object type의 등록 property만 filter 가능
- workspace scope와 `planner.object_query` permission 검사
- query는 `OntologyService.query_objects`를 통해서만 preview 실행
- arbitrary SQL·Cypher·credential table 접근 없음

### 2. 역할·Preference 기반 Board recommendation

API:

```text
POST /api/planner/board-recommendations
```

입력:

- 사용자 역할
- 자연어 목표
- 현재 resolved Dashboard
- 현재 Board 존재 여부
- 사용자가 숨긴 Board
- 사용자가 12-column으로 확대한 Board

출력은 역할에 허용된 Board Catalog ID만 사용한다.

```text
requires_approval = true
persisted = false
```

추천만으로 개인 설정은 변경되지 않는다.

### 3. FDE Dashboard draft

API:

```text
POST /api/planner/dashboard-drafts
```

- FDE·tenant admin만 사용
- target role Catalog만 사용
- mandatory Board 보존
- Board role·binding·plain-text·schema 검증
- 결과는 preview이며 저장되지 않음
- Canvas 적용 후에도 별도 personal save 또는 template approval request가 필요

기본 FDE template v3의 Builder 탭에 `Ontology Planner Assistant` Board를 추가했다.

### 4. Grounded narrative

API:

```text
POST /api/planner/grounded-narrative
```

각 claim은 하나 이상의 `evidence_field_ids`를 포함해야 한다. 허용되지 않은 Evidence reference, 자동 제어 완료, 확정된 근본 원인·고장 단정은 거부한다.

### 5. Provider fail-closed

Provider 미설정·timeout·parser·schema·Catalog·grounding 실패 시:

```text
mode = deterministic_fallback
기존 Dashboard 유지
query·draft 자동 persistence 없음
```

### 권한

- `planner.object_query`
- `planner.board_recommend`
- `planner.dashboard_draft`
- `planner.narrative`

일반 역할은 query·recommendation·narrative를 사용할 수 있다. Dashboard draft는 FDE·tenant admin만 사용한다.

---

## 31단계 — Export·보안·성능·릴리스

### Export

모듈:

- `export_models.py`
- `export_repository.py`
- `export_service.py`
- `schemas/export.schema.json`

API:

```text
POST /api/exports
GET  /api/exports/checkpoints
```

지원 형식:

- JSON: 전체 permission-scoped snapshot
- CSV: flattened `path,value`, UTF-8 BOM
- PDF: snapshot hash, metadata와 검증된 field summary

지원 scope:

- `dashboard`
- `event`
- `role_workspace`

Export 흐름:

```text
permission·workspace scope 검사
→ canonical snapshot 생성
→ snapshot SHA-256
→ JSON·CSV·PDF artifact 생성
→ artifact SHA-256
→ export_checkpoints 저장
→ export.created operational audit
```

응답 header:

- `Content-Disposition`
- `X-Export-Checkpoint-ID`
- `X-Content-SHA256`
- `X-Snapshot-SHA256`

일반 사용자는 자신이 생성한 checkpoint만 조회한다. Tenant admin은 workspace 전체 checkpoint를 검토할 수 있다.

### PDF

ReportLab으로 서버에서 생성한다. 한국어 font는 다음 순서로 탐색한다.

1. `EXPORT_PDF_FONT`
2. macOS Apple Gothic·Noto Sans Gothic
3. Linux Noto CJK·Nanum Gothic
4. Windows Malgun Gothic
5. 없으면 명시적 Helvetica fallback

PDF가 지나치게 커지는 것을 막기 위해 260 field 이후는 JSON export를 안내한다.

### Rate limit

MVP single-process fixed-window limiter:

- Login: 12 requests / minute / DB·IP·email hash
- Planner: 30 / minute / user
- Export: 20 / minute / user
- Session management: 20 / minute / user

초과 시:

```text
HTTP 429
Retry-After header
rate_limit_exceeded
```

Production multi-instance에서는 Redis 기반 shared limiter로 교체해야 한다.

### Session hardening

기존 12시간 absolute expiry에 다음을 추가했다.

- 60분 idle timeout
- user-agent hash binding
- IP hash 관찰
- `last_seen_at`
- explicit token rotation
- `rotated_from`
- active session 목록
- 다른 session 일괄 revoke
- session token hash만 DB 저장

API:

```text
POST   /api/auth/refresh
GET    /api/auth/sessions
DELETE /api/auth/sessions/others
```

Refresh 시 기존 token과 CSRF token은 폐기되고 새 token으로 교체된다.

### Security headers

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Permissions-Policy`
- API `Content-Security-Policy`
- auth·admin·export `Cache-Control: no-store`
- production HSTS

### 성능 기준

10개 이상 Board를 가진 resolved Dashboard를 120회 resolve하여 다음 budget을 고정했다.

```text
mean < 30 ms
p95  < 60 ms
```

### 회귀 matrix

- 8개 test role login·Planner·Export permission
- 사용자별 export checkpoint 격리
- FDE direct publish 403
- tenant admin approval
- share link scope
- template v3 migration과 override merge
- CSRF
- session rotation·idle timeout·client binding
- rate limit
- PDF·CSV·JSON hash와 audit

---

## 테스트 결과

### Backend

총 53건 통과.

- 기존 39건
- Stage 30 Planner 6건
- Stage 31 Export·Security·Performance 8건

Planner 공격·실패 회귀:

- credential Object type 생성 시도 → deterministic fallback
- `password_hash` property 접근 시도 → 차단
- Catalog 밖 arbitrary code Board → 차단
- unknown Evidence reference → 차단
- 자동 정지·확정 원인 claim → 차단
- Provider 장애 → 기존 Dashboard 유지

### Browser E2E

총 13건 통과.

신규 흐름:

1. FDE Planner 자연어 Object query
2. non-persisted Dashboard draft를 검토 Canvas에 적용
3. JSON artifact download와 export checkpoint

### Release gate

```text
Gate: ontology-dashboard-v0.6
Checks: 10/10 PASS
Python: 53 PASS
Gold: 8/8 PASS
Playwright: 13 PASS
TypeScript strict: PASS
Production build: PASS
```

Production build:

```text
HTML: 0.52 kB / gzip 0.32 kB
CSS: 50.10 kB / gzip 9.52 kB
JavaScript: 299.55 kB / gzip 87.39 kB
```

## 남은 운영 전환 항목

- in-memory rate limiter를 Redis로 교체
- SQLite를 PostgreSQL·Alembic으로 전환
- enterprise SSO와 조직별 session policy
- export artifact object storage와 retention policy
- 실제 provider 품질·비용·latency benchmark
- 실제 생산 데이터 기반 Planner evaluation
