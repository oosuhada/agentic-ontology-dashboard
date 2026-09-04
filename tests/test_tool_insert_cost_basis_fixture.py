from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.infra.maintenance_cost_basis_provider import JsonMaintenanceCostBasisProvider
from app.maintenance import (
    CostAnalysisBasis,
    ToolReplacementCostAnalysisInput,
    calculate_tool_replacement_cost_scenarios,
)
from app.maintenance.cost_basis import CostBasisResolutionContext


ROOT = Path(__file__).resolve().parents[1]
BASIS_PATH = (
    ROOT
    / "data"
    / "fixtures"
    / "maintenance_cost"
    / "tool-insert-cost-basis-v1.json"
)


def load_basis() -> dict:
    return json.loads(BASIS_PATH.read_text(encoding="utf-8"))


def applicable_context() -> CostBasisResolutionContext:
    return CostBasisResolutionContext(
        execution_mode="in_house",
        spare_part_available=True,
        vendor_dispatch_required=False,
    )


def test_tool_replacement_is_exactly_one_carbide_insert() -> None:
    basis = load_basis()

    assert basis["action_code"] == "TOOL_REPLACEMENT"
    assert basis["applicability"] == {
        "execution_mode": "in_house",
        "spare_part_available": True,
        "vendor_dispatch_required": False,
    }
    assert basis["replacement_scope"] == {
        "component_id": "tooling",
        "part_id": "SP-CNC-CARBIDE-INSERT-ONE",
        "part_label": "카바이드 절삭 인서트 1개",
        "quantity": 1,
        "unit": "piece",
    }


def test_public_reference_values_match_their_recorded_derivations() -> None:
    basis = load_basis()
    parts = basis["parts_cost"]
    parts_derivation = parts["derivation"]
    expected_parts_cost = round(
        (
            parts_derivation["catalog_pack_price_usd"]
            / parts_derivation["pack_quantity"]
        )
        * parts_derivation["usd_krw_close"]
    )
    assert parts["reference_minor"] == expected_parts_cost == 12251

    labor = basis["labor_rate_per_minute"]
    labor_derivation = labor["derivation"]
    expected_labor_rate = round(
        labor_derivation["survey_daily_wage_krw"]
        / labor_derivation["survey_day_minutes"]
    )
    assert labor["normal_minor"] == expected_labor_rate == 292


def test_demo_policy_values_record_derivation_and_source_kind() -> None:
    basis = load_basis()
    policy = basis["demo_policy_inputs"]

    assert set(policy) == {
        "labor_duration_minutes",
        "external_service_cost_minor",
        "expected_downtime_minutes",
        "production_loss_rate_minor_per_minute",
        "failure_consequence_cost_minor",
        "expected_failure_loss_minor",
    }
    assert policy["labor_duration_minutes"]["sensitivity"] == {
        "low": 5,
        "base": 10,
        "high": 15,
    }
    assert policy["external_service_cost_minor"]["sensitivity"] == {
        "low": 0,
        "base": 0,
        "high": 0,
    }
    assert policy["expected_downtime_minutes"]["sensitivity"] == {
        "low": 15,
        "base": 30,
        "high": 45,
    }
    assert policy["production_loss_rate_minor_per_minute"]["sensitivity"] == {
        "low": 846,
        "base": 1058,
        "high": 1269,
    }
    assert policy["failure_consequence_cost_minor"]["sensitivity"] == {
        "low": 67391,
        "base": 147971,
        "high": 334331,
    }
    probabilities = policy["expected_failure_loss_minor"]["scenario_probabilities"]
    assert probabilities["immediate"]["failure_probability"] == 0.21
    assert probabilities["no_action_baseline"]["failure_probability"] == 0.82
    assert probabilities["planned_window"] is None
    assert probabilities["reinspect_after"] is None
    assert all(
        entry["reasoning"]
        for name, entry in policy.items()
        if name != "expected_failure_loss_minor"
    )
    assert basis["parts_cost"]["confidence"] == "low"
    assert "actual site quotation" in basis["description"]
    assert len(basis["sources"]) == 12
    assert basis["labor_rate_per_minute"]["night_minor"] == 438
    assert basis["execution_time_policy"] == {
        "timezone": "Asia/Seoul",
        "planned_window_delay_hours": 12,
        "night_window": {"start_hour": 22, "end_hour": 6},
        "normal_rate_minor_per_minute": 292,
        "night_rate_minor_per_minute": 438,
        "reasoning": basis["execution_time_policy"]["reasoning"],
        "source_ids": ["korean-labor-standards-act-article-56"],
        "limitations": basis["execution_time_policy"]["limitations"],
    }


