# Branching, Lineage and Markings Runbook

Commercial V4 uses product branches that are independent of Git branches. Draft
resources are written as branch overlays over `main`; direct writes to `main` are
rejected. Merge is an atomic status transition after conflict validation and partial
merge is prohibited.

The initial lineage graph covers source → Dataset → Object Type → Function → Action
and Dataset → Dashboard. Markings apply at resource or field level. Policy decisions
require all effective markings and record allow/deny decisions without exposing
restricted values.

```bash
.venv/bin/python -m pytest -q \
  tests/test_branching_lineage_phase28.py \
  tests/test_persistence_foundation.py \
  tests/test_predictive_maintenance_postgresql.py

cd web
npm run lint
npm test -- --run src/platform/application/applicationRegistry.test.ts
npm run build
```

In V4 select **Lineage & evidence**, create a review branch, inspect the lineage
edges, then run the export-policy check. The sample Dataset is `confidential` and its
`failure_probability` field is `export_restricted`; export remains denied even when
the caller is eligible for both markings.

Production branch review approvals, rebase UI, field-level three-way merge, inherited
marking propagation across every materialization, and time-bound break-glass grants
remain explicit follow-on capabilities.
