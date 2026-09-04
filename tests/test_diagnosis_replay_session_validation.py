from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.diagnosis.runtime_service import PredictiveMaintenanceRuntimeService


class ReplayValidationRepository:
    def __init__(
        self,
        *,
        state: str = "running",
        asset_exists: bool = True,
        row_overrides: dict[str, object] | None = None,
    ) -> None:
        now = datetime(2026, 8, 24, 6, 0, tzinfo=timezone.utc)
        self.row = {
            "id": "SESSION-001",
            "organization_id": "org-test",
            "project_id": "project-test",
            "workspace_id": "workspace-test",
            "dataset_id": "dataset-test",
            "dataset_version_id": "dataset-version-test",
            "created_by": "operator-test",
            "state": state,
            "simulation_time": now,
            "dataset_start": now,
            "dataset_end": now,
            "source_freshness_at": now,
            "speed_minutes_per_second": 1.0,
            "sequence": 1,
            "created_at": now,
            "updated_at": now,
        }
        self.row.update(row_overrides or {})
        self.asset_exists = asset_exists
        self.session_calls: list[dict[str, object]] = []
        self.asset_calls: list[dict[str, object]] = []

    def session(self, **values):
        self.session_calls.append(values)
        return dict(self.row)

    def asset_exists_in_version(self, **values):
        self.asset_calls.append(values)
        return self.asset_exists


class MissingReplaySessionRepository(ReplayValidationRepository):
    def session(self, **values):
        self.session_calls.append(values)
        raise KeyError(values["session_id"])


def _resolve(repository: ReplayValidationRepository) -> dict[str, str]:
    return PredictiveMaintenanceRuntimeService(repository).resolve_maintenance_replay_session(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        session_id="SESSION-001",
        equipment_id="CNC-001",
    )


@pytest.mark.parametrize("state", ["running", "paused"])
def test_resolve_maintenance_replay_session_returns_minimal_binding_without_advancing(
    state: str,
) -> None:
    repository = ReplayValidationRepository(state=state)

    binding = _resolve(repository)

    assert binding == {
        "organization_id": "org-test",
        "project_id": "project-test",
        "workspace_id": "workspace-test",
        "equipment_id": "CNC-001",
        "simulation_session_id": "SESSION-001",
    }
    assert repository.session_calls == [
        {
            "organization_id": "org-test",
            "project_id": "project-test",
            "workspace_id": "workspace-test",
            "session_id": "SESSION-001",
            "advance": False,
        }
    ]
    assert repository.asset_calls == [
        {
            "organization_id": "org-test",
            "project_id": "project-test",
            "workspace_id": "workspace-test",
            "dataset_version_id": "dataset-version-test",
            "asset_id": "CNC-001",
        }
    ]


@pytest.mark.parametrize("state", ["stopped", "completed"])
def test_resolve_maintenance_replay_session_rejects_ineligible_state(state: str) -> None:
    repository = ReplayValidationRepository(state=state)

    with pytest.raises(ValueError, match="not eligible"):
        _resolve(repository)

    assert repository.asset_calls == []


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("organization_id", "org-other", "scope"),
        ("project_id", "project-other", "scope"),
        ("workspace_id", "workspace-other", "scope"),
        ("id", "SESSION-OTHER", "canonical identity"),
    ],
)
def test_resolve_maintenance_replay_session_rejects_noncanonical_row(
    field: str,
    value: str,
    message: str,
) -> None:
    repository = ReplayValidationRepository(row_overrides={field: value})

    with pytest.raises(ValueError, match=message):
        _resolve(repository)

    assert repository.asset_calls == []


def test_resolve_maintenance_replay_session_rejects_missing_dataset_identity() -> None:
    repository = ReplayValidationRepository(row_overrides={"dataset_version_id": ""})

    with pytest.raises(ValueError, match="Dataset Version is missing"):
        _resolve(repository)

    assert repository.asset_calls == []


def test_resolve_maintenance_replay_session_rejects_equipment_outside_dataset() -> None:
    repository = ReplayValidationRepository(asset_exists=False)

    with pytest.raises(ValueError, match="not present"):
        _resolve(repository)


def test_resolve_maintenance_replay_session_preserves_not_found_failure() -> None:
    repository = MissingReplaySessionRepository()

    with pytest.raises(KeyError, match="SESSION-001"):
        _resolve(repository)

    assert repository.asset_calls == []


def test_resolve_maintenance_source_session_uses_product_result_lineage(
    monkeypatch,
) -> None:
    repository = ReplayValidationRepository()
    repository.result_artifact_row = lambda **_values: {
        "artifact_id": "RESULT-001",
        "dataset_version_id": "dataset-version-test",
    }
    service = PredictiveMaintenanceRuntimeService(repository)
    monkeypatch.setattr(service, "context", lambda **_values: object())
    monkeypatch.setattr(
        service,
        "_product_result",
        lambda **_values: SimpleNamespace(
            artifact_id="RESULT-001",
            asset_id="CNC-001",
            provenance=SimpleNamespace(simulation_session_id="local-realtime-001"),
        ),
    )

    binding = service.resolve_maintenance_source_session(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        source_product_result_id="RESULT-001",
        equipment_id="CNC-001",
    )

    assert binding == {
        "organization_id": "org-test",
        "project_id": "project-test",
        "workspace_id": "workspace-test",
        "equipment_id": "CNC-001",
        "simulation_session_id": "local-realtime-001",
    }


def test_resolve_maintenance_source_session_reports_missing_lineage(
    monkeypatch,
) -> None:
    repository = ReplayValidationRepository()
    repository.result_artifact_row = lambda **_values: {
        "artifact_id": "RESULT-001",
        "dataset_version_id": "dataset-version-test",
    }
    service = PredictiveMaintenanceRuntimeService(repository)
    monkeypatch.setattr(service, "context", lambda **_values: object())
    monkeypatch.setattr(
        service,
        "_product_result",
        lambda **_values: SimpleNamespace(
            artifact_id="RESULT-001",
            asset_id="CNC-001",
            provenance=SimpleNamespace(simulation_session_id=None),
        ),
    )

    assert (
        service.resolve_maintenance_source_session(
            organization_id="org-test",
            project_id="project-test",
            workspace_id="workspace-test",
            source_product_result_id="RESULT-001",
            equipment_id="CNC-001",
        )
        is None
    )


def test_post_maintenance_runtime_status_returns_receive_only_generator_state() -> None:
    repository = ReplayValidationRepository()
    repository.post_maintenance_runtime_status_row = lambda **_values: {
        "status": "history_insufficient",
        "failure_reason": None,
        "observed_at": "2026-09-04T03:40:00+00:00",
        "model_id": "cnc-random-forest",
        "model_version": "cnc-random-forest-v3",
        "lineage": {"maintenance_event_id": "MAINTENANCE-EVENT-1"},
        "received_at": datetime(2026, 9, 4, 3, 40, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 9, 4, 3, 40, tzinfo=timezone.utc),
    }

    status = PredictiveMaintenanceRuntimeService(
        repository
    ).post_maintenance_runtime_status(
        organization_id="org-test",
        project_id="project-test",
        workspace_id="workspace-test",
        asset_id="CNC-001",
        maintenance_event_id="MAINTENANCE-EVENT-1",
    )

    assert status is not None
    assert status["status"] == "history_insufficient"
    assert status["lineage"]["maintenance_event_id"] == "MAINTENANCE-EVENT-1"
