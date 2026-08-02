# Ubuntu visual calibration evidence

- Date: 2026-08-02
- Git SHA: `112e55461df6e2a6ce2a602f59ad1ded8dadc56c`
- GitHub Actions run: [30748701960](https://github.com/oosuhada/agentic-ontology-dashboard/actions/runs/30748701960)
- Artifact: `palantir-overhaul-ubuntu-30748701960` (30-day retention)
- Result: `PASS`

## Environment

```text
Runner OS        Linux x64
Image            ubuntu24 / 20260720.247.2
Kernel           Linux 6.17.0-1020-azure
Python           3.12.13
Node             24.18.0
Playwright       1.62.1
Candidate PNGs   24
```

The artifact also contains the installed font family/package inventories, sanitized environment metadata, the 16-check release report, all 24 candidate PNGs, and the visual report.

## Release and visual results

```text
Hygiene                              PASS
PostgreSQL migration/RLS             PASS
PostgreSQL runtime repositories      PASS
Backend pytest                       122 PASS
Gold scenarios                       8/8 PASS
Frontend Vitest                      6 PASS
TypeScript/build/bundle budget       PASS
Playwright                           49 PASS / 3 intentional skip
Release gate                         16/16 PASS
Committed visual set                 48 artifacts / 24 pairs PASS
Ubuntu candidates                    24/24 PASS
Structural maximum                   1.5436%
```

Raw mean and changed-pixel values are informational across operating systems because the approved set uses macOS font rasterization. The Ubuntu gate uses the blurred structural metric.

## Calibration decision

The largest structural differences were:

| Candidate | Structural delta |
|---|---:|
| `720x500/project-home.png` | 1.5436% |
| `720x500/analysis.png` | 1.3674% |
| `720x500/governance.png` | 1.0350% |
| `720x500/dashboard.png` | 0.9903% |

Manual comparison confirmed font fallback and Korean/Latin line wrapping as the cause; pane order, controls, selected states, hierarchy, and document width were preserved. The runner does not have Inter, Pretendard, or Apple system fonts and falls back to the installed Linux families.

The execution plan requires `observed max × 1.5~2.0`. The lower bound is:

```text
1.5436% × 1.5 = 2.3154%
```

The cross-platform structural ceiling is therefore rounded to `2.4%`. Same-platform thresholds remain unchanged at `0.15%` raw mean, `0.75%` changed pixels, and `0.10%` structural delta.

## Product-design review

The approved 1440px and constrained 720px surfaces were reviewed manually; the 1728px set was checked through manifest integrity, live DOM geometry, and Playwright capture.

- Dashboard, Analysis, Agent, Ontology, Dataset, Governance, Project Home, and Admin retain a consistent resource-header and pane hierarchy.
- The 720px layout collapses the rail and stacks controls without document-level horizontal overflow.
- Analysis preserves connector insertion, governed path ordering, selected output, and inspector priority.
- Object Table, Explore, and Graph remain functionally distinct and retain the same scoped inspector.
- Dataset immutable-version tabs and Governance projection/approval inspectors retain their intended priority.
- Empty Agent state, degraded Project 3 state, loading states, status pills, and light/dark theme behavior remain covered.
- A real nondeterministic Dashboard capture was found locally: the screenshot could be taken while the lazy board module was still loading. The capture now waits for the metric strip and the loading placeholder to disappear.

No approved screenshot required replacement.
