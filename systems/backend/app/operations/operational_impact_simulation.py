"""Deterministic conditional impact comparison for operational decisions."""

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


class ImpactOption(StrEnum):
    STOP_NOW = "stop_now"
    PLANNED_MAINTENANCE = "planned_maintenance"
    CONTINUE_OPERATION = "continue_operation"


class ImpactCalculationState(StrEnum):
    CALCULATED = "calculated"
    NOT_CALCULABLE = "not_calculable"


class ImpactSimulationAssumptions(FrozenModel):
    policy_version: str = Field(min_length=1, max_length=160)
    primary_capacity_units: dict[ImpactOption, int]
    alternative_capacity_allowed: dict[ImpactOption, bool]
    source_refs: tuple[str, ...] = Field(min_length=1)


class ImpactOptionResult(FrozenModel):
    option: ImpactOption
    state: ImpactCalculationState
    preconditions: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    required_units: int | None = Field(default=None, ge=0)
    primary_capacity_after_action: int | None = Field(default=None, ge=0)
    gross_exposed_units: int | None = Field(default=None, ge=0)
    alternative_absorbed_units: int | None = Field(default=None, ge=0)
    remaining_exposed_units: int | None = Field(default=None, ge=0)
    intermediate_values: dict[str, int] = Field(default_factory=dict)
    limitations: tuple[str, ...] = ()


class ImpactSimulationResult(FrozenModel):
    schema_version: str = "operational-impact-simulation-v1.0"
    simulation_policy_version: str
    evidence_snapshot_id: str
    risk_status: str
    context_version_set: dict[str, str]
    assumptions: ImpactSimulationAssumptions
    options: tuple[ImpactOptionResult, ...]
    source_refs: tuple[str, ...]
    limitations: tuple[str, ...]


