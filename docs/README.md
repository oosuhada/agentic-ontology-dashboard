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
├── 10-product/               문제, 사용자, 역할, Dataset과 정책
├── 20-architecture/          시스템 구조, 계약, ADR와 current state
├── 30-implementation/        현재 상태, 로드맵, stage-history
├── 40-ui-ux/                 구현 설명, 계획, Reference
├── 50-operations/            실행, 검증, 릴리스, 문제 해결
├── 60-development-prompts/   다음 세션 실행 프롬프트
├── 90-archive/               과거 비교 분석과 superseded 계획
└── ui/                       대용량 화면 캡처·레퍼런스 자산
```

## 물리 경로 정책

기존 루트 Markdown과 루트 수준의 ADR·current-state 디렉터리는 목적별 폴더로 물리 이동했다. 저장소 전체 Markdown 링크와 스크립트의 명시적 문서 경로도 새 위치로 변경했다.

새 문서는 다음 규칙을 따른다.

1. 팀 공유 문서는 `00-team-onboarding/`에 둔다.
2. 제품·아키텍처·구현·UI·운영 문서는 해당 번호 폴더에 둔다.
3. `docs/` 루트에는 새 Markdown 파일을 추가하지 않는다.
4. 자동 생성 화면은 `00-team-onboarding/assets/screenshots/` 또는 `ui/`에 둔다.
5. 과거 분석 문서를 수정해 현재 상태처럼 보이게 하지 않고, 최신 상태 문서에서 명시적으로 연결한다.

문서 구조 검증:

```bash
python3 scripts/check_docs_structure.py
```

필수 실제 경로와 폐기된 과거 경로는 [`document-registry.json`](./document-registry.json)에 등록한다. `README.md` 외 루트 Markdown, 과거 경로의 재생성 또는 깨진 로컬 링크는 검증 실패로 처리한다.

## 현재 기준 버전

- Tag: `docs-physical-reorg-ready-20260804`
- 제품 기능 기준: `complete-user-flow-20260803`
- 팀 공유 패키지 재검증: 2026-08-04
- 상세 결과: [`00-team-onboarding/09-verification-report.md`](./00-team-onboarding/09-verification-report.md)

