# Asset Detail / Overview UI Decision Log

Date: 2026-08-25

Scope: Asset Detail 후속 작업 중 UI/UX 책임 정리와 역할별 Operations Overview 보강. Agent workflow, Backend risk/criticality/review priority 계산, Closed-loop state machine은 이번 범위에서 제외한다.

## Summary

이번 UI 변경의 핵심 결정은 더 많은 예지보전 정보를 화면에 올리는 것이 아니라,
사용자가 대시보드를 열었을 때 바로 다음 판단과 행동을 알 수 있게 만드는 것이다.

초기 Operations는 Palantir Ontology식 제품 철학에서 출발했다. 즉 설비, 관측값, 위험 판단, 리포트,
권고, 작업 상태가 각각 흩어진 UI 조각이 아니라 하나의 관계망 안에서 이어져야 한다는 생각이다.
하지만 이 철학을 화면에 그대로 풀어내면 Objects, Operations, Report, Ontology Workbench가 모두
많은 근거와 설명을 반복하게 된다. 그 결과 본래 목적이었던 이상감지 기반 모니터링과 리포트
확인이 오히려 무거운 정보 탐색 화면처럼 보였다.

PR #110 / Asset Criticality Modeling 계획서의 단순화 방향은 이 문제를 다시 보게 만든 기준이었다.
그 계획은 “데이터를 많이 보여주는가”보다 “risk, criticality, evidence, context가 같은 판단 시점과
source boundary에서 온 것이라고 말할 수 있는가”를 우선한다. 여기서 UI도 같은 결론을 따른다.
화면은 ontology 관계를 모두 노출하는 곳이 아니라, 관계가 정리된 결과를 사용자가 바로 소비하는
업무 표면이어야 한다.

따라서 이번 변경은 `상황 → 설비 → 작업` 흐름을 한 화면에서 이어가되, 사용자 역할별로 첫눈에
보는 판단 대상을 분리하는 방향으로 정리했다.

- 생산 관리자: 공정/라인/셀 관점에서 오늘 계획 영향과 의사결정 대기 항목을 본다.
- 현장 관리자: 점검 후보 설비와 의심 부품, 센서 관측 흐름, 처리 진입을 본다.
- 상세 사이드뷰: `상태`와 `처리` 탭으로 나누고, 화면 안의 추가 팝업은 만들지 않는다.
- Objects / Operations / Report의 역할 분리는 유지하되, Overview가 빠른 진입 화면 역할을 맡는다.

## Product Rationale

이번 작업의 UX 판단은 세 가지 문제의식에서 출발했다.

첫째, 기존 화면은 PdM의 기술적 설명에는 충실했지만 사용자가 “그래서 지금 무엇을 해야 하는가”를
바로 알기 어려웠다. 위험도, top factor, 리포트 문장, 추천 조치가 여러 화면에 반복되면 사용자는
대시보드에서 유용한 정보를 얻기보다 같은 설명을 다시 해석해야 한다.

둘째, Ontology 철학은 화면에 모든 관계를 드러내는 뜻이 아니다. Operations에서 중요한 것은
`Asset → Observation → Evidence → Recommendation → Work Request → Maintenance Feedback`의 관계를
뒤에서 유지하되, 사용자는 자기 역할에 맞는 업무만 보게 하는 것이다. Ontology Workbench는 관계 탐색과
디버깅의 보조 도구로 남기고, 생산/현장 사용자의 핵심 흐름을 대체하지 않는다.

셋째, Closed-loop 구조가 보여주는 제품 방향은 “리포트를 읽고 끝나는 화면”이 아니라
작업 요청, 작업 시작, 작업자 배정, 작업 종료, 정기 점검, 재관측으로 이어지는 피드백 루프다.
그러려면 UI도 리포트/모니터링 중심에서 멈추지 않고 사용자의 다음 액션을 이끌어야 한다. 다만 이번
PR은 Closed-loop 상태 머신이나 agent workflow를 구현하지 않으므로, 실제 생성된 WorkOrder처럼 보이게
하지 않고 `점검 후보`, `작업요청 미생성`, `검토 필요`로 경계를 표시한다.

이 배경에서 세운 UI 원칙은 다음과 같다.

