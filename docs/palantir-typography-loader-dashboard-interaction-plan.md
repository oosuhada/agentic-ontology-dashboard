# Palantir-style Typography, Lifecycle Loader and Dashboard Arrange Mode Plan

Created: 2026-08-03

## 1. Goal

The global shell and Workbench information architecture are already substantially closer to a Foundry-style product. The next pass must improve the remaining interaction and visual-system gaps:

1. unify typography and allow users to control readable UI scale;
2. replace generic spinners with an original `Data → Logic → Action` lifecycle loader;
3. add an iPhone-home-screen-inspired Dashboard arrange mode entered by long press;
4. support board movement, bidirectional resizing and favorites with persistence;
5. preserve existing data contracts, role permissions, cross-filter behavior and release gates.

This is a focused frontend interaction pass. It must not reopen the already completed global shell redesign, namespace relocation, Analysis lifecycle, Dataset materialization, Project 3 boundary or unrelated infrastructure work.

## 2. Current checkout warning

At the time this plan was written, the working tree contained unrelated in-progress changes across backend seed/catalog code, local server scripts, Dashboard runtime files, visual artifacts and E2E configuration.

The next session must:

- inspect `git status --short --branch` before editing;
- preserve every existing modification;
- never run destructive `git reset`, `git checkout -- .`, `git clean`, or blanket restore commands;
- separate this feature's files from unrelated changes when committing;
- verify whether another session completed or superseded any listed item before implementation.

## 3. Reference assets

Read first:

```text
docs/ui/interaction-polish-reference/README.md
docs/ui/interaction-polish-reference/data-logic-action-orbit-reconstruction.svg
docs/ui/palantir-overhaul/final/1440x1000/dashboard.png
```

The user-provided source attachment IDs and visual observations are recorded in the reference README.

## 4. Typography system

### 4.1 Problem

The current application uses multiple historical CSS layers. Small labels, board metadata, table cells, toolbars, headings and helper copy do not consistently map to one semantic type system. A binary `compact`/`comfortable` Dashboard-only density toggle exists, but it does not provide a clear global font-size preference.

### 4.2 Required design tokens

Create one semantic scale in `web/src/ui/foundry/tokens.css` and remove direct pixel sizes from the touched surfaces.

Recommended token model:

```text
--od-font-scale: 1
--od-type-2xs: calc(0.625rem * var(--od-font-scale))
--od-type-xs:  calc(0.6875rem * var(--od-font-scale))
--od-type-sm:  calc(0.75rem * var(--od-font-scale))
--od-type-md:  calc(0.8125rem * var(--od-font-scale))
--od-type-lg:  calc(0.9375rem * var(--od-font-scale))
--od-type-xl:  calc(1.125rem * var(--od-font-scale))
--od-type-2xl: calc(1.375rem * var(--od-font-scale))
```

The implementation may adjust exact values after screenshot review, but it must preserve a small, explicit semantic set.

Define matching line-height and weight tokens:

```text
--od-leading-tight
--od-leading-control
--od-leading-body
--od-weight-regular
--od-weight-medium
--od-weight-semibold
```

### 4.3 Display preferences menu

Add a visible `Display` or `보기 설정` control to the global top bar or resource navigation footer.

It must contain two independent settings:

```text
Text size: Small / Default / Large / Extra large
Density: Compact / Standard / Comfortable
```

Recommended scale values:

```text
Small       0.90
Default     1.00
Large       1.10
Extra large 1.20
```

Requirements:

- live preview without reload;
- reset-to-default action;
- persistent per authenticated user;
- unauthenticated fallback persisted locally for login/register screens;
- no document-level horizontal overflow at 720×500;
- usable at browser 200% zoom;
- table rows and controls may increase with density, but font scale and density must remain separate settings;
- avoid text smaller than the final approved minimum except truly auxiliary metadata.

Prefer extending the existing dashboard/user preference contract additively. If backend persistence is not necessary for the first slice, use a versioned local storage key and document the migration path.

### 4.4 Surfaces to normalize

At minimum:

- global top bar and resource navigation;
- Dashboard tabs, context panel, board header, runtime metadata and table cells;
- Analysis nodes and inspector;
- Object Explorer table and inspector;
- Dataset and Governance tables;
- Auth and Admin;
- loading, empty, error and degraded states.

