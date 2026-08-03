# Next Session Prompt — Typography, Lifecycle Loader and Dashboard Arrange Mode

아래 내용을 새 ChatGPT 세션에 그대로 붙여넣는다.

---

@devspace.mcp

다음 로컬 프로젝트를 **실제 checkout 모드**로 열어줘.

```text
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2
```

이번 세션의 목표는 기존 Palantir/Foundry형 공통 Shell을 다시 만드는 것이 아니라, 다음 세 가지 사용자 체감 품질을 실제 코드로 완성하는 것이다.

```text
1. 전역 typography 통일과 사용자 조절 가능한 Text size / Density 메뉴
2. Data → Logic → Action 원본 SVG/CSS lifecycle loader
3. Dashboard long-press arrange mode, jiggle micro-animation, drag/resize, favorite persistence
```

가장 먼저 아래 문서를 처음부터 끝까지 읽어라.

```text
docs/40-ui-ux/plans/palantir-typography-loader-dashboard-interaction-plan.md
docs/ui/interaction-polish-reference/README.md
docs/ui/interaction-polish-reference/data-logic-action-orbit-reconstruction.svg
docs/ui/palantir-overhaul/convergence-review.md
docs/ui/palantir-overhaul/scorecard.md
docs/60-development-prompts/next-session-remaining-work-execution-plan.md
```

## 시작 전 필수 안전 절차

현재 checkout에는 다른 작업의 미커밋 변경이 남아 있을 수 있다.

반드시 먼저 다음을 실행하고 결과를 보존해라.

```bash
git status --short --branch
git diff --stat
git log -5 --oneline
```

다음 명령은 절대 사용하지 마라.

```text
git reset --hard
git checkout -- .
git restore .
git clean -fd
미커밋 변경 전체를 stash하거나 덮어쓰는 행위
```

기존 변경의 작성자를 추정해 임의로 되돌리지 말고, 이번 기능과 충돌하는 파일은 현재 diff를 먼저 읽은 뒤 additive하게 수정해라. 최종 커밋에도 관련 없는 기존 변경을 무조건 포함하지 마라.

## 현재 구현에서 우선 확인할 파일

```text
web/src/main.tsx
web/src/ui/foundry/tokens.css
web/src/ui/foundry/convergence.css
web/src/ui/foundry/WorkbenchState.tsx
web/src/ui/foundry/BoardFrame.tsx
web/src/features/auth/AuthShell.tsx
web/src/features/dashboard/DashboardShell.tsx
web/src/features/dashboard/DashboardGridCanvas.tsx
web/src/features/dashboard/DashboardBoardRenderer.tsx
web/src/features/dashboard/ContextPanel.tsx
web/src/features/dashboard/dashboard-runtime.css
web/src/styles.css
web/src/workbench.css
api/ontology_dashboard/dashboard_repository.py
web/e2e/foundry-overhaul.spec.ts
web/e2e/gold-flow.spec.ts
web/e2e/ui-modernization.spec.ts
web/e2e/workbench-final-overhaul.spec.ts
```

실제 checkout에서 파일명이 달라졌다면 검색해서 현재 canonical 구현을 사용해라.

## 구현 순서

### Phase 0 — Baseline

1. 실행 중인 API/Web 서버와 포트를 확인한다.
2. 현재 `/login`과 주 Dashboard를 `1440x1000`, `1728x1117`, `720x500`으로 캡처한다.
3. 주요 selector의 computed font size, line height, control height를 기록한다.
4. 기존 Dashboard preference schema와 `react-grid-layout` 설정을 확인한다.

### Phase 1 — Typography와 Display menu

1. `tokens.css`에 semantic type/line-height/weight token을 만든다.
2. Dashboard에만 있는 binary density state를 전역 Display preference로 확장한다.
3. `Text size: Small / Default / Large / Extra large`와 `Density: Compact / Standard / Comfortable`를 독립적으로 선택하게 한다.
4. top bar 또는 resource navigation footer에 명확한 `Display` 메뉴를 둔다.
5. 로그인 화면과 authenticated Workbench가 동일한 semantic scale을 사용하게 한다.
6. 사용자별 persistence를 구현하고 invalid/old preference migration을 처리한다.

### Phase 2 — Data → Logic → Action loader

1. 다음 자산을 reference로만 사용한다.

```text
docs/ui/interaction-polish-reference/data-logic-action-orbit-reconstruction.svg
```

