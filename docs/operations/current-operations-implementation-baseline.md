# 현행 Operations 구현 계약 기준선

## 1. 목적과 기준

이 문서는 현재 명세의 제안/Target과 이미 구현된 제품 계약을 구분하기 위한 기준선이다.

- 제품·계약·실행 코드 기준: `Biz-CollabCraft/ontology_dashboard`
- 통합 기준: PR #9 병합 커밋 `7e7b9c4` (2026-08-10)
- 실행 책임 기준: PR #10 시스템 아키텍처를 반영한 PR #9 재배치 결과
- 비교 provenance: `oosuhada/agentic-ontology-dashboard`의
  `codex/current-operations-repository-convergence-20260806` 브랜치와 원본 커밋 `37c1251`

개인 프로토타입은 더 이상 현행 실행 기준이 아니다. 이후 Operations 코드·계약 변경은
팀 저장소에서 수행하며, 개인 프로토타입은 이관 provenance와 회귀 비교에만 사용한다.

현행 구현값은 제품 방향이 영구 확정됐다는 의미가 아니다. 이를 변경하는 항목은
단순 확인이 아니라 코드·테스트·데이터 마이그레이션 영향을 검토하는 변경 결정이다.

### 1.1 통합 후 실행 책임

```text
gen_data
Source Data / Canonical V3.1 source-reference baseline
      ↓
systems/generator
Protocol Mapping 적용 → Canonical Observation Dataset → Preprocessing Plan → Feature Schema 기반 Feature Dataset Bundle → Training/Evaluation → Model Artifact
      ↓
systems/backend/app/diagnosis
Model Artifact 검증 → Runtime Inference → Result Artifact / Evidence
      ↓
api / web / report consumer
```

`gen_data`의 prediction/model output은 운영 최신 결과가 아니라 compatibility·regression
fixture다. 운영 Product Result Artifact는 주입된 Model Artifact를 검증한 Backend
runtime inference에서 생성한다. Model Artifact가 없는 로컬 데모에서는 명시적
compatibility fallback을 허용하지만, 그 외 환경은 fail-closed를 따른다.

## 2. 확인된 현행 계약

| 영역 | 현행 구현 |
|---|---|
| Identity/RBAC 역할 | `process_manager`, `process_engineer`, `maintenance_technician` 등 canonical role code |
| Closed-loop 제품 역할 | 생산 운영 의사결정자, 현장 엔지니어, 정비 작업자 |
| legacy Report/UI view alias | `manager`, `engineer`; RBAC role code와 별도 compatibility 관점 |
| 핵심 권한 | `process_manager`의 `events.decision`, 현장 역할의 `events.note`/field task capability; 최종 Action 노출은 Backend `available_actions`가 결정 |
| 쓰기 기능 | Decision·Note 실제 저장, Activity 감사 이력 제공 |
| Operations | Event Queue, Evidence, Recommendation, Decision, Note, Activity 중심 |
| Artifact 위험 enum | `normal`, `attention`, `warning`, `critical` |
| ViewModel 품질 상태 | `data_quality_hold`; Artifact `status_grade`와 별도 |
| 상태 표시 | 정상, 주의, 경고, 위험, 데이터 확인 |
| Objects 필터 | 검색, 라인, 상태, 담당자 |
| URL 상태 | `view`, `asset_id`, `event_id`, `role`, `workspace_id` |
| 최신 결과 pagination | `offset`, `limit`, `total`; 기본 100, 최대 500 |
| stale | 프론트에서 최신 관측시각 기준 24시간 초과 |
| 데이터 fallback | Canonical Runtime 실패 시 Gold Fixture와 warning 사용 |
| Report 요청 | `ReportRequest(role, locale, use_llm)` |
| Report 출력 | `contracts/schemas/report.schema.json`의 role-aware grounded report |
| Report fallback | LLM → deterministic → 최종 template 표시 흐름 |
| 공식 Operations 진입점 | `/app/projects/{project_id}/operations` |
| 확장 화면 노출 | 기본 비노출. `VITE_WEEK2_Operations_ONLY=false`일 때만 기존 Workbench route 사용 |
| 현행 보고서 단위 | 선택 Event 단위 `Event Executive Brief`; 기간 집계형 Executive Report는 V2 Target |

## 3. 현행 핵심 API

Canonical Predictive Maintenance base path:

```text
/api/projects/{project_id}/workspaces/{workspace_id}/predictive-maintenance
```

| Method | Path |
|---|---|
| GET | `/dashboard` |
| GET | `/results/latest` |
| GET | `/api/events/{event_id}/evidence` |
| POST | `/api/events/{event_id}/report` |
| POST | `/api/events/{event_id}/decision` |
| POST | `/api/events/{event_id}/notes` |
| GET | `/api/events/{event_id}/activity` |

## 4. 변경 결정이 필요한 주요 차이

| 주제 | 현행 | 기존 제안/Target | 결정 성격 |
|---|---|---|---|
| Operations | Event 업무 흐름 | 생산 Cycle·정비 목록 | 제품 흐름 재설계 |
| Decision·Note | 저장 기능 | 조회 중심 또는 제외 | 기존 기능 제거·범위 변경 |
| Pagination | offset/limit | page/size | API 계약 변경 |
| Report JSON | ReportRequest와 report schema | ReportInput/ReportOutput | API·LLM·UI 계약 변경 |
| Objects 필터 | 검색·라인·상태·담당자 | 사이트·셀·유형·상태·기간 | UI·조회 계약 변경 |
| 역할 명칭 | RBAC `process_manager`/`process_engineer`/`maintenance_technician`; legacy view `manager`/`engineer` | 생산 운영 의사결정자/현장 엔지니어/정비 작업자 | Closed-loop canonical 계약으로 구분 완료 |

## 5. 사용 원칙

- 명세서의 현행 설명은 이 문서를 따른다.
- Closed-loop의 canonical 사용자 역할·Action·`available_actions`·Event API 소비 규칙은
  [`../closed-loop-product-consumption-contract.md`](../closed-loop-product-consumption-contract.md)를 따른다.
- `manager`/`engineer`는 기존 Report/UI compatibility view 값으로만 설명하고 Identity/RBAC role code와
  같은 enum으로 취급하지 않는다.
- 현행과 다른 내용에는 `변경 제안`을 표시한다.
- 변경 제안을 채택하기 전에는 실제 API 경로와 JSON schema를 대체하지 않는다.
- 팀 결정에는 결정자, 결정일, 코드 영향과 전환 방법을 기록한다.
- 현재 Operations 기준선에서는 `/operations` 외 Dataset, Governance, Modeling, Agent, Analysis,
  Blueprint/Commercial 화면을 공식 제품 Surface로 취급하지 않는다. 코드는 후속 개발을
  위해 보존하되 기본 런타임에서는 `/operations`로 수렴시킨다.
