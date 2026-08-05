# Ontology Interfaces, Actions and Functions Runbook

## Runtime boundary

Commercial V4 exposes versioned Ontology Interfaces, schema-driven governed Actions,
and deterministic published Functions. V1 through V3 keep their existing Object and
Action workflows.

The sample `Asset` Interface is implemented by `equipment` and `compressor` through
explicit property mappings. The `request-asset-inspection` Action uses one persisted
JSON schema for both server validation and generated UI preview. The
`asset-risk-metric` Function is a fixed published implementation with a runtime
checksum, strict input/output schemas, a 250 ms timeout contract, and `deny_all`
network policy.

## Verification

```bash
.venv/bin/python -m pytest -q \
  tests/test_ontology_primitives_phase27.py \
  tests/test_persistence_foundation.py \
  tests/test_predictive_maintenance_postgresql.py

cd web
npm run lint
npm test -- --run
npm run build
```

Open `/app/projects/manufacturing-demo-project/blueprint-v4`, select **Actions &
functions**, then run the Action preview and deterministic Function.

## Safety guarantees

- No raw SQL or Cypher interface is exposed.
- User or LLM supplied code is never executed or published.
- Function inputs must exactly match the published schema.
- Network access and secret injection are denied in the current runtime.
- Action preview is dry-run only and records the intended actor, reason, targets and
  parameters before any approval or side effect.
- Cross-project reads are prevented by repository scoping and PostgreSQL RLS.

Container-isolated third-party function packages, approval execution, compensation,
and external side-effect adapters remain future production capabilities and must not
be represented as configured.
