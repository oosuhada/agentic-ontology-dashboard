import json
from datetime import datetime, timezone
from pathlib import Path

from app.operations.operational_context_contract import OperationalRequestIdentity
from app.operations.operational_context_ports import (
    FixtureMaintenanceReadinessContextReadPort,
    FixtureProductionDecisionContextReadPort,
    FixtureQualityDeliveryContextReadPort,
)
from app.operations.operational_impact_simulation import (
    ImpactCalculationState,
    ImpactOption,
    ImpactSimulationAssumptions,
    simulate_operational_impact,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "data" / "fixtures" / "operation_context"


def load(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


IDENTITY = OperationalRequestIdentity(
    organization_id="ORG-001",
    project_id="manufacturing-demo-project",
    workspace_id="manufacturing-demo",
    asset_id="CNC-S04-L02-03",
    evidence_snapshot_id="ARTIFACT-GS-004",
    decision_as_of=datetime(2026, 9, 2, 1, tzinfo=timezone.utc),
)
RETRIEVED_AT = datetime(2026, 9, 2, 2, tzinfo=timezone.utc)
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


def contexts(
    *,
    clear_quality: bool,
    ready_maintenance: bool,
) -> dict:
    production = FixtureProductionDecisionContextReadPort(
        context=load("operational-decision-context-v1.json"),
        source_ref="fixture:production-decision",
    ).lookup(identity=IDENTITY, retrieved_at=RETRIEVED_AT)

    maintenance_fixture = load("maintenance-readiness-context-v1.json")
    if ready_maintenance:
        inventory = maintenance_fixture["inventory_snapshots"][0]
        inventory["reserved_quantity"] = 0
        inventory["available_quantity"] = 2
    maintenance = FixtureMaintenanceReadinessContextReadPort(
        context=maintenance_fixture,
        source_ref="fixture:maintenance-readiness",
    ).lookup(identity=IDENTITY, retrieved_at=RETRIEVED_AT)

    quality_fixture = load("quality-delivery-context-v1.json")
    if clear_quality:
        held = quality_fixture["quality_lots"][1]
        held["quality_state"] = "released"
        held["release_required"] = False
    quality = FixtureQualityDeliveryContextReadPort(
        context=quality_fixture,
        source_ref="fixture:quality-delivery",
    ).lookup(identity=IDENTITY, retrieved_at=RETRIEVED_AT)

    return {
        "production": production,
        "maintenance_readiness": maintenance,
        "quality_delivery": quality,
    }


def by_option(result) -> dict:
    return {item.option: item for item in result.options}


def test_quality_hold_withholds_all_option_calculations() -> None:
    result = simulate_operational_impact(
        identity=IDENTITY,
        risk_status="critical",
        contexts=contexts(clear_quality=False, ready_maintenance=True),
        assumptions=ASSUMPTIONS,
    )

    assert all(
        item.state is ImpactCalculationState.NOT_CALCULABLE
        for item in result.options
    )
    assert all(
        item.reason_codes == ("QUALITY_HOLD:DEMO-LOT-015",)
        for item in result.options
    )


def test_maintenance_blocker_only_withholds_planned_maintenance() -> None:
    result = simulate_operational_impact(
        identity=IDENTITY,
        risk_status="critical",
        contexts=contexts(clear_quality=True, ready_maintenance=False),
        assumptions=ASSUMPTIONS,
    )
    options = by_option(result)

    assert (
        options[ImpactOption.PLANNED_MAINTENANCE].state
        is ImpactCalculationState.NOT_CALCULABLE
    )
    assert options[ImpactOption.PLANNED_MAINTENANCE].reason_codes == (
        "MAINTENANCE_BLOCKED:part_inventory",
    )
    assert (
        options[ImpactOption.STOP_NOW].state
        is ImpactCalculationState.CALCULATED
    )
    assert (
        options[ImpactOption.CONTINUE_OPERATION].state
        is ImpactCalculationState.CALCULATED
    )


def test_ready_context_calculates_three_options_without_ranking() -> None:
    result = simulate_operational_impact(
        identity=IDENTITY,
        risk_status="critical",
        contexts=contexts(clear_quality=True, ready_maintenance=True),
        assumptions=ASSUMPTIONS,
    )
    options = by_option(result)

    assert options[ImpactOption.STOP_NOW].remaining_exposed_units == 150
    assert (
        options[ImpactOption.PLANNED_MAINTENANCE].remaining_exposed_units
        == 30
    )
    assert (
        options[ImpactOption.CONTINUE_OPERATION].remaining_exposed_units
        == 0
    )
    assert result.risk_status == "critical"
    assert not hasattr(result, "recommended_option")
    assert result.context_version_set == {
        "maintenance_readiness": "MAINT-READINESS-SNAPSHOT-2026-09-02-01",
        "production": "OPS-DECISION-SNAPSHOT-2026-09-02-01",
        "quality_delivery": "QUALITY-DELIVERY-SNAPSHOT-2026-09-02-01",
    }


def test_simulation_is_deterministic_for_same_versions_and_assumptions() -> None:
    supplied = contexts(clear_quality=True, ready_maintenance=True)

    first = simulate_operational_impact(
        identity=IDENTITY,
        risk_status="critical",
        contexts=supplied,
        assumptions=ASSUMPTIONS,
    )
    second = simulate_operational_impact(
        identity=IDENTITY,
        risk_status="critical",
        contexts=supplied,
        assumptions=ASSUMPTIONS,
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_missing_domain_context_is_not_calculable_not_zero() -> None:
    supplied = contexts(clear_quality=True, ready_maintenance=True)
    supplied.pop("quality_delivery")

    result = simulate_operational_impact(
        identity=IDENTITY,
        risk_status="critical",
        contexts=supplied,
        assumptions=ASSUMPTIONS,
    )

    assert all(item.required_units is None for item in result.options)
    assert all(
        item.reason_codes == ("MISSING_CONTEXT:quality_delivery",)
        for item in result.options
    )
