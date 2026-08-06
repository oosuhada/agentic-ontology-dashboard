# Immutable database migration history

The migration directories contain the complete upgrade chain for databases that may have been created by earlier repository versions.

Some historical filenames and tables refer to features that are no longer exposed by the current Predictive Maintenance MVP. They remain here because applied migrations must never be renamed, edited or removed after deployment. Removing them would make a clean database and an upgraded database follow different schema histories.

Current product code uses only the identity, Project/Workspace, audit, ontology action, Canonical V3.1, Result Artifact and replay portions of this schema. Retired routes and modules are not re-enabled by retaining migration history.

Rules:

1. Never modify an applied migration.
2. Add a new forward-only migration for future schema changes.
3. Keep SQLite and PostgreSQL migration ordering deterministic.
4. Validate the full chain with `scripts/release_gate.py`.
