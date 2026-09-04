# Runtime Overlay 기존 계획 변경 영향 안내

## 1. 목적과 지위

이 문서는 [`closed-loop-runtime-overlay-contract.md`](./closed-loop-runtime-overlay-contract.md)를
도입할 때 기존 계획과 진행 중인 구현에서 바뀌는 지점을 팀원별로 안내한다.

이 문서는 새로운 상태나 Payload를 정의하는 정본이 아니다. 상세 동작은 Runtime Overlay
계약을 따르고, 기존 Domain과 Product 소비 의미는 각 canonical contract를 따른다.

## 2. 유지되는 기존 원칙

- 기존 Closed-loop Domain 객체와 상태 머신을 다시 만들지 않는다.
- PR #42의 Domain 계약과 PR #44의 Product/API/UI 소비 계약을 유지한다.
- Canonical V3.1과 정비 전 Product Result/Evidence는 immutable하다.
- `systems/generator`는 Feature/Label, training과 Model Artifact publish까지 소유한다.
- Backend Diagnosis가 Runtime Prediction과 Product Result/Evidence를 생성한다.
- 정비 완료만으로 정상 판정을 만들지 않는다.
- What-if와 비용 최적화는 핵심 Operations 범위에 포함하지 않는다.

## 3. 기존 표현에서 달라지는 부분

| 기존 계획 표현 | 보강된 구현 기준 |
|---|---|
| 정비 후 새 Observation 생성 | 대상 설비만 `maintenance_replay_overlay` branch에서 생성 |
| 정비 후 재예측 | Backend가 `history_requirement`을 충족했다고 판정한 첫 inference-ready Observation에서 실행 |
| 이력 확보 방식 미정 | 대상 설비 Overlay branch clock만 Fast-forward하고 Observation을 지속 생성 |
| Replay는 새 센서값을 만들지 않음 | Canonical Replay는 계속 read-only, Overlay는 별도 opt-in 경로 |
| 완료 시각 `completed_at` | 내부 Domain은 유지, 시스템 간 이벤트는 `maintenance_completed_at` |
| 완료 이벤트 단일 처리 | Started, Completed, ReplayRequested 단계와 지연 도착 처리 |
| HTTP mutation 멱등성 | Integration delivery에는 `idempotency_key`와 `state_version` 사용 |
| `state_patch` 자유 형식 | `action_code`별 field/operation/value/unit whitelist |
| 정비 후 첫 값에서 Prediction | 첫 inference-ready 값에서 Prediction, 이후 정상 주기 유지 |
| 정비 전후 history 규칙 없음 | `restart_at`부터 새 history segment, 암묵적 혼합 금지 |

## 4. 현재 구현 PR 영향

### 광우 — Closed-loop Persistence/API 후속 작업

기존 Persistence, 상태 머신과 API 작업은 폐기하거나 다시 만들지 않는다.

추가되는 작업:

- Maintenance 완료 transaction에 Integration Outbox 적재
- 내부 `completed_at`을 이벤트 `maintenance_completed_at`으로 매핑
- `maintenance_event_id`, `idempotency_key`, `state_version` 전달
- typed `state_patch`와 source lineage 전달
- 완료 전 restart 요청 금지

추가되지 않는 작업:

- Generator Overlay 구현
- Simulation Clock 실행
- Feature history 계산
- Runtime Prediction 또는 Result/Evidence 생성

### 성민 — `gen_data` Generator/Replay 후속 작업

- 전체 Generator 교체가 아니라 대상 설비 Overlay mode 추가
- 대상 설비 pause와 다른 설비 계속 재생 보장
- 정비 효과를 Overlay Snapshot에 적용
- 대상 설비 branch clock만 Fast-forward
- 기존 Observation의 `source_kind`를 `maintenance_replay_overlay`로 확장하고 lineage를
  가진 Overlay Observation 발행
- Model Artifact를 읽지 않고 Overlay Observation을 지속 생성
- 생성 완료는 `observations.available`로 알리며 readiness를 선언하지 않음
- 운영 Product Result/Evidence는 생성하지 않음

### 호범 — Backend Diagnosis 후속 작업

- Overlay Observation을 기존 Runtime Diagnosis 입력으로 소비
- `restart_at` 이후 새 history segment 적용
- Model Artifact의 `history_requirement`에서 최소 이력을 계산하는 유일한 readiness owner
- 이력 부족 시 Prediction하지 않고 이후 available Observation을 기다림
- stream 종료·실패 등 유효 이력 확보 불가가 확정될 때만 `history_insufficient` 처리
- `warming_up`과 `history_insufficient` 처리
- 첫 inference-ready Observation에서 신규 Product Result/Evidence 생성
- 정비 전 Result/Evidence는 수정하지 않음
- Canonical Observation과 분리된 Runtime Overlay 저장소/port를 통해 history 조회
- 대상 설비의 정비 후 Canonical 미래 행을 Overlay history에 다시 섞지 않음

### 우수 — Product API/UI/E2E 후속 작업

- `equipment_under_maintenance`, `warming_up`, `history_insufficient`, `ready`,
  `predicted` 상태 표시
