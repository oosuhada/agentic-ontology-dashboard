# Next Session Prompt — Color System and Chart Intelligence UI/UX

아래 내용을 다음 ChatGPT 세션에 그대로 붙여넣는다.

---

```text
@devspace-codex

다음 로컬 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

가장 먼저 다음 문서를 처음부터 끝까지 읽어줘.

docs/40-ui-ux/plans/chart-intelligence-color-system-uiux-plan.md

이어서 현재 source를 직접 확인해 문서의 Current-state 판정과 실제 구현이 달라진 부분이 있는지 비교해줘.

우선 확인할 파일:

web/src/ui/foundry/tokens.css
web/src/ui/foundry/ChartPanel.tsx
web/src/ui/foundry/BoardFrame.tsx
web/src/features/dashboard/types.ts
web/src/features/dashboard/CatalogDataBoard.tsx
web/src/features/dashboard/AnalysisReferenceBoard.tsx
web/src/features/dashboard/renderers/EChartsRenderer.tsx
web/src/features/dashboard/BoardInspector.tsx
web/src/features/dashboard/DashboardBoardRenderer.tsx
web/src/features/manufacturing/ManufacturingApp.tsx
web/src/features/manufacturing/useDashboardEditor.ts
api/ontology_dashboard/dashboard_models.py
api/ontology_dashboard/dashboard_service.py
api/ontology_dashboard/analysis_service.py
api/ontology_dashboard/planner/models.py
api/ontology_dashboard/planner/service.py

현재 checkout에 다른 세션의 미커밋 변경이 있을 수 있으므로 가장 먼저 다음을 확인해.

git status --short --branch
git diff --stat
git log -5 --oneline

기존 변경은 reset, restore, checkout, clean, 전체 stash하지 말고 보존해. 충돌하는 파일은 현재 diff를 먼저 읽고 additive하게 수정해.

이번 세션은 release gate나 광범위한 검증이 아니라 UI/UX 구현에 집중해.

다음은 실행하지 마.

- scripts/release_gate.py
- 전체 backend pytest
- npm run test:e2e 전체
- 기존 48장 visual baseline 전체 재생성
- CI threshold 조정
- 장시간 pixel-diff 조사

필요한 검증은 TypeScript, production build, 이번 기능 전용 짧은 browser smoke만 사용해. UI 구현이 완료되기 전에 테스트 반복으로 시간을 소비하지 마.

이번 세션의 최우선 목표는 다음과 같아.

1. 사용자 제공 palette를 canonical global token과 chart palette에 적용
2. 기존 ECharts hardcoded color 제거
3. typed visualization registry 구현
4. chart pool을 최소 metric, table, bar, stacked bar, line, area, pie/donut, histogram, scatter, heatmap으로 확장
5. 데이터 field profile과 deterministic chart recommendation 구현
6. chart-capable Board header에 `Auto · Line` 형태의 `Visualize as` switcher 구현
7. recommended, alternatives, unavailable chart와 이유를 menu에 표시
8. 같은 query rows와 cross-filter 상태를 유지하면서 chart만 즉시 전환
9. Board Inspector에 Visualization section 추가
10. manual override와 `Reset to Auto` 구현
11. `board.settings.visualization`에 user override를 저장하고 기존 Dashboard preference, undo/redo, draft recovery, reload, 재로그인 복원을 재사용
12. 기존 Planner에 typed visualization recommendation을 추가하되 LLM은 registry에 존재하고 실제 field가 있는 후보만 선택하도록 제한

반드시 사용할 palette:

Brand and accent
- Navy primary: #0C1C74
- Slate ink: #3A4950
- Orange accent: #E64D2B
- Red reserved: #DB0714

Semantic
- Info/action: #0C1C74
- Success: #29A634
- Warning: #D1970C
- Danger: #DB0714

Categorical chart series
- #0C1C74
- #E64D2B
- #00A396
- #D1970C
- #7861DB
- #29A634
- #DA2D6F
- #5F6B7B

Neutral
- #FFFFFF
- #F7F8F9
- #DCDCDD
- #5F6B7B
- #3A4950

Red는 delete, deny, failed, critical 외 용도로 사용하지 마. Orange accent와 semantic warning을 같은 의미로 혼용하지 마. category color는 stable mapping으로 유지해.

현재 구현은 chart renderer foundation과 server render_spec은 있지만, AI가 chart 종류를 추천하거나 사용자가 Board header에서 같은 데이터를 다른 chart로 전환하는 UX는 아직 없다는 전제에서 시작해. 기존 Planner의 Board recommendation을 chart recommendation이 완성된 것으로 오해하지 마.

구현 순서:

Phase 0
- palette token과 chartPalette helper
- current hardcoded color migration

Phase 1
- visualization registry
- generic renderer chart pool 확장

Phase 2
- field profile
- deterministic recommendation과 alternatives

Phase 3
- Board header Visualize as switcher
- Auto/Manual 상태와 rationale

Phase 4
- Visualization Inspector
- persistence, undo/redo, draft recovery

Phase 5
- existing Planner의 typed AI chart recommendation
- deterministic fallback

Phase 6
- 1440x1000과 720x500 UI polish

문서만 작성하고 멈추지 말고 실제 코드와 브라우저 UI를 구현해. 첫 세션에 전체 Phase를 무리하게 끝내기 어렵다면 Phase 0~4를 사용자에게 실제 보이는 완료 상태까지 우선 구현하고, Phase 5 AI integration은 typed interface와 fallback까지 진행해.

다음 contract는 회귀시키지 마.

- server-first cross-filter
- click/brush selection
- Board Inspector selection
- Dashboard layout drag/resize
- favorite persistence
- saved view/share/export
- undo/redo와 draft recovery
- mandatory board 보호
- role와 permission boundary
- AnalysisReference version policy
- 720px document overflow 방지
- reduced motion

작업 완료 후 다음을 보고해.

1. 현재 구현 판정과 실제 gap
2. 적용한 palette token과 주요 화면
3. 구현한 chart pool
4. Auto recommendation 규칙과 alternatives
5. Board header switcher와 Inspector UX
6. persistence와 reload/재로그인 결과
7. AI recommendation과 deterministic fallback
8. 주요 변경 파일
9. 실행한 최소 검증과 실제 브라우저 확인 결과
10. 남은 UIUX 작업

Git commit/push와 서버 재시작은 내가 별도로 요청할 때만 수행해.
```

