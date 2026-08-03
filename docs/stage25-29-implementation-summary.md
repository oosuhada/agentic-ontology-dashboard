# 25~29단계 구현 요약 — Role Workspaces

구현일: 2026-08-01

## 목표

24단계까지 구축한 persistent Dashboard 플랫폼 위에 역할별로 실제 업무가 달라지는 전용 데이터 계약, Board, Action과 승인 workflow를 구현한다.

대상 역할:

- 임원 Viewer
- 품질·감사 Viewer
- 현장 작업자
- FDE
- 데이터 사이언티스트

기본 Dashboard template은 v2로 승격했다. 기존 v1 사용자 override는 stable tab·board ID 병합 규칙으로 유지된다.

## 공통 구조

### Backend

- `role_workflow_models.py`: 역할 workspace와 승인 요청 contract
- `role_workflow_repository.py`: export checkpoint, field Action, template·model approval persistence
- `role_workflow_service.py`: 역할별 집계·재구성·workflow orchestration

### Frontend

- `web/src/features/roles/types.ts`
- `web/src/features/roles/RoleBoardRenderer.tsx`

일반 Dashboard shell과 Board canvas는 유지하고 역할 전용 renderer만 별도 모듈로 분리했다.

### SQLite

추가 테이블:

- `audit_export_checkpoints`
- `field_task_actions`
- `template_publish_requests`
- `model_release_requests`

## 25단계 — 임원 Viewer

### 전용 Board

- Executive Portfolio
- Risk & Impact Trend
- Unresolved Critical Events
- Business Impact Assumptions

### 데이터 계약

`GET /api/role-workspaces/executive`

제공 데이터:

- 조직·workspace 단위 설비·사건 수
- 상태 분포
- 평균 위험도
- 위험·영향 추세
- 운영 decision이 없는 중요 사건
- 추정 downtime 영향

사업 금액 영향은 실제 생산 단가 데이터가 없으므로 `null`로 반환하고 계산 가정을 별도 배열로 표시한다. 임원 화면에서는 센서 시계열을 기본으로 노출하지 않으며 unresolved 사건을 선택하면 기존 Evidence로 drill-down한다.

## 26단계 — 품질·감사 Viewer

### 전용 Board

- Event Reconstruction
- Version Snapshot
- Evidence → Report Trace
- Action History
- Audit Export Checkpoint

### 데이터 계약

`GET /api/role-workspaces/audit`

한 사건을 다음 순서로 재구성한다.

```text
Input snapshot
→ Evidence Package
→ Model·Policy·Context version
→ Report sections
→ Evidence field IDs
→ Human·Ontology·Field Action
```

`POST /api/role-workspaces/audit/export-checkpoints`

Export checkpoint는 현재 재구성 snapshot을 canonical JSON으로 직렬화하고 SHA-256 hash를 저장한다. 실제 파일 export 기능과 별개로 누가, 어떤 형식과 목적으로 snapshot을 고정했는지 `audit.export.checkpoint` 감사 기록을 남긴다.

## 27단계 — 현장 작업자

### 전용 Board

- Mobile Field Task
- Safety & Location
- Measurement & Photo Metadata
- Complete · Issue · Blocked

작은 화면에서는 일반 context panel을 숨기고 task board에서 대상 전환, 안전 확인, checklist, 측정과 상태 Action을 완료한다.

### Ontology Action

- `complete_inspection`
- `report_inspection_issue`
- `mark_inspection_blocked`

모든 Action은 기존 Ontology idempotency와 audit 계약을 사용한다.

현장 입력:

- 완료 checklist
- 측정값
- 위치
- handoff 또는 문제 메모
- 사진 binary가 아닌 metadata

사진 metadata는 filename, captured time, MIME type, size, caption, hash 필드만 허용한다. 실제 binary 업로드는 구현 범위 밖이다.

Offline queue는 아직 실행하지 않으며 다음 계약만 명시한다.

- `implemented: false`
- future option
- client action ID
- server status와 idempotency key 우선 conflict policy

## 28단계 — FDE Workbench