2. Palantir 로고나 원본 proprietary artwork를 복사하지 말고 Ontology Dashboard 전용 SVG/CSS component를 만든다.
3. `page`, `panel`, `board`, `inline` variant를 제공한다.
4. Data, Logic, Action 단계가 2.4~3초 주기로 자연스럽게 반복되게 한다.
5. `prefers-reduced-motion`, static fallback, `aria-live` operation label을 구현한다.
6. `WorkbenchState`, route lazy fallback, Dashboard/Analysis/Object/Dataset의 의미 있는 loading state에 연결한다.

### Phase 3 — Long-press Dashboard arrange mode

1. 약 500ms long press로 arrange mode에 진입하게 한다.
2. 8px 이상 이동, scroll, interactive child, pointer cancel이면 long press를 취소한다.
3. 기존 `Edit` 버튼과 keyboard/menu command도 동일한 arrange state machine을 사용하게 한다.
4. arrange mode에서 board가 아주 미세하게 staggered jiggle하도록 한다.
5. drag handle로 위치를 이동하고 상하·좌우·대각 resize handle을 제공한다.
6. 현재 board별 min/max constraint, undo/redo, draft recovery, mandatory board 보호를 유지한다.
7. `Escape`와 `Done`으로 종료하고 reduced-motion에서는 jiggle을 끈다.

### Phase 4 — Favorite

1. board header/action menu에 favorite star를 추가한다.
2. favorite는 layout을 자동으로 파괴하거나 재정렬하지 않는 metadata로 취급한다.
3. user/project/workspace/tab scope로 저장하고 reload와 재로그인 후 복원한다.
4. governed/mandatory board의 삭제·권한 규칙은 그대로 유지한다.

### Phase 5 — 검증·문서·Git·서버

1. plan 문서의 unit/E2E 요구사항을 구현한다.
2. 3개 viewport screenshot을 재생성하고 baseline과 직접 비교한다.
3. 기존 기능 회귀가 없는지 전체 release gate를 실행한다.
4. 관련 없는 미커밋 변경을 보존한 상태로 이번 기능을 논리적인 커밋 단위로 구성한다.
5. 커밋을 `main`에 push한다.
6. API `8100`, Web `3100` 기준으로 로컬 서버를 재시작한다.
7. health, login, API docs가 HTTP 200인지 확인한다.

## 구현 원칙

- mock UI를 만들지 말고 현재 실제 runtime과 preference contract를 사용한다.
- 이미 완료된 global shell, Object/Analysis/Dataset/Agent 구조를 반복 구현하지 않는다.
- font size를 selector마다 임의 숫자로 추가하지 말고 semantic token으로 통일한다.
- GIF 파일만 던져 넣는 방식보다 SVG/CSS loader를 우선한다.
- loader가 실제 처리율처럼 보이는 가짜 percentage를 표시하지 않게 한다.
- long press가 chart/table/button의 정상 click을 방해하지 않게 한다.
- arrange mode는 touch, mouse, pen과 keyboard 모두 접근 가능해야 한다.
- Apple 또는 Palantir의 로고, icon, font, proprietary CSS/JS/image를 복사하지 않는다.
- 720px viewport, 200% zoom, light/dark, reduced motion, focus ring을 유지한다.
- backend 변경이 필요하면 기존 contract를 깨지 않는 additive field만 추가하고 실제 UI에서 사용한다.

## 최소 검증

```bash
.venv/bin/python -m pytest -q tests
cd web
npm run test
npm run lint
npm run build
npm run test:e2e
cd ..
.venv/bin/python scripts/check_visual_baselines.py
.venv/bin/python scripts/check_palantir_overhaul_visuals.py
.venv/bin/python scripts/release_gate.py --with-e2e
```

실제 script 옵션이 다르면 repository의 현재 CLI를 확인해 맞는 명령을 사용해라.

## 완료 보고 형식

작업 종료 후 반드시 다음을 정리해라.

```text
1. Typography token과 Display preference 구현 내용
2. Loader component와 적용된 loading state
3. Long-press/arrange/drag/resize/favorite 동작
4. 주요 수정 파일
5. unit, build, Playwright, visual, release gate 결과
6. 접근성·reduced-motion·720px 검증 결과
7. commit SHA와 push 결과
8. 실행 중인 Web/API 주소와 health 상태
9. 남은 실제 제약 또는 후속 작업
```

문서만 만들고 멈추지 말고, 위 완료 조건을 충족할 때까지 실제 구현·브라우저 검증·커밋·푸시·서버 재시작을 수행해라.
