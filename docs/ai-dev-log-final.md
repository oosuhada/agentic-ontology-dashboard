# AI Workflow Working Log

작성일: 2026-08-25

이 문서는 `ontology-dashboard` 작업 중 생산계획/운영 문맥, 설비 상세 ViewModel, 역할별 UI,
작업요청/정비 상태 흐름, AI 요약 생성/소비 계약을 맞추기 위해 사용한 작업 로그다.
최종 의사결정의 원본은 부모 프로젝트의 `/Users/hb/Documents/final/docs/project/DECISION_LOG.md`에 기록한다.

관련 결정 문서:

- Project decision log: `/Users/hb/Documents/final/docs/project/DECISION_LOG.md`
- Architecture boundary: `docs/architecture-decisions/ADR-004-product-result-evidence-viewmodel-trust-boundary.md`
- Operations UI boundary: `docs/operations/asset-detail-overview-ui-decision-log.md`
- Team responsibility plan: `docs/final_team_role_and_step_plan.md`

## 1. 현재 구현 상태

- API/계약 브랜치: `codex/operation-context-api`
- 푸시 상태: 원격 `origin/codex/operation-context-api` 푸시 완료
- 주요 커밋:
  - `3430c4a feat: connect production planning operation context`
  - `9164ff4 fix: tighten operation context view model contract`
- 검증:
  - `python3 -m pytest -q tests/test_asset_detail_view_model_composer.py tests/test_asset_detail_view_model_contract.py tests/test_operations.py` → 71 passed
  - `python3 systems/verify_contract_vectors.py` → passed
  - `python3 systems/verify_architecture.py` → passed
- 로컬 주의:
  - 메인 워크트리의 `README.md` 변경은 생산계획 API 작업과 무관하여 커밋/푸시에서 제외했다.
  - UI 워크트리에는 별도 로컬 변경이 크므로, UI 병합은 해당 변경을 보존한 상태에서 계약 정렬 방식으로 진행한다.

## 2. 데이터 흐름 결정

최종 데이터 흐름은 다음을 기준으로 한다.

```text
GS/Event fixture + operation-context fixture
  ↓
Backend composer
  ↓
AssetDetailViewModel
  ↓
Frontend role-specific views
```

결정 사항:

- `AssetDetailViewModel`은 하나만 유지한다.
- 생산관리자/현장관리자 화면은 같은 ViewModel을 다르게 소비한다.
- 별도 `ProductionManagerViewModel`은 현재 만들지 않는다.
- ViewModel 안에 typed section을 추가하는 방식으로 확장한다.
- `operation_context`는 생산계획/생산영향 표시용 운영 문맥이다.
- `operation_context`는 Product Result/Evidence의 `failure_probability`, `status_grade`, `top_factors`, `recommended_action`을 변경하지 않는다.
- Frontend는 event와 operation context를 직접 join하지 않는다.
- Frontend는 생산량, 가동률, 파생 센서값을 임의 계산하지 않는다.

## 3. ViewModel 계약 결정

최신 계약 기준:

- 피처 시계열은 `features[].history.points`다.
- 과거의 `features[].series` 참조는 제거해야 한다.
- 프론트 내부 모델에서는 `historyPoints`로 매핑해 소비할 수 있다.
- `risk_series`는 센서 이력이 아니라 Backend Diagnosis Runtime Prediction History다.
- `equipment_history[]`는 사람에게 보여주는 이력 projection이다.
- `equipment_history[]`에 machine-readable lineage 필드를 섞지 않는다.

`operation_context`는 summary 필드와 rich 생산계획 필드를 함께 가질 수 있다.

```text
operation_context
  load_level
  runtime_hours_7d
  production_impact
  context_id
  source_type
  temporal_scope
  production_plan
  capacity_model
  event_impact
  limitations
```

`source_type: synthetic_capacity_model`이 있으면 rich 생산계획 필드는 모두 계약상 필요하다.

## 4. 생산계획/생산영향 결정

