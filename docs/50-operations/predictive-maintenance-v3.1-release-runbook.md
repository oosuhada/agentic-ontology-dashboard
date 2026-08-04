# Predictive Maintenance Canonical v3.1 Release Runbook

## Purpose

This runbook verifies the immutable V3.1 data, Result Artifact, Ontology, graph,
replay, visualization, Dashboard, and governance boundary without treating missing
external infrastructure as a successful production release.

## Local contract verification

```bash
PACKAGE_ROOT="/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1"
PROJECT3_ROOT="/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트3"

PYTHONPATH=api:ml/src .venv/bin/python \
  scripts/verify_predictive_maintenance_v3_1_release.py \
  --package-root "$PACKAGE_ROOT" \
  --project3-root "$PROJECT3_ROOT" \
  --run-package-validator \
  --output artifacts/predictive-maintenance-v3.1-release.json
```

An exit code of `0` means all supplied local contracts passed. A `blocked` item is
reported when an external service or credential was not supplied; it is never
converted into a pass. `--strict` returns a non-zero exit code when blocked items
remain.

## Targeted regression suites

```bash
PYTHONPATH=api:ml/src .venv/bin/python -m pytest -q \
  tests/test_predictive_maintenance_v3_compatibility.py \
  tests/test_predictive_maintenance_projection.py \
  tests/test_predictive_maintenance_graph_projection.py \
  tests/test_predictive_maintenance_result_replay.py \
  tests/test_predictive_maintenance_visualization_planner.py \
  tests/test_predictive_maintenance_v3_release_verifier.py

cd web
npm test -- --run src/features/predictive-maintenance/PredictiveMaintenanceReplayPanel.test.tsx
npm run lint
npm run build
```

Project 3 contract tests:

```bash
cd "/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트3"
.venv/bin/python -m pytest -q \
  tests/test_ontology_graph_projection.py \
  tests/test_project_graph_scope.py \
  tests/test_project_readiness.py \
  tests/test_text2cypher.py
```

## Production capability verification

```bash
.venv/bin/python scripts/verify_production_environment.py
```

For a strict staging release, configure the required URLs and credentials and run:

```bash
.venv/bin/python scripts/verify_production_environment.py --strict \
  --require postgresql \
  --require redis \
  --require neo4j \
  --require project3
```

## Recovery and rollback

1. Do not modify or delete the V2 Dataset Version.
2. Mark a failed V3.1 ingestion or projection as failed; never leave it partially ready.
3. Retry graph delivery with the same idempotency key.
4. Keep PostgreSQL Result Artifact and replay available when Neo4j is degraded.
5. Select the prior V2 Dataset Version to roll the UI back without rewriting lineage.
6. Rebuild V3.1 only from the verified package and checksum, then register a new
   immutable Dataset Version if any source artifact changes.

## Semantic safety

- `SUPPLIES_AIR_TO` is topology, not a causal claim.
- The model predicts binary failure risk, not PWF/HDF/OSF/TWF classes.
- A recommended action is not an approved or executed WorkOrder.
- Evaluation truth and experiment hidden truth are evaluator-only.
- Release-gate accuracy is governance evidence, not instance-level prediction accuracy.

## Current external prerequisites

Production release remains blocked until the environment supplies Docker Compose,
PostgreSQL, Redis, Neo4j, Project 3, OIDC, connector, object-storage, and observability
configuration required by `verify_production_environment.py`.