- `warming_up` 진행률을 가능하면 `n/N`으로 표시
- canonical runtime-status read location은 versioned handoff 확정 후 Backend integration
  단계에서 결정
- 정비 완료와 정상 Prediction을 구분
- 정비 전 Result → Maintenance → 정비 후 Result E2E 구성
- 기존 Backend/Frontend Observation의 `source_kind="canonical_observation"` literal을
  `maintenance_replay_overlay`까지 additive 확장

## 5. 활성 문서별 수정 위치

| 문서 | 수정 위치와 내용 | 검토 주체 |
|---|---|---|
| `closed-loop-implementation-plan.md` | 구현 목표, 담당 경계, PR 2/3, 인계, E2E, 체크리스트 | 광우 + 전체 |
| `closed-loop-domain-contract.md` | Maintenance 완료 Integration handoff와 시각 매핑 | 광우 |
| `closed-loop-product-consumption-contract.md` | Runtime 준비 상태와 E2E 단계 | 우수 + 광우/호범 |
| `architecture.md` | Canonical Replay와 Overlay branch 분리 | 전체 |
| `ADR-002` | post-maintenance history segment와 inference-ready 조건 | 성민 + 호범 |
| `final_team_role_and_step_plan.md` | Step 6/10/12와 담당자 인계 | 전체 |
| `operations/requirements-specification.md` | Current Replay와 Target Overlay 구분 | 우수 + 전체 |
| `operations/runtime-ownership-integration.md` | `gen_data`, Backend, Closed-loop 책임 | 성민 + 호범 + 광우 |
| `operations/api-specification.md` | 최종 endpoint/response 확정 후 상태 계약 반영 | 우수 + 광우/호범 |
| `operations/traceability-matrix.md` | 실제 코드와 테스트가 생긴 뒤 경로 추가 | 우수 + 전체 |

현재 구현에서 확인된 직접 영향 경로는 다음과 같다. 아래 경로는 이 문서 PR에서
수정하지 않고 실제 Overlay 저장/API 구현 PR에서 변경한다.

| 현재 경로 | 후속 변경 |
|---|---|
| `systems/backend/ontology_dashboard/predictive_maintenance_runtime/models.py` | `SensorObservation.source_kind` enum과 Overlay lineage 확장 |
| `systems/backend/ontology_dashboard/predictive_maintenance_runtime/repository.py` | Canonical-only 조회를 branch-aware read model로 확장 |
| `systems/frontend/src/features/predictive-maintenance/types.ts` | Observation `source_kind` union과 준비 상태 타입 확장 |
| `systems/backend/migrations/` | 별도 append-only Runtime Overlay Observation 저장소 추가 |

## 6. `gen_data` 저장소 후속 문서

`gen_data`는 별도 저장소이므로 해당 소유자의 후속 PR에서 반영한다.

| 문서 | 수정 내용 |
|---|---|
| `ARCHITECTURE_DECISION.md` | read-only Canonical Replay와 opt-in Overlay 분리 |
| `OWNERSHIP_AND_MIGRATION.md` | Overlay Observation 생성 책임 추가 |
| `docs/02_architecture.md` | 설비별 Overlay state와 branch-local clock |
| `docs/03_detailed_spec.md` | 이벤트, Snapshot, Fast-forward, 멱등성, envelope, acceptance |
| `README.md` | Overlay mode와 Non-goal 요약 |
| `docs/ai-code-review-context.md` | 계약 승인·구현 후 Overlay invariant 추가 |

## 7. 수정하지 않는 기록

- `docs/operations/history/2026-08-week2/**`
- `gen_data/V3_1_CHANGELOG.md`
- `gen_data/V3_1_IMPLEMENTATION_REPORT.md`
- `gen_data/V3_1_RELEASE_VERIFICATION.md`
- `gen_data/FINAL_AUDIT_REPORT.md`
- Canonical 릴리스 Schema와 검증 결과

과거 기록은 당시 사실을 보존한다. 필요한 경우 Runtime Overlay 계약 링크만 추가하고
과거 결론을 현재 계획에 맞춰 재작성하지 않는다.

## 8. 구현 전 확정·인계 체크리스트

- [ ] 공유 이벤트 완료 필드가 `maintenance_completed_at`으로 확정됐다.
- [ ] Closed-loop가 발행하는 단계별 이벤트와 consumer가 확정됐다.
- [ ] Backend는 Maintenance 이벤트가 아니라 Overlay Observation으로 Prediction한다.
- [ ] Backend만 최소 Observation 수를 `history_requirement`에서 계산하고 readiness를 판정한다.
- [ ] `gen_data`는 Model Artifact를 읽지 않고 Overlay Observation을 지속 생성한다.
- [ ] `state_patch` whitelist가 Schema로 확정됐다.
- [ ] Product API 위치는 versioned handoff 확정 후 Backend integration에서 결정하는
      Deferred 항목으로 추적된다.
- [ ] 대상 설비 branch clock만 Fast-forward한다.
- [ ] Overlay 저장소가 Canonical Observation 저장소와 분리됐다.
- [ ] branch-aware read가 정비 후 Canonical 미래 행을 제외한다.
- [ ] 각 담당자가 자신의 후속 PR 범위를 확인했다.
