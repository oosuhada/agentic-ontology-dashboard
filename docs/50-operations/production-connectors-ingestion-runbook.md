# Production Connectors and Governed Ingestion Runbook

## Scope

Phase 26 establishes a tenant-scoped connector registry, durable ingestion jobs,
atomic checkpoints, schema-drift classification, idempotent committed records,
quarantine records, and the Commercial V4 ingestion surface. The built-in fixture
adapter is for local verification only. Production providers remain
`not_configured` until a secret-manager reference and provider adapter are present.

## Configuration

Configure providers with secret references only. Never put credentials in connector
configuration, logs, or source control.

```bash
export ONTOLOGY_DASHBOARD_CONNECTOR_POSTGRESQL_CREDENTIAL_REF='secret://connectors/source-a'
export ONTOLOGY_DASHBOARD_CONNECTOR_S3_CREDENTIAL_REF='secret://connectors/bucket-a'
```

The readiness API reports only whether a reference exists; it never returns the
reference value.

## Local verification

```bash
.venv/bin/python -m pytest -q \
  tests/test_connectors_phase26.py \
  tests/test_persistence_foundation.py \
  tests/test_predictive_maintenance_postgresql.py

cd web
npm run lint
npm test -- --run
npm run build
```

Open Commercial V4 and select **Ingestion**:

```text
/app/projects/manufacturing-demo-project/blueprint-v4
```

The fixture run is queued through the durable worker. Checkpoint advancement occurs
inside the same transaction that records validated rows and quarantine entries.

## Worker operation

Start the canonical worker command documented by the deployment runtime. The worker
must advertise the `connector_ingestion` job type. A missing adapter fails the job;
it must not acknowledge or advance the source checkpoint.

## Incident handling

- **Breaking schema drift:** pause the connector, inspect the schema diff and
  quarantine sample, update mapping through approval, then replay.
- **Growing quarantine:** inspect reason codes without exporting sensitive payloads.
- **Queue saturation:** reduce source batch rate or increase worker capacity; do not
  bypass durable queue limits.
- **Credential rotation:** update the secret-manager object behind the reference,
  test connectivity, then resume. Do not replace the reference with plaintext.
- **Checkpoint recovery:** restore the database and durable job state together,
  verify committed-record checksums, then resume from the stored checkpoint.

## Production status semantics

- `ready`: provider adapter and secret reference are configured and verified.
- `degraded`: local fixture path works, but one or more production providers are
  unconfigured.
- `blocked`: production mode requires providers that are not configured.
- `not_configured`: no credential reference exists for that provider.

Customer source credentials and a real provider endpoint are external prerequisites;
their absence must remain `BLOCKED`, not `PASS`.
