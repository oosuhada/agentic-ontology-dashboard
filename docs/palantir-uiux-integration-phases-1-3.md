# Palantir UI/UX Integration — Phases 1–3

## Checkpoint

The pre-integration application state is preserved by the annotated Git tag:

```text
pre-palantir-uiux-integration-20260803-1552
```

To inspect or branch from the checkpoint without destroying current work:

```bash
git switch -c inspect/pre-palantir-uiux-integration pre-palantir-uiux-integration-20260803-1552
```

## Phase 1 — Frontend-only projection layer

### 1. Typed DataPill metadata

- Added a frontend-only `AnalysisDataKind` taxonomy.
- Added typed input/output metadata for every existing Analysis step.
- Added `DataPill` to Path cards, Canvas cards, dependency nodes, Contents, and compatible actions.
- Existing backend `nodes` and `edges` payloads are unchanged.

### 2. Path / Canvas / Graph switch

- Path remains the default and preserves current server execution behavior.
- Canvas projects the same nodes into free-form movable and resizable cards.
- Graph projects the same nodes and edges into a dependency graph.

### 3. Graph projection

- Uses existing Analysis node and edge state.
- Supports focus mode.
- Supports horizontal and vertical layouts.
- Supports computational-node collapse with rewired visible edges.

### 4. Contents and Dependency panels

- Contents lists canvases and cards.
- Dependency panel displays upstream and downstream cards.
- Selecting a dependency updates the shared selected Analysis node.

### 5. Resizable Workbench layout

- Left and right pane widths are pointer- and keyboard-resizable.
- Widths are stored in `localStorage`.
- Double-clicking a separator restores the default width.
- Mobile continues to use the existing drawer pattern.

## Phase 2 — Existing API integration

### 6. Compatible next actions

- The Analysis palette derives compatibility from the selected node output type.
- Incompatible steps remain visible but disabled with the required input contract.
- Compatible actions continue to call the existing `addStep()` path.

### 7. Multiple Canvas presentation state

- Multiple named canvases can be created, renamed, duplicated, selected, and deleted.
- Canvas frames and active view are presentation-only state.
- Presentation state is stored separately from the server Analysis definition.

### 8. Hidden computational nodes

- Cards can be hidden from a presentation Canvas without removing them from execution.
- Graph mode can collapse computational nodes while retaining logical connectivity.
- Hidden nodes remain visible in dependency and lineage semantics.

### 9. ObjectSet selection merge

- Row selection is independent from row focus.
- Supported merge modes:
  - Replace
  - Union
  - Intersection
  - Difference
- Staged selections are explicitly applied before changing the active ObjectSet selection.

### 10. Linked-object traversal actions

- Selected ObjectSet roots can be traversed through the existing ontology traversal API.
- Multiple traversal responses are merged by object and edge identity.
- The merged result opens in the existing Explore view and inspector flow.

## Phase 3 — Result presentation

### 11. Time-series range UI

- Added explicit training-range start and end controls.
- Added visible selected-range shading.
- Added full-range reset.

### 12. Forecast editor

- Model selection: Linear, Constant, Seasonal.
- Forecast horizon, confidence interval, slope, and seasonal coefficient controls.
- Settings remain presentation-only.

### 13. Confidence band and event markers

- Forecast boundary is visibly separated from observed data.
- Forecast confidence band is rendered around projected values.
- Event marker lines, points, and labels can be toggled.
- When server result rows exist, they are preferred as the chart input.
- Authoritative forecast values still belong to the Prediction Result Contract.

### 14. Visual reference gallery

Public route:

```text
/reference
```

The gallery compares the tagged 1440×1000 pre-integration baseline with current browser captures for:

- typed Analysis Path
- free-form Canvas
- dependency Graph
- Forecast editor
- ObjectSet selection
- linked traversal

Generated captures:

```text
docs/ui/palantir-integration/final/
```

## Main implementation files

```text
web/src/ui/foundry/DataPill.tsx
web/src/ui/foundry/ResizableWorkbenchLayout.tsx
web/src/features/analysis/analysisPresentation.ts
web/src/features/analysis/AnalysisCanvasProjection.tsx
web/src/features/analysis/AnalysisGraphProjection.tsx
web/src/features/analysis/AnalysisContentsPanel.tsx
web/src/features/analysis/AnalysisDependencyPanel.tsx
web/src/features/analysis/AnalysisTimeSeriesForecast.tsx
web/src/features/reference/ReferenceGallery.tsx
web/e2e/palantir-integration-phases.spec.ts
```

## Verification

Completed successfully:

```text
npm run lint
npm run build
npm test
playwright: palantir-integration-phases.spec.ts — 3 passed
playwright: UI-06 Analysis regression — 1 passed
playwright: mobile workbench regression — passed in the combined run
```

The broad `workbench-final-overhaul` run completed 7 of 9 tests. The Analysis failure was caused by an edge label intercepting pointer input and was fixed; its focused rerun passed. The remaining failure is an unrelated pre-existing 720px Dashboard capture expectation for `.dashboard-data-connections`.
