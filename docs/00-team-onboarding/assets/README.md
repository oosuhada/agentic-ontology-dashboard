# Team onboarding assets

이 폴더는 팀 공유 문서에서 사용하는 검증된 화면 캡처만 보관한다.

- `screenshots/00-team-share-story.png`: `/team-share` 전체 HTML Story 캡처
- `screenshots/01-15`: 실제 사용자 흐름과 Workbench별 1440×1000 검증 캡처

- 캡처 생성: `cd web && CAPTURE_TEAM_SHARE=1 npx playwright test e2e/team-share-captures.spec.ts`
- Story 캡처 생성: `cd web && npm run capture:team-share-story`
- 최신 AI4I 2020 V3.1·Adaptive Modeling·다크모드 캡처: `cd web && npm run capture:team-share-adaptive`
- 최신 Story 데스크톱·모바일: `cd web && npm run capture:team-share-adaptive-story`
- 최신 화면 설명 문서: [`../10-adaptive-modeling-release-tour.md`](../10-adaptive-modeling-release-tour.md)
- AI4I 2020 V3.1 + Adaptive Modeling 전체 캡처와 Story 생성: `cd web && npm run capture:team-share-adaptive`
- 화면 크기: 1440 × 1000, light theme
- 기존 11장: Playwright 격리 SQLite 데이터베이스와 demo seed
- 최신 6장: 로컬 PostgreSQL의 실제 V3.1 Dataset Version·Result Artifact·replay와 현재 ML Validator blocked 상태
- 비밀번호나 실제 개인정보는 캡처하지 않는다.
- Admin 캡처는 shell/sidebar의 계산된 레이아웃을 측정한다.
- Adaptive Dashboard 캡처는 8개 Board와 비동기 상태 종료를 확인한다.
- ECharts 캡처는 `finished` 이벤트와 실제 Canvas 픽셀을 확인한다.

이미지는 직접 수정하지 않고 캡처 시나리오를 다시 실행해 갱신한다.

Story 자산:

- `00-team-share-story.png`: 데스크톱 전체 페이지
- `00-team-share-story-mobile.png`: 390×844 모바일 전체 페이지

## 최신 전체 프로젝트 Story

- 기존 `/team-share`와 기존 캡처는 변경하지 않는다.
- 최신 인터랙티브 경로: `/team-share-adaptive`
- 최신 독립 HTML: `/team-share-adaptive.html`
- 최신 자산 폴더: `web/public/team-share-adaptive-assets/`
- 최신 Story는 기존 기능 11장과 AI4I 2020 V3.1·Adaptive Modeling·다크모드 기능 6장을 합친 완결형 프로젝트 투어다.
- `06-dashboard-dark-mode.png`: runtime·server-filtered scope·Planner Assistant의 실제 dark surface와 대비 검증 화면
- 최신 검증 태그: `team-share-adaptive-v3.1-postgresql-20260805`
- 캡처는 loader, skeleton, refreshing, `aria-busy=true`, 미완성 image/font 상태가 모두 사라진 뒤 생성한다.
- 최신 runtime 캡처는 `dsv-9fc144c7-d3f8-5b37-8465-04248165b7ce`와 replay context가
  표시되고 API·ECharts가 완료된 뒤 생성한다. 이미지를 직접 편집하지 않는다.
