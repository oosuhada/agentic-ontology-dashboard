from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, Sequence

from .cost_analysis_schema import MaintenanceCostScenarioResult
from .cost_basis import (
    CoolingSystemRestoreCostBasis,
    CostBasisResolutionContext,
    ToolReplacementCostBasis,
)
from .integration import MaintenanceStatePatch
from .maintenance_schema import (
    InspectionResult,
    MaintenanceEvent,
    OperationalRecommendedAction,
    RecommendationDecision,
    WorkOrder,
)


class DiagnosisResultQueryPort(Protocol):
    """Inbound query boundary for Diagnosis-owned Product Result/Evidence."""

    def product_result(self, product_result_id: str, **scope: Any) -> Any: ...


class EquipmentStatePatchPort(Protocol):
    """Equipment-owned concurrency/apply boundary consumed by Maintenance."""

    def apply_state_patch(
        self,
        *,
        equipment_id: str,
        expected_state_version: int,
        patch: MaintenanceStatePatch,
        **scope: Any,
    ) -> int: ...


class MaintenanceReadPort(Protocol):
    def work_orders(self, **scope: Any) -> Sequence[WorkOrder]: ...
    def maintenance_events(self, **scope: Any) -> Sequence[MaintenanceEvent]: ...


class MaintenanceCommandRepositoryPort(Protocol):
    """Persistence boundary used by the canonical Maintenance application service."""

    def create_inspection_work_order(self, **values: Any) -> dict[str, Any]: ...
    def get_work_order(self, **identity: Any) -> WorkOrder | None: ...
    def list_open_inspection_work_orders(self, **scope: Any) -> Sequence[WorkOrder]: ...
    def transition_inspection_work_order(self, **values: Any) -> dict[str, Any]: ...
    def complete_inspection(self, **values: Any) -> dict[str, Any]: ...
    def get_inspection_result(self, **identity: Any) -> InspectionResult | None: ...
    def create_cost_analysis(self, **values: Any) -> dict[str, Any]: ...
    def get_cost_analysis(
        self, **identity: Any
    ) -> MaintenanceCostScenarioResult | None: ...
    def list_cost_analyses(
        self, **identity: Any
    ) -> Sequence[MaintenanceCostScenarioResult]: ...
    def create_manual_recommendation(self, **values: Any) -> dict[str, Any]: ...
    def get_recommendation(
        self, **identity: Any
    ) -> OperationalRecommendedAction | None: ...
    def decide_recommendation(
        self,
        *,
        recommendation: OperationalRecommendedAction,
        decision: RecommendationDecision,
        work_order: WorkOrder | None,
        **values: Any,
    ) -> dict[str, Any]: ...
    def approve_work_order(self, **values: Any) -> dict[str, Any]: ...
    def get_maintenance_action(self, **identity: Any) -> dict[str, Any] | None: ...
    def start_maintenance(self, *args: Any, **values: Any) -> dict[str, Any]: ...
    def complete_maintenance(self, *args: Any, **values: Any) -> dict[str, Any]: ...
    def get_maintenance_event(self, **identity: Any) -> dict[str, Any] | None: ...
    def request_replay(self, *args: Any, **values: Any) -> dict[str, Any]: ...
    def event_lineage(self, **identity: Any) -> dict[str, Any]: ...


class MaintenanceReplaySessionValidationPort(Protocol):
    """Consumer-owned boundary for a Diagnosis-validated replay reference."""

    def resolve_maintenance_replay_session(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        session_id: str,
        equipment_id: str,
    ) -> dict[str, Any]: ...

    def resolve_maintenance_source_session(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        source_product_result_id: str,
        equipment_id: str,
    ) -> dict[str, Any] | None: ...


class MaintenanceCostBasisProvider(Protocol):
    """Versioned economic inputs owned behind the Backend boundary."""

    def tool_replacement_basis(
        self, *, calculated_at: datetime, context: CostBasisResolutionContext
    ) -> ToolReplacementCostBasis: ...

    def cooling_system_restore_basis(
        self, *, calculated_at: datetime, context: CostBasisResolutionContext
    ) -> CoolingSystemRestoreCostBasis: ...


class LiveMaintenanceOverlayPort(Protocol):
    def active_asset_ids(self, *, stream_root: str | Path) -> set[str]: ...
    def process_available(self, batch: dict[str, Any]) -> list[dict[str, Any]]: ...


__all__ = [
    "DiagnosisResultQueryPort",
    "EquipmentStatePatchPort",
    "MaintenanceReadPort",
    "MaintenanceCommandRepositoryPort",
    "MaintenanceReplaySessionValidationPort",
    "MaintenanceCostBasisProvider",
    "LiveMaintenanceOverlayPort",
]