def simulate_operational_impact(
    *,
    identity: OperationalRequestIdentity,
    risk_status: str,
    contexts: Mapping[str, OperationalContextEnvelope],
    assumptions: ImpactSimulationAssumptions,
) -> ImpactSimulationResult:
    """Compare options without generating risk, recommendation, or mutation."""

    required_domains = {"production", "maintenance_readiness", "quality_delivery"}
    missing_domains = sorted(required_domains.difference(contexts))
    for envelope in contexts.values():
        require_matching_scope(identity, envelope)

    versions = context_version_set(contexts)
    source_refs = tuple(
        dict.fromkeys(
            [
                *assumptions.source_refs,
                *(
                    reference
                    for envelope in contexts.values()
                    for reference in envelope.source_refs
                ),
            ]
        )
    )
    limitations = (
        "Conditional deterministic comparison only; not realized production loss.",
        "The simulation does not calculate or change failure probability.",
        "The simulation does not select or execute an action.",
    )

    if missing_domains:
        return _blocked_result(
            identity=identity,
            risk_status=risk_status,
            versions=versions,
            assumptions=assumptions,
            source_refs=source_refs,
            limitations=limitations,
            reason_codes=tuple(
                f"MISSING_CONTEXT:{domain}" for domain in missing_domains
            ),
        )

    unavailable = [
        domain
        for domain in sorted(required_domains)
        if contexts[domain].status is not OperationalContextStatus.AVAILABLE
    ]
    if unavailable:
        return _blocked_result(
            identity=identity,
            risk_status=risk_status,
            versions=versions,
            assumptions=assumptions,
            source_refs=source_refs,
            limitations=limitations,
            reason_codes=tuple(
                f"CONTEXT_NOT_AVAILABLE:{domain}" for domain in unavailable
            ),
        )

    production = contexts["production"].data
    maintenance = contexts["maintenance_readiness"].data
    quality = contexts["quality_delivery"].data
    wip_records = production.get("wip") or []
    if not wip_records:
        return _blocked_result(
            identity=identity,
            risk_status=risk_status,
            versions=versions,
            assumptions=assumptions,
            source_refs=source_refs,
            limitations=limitations,
            reason_codes=("MISSING_WIP",),
        )

    if (quality.get("quality_gate") or {}).get("state") == "blocked":
        held = (quality.get("quality_gate") or {}).get("held_lot_ids") or []
        return _blocked_result(
            identity=identity,
            risk_status=risk_status,
            versions=versions,
            assumptions=assumptions,
            source_refs=source_refs,
            limitations=limitations,
            reason_codes=tuple(
                f"QUALITY_HOLD:{lot_id}" for lot_id in held
            )
            or ("QUALITY_HOLD",),
        )

    required_units = sum(int(item["quantity"]) for item in wip_records)
    alternative_capacity = sum(
        int(item["net_transferable_units"])
        for item in production.get("alternative_resources") or []
        if item.get("relationship_state") in {"verified", "assumed_demo"}
    )
    maintenance_state = (maintenance.get("readiness") or {}).get(
        "overall_state"
    )
    options: list[ImpactOptionResult] = []
    for option in ImpactOption:
        if (
            option is ImpactOption.PLANNED_MAINTENANCE
            and maintenance_state != "ready_for_human_approval"
        ):
            blockers = (maintenance.get("readiness") or {}).get("blockers") or []
            options.append(
                ImpactOptionResult(
                    option=option,
                    state=ImpactCalculationState.NOT_CALCULABLE,
                    preconditions=("maintenance readiness must be satisfied",),
                    reason_codes=tuple(
                        f"MAINTENANCE_BLOCKED:{item}" for item in blockers
                    )
                    or ("MAINTENANCE_BLOCKED",),
                    limitations=(
                        "Impact is withheld until maintenance prerequisites are ready.",
                    ),
                )
            )
            continue

        primary_capacity = assumptions.primary_capacity_units.get(option)
        allow_alternative = assumptions.alternative_capacity_allowed.get(option)
        if primary_capacity is None or allow_alternative is None:
            options.append(
                ImpactOptionResult(
                    option=option,
                    state=ImpactCalculationState.NOT_CALCULABLE,
                    reason_codes=("MISSING_OPTION_ASSUMPTION",),
                )
            )
            continue

        gross_exposed = max(0, required_units - primary_capacity)
        absorbed = (
            min(gross_exposed, alternative_capacity)
            if allow_alternative
            else 0
        )
        remaining = gross_exposed - absorbed
        options.append(
            ImpactOptionResult(
                option=option,
                state=ImpactCalculationState.CALCULATED,
                preconditions=_preconditions(option),
                required_units=required_units,
                primary_capacity_after_action=primary_capacity,
                gross_exposed_units=gross_exposed,
                alternative_absorbed_units=absorbed,
                remaining_exposed_units=remaining,
                intermediate_values={
                    "required_units": required_units,
                    "primary_capacity_after_action": primary_capacity,
                    "verified_alternative_capacity": alternative_capacity,
                    "gross_exposed_units": gross_exposed,
                    "absorbed_units": absorbed,
                },
                limitations=(
                    "Calculated from versioned synthetic assumptions."
                    if _is_synthetic(contexts)
                    else "Calculated from the supplied versioned context.",
                ),
            )
        )

    return ImpactSimulationResult(
        simulation_policy_version=assumptions.policy_version,
        evidence_snapshot_id=identity.evidence_snapshot_id,
        risk_status=risk_status,
        context_version_set=versions,
        assumptions=assumptions,
        options=tuple(options),
        source_refs=source_refs,
        limitations=limitations,
    )


def _blocked_result(
    *,
    identity: OperationalRequestIdentity,
    risk_status: str,
    versions: dict[str, str],
    assumptions: ImpactSimulationAssumptions,
    source_refs: tuple[str, ...],
    limitations: tuple[str, ...],
    reason_codes: tuple[str, ...],
) -> ImpactSimulationResult:
    return ImpactSimulationResult(
        simulation_policy_version=assumptions.policy_version,
        evidence_snapshot_id=identity.evidence_snapshot_id,
        risk_status=risk_status,
        context_version_set=versions,
        assumptions=assumptions,
        options=tuple(
            ImpactOptionResult(
                option=option,
                state=ImpactCalculationState.NOT_CALCULABLE,
                reason_codes=reason_codes,
            )
            for option in ImpactOption
        ),
        source_refs=source_refs,
        limitations=limitations,
    )


def _preconditions(option: ImpactOption) -> tuple[str, ...]:
    if option is ImpactOption.STOP_NOW:
        return ("human stop approval",)
    if option is ImpactOption.PLANNED_MAINTENANCE:
        return (
            "maintenance window",
            "part readiness",
            "skill candidate",
            "human approval",
        )
    return ("human continue approval", "continued observation")


def _is_synthetic(
    contexts: Mapping[str, OperationalContextEnvelope],
) -> bool:
    return any(
        envelope.data.get("source_classification")
        == "synthetic_demo_context"
        for envelope in contexts.values()
    )