생산계획은 별도 fixture로 둔다.

- Schema: `contracts/schemas/operation-context.schema.json`
- Fixture: `data/fixtures/operation_context/production-planning-context-v1.json`
- 근거 문서: `docs/operations/production-planning-assumptions.md`

결정 사항:

- Gold/Event fixture에 생산계획 필드를 직접 추가하지 않는다.
- 생산계획 fixture는 project, dataset version, temporal scope로 매칭한다.
- Event observation timestamp가 `temporal_scope.valid_from <= timestamp < valid_to`를 만족할 때만 연결한다.
- data-quality hold event는 생산 영향 수치를 만들지 않고 `withheld_data_quality_hold`로 둔다.
- 생산량은 실적이 아니라 `synthetic_capacity_model` 기반 계획/영향 추정이다.
- 납기일, 고객 주문, MES/ERP/APS 기록은 현재 계약에 없다.
- 따라서 납기 준수, 실제 생산량 증가, 실제 손실 회복은 표현하지 않는다.

UI에서 우선 사용할 필드:

- `operation_context.production_plan.planned_units`
- `operation_context.capacity_model.basis`
- `operation_context.event_impact.estimated_lost_units`
- `operation_context.event_impact.screen_priority`
- `operation_context.event_impact.impact_status`
- `operation_context.limitations`

## 5. 라인/셀 표시 결정

현재 계약에서 안정적으로 보장되는 운영 그룹은 `line`이다.

결정 사항:

- 생산관리자 맵은 셀 단위가 아니라 라인 단위로 표현한다.
- 화면 명칭은 `라인별 설비 영향 맵`을 사용한다.

- `cell_id` 또는 `cell`은 fallback label로만 사용한다.
- `A셀 3대`, `B셀 1대`, `4구역 x 5셀`, `셀당 5대`, `100대 배치` 같은 물리 topology 확정 표현은 사용하지 않는다.
- UI 워크트리에 이미 들어간 factory/cell map은 계약상 과한 가정이므로 라인 기준으로 정리한다.

프론트 매핑 우선순위:

```text
line = equipment.line ?? equipment.cell_id ?? "미지정 라인"
cell = equipment.cell_id ?? equipment.line
```

`cell_id`가 `line`보다 우선되면 운영 그룹이 흔들릴 수 있으므로 수정한다.

## 6. Agent Review Summary 생성 트리거 결정

AI 요약은 UI 사이드뷰 클릭, 탭 전환, 화면 새로고침 같은 presentation event마다 새로 생성하지 않는다.
사용자가 같은 Product Result/Evidence snapshot을 다시 열면 같은 Summary를 재사용해야 한다.

최종 방향:

```text
Product Result / Evidence Snapshot
  ↓
Agent Review Packet
  ↓
watcher가 snapshot/source checksum/prompt/schema/model version diff 확인
  ↓
Agent Review Summary 생성 또는 재사용
  ↓
DB 저장본을 UI / Report가 조회
```

결정 사항:

- `Agent Review Summary`는 read-only 표현 산출물이며 Closed-loop 명령이 아니다.
- LLM 호출 트리거는 UI 이벤트가 아니라 evidence snapshot diff다.
- `summary_key`는 asset, event, dataset version, snapshot basis/source checksum, prompt version,
  summary schema version, model version을 포함해야 한다.
- 같은 `summary_key`가 있으면 DB 저장본을 반환한다.
- diff가 있거나 validation/prompt/schema/model version이 바뀐 경우에만 watcher가 새 요약을 만든다.
- LLM 후보는 validation을 통과해야 저장된다.
- LLM provider가 없거나 validation에 실패하면 deterministic fallback Summary를 같은 저장 계약으로 남긴다.
- UI는 summary 상태를 조회해 `ready`, `generating`, `fallback`, `failed`, `stale` 같은 상태를 표현한다.
- Closed-loop는 Summary 문장이 아니라 Product Result/Evidence `snapshot_basis`와
  Recommendation/Action 계약을 기준으로 동작한다.

