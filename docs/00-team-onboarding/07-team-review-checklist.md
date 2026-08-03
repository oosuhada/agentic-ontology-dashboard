# 팀 리뷰 체크리스트

이 저장소를 공유할 때 “전체적으로 어때요?”라고 질문하지 않는다. 아래 결정 항목을 순서대로 검토한다.

## 1. 제품 흐름

- [ ] Dataset → Ontology → Analysis → Report/Dashboard → Action 흐름을 채택한다.
- [ ] 임원·매니저의 메인 산출물을 Report로 정의한다.
- [ ] 실무자의 메인 작업 공간을 Dashboard로 정의한다.
- [ ] 실무자가 공용 Report를 작성하고 관리자가 읽는 흐름을 채택한다.

## 2. 초기 역할 범위

- [ ] 초기 MVP에서 실제로 데모할 역할을 정한다.
- [ ] 역할별 읽기·수정·승인 권한을 확정한다.
- [ ] 조직 관리자와 FDE의 경계를 확정한다.

권장 초기 데모 범위:

```text
조직 관리자
운영 매니저
도메인 엔지니어
FDE
```

나머지 역할은 Template과 권한 검증 후 확장한다.

## 3. Dataset 전략

- [ ] 첫 발표에 사용할 Dataset을 확정한다.
- [ ] 각 Dataset의 schema와 Ontology mapping 책임자를 정한다.
- [ ] 자동 UI Composition에 사용할 semantic rule을 검토한다.
- [ ] Factory/Fleet/Compressor 중 실제 팀 주제와 맞지 않는 demo를 제거할지 결정한다.

## 4. 기술 채택 범위

- [ ] 현재 React/FastAPI 구조를 기준으로 이어갈지 결정한다.
- [ ] SQLite demo와 운영 PostgreSQL 경계를 확정한다.
- [ ] Project 3 Graph·RAG 연결 범위를 확정한다.
- [ ] 외부 LLM 사용 여부와 자격증명 관리 방식을 정한다.

## 5. 프로토타입에서 후속으로 미룰 기능

- [ ] Forecast authoritative engine
- [ ] 정식 보고서 승인·반려 workflow
- [ ] 이메일·Slack 알림
- [ ] 실시간 공동 Dashboard 편집
- [ ] 실제 설비·작업 시스템 Action 연동

## 6. 코드 공유 방식

권장 방식:

```text
main
└── 팀이 합의한 안정 기준

prototype/ontology-dashboard-prebuild
└── 현재 전체 선행 프로토타입
```

Draft PR 제목 예시:

```text
[RFC / Prototype] Ontology Dashboard prebuild and team adoption review
```

PR에는 다음을 명시한다.

- 즉시 병합 목적이 아님
- 팀 논의 비용을 줄이기 위한 선행 구현
- 채택할 기능을 선택해야 함
- 운영 인프라와 외부 자격증명은 별도 범위

## 리뷰 종료 조건

- [ ] 초기 사용자 시나리오 2~3개 확정
- [ ] 초기 역할 확정
- [ ] 초기 Dataset 확정
- [ ] 유지할 Workbench 확정
- [ ] 제거하거나 후속으로 미룰 기능 확정
- [ ] 팀별 코드 Ownership 확정
- [ ] 정식 개발 브랜치 전략 확정

