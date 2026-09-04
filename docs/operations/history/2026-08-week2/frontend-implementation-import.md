# Week 2 Operations 실행 소스 이관 기록

- 상태: 팀 저장소 이관 기준
- 이관 대상 저장소: `Biz-CollabCraft/ontology_dashboard`
- 원본 프로토타입: `oosuhada/agentic-ontology-dashboard`
- 원본 브랜치: `feature/predictive-maintenance-adaptive-modeling`
- 원본 커밋: `37c1251b46cb80f793d782088849b4b02d9cc295`
- 원본 커밋 제목: `fix: limit Operations demo login roles`

## 목적

개인 프로토타입에만 존재하던 Week 2 Operations 실행 코드를 팀 저장소의 실제 개발
기준으로 승격한다. 문서만 복사하는 것이 아니라 Operations 화면을 실행하는 프론트엔드와
해당 화면이 사용하는 백엔드·스키마·실행 스크립트를 함께 이관한다.

## 이관한 실행 소스

- `systems/frontend/`: React/Vite 프론트엔드, Overview·Objects·Operations·Event Executive Brief 포함
- `systems/backend/`: FastAPI 백엔드, predictive-maintenance runtime과 Event/Report API 포함
- `ml/`: 모델링/예측 보조 코드
- `schemas/`: Result Artifact, Evidence, Dashboard 등 공통 계약
- `scripts/`: 로컬 실행, 적재, 검증 스크립트
- `tests/`: API·계약·Operations 검증 테스트
- `infra/`: 로컬 Docker/DB 실행 구성
- `data/`: 실행에 필요한 소규모 fixture와 manifest
- `prompts/`, `evaluation/`: 실행·검증에 필요한 보조 자산

팀 저장소에 이미 존재하던 `docs/` 계약 문서와 `.github/` workflow는 덮어쓰지
않았다. 팀 문서의 Current/Target 결정이 실행 코드보다 우선하며, 구현 차이는 별도
PR에서 수렴한다.

## Week 2 Operations 화면

원본 커밋에서 다음 화면 캡처도 팀 문서 자산으로 함께 이관했다.

1. [Overview desktop](./assets/week2-operations-frontend-convergence/01-overview-desktop.png)
2. [Objects inspector desktop](./assets/week2-operations-frontend-convergence/02-objects-inspector-desktop.png)
3. [Operations desktop](./assets/week2-operations-frontend-convergence/03-operations-desktop.png)
4. [Event Executive Brief A4](./assets/week2-operations-frontend-convergence/04-executive-report-a4.png)
5. [Overview mobile](./assets/week2-operations-frontend-convergence/05-overview-mobile.png)

## 코드상 주요 화면 위치

- `systems/frontend/src/features/blueprint/BlueprintManufacturingApp.tsx`
- `systems/frontend/src/features/blueprint-v2/BlueprintManufacturingV2App.tsx`
- `systems/frontend/src/features/manufacturing/ManufacturingApp.tsx`
- `systems/frontend/src/features/dashboard/`
- `systems/frontend/src/features/reports/RoleReportWorkbench.tsx`

## 이관하지 않은 것

개인 프로토타입의 전체 `docs/`와 상용화 Phase 문서는 팀 저장소에 그대로 복제하지
않는다. 요구사항·기능·API·스키마의 공식 기준은 이미 팀 저장소의
현재 계약은 `docs/operations/`에 존재하므로 중복 계약 문서를 만들지 않는다.

Canonical V3.1의 원본/생성 데이터와 대용량 산출물은 역할상
`Biz-CollabCraft/gen_data`로 분리한다.

## 이후 기준

이관 이후 Week 2 Operations 프론트엔드/API 수정은 팀 저장소에서 브랜치를 생성해 PR로
반영한다. 개인 프로토타입에 추가된 변경이 필요하면 커밋 단위로 비교한 뒤 선택적으로
포팅하고, 두 저장소를 동시에 독립적으로 수정해 서로 다른 최신본을 만들지 않는다.

### 공식 Week 2 제품 Surface

- 공식 진입점: `/app/projects/{project_id}/operations`
- 공식 화면: Overview, Objects, Operations, Event Executive Brief
- 기본 설정: `VITE_WEEK2_Operations_ONLY=true`
- Dataset, Governance, Modeling, Agent, Analysis, Ontology 전체 Workbench와
  Blueprint/Commercial 화면은 import 자산으로 보존하되 Week 2 공식 Surface에서는
  노출하지 않는다.
- 후속 개발이나 비교 검증이 필요할 때만 `VITE_WEEK2_Operations_ONLY=false`로 기존 route를
  명시적으로 다시 활성화한다.