def test_derived_demo_costs_match_recorded_formulas() -> None:
    basis = load_basis()
    policy = basis["demo_policy_inputs"]
    production = policy["production_loss_rate_minor_per_minute"]
    production_derivation = production["derivation"]
    for band in ("low", "base", "high"):
        expected_rate = round(
            (
                production_derivation["oee"]
                / production_derivation["standard_cycle_minutes_per_unit"]
            )
            * production_derivation["unit_contribution_margin_minor"][band]
        )
        assert production["sensitivity"][band] == expected_rate

    consequence = policy["failure_consequence_cost_minor"]
    consequence_derivation = consequence["derivation"]
    for band in ("low", "base", "high"):
        expected_consequence = (
            basis["parts_cost"]["reference_minor"]
            + consequence_derivation["emergency_labor_duration_minutes"][band]
            * basis["labor_rate_per_minute"]["normal_minor"]
            + consequence_derivation["unplanned_downtime_minutes"][band]
            * production["sensitivity"][band]
        )
        assert consequence["sensitivity"][band] == expected_consequence


def test_every_policy_source_id_resolves_and_internal_sources_exist() -> None:
    basis = load_basis()
    sources = {source["source_id"]: source for source in basis["sources"]}

    for entry in basis["demo_policy_inputs"].values():
        for source_id in entry.get("source_ids", []):
            assert source_id in sources
    for source_id in basis["execution_time_policy"]["source_ids"]:
        assert source_id in sources

    for source in sources.values():
        reference = source["url"]
        if not reference.startswith(("https://", "http://")):
            assert (ROOT / reference).is_file()


def test_backend_provider_calculates_only_governed_probability_scenarios() -> None:
    calculated_at = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)
    basis = JsonMaintenanceCostBasisProvider(BASIS_PATH).tool_replacement_basis(
        calculated_at=calculated_at,
        context=applicable_context(),
    )

    assert basis.price_version == "tool-insert-demo-economic-basis-2026-09"
    assert basis.calculation_policy_version == "maintenance-cost-policy-v2"
    assert len(basis.scenarios) == 4
    immediate = next(
        scenario
        for scenario in basis.scenarios
        if scenario.execution_timing.value == "immediate"
    )
    assert immediate.parts_cost is not None
    assert immediate.parts_cost.base_minor == 12251
    assert immediate.labor_rate_per_minute is not None
    assert immediate.labor_rate_per_minute.base_minor_per_minute == 292
    assert immediate.labor_rate_type == "normal"
    assert immediate.assumed_execution_at == calculated_at
    assert immediate.labor_duration is not None
    assert immediate.labor_duration.model_dump() == {
        "low_minutes": 5,
        "base_minutes": 10,
        "high_minutes": 15,
    }
    assert immediate.external_service_cost is not None
    assert immediate.external_service_cost.base_minor == 0
    assert immediate.expected_downtime is not None
    assert immediate.expected_downtime.base_minutes == 30
    assert immediate.production_loss_rate_per_minute is not None
    assert immediate.production_loss_rate_per_minute.base_minor_per_minute == 1058
    assert immediate.expected_failure_loss is not None
    assert immediate.expected_failure_loss.model_dump() == {
        "low_minor": 14152,
        "base_minor": 31074,
        "high_minor": 70210,
    }

    planned = next(
        scenario
        for scenario in basis.scenarios
        if scenario.execution_timing.value == "planned_window"
    )
    reinspect = next(
        scenario
        for scenario in basis.scenarios
        if scenario.execution_timing.value == "reinspect_after"
    )
    no_action = next(
        scenario
        for scenario in basis.scenarios
        if scenario.execution_timing.value == "no_action_baseline"
    )
    assert planned.expected_failure_loss is None
    assert planned.labor_rate_type == "night"
    assert planned.labor_rate_per_minute is not None
    assert planned.labor_rate_per_minute.base_minor_per_minute == 438
    assert planned.assumed_execution_at == datetime(2026, 9, 1, 13, 0, tzinfo=UTC)
    assert reinspect.labor_duration is None
    assert reinspect.expected_downtime is None
    assert reinspect.expected_failure_loss is None
    assert no_action.labor_duration is not None
    assert no_action.labor_duration.base_minutes == 0
    assert no_action.expected_failure_loss is not None
    assert no_action.expected_failure_loss.model_dump() == {
        "low_minor": 55261,
        "base_minor": 121336,
        "high_minor": 274151,
    }