## 5. `Data → Logic → Action` lifecycle loader

### 5.1 Component

Create a reusable component such as:

```text
web/src/ui/foundry/OntologyLifecycleLoader.tsx
web/src/ui/foundry/ontology-lifecycle-loader.css
```

Variants:

```text
page    full route or authentication transition
panel   Workbench pane loading
board   individual Dashboard board loading
inline  compact async action
```

### 5.2 Motion sequence

Use the local reconstruction as the visual starting point.

One loop should progress through:

```text
Data   → source nodes appear and blue glow activates
Logic  → transformation nodes join and violet glow activates
Action → governed action nodes join and neutral/green glow activates
```

Recommended timing:

```text
total loop 2.4–3.0 seconds
phase overlap 120–200 ms
orbit rotation very slow and continuous
node scale/opacity transition 160–240 ms
```

Do not show a fake numeric percentage. Display a truthful operation label passed by the caller, for example `Loading governed objects` or `Materializing dataset version`.

### 5.3 Technical requirements

- Prefer inline SVG plus CSS animation over a large GIF.
- Optional animated WebP/GIF export may be produced only as a fallback or documentation artifact.
- No Palantir logo, copied proprietary illustration or proprietary font.
- Respect `prefers-reduced-motion`; reduced motion shows a static three-stage composition or simple opacity change.
- Expose an accessible name and `aria-live="polite"` operation text.
- Avoid layout shift by reserving stable dimensions.
- Replace generic spinners only where the lifecycle metaphor is appropriate; keep tiny button progress indicators lightweight.

### 5.4 Integration targets

- route lazy fallback;
- `WorkbenchState` loading state;
- Dashboard initial hydration;
- board-level query loading;
- Analysis execution/materialization;
- Object graph loading;
- Dataset/Governance record loading;
- authentication transition, without delaying successful navigation.

## 6. Dashboard long-press arrange mode

### 6.1 Entry and exit

Enter arrange mode through either:

- long press on an eligible board or empty canvas area for approximately 500 ms; or
- the existing explicit `Edit` action; or
- an accessible keyboard/menu command.

Pointer behavior:

- cancel the long press when movement exceeds 8 px;
- cancel on scroll, pointer cancel, context menu or interactive child activation;
- do not trigger from buttons, inputs, table rows, chart controls, links or resize handles;
- support mouse, pen and touch pointer types.

Exit through:

- `Done`/`완료`;
- `Escape`;
- optional outside-canvas action when no unsaved changes exist.

### 6.2 Arrange-mode micro-animation

When arrange mode is active, eligible boards should use a subtle staggered jiggle similar to a mobile home-screen arrangement state:

```text
rotation approximately -0.45° to +0.45°
vertical translation no more than 1 px
duration approximately 140–190 ms
per-board stagger to avoid synchronized movement
```

Rules:

- stop or reduce the jiggle for the board currently being dragged/resized;
- disable it under `prefers-reduced-motion`;
- never compromise text clarity or cause document overflow;
- use the Ontology Dashboard visual language, not copied Apple assets.

### 6.3 Move and resize

The existing `react-grid-layout` runtime should remain the source of truth.

Required behavior:

- entire board moves from a clear drag handle in arrange mode;
- resize handles support horizontal, vertical and diagonal directions where the library and current layout constraints allow;
- preserve each board's minimum/maximum width and height;
- show a visible placement placeholder;
- show current width × height or column × row span while resizing;
- prevent context/filter/inspector rails from being dragged as boards;
- retain undo/redo and draft recovery;
- preserve mobile behavior and avoid accidental page scrolling during an intentional drag.

Suggested `react-grid-layout` settings to evaluate:

```text
isDraggable={arrangeMode}
isResizable={arrangeMode}
draggableHandle=".dashboard-board-drag-handle"
resizeHandles={["n", "s", "e", "w", "ne", "nw", "se", "sw"]}
```

Use only handles actually supported and stable in the installed version.

### 6.4 Favorite boards

Add a star/favorite affordance to each board.

Requirements:

- visible in arrange mode and available from the board action menu in view mode;
- favorite state is metadata and must not silently destroy the user's saved layout;
- optional `Favorites only` filter or favorite section may be added if it does not hide mandatory boards unexpectedly;
- favorite board IDs persist per user, project, workspace and dashboard tab;
- mandatory/governed board rules remain intact;
- favorite state survives reload and sign-in restoration.

