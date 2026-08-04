# Palantir-inspired UI overhaul evidence

This directory contains the browser evidence for UI-00 through UI-08 and the approved 48-image visual regression set.

## Capture matrix

Each stage contains 24 PNG files: eight authenticated surfaces at three viewports.

| Surface | Route |
|---|---|
| Dashboard | historical/intermediate: `/app/projects/manufacturing-demo-project`; final: `/app/projects/azure-pdm-demo-project` |
| Analysis | `/app/analysis/<analysis-id>` |
| Project Home | `/app/projects/manufacturing-demo-project/home` |
| Agent | `/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/agent` |
| Ontology | `/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/ontology` |
| Datasets | `/app/projects/manufacturing-demo-project/datasets` |
| Governance | `/app/projects/manufacturing-demo-project/workspaces/manufacturing-demo/governance` |
| Admin | `/admin` |

Viewports:

- `1440x1000`
- `1728x1117`
- `720x500` (200%-equivalent constrained desktop verification)

## Directories

- `baseline/`: UI-00 capture before token, shell, dashboard chrome, and primitive changes. Provenance is recorded in `baseline-provenance.json`.
- `stage-04/`: intermediate capture following UI-01 through UI-04.
- `final/`: approved final capture following UI-05 through UI-08.
- `visual-manifest.json`: dimensions, bytes, SHA-256 values, pair deltas, and CI thresholds for `baseline/` + `final/`.
- `scorecard.md`: before/final implementation and validation scorecard.

## Reproduce

```bash
cd web
npm run test:e2e -- e2e/foundry-overhaul.spec.ts
npm run test:e2e:overhaul
npm run test:visual:overhaul
npm run test:e2e -- e2e/palantir-overhaul-baseline.spec.ts  # verifies the default skip guard
```

The historical baseline was captured from the exact source SHA recorded in `baseline-provenance.json`; it must only be regenerated from an isolated clean worktree at that SHA. `CAPTURE_PALANTIR_BASELINE=1` is therefore reserved for an intentional historical recapture, not normal development.

The final E2E verifies Analysis vertical authoring, Object Explorer Table/Explore/Graph modes, Agent claim/evidence/checkpoint/trace navigation, Dataset materialization and detail tabs, Governance record inspectors, and document overflow at `720x500`. Normal runs write a fresh candidate set to `web/test-results/palantir-overhaul-candidate`. `CAPTURE_PALANTIR_FINAL=1` is reserved for explicitly approving a new `final/` set.

The visual gate enforces:

- exactly 48 committed PNG artifacts and 24 matching before/final pairs;
- exact dimensions, file sizes, and SHA-256 hashes from `visual-manifest.json`;
- baseline-to-final mean delta between 3% and 35%;
- same-platform candidate-to-approved mean pixel delta no greater than 0.15%;
- same-platform candidate changed-pixel ratio no greater than 0.75%;
- same-platform blurred structural delta no greater than 0.10%;
- cross-platform blurred structural delta no greater than 2.0%, with raw pixel checks disabled to avoid font rasterization false positives.

GitHub Actions already executes `scripts/release_gate.py --with-e2e`; the release gate now runs the committed-set check and then compares the Playwright candidate set to the approved final set.