- 첫 화면은 설명보다 판단을 먼저 준다.
- 역할별로 첫 질문을 다르게 둔다.
- 위험 근거는 숨기지 않되, 모든 화면에서 반복하지 않는다.
- 버튼과 선택으로 다음 업무 흐름이 이어지게 한다.
- 없는 데이터는 정상처럼 보정하지 않고 gap/hold/미연결로 남긴다.
- 자동화와 agent draft는 사람의 승인/작업 상태를 대체하지 않는다.

## Workflow Frame

최종 사용자 흐름은 아래처럼 정리한다.

```text
상황판에서 오늘 볼 위험을 고른다
  → 선택한 설비의 상태와 근거를 확인한다
  → 작업요청 후보 또는 검토 액션으로 넘어간다
  → 담당자/작업 상태/정기 점검/재관측이 Closed-loop로 이어진다
```

이 흐름은 기존 `Overview → Objects → Operations → Report`를 없애는 것이 아니다. 오히려 각 화면의
책임을 더 선명하게 만든다.

| 영역 | 이번 UX 해석 | 줄인 것 |
|---|---|---|
| Overview | 지금 볼 상황과 다음 선택을 보여주는 업무 시작점 | 상세 근거와 리포트 문장 반복 |
| Assets / Objects | 설비 상태, 센서 관측, evidence gap을 확인하는 inspection surface | 작업 승인/생성 UI |
| Work Requests / Operations | 사람이 결정하고 기록해야 할 governed action surface | full evidence explorer 반복 |
| Report | 같은 snapshot을 공유 가능한 narrative로 정리하는 화면 | action control과 KPI 복제 |

## Decision 1. Role-Based Overview

결정:

- 상단 역할 토글 중심 UX를 줄이고, 사이드탭/메인 흐름에서 `현장 관리자`, `생산 관리자` 역할별 화면을 분리한다.
- 두 역할이 같은 KPI 카드 묶음을 공유하지 않게 한다.
- “모든 사용자가 같은 대시보드를 보고 각자 해석하는 방식”이 아니라, 같은 ViewModel을 역할별 업무 질문에 맞게 다르게 소비한다.

근거:

- 생산 관리자는 오늘 계획 영향, 위험 라인, 생산 지연 가능성, 조치 제약을 먼저 판단해야 한다.
- 현장 관리자는 어느 설비와 부품을 확인해야 하는지, WorkOrder가 실제 생성됐는지, 데이터 품질 문제가 있는지를 먼저 확인해야 한다.
- 같은 Overview에서 생산계획 수량, 생산 영향 units, 센서 그래프, 의심 부품을 모두 노출하면 실제 업무 순서가 흐려진다.
- Closed-loop Product 소비 계약은 핵심 Operations UX를 현장 엔지니어, 생산 운영 의사결정자, 정비 작업자가 이어받는 흐름으로 본다. 따라서 첫 화면도 사용자 역할별 다음 행동을 분리해야 한다.

구현 방향:

- `process_manager` topline은 오늘 계획, 최대 계획 영향, 즉시 판단 필요, 데이터 품질 보류, 부품 미확보 중심으로 구성한다.
- `field_operator` topline은 점검 후보, 최우선 설비, 부품 확인 필요, 데이터 품질 확인, WorkOrder 미생성 상태 중심으로 구성한다.
- `24시간 이내 고장 발생률` donut은 메인 KPI에서 제거하고 선택 설비 상세의 보조 위험도 맥락으로만 남긴다.

## Decision 2. Single Screen, Drawer Detail

결정:

- Overview, Assets, Work Orders를 각각 완전히 분리된 주요 화면처럼 반복하지 않고, 역할별 Overview에서 설비/작업 상세로 이어지는 구조를 채택한다.
- 설비나 작업 후보를 선택하면 오른쪽 사이드뷰에서 상세를 열고, 배경 클릭 또는 다른 선택으로 흐름을 바꾼다.
- 사이드뷰 내부는 `상태`와 `처리` 탭만 둔다.
- `상태` 탭은 판단 근거를, `처리` 탭은 다음 업무 진입을 맡는다.

근거:

- 사용자는 “판단 생성 입력”을 작성하는 것보다 버튼과 선택으로 다음 액션을 이어가길 원한다.
- 사이드뷰 안에 다시 팝업을 만들면 현재 설비 상태, 근거, 처리 액션의 관계가 끊긴다.
- Notion식 오른쪽 페이지 패턴은 현재 맥락을 유지하면서 상세를 볼 수 있어 공정 맵/우선순위 목록과 잘 맞는다.
- 작업 요청, 작업 시작, 작업자 배정, 작업 종료, 정기 점검 같은 Closed-loop 단계는 한 번에 구현하지 않더라도 UI 정보 구조가 그 방향을 막지 않아야 한다.

