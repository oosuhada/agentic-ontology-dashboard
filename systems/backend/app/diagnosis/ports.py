from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, Sequence

from app.dataset.dataset_domain import ObservationDatasetQuery
from app.equipment.equipment_schema import EquipmentCurrentStateQuery

from .diagnosis_schema import PredictionResult


ALLOWED_DERIVED_MEASURES = {
    "power_w",
    "temperature_gap_k",
    "overstrain_load",
}


class DiagnosisRuntimeRepositoryPort(Protocol):
    """Persistence/query boundary required by the Diagnosis runtime service."""

    def clock_now(self) -> datetime: ...
    def resolve_version(self, **kwargs: Any) -> dict[str, Any]: ...
    def list_versions(self, **kwargs: Any) -> list[dict[str, Any]]: ...
    def selected_version_for_user(self, **kwargs: Any) -> str | None: ...
    def save_selected_version(self, **kwargs: Any) -> None: ...
    def latest_result_rows(self, **kwargs: Any) -> list[dict[str, Any]]: ...
    def result_artifact_row(self, **kwargs: Any) -> dict[str, Any] | None: ...
    def snapshot_drilldown(self, **kwargs: Any) -> dict[str, Any] | None: ...
    def timeline_rows(self, **kwargs: Any) -> list[dict[str, Any]]: ...
    def result_history_rows(self, **kwargs: Any) -> list[dict[str, Any]]: ...
    def observation_bounds(self, **kwargs: Any) -> tuple[datetime, datetime]: ...
    def observation_rows(self, **kwargs: Any) -> list[dict[str, Any]]: ...
    def nearest_timeline_rows(self, **kwargs: Any) -> list[dict[str, Any]]: ...
    def nearest_sensor_time(self, **kwargs: Any) -> datetime | None: ...
    def observations_at(self, **kwargs: Any) -> list[dict[str, Any]]: ...
    def latest_artifact_references(self, **kwargs: Any) -> list[dict[str, Any]]: ...
    def dashboard_support_rows(self, **kwargs: Any) -> dict[str, Any]: ...
    def create_session(self, **kwargs: Any) -> dict[str, Any]: ...
    def session(self, **kwargs: Any) -> dict[str, Any] | None: ...
    def asset_exists_in_version(self, **kwargs: Any) -> bool: ...
    def assets_exist_in_workspace(self, **kwargs: Any) -> set[str]: ...
    def save_prediction_batch_inbox(self, **kwargs: Any) -> dict[str, Any]: ...
    def prediction_batch_promotion_context(self, **kwargs: Any) -> dict[str, Any] | None: ...
    def save_prediction_batch_promotions(self, **kwargs: Any) -> dict[str, Any]: ...
    def update_session(self, **kwargs: Any) -> dict[str, Any]: ...


class EventEvidenceProjectionQueryPort(Protocol):
    """Diagnosis-owned public query used by authorized downstream workflows."""

    def event_evidence_projection(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        event_id: str,
    ) -> dict[str, Any] | None: ...


class ContextProvider(Protocol):
    """Maintenance-context boundary used while building diagnosis evidence."""

    provider_name: str

    def get_context(
        self,
        equipment_id: str,
        failure_type: str,
    ) -> dict[str, Any] | None: ...


class PredictionResultRepositoryPort(Protocol):
    """Persistence contract matching the migrated prediction repository API.

    ``save``/``list`` expose scoped persistence summary rows for the existing
    adapter surface, while ``get_payload`` returns the canonical Diagnosis
    product-result model.
    """

    def save(self, result: PredictionResult) -> dict[str, Any]: ...
    def get_payload(
        self,
        *,
        organization_id: str,
        project_id: str,
        prediction_id: str,
    ) -> PredictionResult | None: ...
    def list(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str | None = None,
        limit: int = 100,
    ) -> Sequence[dict[str, Any]]: ...


class LiveDiagnosisApplicationPort(Protocol):
    def materialize_live_results(self, batch: dict[str, Any]) -> dict[str, Any]: ...


# Compatibility names retained for Diagnosis consumers, but the contracts are
# owned by the provider domains. Re-exporting the canonical public protocols
# prevents the same Dataset/Equipment boundary from drifting into two shapes.
EquipmentSnapshotQueryPort = EquipmentCurrentStateQuery
ObservationDatasetQueryPort = ObservationDatasetQuery


__all__ = [
    "ALLOWED_DERIVED_MEASURES",
    "ContextProvider",
    "DiagnosisRuntimeRepositoryPort",
    "EventEvidenceProjectionQueryPort",
    "LiveDiagnosisApplicationPort",
    "EquipmentSnapshotQueryPort",
    "ObservationDatasetQueryPort",
    "PredictionResultRepositoryPort",
]
