# 팀 공유 메시지와 진행 방식

## 팀 채팅에 보낼 메시지

```text
프로젝트를 본격적으로 시작하기 전에 요구사항과 사용자 흐름의 해석 차이를 줄이기 위해, 실제로 동작하는 Ontology Dashboard 선행 프로토타입을 만들어봤습니다.

이 저장소는 화면 디자인만 만든 것이 아니라 아래 전체 흐름을 구현한 상태입니다.

- 구성원이 희망 역할을 선택해 가입 요청
- 관리자가 알림을 받고 역할·Workspace·개별 권한을 확인해 승인
- 운영 매니저·임원은 Reports, 엔지니어·실무자는 Dashboard로 진입
- 실무자가 텍스트 보고서를 수정하고 매니저가 같은 수정본과 근거 시각화를 검토
- 보고서에서 상세 Dashboard로 drill-down
- Dataset schema에 따라 Factory, Fleet, Compressor 화면의 Board 종류와 배치가 변경
- 같은 역할이어도 사용자 ID별 Dashboard·Filter·Display 설정을 저장하고 재로그인 시 복원
- Analysis Path/Canvas/Graph와 Ontology ObjectSet 탐색

전체를 그대로 채택하자는 의미는 아니고, 구현된 결과를 기준으로 초기 MVP 범위와 역할별 경험, Dataset 전략을 함께 결정하기 위한 RFC 성격의 저장소입니다.

먼저 아래 문서만 확인해 주세요.

1. docs/00-team-onboarding/README.md
2. docs/00-team-onboarding/02-feature-tour.md
3. docs/00-team-onboarding/04-demo-guide.md
4. docs/00-team-onboarding/06-implementation-status.md

리뷰에서는 코드 스타일보다 먼저 다음을 결정하면 좋겠습니다.

1. 역할별 Report/Dashboard 흐름을 채택할지
2. 초기 MVP 역할을 어디까지 포함할지
3. 첫 Dataset과 Ontology mapping을 무엇으로 확정할지
4. 현재 Workbench 중 무엇을 유지하고 무엇을 후속으로 미룰지
```

## 15분 공유 미팅 구성

```text
0–2분   프로젝트 문제와 세 가지 핵심 차별점
2–5분   가입 → 관리자 승인 → 역할별 첫 화면
5–8분   엔지니어 보고서 작성 → 매니저 검토 → Dashboard drill-down
8–11분  Factory/Fleet/Compressor 적응형 화면 비교
11–13분 개인화 저장, Analysis, Ontology
13–15분 팀 결정 항목과 담당자 확정
```

## Draft PR 본문 첫 문단

```text
이 PR은 즉시 main에 병합하기 위한 완성 기능 PR이 아니라, 프로젝트 시작 전 제품 흐름과 구현 범위를 구체적으로 검토하기 위한 선행 프로토타입입니다. UI뿐 아니라 인증·권한·보고서·적응형 Dashboard·사용자 preference·Analysis·Ontology 흐름을 연결했으며, 팀 합의 후 채택할 기능만 정식 개발 범위로 정리합니다.
```

## 공유 단위

권장 순서:

1. 화면 투어 문서
2. 로컬 15분 데모
3. 구현 상태 Matrix
4. Repository map
5. Draft PR diff

코드 diff부터 공유하면 제품 흐름보다 파일 수와 구현량에 논의가 집중될 수 있으므로 마지막에 연다.

## 팀에 요청할 피드백 형식

각 팀원은 아래 형식으로 남긴다.

```text
채택해야 하는 기능:
후속으로 미룰 기능:
제거해야 하는 기능:
초기 MVP 역할:
첫 Dataset:
담당하고 싶은 영역:
가장 큰 기술 리스크:
```