### 전용 Board

- Customer Workspace Overview
- Ontology Registry Workbench
- Deployment Checklist
- Diagnostic Events
- Template Approval Queue

### 보안 경계

FDE가 조회할 수 없는 정보:

- password hash
- session token
- provider secret
- 사용자 계정 관리 API

FDE는 다른 역할 template을 preview·편집할 수 있지만 직접 publish할 수 없다.

```text
FDE draft
→ POST publish request
→ pending_approval
→ Tenant Admin review
→ approve 또는 reject
→ 승인 시 새 immutable template version publish
```

관련 API:

- `POST /api/dashboard-templates/{role}/publish-requests`
- `GET /api/admin/workflow-approvals`
- `POST /api/admin/template-publish-requests/{id}/decision`

## 29단계 — 데이터 사이언티스트 Console

### 전용 Board

- Model & Dataset Versions
- Operational Threshold Cost
- Slice & Error Analysis
- Drift & Schema Anomaly
- Gold Regression
- Release Candidate Approval

### 분리 원칙

학습 지표와 운영 threshold를 같은 metric으로 표현하지 않는다.

```text
training_metrics.scope = training_or_offline_evaluation
operational_thresholds.scope = production_decision_policy
```

현재 fixture heuristic에는 학습 run artifact가 연결되지 않았으므로 training metric은 `available: false`와 이유를 명시한다.

Model Console은 다음을 제공한다.

- Evidence에서 실제 사용 중인 model·policy version
- fixture schema dataset version
- threshold별 개입 수와 상대 비용
- 상태·중요도 slice
- schema·quality anomaly
- Gold 8개 시나리오 회귀 결과

Model release는 즉시 배포하지 않는다.

```text
Data Scientist release candidate
→ pending_approval
→ Tenant Admin approve 또는 reject
→ immutable workflow·audit record
```

관련 API:

- `GET /api/role-workspaces/ml`
- `POST /api/role-workspaces/ml/release-requests`
- `POST /api/admin/model-release-requests/{id}/decision`

## 권한

추가 permission:

- `executive.overview.read`
- `audit.reconstruction.read`
- `audit.export.checkpoint`
- `field.tasks.read`
- `field.tasks.update`
- `fde.workbench.read`
- `dashboards.templates.request`
- `dashboards.templates.approve`
- `ml.console.read`
- `ml.release.request`
- `ml.release.approve`

Tenant admin은 모든 permission을 가진다. FDE는 template 초안과 승인 요청 권한은 있지만 승인 권한이 없다.

## 계약

- Python: `role_workflow_models.py`
- TypeScript: `web/src/features/roles/types.ts`
- JSON Schema: `schemas/role-workspaces.schema.json`

## 테스트

### Backend

총 39건 통과. 25~29단계 전용 5건:

1. Executive aggregate·assumption·drill-down·역할 차단
2. Audit reconstruction·Evidence trace·export checkpoint·audit
3. Mobile field task·측정·사진 metadata·idempotent 완료 Action
4. FDE secret 비노출·직접 publish 차단·관리자 승인
5. Model Console scope 분리·Gold 8/8·release 승인

### Browser E2E

총 11건 통과. 신규 역할 흐름:

1. Executive Portfolio 이해와 unresolved drill-down
2. Audit reconstruction과 export checkpoint
3. 390px 모바일 현장 작업 완료
4. FDE diagnostic과 template 승인 요청 경계
5. Model release 요청과 관리자 approval queue

## 검증 결과

```text
Release gate: ontology-dashboard-v0.5
Checks: 10/10 PASS
Python tests: 39 PASS
Gold scenarios: 8/8 PASS
Playwright: 11 PASS
TypeScript strict check: PASS
Production build: PASS
```

Production build:

```text
HTML: 0.52 kB / gzip 0.32 kB
CSS: 46.00 kB / gzip 8.96 kB
JavaScript: 290.52 kB / gzip 85.38 kB
```

## 다음 단계

- 30단계: LLM·Ontology Planner 고도화
- 31단계: Export·보안·성능·release hardening