## 7. 가동률/KPI 표현 결정

현재 fixture 기준으로는 가동률을 정당하게 산출할 수 없다.

이유:

- `availability`, `uptime`, `OEE`, `production_count`, `throughput`, `operating_state`, `is_operating` 같은 실제 운영 분모/분자 필드가 없다.
- `estimated_downtime_minutes`는 예상 영향이지 실제 가동/비가동 시간 기록이 아니다.
- 생산계획 데이터가 있어도 실제 실적이 없으면 성과 KPI가 아니라 계획 영향 추정만 가능하다.

금지 표현:

- 가동률
- OEE 개선
- 생산량 증가 실적
- 정비로 생산량을 올림
- 실제 개선
- 점검 후 정상화
- 평상시 범위 복귀

허용 표현:

- 예상 생산 영향
- 계획 영향 추정
- 검토 우선순위
- 데이터 품질 보류
- 24시간 위험 예측
- 고장 확정 아님
- 정비 후 관측 대기

## 8. 예측 의미 결정

현재 모델/fixture의 예측 의미는 다음과 같이 표현한다.

- 현재 예측은 24h horizon binary risk에 가깝다.
- 정확한 RUL 또는 “몇 시간 뒤 고장” 예측으로 표현하지 않는다.
- “24시간 내 위험 예측”은 가능하다.
- “6시간 뒤 고장”, “정확한 고장 예정 시각”은 표현하지 않는다.
- GS fixture는 fleet base-rate dataset이 아니라 시나리오 fixture다.
- 따라서 `24시간 이내 고장 발생률` 원그래프는 메인 KPI로 적합하지 않다.

## 9. 피처/파생값 그래프 결정

UI는 모든 피처 시계열을 실제 `historyPoints` 기반으로 표시한다.

결정 사항:

- 대표 피처 1개만 표시하지 않는다.
- 모든 direct feature는 기본적으로 그래프 표시 대상이다.
- `historyPoints`가 없으면 임의 그래프를 만들지 않고 empty state를 표시한다.
- null 또는 quality hold 값은 품질 상태가 드러나게 처리한다.
- 파생 지표는 Frontend에서 계산하지 않는다.
- Backend ViewModel에서 feature로 내려온 파생값만 표시한다.

파생 지표 key:

- `temperature_difference_k`
- `mechanical_power_w`
- `overstrain_index`

파생 지표가 없으면 `파생 지표 미연결` empty state를 표시한다.

## 10. 작업요청/정비 상태 결정

작업요청과 정비 완료는 분리한다.

결정 사항:

- `작업 요청`은 WorkOrder/Action 요청 생성이다.
- `작업 요청` 시점에 `MaintenanceEvent`를 만들지 않는다.
- `MaintenanceEvent`는 실제 정비 완료 사실이 생겼을 때만 생성한다.
- MaintenanceEvent는 immutable completed maintenance fact로 취급한다.
- `점검 시작 -> 정비 완료` 시간은 정비 리드타임/운영 이력으로 저장한다.
- 현재 예측 모델의 직접 입력값으로 `maintenance_duration_minutes`를 바로 넣지는 않는다.
- 정비 완료 시각은 이후 재예측 구간을 나누는 기준점이다.
- 재예측은 정비 완료 이후 새 관측이 쌓인 뒤 수행한다.
- 관측이 부족하면 `정비 후 관측 대기`로 표시한다.

상태 흐름:

```text
candidate_recommended
  -> work_requested
  -> assigned
  -> inspection_started
  -> maintenance_completed
  -> observation_pending
  -> ready_for_reprediction
```

기본 상태:

- 실제 WorkOrder API/DB 상태가 없으면 `candidate_recommended`로 둔다.
- 절대 기본값을 `maintenance_completed`로 두지 않는다.

## 11. 사이드뷰 UX 결정

