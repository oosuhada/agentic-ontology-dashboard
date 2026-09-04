import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.operations.operational_context_contract import OperationalRequestIdentity
from app.operations.operational_context_ports import (
    FixtureMaintenanceReadinessContextReadPort,
    FixtureProductionDecisionContextReadPort,
    FixtureQualityDeliveryContextReadPort,
)
from app.operations.operational_decision_agent import (
    BoundedOperationalDecisionAgent,
    OperationalAgentIntent,
    OperationalAgentRequest,
)
from app.operations.operational_decision_brief import (
    DecisionBriefRole,
    compose_operational_decision_brief,
    diff_context_versions,
)
from app.operations.operational_impact_simulation import (
    ImpactOption,
    ImpactSimulationAssumptions,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "data" / "fixtures" / "operation_context"
RETRIEVED_AT = datetime(2026, 9, 2, 2, tzinfo=timezone.utc)
IDENTITY = OperationalRequestIdentity(
    organization_id="ORG-001",
    project_id="manufacturing-demo-project",
    workspace_id="manufacturing-demo",
    asset_id="CNC-S04-L02-03",
    evidence_snapshot_id="ARTIFACT-GS-004",
    decision_as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
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


def run_for_role(role: DecisionBriefRole, *, ready: bool):
    maintenance = load("maintenance-readiness-context-v1.json")
    if ready:
        inventory = maintenance["inventory_snapshots"][0]
        inventory["reserved_quantity"] = 0
        inventory["available_quantity"] = 2
    quality = load("quality-delivery-context-v1.json")
    quality["quality_lots"][1]["quality_state"] = "released"
    quality["quality_lots"][1]["release_required"] = False
    ports = {
        "production": FixtureProductionDecisionContextReadPort(
            context=load("operational-decision-context-v1.json"),
            source_ref="fixture:production",
        ),
        "maintenance_readiness": FixtureMaintenanceReadinessContextReadPort(
            context=maintenance,
            source_ref="fixture:maintenance",
        ),
        "quality_delivery": FixtureQualityDeliveryContextReadPort(
            context=quality,
            source_ref="fixture:quality",
        ),
    }
    request = OperationalAgentRequest(
        identity=IDENTITY,
        actor_role=role.value,
        intent=OperationalAgentIntent.MAINTENANCE_TIMING_DECISION,
        risk_status="critical",
    )
    result = BoundedOperationalDecisionAgent(
        ports=ports,
        impact_assumptions=ASSUMPTIONS,
    ).run(
        request=request,
        retrieved_at=RETRIEVED_AT,
        validated_at=RETRIEVED_AT + timedelta(seconds=3),
    )
    return request, result


def test_role_brief_preserves_facts_relations_and_options() -> None:
    briefs = []
    for role in DecisionBriefRole:
        request, result = run_for_role(role, ready=True)
        briefs.append(
            compose_operational_decision_brief(request=request, result=result)
        )

    baseline = briefs[0]
    assert baseline.why_now.wip_units == 200
    assert baseline.why_now.order_ids == ("DEMO-PO-001",)
    assert baseline.mutation_available is False
    assert baseline.recommendation is None
    for brief in briefs[1:]:
        assert brief.why_now == baseline.why_now
        assert brief.relationships == baseline.relationships
        assert brief.option_comparison == baseline.option_comparison
        assert brief.source_refs == baseline.source_refs
        assert brief.role_sections != baseline.role_sections


def test_maintenance_brief_exposes_candidate_part_blocker_without_actual_claim() -> None:
    request, result = run_for_role(
        DecisionBriefRole.MAINTENANCE_TECHNICIAN,
        ready=False,
    )
    brief = compose_operational_decision_brief(request=request, result=result)

    assert brief.readiness["overall_state"] == "blocked"
    assert "part_inventory" in brief.readiness["blockers"]
    action_edges = [
        edge
        for edge in brief.relationships
        if edge.relationship_type == "action_requires_part"
    ]
    assert action_edges
    assert action_edges[0].source_type == "maintenance_action_candidate"
    assert not any(
        edge.source_type in {"part_reservation", "part_issue", "part_usage"}
        for edge in brief.relationships
    )


def test_context_version_diff_invalidates_derived_outputs_only_on_change() -> None:
    unchanged = diff_context_versions(
        before={"production": "plan-17"},
        after={"production": "plan-17"},
    )
    changed = diff_context_versions(
        before={"production": "plan-17", "inventory": "inventory-42"},
        after={"production": "plan-17", "inventory": "inventory-43"},
    )

    assert unchanged.changed_domains == ()
    assert unchanged.invalidated_outputs == ()
    assert changed.changed_domains == ("inventory",)
    assert changed.changes[0].before == "inventory-42"
    assert changed.changes[0].after == "inventory-43"
    assert changed.invalidated_outputs == (
        "impact_simulation",
        "operational_decision_brief",
    )


def test_consumer_preserves_source_classification_and_limitations() -> None:
    request, result = run_for_role(DecisionBriefRole.SYSTEM_ADMIN, ready=True)
    brief = compose_operational_decision_brief(request=request, result=result)

    assert set(brief.source_classifications) == {
        "production",
        "maintenance_readiness",
        "quality_delivery",
    }
    assert set(brief.source_classifications.values()) == {
        "synthetic_demo_context"
    }
    assert any("does not recommend" in item for item in brief.limitations)
    assert len(brief.option_comparison) == 3