구현 방향:

- 상태 탭: 위험 상태, 센서/피처 관측 흐름, 의심 부품, 점검 위치, 생산 영향 보조 라벨.
- 처리 탭: 작업요청 후보, WorkOrder ID 미생성 상태, 가능한 다음 액션, 메모/검토 진입.
- X 버튼은 제거하고 선택/배경 흐름으로 닫힘을 유도한다.

## Decision 3. Production Manager Factory Map

결정:

- 생산 관리자 화면은 `라인별 설비 영향 맵`을 공장 배치형 UI로 보여준다.
- Canonical V3.1의 `site_id`, `cell_id`, `asset_id`를 기준으로 `4구역 × 5셀 × 셀당 5대`의 100대 설비 배치를 표현한다.
- 각 셀은 공기압축기 1대와 CNC 가공기 4대 슬롯으로 구성한다.

근거:

- Canonical V3.1 기준 데이터셋은 100대 설비 가정을 갖고 있고, `cell_id`로 셀 위치를 추론할 수 있다.
- 사용자가 생산 관리자 관점에서 원하는 것은 “테이블형 라인 요약”보다 전체 공장 어디가 위험한지 한눈에 보는 지도다.
- 단, 물리 토폴로지를 backend 계약으로 새로 확정한 것은 아니므로 UI 문구는 계약 배치/계획 영향 추정임을 표시한다.
- 생산 관리자는 센서별 상세보다 어느 셀/라인이 계획과 작업 순서에 영향을 주는지 먼저 알아야 한다.

구현 방향:

- `CNC-S04-L02-03`은 `4구역 · 2셀 · CNC 가공기 3`으로 표시한다.
- `CMP-*`는 `공기압축기`, `CNC-*`는 `CNC 가공기`로 표시한다.
- 정상/위험/경고/주의/데이터 품질 보류 상태를 색상으로 구분한다.
- 상세 데이터가 연결되지 않은 슬롯은 `정상`으로 보이지 않게 `상태 미연결`로 표시한다.

## Decision 4. Canonical ID Alignment

결정:

- GS fixture의 예전 `M-*` asset id를 Canonical V3.1 규칙의 설비 ID로 정리한다.

## Decision 5. Closed-loop Read Surface Boundary

결정:

- Overview의 작업 상태 큐와 사이드뷰 처리 탭은 Closed-loop 실행을 새로 구현하지 않고,
  `WorkOrder`, `MaintenanceAction`, `MaintenanceEvent`, `Activity`, `available_actions`를
  받을 수 있는 read surface로 정리한다.
- API가 closed-loop 요약을 내려주면 그 상태와 ID를 우선 표시하고, 없으면 `작업요청 미생성 후보`와
  화면용 demo 상태로 남긴다.
- closed-loop read model이 있는 경우 프론트가 상태를 임의로 다음 단계로 전이하지 않는다. 실제 상태 변경은
  후속 mutation API와 idempotency 계약이 연결된 뒤 처리한다.

근거:

- Issue #99는 Maintenance Loop Prototype을 그대로 복사하는 작업이 아니라, canonical 시스템 이식 전
  Integration Gate를 관리하는 이슈다.
- PR #103으로 Inspection WorkOrder, Operations manual Recommendation, Decision, WorkOrder,
  Persistence의 기본 계약은 들어왔지만 Runtime Overlay, outbox 운영 복구, 정비 후 Product Result,
  실제 E2E는 아직 상위 Integration Gate로 남아 있다.
- 따라서 이번 UI PR은 사용자가 볼 작업 흐름을 막지 않도록 읽기/표시 계약을 준비하되, WorkOrder ID,
  MaintenanceEvent ID, 권한 액션을 프론트에서 합성하지 않는다.

구현 방향:

- `AssetDetailViewModel.closed_loop`는 optional summary envelope로 소비한다.
- `work_orders[]`, `maintenance_actions[]`, `maintenance_events[]`, `activities[]`,
  `available_actions[]`, `runtime_status`를 화면 표시용으로 보존한다.
