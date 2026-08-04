# Adaptive Modeling bounded context

Adaptive Modeling extends the Dataset → Ontology → Prediction platform after the
Predictive Maintenance Canonical v3.1 release. It owns governed metadata and
orchestration for intake profiles, mapping decisions, feature recipes, experiments,
model versions, and explanation artifacts.

It does not duplicate Dataset ingestion, Ontology materialization, Prediction Result,
WorkOrder, or Project 3 graph/Text-to-Cypher responsibilities.

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