@pytest.mark.parametrize(
    ("calculated_at", "expected_type", "expected_rate"),
    (
        (datetime(2026, 9, 1, 12, 59, tzinfo=UTC), "normal", 292),
        (datetime(2026, 9, 1, 13, 0, tzinfo=UTC), "night", 438),
        (datetime(2026, 9, 1, 20, 59, tzinfo=UTC), "night", 438),
        (datetime(2026, 9, 1, 21, 0, tzinfo=UTC), "normal", 292),
    ),
)
def test_server_time_selects_korean_night_rate_boundaries(
    calculated_at: datetime,
    expected_type: str,
    expected_rate: int,
) -> None:
    basis = JsonMaintenanceCostBasisProvider(BASIS_PATH).tool_replacement_basis(
        calculated_at=calculated_at,
        context=applicable_context(),
    )
    immediate = next(
        scenario
        for scenario in basis.scenarios
        if scenario.execution_timing.value == "immediate"
    )

    assert immediate.labor_rate_type == expected_type
    assert immediate.labor_rate_per_minute is not None
    assert immediate.labor_rate_per_minute.base_minor_per_minute == expected_rate


def test_cost_basis_rejects_timezone_naive_server_time() -> None:
    with pytest.raises(ValueError, match="timezone offset"):
        JsonMaintenanceCostBasisProvider(BASIS_PATH).tool_replacement_basis(
            calculated_at=datetime(2026, 9, 1, 10, 0),
            context=applicable_context(),
        )


@pytest.mark.parametrize(
    "context",
    (
        CostBasisResolutionContext(
            execution_mode="external",
            spare_part_available=True,
            vendor_dispatch_required=False,
        ),
        CostBasisResolutionContext(
            execution_mode="in_house",
            spare_part_available=False,
            vendor_dispatch_required=False,
        ),
        CostBasisResolutionContext(
            execution_mode="in_house",
            spare_part_available=True,
            vendor_dispatch_required=True,
        ),
    ),
)
def test_tool_cost_basis_rejects_inapplicable_operational_context(
    context: CostBasisResolutionContext,
) -> None:
    with pytest.raises(ValueError, match="cost basis is not applicable"):
        JsonMaintenanceCostBasisProvider(BASIS_PATH).tool_replacement_basis(
            calculated_at=datetime(2026, 9, 1, 1, 0, tzinfo=UTC),
            context=context,
        )


def test_versioned_basis_produces_partial_fail_closed_cost_comparison() -> None:
    calculated_at = datetime(2026, 8, 31, tzinfo=UTC)
    basis = JsonMaintenanceCostBasisProvider(BASIS_PATH).tool_replacement_basis(
        calculated_at=calculated_at,
        context=applicable_context(),
    )
    result = calculate_tool_replacement_cost_scenarios(
        ToolReplacementCostAnalysisInput(
            analysis_id="cost-analysis-demo-basis",
            organization_id="org-ontology-demo",
            project_id="manufacturing-demo-project",
            workspace_id="manufacturing-demo",
            asset_id="CNC-S04-L04-01",
            equipment_id="CNC-S04-L04-01",
            calculated_at=calculated_at,
            based_on=CostAnalysisBasis(
                product_result_id="product-result-demo",
                evidence_id="evidence-demo",
                inspection_work_order_id="inspection-work-order-demo",
                inspection_result_id="inspection-result-demo",
                sop_id="SOP-DEMO-CNC-ROTATING-ASSEMBLY-001",
                sop_version="1.1",
            ),
            action_candidate_id="candidate-tool-replacement-demo",
            action_code="TOOL_REPLACEMENT",
            currency=basis.currency,
            currency_minor_unit=basis.currency_minor_unit,
            scenarios=basis.scenarios,
            assumptions=basis.assumptions,
            input_sources=basis.input_sources,
            price_version=basis.price_version,
            calculation_policy_version=basis.calculation_policy_version,
        )
    )

    immediate = next(
        option
        for option in result.options
        if option.execution_timing.value == "immediate"
    )
    assert immediate.calculation_status.value == "calculated"
    assert immediate.total_expected_cost is not None
    assert immediate.total_expected_cost.model_dump() == {
        "low_minor": 40553,
        "base_minor": 77985,
        "high_minor": 143946,
    }
    assert result.lowest_calculated_cost_option_id == immediate.option_id
    assert result.missing_inputs == (
        "expected_downtime",
        "expected_failure_loss",
        "labor_duration",
    )
