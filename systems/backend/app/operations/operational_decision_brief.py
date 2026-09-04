"""Deterministic consumer projection for operational decision support."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.operations.operational_decision_agent import (
    OperationalAgentRequest,
    OperationalDecisionAgentResult,
)
from app.operations.operational_impact_simulation import ImpactOptionResult
from app.operations.operational_relation_resolver import OperationalRelationship


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DecisionBriefRole(StrEnum):
    PROCESS_MANAGER = "process_manager"
    PROCESS_ENGINEER = "process_engineer"
    MAINTENANCE_TECHNICIAN = "maintenance_technician"
    SYSTEM_ADMIN = "system_admin"


class SituationContextFrame(FrozenModel):
    evidence_snapshot_id: str
    decision_as_of: str
    actor_role: DecisionBriefRole
    intent: str
    risk_status: str
    asset_id: str
    active_operation_ids: tuple[str, ...]
    active_constraints: tuple[str, ...]
    context_version_set: dict[str, str]


class WhyNowBrief(FrozenModel):
    risk_status: str
    asset_id: str
    order_ids: tuple[str, ...]
    wip_units: int | None = Field(default=None, ge=0)
    lot_ids: tuple[str, ...]
    earliest_due_at: str | None
    decision_blockers: tuple[str, ...]
    source_refs: tuple[str, ...]


class OperationalGapView(FrozenModel):
    state: str
    owner_domain: str
    blocks_options: tuple[str, ...]
    detail: dict[str, Any]


class OperationalDecisionBrief(FrozenModel):
    schema_version: str = "operational-decision-brief-v1.0"
    frame: SituationContextFrame
    why_now: WhyNowBrief
    relationships: tuple[OperationalRelationship, ...]
    readiness: dict[str, Any]
    option_comparison: tuple[ImpactOptionResult, ...]
    gaps: tuple[OperationalGapView, ...]
    role_sections: tuple[str, ...]
    source_classifications: dict[str, str]
    source_refs: tuple[str, ...]
    limitations: tuple[str, ...]
    mutation_available: bool = False
    recommendation: None = None


class ContextVersionChange(FrozenModel):
    owner_domain: str
    before: str | None
    after: str | None


class ContextVersionDiff(FrozenModel):
    changed_domains: tuple[str, ...]
    changes: tuple[ContextVersionChange, ...]
    invalidated_outputs: tuple[str, ...]


_ROLE_SECTIONS = {
    DecisionBriefRole.PROCESS_MANAGER: (
        "why_now",
        "affected_orders_wip_delivery",
        "alternative_capacity",
        "option_comparison",
        "decision_blockers",
    ),
    DecisionBriefRole.PROCESS_ENGINEER: (
        "risk_evidence",
        "operation_relationships",
        "quality_lot_state",
        "data_gaps",
        "additional_checks",
    ),
    DecisionBriefRole.MAINTENANCE_TECHNICIAN: (
        "maintenance_window",
        "part_requirement_and_inventory",
        "skill_and_technician_candidates",
        "approval_state",
        "work_execution_state",
    ),
    DecisionBriefRole.SYSTEM_ADMIN: (
        "tool_trajectory",
        "scope_and_identity",
        "source_versions",
        "freshness",
        "retry_and_failure",
    ),
}


def compose_operational_decision_brief(
    *,
    request: OperationalAgentRequest,
    result: OperationalDecisionAgentResult,
) -> OperationalDecisionBrief:
    """Project one trusted result into a role-ordered, read-only consumer shape."""

    role = DecisionBriefRole(request.actor_role)
    production = _data(result, "production")
    maintenance = _data(result, "maintenance_readiness")
    quality = _data(result, "quality_delivery")
    orders = production.get("production_orders") or []
    wip = production.get("wip") or []
    lots = quality.get("quality_lots") or []
    deliveries = quality.get("delivery_commitments") or []
    relationships = (
        result.relation_context.relationships
        if result.relation_context is not None
        else ()
    )
    relation_gaps = (
        result.relation_context.gaps
        if result.relation_context is not None
        else ()
    )
    relation_conflicts = (
        result.relation_context.conflicts
        if result.relation_context is not None
        else ()
    )
    blockers = tuple(
        str(item)
        for item in (maintenance.get("readiness") or {}).get("blockers") or []
    )
    option_comparison = (
        result.impact_simulation.options
        if result.impact_simulation is not None
        else ()
    )
    refs = tuple(
        dict.fromkeys(
            [
                *(
                    reference
                    for envelope in result.contexts.values()
                    for reference in envelope.source_refs
                ),
                *(
                    reference
                    for relation in relationships
                    for reference in relation.source_refs
                ),
                *(
                    result.impact_simulation.source_refs
                    if result.impact_simulation is not None
                    else ()
                ),
            ]
        )
    )
    due_values = sorted(
        str(item["due_at"])
        for item in [*orders, *deliveries]
        if item.get("due_at")
    )
    active_constraints = tuple(
        dict.fromkeys(
            [
                *blockers,
                *(f"quality_hold:{item['lot_id']}" for item in lots if item.get("release_required")),
                *(f"relation_gap:{item.get('status', 'unknown')}" for item in relation_gaps),
                *(f"relation_conflict:{item.get('relationship_type', 'unknown')}" for item in relation_conflicts),
            ]
        )
    )
    limitations = tuple(
        dict.fromkeys(
            [
                "Role-specific ordering does not change facts, relationships, or calculations.",
                "This brief does not recommend, approve, schedule, assign, or execute an action.",
                *(
                    result.impact_simulation.limitations
                    if result.impact_simulation is not None
                    else ("Impact comparison is unavailable.",)
                ),
            ]
        )
    )

    return OperationalDecisionBrief(
        frame=SituationContextFrame(
            evidence_snapshot_id=request.identity.evidence_snapshot_id,
            decision_as_of=request.identity.decision_as_of.isoformat(),
            actor_role=role,
            intent=request.intent.value,
            risk_status=request.risk_status,
            asset_id=request.identity.asset_id,
            active_operation_ids=tuple(
                dict.fromkeys(
                    str(item["operation_id"])
                    for item in orders
                    if item.get("operation_id")
                )
            ),
            active_constraints=active_constraints,
            context_version_set=result.context_version_set,
        ),
        why_now=WhyNowBrief(
            risk_status=request.risk_status,
            asset_id=request.identity.asset_id,
            order_ids=tuple(str(item["order_id"]) for item in orders),
            wip_units=(
                sum(int(item["quantity"]) for item in wip)
                if wip
                else None
            ),
            lot_ids=tuple(str(item["lot_id"]) for item in lots),
            earliest_due_at=due_values[0] if due_values else None,
            decision_blockers=active_constraints,
            source_refs=refs,
        ),
        relationships=relationships,
        readiness=maintenance.get("readiness") or {
            "overall_state": "unknown",
            "blockers": ["maintenance_readiness_not_available"],
        },
        option_comparison=option_comparison,
        gaps=_gap_views(result, relation_gaps, relation_conflicts),
        role_sections=_ROLE_SECTIONS[role],
        source_classifications={
            domain: str(
                envelope.data.get("source_classification")
                or "not_declared"
            )
            for domain, envelope in result.contexts.items()
        },
        source_refs=refs,
        limitations=limitations,
    )


def diff_context_versions(
    *,
    before: dict[str, str],
    after: dict[str, str],
) -> ContextVersionDiff:
    """Explain materialization invalidation from version identity only."""

    domains = sorted(set(before) | set(after))
    changes = tuple(
        ContextVersionChange(
            owner_domain=domain,
            before=before.get(domain),
            after=after.get(domain),
        )
        for domain in domains
        if before.get(domain) != after.get(domain)
    )
    changed = tuple(change.owner_domain for change in changes)
    return ContextVersionDiff(
        changed_domains=changed,
        changes=changes,
        invalidated_outputs=(
            ("impact_simulation", "operational_decision_brief")
            if changed
            else ()
        ),
    )


def _data(result: OperationalDecisionAgentResult, domain: str) -> dict[str, Any]:
    envelope = result.contexts.get(domain)
    return envelope.data if envelope is not None else {}


def _gap_views(
    result: OperationalDecisionAgentResult,
    relation_gaps: tuple[dict[str, Any], ...],
    relation_conflicts: tuple[dict[str, Any], ...],
) -> tuple[OperationalGapView, ...]:
    views: list[OperationalGapView] = []
    for gap in [*result.gaps, *relation_gaps]:
        owner = str(gap.get("owner_domain") or gap.get("domain") or "agent")
        state = str(gap.get("status") or gap.get("state") or "missing")
        views.append(
            OperationalGapView(
                state=state,
                owner_domain=owner,
                blocks_options=_blocked_options(owner, state),
                detail=gap,
            )
        )
    for conflict in relation_conflicts:
        views.append(
            OperationalGapView(
                state="conflicting",
                owner_domain=str(conflict.get("owner_domain") or "relation"),
                blocks_options=("stop_now", "planned_maintenance", "continue_operation"),
                detail=conflict,
            )
        )
    return tuple(views)


def _blocked_options(owner_domain: str, state: str) -> tuple[str, ...]:
    if owner_domain == "maintenance_readiness":
        return ("planned_maintenance",)
    if state in {"conflicting", "unauthorized", "stale"}:
        return ("stop_now", "planned_maintenance", "continue_operation")
    if owner_domain in {"production", "quality_delivery"}:
        return ("stop_now", "planned_maintenance", "continue_operation")
    return ()
