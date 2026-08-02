# UI-00 to UI-08 scorecard

Verified on 2026-08-02 against the actual checkout, isolated Playwright databases, the starting-SHA worktree, and the release gate.

## Stage status

| Stage | Result | Evidence |
|---|---|---|
| UI-00 Baseline and reference register | Complete | 24 starting-SHA screenshots, reference review, license record and `baseline-provenance.json` |
| UI-01 Tokens and primitives | Complete | Foundry token layer, EntityTitle, StatusPill, WorkbenchHeader/Toolbar and explicit Empty/Loading/Error states |
| UI-02 Global application shell | Complete + convergence pass | Shared 40px platform rail, 184px resource navigation and 34px topbar across primary Workbenches |
| UI-03 Dashboard resource chrome | Complete | Resource header, compact tabs/actions, parameter rail, saved view, share, export and inspector |
| UI-04 Shared board runtime | Complete | BoardFrame, MetricStrip, DenseDataTable, ChartPanel and runtime metadata |
| UI-05 Object Explorer | Complete | Dense Object Set table, Table/Explore/Graph modes and Properties/Links/Actions/Lineage inspector |
| UI-06 Analysis authoring | Complete | Vertical path, grouped palette, connector insertion, board I/O, run lifecycle and five inspector tabs |
| UI-07 Agent evidence terminal | Complete | Persisted run history, bottom composer and Evidence/Claims/Checkpoints/Persisted Trace inspector |
| UI-08 Dataset and Governance polish | Complete | Dataset resource/version inspector and Governance projection/approval record inspectors |
| 48-image visual regression | Complete | Exact committed manifest, same-platform raw threshold, cross-platform structural threshold and CI release-gate integration |

## Final information architecture

| Surface | Final structure |
|---|---|
| Dashboard | Global shell → resource header → compact toolbar → parameter rail → board canvas → optional inspector |
| Analysis | Board palette → vertical governed path → selected output → Config/Result/Quality/Lineage/Runtime inspector |
| Object Explorer | Object type rail → dense Object Set or Explore/Graph view → Properties/Links/Actions/Lineage inspector |
| Agent | Persisted run history → grounded answer and claims → bottom composer → evidence/checkpoint/trace inspector |
| Dataset | Dense Dataset resource table → immutable Version identity → Overview/Schema/Profile/Files/Versions/Lineage/Projections |
| Governance | KPI and checkpoint tabs → projection/approval records → selected governed record inspector |

## Geometry assertions

The browser tests measure the live DOM:

- global topbar: 34px
- platform rail: 40px
- resource navigation: 184px
- expanded navigation total: 224px
- collapsed navigation: 40px
- Dashboard toolbar: 32px
- BoardFrame header: 29px
- DenseDataTable row: 28px
- Object Explorer desktop panes: 255px / flexible canvas / 300px
- all primary Workbenches: no document-level horizontal overflow at 720x500

## Functional regression coverage

The overhaul preserves existing API and scope contracts. Passing browser tests cover:

- Dashboard edit, undo/redo, recovery, save, share, export and cross-filter propagation
- Analysis server run, cancel, result inspection, pinned Dashboard reference and Dataset materialization
- Object search, Project 3 degraded safety, traversal, graph view and permission-scoped actions
- Agent query, claims-to-evidence navigation, persisted runs, checkpoints and trace records
- Dataset pagination, immutable Version detail, mappings, lineage and store projections
- Governance project scope, projection retry, approval and policy records
- role access, archived Project tombstones, accessibility landmarks and persisted theme

## Screenshot evidence

Three evidence stages exist:

- `baseline/`: 24 historical screenshots restored from starting SHA `37c9481655a3df18b95b13765251655bd738ba1f`.
- `stage-04/`: 24 intermediate screenshots after UI-01 through UI-04.
- `final/`: 24 approved screenshots after UI-05 through UI-08.

Each stage covers Dashboard, Analysis, Project Home, Agent, Ontology, Datasets, Governance and Admin at `1440x1000`, `1728x1117` and `720x500`.

The committed visual contract uses `baseline/` + `final/`, for exactly 48 PNG artifacts and 24 matching pairs. Baseline-to-final mean pixel deltas remain between the manifest limits of 3% and 35%.

## Visual regression profiles

`visual-manifest.json` records the approved platform as `darwin`.

Same-platform candidate checks:

- mean raw pixel delta ≤ 0.15%
- changed pixel ratio ≤ 0.75%
- blurred structural mean delta ≤ 0.10%

Cross-platform candidate checks:

- raw pixel checks disabled to avoid operating-system font rasterization false positives
- grayscale 180×125 downsample + Gaussian blur structural mean delta ≤ 2.4%

Latest local candidate result:

```text
Candidate images                         24 / 24
Mean raw pixel delta max                 0.0716% / 0.15% PASS
Changed pixel ratio max                  0.2544% / 0.75% PASS
Structural mean delta max                0.0425% / 0.10% PASS
```

First successful Ubuntu candidate result:

```text
GitHub Actions run                      30748701960 PASS
Ubuntu image                            ubuntu24 / 20260720.247.2
Playwright                              1.62.1
Candidate images                        24 / 24
Cross-platform structural max           1.5436% / 2.4% PASS
Observed × 1.5                          2.3154%
Calibrated ceiling                      2.4%
```

The maximum is the `720x500/project-home.png` font-fallback reflow. The next highest result is `720x500/analysis.png` at 1.3674%. The successful artifact and review are recorded in `ubuntu-calibration.md`.

## Final validation

```text
Canonical naming                         PASS
PostgreSQL migration/RLS/runtime         PASS
Backend pytest                           122 PASS
Gold scenarios                           8/8 PASS
Frontend Vitest                          6 PASS
TypeScript                               PASS
Production build                         PASS
Initial JavaScript                       228.07 KiB / 300 KiB PASS
Largest deferred JavaScript              443.24 KiB / 500 KiB PASS
Full Playwright regression               49 PASS / 3 INTENTIONAL SKIP
Final overhaul acceptance                8 PASS
Legacy comparison manifest               PASS
48-image committed visual manifest       PASS
Candidate visual thresholds              PASS
Ubuntu release gate                      16/16 PASS
```

## Review outcome

The final evidence set passed the surface hierarchy, information density, 720px overflow, degraded-state, inspector priority, Analysis connector, and Object Explore/Graph differentiation review. No approved screenshot needed replacement. Dashboard capture now waits for the lazy metric board instead of accepting a loading placeholder.

The physical namespace relocation is complete. The 2026-08-03 convergence pass also replaced the generic SaaS sidebar with a platform rail + resource navigation hierarchy and approved a new 24-image final set. See `convergence-review.md` for the gap diagnosis and measured change. Managed production, connector, IdP, object-storage, and observability work remains externally blocked on this host.
