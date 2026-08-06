# Palantir / Foundry visual convergence review

- Reviewed: 2026-08-03
- Scope: authenticated product shell, Dashboard, Analysis, Object Explorer, Agent, Dataset and Governance surfaces
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

Legacy feature CSS remains in place for compatibility, but the final convergence layer explicitly removes large-card treatment from authenticated workbench surfaces.

## Measured change

The new 24-image approved set is intentionally different from the previous approved set. Before approval, the candidate-to-previous-final comparison measured:

```text
Desktop mean pixel change            approximately 10% to 14.5% on core workbenches
Maximum changed-pixel ratio          94.45%
Maximum structural change            12.08%
```

Against the original historical baseline, the newly approved final set remains inside the unchanged acceptance range:

```text
Baseline-to-final mean delta minimum   4.0743%
Baseline-to-final mean delta maximum  29.3991%
Allowed range                          3% to 35%
```

Key 1440×1000 baseline-to-final deltas:

| Surface | Mean pixel delta | Structural delta |
|---|---:|---:|
| Dashboard | 14.4834% | 13.0177% |
| Analysis | 15.1516% | 13.2030% |
| Agent | 7.2840% | 5.8512% |
| Object Explorer | 7.8046% | 6.2367% |
| Datasets | 8.1273% | 6.5979% |
| Governance | 6.6670% | 5.3150% |

## Stability after approval

A second independent capture of all 24 images passed the existing strict candidate thresholds without relaxing them:

```text
Maximum mean pixel delta          0.0716% / 0.15%
Maximum changed-pixel ratio       0.2544% / 0.75%
Maximum structural mean delta     0.0425% / 0.10%
```

## Remaining visual debt

The strongest remaining opportunities are no longer the global shell. They are feature-level fidelity items:

- richer Contour-style Dashboard preview/resource hierarchy in edit mode;
- more sophisticated table column affordances and inline aggregation controls;
- narrower Analysis node internals and more explicit connector/output semantics;
- Object Explorer object-type icons and link exploration polish;
- Admin/Auth convergence, which remains less Foundry-like than the primary workbenches;
- gradual removal of the old `styles.css` and `workbench.css` rules after every remaining selector has a feature-owned replacement.

The visual regression gate continues to protect the newly approved final set. It should not be treated as a Palantir-similarity score; future reference convergence must still include an explicit reference review like this document.
