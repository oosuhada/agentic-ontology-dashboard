from __future__ import annotations

import pytest

from app import dependencies


def test_maintenance_service_uses_diagnosis_runtime_for_replay_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = object()
    project_context = object()
    diagnosis_runtime = object()
    runtime_calls: list[None] = []

    dependencies.get_maintenance_loop_service.cache_clear()
    monkeypatch.setattr(dependencies, "ensure_database_migrations", lambda: None)
    monkeypatch.setattr(dependencies, "database_target", lambda: "maintenance-test.sqlite3")
    monkeypatch.setattr(dependencies, "is_postgresql", lambda _target: False)
    monkeypatch.setattr(
        dependencies,
        "RuntimeProjectContextResolver",
        lambda _target: project_context,
    )
    monkeypatch.setattr(
        dependencies,
        "MaintenanceRepository",
        lambda _target, *, project_context: repository,
    )

    def runtime_service():
        runtime_calls.append(None)
        return diagnosis_runtime

    monkeypatch.setattr(
        dependencies,
        "get_predictive_maintenance_runtime_service",
        runtime_service,
    )

    try:
        service = dependencies.get_maintenance_loop_service()
    finally:
        dependencies.get_maintenance_loop_service.cache_clear()

    assert service.repository is repository
    assert service.event_evidence_query.runtime is diagnosis_runtime
    assert service.replay_session_query is diagnosis_runtime
    assert runtime_calls == [None]
