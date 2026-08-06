# Mentoring MVP Definition · 2026-08

2026년 8월 멘토링 결과를 반영해 Ontology Dashboard의 발표·구현 우선순위를 다시 고정한 문서 묶음이다.

## 기준 문서

- [MVP 범위 및 4개 화면 명세서](./mvp-scope-and-screen-specification.md)
- [MVP API 명세서](./mvp-api-specification.md)
- [MVP 데이터 계약서](./mvp-data-contract.md)
- [Week 2 역할 분담 및 산출물 정의](./week2-team-role-and-deliverables.md)

## 문서 사용 순서

1. 범위 및 화면 명세서에서 사용자·화면·제외 범위를 확인한다.
2. API 명세서에서 화면별 호출, 권한, 요청·응답과 구현 gap을 확인한다.
3. 데이터 계약서에서 Canonical V3.1 필드 의미, enum, lineage와 화면 간 일관성 규칙을 확인한다.
4. Week 2 역할 분담 문서에서 담당자별 구현 범위, 협업 관계, 산출물과 완료 기준을 확인한다.

## 이번 범위의 핵심

```text
Canonical V3.1
→ V2 Blueprint Overview
→ V2 Blueprint Objects
→ V2 Blueprint Operations
→ V1 Executive Report View
```

- MVP 핵심 사용자는 `생산 관리자`와 `현장 담당자` 두 그룹으로 제한한다.
- V2의 `Analysis`는 MVP에서 제외한다.
- 기존 V3·V4 상용화 화면과 플랫폼 확장 기능은 이번 MVP 완료 조건에 포함하지 않는다.
- 모델 임계값은 업종별 정답을 고정하지 않고, 미탐·오탐 비용 가정에 따른 권장 범위를 제안하는 수준으로 다룬다.

## 기존 문서와의 관계

기존 [`../mvp-scope.md`](../mvp-scope.md)는 전체 제품 방향과 과거 수직 흐름을 설명하는 참고 문서로 유지한다. 실제 1·2주차 요구사항 정의와 MVP 화면 구현 범위는 이 폴더의 명세서를 우선 기준으로 사용한다.

