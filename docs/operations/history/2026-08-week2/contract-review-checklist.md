# Week 2 계약 검토 체크리스트

## 1. 목적과 판정 기준

이 문서는 현행 실행 코드와 Week 2 설계안을 비교해 팀 결정을 기록한다. 모든 항목을
미결정으로 간주하지 않으며, [현행 Operations 구현 계약 기준선](../../current-operations-implementation-baseline.md)을
코드 사실의 기준으로 사용한다.

| 분류 | 의미 |
|---|---|
| `현행 구현 계약` | 코드·schema·테스트에서 확인된 값 |
| `용어·표현 합의` | 내부 계약은 유지하고 제품 표시를 통일할 항목 |
| `부분 일치` | 방향은 같지만 필드·경로·책임이 일부 다름 |
| `구현 변경 필요` | 채택하면 코드·API·UI·테스트 변경이 필요한 요구사항 |

각 결정에는 `선택`, `변경 내용`, `코드 영향`, `근거`, `결정자`, `결정일`을 기록한다.

## 2. 현황 요약

| ID | 주제 | 분류 | 결정 상태 |
|---|---|---|---|
| DEC-COM-01 | 기준 저장소 | 현행 구현 계약 | `결정 완료` — PR #9/#10 통합 반영 |
| DEC-COM-02 | 사용자 명칭 | 용어·표현 합의 | `결정 완료` |
| DEC-COM-03 | Decision·Note 범위 | 현행 구현 계약 | `결정 완료` |
| SCR-01 | 화면별 실제 필드 | 부분 일치 | `결정 완료` — Current/Target 분리 |
| SCR-02 | 상태 명칭 | 용어·표현 합의 | `결정 완료` |
| SCR-03 | 필터·정렬·이동 | 현행 구현 계약 | `결정 완료` |
| SCR-04 | 화면 상태 | 현행 구현 계약 | `결정 완료` |
| API-01 | API 구조 | 부분 일치 | `결정 완료` — 현행 유지, Target 분리 |
| API-02 | pagination | 현행 구현 계약 | `결정 완료` |
| API-03 | 위험등급 책임 | 현행 구현 계약 | `결정 완료` |
| API-04 | snapshot·stale | 현행 구현 계약 | `결정 완료` |
| API-05 | 결합 필드·provenance | 부분 일치 | `결정 완료` — 추적 형식은 임시 유지 |
| API-06 | fallback | 현행 구현 계약 | `결정 완료` |
| RPT-01 | Report 입력 JSON | 부분 일치 | `결정 완료` |
| RPT-02 | Report 출력 JSON | 부분 일치 | `결정 완료` |
| RPT-03 | 문장 안전 규칙 | 현행 구현 계약 | `결정 완료` |
| RPT-04 | 실패 대체 | 현행 구현 계약 | `결정 완료` |

이 분류는 팀 결정의 대체물이 아니다. `현행 구현 계약`은 코드 사실을 확정하며,
그 계약을 제품 기준으로 계속 유지할지는 팀이 결정한다.

## 3. 공통 결정

### DEC-COM-01 — 기준 저장소

- 현행: 제품·계약·실행 코드는 `Biz-CollabCraft/ontology_dashboard`를 단일 기준으로
  사용한다. 개인 프로토타입 실행 소스는 PR #9에서 팀 저장소로 이관됐고 PR #10의
  시스템 아키텍처 책임에 맞춰 재배치됐다.
- 결정: Week 2 프론트엔드/API/계약 변경은 팀 저장소에서 수행한다. 개인 프로토타입은
  원본 커밋 provenance와 회귀 비교 자료로만 사용한다.
- 코드 영향: PR #9 병합 커밋 `7e7b9c4`; `api/`, `web/`, `schemas/`, `systems/`,
  `tests/`를 팀 실행 기준으로 사용한다.
- 분류: `현행 구현 계약`
- 상태: `결정 완료` (2026-08-10)

### DEC-COM-02 — Operations 사용자 명칭

- 2026-08-07 당시 결정은 기존 Report/UI view의 `manager`, `engineer`를 유지하는 것이었다.
- 2026-08-18 Closed-loop 계약에서는 Identity/RBAC role code를
  `process_manager`, `process_engineer`, `maintenance_technician`으로 명확히 구분한다.
- 제품 표시 의미는 생산 운영 의사결정자, 현장 엔지니어, 정비 작업자로 고정한다.
- `manager`, `engineer`는 기존 Report/UI compatibility view alias로만 유지하며 RBAC role code와
  같은 enum으로 해석하지 않는다.
- 상세 역할별 Action은
  [`closed-loop-product-consumption-contract.md`](../../../closed-loop-product-consumption-contract.md)를 따른다.
- 분류: `용어·표현 합의`

