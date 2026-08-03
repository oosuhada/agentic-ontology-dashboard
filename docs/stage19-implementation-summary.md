# 19단계 구현 요약 — Ontology registry와 제조 domain adapter

구현일: 2026-08-01

## 목표

기존 Manufacturing Predictive Maintenance Pack의 fixture·Evidence·판단·메모 데이터를 domain-neutral Ontology의 Object, Link, Action 계약으로 조회하고 실행할 수 있게 한다. 기존 제조 API와 React 화면 계약은 유지한다.

## 구현 결과

### 1. 제조 domain adapter

`api/factory_signal_board/ontology_adapter.py`

- Equipment → `equipment:<equipment_id>`
- RiskEvent → `risk_event:<event_id>`
- Evidence Package → `evidence_package:<evidence_id>`
- Inspection → `inspection:<event_id>`
- 기존 decision·note → `maintenance_action:<record_id>`

fixture와 Evidence Package는 읽을 때 ObjectRecord로 투영한다. decision·note는 기존 SQLite 운영 기록을 읽어 maintenance action object로 투영한다. 원본 fixture를 별도의 ontology instance table로 복제하지 않아 두 source of truth가 생기지 않도록 했다.

### 2. Link projection과 traversal

지원 LinkType:

- `equipment_has_risk_event`
- `risk_event_has_evidence`
- `risk_event_requires_inspection`
- `inspection_records_action`

`GET /api/ontology/objects/{object_id}/links`는 다음을 지원한다.

- `direction=outgoing|incoming|both`
- `depth=1..5`
- 선택적 `link_type` 필터

Equipment에서 depth 2로 탐색하면 RiskEvent와 연결 Evidence·Inspection을 함께 조회할 수 있다.

### 3. Object query API

- `GET /api/ontology/objects`
- `GET /api/ontology/objects/{object_id}`
- `GET /api/ontology/objects/{object_id}/links`
- `GET /api/ontology/objects/{object_id}/action-invocations`

목록 API는 `workspace_id`, `object_type`, `q`, `offset`, `limit`을 지원한다. 모든 조회는 `ontology.objects.read` permission과 principal의 workspace scope를 서버에서 검사한다.

### 4. Idempotent Ontology Action

`POST /api/ontology/actions/invoke`

지원 Action:

- `record_operational_decision`
- `record_inspection_note`

서버 검증:

- ActionType registry 존재 여부
- 대상 ObjectType 일치
- required permission
- workspace scope
- 필수·알 수 없는 parameter
- parameter value type
- CSRF

`ontology_action_invocations` 테이블은 사용자·workspace별 idempotency key를 선점한다.

- 같은 key + 같은 payload: 기존 결과 반환, `replayed=true`
- 같은 key + 다른 payload: `409 idempotency_key_conflict`
- 처리 중 같은 요청: `409 action_in_progress`
- 이전 실패 key: `409 prior_action_failed`

### 5. 기존 workflow 호환

기존 API 응답 형태는 유지하면서 내부 실행을 Ontology Action으로 변경했다.

- `POST /api/events/{event_id}/decision`
- `POST /api/events/{event_id}/notes`

클라이언트가 전달한 actor는 계속 무시하며 authenticated principal의 display name을 기록한다.

정상 사건처럼 사전에 Inspection object가 없는 경우에도 `record_inspection_note` Action이 `inspection:<event_id>` virtual target을 검증한 후 note를 기록한다. 다음 조회부터 Inspection과 `risk_event_requires_inspection`, `inspection_records_action` 관계가 materialize된다.

### 6. 감사

모든 성공 Action은 두 종류의 기록을 가진다.

- 기존 decision 또는 note operational record
- `ontology.action.<action_type>` audit_log record

Action invocation에는 audit ID와 성공 결과가 저장된다.

## 주요 파일

- `api/factory_signal_board/ontology.py`
- `api/factory_signal_board/ontology_adapter.py`
- `api/factory_signal_board/ontology_repository.py`
- `api/factory_signal_board/ontology_service.py`
- `api/factory_signal_board/main.py`
- `api/factory_signal_board/identity_models.py`
- `schemas/ontology-core.schema.json`
- `web/src/features/ontology/types.ts`
- `tests/test_ontology_stage19.py`

## 검증 범위

19단계 전용 테스트:

1. Object 검색과 Equipment → RiskEvent → Evidence·Inspection 2-hop traversal
2. Action 성공·replay·idempotency conflict
3. 명시적 ontology Action audit 영속화
4. virtual Inspection에 note Action 실행 후 관계 materialization
5. Action permission과 workspace scope 차단
6. 기존 decision·note API가 ontology Action invocation을 생성하는지 확인

## 다음 단계

20단계는 Dashboard template·tab·board persistence다.

권장 구현 순서:

1. dashboard template/version schema
2. dashboard tab과 board instance schema
3. 역할별 default template seed
4. resolved dashboard API
5. mandatory board policy
6. template preview와 migration test
