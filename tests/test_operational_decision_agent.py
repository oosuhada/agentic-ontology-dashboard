import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.operations.operational_context_contract import OperationalRequestIdentity
from app.operations.operational_context_ports import (
    FixtureMaintenanceReadinessContextReadPort,
    FixtureProductionDecisionContextReadPort,
    FixtureQualityDeliveryContextReadPort,
)
from app.operations.operational_decision_agent import (
    AgentTerminalState,
    BoundedOperationalDecisionAgent,
    OperationalAgentIntent,
    OperationalAgentRequest,
    ReActExecutionPolicy,
)
from app.operations.operational_impact_simulation import (
    ImpactOption,
    ImpactSimulationAssumptions,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "data" / "fixtures" / "operation_context"
RETRIEVED_AT = datetime(2026, 9, 2, 2, tzinfo=timezone.utc)
VALIDATED_AT = RETRIEVED_AT + timedelta(seconds=3)
IDENTITY = OperationalRequestIdentity(
    organization_id="ORG-001",
    project_id="manufacturing-demo-project",
    workspace_id="manufacturing-demo",
    asset_id="CNC-S04-L02-03",
    evidence_snapshot_id="ARTIFACT-GS-004",
    decision_as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
)
REQUEST = OperationalAgentRequest(
    identity=IDENTITY,
    actor_role="process_manager",
    intent=OperationalAgentIntent.MAINTENANCE_TIMING_DECISION,
    risk_status="critical",
)
ASSUMPTIONS = ImpactSimulationAssumptions(
    policy_version="operational-impact-demo-v1",
    primary_capacity_units={
        ImpactOption.STOP_NOW: 0,
        ImpactOption.PLANNED_MAINTENANCE: 120,
        ImpactOption.CONTINUE_OPERATION: 200,
    },
    alternative_capacity_allowed={
        ImpactOption.STOP_NOW: True,
        ImpactOption.PLANNED_MAINTENANCE: True,
        ImpactOption.CONTINUE_OPERATION: False,
    },
    source_refs=("policy:operational-impact-demo-v1",),
)


def load(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def ports(*, clear_quality: bool, ready_maintenance: bool) -> dict:
    maintenance_fixture = load("maintenance-readiness-context-v1.json")
    if ready_maintenance:
        inventory = maintenance_fixture["inventory_snapshots"][0]
        inventory["reserved_quantity"] = 0
        inventory["available_quantity"] = 2

    quality_fixture = load("quality-delivery-context-v1.json")
    if clear_quality:
        held = quality_fixture["quality_lots"][1]
        held["quality_state"] = "released"
        held["release_required"] = False

    return {
        "production": FixtureProductionDecisionContextReadPort(
            context=load("operational-decision-context-v1.json"),
            source_ref="fixture:production",
        ),
        "maintenance_readiness": FixtureMaintenanceReadinessContextReadPort(
            context=maintenance_fixture,
            source_ref="fixture:maintenance",
        ),
        "quality_delivery": FixtureQualityDeliveryContextReadPort(
            context=quality_fixture,
            source_ref="fixture:quality",
        ),
    }


def test_agent_collects_context_simulates_and_revalidates() -> None:
    result = BoundedOperationalDecisionAgent(
        ports=ports(clear_quality=True, ready_maintenance=True),
        impact_assumptions=ASSUMPTIONS,
    ).run(
        request=REQUEST,
        retrieved_at=RETRIEVED_AT,
        validated_at=VALIDATED_AT,
    )

    assert result.terminal_state is AgentTerminalState.COMPLETE
    assert result.temporal_validation["valid"] is True
    assert result.impact_simulation is not None
    assert [step.selected_tool for step in result.trajectory] == [
        "evidence.lookup",
        "production.lookup",
        "maintenance_readiness.lookup",
        "quality_delivery.lookup",
        "relation.resolve",
        "impact.simulate",
        "temporal.validate",
    ]
    assert result.relation_context is not None
    assert result.relation_context.conflicts == ()
    assert any(
        relation.relationship_type == "action_requires_part"
        for relation in result.relation_context.relationships
    )
    assert result.mutation_attempted is False
    assert all(
        token not in step.selected_tool
        for step in result.trajectory
        for token in ("create", "approve", "start", "complete")
    )


def test_agent_returns_partial_when_quality_blocks_calculation() -> None:
    result = BoundedOperationalDecisionAgent(
        ports=ports(clear_quality=False, ready_maintenance=True),
        impact_assumptions=ASSUMPTIONS,
    ).run(
        request=REQUEST,
        retrieved_at=RETRIEVED_AT,
        validated_at=VALIDATED_AT,
    )

    assert result.terminal_state is AgentTerminalState.PARTIAL_WITH_GAPS
    assert result.impact_simulation is not None
    assert all(
        option.reason_codes == ("QUALITY_HOLD:DEMO-LOT-015",)
        for option in result.impact_simulation.options
    )


@dataclass
class ChangingVersionPort:
    wrapped: object
    calls: int = 0
    owner_domain: str = "production"

    def lookup(self, *, identity, retrieved_at):
        self.calls += 1
        result = self.wrapped.lookup(
            identity=identity,
            retrieved_at=retrieved_at,
        )
        if self.calls > 1:
            return result.model_copy(
                update={"source_version": "PRODUCTION-CHANGED"}
            )
        return result


def test_temporal_version_change_discards_simulation() -> None:
    supplied = ports(clear_quality=True, ready_maintenance=True)
    supplied["production"] = ChangingVersionPort(supplied["production"])

    result = BoundedOperationalDecisionAgent(
        ports=supplied,
        impact_assumptions=ASSUMPTIONS,
    ).run(
        request=REQUEST,
        retrieved_at=RETRIEVED_AT,
        validated_at=VALIDATED_AT,
    )

    assert result.terminal_state is AgentTerminalState.BLOCKED
    assert result.impact_simulation is None
    assert result.temporal_validation["valid"] is False
    assert result.temporal_validation["mismatches"][0]["domain"] == "production"
    assert result.trajectory[-1].next_action == "discard_context_and_result"


@dataclass
class TransientOncePort:
    wrapped: object
    calls: int = 0
    owner_domain: str = "production"

    def lookup(self, *, identity, retrieved_at):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary source timeout")
        return self.wrapped.lookup(
            identity=identity,
            retrieved_at=retrieved_at,
        )


def test_retryable_port_failure_retries_once_and_records_attempts() -> None:
    supplied = ports(clear_quality=True, ready_maintenance=True)
    transient = TransientOncePort(supplied["production"])
    supplied["production"] = transient

    result = BoundedOperationalDecisionAgent(
        ports=supplied,
        impact_assumptions=ASSUMPTIONS,
    ).run(
        request=REQUEST,
        retrieved_at=RETRIEVED_AT,
        validated_at=VALIDATED_AT,
    )

    assert result.terminal_state is AgentTerminalState.COMPLETE
    production_step = next(
        step
        for step in result.trajectory
        if step.selected_tool == "production.lookup"
    )
    assert production_step.attempt_count == 2
    assert transient.calls == 3  # two collection attempts plus revalidation


@dataclass
class FailingExternalPort:
    owner_domain: str
    exc: BaseException
    calls: int = 0

    def lookup(self, *, identity, retrieved_at):
        self.calls += 1
        raise self.exc


def test_external_api_timeout_is_retried_and_preserved_as_fallback_gap() -> None:
    supplied = ports(clear_quality=True, ready_maintenance=True)
    failing = FailingExternalPort(
        owner_domain="production",
        exc=TimeoutError("external production API timed out"),
    )
    supplied["production"] = failing

    result = BoundedOperationalDecisionAgent(
        ports=supplied,
        impact_assumptions=ASSUMPTIONS,
    ).run(
        request=REQUEST,
        retrieved_at=RETRIEVED_AT,
        validated_at=VALIDATED_AT,
    )

    assert result.terminal_state is AgentTerminalState.PARTIAL_WITH_GAPS
    assert "production" not in result.contexts
    production_gap = next(gap for gap in result.gaps if gap["domain"] == "production")
    assert production_gap["status"] == "failed"
    assert production_gap["fallback_reason"] == "external_api_timeout"
    assert production_gap["attempt_count"] == 2
    assert production_gap["retryable"] is True
    assert failing.calls == 2
    assert all(fact["owner_domain"] != "production" for fact in result.facts)


def test_external_api_malformed_response_is_not_synthesized_as_context() -> None:
    supplied = ports(clear_quality=True, ready_maintenance=True)
    failing = FailingExternalPort(
        owner_domain="quality_delivery",
        exc=ValueError("missing source_version"),
    )
    supplied["quality_delivery"] = failing

    result = BoundedOperationalDecisionAgent(
        ports=supplied,
        impact_assumptions=ASSUMPTIONS,
    ).run(
        request=REQUEST,
        retrieved_at=RETRIEVED_AT,
        validated_at=VALIDATED_AT,
    )

    assert result.terminal_state is AgentTerminalState.PARTIAL_WITH_GAPS
    assert "quality_delivery" not in result.contexts
    quality_gap = next(
        gap for gap in result.gaps if gap["domain"] == "quality_delivery"
    )
    assert quality_gap["status"] == "failed"
    assert quality_gap["fallback_reason"] == "external_api_malformed_response"
    assert quality_gap["attempt_count"] == 1
    assert quality_gap["retryable"] is False
    assert all(
        fact["owner_domain"] != "quality_delivery" for fact in result.facts
    )


def test_step_budget_stops_without_inventing_a_result() -> None:
    result = BoundedOperationalDecisionAgent(
        ports=ports(clear_quality=True, ready_maintenance=True),
        impact_assumptions=ASSUMPTIONS,
        policy=ReActExecutionPolicy(max_steps=3),
    ).run(
        request=REQUEST,
        retrieved_at=RETRIEVED_AT,
        validated_at=VALIDATED_AT,
    )

    assert result.terminal_state is AgentTerminalState.BLOCKED
    assert result.impact_simulation is None
    assert len(result.contexts) < 3


def test_mutation_like_tool_registration_is_rejected() -> None:
    supplied = ports(clear_quality=True, ready_maintenance=True)
    supplied["maintenance.create"] = supplied["production"]

    with pytest.raises(ValueError, match="mutation-like tools"):
        BoundedOperationalDecisionAgent(
            ports=supplied,
            impact_assumptions=ASSUMPTIONS,
            policy=ReActExecutionPolicy(
                required_domains=(
                    "production",
                    "maintenance_readiness",
                    "quality_delivery",
                    "maintenance.create",
                )
            ),
        )