```text
Identity/RBAC: process_manager / process_engineer / maintenance_technician
제품 표시: 생산 운영 의사결정자 / 현장 엔지니어 / 정비 작업자
legacy Report/UI view: manager / engineer
Closed-loop 결정 상태: 완료
결정일: 2026-08-18
```

### DEC-COM-03 — Decision·Note 범위

- 현행: Decision과 Note 모두 실제 저장 기능이다. 생산 운영 의사결정자(`process_manager`)는
  `events.decision`, 현장 역할은 `events.note` 권한을 사용하며 Activity 감사 이력과 테스트가 있다.
- 결정: Week 2 Operations에서 현행 Decision·Note를 유지한다. Recommendation, 사람의
  Decision과 Note는 분리하고 자동 실행으로 연결하지 않는다.
- 분류: `현행 구현 계약`
- 결정 상태: `완료` (2026-08-07)

## 4. 팀원1 — 화면 계약

### SCR-01 — 화면별 실제 필드

- 현행 Overview: 위험 KPI·Downtime·판단 대기 Event 중심.
- 현행 Objects: 검색·라인·상태·담당자 필터와 설비 Inspector 중심.
- 현행 Operations: Event Queue, Evidence, Decision, Note, Activity 중심.
- 현행 Executive Report: 선택 Event 단위 역할별 보고서.
- V2 제안: 가동·생산·정비 기간 집계, site/cell/기간 필터와 기간 기반 보고서.
- 결정: 네 화면 모두 Current와 Target을 분리해 기록한다. Week 2 구현 여부는
  사용자 가치와 변경 비용으로 판단하며 Target을 현행 설명으로 사용하지 않는다.
- 분류: `부분 일치`
- 결정 상태: `완료` (2026-08-07)

### SCR-02 — 상태 명칭과 표현

- Artifact `status_grade`: `normal`, `attention`, `warning`, `critical`.
- ViewModel 데이터 품질 상태: `data_quality_hold`; Artifact enum이 아니다.
- 현행 표시: 정상, 주의, 경고, 위험, 데이터 확인.
- 결정: API 원본 4등급과 ViewModel 품질 상태를 분리하고 현행 표시 명칭으로 통일한다.
- 분류: `용어·표현 합의`
- 결정 상태: `완료` (2026-08-07)

### SCR-03 — 필터·정렬·이동

- 현행 Objects 필터: 검색, 라인, 상태, 담당자.
- 현행 URL: `view`, `asset_id`, `event_id`, `role`, `workspace_id`.
- 문서 제안: 사이트, 셀, 설비 유형, 상태, 기간과 필터 URL 유지.
- 결정: Week 2는 현행 필터와 URL 상태를 유지한다. site/cell/기간 필터는 Target으로
  남기고 별도 결정 없이 이번 주 구현 범위를 늘리지 않는다.
- 분류: `현행 구현 계약`
- 결정 상태: `완료` (2026-08-07)

### SCR-04 — 화면 상태

- 현행: loading, empty, error, stale, permission과 fallback warning을 사용한다.
- 결정: 현행 상태를 유지한다. 네트워크·5xx는 재시도, 4xx는 수정 안내, permission은
  권한 안내를 제공하고 stale·fallback·품질 보류는 텍스트와 아이콘으로 표시한다.
- 분류: `현행 구현 계약`
- 결정 상태: `완료` (2026-08-07)

## 5. 팀원3 — 데이터·조회·집계 API 계약

### API-01 — API 구조

- 현행 Canonical base path:
  `/api/projects/{project_id}/workspaces/{workspace_id}/predictive-maintenance`.
- 현행 핵심: `GET /dashboard`, `GET /results/latest`.
- 현행 Event: `/api/events/{event_id}/evidence|report|decision|notes|activity`.
- 문서의 `/overview`, `/objects`, `/operations`는 `변경 제안`이다.
- 결정: Week 2는 현행 경로를 유지한다. 화면별 Target API는 호환성과 필요성이
  확인될 때 별도 구현한다.
- 분류: `부분 일치`
- 결정 상태: `완료` (2026-08-07)

### API-02 — 목록 pagination

- 현행 `/results/latest`: `offset`, `limit`, `total`; 기본 100, 최대 500.
- 문서의 `page`, `size`: `변경 제안`.
- 결정: Week 2는 현행 `offset`, `limit`, `total`을 유지한다. page/size는 Target이다.
- 분류: `현행 구현 계약`
- 결정 상태: `완료` (2026-08-07)

### API-03 — 위험등급 산출 책임

- 현행: API는 Artifact의 4등급 `status_grade`를 사용하고 ViewModel은 데이터 품질
  보류를 `data_quality_hold`로 별도 표현한다.
