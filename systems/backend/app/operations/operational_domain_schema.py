"""Typed production decision context used by read-only agent tools."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RelationshipState(StrEnum):
    VERIFIED = "verified"
    ASSUMED_DEMO = "assumed_demo"
    NOT_CONNECTED = "not_connected"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"


class ProductionOrder(FrozenModel):
    order_id: str = Field(min_length=1, max_length=240)
    product_id: str = Field(min_length=1, max_length=240)
    product_label: str = Field(min_length=1, max_length=240)
    required_quantity: int = Field(ge=0)
    completed_quantity: int = Field(ge=0)
    due_at: datetime
    priority: int = Field(ge=0)
    operation_id: str = Field(min_length=1, max_length=240)
    assigned_asset_id: str = Field(min_length=1, max_length=240)
    relationship_state: RelationshipState
    source_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_quantities_and_time(self) -> ProductionOrder:
        if self.completed_quantity > self.required_quantity:
            raise ValueError("completed_quantity must not exceed required_quantity")
        _require_aware(self.due_at, "due_at")
        return self


class WipRecord(FrozenModel):
    wip_id: str = Field(min_length=1, max_length=240)
    order_id: str = Field(min_length=1, max_length=240)
    operation_id: str = Field(min_length=1, max_length=240)
    asset_id: str = Field(min_length=1, max_length=240)
    quantity: int = Field(ge=0)
    lot_ids: tuple[str, ...] = Field(min_length=1)
    status: str = Field(min_length=1, max_length=80)
    relationship_state: RelationshipState
    source_refs: tuple[str, ...] = Field(min_length=1)


class AlternativeResourceCapacity(FrozenModel):
    resource_id: str = Field(min_length=1, max_length=240)
    operation_ids: tuple[str, ...] = Field(min_length=1)
    compatible_product_ids: tuple[str, ...] = Field(min_length=1)
    available_from: datetime
    available_to: datetime
    gross_capacity_units: int = Field(ge=0)
    setup_minutes: int = Field(ge=0)
    net_transferable_units: int = Field(ge=0)
    relationship_state: RelationshipState
    source_refs: tuple[str, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_window_and_capacity(self) -> AlternativeResourceCapacity:
        _require_aware(self.available_from, "available_from")
        _require_aware(self.available_to, "available_to")
        if self.available_from >= self.available_to:
            raise ValueError("available_from must be before available_to")
        if self.net_transferable_units > self.gross_capacity_units:
            raise ValueError(
                "net_transferable_units must not exceed gross_capacity_units"
            )
        return self


class ProductionDecisionContext(FrozenModel):
    source_classification: str = Field(min_length=1, max_length=120)
    production_orders: tuple[ProductionOrder, ...]
    wip: tuple[WipRecord, ...]
    alternative_resources: tuple[AlternativeResourceCapacity, ...]
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_relationships(self) -> ProductionDecisionContext:
        orders = {order.order_id: order for order in self.production_orders}
        for item in self.wip:
            order = orders.get(item.order_id)
            if order is None:
                raise ValueError(f"WIP {item.wip_id} references unknown order")
            if item.operation_id != order.operation_id:
                raise ValueError(
                    f"WIP {item.wip_id} operation must match its order"
                )

        order_products = {order.product_id for order in self.production_orders}
        order_operations = {order.operation_id for order in self.production_orders}
        for resource in self.alternative_resources:
            if not set(resource.operation_ids).intersection(order_operations):
                raise ValueError(
                    f"alternative resource {resource.resource_id} has no matching operation"
                )
            if not set(resource.compatible_product_ids).intersection(order_products):
                raise ValueError(
                    f"alternative resource {resource.resource_id} has no matching product"
                )
        return self


class MaintenanceWindow(FrozenModel):
    window_id: str = Field(min_length=1, max_length=240)
    asset_id: str = Field(min_length=1, max_length=240)
    available_from: datetime
    available_to: datetime
    expected_duration_minutes: int = Field(gt=0)
    approval_required: bool
    active_work_order_conflict: bool
    relationship_state: RelationshipState
    source_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_window(self) -> MaintenanceWindow:
        _require_aware(self.available_from, "available_from")
        _require_aware(self.available_to, "available_to")
        if self.available_from >= self.available_to:
            raise ValueError("maintenance available_from must be before available_to")
        return self


class PartRequirement(FrozenModel):
    part_requirement_id: str = Field(min_length=1, max_length=240)
    action_candidate_id: str | None = Field(default=None, max_length=240)
    maintenance_action_id: str | None = Field(default=None, max_length=240)
    action_code: str = Field(min_length=1, max_length=120)
    target_component_id: str = Field(min_length=1, max_length=240)
    required_part_spec: str = Field(min_length=1, max_length=240)
    required_quantity: int = Field(gt=0)
    acceptable_part_ids: tuple[str, ...] = Field(min_length=1)
    requirement_version: str = Field(min_length=1, max_length=240)
    status: str = Field(min_length=1, max_length=80)
    relationship_state: RelationshipState
    source_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_action_identity(self) -> PartRequirement:
        identities = [
            value
            for value in (self.action_candidate_id, self.maintenance_action_id)
            if value
        ]
        if len(identities) != 1:
            raise ValueError(
                "part requirement requires exactly one action candidate or action"
            )
        if self.status == "candidate" and not self.action_candidate_id:
            raise ValueError("candidate requirement requires action_candidate_id")
        if self.status == "confirmed" and not self.maintenance_action_id:
            raise ValueError("confirmed requirement requires maintenance_action_id")
        return self


class PartInventorySnapshot(FrozenModel):
    part_id: str = Field(min_length=1, max_length=240)
    on_hand_quantity: int = Field(ge=0)
    reserved_quantity: int = Field(ge=0)
    available_quantity: int = Field(ge=0)
    expected_replenishment_at: datetime | None = None
    inventory_location_ref: str | None = Field(default=None, max_length=240)
    relationship_state: RelationshipState
    source_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> PartInventorySnapshot:
        if self.reserved_quantity > self.on_hand_quantity:
            raise ValueError("reserved quantity must not exceed on-hand quantity")
        if self.available_quantity != self.on_hand_quantity - self.reserved_quantity:
            raise ValueError("available quantity must equal on-hand minus reserved")
        if self.expected_replenishment_at is not None:
            _require_aware(
                self.expected_replenishment_at,
                "expected_replenishment_at",
            )
        return self


class TechnicianReadiness(FrozenModel):
    technician_id: str = Field(min_length=1, max_length=240)
    skill_codes: tuple[str, ...] = Field(min_length=1)
    available_from: datetime
    available_to: datetime
    assignment_state: str = Field(min_length=1, max_length=80)
    relationship_state: RelationshipState
    source_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_availability(self) -> TechnicianReadiness:
        _require_aware(self.available_from, "available_from")
        _require_aware(self.available_to, "available_to")
        if self.available_from >= self.available_to:
            raise ValueError("technician available_from must be before available_to")
        return self


class MaintenanceReadinessContext(FrozenModel):
    source_classification: str = Field(min_length=1, max_length=120)
    asset_id: str = Field(min_length=1, max_length=240)
    action_code: str = Field(min_length=1, max_length=120)
    required_skill_codes: tuple[str, ...] = Field(min_length=1)
    maintenance_windows: tuple[MaintenanceWindow, ...]
    part_requirements: tuple[PartRequirement, ...]
    inventory_snapshots: tuple[PartInventorySnapshot, ...]
    technician_candidates: tuple[TechnicianReadiness, ...]
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_readiness_relationships(self) -> MaintenanceReadinessContext:
        part_ids = {
            snapshot.part_id for snapshot in self.inventory_snapshots
        }
        for requirement in self.part_requirements:
            if requirement.action_code != self.action_code:
                raise ValueError("part requirement action code mismatch")
            if not set(requirement.acceptable_part_ids).intersection(part_ids):
                raise ValueError(
                    f"part requirement {requirement.part_requirement_id} "
                    "has no inventory snapshot"
                )
        required_skills = set(self.required_skill_codes)
        for technician in self.technician_candidates:
            if not required_skills.intersection(technician.skill_codes):
                raise ValueError(
                    f"technician {technician.technician_id} lacks required skill"
                )
        if any(window.asset_id != self.asset_id for window in self.maintenance_windows):
            raise ValueError("maintenance window asset mismatch")
        return self


class QualityLotRecord(FrozenModel):
    lot_id: str = Field(min_length=1, max_length=240)
    wip_id: str = Field(min_length=1, max_length=240)
    order_id: str = Field(min_length=1, max_length=240)
    quantity: int = Field(ge=0)
    quality_state: str = Field(min_length=1, max_length=80)
    release_required: bool
    relationship_state: RelationshipState
    source_refs: tuple[str, ...] = Field(min_length=1)


class DeliveryCommitment(FrozenModel):
    delivery_id: str = Field(min_length=1, max_length=240)
    order_id: str = Field(min_length=1, max_length=240)
    committed_quantity: int = Field(ge=0)
    due_at: datetime
    priority: int = Field(ge=0)
    relationship_state: RelationshipState
    source_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_due_at(self) -> DeliveryCommitment:
        _require_aware(self.due_at, "due_at")
        return self


class QualityDeliveryContext(FrozenModel):
    source_classification: str = Field(min_length=1, max_length=120)
    asset_id: str = Field(min_length=1, max_length=240)
    quality_lots: tuple[QualityLotRecord, ...]
    delivery_commitments: tuple[DeliveryCommitment, ...]
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_quality_delivery_relationships(
        self,
    ) -> QualityDeliveryContext:
        order_ids = {lot.order_id for lot in self.quality_lots}
        for delivery in self.delivery_commitments:
            if delivery.order_id not in order_ids:
                raise ValueError(
                    f"delivery {delivery.delivery_id} references unknown order"
                )
        return self


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
