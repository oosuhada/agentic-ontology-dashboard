# Current test suite

The retained tests cover only the current Predictive Maintenance MVP and its data/runtime foundations.

- `test_mvp.py`: two-role login, route boundary, Project/Workspace, fallback, Evidence/Report, Decision/Note
- `test_predictive_maintenance_*`: Canonical V3.1 bundle, PostgreSQL runtime, Result Artifact, replay, projection, release verification
- `test_persistence_foundation.py`: current migration and audit persistence
- `test_runtime_settings.py`: production/runtime configuration
- `test_backup_restore.py`: database backup and restore

Run all retained tests with:

```bash
PYTHONPATH=api:ml/src .venv/bin/pytest -q tests
```