- 결정: 두 상태를 분리하고 조회·Report API는 위험등급을 재계산하지 않는다.
- 분류: `현행 구현 계약`
- 결정 상태: `완료` (2026-08-07)

### API-04 — 기준시각과 stale

- 현행: 프론트가 최신 `observedAt` 기준 24시간 초과를 stale로 판단한다.
- 결정: Week 2는 timezone을 포함한 `observed_at` 기준 프론트 24시간 판정을
  유지한다. 이는 도메인 불변값이 아니라 Operations freshness 정책이며 API 이전은 후속이다.
- 분류: `현행 구현 계약`
- 결정 상태: `완료` (2026-08-07)

### API-05 — 결합 필드와 provenance

- 현행: Result Artifact, Event/Evidence와 Asset/ViewModel 확장 필드가 함께 사용된다.
- 결정: provenance는 구조화해 보존한다. Week 2 `source_field`는 현행 Evidence와
  호환되는 형식을 사용하고 JSON Pointer는 팀원3·4 구현 검토 후 Target으로 판단한다.
- 분류: `부분 일치`
- 결정 상태: `완료` (2026-08-07)

### API-06 — fallback

- 현행: Canonical Runtime 실패 시 Gold Fixture를 사용하고 warning과 fallback
  표시를 제공한다.
- 결정: Gold Fixture 사용 시 source·warning·fallback 표시를 항상 보존하고 데이터
  fallback과 리포트 생성 fallback을 구분한다.
- 분류: `현행 구현 계약`
- 결정 상태: `완료` (2026-08-07)

## 6. 팀원4 — 리포트 API·생성 계약

### RPT-01 — 입력 JSON

- 현행: `ReportRequest(role, locale, use_llm)`.
- 문서의 기간·필터·집계를 포함한 `ReportInput`: `변경 제안`.
- 검토안: V2 `ReportInput`을 변경 제안으로 유지하고 현행 `ReportRequest`를
  대체하지 않는다. mock 입력으로 deterministic 생성 가능성을 먼저 검증한다.
- 담당: 팀원4가 mock 계약 검증과 향후 리포트 API 구현을 맡는다.
- 코드 영향: 이번 단계는 API 변경 없음.
- 결정: Week 2는 Event Evidence 기반 mock으로 deterministic 기준선을 먼저 만든다.
  기간 기반 Executive ReportInput은 제품 Target으로 유지하고 추가 집계 API가
  필요한 경우 후속 처리한다.
- 분류: `부분 일치`
- 결정 상태: `완료` (2026-08-07)

### RPT-02 — 출력 JSON

- 현행: `contracts/schemas/report.schema.json`의 role-aware grounded report.
- 문서의 `ReportOutput`: `변경 제안`.
- 검토안: `executive-report-v1.0`을 V2 후보로 검증하고 현행 grounded report
  schema와 분리한다.
- 담당: 팀원4.
- 코드 영향: 실제 적용 시 schema·UI·테스트 변경 필요.
- 결정: Week 2 Event 출력은 현행 grounded report schema를 기준으로 한다.
  `executive-report-v1.0`은 기간 기반 Target 후보로 분리한다.
- 분류: `부분 일치`
- 결정 상태: `완료` (2026-08-07)

### RPT-03 — 문장 규칙

- 현행: 고장·인과·자동 실행을 확정하지 않고 근거·한계·citation을 보존하는
  prompt, schema와 평가 규칙이 있다.
- 검토안: 권장안 수락. 고장·원인 확정, 자동 정지·정비 지시, 비용 절감·생산
  손실 단정을 금지한다. 입력 수치와 enum을 변경하지 않고 없는 값은 추론하지 않는다.
- 분류: `현행 구현 계약`
- 결정 상태: `완료` (2026-08-07)

### RPT-04 — 실패 대체 응답

- 현행: LLM 실패 시 deterministic report, 최종 template fallback과 경고 표시를
  사용한다.
- 검토안: LLM → deterministic → template 흐름을 유지하고 V2 명칭을 별도로
  정의한다. 현행 `deterministic_fallback`은 V2의 `generation_method=deterministic`,
  `fallback_reason=llm_failed`로 매핑한다.
- 담당: 팀원4 Report API.
- 분류: `현행 구현 계약`
- 결정 상태: `완료` (2026-08-07)

## 6.1 팀원2·3 — Generator Feature/Label/Artifact 계약 (PR #21~#24)

| ID | 주제 | 분류 | 결정 상태 | 계약 결정 | 코드 구현 | 테스트 |
|---|---|---|---|---|---|---|
| GEN-FEAT-01 | Feature canonical owner | 현행 구현 계약 | `결정 완료` (`systems/generator`) | 완료 | 완료 | 완료 |
| GEN-FEAT-02 | Feature naming/versioning | 구현 변경 필요 | `목표 계약 / 구현 필요` (ADR-001) | 완료 | 필요 | 필요 |
| GEN-FEAT-03 | asset/time partition | 현행 구현 계약 | `결정 완료` (PR #21 구현됨) | 완료 | 완료 | 완료 |
| GEN-LABEL-01 | failure anchor semantics | 구현 변경 필요 | `목표 계약 / 구현 진행 중` | 완료 | 진행 중 | 진행 중 |
| GEN-LABEL-02 | horizon boundary | 구현 변경 필요 | `목표 계약 / 구현 진행 중` | 완료 | 진행 중 | 진행 중 |
| GEN-LABEL-03 | active failure exclusion / fail-fast 기본값 | 구현 변경 필요 | `목표 계약 / 구현 필요` | 완료 | 필요 | 필요 |
| GEN-ART-01 | run registry vs Model Artifact | 구현 변경 필요 | `목표 계약 / PR #22 구현 필요` | 완료 | 필요 (PR #22) | 필요 |
| GEN-ART-02 | immutable publish/checksum/provider | 구현 변경 필요 | `목표 계약 / PR #22 구현 필요` | 완료 | 필요 (PR #22) | 필요 |
| GEN-ART-03 | Artifact 공식 버전 | 계약 결정 완료 | `model-artifact-v1.0` 최초 공식, 이전 동일 문자열은 개발 초안 | 완료 | 필요 (PR #22) | 필요 (round-trip, manifest 필드 검증) |
| GEN-ART-04 | Artifact 필수 파일·role | 계약 결정 완료 | 6개 파일 전부 필수, 5개 role 전부 `artifact_files` 필수 등록 | 완료 | 필요 (PR #22) | 필요 (round-trip, manifest 필드 검증) |
| GEN-ART-05 | 학습 데이터 분할 전략 | 계약 결정 완료 | `training_config.split_strategy = "asset_time_split"` 기본값 | 완료 | 필요 (PR #22) | 필요 (round-trip, manifest 필드 검증) |
| GEN-ART-06 | Artifact 모델 식별 | 계약 결정 완료 | Manifest canonical identity는 `model_id`/`model_version` 별도 필드. `{model_base}_{version}`은 화면·경로용 파생 표시값일 뿐, 신호(signal) 내 사용 여부는 GEN-STACK-02로 이관 | 완료 | 필요 (PR #22) | 필요 (round-trip, manifest 필드 검증) |
| GEN-API-01 | training daemon 범위 | 구현 변경 필요 | `목표 계약 / PR #23 구현 필요` | 완료 | 필요 | 필요 |
| RUN-OWN-01 | runtime inference owner | 현행 구현 계약 | `결정 완료` (`systems/backend/diagnosis`) | 완료 | 완료 | 완료 |
| RUN-OWN-02 | Product Result Artifact owner | 현행 구현 계약 | `결정 완료` (`systems/backend/diagnosis`) | 완료 | 완료 | 완료 |
| GEN-STACK-02 | 주기적 다중 모델 예측·신호 취합 실행 주체 | **결정 필요** | ADR-002 미해결 항목 — 다음 회의 대상 | **결정 필요** | 미정 | 미정 |
| GEN-ART-07 | Manifest 중첩 객체 엄격성 및 학습 재현성 필드 | **결정 필요** | `training_config`/`provenance`/`compatibility`의 `additionalProperties` 정책과 `feature_count`/`random_seed` 필수 여부를 공식 전환 전에 결정 | **결정 필요** | 미정 | 미정 |

상세 내용은 `docs/operations/generator-feature-label-contract.md`,
`docs/operations/model-artifact-publish-contract.md`,
`docs/architecture-decisions/ADR-001-unified-feature-contract.md`,
`docs/architecture-decisions/ADR-002-training-runtime-prediction-ownership.md`를 따른다.

특히 **GEN-LABEL-03**(fail-fast 기본값)은 PR #21 단독 결정이 아니다. `systems/generator/model/model_training.py`(PR #22)가 `build_labels()`를 호출하는 방식과 직접 연결되므로, #21과 #22 담당자가 함께 결정하고 이 표에 기록한다.

## 7. 결정 기록 양식

각 항목 아래에 다음 형식으로 기록한다.

```text
선택:
변경 내용:
코드 영향:
근거:
결정자:
결정일:
```

## 8. 검토 완료 조건

- 17개 항목의 현행값과 변경 제안이 구분된다.
- 구현 변경 항목에는 영향 범위와 전환 방법이 기록된다.
- 합의 결과가 스키마·기능·API·리포트·Operations 설계에 반영된다.
- 실제 API 경로와 JSON schema를 추적성 매트릭스에 연결한다.
- Week 2 결정에는 결정 근거와 결정일이 있으며 저장소 통합은 후속 항목으로 분리한다.
