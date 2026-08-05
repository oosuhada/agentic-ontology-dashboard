# Continuous Governed MLOps Runbook

Commercial V4 displays Feature View parity/freshness, champion/challenger state,
sample-size-aware drift, retraining review and release-unit rollback. Drift alone
never promotes a model. Shadow predictions cannot trigger operational Actions.

```bash
.venv/bin/python -m pytest -q tests/test_mlops_runtime_phase31.py \
  tests/test_persistence_foundation.py tests/test_predictive_maintenance_postgresql.py
cd web && npm run lint && npm run build
```

The online Feature Store remains `not_configured` without production Redis-compatible
infrastructure. Synthetic benchmark results are limitations, not production evidence.
