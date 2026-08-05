from __future__ import annotations

from pathlib import Path

from ontology_dashboard.migrations import migrate, migration_status
from ontology_dashboard.ontology_repository import OntologyActionRepository
from ontology_dashboard.persistence_readiness import (
    persistence_readiness,
    verify_rls_migration_evidence,
)
from ontology_dashboard.projects import ProjectRepository


ROOT = Path(__file__).resolve().parents[1]


def test_phase20_additive_migration_and_recovery_state(tmp_path: Path) -> None:
    database = tmp_path / "phase20.db"
    migrate(str(database))
    assert "0019_tenant_transaction_convergence" in migration_status(str(database))["available"]
    ProjectRepository(database)
    repository = OntologyActionRepository(database)
    invocation, created = repository.reserve(
        idempotency_key="phase20-recovery",
        workspace_id="manufacturing-demo",
        action_type="request_inspection",
        object_id="risk-event:phase20",
        actor_user_id="user-manager",
        actor_display_name="Manager",
        request_hash="a" * 64,
        request={"decision": "inspect"},
    )
    assert created is True
    assert invocation["recovery_state"] == "none"
    repository.fail(
        invocation["id"],
        project_id="manufacturing-demo-project",
        code="external_timeout",
        message="retry later",
    )
    failed = repository.find_by_idempotency_key(
        workspace_id="manufacturing-demo",
        actor_user_id="user-manager",
        idempotency_key="phase20-recovery",
    )
    assert failed is not None
    assert failed["state"] == "failed"
    assert failed["recovery_state"] == "retryable"
    assert failed["attempt_count"] == 1
    reconciled = repository.mark_recovery_state(
        invocation["id"],
        project_id="manufacturing-demo-project",
        recovery_state="reconciled",
    )
    assert reconciled["recovery_state"] == "reconciled"


def test_rls_source_matrix_and_local_blocked_semantics() -> None:
    evidence = verify_rls_migration_evidence(ROOT)
    assert evidence["pass"] is True
    assert evidence["covered_tables"] >= 35
    readiness = persistence_readiness("/tmp/pilot.sqlite", app_env="development")
    assert readiness.state == "blocked"
    assert readiness.active_database == "sqlite"
    assert readiness.production_fail_fast is True
    assert all(group.state == "covered" for group in readiness.rls_coverage)


def test_postgresql_runtime_is_reported_as_ready_without_sqlite_fallback() -> None:
    readiness = persistence_readiness(
        "postgresql://ontology_app@db.example/ontology",
        app_env="production",
    )
    assert readiness.state == "ready"
    assert readiness.active_database == "postgresql"
    assert readiness.blockers == ()
    assert readiness.identity_repository == "PostgreSQLIdentityRepository"
