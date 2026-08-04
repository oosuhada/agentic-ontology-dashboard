# Team onboarding assets

이 폴더는 팀 공유 문서에서 사용하는 검증된 화면 캡처만 보관한다.

- `screenshots/00-team-share-story.png`: `/team-share` 전체 HTML Story 캡처
- `screenshots/01-15`: 실제 사용자 흐름과 Workbench별 1440×1000 검증 캡처

- 캡처 생성: `cd web && CAPTURE_TEAM_SHARE=1 npx playwright test e2e/team-share-captures.spec.ts`
- Story 캡처 생성: `cd web && npm run capture:team-share-story`
- 화면 크기: 1440 × 1000, light theme
- 데이터: Playwright 격리 SQLite 데이터베이스와 demo seed
- 비밀번호나 실제 개인정보는 캡처하지 않는다.
- Admin 캡처는 shell/sidebar의 계산된 레이아웃을 측정한다.
- Adaptive Dashboard 캡처는 8개 Board와 비동기 상태 종료를 확인한다.
- ECharts 캡처는 `finished` 이벤트와 실제 Canvas 픽셀을 확인한다.

이미지는 직접 수정하지 않고 캡처 시나리오를 다시 실행해 갱신한다.

Story 자산:

- `00-team-share-story.png`: 데스크톱 전체 페이지
- `00-team-share-story-mobile.png`: 390×844 모바일 전체 페이지
