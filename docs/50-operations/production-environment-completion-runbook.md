# Production Environment Completion Runbook

- Last updated: 2026-08-02
- Scope: Ontology Dashboard production evidence that cannot be produced from the current checkout alone
- Principle: missing infrastructure or credentials are reported as `blocked`; they are never counted as implemented or verified

## 1. Preflight

Run the informational check on any environment:

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/verify_production_environment.py
```

A staging gate should name the required capabilities and use strict mode:

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/verify_production_environment.py \
  --strict \
  --require compose \
  --require postgresql \
  --require redis \
  --require neo4j \
  --require project3
```

The verifier does not print secret values. It only reports configuration and reachability.

## 2. Required environment variables

### Core runtime

```text
ONTOLOGY_DASHBOARD_DATABASE_URL
ONTOLOGY_DASHBOARD_REDIS_URL
ONTOLOGY_DASHBOARD_NEO4J_URI
ONTOLOGY_DASHBOARD_NEO4J_USERNAME
ONTOLOGY_DASHBOARD_NEO4J_PASSWORD
ONTOLOGY_DASHBOARD_PROJECT3_URL
ONTOLOGY_DASHBOARD_PROJECT3_PROJECT_MAP
```

### OIDC staging validation

```text
ONTOLOGY_DASHBOARD_OIDC_ISSUER
ONTOLOGY_DASHBOARD_OIDC_CLIENT_ID
ONTOLOGY_DASHBOARD_OIDC_CLIENT_SECRET
```

These variables are prerequisites for a future IdP adapter. The current local cookie identity implementation remains the verified MVP authentication path.

### Optional production connector selection

Configure only the protocol selected for the first customer vertical:

```text
ONTOLOGY_DASHBOARD_REST_CONNECTOR_URL
ONTOLOGY_DASHBOARD_KAFKA_BOOTSTRAP_SERVERS
ONTOLOGY_DASHBOARD_MQTT_URL
ONTOLOGY_DASHBOARD_OPCUA_URL
```

### Object storage and observability

```text
ONTOLOGY_DASHBOARD_OBJECT_STORAGE_ENDPOINT
ONTOLOGY_DASHBOARD_OBJECT_STORAGE_BUCKET
OTEL_EXPORTER_OTLP_ENDPOINT
```

## 3. Compose cold-start drill

Prerequisite: Docker Engine/Desktop and Compose v2.

```bash
docker compose -f infra/docker-compose.yml down -v --remove-orphans
docker compose -f infra/docker-compose.yml pull
docker compose -f infra/docker-compose.yml up -d

docker compose -f infra/docker-compose.yml ps
PYTHONPATH=api:ml/src .venv/bin/python scripts/release_gate.py --with-e2e
```

Acceptance evidence:

- PostgreSQL becomes healthy from an empty volume.
- all ordered migrations apply once and are idempotent on restart.
- Redis rate limiting uses shared state across at least two API instances.
- Neo4j is reachable with a non-default password and scoped database.
- Project 3 typed health, schema, graph and RAG routes are reachable.
- no service relies on the checked-in SQLite database.

## 4. Rollback drill

1. Record current migration version and application image tag.
2. Create a PostgreSQL backup and an object-storage manifest snapshot.
3. Deploy the next image and apply migrations.
4. Run the release gate and the live Project 3 hybrid gate.
5. Inject a controlled failure after one transactional write.
6. Roll back the application image.
7. Restore only when the migration is explicitly non-backward-compatible.
8. Verify Project, Dashboard, Action, Dataset, Analysis and Agent records by project scope.

Never run destructive rollback commands against an unlabelled database.

## 5. Managed PostgreSQL and Redis load evidence

Minimum staging scenario:

- two API instances
- one outbox worker
- 30 minutes steady load
- burst login, Dashboard query, Analysis run and Agent query traffic
- forced PostgreSQL connection interruption
- forced Redis interruption

Measure:

- pool wait and timeout rate
- transaction rollback rate
- outbox retry and dead-letter count
- rate-limit consistency between instances
- P50/P95/P99 latency
- cross-project isolation failures: target `0`
- lost or duplicated Action invocation: target `0`

## 6. Backup and restore

Required evidence:

- PostgreSQL logical or provider-native backup
- object-storage inventory and checksum manifest
- encryption and retention policy
- restore into a new environment
- application migration and release gate after restore
- tenant/project isolation verification after restore

The existing SQLite round-trip/tamper tests are regression evidence only; they do not replace a managed PostgreSQL restore drill.

## 7. Identity completion

Before external production users:

- choose OIDC provider and callback URLs
- map IdP subject to Organization and Project membership
- implement invitation, email verification and password-reset policy, or delegate them fully to the IdP
- validate logout, refresh, revocation and suspended membership
- decide MFA and SCIM requirements
- preserve project-level roles and self-lockout prevention

No IdP adapter should bypass the current server-side permission and project-scope checks.

## 8. Connector completion

Implement one protocol at a time. Every connector must provide:

- Project and Dataset identity
- credential reference, never embedded secret
- retry/backoff and circuit-break policy
- source checkpoint or offset
- idempotent replay
- schema compatibility decision
- invalid-record quarantine
- backpressure thresholds
- freshness and lineage metadata
- health and degraded state in Governance

Recommended sequence: REST, Kafka, MQTT, OPC-UA.

## 9. Object storage and observability

Object storage acceptance:

- immutable artifact key includes organization/project/dataset version
- checksum validated on write and read
- signed URL expiry and permission check
- retention and deletion audit

Observability acceptance:

- request ID and persisted run ID correlate API, worker and Project 3 calls
- structured logs exclude secrets and sensitive payloads
- OpenTelemetry traces cover Analysis and Agent checkpoints
- alerts exist for pool exhaustion, outbox dead letters, projection failure and Project 3 circuit open

## 10. Completion rule

An item moves from `blocked` to `verified` only when the command output, environment identifier, timestamp and resulting report are stored with the release evidence. Configuration files or unexecuted compose manifests alone are not completion evidence.