Recommended additive preference shape:

```json
{
  "display": {
    "font_scale": "default",
    "density": "compact"
  },
  "favorite_board_ids": ["board-id"],
  "layouts": {}
}
```

Confirm the existing preference schema before choosing the final representation.

### 6.5 Interaction state machine

Implement explicit states instead of scattered booleans:

```text
view
press-armed
arranging
dragging
resizing
saving
```

The state machine may be a reducer or small hook. It must prevent click, long-press, drag and resize gestures from competing.

## 7. Recommended implementation order

### Phase 0 — Preserve and baseline

- inspect Git status and current server state;
- identify pre-existing modifications;
- capture `/login` and the primary Dashboard at 1440×1000, 1728×1117 and 720×500;
- record current font-size distribution from computed styles;
- confirm existing preference and `react-grid-layout` behavior.

### Phase 1 — Typography and display preferences

- add semantic type/leading tokens;
- add global display preference provider/hook;
- add visible menu and persistence;
- migrate touched surfaces to semantic tokens;
- verify login and Dashboard before broader routes.

### Phase 2 — Lifecycle loader

- implement SVG/CSS loader and variants;
- integrate `WorkbenchState` and route/board loading;
- add reduced-motion behavior and accessibility tests.

### Phase 3 — Arrange mode

- implement long-press hook/state machine;
- connect explicit Edit and keyboard entry;
- add jiggle state and drag handles;
- enable multidirectional resize with constraints;
- preserve undo/redo/recovery.

### Phase 4 — Favorites and persistence

- add favorite UI and metadata;
- persist and restore alongside layout/display preferences;
- verify role/mandatory-board behavior.

### Phase 5 — Validation and visual evidence

- update focused E2E tests;
- capture all affected viewports;
- update approved visual artifacts only after review;
- run the full release gate;
- restart API and web servers;
- commit and push only this feature's coherent changes without absorbing unrelated work.

## 8. Primary files to inspect

```text
web/src/main.tsx
web/src/App.tsx
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
api/ontology_dashboard/dashboard_models.py
web/e2e/foundry-overhaul.spec.ts
web/e2e/gold-flow.spec.ts
web/e2e/ui-modernization.spec.ts
web/e2e/workbench-final-overhaul.spec.ts
scripts/release_gate.py
```

Adjust the list to the actual checkout. Do not create parallel preference or layout systems when an existing one can be extended.

## 9. Test requirements

### Unit/component

- font scale maps to expected root custom property;
- density and font size remain independent;
- preference migration and invalid-value fallback;
- long press fires once after threshold;
- movement/scroll/interactive-target cancellation;
- arrange reducer transitions;
- favorite toggle and serialization;
- reduced-motion loader state.

### Playwright

- display menu changes text size and survives reload;
- login and authenticated route share the semantic typography system;
- long press enters arrange mode;
- boards receive arrange/jiggle state;
- drag changes persisted grid position;
- horizontal and vertical resize changes persisted dimensions;
- favorite survives reload;
- Escape exits arrange mode;
- interactive board controls do not trigger long press;
- 720×500 has no document-level horizontal overflow;
- reduced-motion context does not run jiggle/orbit transforms;
- loading state exposes an accessible operation label.

### Full gate

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

Use the repository's actual supported release-gate flags if they differ.

## 10. Definition of done

- One semantic typography scale governs all touched surfaces.
- A visible, persistent font-size and density menu is available.
- No primary UI text becomes unreadably small at default scale.
- The original `Data → Logic → Action` loader appears in meaningful loading states.
- Reduced-motion users receive a stable non-jiggling experience.
- Long press and explicit Edit both enter the same arrange mode.
- Boards visibly but subtly jiggle only while arranging.
- Boards can be moved and resized horizontally and vertically within constraints.
- Favorites persist without changing mandatory/governed board semantics.
- Existing cross-filter, selection, inspector, export, saved-view and role behavior remains intact.
- Focused and full tests pass.
- Updated screenshots are reviewed at all three required viewports.
- Servers restart successfully on the documented local ports.
- Feature changes are committed and pushed without destructive handling of pre-existing work.