- 사이드뷰의 현재 상태, 작업 ID, 담당자, 다음 권장 액션은 closed-loop read model이 있으면 그 값을 우선한다.
- Overview 상단의 작업 상태 KPI도 같은 closed-loop read model을 우선한다. 큐와 사이드뷰가
  `작업 요청됨`을 보이는데 상단 카드만 `미생성`으로 남으면 사용자가 상태 source를 신뢰하기 어렵다.
- closed-loop 값이 없으면 기존처럼 후보 추천, 작업요청 미생성, API 미연결 문구로 경계를 표시한다.
- UI 표시명은 하드코딩된 “33호기” 같은 번호가 아니라 `site/cell/slot` 기반 설비명으로 매핑한다.

근거:

- `M-033` 같은 ID는 Canonical V3.1의 `CNC-Sxx-Lxx-xx` / `CMP-Sxx-Lxx-xx` 배치 추론과 맞지 않는다.
- 공장 맵은 슬롯 ID와 ViewModel asset ID가 일치해야 상태 색상을 정확히 표시할 수 있다.
- 이전 서버 프로세스가 fixture를 메모리에 들고 있으면 최신 ID 변경이 반영되지 않아 지도 슬롯이 모두 미연결로 보일 수 있다.
- `ManufacturingPredictiveMaintenanceService`는 서버 시작 시점에 `data/fixtures/GS-*.json`을 읽어
  `project_fixtures`에 보관한다. 따라서 GS-004 fixture에 `closed_loop`를 추가한 뒤에도 기존 8100
  백엔드를 재시작하지 않으면 브라우저에는 예전 `작업요청 미생성` 스냅샷이 계속 보인다.
- 8100 백엔드를 현재 worktree 기준으로 재기동한 뒤 `EVT-GS-004 / CNC-S04-L02-03`에서
  `WO-INS-GS-004-001`, `작업 요청됨`, `현재 상태 · API`, `점검 승인` 표시를 확인했다.

Closed-loop 담당자 handoff:

- UI는 `closed_loop.work_orders[]`, `available_actions[]`, `activities[]`를 읽고 표시하는 surface까지 맡는다.
- `점검 승인`, `작업 요청`, `담당자 배정`, `점검 시작`, `정비 완료`, `정비 후 관측 대기`,
  `재예측 가능`을 실제 DB/API 상태 전이로 연결하는 일은 Closed-loop mutation/API 작업으로 넘긴다.
- mutation API가 연결되기 전까지 UI는 WorkOrder ID, MaintenanceAction ID, MaintenanceEvent ID,
  권한 액션, 완료 상태를 합성하지 않는다.
- 후속 API는 idempotency, 권한, 상태 전이 실패, Activity append, 정비 후 Product Result/재예측
  연결 기준을 함께 가져야 한다. 버튼 로딩과 팝업 UX는 이미 화면 흐름을 검증하기 위한 shell로만 남긴다.

대표 매핑:

| Event | Canonical asset | 표시명 | 의미 |
|---|---|---|---|
| `EVT-GS-001` | `CNC-S01-L01-01` | 1구역 · 1셀 · CNC 가공기 1 | 정상 안정 사례 |
| `EVT-GS-002` | `CNC-S04-L04-01` | 4구역 · 4셀 · CNC 가공기 1 | 공구 마모 경고 |
| `EVT-GS-003` | `CNC-S01-L04-03` | 1구역 · 4셀 · CNC 가공기 3 | 열 방산 경고 |
| `EVT-GS-004` | `CNC-S04-L02-03` | 4구역 · 2셀 · CNC 가공기 3 | 구동부 과부하 critical |
| `EVT-GS-005` | `CNC-S03-L01-03` | 3구역 · 1셀 · CNC 가공기 3 | 복합 요인 warning |
| `EVT-GS-006` | `CNC-S02-L02-02` | 2구역 · 2셀 · CNC 가공기 2 | 낮은 신뢰도 |
| `EVT-GS-007` | `CNC-S04-L05-01` | 4구역 · 5셀 · CNC 가공기 1 | 데이터 품질 보류 |
| `EVT-GS-008` | `CNC-S04-L04-02` | 4구역 · 4셀 · CNC 가공기 2 | LLM offline fallback |

## Decision 6. Sensor Observation Flow

결정:

