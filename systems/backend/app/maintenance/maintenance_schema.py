"""Closed-loop value objects without HTTP or persistence concerns."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OperationalDecisionKind(StrEnum):
    """Operational decision values shared by maintenance authorization flows."""

    CONTINUE_MONITORING = "continue_monitoring"
    REQUEST_INSPECTION = "request_inspection"
    REVIEW_SHUTDOWN = "review_shutdown"
    HOLD_FOR_DATA_CHECK = "hold_for_data_check"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScopedRecord(FrozenModel):
    organization_id: str = Field(min_length=1, max_length=160)
    project_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)


class RiskEventStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class RecommendationStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    SUPERSEDED = "superseded"


class RecommendationDisposition(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    DEFER = "defer"


class WorkOrderType(StrEnum):
    INSPECTION = "inspection"
    MAINTENANCE = "maintenance"


class WorkOrderStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InspectionOutcome(StrEnum):
    NO_ACTION_REQUIRED = "no_action_required"
    MAINTENANCE_RECOMMENDED = "maintenance_recommended"
    DATA_CHECK_REQUIRED = "data_check_required"


class MaintenanceActionStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MaterializationStrategy(StrEnum):
    RUNTIME_GENERATED = "runtime_generated"
    IMPORTED_PRECOMPUTED = "imported_precomputed"


class IdempotencyState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class IdempotencyOutcome(StrEnum):
    NEW = "new"
    REPLAY = "replay"


class EquipmentIdentity(ScopedRecord):
    asset_id: str = Field(min_length=1, max_length=240)
    equipment_id: str = Field(min_length=1, max_length=240)
    asset_type: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_operations_identity(self) -> EquipmentIdentity:
        if self.asset_id != self.equipment_id:
            raise ValueError("Operations identity requires equipment_id = asset_id")
        return self

    @property
    def stable_key(self) -> str:
        return f"{self.organization_id}:{self.project_id}:{self.asset_id}"


class OperationalRecommendedAction(ScopedRecord):
    recommendation_id: str = Field(min_length=1, max_length=240)
    recommendation_origin: Literal[
        "product_result_projection", "operations_manual"
    ] = "product_result_projection"
    status: RecommendationStatus = RecommendationStatus.PROPOSED
    materialization_strategy: Literal[MaterializationStrategy.RUNTIME_GENERATED] = (
        MaterializationStrategy.RUNTIME_GENERATED
    )
    asset_id: str = Field(min_length=1, max_length=240)
    equipment_id: str = Field(min_length=1, max_length=240)
    asset_type: str = Field(min_length=1, max_length=160)
    event_id: str = Field(min_length=1, max_length=240)
    source_action_id: str = Field(min_length=1, max_length=240)
    source_product_result_id: str = Field(min_length=1, max_length=240)
    source_evidence_id: str = Field(min_length=1, max_length=240)
    source_schema_version: str = Field(min_length=1, max_length=160)
    source_policy_version: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=500)
    kind: str = Field(min_length=1, max_length=128)
    requires_human_approval: bool
    basis: tuple[str, ...] = Field(min_length=1)
    source_inspection_work_order_id: str | None = Field(
        default=None, min_length=1, max_length=240
    )
    source_inspection_reference: str | None = Field(
        default=None, min_length=1, max_length=240
    )
    source_cost_analysis_id: str | None = Field(
        default=None, min_length=1, max_length=240
    )
    source_cost_option_id: str | None = Field(
        default=None, min_length=1, max_length=240
    )
    source_action_candidate_id: str | None = Field(
        default=None, min_length=1, max_length=240
    )
    action_code: Literal["TOOL_REPLACEMENT", "COOLING_SYSTEM_RESTORE"] | None = None
    authored_by: str | None = Field(default=None, min_length=1, max_length=240)
    authored_at: datetime | None = None

    @model_validator(mode="after")
    def require_operations_identity(self) -> OperationalRecommendedAction:
        if self.asset_id != self.equipment_id:
            raise ValueError("Operations recommendation requires equipment_id = asset_id")
        manual_required_fields = (
            self.source_inspection_work_order_id,
            self.source_inspection_reference,
            self.action_code,
            self.authored_by,
            self.authored_at,
        )
        cost_reference_fields = (
            self.source_cost_analysis_id,
            self.source_cost_option_id,
            self.source_action_candidate_id,
        )
        if self.recommendation_origin == "product_result_projection":
            if any(
                value is not None
                for value in (*manual_required_fields, *cost_reference_fields)
            ):
                raise ValueError(
                    "product_result_projection cannot contain operations_manual lineage"
                )
            return self
        if any(value is None for value in manual_required_fields):
            raise ValueError(
                "operations_manual requires inspection, action, and author lineage"
            )
        if (self.source_cost_analysis_id is None) != (
            self.source_action_candidate_id is None
        ):
            raise ValueError(
                "cost-referenced operations_manual requires analysis and action candidate lineage"
            )
        if (
            self.source_cost_option_id is not None
            and self.source_cost_analysis_id is None
        ):
            raise ValueError(
                "cost-selected operations_manual requires analysis and action candidate lineage"
            )
        if self.kind != self.action_code:
            raise ValueError("operations_manual kind must match action_code")
        if not self.requires_human_approval:
            raise ValueError("operations_manual requires human approval")
        return self

    @property
    def materialization_key(self) -> str:
        if self.recommendation_origin == "operations_manual":
            return (
                f"{self.source_inspection_work_order_id}:"
                f"{self.source_inspection_reference}:{self.action_code}"
            )
        return f"{self.source_product_result_id}:{self.source_action_id}"


class RecommendationDecision(ScopedRecord):
    decision_id: str = Field(min_length=1, max_length=240)
    event_id: str = Field(min_length=1, max_length=240)
    recommendation_id: str = Field(min_length=1, max_length=240)
    disposition: RecommendationDisposition
    actor_id: str = Field(min_length=1, max_length=240)
    decided_at: datetime
    note: str = Field(default="", max_length=4000)


class WorkOrderAuthorization(FrozenModel):
    work_type: WorkOrderType
    recommendation_id: str | None = None
    recommendation_decision_id: str | None = None
    recommendation_status: Literal[RecommendationStatus.ACCEPTED] | None = None
    recommendation_disposition: Literal[RecommendationDisposition.ACCEPT] | None = None
    operational_decision: OperationalDecisionKind | None = None
    source_product_result_id: str | None = Field(default=None, min_length=1, max_length=240)
    source_evidence_id: str | None = Field(default=None, min_length=1, max_length=240)
    source_action_id: str | None = Field(default=None, min_length=1, max_length=240)
    source_schema_version: str | None = Field(default=None, min_length=1, max_length=160)
    source_policy_version: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_valid_authorization_shape(self) -> WorkOrderAuthorization:
        recommendation_fields = (
            self.recommendation_id,
            self.recommendation_decision_id,
            self.recommendation_status,
            self.recommendation_disposition,
        )
        inspection_source_fields = (
            self.source_product_result_id,
            self.source_evidence_id,
            self.source_action_id,
            self.source_schema_version,
            self.source_policy_version,
        )
        if self.work_type is WorkOrderType.INSPECTION:
            if self.operational_decision not in {
                OperationalDecisionKind.REQUEST_INSPECTION,
                OperationalDecisionKind.REVIEW_SHUTDOWN,
            }:
                raise ValueError("inspection requires request_inspection or review_shutdown")
            if any(value is not None for value in recommendation_fields):
                raise ValueError("inspection authorization cannot contain maintenance approval")
            if any(value is None for value in inspection_source_fields):
                raise ValueError(
                    "inspection authorization requires Product Result/Evidence projection lineage"
                )
            return self
        if self.operational_decision is not None:
            raise ValueError("maintenance authorization cannot use an operational decision")
        if any(value is not None for value in inspection_source_fields):
            raise ValueError("maintenance authorization cannot contain inspection source lineage")
        if any(value is None for value in recommendation_fields):
            raise ValueError("maintenance authorization requires an accepted recommendation decision")
        return self


class WorkOrder(ScopedRecord):
    work_order_id: str = Field(min_length=1, max_length=240)
    event_id: str = Field(min_length=1, max_length=240)
    asset_id: str = Field(min_length=1, max_length=240)
    equipment_id: str = Field(min_length=1, max_length=240)
    asset_type: str = Field(min_length=1, max_length=160)
    work_type: WorkOrderType
    status: WorkOrderStatus = WorkOrderStatus.REQUESTED
    assigned_to: str | None = Field(default=None, min_length=1, max_length=240)
    assigned_at: datetime | None = None
    idempotency_key: str = Field(min_length=8, max_length=200)
    authorization: WorkOrderAuthorization

    @model_validator(mode="after")
    def require_matching_authorization(self) -> WorkOrder:
        if self.authorization.work_type != self.work_type:
            raise ValueError("work order type must match its authorization")
        if self.asset_id != self.equipment_id:
            raise ValueError("Operations work order requires equipment_id = asset_id")
        if self.work_type is WorkOrderType.INSPECTION:
            if self.status is WorkOrderStatus.REQUESTED:
                if self.assigned_to is not None or self.assigned_at is not None:
                    raise ValueError("requested inspection work order cannot be assigned")
            elif self.status in {WorkOrderStatus.APPROVED, WorkOrderStatus.IN_PROGRESS} and (
                self.assigned_to is None or self.assigned_at is None
            ):
                raise ValueError("accepted inspection work order requires an assignee")
            elif (self.assigned_to is None) != (self.assigned_at is None):
                raise ValueError("inspection assignment identity and timestamp must be paired")
        return self


class InspectionChecklistItem(FrozenModel):
    item_id: str = Field(min_length=1, max_length=160)
    status: Literal["pass", "fail", "not_checked"]
    note: str = Field(default="", max_length=2000)


class InspectionMeasurement(FrozenModel):
    name: str = Field(min_length=1, max_length=160)
    value: float | int | str | bool | None
    unit: str = Field(default="", max_length=80)


class InspectionResult(ScopedRecord):
    """Immutable field-inspection fact; never a maintenance approval/event."""

    inspection_result_id: str = Field(min_length=1, max_length=240)
    work_order_id: str = Field(min_length=1, max_length=240)
    event_id: str = Field(min_length=1, max_length=240)
    asset_id: str = Field(min_length=1, max_length=240)
    equipment_id: str = Field(min_length=1, max_length=240)
    asset_type: str = Field(min_length=1, max_length=160)
    outcome: InspectionOutcome
    checklist: tuple[InspectionChecklistItem, ...] = Field(min_length=1)
    measurements: tuple[InspectionMeasurement, ...] = ()
    findings: tuple[str, ...] = Field(min_length=1)
    note: str = Field(default="", max_length=4000)
    recorded_by: str = Field(min_length=1, max_length=240)
    recorded_at: datetime

    @model_validator(mode="after")
    def require_inspection_identity(self) -> InspectionResult:
        if self.asset_id != self.equipment_id:
            raise ValueError("Operations inspection result requires equipment_id = asset_id")
        return self


class MaintenanceActionCandidate(ScopedRecord):
    """Maintenance-owned projection derived from an immutable inspection result."""

    action_candidate_id: str = Field(min_length=1, max_length=240)
    inspection_result_id: str = Field(min_length=1, max_length=240)
    event_id: str = Field(min_length=1, max_length=240)
    asset_id: str = Field(min_length=1, max_length=240)
    equipment_id: str = Field(min_length=1, max_length=240)
    action_code: Literal["TOOL_REPLACEMENT", "COOLING_SYSTEM_RESTORE"]
    basis_codes: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_candidate_identity(self) -> MaintenanceActionCandidate:
        if self.asset_id != self.equipment_id:
            raise ValueError("Operations action candidate requires equipment_id = asset_id")
        return self


class MaintenanceAction(ScopedRecord):
    maintenance_action_id: str = Field(min_length=1, max_length=240)
    work_order_id: str = Field(min_length=1, max_length=240)
    event_id: str = Field(min_length=1, max_length=240)
    asset_id: str = Field(min_length=1, max_length=240)
    equipment_id: str = Field(min_length=1, max_length=240)
    recommendation_id: str = Field(min_length=1, max_length=240)
    recommendation_decision_id: str = Field(min_length=1, max_length=240)
    status: MaintenanceActionStatus = MaintenanceActionStatus.PLANNED
    idempotency_key: str = Field(min_length=8, max_length=200)

    @model_validator(mode="after")
    def require_operations_identity(self) -> MaintenanceAction:
        if self.asset_id != self.equipment_id:
            raise ValueError("Operations maintenance action requires equipment_id = asset_id")
        return self


class MaintenanceEvent(ScopedRecord):
    """Immutable fact created only after maintenance work is completed."""

    maintenance_event_id: str = Field(min_length=1, max_length=240)
    maintenance_action_id: str = Field(min_length=1, max_length=240)
    work_order_id: str = Field(min_length=1, max_length=240)
    event_id: str = Field(min_length=1, max_length=240)
    asset_id: str = Field(min_length=1, max_length=240)
    equipment_id: str = Field(min_length=1, max_length=240)
    recommendation_id: str = Field(min_length=1, max_length=240)
    recommendation_decision_id: str = Field(min_length=1, max_length=240)
    completed_at: datetime
    outcome: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def require_operations_identity(self) -> MaintenanceEvent:
        if self.asset_id != self.equipment_id:
            raise ValueError("Operations maintenance event requires equipment_id = asset_id")
        return self


class IdempotencyRecord(FrozenModel):
    idempotency_key: str = Field(min_length=8, max_length=200)
    request_fingerprint: str = Field(min_length=1, max_length=256)
    state: IdempotencyState
