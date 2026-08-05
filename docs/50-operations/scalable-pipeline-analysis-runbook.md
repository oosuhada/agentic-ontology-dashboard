# Scalable Pipeline and Analysis Runbook

Commercial V4 exposes a typed pipeline graph and a safe PostgreSQL pushdown preview.
Identifiers are allowlisted, values remain bound parameters, Cartesian joins without
keys are blocked, and deep pagination uses a keyset cursor rather than `OFFSET`.

Preview is never represented as materialization. Published outputs are immutable
Dataset Versions after schema, quality and marking checks.

```bash
.venv/bin/python -m pytest -q tests/test_pipeline_runtime_phase30.py \
  tests/test_persistence_foundation.py tests/test_predictive_maintenance_postgresql.py
cd web && npm run lint && npm run build
```

Open Commercial V4 and select **Analysis & Pipeline** to inspect nodes, estimated
scan cost, query plan, cancellation contract and materialization semantics.
