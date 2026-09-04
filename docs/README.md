# 프로젝트 문서

이 디렉터리는 `oosuhada/agentic-ontology-dashboard`의 제품 방향, 아키텍처,
데이터·API 계약, 운영 절차와 검증 기록을 관리합니다.

## 정본 문서

- [제품 방향](./product-direction.md): 문제 정의, 역할별 UX, 제품 원칙과 roadmap
- [시스템 아키텍처](./architecture.md): 현재 시스템 경계와 데이터 흐름
- [프로젝트 보고서](./submission-report.md): 구현 결과와 제품 가치
- [개인 발표·제품 데모 흐름](./presentation-demo-flow.md): 한 명이 진행하는 시연 순서와 fallback
- [Operations 문서](./operations/README.md): 요구사항, API, schema와 runtime 계약
- [Architecture Decision Records](./architecture-decisions/README.md): 주요 기술 결정
- [Shared Contracts](../contracts/README.md): 시스템 간 기계 판독 계약

문서가 충돌할 때는 다음 순서를 따릅니다.

1. 실행 코드와 versioned contract
2. `product-direction.md`
3. `architecture.md`와 Architecture Decision Record
4. Operations의 현재 명세
5. 과거 계획과 history 문서

## Closed-loop

- [Domain Contract](./closed-loop-domain-contract.md)
- [Product/API/UI Consumption Contract](./closed-loop-product-consumption-contract.md)
- [Runtime Overlay Contract](./closed-loop-runtime-overlay-contract.md)

## Operations

- [요구사항](./operations/requirements-specification.md)
- [기능 명세](./operations/functional-specification.md)
- [API 명세](./operations/api-specification.md)
- [Schema](./operations/schema-definition.md)
- [Report 명세](./operations/report-specification.md)
- [Generator Feature/Label 계약](./operations/generator-feature-label-contract.md)
- [Model Artifact Publish 계약](./operations/model-artifact-publish-contract.md)
- [Runtime Ownership](./operations/runtime-ownership-integration.md)
- [Traceability Matrix](./operations/traceability-matrix.md)
- [Mac mini Production](./operations/macmini-production.md)

## 관리 원칙

- 개인 이름이나 과거 담당자 구분을 현재 제품 계약으로 사용하지 않습니다.
- 기능 책임은 사람 대신 `source`, `generator`, `backend`, `frontend`, `report` 경계로 기록합니다.
- 업무 사용자 역할인 엔지니어·운영 관리자·경영진·정비 담당자는 제품 도메인으로 유지합니다.
- 대용량 데이터, runtime DB, cache와 생성 결과는 문서 디렉터리에 중복 저장하지 않습니다.
- 사실, 추정, fixture와 향후 계획을 명확히 구분합니다.
- 시스템 경계를 넘는 계약의 정본은 `contracts/`의 versioned schema입니다.
- 오래된 계획은 현재 아키텍처를 덮어쓰지 않습니다.
