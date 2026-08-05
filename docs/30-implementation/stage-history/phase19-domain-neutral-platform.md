# Phase 19 — Canonical Modularization and Domain Neutrality

- Canonical Python namespace: `ontology_dashboard`
- Domain-pack registry: `api/ontology_dashboard/domain_packs/`
- V4 definition API: `/api/platform/projects/{project_id}/applications/v4`

The platform now resolves Project metadata to a typed domain-pack definition. The predictive
maintenance implementation is the first vertical pack rather than an implicit platform namespace.
Unknown packs fail safely to `generic-operations`, while the persisted `predictive-maintenance`
alias resolves to the canonical `manufacturing-predictive-maintenance` definition without changing
existing Project records.

V4 renders bounded contexts and namespace provenance from the API. V1 through V3 keep their
existing components, routes and terminology.
