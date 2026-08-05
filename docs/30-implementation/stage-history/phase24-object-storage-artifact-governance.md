# Phase 24 — Object Storage and Artifact Governance

- added additive PostgreSQL/SQLite migration `0022_object_storage_artifact_governance`
- introduced typed local-emulator and S3 object-storage adapters
- added deterministic organization/Project/workspace/resource/version/checksum object keys
- made PostgreSQL the source of truth for artifact metadata, provenance, retention and audit
- added SHA-256 verification on upload, read, reconciliation and restore
- added user-bound short-lived signed downloads and separate access audit
- added retention preview/apply with legal-hold protection
- added missing/mismatch/orphan reconciliation and checksum-preserving restore
- migrated model/evaluation/feature artifact producers to `GovernedArtifactStore` while preserving
  legacy `artifact://` reads
- connected V4 Artifacts UI to readiness, catalog, verification, signed download and reconciliation

The local backend is an emulator and reports `degraded`. Managed object-storage credentials,
provider-side versioning/lifecycle proof and production restore evidence remain `BLOCKED` until a
staging or customer environment is available.
