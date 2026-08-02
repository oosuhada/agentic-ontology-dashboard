# Ontology Dashboard Visual Language

- Updated: 2026-08-02
- Scope: visual tokens and density rules only. Product behavior, RBAC and data contracts remain in their feature documents.
- Reference use: Palantir Blueprint/Contour information hierarchy and the local reference implementations are used as interaction and density references. Source code and brand assets are not copied.

## 1. Visual intent

Ontology Dashboard should feel like a high-density operational workbench rather than a consumer analytics landing page.

The target hierarchy is:

1. neutral application canvas;
2. clearly bounded working surfaces;
3. compact headers and controls;
4. semantic color used only for state, selection and action;
5. inspectable evidence and metadata without oversized cards.

Large rounded marketing cards, excessive shadows, decorative gradients and large empty gutters are not part of the workbench language.

## 2. Canonical tokens

The runtime tokens live in `web/src/styles.css` under `:root` and `[data-theme="dark"]`.

### Surfaces

| Token | Light | Purpose |
|---|---:|---|
| `--od-canvas` | `#edf0f3` | application and pane background |
| `--od-surface` | `#ffffff` | primary work surface |
| `--od-surface-muted` | `#f6f7f9` | rail, inspector and secondary pane |
| `--od-surface-raised` | `#ffffff` | menu or temporarily raised content |

### Borders and elevation

| Token | Value | Rule |
|---|---:|---|
| `--od-border` | `#c8ced8` | pane and major section boundary |
| `--od-border-subtle` | `#e1e5eb` | rows and internal cards |
| `--od-shadow-panel` | one restrained 1–2px shadow | only for top-level workbench surfaces |
| `--od-radius-panel` | `6px` | top-level panel |
| `--od-radius-control` | `4px` | input, row and compact card |

### Text

| Token | Light | Usage |
|---|---:|---|
| `--od-text` | `#182026` | primary text |
| `--od-text-secondary` | `#5f6b7c` | descriptions and metadata |
| `--od-text-muted` | `#8a94a6` | timestamps and secondary IDs |

### Semantic color

| Token | Value | Usage |
|---|---:|---|
| `--od-accent` | `#2d72d2` | selected object, active navigation, primary action |
| `--od-success` | `#238551` | ready, validated, succeeded |
| `--od-warning` | `#c87619` | stale, indexing, degraded |
| `--od-danger` | `#cd4246` | failed, denied, invalid |

Semantic color must not be used to decorate an entire workbench. It identifies state or directs attention.

## 3. Density rules

- Global workbench padding: 12–14px.
- Pane headers: 40–44px.
- Compact control and table row target: approximately 30px.
- Pane-to-pane gap: use borders instead of wide whitespace.
- Section gap: 6–9px.
- Metadata text: 7–9px where the information is supplementary.
- Primary workbench title: 17–19px, not a marketing-display headline.
- Inspector width: 280–320px on desktop.
- Left rail width: 240–300px depending on the workflow.

## 4. Workbench composition

### Header

The header contains scope, title and high-frequency actions only. Long descriptions belong in a callout or inspector.

### Left rail

The left rail contains one of:

- object type and object list;
- query controls and recent runs;
- dataset list;
- navigation or saved views.

It must not duplicate tenant administration.

### Center workspace

The center is the primary task surface: graph, answer/evidence, canvas or table. It receives the largest flexible column.

### Right inspector

The right side explains selection, source, lineage, validation and runtime metadata. It should be independently scrollable.

## 5. Evidence-specific rules

Agent and audit screens must render the following together:

- claim text;
- claim validation and confidence;
- clickable evidence IDs;
- source store;
- source reference;
- Dataset Version when present;
- Object ID when present;
- score and metadata;
- orchestration step and latency;
- degraded caveat or failure.

A claim cannot visually appear as verified when its evidence link is missing. Clicking an evidence ID should move focus to the corresponding evidence record.

## 6. Light and dark consistency

Dark mode uses the same hierarchy, dimensions and semantic meaning. It is not a separate visual theme. Borders remain visible, selected surfaces use a restrained accent background, and state colors preserve their meaning.

## 7. Applied workbenches

The shared semantic tokens and compact density rules now apply to:

```text
/app/projects/:projectId/home
/app/projects/:projectId/datasets
/app/projects/:projectId/workspaces/:workspaceId/agent
/app/projects/:projectId/workspaces/:workspaceId/ontology
/app/projects/:projectId/workspaces/:workspaceId/governance
```

Agent retains the three-pane evidence-first composition. Ontology, Governance and Dataset surfaces use the same canvas, surface, border, text, selection and focus tokens. Project Home uses the same compact operational hierarchy instead of a marketing landing-page layout. Light and dark mode therefore share dimensions, status meaning and selection treatment across all governed workbenches.

## 8. Performance budget

High-density workbenches must not force every renderer into the authentication and routing shell.

- Initial JavaScript loaded from `index.html`: maximum 300 KiB raw.
- Admin, Manufacturing, Agent, Ontology, Dataset and Governance surfaces use route-level lazy boundaries.
- Analysis and board renderer implementations use runtime lazy boundaries inside Manufacturing.
- Large table/chart dependencies remain deferred and must not re-enter the initial route payload.
- Table filtering, sorting, column visibility, virtual scrolling and server pagination use a lightweight local renderer rather than loading a full table framework into every route.
- Pie and Cartesian ECharts runtimes are split so each board loads only its required chart modules.
- `npm run build` executes `web/scripts/check-initial-bundle.mjs` and fails when the initial budget regresses.

Current verified budgets:

```text
initial JavaScript       213.87 KiB / 300 KiB
largest deferred chunk   443.24 KiB / 500 KiB target
DataTable renderer         6.42 KiB
Dashboard board router    10.25 KiB
```

## 9. Acceptance

A workbench visual change is accepted only if:

1. the corresponding Playwright flow still passes;
2. project/workspace isolation still passes;
3. important IDs and metadata are not clipped;
4. keyboard focus remains visible;
5. light and dark mode preserve readable contrast;
6. a screenshot artifact is attached to the test report for major layout changes;
7. the initial JavaScript budget still passes.
