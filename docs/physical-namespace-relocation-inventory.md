# Physical Namespace Relocation Inventory

- Last updated: 2026-08-02
- Baseline HEAD inspected for the Dashboard slice: `c8fccb6`
- Canonical package: `api/ontology_dashboard/`
- Legacy compatibility path: removed

## Decision Gate

`scripts/verify_production_environment.py` reported Docker Compose as ready and PostgreSQL, Redis, Neo4j, Project 3, OIDC, production connectors, object storage, and OTLP as blocked because credentials or endpoints are not configured. The selected local work is therefore Phase 3 — Physical Namespace Relocation.

## Import graph findings

- `ontology_dashboard.__path__` now contains only `api/ontology_dashboard/`.
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
| Analysis | `analysis_models.py`, `analysis_repository.py`, `analysis_service.py` | same module names under `api/ontology_dashboard/` | durable run repository, cache identity, cursor/cancel/progress lifecycle and materialization service contract | complete; legacy files are thin re-export shims | analysis lifecycle, cache/cancel/cursor and materialization tests |
| Export/workflow | export and role-workflow model/repository/service files | same module names under `api/ontology_dashboard/` | outbox, workflow, export repositories, approvals and checkpoints | complete; legacy files are thin re-export shims | export, workflow, governance, isolation and outbox tests |
| Ontology/planner | ontology files plus conversation/LLM/report compatibility modules | canonical ontology/planner/orchestration boundaries | ontology repositories, registry constants, provider and legacy layout planner identity | complete | ontology, planner, Project 3 tests |
| Shim cleanup | all legacy re-export files | removed | no historical runtime package remains | complete | architecture guard and package build |
| Path extension removal | `ontology_dashboard.__path__` legacy extension | canonical package only | import provenance | complete | API boot, full tests, release gate |

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

During migration, matching files under `api/factory_signal_board/` were reduced to canonical re-exports. Final cleanup removed those source files entirely, and the architecture-debt guard now fails if any legacy Python source or package-discovery entry returns.

## Dashboard completion evidence

The following implementations now load from `api/ontology_dashboard/`:

```text
ontology_dashboard.dashboard_models
ontology_dashboard.dashboard_catalog
ontology_dashboard.dashboard_repository
ontology_dashboard.dashboard_service
```

The `BOARD_DEFINITION_BY_ID` catalog remains a single canonical module constant, `DashboardService` imports the same `DashboardRepository` class exposed by the repository module, and `PostgreSQLDashboardRepository` remains a subclass of that canonical repository class. The legacy files contain only canonical re-exports.

## Analysis completion evidence

The following implementations now load from `api/ontology_dashboard/`:

```text
ontology_dashboard.analysis_models
ontology_dashboard.analysis_repository
ontology_dashboard.analysis_service
```

`AnalysisService` imports the same canonical `AnalysisRepository` class exposed by the repository module. Durable run status, cache keys/hits, cursor pages, cancellation/progress checkpoints, Dataset materialization integration, and Project/Workspace predicates are unchanged. The legacy files contain only canonical re-exports.

## Export/workflow completion evidence

The following implementations now load from `api/ontology_dashboard/`:

```text
ontology_dashboard.export_models
ontology_dashboard.export_repository
ontology_dashboard.export_service
ontology_dashboard.role_workflow_models
ontology_dashboard.role_workflow_repository
ontology_dashboard.role_workflow_service
```

`ExportService` and `RoleWorkflowService` import the same canonical repository classes exposed by their repository modules. PostgreSQL export/workflow repositories remain subclasses of those canonical classes. Audit/export checkpoints, field actions, template/model approvals, transactional outbox writes, WorkOrder compatibility, and Project/Workspace predicates are unchanged.

## Ontology and final cleanup evidence

Ontology registry, adapter, action repository, service, conversation routing, report rendering and LLM provider implementations now load from `api/ontology_dashboard/`. The former layout planner implementation is represented by the canonical `ontology_dashboard.planner.layout` module, while the two historical ontology planner module paths are explicit canonical compatibility modules.

The `api/factory_signal_board/` directory, setuptools package discovery entry, and `ontology_dashboard.__path__` extension have been removed. Runtime package resolution now has one canonical directory and the architecture guard fails if the legacy package or path extension returns.

## Next slice

Phase 3 physical namespace relocation is complete. The next executable local work depends on approved full Azure/MetroPT source files; otherwise the next priority is a production environment runbook on a host with managed service credentials.
