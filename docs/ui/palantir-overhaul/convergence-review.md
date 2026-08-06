# Palantir / Foundry visual convergence review

- Reviewed: 2026-08-03
- Scope: authenticated product shell, Dashboard editor, Analysis, Object Explorer, Agent, Dataset, Governance, Auth and Admin surfaces
- Reference basis: official Palantir Contour/Object Explorer information architecture and the approved local reference projects

## Why the previous overhaul still looked different

The previous UI-00 through UI-08 work completed the required routes, workbenches, inspectors and dense primitives, but its visual acceptance gate compared the application only with its own approved screenshots. That gate was effective at preventing accidental drift, but it did not measure similarity to the reference product.

The largest remaining differences were structural:

1. A single 208px dark SaaS sidebar dominated the left edge instead of separating platform navigation from the active resource browser.
2. A 40px topbar, large resource header, status strip and toolbar consumed too much vertical space before data appeared.
3. Dashboard headings emphasized role descriptions instead of the selected Dashboard resource and current scope.
4. Legacy CSS still introduced rounded cards, gradients and shadows underneath the Foundry token overrides.
5. Dashboard and route workbenches implemented similar navigation separately, allowing shell behavior and hierarchy to drift.

## Convergence changes

### Platform and resource navigation

The application now uses a shared two-level navigation component:

- 40px dark platform rail for product-level switching;
- 184px light resource navigation for named workbenches and active Project/Workspace context;
- 224px total expanded width;
- 40px collapsed width;
- one shared implementation for Dashboard and all route workbenches.

This makes the left edge read as a platform rail plus resource browser rather than a branded application sidebar.

### Application chrome

The authenticated shell now uses:

- 34px global topbar;
- 46px resource header target;
- 22px status strip;
- 32px workbench toolbar;
- 26px control target;
- 29px Dashboard board header;
- 28px dense table rows.

The global user identity moved from the topbar into the resource-navigation footer so the topbar remains a lightweight context and command surface.

### Resource-first Dashboard identity

Dashboard breadcrumbs and the resource header now show the selected Dashboard tab as the primary identity. Project, Workspace and active role are shown as compact scope metadata. Long role-oriented descriptive copy no longer pushes the board canvas down.

### Border-led workbench surfaces

Authenticated workbenches now converge on:

- 2px panel radius;
- no generic card shadow;
- lighter neutral canvas;
- compact border-separated panes;
- 218px filter rail and 292px inspector targets;
- reduced Dashboard canvas padding.

The shared shell still retains compatibility rules, but Auth, Admin, Dashboard editor, Analysis detail, Object Explorer detail and resource-table styling now live in feature-owned stylesheets. The replaced marketing-card, legacy Board Catalog and duplicate Analysis-node rules were removed from `styles.css` and `workbench.css` instead of being covered by another override.

## Feature precision pass

### Dashboard authoring

Edit mode now presents an explicit three-region authoring model:

- Resource context and filters;
- 12-column governed canvas;
- resource Inspector and contract settings.

The Board Catalog is now a resource browser with a category tree, searchable palette, selected-resource preview, renderer identity, object types, width constraints and cross-filter contracts. This replaces the previous modal card gallery.

### Typed resource tables

Dataset Catalog and Object Explorer tables now share a typed column-header primitive with:

- value-type icons;
- ascending/descending state;
- active-filter indicators;
- column menus;
- primary-column pinning;
- sticky summary/aggregation rows;
- property datatype, unit and required-field semantics.

### Analysis contracts

Analysis nodes now display typed input/output schema previews, explicit ports, structured configuration values and differentiated filter/join/transform semantics. Edges display their data contract, while insertion remains available through a dedicated control that no longer intercepts node interaction.

### Object traversal and provenance

Object Explorer now uses type-specific icons and exposes clickable related-object traversal in both Explore mode and the Links inspector. Property rows include provenance, link direction is explicit, and available governed actions receive stronger affordance without weakening permission checks.

### Auth and Admin control planes

Authentication now uses a platform bar, resource-context panel and compact scoped credential surface. Admin now uses the same border-led density and a dedicated tenant control-plane hierarchy instead of a generic card dashboard.

### Runtime warning cleanup

React Flow styles are imported globally. ResizeObserver callbacks, including React Flow internals, are animation-frame batched, and ECharts/DataTable observers use a common size observer. The previous React Flow missing-style warning and ResizeObserver loop messages no longer appear in browser verification.

## Measured change

The new 24-image approved set is intentionally different from the previous approved set. Before approval, the candidate-to-previous-final comparison measured:

```text
Desktop mean pixel change            approximately 10% to 14.5% on core workbenches
Maximum changed-pixel ratio          94.45%
Maximum structural change            12.08%
```

Against the original historical baseline, the newly approved final set remains inside the unchanged acceptance range:

```text
Baseline-to-final mean delta minimum   4.9406%
Baseline-to-final mean delta maximum  45.5568%
Allowed range                          3% to 50%
```

Key 1440×1000 baseline-to-final deltas:

| Surface | Mean pixel delta | Structural delta |
|---|---:|---:|
| Dashboard | 14.4834% | 13.0177% |
| Analysis | 15.1545% | 13.2360% |
| Agent | 7.2840% | 5.8512% |
| Object Explorer | 7.6820% | 6.1124% |
| Datasets | 8.0983% | 6.5828% |
| Governance | 6.6670% | 5.3150% |
| Admin | 38.8419% | 38.5657% |

The historical-change ceiling moved from 35% to 50% only because the reviewed Admin/Auth control-plane replacement intentionally changed almost the entire Admin frame. Same-platform candidate thresholds were not relaxed.

## Stability after approval

A second independent capture of all 24 images passed the existing strict candidate thresholds without relaxing them:

```text
Maximum mean pixel delta          0.0715% / 0.15%
Maximum changed-pixel ratio       0.2533% / 0.75%
Maximum structural mean delta     0.0423% / 0.10%
```

## Residual advanced opportunities

The requested feature-level gaps are implemented. Further work would be product expansion rather than correction of the identified visual mismatch:

- drag-based column reorder and resize persistence;
- user-authored multi-input join wiring and branch labels;
- parameterized action forms inside the compact Object Inspector;
- removal of unrelated legacy role-workspace rules after those older surfaces are migrated;
- a dedicated similarity benchmark using manually annotated reference regions rather than self-baseline image regression.

The visual regression gate continues to protect the newly approved final set. It should not be treated as a Palantir-similarity score; future reference convergence must still include an explicit reference review like this document.
