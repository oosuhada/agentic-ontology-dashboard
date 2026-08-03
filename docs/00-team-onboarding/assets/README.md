# Team onboarding assets

이 폴더는 팀 공유 문서에서 사용하는 검증된 화면 캡처만 보관한다.

- 캡처 생성: `cd web && CAPTURE_TEAM_SHARE=1 npx playwright test e2e/team-share-captures.spec.ts`
- 화면 크기: 1440 × 1000, light theme
- 데이터: Playwright 격리 SQLite 데이터베이스와 demo seed
- 비밀번호나 실제 개인정보는 캡처하지 않는다.

이미지는 직접 수정하지 않고 캡처 시나리오를 다시 실행해 갱신한다.
