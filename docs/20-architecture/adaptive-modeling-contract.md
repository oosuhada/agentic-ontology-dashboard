# Adaptive Modeling bounded context

Adaptive Modeling extends the Dataset → Ontology → Prediction platform after the
Predictive Maintenance Canonical v3.1 release. It owns governed metadata and
orchestration for intake profiles, mapping decisions, feature recipes, experiments,
model versions, and explanation artifacts.

It does not duplicate Dataset ingestion, Ontology materialization, Prediction Result,
WorkOrder, or Project 3 graph/Text-to-Cypher responsibilities.

An approved Manifest Draft is converted to a `governed-tabular` Dataset Manifest and
passed to the existing Adapter/Dataset Catalog boundary. Adaptive Modeling never writes
a replacement Dataset Version table. Governed scoring also writes the existing
Prediction Result contract in addition to its Model Score and Explanation Artifact.

## Design boundaries

- Dataset Versions remain immutable.
- Feature Dataset Versions are derived artifacts with their own identity and checksum.
- Model artifacts use portable artifact URIs; local paths are implementation details.
- Probability, calibration, threshold policy, and confidence are distinct contracts.
- Long-running training is executed by a worker or CLI, never synchronous `/api/train`.
- LLM use is deterministic-first and registry-bound.
- The `prototype_share` ideas are reimplemented; source code and its `mcp_tools`
  terminology are not adopted because no MCP protocol/server is implemented.
- Evaluation truth and experiment hidden truth are evaluator-only.

## Runtime topology

```text
FastAPI modeling endpoints
  → ModelingService
  → SQLite/PostgreSQL ModelingRepository
  → Local/shared ArtifactStore

approved Manifest Draft
  → existing AdapterService
  → DatasetCatalog / immutable Dataset Version

queued Experiment Run
  → external one-shot worker CLI
  → immutable candidate/report/model/threshold artifacts

active Model Version
  → governed scoring
  → existing PredictionResultRepository
  → ExplanationArtifact
```

PostgreSQL access sets tenant/project scope with transaction-local `set_config` so the
existing RLS policies are active. Model activation locks project/workspace model rows and
retires the previous model in the same transaction.

## Explicit degraded boundaries

- A separate worker heartbeat registry is not implemented; stale recovery uses
  Experiment `updated_at` and an explicit recovery endpoint.
- The current artifact store is a durable local/shared filesystem implementation, not an
  S3/GCS adapter.
- Calibration, global importance and operational drift remain unavailable unless a
  governed artifact is produced; offline metrics are never used as a substitute.
