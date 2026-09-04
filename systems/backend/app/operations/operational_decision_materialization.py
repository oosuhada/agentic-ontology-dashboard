"""Immutable brief snapshot and human-selected decision handoff contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.operations.operational_context_contract import context_version_set_hash
from app.operations.operational_decision_agent import (
    AgentTerminalState,
    OperationalAgentRequest,
    OperationalDecisionAgentResult,
)
from app.operations.operational_decision_brief import OperationalDecisionBrief
from app.operations.operational_impact_simulation import ImpactOption


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OperationalBriefSnapshot(FrozenModel):
    schema_version: str = "operational-brief-snapshot-v1.0"
    snapshot_id: str
    evidence_snapshot_id: str
    actor_role: str
    context_version_set: dict[str, str]
    context_version_hash: str
    simulation_policy_version: str
    stored_at: datetime
    terminal_state: AgentTerminalState
    brief: OperationalDecisionBrief


class DecisionHandoffPackage(FrozenModel):
    schema_version: str = "operational-decision-handoff-v1.0"
    handoff_id: str
    selected_option: ImpactOption
    selected_by: str = Field(min_length=1, max_length=240)
    selected_at: datetime
    evidence_snapshot_id: str
    context_version_set: dict[str, str]
    context_version_hash: str
    simulation_result_id: str
    simulation_policy_version: str
    assumptions: dict[str, Any]
    source_refs: tuple[str, ...]
    command_created: bool = False


def materialize_operational_brief(
    *,
    request: OperationalAgentRequest,
    result: OperationalDecisionAgentResult,
    brief: OperationalDecisionBrief,
    stored_at: datetime,
) -> OperationalBriefSnapshot:
    """Create a snapshot only after successful version revalidation."""

    _require_temporally_valid(result)
    if brief.frame.evidence_snapshot_id != request.identity.evidence_snapshot_id:
        raise ValueError("brief evidence identity mismatch")
    if brief.frame.context_version_set != result.context_version_set:
        raise ValueError("brief context version mismatch")
    if result.impact_simulation is None:
        raise ValueError("brief materialization requires an impact simulation")
    snapshot_id = _stable_id(
        "OBRIEF",
        {
            "evidence_snapshot_id": request.identity.evidence_snapshot_id,
            "actor_role": request.actor_role,
            "context_version_set": result.context_version_set,
            "simulation_policy_version": (
                result.impact_simulation.simulation_policy_version
            ),
            "brief_schema_version": brief.schema_version,
        },
    )
    return OperationalBriefSnapshot(
        snapshot_id=snapshot_id,
        evidence_snapshot_id=request.identity.evidence_snapshot_id,
        actor_role=request.actor_role,
        context_version_set=result.context_version_set,
        context_version_hash=result.context_version_hash,
        simulation_policy_version=(
            result.impact_simulation.simulation_policy_version
        ),
        stored_at=stored_at,
        terminal_state=result.terminal_state,
        brief=brief,
    )


def create_decision_handoff_package(
    *,
    request: OperationalAgentRequest,
    result: OperationalDecisionAgentResult,
    brief_snapshot: OperationalBriefSnapshot,
    selected_option: ImpactOption,
    selected_by: str,
    selected_at: datetime,
) -> DecisionHandoffPackage:
    """Package a human selection without issuing a Closed-loop command."""

    _require_temporally_valid(result)
    if result.impact_simulation is None:
        raise ValueError("decision handoff requires an impact simulation")
    if brief_snapshot.evidence_snapshot_id != request.identity.evidence_snapshot_id:
        raise ValueError("handoff evidence identity mismatch")
    if brief_snapshot.context_version_set != result.context_version_set:
        raise ValueError("handoff context version mismatch")
    if context_version_set_hash(brief_snapshot.context_version_set) != (
        brief_snapshot.context_version_hash
    ):
        raise ValueError("brief snapshot version hash mismatch")
    options = {item.option for item in result.impact_simulation.options}
    if selected_option not in options:
        raise ValueError("selected option is not present in the simulation")
    simulation_result_id = _stable_id(
        "OSIM",
        result.impact_simulation.model_dump(mode="json"),
    )
    handoff_id = _stable_id(
        "OHANDOFF",
        {
            "brief_snapshot_id": brief_snapshot.snapshot_id,
            "selected_option": selected_option.value,
            "selected_by": selected_by,
            "selected_at": selected_at.isoformat(),
        },
    )
    return DecisionHandoffPackage(
        handoff_id=handoff_id,
        selected_option=selected_option,
        selected_by=selected_by,
        selected_at=selected_at,
        evidence_snapshot_id=request.identity.evidence_snapshot_id,
        context_version_set=result.context_version_set,
        context_version_hash=result.context_version_hash,
        simulation_result_id=simulation_result_id,
        simulation_policy_version=(
            result.impact_simulation.simulation_policy_version
        ),
        assumptions=result.impact_simulation.assumptions.model_dump(mode="json"),
        source_refs=result.impact_simulation.source_refs,
    )


def _require_temporally_valid(result: OperationalDecisionAgentResult) -> None:
    if result.temporal_validation.get("valid") is not True:
        raise ValueError("temporal validation must pass before materialization")
    if result.terminal_state not in {
        AgentTerminalState.COMPLETE,
        AgentTerminalState.PARTIAL_WITH_GAPS,
    }:
        raise ValueError("terminal state is not materializable")


def _stable_id(prefix: str, value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"
