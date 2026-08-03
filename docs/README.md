# Documentation home

`docs/`의 공식 진입점이다. 팀 공유, 제품 정의, 아키텍처, 구현 이력, UI 레퍼런스와 운영 문서를 목적별로 찾을 수 있도록 분류한다.

## 가장 먼저 읽을 문서

| 대상 | 시작 문서 | 읽는 시간 |
|---|---|---:|
| 처음 참여하는 팀원 | [`00-team-onboarding/README.md`](./00-team-onboarding/README.md) | 5분 |
| 제품·기획 담당 | [`10-product/README.md`](./10-product/README.md) | 10분 |
| 백엔드·아키텍처 담당 | [`20-architecture/README.md`](./20-architecture/README.md) | 15분 |
| 프론트엔드·UI 담당 | [`40-ui-ux/README.md`](./40-ui-ux/README.md) | 15분 |
| 실행·검증 담당 | [`50-operations/README.md`](./50-operations/README.md) | 10분 |
| 다음 개발 세션 담당 | [`60-development-prompts/README.md`](./60-development-prompts/README.md) | 작업별 상이 |

## 문서 구조

```text
docs/
├── 00-team-onboarding/       팀 공유용 시작점, 화면 투어, 데모, 상태표
├── 10-product/               문제, 사용자, 역할, 데이터 전략 인덱스
├── 20-architecture/          시스템 구조, 계약, ADR 인덱스
├── 30-implementation/        현재 상태, 로드맵, 구현 이력 인덱스
├── 40-ui-ux/                 Foundry UI, 시각 언어, 화면 자산 인덱스
├── 50-operations/            실행, 검증, 릴리스, 문제 해결 인덱스
├── 60-development-prompts/   다음 세션 실행 프롬프트 인덱스
├── 90-archive/               과거 비교 분석과 참고 문서 인덱스
├── adr/                      Architecture Decision Records
├── architecture/             기존 아키텍처 상세 문서
└── ui/                       대용량 화면 캡처·레퍼런스 자산 저장소
```

## 경로 유지 정책

기존 문서 다수는 다른 문서와 자동화에서 `docs/<filename>.md` 형태로 참조한다. 팀 공유 직전의 대규모 이동으로 링크가 깨지는 것을 방지하기 위해 기존 문서 경로는 유지하고, 목적별 폴더의 `README.md`가 이를 분류한다.

새 문서는 다음 규칙을 따른다.

1. 팀 공유 문서는 `00-team-onboarding/`에 둔다.
2. 제품·아키텍처·구현·UI·운영 문서는 해당 번호 폴더에 둔다.
3. `docs/` 루트에는 새 Markdown 파일을 추가하지 않는다.
4. 자동 생성 화면은 `00-team-onboarding/assets/screenshots/` 또는 `ui/`에 둔다.
5. 과거 분석 문서를 수정해 현재 상태처럼 보이게 하지 않고, 최신 상태 문서에서 명시적으로 연결한다.

## 현재 기준 버전

- Commit: `064fb49 feat(core): complete governed onboarding and adaptive user flow`
- Tag: `complete-user-flow-20260803`
- 팀 공유 패키지 생성 기준: 2026-08-03