현재 사이드뷰 탭은 `상태 / 처리` 두 개를 유지한다.

새 `작업` 탭은 만들지 않는다.

최종 구조:

```text
[사이드뷰 헤더]
설비명 / 라인 / 위험 상태 / 고장 확정 아님

[작업 상태 고정 바]
현재 상태
다음 권장 액션
primary action 버튼 1개

[탭]
상태 | 처리
```

결정 사항:

- 작업 상태 고정 바는 탭 바깥, 사이드뷰 헤더 아래에 둔다.
- 사용자가 `상태` 탭에 있든 `처리` 탭에 있든 현재 상태와 다음 액션이 계속 보인다.
- `상태` 탭은 왜 이 상태인지 이해하는 곳이다.
- `처리` 탭은 실제로 상태를 바꾸는 곳이다.
- 팝업/모달은 상태 표시용이 아니라 확인/입력용으로만 사용한다.

상태 탭:

- 현재 판단 요약
- 작업 상태 타임라인
- 위험 예측
- 데이터 품질 상태
- review priority
- 전체 피처 그래프
- 파생 지표 그래프
- 생산 영향 추정 요약

처리 탭:

- 현재 가능한 primary action 1개
- 요청 메모
- 담당자
- 조치 유형
- 교체 부품
- 완료 메모
- API 미연결 시 `작업요청 화면에서 처리` 안내

## 12. 역할별 화면 결정

역할별 메인 화면은 같은 내용을 반복하지 않는다.

생산관리자:

- 생산계획
- 예상 생산 영향
- 위험 라인
- 라인별 설비 영향 맵
- 데이터 품질 보류
- 작업 상태는 요약 중심

현장관리자:

- 점검 대상 설비
- 전체 피처 시계열
- 파생 지표 시계열
- 작업 상태
- 점검 위치
- 의심 부품
- 다음 액션

## 13. UI 작업 시 현재 로컬 변경 기준

UI 워크트리:

```text
/Users/hb/Documents/final/ontology-dashboard/.worktrees/feat/asset-detail-agent-ux-workflow-research
```

현재 UI 워크트리에는 이미 큰 로컬 변경이 있다.

- 역할별 메인 화면 분리
- 생산관리자 factory/cell map
- 현장관리자 점검 후보 카드
- 사이드뷰 `상태 / 처리` 탭
- `displayLabels.ts`
- `FeatureSeriesCollection`
- `DerivedMetricSlots`
- map-report UI 톤 이식
- GS fixture asset label 변경

후속 UI 작업은 새로 만드는 작업이 아니라, 이 로컬 변경을 보존하면서 아래를 정리하는 작업이다.

- `codex/operation-context-api` 계약 반영
- `operation_context` rich fields 타입/어댑터 매핑
- hardcoded 생산계획 값을 API 값 우선으로 전환
- factory/cell topology 확정 표현 제거
- line 기준 맵으로 정리
- 작업 상태 고정 바 추가
- 금지 표현 제거

## 14. 다음 작업 순서

1. UI 워크트리에서 `codex/operation-context-api`를 병합하거나 필요한 계약 변경을 반영한다.
2. `operationsContracts.ts` / `operationsAdapters.ts`에 rich `operation_context`를 매핑한다.
3. `OperationsOverviewPage.tsx`의 hardcoded 생산계획 값을 API 우선으로 바꾼다.
4. factory/cell map을 line impact map으로 정리한다.
5. 사이드뷰 헤더 아래 작업 상태 고정 바를 추가한다.
6. `상태` 탭에 작업 상태 타임라인과 전체 피처/파생 그래프를 정렬한다.
7. `처리` 탭에 primary action과 입력 자리만 둔다.
8. map-report 하드코딩 문구 중 정상화/효과 입증처럼 보이는 문구를 제거한다.
9. TypeScript 타입검사와 가능한 프론트 테스트를 실행한다.
10. API 계약과 UI 표시 문구가 어긋나지 않는지 최종 리뷰한다.