- 현장 관리자 상세에서는 선택 설비의 모든 센서/피처를 `historyPoints` 기반으로 표시한다.
- `시계열` 용어는 현장 화면에서 줄이고 `관측 흐름`, `최근 24시간 관측 분포` 같은 표현으로 대체한다.
- 파생 지표도 backend/ViewModel에서 내려온 feature만 같은 그래프 컴포넌트로 표시하고, 기본은 접힌 상태로 둔다.

근거:

- 현장 관리자는 모델 용어보다 토크, 공구 마모, 회전 속도 같은 현장 점검 항목을 우선 이해해야 한다.
- `features[].history.points`가 최신 계약이고, 프론트는 legacy feature-level series 필드를 가정하면 안 된다.
- 현재값은 화면 표현상 최근 관측 흐름에 이어서 보여줄 수 있지만, 계약 payload의 `current`와 `history`를 병합하지 않는다.
- 그래프는 “많아 보이는 데이터”가 아니라 점검자가 어느 부품과 센서를 먼저 확인할지 판단하게 해주는 evidence여야 한다.

구현 방향:

- 토크, 공구 마모, 회전 속도를 우선 강조한다.
- 온도처럼 판단력이 낮은 그래프는 보조 관측으로 접거나 아래에 둔다.
- 정상 범위 문구는 `최근 24시간 관측 분포`로 바꾸고, 이탈 표시는 `최근 분포 대비 이탈`로 표현한다.
- 값이 없는 파생 지표는 `ViewModel 연결 후 표시` 빈 상태로 둔다.

## Decision 7. Production Impact Wording

결정:

- 실제 운영 성과나 정비 효과가 입증된 것처럼 보이는 표현은 사용하지 않는다.
- 생산 관리자 화면에서는 `예상 생산 영향`, `계획 영향 추정`, `검토 우선순위`, `데이터 품질 보류`로 표현한다.

근거:

- 현재 fixture와 ViewModel로는 실제 uptime/downtime, OEE, production count를 정당하게 산출할 수 없다.
- `estimated_downtime_minutes`를 설비 운영 성과 지표로 변환하면 frontend synthesis가 된다.
- 생산계획 데이터는 아직 ViewModel/API 연결 전이므로 `synthetic_capacity_model 기반 계획 영향 추정` 경계를 명확히 해야 한다.

적용 문구:

- 오늘 계획: `16,200개/일`
- 최대 계획 영향: `EVT-GS-004 / CNC-S04-L02-03 / 4구역 2셀 / 51 units 예상`
- 데이터 품질 보류: `EVT-GS-007 / CNC-S04-L05-01`
- 부품 제약: GS-004는 `spare_part_available: false`이므로 `부품 미확보`

## Decision 8. Frontend Synthesis Boundary

결정:

- 프론트는 다음 값을 새로 계산하거나 사실처럼 보이게 만들지 않는다.

```text
criticality
review_priority
WorkOrder ID
Recommendation state
permission / available_actions
failure probability
production count
uptime / downtime / availability
derived sensor values
```

근거:

- 이 값들은 backend ViewModel, Diagnosis Runtime, Closed-loop Domain, authorization projection의 소유다.
- UI는 같은 ViewModel을 역할별로 다르게 소비하는 표현 레이어다.
- 없는 데이터는 `정상`, `low`, `false`, `0`으로 보정하지 않고 gap/hold/미연결로 표시해야 한다.
- Palantir Ontology식 객체-관계 철학을 UI에 적용한다는 것은 프론트가 임의 사실을 만드는 것이 아니라, 원천/근거/작업 상태의 소유권을 잃지 않는다는 뜻이다.

구현 방향:

- missing context는 `상태 미연결`, `데이터 품질 확인 필요`, `생산 영향 미산정`으로 표시한다.
- `features[].current`와 `features[].history.points`는 UI 표현에서만 이어 보이게 하고 payload는 변경하지 않는다.
- factory map의 빈 슬롯은 `normal`이 아니라 neutral slot 상태로 둔다.

## Decision 9. Agent Review Summary Read Surface

결정:

- Overview 사이드뷰와 Report는 `Agent Review Summary` 저장본을 조회하는 read surface로 둔다.
- 사이드뷰 클릭, 탭 전환, 화면 새로고침은 LLM 생성 트리거가 아니다.
- 같은 Product Result/Evidence snapshot과 같은 prompt/schema/model version에서는 같은 Summary를 재사용한다.
- 새 Summary 생성은 backend watcher가 evidence snapshot diff 또는 version diff를 감지했을 때 수행한다.
- UI는 Summary 상태를 `ready`, `generating`, `fallback`, `failed`, `stale`처럼 표시할 수 있지만,
  Summary 문장을 Closed-loop 추천, 승인, 상태 전이의 근거로 사용하지 않는다.

