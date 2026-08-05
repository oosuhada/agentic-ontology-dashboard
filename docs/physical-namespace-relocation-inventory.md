# Physical Namespace Relocation Inventory

- Last updated: 2026-08-02
- Baseline HEAD inspected for the Dashboard slice: `c8fccb6`
- Canonical package: `api/ontology_dashboard/`
- Temporary compatibility path: `api/factory_signal_board/`

## Decision Gate

`scripts/verify_production_environment.py` reported Docker Compose as ready and PostgreSQL, Redis, Neo4j, Project 3, OIDC, production connectors, object storage, and OTLP as blocked because credentials or endpoints are not configured. The selected local work is therefore Phase 3 — Physical Namespace Relocation.

## Import graph findings

- `ontology_dashboard.__path__` still extends into `api/factory_signal_board/`.
- The canonical FastAPI composition root and planner package are already physically canonical.
- Foundation and identity imports are consumed by the composition root, PostgreSQL repositories, projects, adapters, tests, and scripts.
- Dashboard models, catalog constants, repository cache, and service are consumed by routers, planner, PostgreSQL repositories, exports, workflows, tests, and runtime verification scripts.
- `IdentityService`, `IdentityRepository`, and the application service are instantiated by dependency composition; no module-level repository singleton is created by this slice.
- Runtime singleton identity is preserved by moving implementations first and reducing legacy files to import-only re-exports.

## Migration matrix

| Slice | Legacy implementation | Canonical destination | Stateful boundary | Compatibility state | Verification |
|---|---|---|---|---|---|
| Inventory | all remaining modules | this document and architecture guard | import graph and package path | complete | source/import inventory |
| Foundation/identity | `context.py`, `contracts.py`, `security.py`, `identity_models.py`, `identity_repository.py`, `identity.py`, `repository.py`, `service.py` | same module names under `api/ontology_dashboard/` | identity repository and application service instances | complete; legacy files are thin re-export shims | auth, tenant, Project, persistence, architecture tests |
| Dashboard | `dashboard_models.py`, `dashboard_catalog.py`, `dashboard_repository.py`, `dashboard_service.py` | same module names under `api/ontology_dashboard/` | repository cache, catalog constant identity, PostgreSQL subclass and template resolution | complete; legacy files are thin re-export shims | dashboard, Project, isolation, export and workflow tests |
| Analysis | `analysis_models.py`, `analysis_repository.py`, `analysis_service.py` | compatibility-preserving canonical module layout, then package consolidation if justified | durable run repository and cache identity | next | analysis lifecycle and materialization tests |
| Export/workflow | export and role-workflow model/repository/service files | `ontology_dashboard.exports` and `ontology_dashboard.workflows` | outbox, workflow, export repositories | pending | export, workflow, outbox tests |
| Ontology/planner | ontology files plus conversation/LLM compatibility modules | canonical ontology/planner/orchestration boundaries | ontology repositories and registry constants | planner complete; ontology remainder pending | ontology, planner, Project 3 tests |
| Shim cleanup | all legacy re-export files | none | no business logic allowed | pending until all consumers are canonical | architecture guard and package build |
| Path extension removal | `ontology_dashboard.__path__` legacy extension | canonical package only | import provenance | pending final slice | API boot, full tests, release gate |

## Foundation/identity completion evidence

The following implementations now load from `api/ontology_dashboard/`:

```text
ontology_dashboard.context
ontology_dashboard.contracts
ontology_dashboard.security
ontology_dashboard.identity_models
ontology_dashboard.identity_repository
ontology_dashboard.identity
ontology_dashboard.repository
ontology_dashboard.service
```

The matching files under `api/factory_signal_board/` contain only a deprecation docstring and a canonical re-export. The architecture-debt guard fails if any of these canonical files disappears or if a legacy file grows beyond that re-export.

## Dashboard completion evidence

The following implementations now load from `api/ontology_dashboard/`:

```text
ontology_dashboard.dashboard_models
ontology_dashboard.dashboard_catalog
ontology_dashboard.dashboard_repository
ontology_dashboard.dashboard_service
```

The `BOARD_DEFINITION_BY_ID` catalog remains a single canonical module constant, `DashboardService` imports the same `DashboardRepository` class exposed by the repository module, and `PostgreSQLDashboardRepository` remains a subclass of that canonical repository class. The legacy files contain only canonical re-exports.

## Next slice

Move the Analysis models, repository, and service as the next compatibility slice. Preserve durable run state, cache identity, cursor pagination, cancellation/progress checkpoints, immutable Dataset Version materialization, and Project/Workspace scope. Do not remove the package path extension until every remaining slice is canonical.
