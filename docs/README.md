# 프로젝트 문서

이 디렉터리는 `Biz-CollabCraft/ontology_dashboard`의 제품 요구사항, 데이터 계약,
API 계약과 팀 공유 문서를 관리한다.

## 문서 묶음

- [최종 역할 분배 및 Step별 실행 계획](./final_team_role_and_step_plan.md)
- [Ontology Operations & Closed-loop 구현 계획](./closed-loop-implementation-plan.md)
- [Closed-loop Domain 계약](./closed-loop-domain-contract.md)
- [Closed-loop Product/API/UI 소비 계약](./closed-loop-product-consumption-contract.md)
- [Closed-loop Runtime Overlay 통합 계약](./closed-loop-runtime-overlay-contract.md)
- [Runtime Overlay 기존 계획 변경 영향 안내](./closed-loop-runtime-overlay-change-impact.md)
- [아키텍처](./architecture.md)
- [CI 개발 피드백 시간 단축 제안](./ci-development-feedback-optimization-proposal.md)
- [Backend Domain-First Migration Map](./backend-migration-map.md)
- [Architecture Decision Records](./architecture-decisions/README.md)
- [Operations / Product documentation](./operations/README.md)
  - [요구사항 명세](./operations/requirements-specification.md)
  - [기능 명세](./operations/functional-specification.md)
  - [API 명세](./operations/api-specification.md)
  - [공통 스키마 정의](./operations/schema-definition.md)
  - [Generator Feature/Label 계약](./operations/generator-feature-label-contract.md)
  - [Model Artifact Publish 계약](./operations/model-artifact-publish-contract.md)
  - [Runtime Ownership](./operations/runtime-ownership-integration.md)
  - [추적성 매트릭스](./operations/traceability-matrix.md)
  - [2026-08 Week 2 history](./operations/history/2026-08-week2/)
- [AI 코드 리뷰 컨텍스트](./ai-code-review-context.md)

## 개인 기여 문서

- [Backend Runtime / Evidence Delivery Contribution](./contributions/hb-backend-runtime-evidence.md)
- [AI Review / Evidence Boundary Contribution](./contributions/hb-ai-review-evidence.md)

## 공유 계약 (Shared Contracts)

시스템 간 공유 계약은 저장소 최상위 `contracts/`에서 관리한다.
현재 공유 JSON Schema는 `contracts/schemas/`로 물리 이동이 완료되었으며, 실행 코드, 테스트, CI, Docker 참조가 모두 `contracts/schemas/`를 정본으로 바라보도록 설정되어 있다.
자세한 내용은 [`contracts/README.md`](../contracts/README.md)를 참고한다.

## 관리 원칙

- 문서 묶음은 목적이나 마일스톤을 나타내는 이름으로 `docs/` 바로 아래에 둔다.
- 다른 저장소의 번호형 디렉터리 체계를 그대로 복사하지 않는다.
- 데이터 원본과 대용량 결과 파일은 문서 디렉터리에 중복 저장하지 않는다.
- 검증된 사실, 요구사항 초안, 팀 합의가 필요한 항목을 문서 상태로 구분한다.
- 현재 계약 위치는 각 문서에서 명시한다. 공유 계약 migration 완료 후 시스템 경계를
  넘는 기계 판독 계약의 정본은 `contracts/`의 versioned Schema로 관리하며,
  milestone 문서는 결정 배경과 변경 이력으로 유지한다.
