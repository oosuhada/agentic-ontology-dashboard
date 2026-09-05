from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.diagnosis.runtime_service import PredictiveMaintenanceRuntimeService


class _RiskIndexRepository:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 5, 8, 30, tzinfo=timezone.utc)
        self.live_observed_at = datetime(2026, 9, 5, 8, 20, tzinfo=timezone.utc)
        self.workspace_observed_at = datetime(2026, 9, 3, 18, 50, tzinfo=timezone.utc)
        self.calls: list[dict[str, object]] = []

    def clock_now(self) -> datetime:
        return self.now

    def latest_wall_clock_live_version(self, **_scope):
        return {
            "id": "dsv-live",
            "dataset_id": "dataset-live",
            "dataset_name": "Live Generator",
            "source_version": "gen-data-wall-clock-live-v2",
            "latest_result_observed_at": self.live_observed_at,
        }

    def resolve_version(self, **_scope):
        return {
            "id": "dsv-pinned",
            "dataset_id": "dataset-pinned",
            "dataset_name": "Pinned Analysis",
            "source_version": "gen-data-wall-clock-live-v2",
            "latest_result_observed_at": self.workspace_observed_at,
        }

    def risk_index_rows(self, **query):
        self.calls.append(query)
        end = query["end"]
        return [
            {
                "observed_at": end,
                "risk_value": 0.81,
                "mean_risk": 0.22,
                "max_risk": 0.91,
                "sample_count": 100,
                "asset_count": 88,
                "critical_count": 4,
            }
        ]


def _service() -> tuple[PredictiveMaintenanceRuntimeService, _RiskIndexRepository]:
    repository = _RiskIndexRepository()
    service = PredictiveMaintenanceRuntimeService(repository)
    service.versions = lambda **_scope: SimpleNamespace(  # type: ignore[method-assign]
        default_dataset_version_id="dsv-pinned",
        selection_mode="explicit",
        selection_reason="explicit_user_selection",
    )
    return service, repository


def test_live_risk_index_uses_generator_dataset_even_when_workspace_is_pinned() -> None:
    service, repository = _service()

    result = service.risk_index(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        user_id="user-1",
        source_mode="live",
        workspace_dataset_version_id="dsv-pinned",
        asset_id=None,
        window="24h",
    )

    assert result["scope"] == "plant"
    assert result["dataset_version_id"] == "dsv-live"
    assert result["live_dataset_version_id"] == "dsv-live"
    assert result["workspace_dataset_version_id"] == "dsv-pinned"
    assert result["workspace_is_pinned"] is True
    assert result["aggregation"] == "plant_failure_probability_p95"
    assert result["point_count"] == 1
    assert result["points"][0]["status"] == "critical"
    assert result["data_age_seconds"] == 600
    assert repository.calls[0]["dataset_version_id"] == "dsv-live"


def test_workspace_asset_risk_index_keeps_the_explicit_dataset_and_real_range() -> None:
    service, repository = _service()

    result = service.risk_index(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        user_id="user-1",
        source_mode="workspace",
        workspace_dataset_version_id="dsv-pinned",
        asset_id="CNC-S04-L02-03",
        window="6h",
    )

    assert result["scope"] == "asset"
    assert result["dataset_version_id"] == "dsv-pinned"
    assert result["aggregation"] == "asset_bucket_mean"
    assert repository.calls[0]["asset_id"] == "CNC-S04-L02-03"
    assert repository.calls[0]["end"] == repository.workspace_observed_at
    assert (
        repository.calls[0]["end"] - repository.calls[0]["start"]
    ).total_seconds() == 6 * 60 * 60
