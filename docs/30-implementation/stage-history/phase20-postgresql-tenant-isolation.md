# Phase 20 — PostgreSQL Identity, RLS and Transaction Convergence

Production persistence remains PostgreSQL-only. The current local demo runtime is reported as
`blocked` for production rather than silently treating SQLite as equivalent.

Implemented evidence:

- additive `0019_tenant_transaction_convergence` migrations for PostgreSQL and pilot SQLite
- explicit Action recovery states and retry accounting
- transaction-local organization/project scope and narrow identity-access bypass documented in API
- seven RLS coverage groups spanning identity, Project, Dataset, Ontology, Analysis, model/agent and outbox/audit tables
- machine-readable `scripts/verify_tenant_isolation.py`
- V4 settings surface showing active repository, RLS matrix, pool configuration, transaction boundary and blockers

The external-side-effect boundary remains the transactional outbox consumer. Existing V1–V3
authentication and Project workflows continue through the shared identity services.
