# Operations / Product Documentation

이 폴더는 `oosuhada/agentic-ontology-dashboard`에서 계속 사용하는 현재 Operations/Product
계약의 canonical namespace다. 과거 이관·비교 분석과 원문 보존 자료는
`history/2026-08-week2/`로 분리한다.

## 현재 계약 읽는 순서

1. [현행 Operations 구현 계약 기준선](./current-operations-implementation-baseline.md)
2. [Operations 요구사항 명세](./requirements-specification.md)
3. [Operations 기능 명세](./functional-specification.md)
4. [Operations API 명세](./api-specification.md)
5. [Operations 공통 스키마 정의](./schema-definition.md)
6. [Operations 리포트 명세](./report-specification.md)
7. [Operations 설계 명세](./operations-design-specification.md)
8. [Operations 추적성 매트릭스](./traceability-matrix.md)
9. [Runtime Ownership 통합 기준](./runtime-ownership-integration.md)
10. [Generator Feature/Label 계약](./generator-feature-label-contract.md)
11. [Model Artifact Publish 계약](./model-artifact-publish-contract.md)
12. [Canonical V3.1 필드 검증표](./v3.1-field-validation.md)
13. [Canonical V3.1 위험 상승 탐지 기준](./preventive-risk-rise-analysis.md)
14. [예방조치 What-if 개발 계획](./preventive-what-if-development-plan.md)
15. [Asset Detail / Overview UI 의사결정 로그](./asset-detail-overview-ui-decision-log.md)

Closed-loop 상태 머신의 canonical source는 [`../closed-loop-domain-contract.md`](../closed-loop-domain-contract.md),
Product/API/UI의 역할·Action·소비 규칙은
[`../closed-loop-product-consumption-contract.md`](../closed-loop-product-consumption-contract.md)를 따른다.
정비 완료 이후 대상 설비 Overlay와 정비 후 Runtime Prediction handoff는
[`../closed-loop-runtime-overlay-contract.md`](../closed-loop-runtime-overlay-contract.md)를 따른다.

## Current vs history

`docs/operations/` 바로 아래 문서는 현재 구현·제품 계약 또는 현재 개발 계획이다. 파일명에 특정
주차를 넣지 않으며, 후속 PR은 이 경로를 기준으로 참조한다.

[`history/2026-08-week2/`](./history/2026-08-week2/)에는 현재 계약의 배경을 확인할 때만
사용하는 과거 스키마·API·화면 자료를 보존한다.

history 문서의 당시 `Week 2` 표현과 의사결정 문맥은 provenance이므로 유지한다. 다만
현재 계약을 참조해야 하는 링크는 `docs/operations/`의 canonical 경로를 가리킨다.

## 기준 자료

- Dataset: `canonical-ai4i-physics-v3.1`
- Model: `independent-logreg-v3.1`
- Result Artifact: `result-artifact-v1.0`
- 제품 문서 저장소: `oosuhada/agentic-ontology-dashboard`

## 관리 원칙

- 검증된 사실, 현재 계약, 제안/Target을 문서 안에서 구분한다.
- 공통 필드명의 현재 단일 기준은 [`schema-definition.md`](./schema-definition.md)다.
- Canonical ZIP과 대용량 CSV/JSONL, credential, cache, 가상환경은 문서 namespace에 복사하지 않는다.
- evaluation truth는 일반 제품 화면/API 계약으로 노출하지 않는다.
- 문서 이동 시 `docs/operations/` current 경로와 history 경로를 구분해 자동리뷰 context가 과거 기록을
  현재 계약처럼 소비하지 않게 한다.