근거:

- 사용자가 사이드뷰를 열 때마다 LLM을 호출하면 같은 근거에 대해 문장, 비용, 지연, audit trail이 흔들린다.
- AI 요약은 Product Result/Evidence를 사람이 빠르게 읽기 위한 표현 산출물이지 새로운 사실 source가 아니다.
- Closed-loop는 Summary 문장이 아니라 Product Result/Evidence `snapshot_basis`와 Recommendation/Action 계약을 기준으로 동작해야 한다.

구현 방향:

- UI는 `summary_id`, `summary_key`, `status`, `generated_at`, `snapshot_basis`, `fallback_reason`을 읽어 표시한다.
- 저장본이 없고 watcher가 생성 중이면 skeleton/loading 대신 `generating` 상태를 표시한다.
- validation 실패 또는 provider 부재 시 deterministic fallback Summary를 같은 표시 계약으로 소비한다.
- Summary와 화면 ViewModel이 같은 snapshot을 소비했는지 `snapshot_basis` 또는 source checksum으로 표시/검증한다.

## Verification Evidence

현재 변경에서 확인한 검증:

```text
npm run lint
```

결과:

```text
tsc --noEmit passed
```

추가로 확인한 runtime evidence:

- 기존 백엔드 프로세스가 fixture를 메모리에 보유한 상태에서는 최신 Canonical ID가 화면에 반영되지 않을 수 있었다.
- 백엔드를 현재 worktree 기준으로 재기동한 뒤, 생산 관리자 공장 맵에서 `critical`, `warning`, `attention`, `hold`, `normal` 노드가 렌더링되는 것을 확인했다.
- `EVT-GS-004` 선택 상태에서 `4구역 · 2셀 · CNC 가공기 3` 슬롯이 `critical`로 매칭되는 것을 확인했다.

## Files Touched By This Decision Set

주요 구현 파일:

- `systems/frontend/src/features/operations/overview/OperationsOverviewPage.tsx`
- `systems/frontend/src/features/operations/operations.css`
- `systems/frontend/src/features/operations/displayLabels.ts`
- `systems/frontend/src/features/operations/api/operationsAdapters.ts`
- `systems/frontend/src/features/operations/api/operationsContracts.ts`
- `systems/frontend/src/features/operations/report/OperationsMapReportAssetDetailView.tsx`
- `systems/backend/app/operations/service.py`
- `systems/frontend/src/types.ts`

계약/fixture/test:

- `contracts/schemas/input-event.schema.json`
- `data/fixtures/GS-001-normal-stable.json`
- `data/fixtures/GS-002-tool-wear-warning.json`
- `data/fixtures/GS-003-heat-dissipation-warning.json`
- `data/fixtures/GS-004-power-overstrain-critical.json`
- `data/fixtures/GS-005-multi-factor-warning.json`
- `data/fixtures/GS-006-low-confidence.json`
- `data/fixtures/GS-007-invalid-sensor-data.json`
- `data/fixtures/GS-008-llm-offline.json`
- `tests/test_operations.py`

## Follow-Up Items

Agent workflow로 넘길 항목:

- Decision Packet 기반 agent draft 작성.
- draft와 실제 Recommendation/Decision/WorkOrder state 분리 표시.
- `available_actions` 기반 governed action proposal 표시.
- 사용자 승인 전 WorkOrder/MaintenanceAction 자동 생성 금지.

Backend/ViewModel 후속 항목:

- 생산 계획 ViewModel 연결.
- 실제 생산량, OEE, uptime/downtime이 필요한 경우 별도 계약으로 추가.
- 파생 지표는 backend에서 `features[].history.points` 형태로 내려주기.
- 공장 물리 토폴로지를 실제 계약으로 격상할지 결정.

문서/검증 후속 항목:

- 브라우저 E2E에서 생산 관리자 공장 맵의 critical/warning/hold 노드 렌더링 검증 추가.
- `M-*` 레거시 URL 접근 시 Canonical asset id로 안내하거나 selection fallback 처리 여부 결정.
- 스크린샷 evidence를 PR 본문에 첨부할지 결정.
