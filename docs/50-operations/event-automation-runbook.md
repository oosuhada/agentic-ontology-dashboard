# Governed Event Automation Runbook

The first V4 scenario converts a high-risk prediction event into an inspection
request proposal. Conditions are typed data, not raw code. Simulation suppresses all
side effects; high-criticality runs require four-eyes approval and step-up.

Idempotency uses automation identity plus event identity. Duplicate and replayed
events cannot repeat work or external side effects. Webhook delivery remains
`not_configured` until signing secrets and an endpoint are supplied.

```bash
.venv/bin/python -m pytest -q tests/test_automation_runtime_phase32.py \
  tests/test_persistence_foundation.py tests/test_predictive_maintenance_postgresql.py
cd web && npm run lint && npm test -- --run src/platform/application/applicationRegistry.test.ts && npm run build
```
