"""Deterministic relation resolver for versioned operational context."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from app.operations.operational_context_contract import (
    OperationalContextEnvelope,
    OperationalContextStatus,
    OperationalRequestIdentity,
    context_version_set,
    require_matching_scope,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ResolvedRelationshipState(StrEnum):
    VERIFIED = "verified"
    ASSUMED_DEMO = "assumed_demo"
    NOT_CONNECTED = "not_connected"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"


class OperationalRelationship(FrozenModel):
    relationship_type: str = Field(min_length=1, max_length=160)
    source_type: str = Field(min_length=1, max_length=120)
    source_id: str = Field(min_length=1, max_length=240)
    target_type: str = Field(min_length=1, max_length=120)
    target_id: str = Field(min_length=1, max_length=240)
    state: ResolvedRelationshipState
    owner_domain: str = Field(min_length=1, max_length=120)
    source_version: str = Field(min_length=1, max_length=240)
    as_of: str = Field(min_length=1, max_length=80)
    source_refs: tuple[str, ...] = Field(min_length=1)


class RelationResolutionResult(FrozenModel):
    schema_version: str = "operational-relation-resolution-v1.0"
    focus: dict[str, str]
    context_version_set: dict[str, str]
    relationships: tuple[OperationalRelationship, ...]
    gaps: tuple[dict[str, Any], ...]
    conflicts: tuple[dict[str, Any], ...]


def resolve_operational_relations(
    *,
    identity: OperationalRequestIdentity,
    contexts: Mapping[str, OperationalContextEnvelope],
) -> RelationResolutionResult:
    """Resolve only explicit ID relationships from supplied domain results."""

    for envelope in contexts.values():
        require_matching_scope(identity, envelope)

    edges: list[OperationalRelationship] = []
    gaps: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    available = {
        domain: envelope
        for domain, envelope in contexts.items()
        if envelope.status is OperationalContextStatus.AVAILABLE
    }
    for domain, envelope in contexts.items():
        if envelope.status is not OperationalContextStatus.AVAILABLE:
            gaps.append(
                {
                    "owner_domain": domain,
                    "status": envelope.status.value,
                    "limitations": list(envelope.limitations),
                }
            )

    production = available.get("production")
    quality = available.get("quality_delivery")
    maintenance = available.get("maintenance_readiness")
    if production is not None:
        _production_edges(identity, production, edges, gaps)
    else:
        gaps.append({"owner_domain": "production", "status": "missing"})

    if quality is not None:
        _quality_edges(quality, production, edges, gaps)
    else:
        gaps.append({"owner_domain": "quality_delivery", "status": "missing"})

    if maintenance is not None:
        _maintenance_edges(maintenance, edges, gaps)
    else:
        gaps.append(
            {"owner_domain": "maintenance_readiness", "status": "missing"}
        )

    unique: dict[tuple[str, str, str], OperationalRelationship] = {}
    for edge in edges:
        key = (edge.relationship_type, edge.source_id, edge.target_id)
        existing = unique.get(key)
        if existing is None:
            unique[key] = edge
            continue
        if existing.state != edge.state or existing.source_version != edge.source_version:
            conflicts.append(
                {
                    "relationship_type": edge.relationship_type,
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "versions": [
                        existing.source_version,
                        edge.source_version,
                    ],
                    "states": [existing.state.value, edge.state.value],
                }
            )
            unique[key] = edge.model_copy(
                update={"state": ResolvedRelationshipState.CONFLICTING}
            )

    return RelationResolutionResult(
        focus={
            "evidence_snapshot_id": identity.evidence_snapshot_id,
            "asset_id": identity.asset_id,
            "decision_as_of": identity.decision_as_of.isoformat(),
        },
        context_version_set=context_version_set(contexts),
        relationships=tuple(unique.values()),
        gaps=tuple(_dedupe_dicts(gaps)),
        conflicts=tuple(conflicts),
    )


def _production_edges(
    identity: OperationalRequestIdentity,
    envelope: OperationalContextEnvelope,
    edges: list[OperationalRelationship],
    gaps: list[dict[str, Any]],
) -> None:
    orders = envelope.data.get("production_orders") or []
    wip_records = envelope.data.get("wip") or []
    alternatives = envelope.data.get("alternative_resources") or []
    for order in orders:
        _append(
            edges,
            envelope,
            "asset_executes_operation",
            "asset",
            identity.asset_id,
            "operation",
            order["operation_id"],
            order,
        )
        _append(
            edges,
            envelope,
            "operation_assigned_to_order",
            "operation",
            order["operation_id"],
            "production_order",
            order["order_id"],
            order,
        )
    order_ids = {item["order_id"] for item in orders}
    for item in wip_records:
        if item["order_id"] not in order_ids:
            gaps.append(
                {
                    "owner_domain": "production",
                    "status": "broken_relationship",
                    "wip_id": item["wip_id"],
                    "missing_order_id": item["order_id"],
                }
            )
            continue
        _append(
            edges,
            envelope,
            "order_contains_wip",
            "production_order",
            item["order_id"],
            "wip",
            item["wip_id"],
            item,
        )
        for lot_id in item.get("lot_ids") or []:
            _append(
                edges,
                envelope,
                "wip_includes_lot",
                "wip",
                item["wip_id"],
                "quality_lot",
                lot_id,
                item,
            )
    for resource in alternatives:
        for operation_id in resource.get("operation_ids") or []:
            _append(
                edges,
                envelope,
                "operation_has_alternative_resource",
                "operation",
                operation_id,
                "asset",
                resource["resource_id"],
                resource,
            )


def _quality_edges(
    envelope: OperationalContextEnvelope,
    production: OperationalContextEnvelope | None,
    edges: list[OperationalRelationship],
    gaps: list[dict[str, Any]],
) -> None:
    production_wip = {
        item["wip_id"]
        for item in (production.data.get("wip") or [])
    } if production is not None else set()
    production_orders = {
        item["order_id"]
        for item in (production.data.get("production_orders") or [])
    } if production is not None else set()

    for lot in envelope.data.get("quality_lots") or []:
        if lot["wip_id"] not in production_wip:
            gaps.append(
                {
                    "owner_domain": "quality_delivery",
                    "status": "broken_relationship",
                    "lot_id": lot["lot_id"],
                    "missing_wip_id": lot["wip_id"],
                }
            )
            continue
        _append(
            edges,
            envelope,
            "wip_quality_state_reported_by_lot",
            "wip",
            lot["wip_id"],
            "quality_lot",
            lot["lot_id"],
            lot,
        )
    for delivery in envelope.data.get("delivery_commitments") or []:
        if delivery["order_id"] not in production_orders:
            gaps.append(
                {
                    "owner_domain": "quality_delivery",
                    "status": "broken_relationship",
                    "delivery_id": delivery["delivery_id"],
                    "missing_order_id": delivery["order_id"],
                }
            )
            continue
        _append(
            edges,
            envelope,
            "order_commits_delivery",
            "production_order",
            delivery["order_id"],
            "delivery_commitment",
            delivery["delivery_id"],
            delivery,
        )


def _maintenance_edges(
    envelope: OperationalContextEnvelope,
    edges: list[OperationalRelationship],
    gaps: list[dict[str, Any]],
) -> None:
    data = envelope.data
    asset_id = str(data.get("asset_id") or "")
    for window in data.get("maintenance_windows") or []:
        _append(
            edges,
            envelope,
            "asset_has_maintenance_window",
            "asset",
            asset_id,
            "maintenance_window",
            window["window_id"],
            window,
        )
    inventory = {
        item["part_id"]: item
        for item in data.get("inventory_snapshots") or []
    }
    for requirement in data.get("part_requirements") or []:
        action_id = requirement.get("maintenance_action_id") or requirement.get(
            "action_candidate_id"
        )
        action_type = (
            "maintenance_action"
            if requirement.get("maintenance_action_id")
            else "maintenance_action_candidate"
        )
        _append(
            edges,
            envelope,
            "action_requires_part",
            action_type,
            action_id,
            "part_requirement",
            requirement["part_requirement_id"],
            requirement,
        )
        for part_id in requirement.get("acceptable_part_ids") or []:
            snapshot = inventory.get(part_id)
            if snapshot is None:
                gaps.append(
                    {
                        "owner_domain": "maintenance_readiness",
                        "status": "missing_inventory_snapshot",
                        "part_requirement_id": requirement[
                            "part_requirement_id"
                        ],
                        "part_id": part_id,
                    }
                )
                continue
            _append(
                edges,
                envelope,
                "part_requirement_accepts_part",
                "part_requirement",
                requirement["part_requirement_id"],
                "part",
                part_id,
                requirement,
            )
            _append(
                edges,
                envelope,
                "inventory_snapshot_reports_part",
                "inventory_snapshot",
                envelope.source_version or "unknown",
                "part",
                part_id,
                snapshot,
            )
    for technician in data.get("technician_candidates") or []:
        for skill in set(data.get("required_skill_codes") or []).intersection(
            technician.get("skill_codes") or []
        ):
            _append(
                edges,
                envelope,
                "required_skill_has_technician_candidate",
                "skill",
                skill,
                "technician_candidate",
                technician["technician_id"],
                technician,
            )


def _append(
    edges: list[OperationalRelationship],
    envelope: OperationalContextEnvelope,
    relationship_type: str,
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    record: Mapping[str, Any],
) -> None:
    if not source_id or not target_id or not envelope.source_version:
        return
    raw_state = str(record.get("relationship_state") or "unknown")
    try:
        state = ResolvedRelationshipState(raw_state)
    except ValueError:
        state = ResolvedRelationshipState.UNKNOWN
    refs = tuple(str(item) for item in record.get("source_refs") or [])
    if not refs:
        refs = envelope.source_refs
    edges.append(
        OperationalRelationship(
            relationship_type=relationship_type,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            state=state,
            owner_domain=envelope.owner_domain,
            source_version=envelope.source_version,
            as_of=envelope.as_of.isoformat(),
            source_refs=refs,
        )
    )


def _dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = repr(sorted(item.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
