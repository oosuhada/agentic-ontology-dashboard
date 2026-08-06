# Ontology Dashboard Implementation Status

- Last updated: 2026-08-02
- Current branch baseline: `main`
- Authoritative execution entrypoint: `docs/next-session-master-prompt.md`
- External operations runbook: `docs/production-environment-completion-runbook.md`

## Current maturity

```text
Backend        98%
Frontend       98%
Architecture   97%
PostgreSQL     88%
Project Layer  96%
Adapter Layer  84%
```

These percentages measure implementation, automated verification and operational evidence against the target architecture. They do not claim that managed infrastructure, external identity or production protocol credentials are available.

## User-visible product surface

```text
Project Home  CONNECTED
Dashboards    CONNECTED / SERVER-FIRST CROSS-FILTER
Analysis      CONNECTED / JOB LIFECYCLE / MATERIALIZATION
Agent         CONNECTED EVIDENCE WORKBENCH
Ontology      CONNECTED WORKBENCH / DEGRADED GRAPH SAFE
Datasets      CONNECTED CATALOG / DEFAULT NAVIGATION ENABLED
Governance    CONNECTED PROJECT WORKBENCH
Admin         CONNECTED MEMBERSHIP / APPROVAL CONTROL PLANE
```

### Newly completed product hardening

- Dataset Catalog is enabled in the default Product Navigation and no longer appears as `SOON`.
- archived Project deep links render a dedicated tombstone instead of silently switching resource context.
- Dashboard editing supports undo, redo, keyboard shortcuts, autosaved local recovery, reload recovery and unsaved navigation warnings.
- Azure Fleet Maintenance and MetroPT Compressor Projects contain project-scoped governed showcase events and Evidence lineage.
- Azure and MetroPT remain read-only for operational Actions until project-specific Action mappings are published.
- all primary Workbench routes pass automated accessible-name, single-main-landmark, duplicate-ID and 720px viewport overflow checks.
- Dashboard cross-filtering is server-first with explicit client fallback state.

## Project showcase state

| Project | Current runtime state | Evidence |
|---|---|---|
| Manufacturing Demo | Full regression baseline with governed Actions | Gold GS-001..GS-008, role workflows and E2E |
| Azure Fleet Maintenance | Project-scoped showcase Dashboard with critical and warning Events | AZ-001/AZ-002 fixtures, Evidence lineage and Project-switch E2E |
| MetroPT Compressor | Project-scoped compressor warning Dashboard | MPT-001 fixture, server table, Evidence lineage and E2E |

The Azure and MetroPT fixtures prove multi-project abstraction and user flow. They are not a substitute for ingesting the complete public datasets. Full Azure five-file ingestion and high-density MetroPT ingestion still require approved source files and provenance review.

## Backend

### Implemented

- canonical FastAPI composition root at `ontology_dashboard.main`
- compatibility-only `factory_signal_board.main` shim
- application factory and feature routers
- cookie authentication, Argon2id, CSRF, session rotation/revocation and RBAC
- Organization → Project → Workspace → Role hierarchy
- project memberships, project-specific roles, active Project persistence and self-lockout protection
- Project-scoped Dashboard, Action, Workflow, Export and Dataset records
- repository project-isolation matrix for Dashboard preferences, Ontology Action, Workflow and Export
- persistent Ontology object/link/action runtime
- Dataset Version, projection, quarantine, materialization and reusable Analysis input
- Analysis queued/running/progress/cancel/cache/cursor lifecycle
- checkpointed multi-store Agent orchestration and persisted evidence/trace
- typed Project 3 boundary without raw Cypher execution
- PostgreSQL repository graph for Identity, Project, Dashboard, Audit, Action, Workflow, Export, Adapter and Prediction Result
- migration, RLS, connection pool, outbox retry/dead-letter and ephemeral PostgreSQL runtime checks

### Remaining local architecture debt

- import graph inventory plus the foundation/identity, Dashboard, Analysis, and Export/Workflow compatibility slices are complete
- `context`, `contracts`, `security`, identity models/repository/service, audit repository, and the manufacturing demo service now load physically from `api/ontology_dashboard/`
- Dashboard models, catalog, repository, and service now load physically from `api/ontology_dashboard/`; catalog and repository class identity are guarded by executable architecture tests
- Analysis models, durable run repository, and service now load physically from `api/ontology_dashboard/`; cache/cancel/cursor/materialization contracts and repository class identity are guarded by tests
- Export and Role Workflow models, repositories, and services now load physically from `api/ontology_dashboard/`; PostgreSQL subclass, outbox, checkpoint, approval and project-isolation contracts are guarded by tests
- matching legacy files are thin re-export shims guarded by executable architecture tests
- the remaining Ontology/provider/report/conversation compatibility slice still depends on the temporary `ontology_dashboard.__path__` extension
- the namespace path extension is removed only after all remaining service/model/repository modules are relocated and package/runtime verification passes

### Externally blocked backend work

- managed PostgreSQL backup/restore and failover drill
- long-duration pool and outbox worker load test
- distributed Redis rate-limit test across multiple API instances
- production OIDC/IdP lifecycle
- live production connector credentials

## Frontend

### Implemented

- role-aware product shell and Project/Workspace/Role selectors
- Project Home, Dashboard, Analysis, Agent, Ontology, Datasets and Governance navigation
- project tombstone and permission fallback routes
- Dashboard editor with grid persistence, mandatory-board protection, undo/redo and recovery
- saved views, shares and exports
- server pagination and cross-filter state
- Analysis vertical authoring path with grouped board palette, connector insertion, board I/O contracts and Config/Result/Quality/Lineage/Runtime inspector tabs
- Object Explorer with dense Object Set table, Table/Explore/Graph modes, Properties/Links/Actions/Lineage inspector and scoped Ask drawer
- Agent grounded-evidence terminal with persisted run history, bottom composer and Evidence/Claims/Checkpoints/Trace inspector tabs
- Dataset Catalog dense resource table with immutable Version, Schema, Profile, Files, Lineage and Projection detail tabs
- Governance checkpoint browser with compact KPI strip, projection/approval record tables and persistent entity inspectors
- Dataset Catalog and Analysis materialization flow
- Governance trace/evidence/projection retry
- fixed light-theme Palantir comparison screenshots and side-by-side comparison sheet
- Palantir-inspired UI overhaul UI-00 through UI-04: token system, shared 48px/208px product rail, 40px global topbar, Dashboard resource chrome and shared board runtime primitives
- shared Foundry-style shell for Project Home, Agent, Ontology, Datasets and Governance, plus matching dense Admin control-plane styling
- reusable EntityTitle, StatusPill, WorkbenchHeader/Toolbar, BoardFrame, MetricStrip, DenseDataTable, ChartPanel and explicit Empty/Loading/Error states
- 24 pre-overhaul screenshots restored from starting SHA, 24 UI-04 intermediate screenshots and 24 final UI-08 screenshots across 1440x1000, 1728x1117 and 720x500
- dedicated 48-image baseline/final manifest with SHA-256 integrity, same-platform raw-pixel thresholds and cross-platform blurred structural thresholds
- Playwright candidate capture and GitHub Actions release-gate integration for visual regression
- Ubuntu candidate, runner/font metadata and release report upload with a 30-day CI artifact
- Ubuntu 24.04 calibration at 1.5436% observed structural delta and a 2.4% cross-platform ceiling
- opt-in baseline/final approval capture protection and updated comparison-sheet manifest
- initial/deferred JavaScript budget gate
- mobile field flow and primary Workbench accessibility/viewport gate

### Remaining

- real customer connector setup screens after the first protocol is selected

## PostgreSQL and project isolation

The active Python repository graph is already wired for PostgreSQL. The remaining work is operational evidence, not first-time repository implementation.

Verified locally or ephemerally:

- ordered migrations and idempotency
- RLS creation and non-superuser Organization/Project denial
- pooled project context
- Identity and active Project session
- Dashboard template resolution
- Audit and Ontology Action writes
- Workflow and transactional outbox
- Export checkpoint
- Adapter manifest and Prediction Result
- Dataset, Analysis and Agent project-aware repositories
- SQLite project-isolation matrix for Dashboard, Action, Workflow and Export

Still requiring an external environment:

- managed service credentials
- failover and recovery-time evidence
- long-duration concurrency and pool exhaustion
- multi-instance Redis consistency
- production backup restoration into a new environment

## Adapter and connector layer

### Implemented

- adapter protocol and registry
- Dataset Manifest and Prediction Result contracts
- CSV, JSON, JSONL and Parquet file ingestion
- checksums, immutable versions, quarantine and schema/profile data
- Azure and MetroPT file adapters and contract fixtures
- project-scoped showcase events with Dataset Version lineage

### Externally blocked

- complete Azure public dataset five-file ingestion
- complete MetroPT high-density time-series ingestion
- production REST/Kafka/MQTT/OPC-UA endpoints and credentials
- streaming checkpoint, backpressure and replay load evidence

## Production environment status

Run:

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/verify_production_environment.py
```

On the current host the verifier reports Docker, managed PostgreSQL, Redis, Neo4j credentials, Project 3 URL, OIDC, production connectors, object storage and OTLP as `blocked`. This is an environment fact, not a hidden test failure.

Strict staging example:

```bash
PYTHONPATH=api:ml/src .venv/bin/python scripts/verify_production_environment.py \
  --strict --require compose --require postgresql --require redis --require neo4j --require project3
```

## Current test baseline

Verified on 2026-08-02:

```text
Canonical naming                          PASS
Architecture debt guard                  PASS
PostgreSQL migration/RLS/runtime         PASS
Backend pytest                           122 PASS
Gold scenarios                           8/8 PASS
Frontend Vitest                          6 PASS
TypeScript                               PASS
Production build                         PASS
Initial JavaScript                       228.07 KiB / 300 KiB PASS
Largest deferred JavaScript              443.24 KiB / 500 KiB PASS
Playwright E2E                           49 PASS / 3 INTENTIONAL SKIP
Final overhaul acceptance                8 PASS
Baseline capture guard                   3 SKIPPED BY DEFAULT
Primary Workbench accessibility          PASS
Legacy comparison manifest               PASS
48-image committed visual manifest       PASS
Latest macOS candidate raw pixel max     0.0877% / 0.15% PASS
Latest macOS changed pixels max          0.2939% / 0.75% PASS
Latest macOS structural delta max        0.0611% / 0.10% PASS
Ubuntu structural delta max              1.5436% / 2.4% PASS
Ubuntu release gate                      16/16 PASS
Production environment verifier          BLOCKED EXTERNAL CAPABILITIES REPORTED
```

## Remaining priority order

```text
1. Run the production-environment runbook on a Docker/managed-service host.
2. On the current blocked host, relocate the remaining physical legacy modules and remove the namespace path extension.
3. Ingest approved complete Azure and MetroPT datasets with provenance artifacts.
4. Select and productionize one external connector, starting with REST.
5. Implement the selected IdP integration and invitation/reset policy.
6. Add S3-compatible artifact storage and OpenTelemetry-backed observability.
```

Do not repeat already completed Workbench, pagination, Analysis lifecycle, WorkOrder, Dataset materialization, Project 3 typed boundary, Dashboard recovery or server-first cross-filter work.

The next physical relocation slice is Dashboard. The detailed import matrix and compatibility status are recorded in `docs/physical-namespace-relocation-inventory.md`.
