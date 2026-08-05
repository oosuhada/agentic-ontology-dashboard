# Commercialization Baseline and Roadmap Freeze

- Schema: `commercialization-baseline/v1`
- Branch: `feature/predictive-maintenance-adaptive-modeling`
- HEAD: `a6f988ee0bd7a69bc16e2033fc8aff884a397dea`
- Commit time: `2026-08-06T02:05:40+09:00`
- Upstream: `origin/feature/predictive-maintenance-adaptive-modeling` (ahead 0, behind 0)
- Canonical current-state document: `docs/30-implementation/implementation-status.md`

## Version baseline

| Version | Route | Application identity | State |
|---|---|---|---|
| V1 | `/app/projects/manufacturing-demo-project` | Ontology Dashboard | implemented |
| V2 | `/app/projects/manufacturing-demo-project/blueprint` | Blueprint V1 | implemented |
| V3 | `/app/projects/manufacturing-demo-project/blueprint-v2` | Blueprint V2 | implemented |
| V4 | `/app/projects/manufacturing-demo-project/blueprint-v4` | Commercial V4 | not_implemented |

V1, V2 and V3 are immutable comparison/regression surfaces for this track. V4 promotion to the
default Project route requires an explicit later release decision and is never automatic.

## Measured checkout inventory

| Metric | Value |
|---|---:|
| Tracked files | 830 |
| Source files | 480 |
| Source lines | 105453 |
| Backend test files | 45 |
| Frontend unit test files | 14 |
| Frontend E2E specs | 33 |
| PostgreSQL migrations | 18 |
| SQLite migrations | 12 |
| Legacy namespace files | 0 |
| JavaScript total (built assets) | 3079.28 KiB |
| Largest JavaScript chunk | 492.73 KiB |
| CSS total (built assets) | 887.78 KiB |

Package-lock consistency: **PASS**.

## Verification snapshot

| Gate | State | Evidence |
|---|---|---|
| Backend pytest | pass | 264 passed / 1019 warnings |
| Frontend Vitest | pass | 36 tests |
| TypeScript | pass | `npm run lint` |
| Production build | pass | initial 308.72 KiB / 310 KiB |
| Documentation | pass | structure and local-link check |
| Deterministic generator | pass | rerun comparison |

## Production capability snapshot

| Capability | State | Blocking Phase | Evidence |
|---|---|---:|---|
| compose | blocked | 22 | docker: unknown command: docker compose  Run 'docker --help' for more information |
| postgresql | blocked | 20 | ONTOLOGY_DASHBOARD_DATABASE_URL is not configured |
| redis | blocked | 23 | ONTOLOGY_DASHBOARD_REDIS_URL is not configured |
| neo4j | blocked | 28 | Neo4j URI and credentials are not configured |
| project3 | blocked | 29 | ONTOLOGY_DASHBOARD_PROJECT3_URL is not configured |
| oidc | blocked | 21 | OIDC issuer, client ID or client secret is missing |
| connectors | blocked | 26 | no production connector endpoint is configured |
| object-storage | blocked | 24 | object storage endpoint or bucket is missing |
| observability | blocked | 25 | OTEL_EXPORTER_OTLP_ENDPOINT is not configured |

Passing local tests does not make a blocked external capability production-ready. A missing
credential, a missing managed service, and missing code are reported independently.

## Document freshness registry

| Document | State | Evidence |
|---|---|---|
| `README.md` | current | current checkout evidence |
| `docs/00-team-onboarding/06-implementation-status.md` | stale | branch claim 'prototype/ontology-dashboard-prebuild' differs from 'feature/predictive-maintenance-adaptive-modeling' |
| `docs/20-architecture/current-state/current-state.md` | stale | references removed compatibility namespace; describes legacy SQLite composition as current |
| `docs/30-implementation/implementation-status.md` | current | current checkout evidence |
| `docs/50-operations/release-gate-report.md` | current | current checkout evidence |
| `docs/50-operations/production-environment-completion-runbook.md` | current | current checkout evidence |

Historical documents remain available, but stale claims are not authoritative. The machine-readable
truth source is `docs/50-operations/commercialization-readiness.json`.

## Readiness interpretation

- Feature/demo/pilot/production/security/performance readiness are separate dimensions.
- Demo screen count is not a platform-maturity metric.
- Palantir-like visual styling is not the same as reusable Ontology, Action, Function, Branching,
  Lineage, Marking and Application runtime primitives.
- V4 starts as `not_implemented`; Phase 18 creates its independent composition while preserving
  V1 through V3.
