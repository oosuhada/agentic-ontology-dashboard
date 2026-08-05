"""Production persistence and tenant-isolation readiness evidence."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .postgresql_repositories import is_postgresql


ReadinessState = Literal["ready", "blocked", "degraded"]


class RLSCoverageGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: str
    tables: tuple[str, ...]
    scope: Literal["organization", "project", "global"]
    operations: tuple[Literal["select", "insert", "update", "delete"], ...]
    migration: str
    state: Literal["covered", "not_applicable"]


class PersistenceReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: ReadinessState
    canonical_database: Literal["postgresql"] = "postgresql"
    active_database: Literal["postgresql", "sqlite"]
    production_fail_fast: bool
    identity_repository: str
    rls_scope_binding: str
    identity_bypass: str
    transaction_boundary: tuple[str, ...]
    action_recovery_states: tuple[str, ...]
    rls_coverage: tuple[RLSCoverageGroup, ...]
    pool: dict[str, int | float]
    blockers: tuple[str, ...]


RLS_COVERAGE = (
    RLSCoverageGroup(
        category="identity",
        tables=(
            "users", "password_credentials", "user_roles", "sessions",
            "user_permission_overrides", "user_display_preferences",
        ),
        scope="organization",
        operations=("select", "insert", "update", "delete"),
        migration="0003_operational_project_scope + 0015_identity_permission_overrides",
        state="covered",
    ),
    RLSCoverageGroup(
        category="project",
        tables=("projects", "workspaces", "project_memberships", "project_membership_roles"),
        scope="project",
        operations=("select", "insert", "update", "delete"),
        migration="0002_project_layer + 0005_project_memberships",
        state="covered",
    ),
    RLSCoverageGroup(
        category="dataset",
        tables=(
            "datasets", "dataset_versions", "dataset_files", "ontology_mappings",
            "store_projections", "materializations", "vector_document_chunks",
        ),
        scope="project",
        operations=("select", "insert", "update", "delete"),
        migration="0008_dataset_projection_pipeline",
        state="covered",
    ),
    RLSCoverageGroup(
        category="ontology-action",
        tables=("ontology_objects", "ontology_links", "ontology_action_invocations"),
        scope="project",
        operations=("select", "insert", "update", "delete"),
        migration="0001_platform_core + 0003_operational_project_scope + 0019_tenant_transaction_convergence",
        state="covered",
    ),
    RLSCoverageGroup(
        category="analysis-dashboard",
        tables=(
            "analysis_definitions", "analysis_runs", "dashboard_templates",
            "dashboard_saved_views", "dashboard_shares", "export_checkpoints",
        ),
        scope="project",
        operations=("select", "insert", "update", "delete"),
        migration="0003_operational_project_scope + 0007_analysis_engine",
        state="covered",
    ),
    RLSCoverageGroup(
        category="agent-model-governance",
        tables=(
            "agent_runs", "agent_checkpoints", "agent_traces",
            "modeling_intake_profiles", "modeling_model_versions",
            "modeling_model_release_requests",
        ),
        scope="project",
        operations=("select", "insert", "update", "delete"),
        migration="0009_agent_orchestration + 0016_adaptive_modeling_foundation + 0017_adaptive_model_registry",
        state="covered",
    ),
    RLSCoverageGroup(
        category="outbox-audit",
        tables=("transactional_outbox", "outbox_delivery_log", "audit_log"),
        scope="project",
        operations=("select", "insert", "update", "delete"),
        migration="0001_platform_core + 0003_operational_project_scope + 0006_outbox_worker",
        state="covered",
    ),
)


def persistence_readiness(database_target: str, *, app_env: str | None = None) -> PersistenceReadiness:
    environment = (app_env or os.getenv("APP_ENV", "development")).strip().lower()
    postgresql = is_postgresql(database_target)
    blockers: list[str] = []
    if not postgresql:
        blockers.append("Production PostgreSQL URL is not configured; SQLite remains pilot-only.")
    if environment == "production" and not postgresql:
        blockers.append("Production startup must fail before serving requests without PostgreSQL.")
    return PersistenceReadiness(
        state="ready" if postgresql else "blocked",
        active_database="postgresql" if postgresql else "sqlite",
        production_fail_fast=True,
        identity_repository=(
            "PostgreSQLIdentityRepository" if postgresql else "IdentityRepository (pilot SQLite)"
        ),
        rls_scope_binding="transaction-local app.organization_id + app.project_id",
        identity_bypass="transaction-local app.identity_access through narrow identity repository only",
        transaction_boundary=(
            "reserve Action invocation",
            "write domain state",
            "append audit event",
            "enqueue transactional outbox",
            "commit once; deliver external side effect after commit",
        ),
        action_recovery_states=(
            "none", "retryable", "compensation_required", "reconciled", "dead_letter",
        ),
        rls_coverage=RLS_COVERAGE,
        pool={
            "min_size": max(1, int(os.getenv("ONTOLOGY_DASHBOARD_DB_POOL_MIN", "1"))),
            "max_size": max(1, int(os.getenv("ONTOLOGY_DASHBOARD_DB_POOL_MAX", "10"))),
            "timeout_seconds": max(1.0, float(os.getenv("ONTOLOGY_DASHBOARD_DB_POOL_TIMEOUT", "10"))),
        },
        blockers=tuple(blockers),
    )


def verify_rls_migration_evidence(root: Path) -> dict[str, object]:
    migration_root = root / "api/migrations/postgresql"
    available = {path.stem for path in migration_root.glob("*.sql")}
    required = {
        "0001_platform_core",
        "0002_project_layer",
        "0003_operational_project_scope",
        "0005_project_memberships",
        "0006_outbox_worker",
        "0007_analysis_engine",
        "0008_dataset_projection_pipeline",
        "0009_agent_orchestration",
        "0015_identity_permission_overrides",
        "0016_adaptive_modeling_foundation",
        "0017_adaptive_model_registry",
        "0019_tenant_transaction_convergence",
    }
    missing = sorted(required - available)
    return {
        "pass": not missing,
        "required_migrations": sorted(required),
        "missing_migrations": missing,
        "coverage_groups": len(RLS_COVERAGE),
        "covered_tables": sum(len(group.tables) for group in RLS_COVERAGE),
    }
