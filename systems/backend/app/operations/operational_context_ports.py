"""Read-only ports for operational context domains."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.operations.operational_domain_schema import (
    MaintenanceReadinessContext,
    ProductionDecisionContext,
    QualityDeliveryContext,
)
from app.operations.operational_context_contract import (
    FreshnessMetadata,
    FreshnessState,
    OperationalContextEnvelope,
    OperationalContextStatus,
    OperationalRequestIdentity,
    OperationalScope,
    classify_freshness,
)


class OperationalContextReadPort(Protocol):
    owner_domain: str

    def lookup(
        self,
        *,
        identity: OperationalRequestIdentity,
        retrieved_at: datetime,
    ) -> OperationalContextEnvelope:
        """Return bounded, versioned context without mutating domain state."""


@dataclass(frozen=True)
class FixtureProductionContextReadPort:
    """Adapter for the existing synthetic production-planning context.

    The fixture is injected by the composition root. This adapter deliberately
    exposes no ProductionOrder or WIP records because the current source does
    not contain them.
    """

    context: dict[str, Any]
    organization_id: str
    workspace_id: str
    source_ref: str
    freshness_policy_version: str = "production-fixture-freshness-v1"
    max_age_seconds: int = 86_400
    owner_domain: str = "production"

    def lookup(
        self,
        *,
        identity: OperationalRequestIdentity,
        retrieved_at: datetime,
    ) -> OperationalContextEnvelope:
        self._require_configured_scope(identity)
        temporal = self.context.get("temporal_scope") or {}
        generated_at = _parse_required_datetime(
            temporal.get("generated_at"), "temporal_scope.generated_at"
        )
        valid_from = _parse_required_datetime(
            temporal.get("valid_from"), "temporal_scope.valid_from"
        )
        valid_to = _parse_required_datetime(
            temporal.get("valid_to"), "temporal_scope.valid_to"
        )
        if valid_from >= valid_to:
            raise ValueError("production context valid_from must be before valid_to")

        freshness_state = classify_freshness(
            source_updated_at=generated_at,
            retrieved_at=retrieved_at,
            max_age_seconds=self.max_age_seconds,
        )
        in_temporal_scope = valid_from <= identity.decision_as_of < valid_to
        status = (
            OperationalContextStatus.AVAILABLE
            if in_temporal_scope and freshness_state is FreshnessState.FRESH
            else OperationalContextStatus.STALE
        )
        effective_freshness = (
            FreshnessState.FRESH
            if status is OperationalContextStatus.AVAILABLE
            else FreshnessState.STALE
        )

        event_impact = next(
            (
                item
                for item in self.context.get("event_impacts") or []
                if str(item.get("equipment_id") or "") == identity.asset_id
            ),
            None,
        )
        limitations = tuple(str(item) for item in self.context.get("limitations") or [])
        if event_impact is None:
            limitations = (*limitations, "No event impact exists for the requested asset.")

        data: dict[str, Any] = {}
        if status is OperationalContextStatus.AVAILABLE:
            data = {
                "context_id": self.context.get("context_id"),
                "source_type": self.context.get("source_type"),
                "production_plan": self.context.get("production_plan") or {},
                "capacity_model": self.context.get("capacity_model") or {},
                "event_impact": event_impact,
                "production_orders": [],
                "wip": [],
                "alternative_resources": [],
                "availability": {
                    "production_orders": "not_connected",
                    "wip": "not_connected",
                    "alternative_resources": "not_connected",
                },
            }
        elif not in_temporal_scope:
            limitations = (
                *limitations,
                "Requested decision_as_of is outside the fixture validity window.",
            )
        else:
            limitations = (
                *limitations,
                "Production context exceeded its configured freshness policy.",
            )

        snapshot_id = str(temporal.get("snapshot_id") or "")
        source_version = snapshot_id or str(self.context.get("context_id") or "")
        if not source_version:
            raise ValueError("production context requires a source version")

        return OperationalContextEnvelope(
            owner_domain=self.owner_domain,
            scope=OperationalScope(
                organization_id=identity.organization_id,
                project_id=identity.project_id,
                workspace_id=identity.workspace_id,
                asset_id=identity.asset_id,
            ),
            status=status,
            source_version=source_version,
            source_updated_at=generated_at,
            retrieved_at=retrieved_at,
            as_of=identity.decision_as_of,
            freshness=FreshnessMetadata(
                policy_version=self.freshness_policy_version,
                max_age_seconds=self.max_age_seconds,
                state=effective_freshness,
            ),
            source_refs=(self.source_ref,),
            data=data,
            limitations=limitations,
        )

    def _require_configured_scope(
        self, identity: OperationalRequestIdentity
    ) -> None:
        fixture_scope = self.context.get("scope") or {}
        fixture_project_id = str(fixture_scope.get("project_id") or "")
        if (
            identity.organization_id != self.organization_id
            or identity.workspace_id != self.workspace_id
            or identity.project_id != fixture_project_id
        ):
            raise ValueError("production context configured scope mismatch")


@dataclass(frozen=True)
class FixtureProductionDecisionContextReadPort:
    """Read a typed synthetic order/WIP/alternative-capacity snapshot."""

    context: dict[str, Any]
    source_ref: str
    freshness_policy_version: str = "production-decision-fixture-freshness-v1"
    max_age_seconds: int = 172_800
    owner_domain: str = "production"

    def lookup(
        self,
        *,
        identity: OperationalRequestIdentity,
        retrieved_at: datetime,
    ) -> OperationalContextEnvelope:
        scope = self.context.get("scope") or {}
        expected_scope = (
            str(scope.get("organization_id") or ""),
            str(scope.get("project_id") or ""),
            str(scope.get("workspace_id") or ""),
        )
        actual_scope = (
            identity.organization_id,
            identity.project_id,
            identity.workspace_id,
        )
        if expected_scope != actual_scope:
            raise ValueError("production decision context configured scope mismatch")

        temporal = self.context.get("temporal_scope") or {}
        generated_at = _parse_required_datetime(
            temporal.get("generated_at"), "temporal_scope.generated_at"
        )
        valid_from = _parse_required_datetime(
            temporal.get("valid_from"), "temporal_scope.valid_from"
        )
        valid_to = _parse_required_datetime(
            temporal.get("valid_to"), "temporal_scope.valid_to"
        )
        if valid_from >= valid_to:
            raise ValueError("production decision valid_from must be before valid_to")

        parsed = ProductionDecisionContext.model_validate(
            {
                "source_classification": self.context.get(
                    "source_classification"
                ),
                "production_orders": self.context.get("production_orders") or [],
                "wip": self.context.get("wip") or [],
                "alternative_resources": self.context.get(
                    "alternative_resources"
                )
                or [],
                "limitations": self.context.get("limitations") or [],
            }
        )
        selected_orders = tuple(
            order
            for order in parsed.production_orders
            if order.assigned_asset_id == identity.asset_id
        )
        order_ids = {order.order_id for order in selected_orders}
        selected_wip = tuple(
            item
            for item in parsed.wip
            if item.order_id in order_ids and item.asset_id == identity.asset_id
        )
        operation_ids = {order.operation_id for order in selected_orders}
        product_ids = {order.product_id for order in selected_orders}
        selected_alternatives = tuple(
            resource
            for resource in parsed.alternative_resources
            if set(resource.operation_ids).intersection(operation_ids)
            and set(resource.compatible_product_ids).intersection(product_ids)
        )

        freshness_state = classify_freshness(
            source_updated_at=generated_at,
            retrieved_at=retrieved_at,
            max_age_seconds=self.max_age_seconds,
        )
        in_window = valid_from <= identity.decision_as_of < valid_to
        status = (
            OperationalContextStatus.AVAILABLE
            if in_window and freshness_state is FreshnessState.FRESH
            else OperationalContextStatus.STALE
        )
        effective_freshness = (
            FreshnessState.FRESH
            if status is OperationalContextStatus.AVAILABLE
            else FreshnessState.STALE
        )
        limitations = parsed.limitations
        data: dict[str, Any] = {}
        if status is OperationalContextStatus.AVAILABLE:
            data = {
                "source_classification": parsed.source_classification,
                "production_orders": [
                    item.model_dump(mode="json") for item in selected_orders
                ],
                "wip": [item.model_dump(mode="json") for item in selected_wip],
                "alternative_resources": [
                    item.model_dump(mode="json")
                    for item in selected_alternatives
                ],
            }
            if not selected_orders:
                limitations = (
                    *limitations,
                    "No production order is assigned to the requested asset.",
                )
        elif not in_window:
            limitations = (
                *limitations,
                "Requested decision_as_of is outside the decision context window.",
            )
        else:
            limitations = (
                *limitations,
                "Production decision context exceeded its freshness policy.",
            )

        source_version = str(temporal.get("snapshot_id") or "")
        if not source_version:
            raise ValueError("production decision context requires snapshot_id")

        return OperationalContextEnvelope(
            owner_domain=self.owner_domain,
            scope=OperationalScope(
                organization_id=identity.organization_id,
                project_id=identity.project_id,
                workspace_id=identity.workspace_id,
                asset_id=identity.asset_id,
            ),
            status=status,
            source_version=source_version,
            source_updated_at=generated_at,
            retrieved_at=retrieved_at,
            as_of=identity.decision_as_of,
            freshness=FreshnessMetadata(
                policy_version=self.freshness_policy_version,
                max_age_seconds=self.max_age_seconds,
                state=effective_freshness,
            ),
            source_refs=(self.source_ref,),
            data=data,
            limitations=limitations,
        )


@dataclass(frozen=True)
class FixtureMaintenanceReadinessContextReadPort:
    context: dict[str, Any]
    source_ref: str
    freshness_policy_version: str = "maintenance-readiness-fixture-v1"
    max_age_seconds: int = 172_800
    owner_domain: str = "maintenance_readiness"

    def lookup(
        self,
        *,
        identity: OperationalRequestIdentity,
        retrieved_at: datetime,
    ) -> OperationalContextEnvelope:
        scope = self.context.get("scope") or {}
        if (
            str(scope.get("organization_id") or ""),
            str(scope.get("project_id") or ""),
            str(scope.get("workspace_id") or ""),
        ) != (
            identity.organization_id,
            identity.project_id,
            identity.workspace_id,
        ):
            raise ValueError("maintenance readiness configured scope mismatch")

        parsed = MaintenanceReadinessContext.model_validate(
            {
                "source_classification": self.context.get(
                    "source_classification"
                ),
                "asset_id": self.context.get("asset_id"),
                "action_code": self.context.get("action_code"),
                "required_skill_codes": self.context.get(
                    "required_skill_codes"
                )
                or [],
                "maintenance_windows": self.context.get(
                    "maintenance_windows"
                )
                or [],
                "part_requirements": self.context.get("part_requirements")
                or [],
                "inventory_snapshots": self.context.get(
                    "inventory_snapshots"
                )
                or [],
                "technician_candidates": self.context.get(
                    "technician_candidates"
                )
                or [],
                "limitations": self.context.get("limitations") or [],
            }
        )
        if parsed.asset_id != identity.asset_id:
            return self._unavailable_for_asset(
                identity=identity,
                retrieved_at=retrieved_at,
                limitation="No maintenance readiness context exists for the requested asset.",
            )

        temporal = self.context.get("temporal_scope") or {}
        generated_at = _parse_required_datetime(
            temporal.get("generated_at"), "temporal_scope.generated_at"
        )
        valid_from = _parse_required_datetime(
            temporal.get("valid_from"), "temporal_scope.valid_from"
        )
        valid_to = _parse_required_datetime(
            temporal.get("valid_to"), "temporal_scope.valid_to"
        )
        freshness_state = classify_freshness(
            source_updated_at=generated_at,
            retrieved_at=retrieved_at,
            max_age_seconds=self.max_age_seconds,
        )
        in_window = valid_from <= identity.decision_as_of < valid_to
        available = in_window and freshness_state is FreshnessState.FRESH
        status = (
            OperationalContextStatus.AVAILABLE
            if available
            else OperationalContextStatus.STALE
        )
        limitations = parsed.limitations
        data: dict[str, Any] = {}
        if available:
            data = {
                "source_classification": parsed.source_classification,
                "asset_id": parsed.asset_id,
                "action_code": parsed.action_code,
                "required_skill_codes": list(parsed.required_skill_codes),
                "maintenance_windows": [
                    item.model_dump(mode="json")
                    for item in parsed.maintenance_windows
                ],
                "part_requirements": [
                    item.model_dump(mode="json")
                    for item in parsed.part_requirements
                ],
                "inventory_snapshots": [
                    item.model_dump(mode="json")
                    for item in parsed.inventory_snapshots
                ],
                "technician_candidates": [
                    item.model_dump(mode="json")
                    for item in parsed.technician_candidates
                ],
                "readiness": _maintenance_readiness(parsed),
                "execution_records": {
                    "part_reservations": [],
                    "part_issues": [],
                    "part_usage": [],
                    "technician_assignments": [],
                    "maintenance_actions": [],
                    "maintenance_events": [],
                },
            }
        elif not in_window:
            limitations = (
                *limitations,
                "Requested decision_as_of is outside the readiness context window.",
            )
        else:
            limitations = (
                *limitations,
                "Maintenance readiness exceeded its freshness policy.",
            )

        snapshot_id = str(temporal.get("snapshot_id") or "")
        if not snapshot_id:
            raise ValueError("maintenance readiness requires snapshot_id")
        return OperationalContextEnvelope(
            owner_domain=self.owner_domain,
            scope=OperationalScope(
                organization_id=identity.organization_id,
                project_id=identity.project_id,
                workspace_id=identity.workspace_id,
                asset_id=identity.asset_id,
            ),
            status=status,
            source_version=snapshot_id,
            source_updated_at=generated_at,
            retrieved_at=retrieved_at,
            as_of=identity.decision_as_of,
            freshness=FreshnessMetadata(
                policy_version=self.freshness_policy_version,
                max_age_seconds=self.max_age_seconds,
                state=(
                    FreshnessState.FRESH
                    if available
                    else FreshnessState.STALE
                ),
            ),
            source_refs=(self.source_ref,),
            data=data,
            limitations=limitations,
        )

    def _unavailable_for_asset(
        self,
        *,
        identity: OperationalRequestIdentity,
        retrieved_at: datetime,
        limitation: str,
    ) -> OperationalContextEnvelope:
        return OperationalContextEnvelope(
            owner_domain=self.owner_domain,
            scope=OperationalScope(
                organization_id=identity.organization_id,
                project_id=identity.project_id,
                workspace_id=identity.workspace_id,
                asset_id=identity.asset_id,
            ),
            status=OperationalContextStatus.UNAVAILABLE,
            retrieved_at=retrieved_at,
            as_of=identity.decision_as_of,
            freshness=FreshnessMetadata(
                policy_version=self.freshness_policy_version,
                max_age_seconds=self.max_age_seconds,
                state=FreshnessState.UNKNOWN,
            ),
            source_refs=(self.source_ref,),
            limitations=(limitation,),
        )


def _maintenance_readiness(
    context: MaintenanceReadinessContext,
) -> dict[str, Any]:
    inventory_by_part = {
        item.part_id: item for item in context.inventory_snapshots
    }
    part_blockers: list[str] = []
    for requirement in context.part_requirements:
        satisfied = any(
            inventory_by_part[part_id].available_quantity
            >= requirement.required_quantity
            for part_id in requirement.acceptable_part_ids
            if part_id in inventory_by_part
        )
        if not satisfied:
            part_blockers.append(requirement.part_requirement_id)

    window_ready = any(
        not item.active_work_order_conflict
        for item in context.maintenance_windows
    )
    skill_ready = any(
        set(context.required_skill_codes).issubset(item.skill_codes)
        for item in context.technician_candidates
    )
    blockers: list[str] = []
    if not window_ready:
        blockers.append("maintenance_window")
    if part_blockers:
        blockers.append("part_inventory")
    if not skill_ready:
        blockers.append("technician_skill")

    return {
        "overall_state": "blocked" if blockers else "ready_for_human_approval",
        "window_ready": window_ready,
        "part_ready": not part_blockers,
        "skill_candidate_ready": skill_ready,
        "blocked_part_requirement_ids": part_blockers,
        "blockers": blockers,
        "approval_state": "pending_human_approval",
        "assignment_state": "candidate_only",
        "execution_state": "not_started",
    }


@dataclass(frozen=True)
class FixtureQualityDeliveryContextReadPort:
    context: dict[str, Any]
    source_ref: str
    freshness_policy_version: str = "quality-delivery-fixture-v1"
    max_age_seconds: int = 172_800
    owner_domain: str = "quality_delivery"

    def lookup(
        self,
        *,
        identity: OperationalRequestIdentity,
        retrieved_at: datetime,
    ) -> OperationalContextEnvelope:
        scope = self.context.get("scope") or {}
        if (
            str(scope.get("organization_id") or ""),
            str(scope.get("project_id") or ""),
            str(scope.get("workspace_id") or ""),
        ) != (
            identity.organization_id,
            identity.project_id,
            identity.workspace_id,
        ):
            raise ValueError("quality delivery configured scope mismatch")

        parsed = QualityDeliveryContext.model_validate(
            {
                "source_classification": self.context.get(
                    "source_classification"
                ),
                "asset_id": self.context.get("asset_id"),
                "quality_lots": self.context.get("quality_lots") or [],
                "delivery_commitments": self.context.get(
                    "delivery_commitments"
                )
                or [],
                "limitations": self.context.get("limitations") or [],
            }
        )
        if parsed.asset_id != identity.asset_id:
            return OperationalContextEnvelope(
                owner_domain=self.owner_domain,
                scope=OperationalScope(
                    organization_id=identity.organization_id,
                    project_id=identity.project_id,
                    workspace_id=identity.workspace_id,
                    asset_id=identity.asset_id,
                ),
                status=OperationalContextStatus.UNAVAILABLE,
                retrieved_at=retrieved_at,
                as_of=identity.decision_as_of,
                freshness=FreshnessMetadata(
                    policy_version=self.freshness_policy_version,
                    max_age_seconds=self.max_age_seconds,
                    state=FreshnessState.UNKNOWN,
                ),
                source_refs=(self.source_ref,),
                limitations=(
                    "No quality/delivery context exists for the requested asset.",
                ),
            )

        temporal = self.context.get("temporal_scope") or {}
        generated_at = _parse_required_datetime(
            temporal.get("generated_at"), "temporal_scope.generated_at"
        )
        valid_from = _parse_required_datetime(
            temporal.get("valid_from"), "temporal_scope.valid_from"
        )
        valid_to = _parse_required_datetime(
            temporal.get("valid_to"), "temporal_scope.valid_to"
        )
        freshness_state = classify_freshness(
            source_updated_at=generated_at,
            retrieved_at=retrieved_at,
            max_age_seconds=self.max_age_seconds,
        )
        in_window = valid_from <= identity.decision_as_of < valid_to
        available = in_window and freshness_state is FreshnessState.FRESH
        status = (
            OperationalContextStatus.AVAILABLE
            if available
            else OperationalContextStatus.STALE
        )
        limitations = parsed.limitations
        data: dict[str, Any] = {}
        if available:
            held_lots = [
                lot
                for lot in parsed.quality_lots
                if lot.release_required or lot.quality_state == "hold"
            ]
            data = {
                "source_classification": parsed.source_classification,
                "asset_id": parsed.asset_id,
                "quality_lots": [
                    item.model_dump(mode="json")
                    for item in parsed.quality_lots
                ],
                "delivery_commitments": [
                    item.model_dump(mode="json")
                    for item in parsed.delivery_commitments
                ],
                "quality_gate": {
                    "state": "blocked" if held_lots else "clear",
                    "held_lot_ids": [item.lot_id for item in held_lots],
                    "blocked_quantity": sum(
                        item.quantity for item in held_lots
                    ),
                },
            }
        elif not in_window:
            limitations = (
                *limitations,
                "Requested decision_as_of is outside the quality/delivery window.",
            )
        else:
            limitations = (
                *limitations,
                "Quality/delivery context exceeded its freshness policy.",
            )

        snapshot_id = str(temporal.get("snapshot_id") or "")
        if not snapshot_id:
            raise ValueError("quality delivery context requires snapshot_id")
        return OperationalContextEnvelope(
            owner_domain=self.owner_domain,
            scope=OperationalScope(
                organization_id=identity.organization_id,
                project_id=identity.project_id,
                workspace_id=identity.workspace_id,
                asset_id=identity.asset_id,
            ),
            status=status,
            source_version=snapshot_id,
            source_updated_at=generated_at,
            retrieved_at=retrieved_at,
            as_of=identity.decision_as_of,
            freshness=FreshnessMetadata(
                policy_version=self.freshness_policy_version,
                max_age_seconds=self.max_age_seconds,
                state=(
                    FreshnessState.FRESH
                    if available
                    else FreshnessState.STALE
                ),
            ),
            source_refs=(self.source_ref,),
            data=data,
            limitations=limitations,
        )


def _parse_required_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed
