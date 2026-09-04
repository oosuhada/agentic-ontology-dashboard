from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.infra.maintenance_cost_basis_provider import JsonMaintenanceCostBasisProvider
from app.maintenance import CostAnalysisBasis, calculate_maintenance_cost_scenarios
from app.maintenance.cost_basis import CostBasisResolutionContext
from app.maintenance.cost_calculator import MaintenanceCostAnalysisInput


ROOT = Path(__file__).resolve().parents[1]
TOOL_BASIS_PATH = (
    ROOT
    / "data"
    / "fixtures"
    / "maintenance_cost"
    / "tool-insert-cost-basis-v1.json"
)
COOLING_BASIS_PATH = (
    ROOT
    / "data"
    / "fixtures"
    / "maintenance_cost"
    / "cooling-system-restore-cost-basis-v1.json"
)


def provider() -> JsonMaintenanceCostBasisProvider:
    return JsonMaintenanceCostBasisProvider(TOOL_BASIS_PATH, COOLING_BASIS_PATH)


def load_basis() -> dict:
    return json.loads(COOLING_BASIS_PATH.read_text(encoding="utf-8"))


def applicable_context() -> CostBasisResolutionContext:
    return CostBasisResolutionContext(
        execution_mode="in_house",
        vendor_dispatch_required=False,
        component_replacement_required=False,
    )


def test_cooling_basis_has_a_bounded_no_replacement_scope() -> None:
    basis = load_basis()

    assert basis["action_code"] == "COOLING_SYSTEM_RESTORE"
    assert basis["applicability"] == {
        "execution_mode": "in_house",
        "vendor_dispatch_required": False,
        "component_replacement_required": False,
    }
    assert basis["restoration_scope"]["operation"] == "clean_clear_and_verify"
    assert basis["restoration_scope"]["component_replacement_included"] is False
    assert "fan replacement" in basis["restoration_scope"]["excluded_operations"]
    assert "separate quoted Action/basis" in basis["restoration_scope"]["scope_rule"]
    assert basis["parts_cost"]["reference_minor"] == 0
    assert basis["external_service_cost"]["reference_minor"] == 0


def test_cooling_basis_marks_site_unknowns_as_demo_assumptions() -> None:
    basis = load_basis()
    policy = basis["demo_policy_inputs"]

    assert policy["labor_duration_minutes"]["source_kind"] == "explicit_demo_assumption"
    assert policy["expected_downtime_minutes"]["source_kind"] == "explicit_demo_assumption"
    assert policy["production_loss_rate_minor_per_minute"]["source_kind"] == (
        "synthetic_scenario_estimate"
    )
    assert policy["expected_failure_loss_minor"]["scenario_values"] == {
        "immediate": {"low": 0, "base": 0, "high": 0},
        "planned_window": None,
        "reinspect_after": None,
        "no_action_baseline": None,
    }


def test_cooling_provider_uses_server_time_and_keeps_future_risk_unknown() -> None:
    calculated_at = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)
    basis = provider().cooling_system_restore_basis(
        calculated_at=calculated_at,
        context=applicable_context(),
    )

    assert basis.price_version == "cooling-restore-demo-economic-basis-2026-09"
    assert basis.calculation_policy_version == "maintenance-cost-policy-v2"
    immediate = next(
        item for item in basis.scenarios if item.execution_timing.value == "immediate"
    )
    planned = next(
        item
        for item in basis.scenarios
        if item.execution_timing.value == "planned_window"
    )
    assert immediate.assumed_execution_at == calculated_at
    assert immediate.labor_rate_type == "normal"
    assert immediate.labor_rate_per_minute is not None
    assert immediate.labor_rate_per_minute.base_minor_per_minute == 292
    assert immediate.parts_cost is not None
    assert immediate.parts_cost.base_minor == 0
    assert immediate.external_service_cost is not None
    assert immediate.external_service_cost.base_minor == 0
    assert immediate.labor_duration is not None
    assert immediate.labor_duration.base_minutes == 45
    assert immediate.expected_downtime is not None
    assert immediate.expected_downtime.base_minutes == 60
    assert immediate.expected_failure_loss is not None
    assert immediate.expected_failure_loss.base_minor == 0
    assert planned.assumed_execution_at == datetime(2026, 9, 1, 13, 0, tzinfo=UTC)
    assert planned.labor_rate_type == "night"
    assert planned.labor_rate_per_minute is not None
    assert planned.labor_rate_per_minute.base_minor_per_minute == 438
    assert planned.expected_failure_loss is None


@pytest.mark.parametrize(
    ("calculated_at", "expected_type", "expected_rate"),
    (
        (datetime(2026, 9, 1, 12, 59, tzinfo=UTC), "normal", 292),
        (datetime(2026, 9, 1, 13, 0, tzinfo=UTC), "night", 438),
        (datetime(2026, 9, 1, 20, 59, tzinfo=UTC), "night", 438),
        (datetime(2026, 9, 1, 21, 0, tzinfo=UTC), "normal", 292),
    ),
)
def test_cooling_server_time_selects_korean_night_rate_boundaries(
    calculated_at: datetime,
    expected_type: str,
    expected_rate: int,
) -> None:
    basis = provider().cooling_system_restore_basis(
        calculated_at=calculated_at,
        context=applicable_context(),
    )
    immediate = next(
        item for item in basis.scenarios if item.execution_timing.value == "immediate"
    )

    assert immediate.labor_rate_type == expected_type
    assert immediate.labor_rate_per_minute is not None
    assert immediate.labor_rate_per_minute.base_minor_per_minute == expected_rate


def test_cooling_cost_basis_rejects_timezone_naive_server_time() -> None:
    with pytest.raises(ValueError, match="timezone offset"):
        provider().cooling_system_restore_basis(
            calculated_at=datetime(2026, 9, 1, 10, 0),
            context=applicable_context(),
        )


@pytest.mark.parametrize(
    "context",
    (
        CostBasisResolutionContext(
            execution_mode="external",
            vendor_dispatch_required=False,
            component_replacement_required=False,
        ),
        CostBasisResolutionContext(
            execution_mode="in_house",
            vendor_dispatch_required=True,
            component_replacement_required=False,
        ),
        CostBasisResolutionContext(
            execution_mode="in_house",
            vendor_dispatch_required=False,
            component_replacement_required=True,
        ),
    ),
)
def test_cooling_cost_basis_rejects_inapplicable_operational_context(
    context: CostBasisResolutionContext,
) -> None:
    with pytest.raises(ValueError, match="cost basis is not applicable"):
        provider().cooling_system_restore_basis(
            calculated_at=datetime(2026, 9, 1, 1, 0, tzinfo=UTC),
            context=context,
        )


def test_cooling_basis_calculates_immediate_only_and_fails_closed_elsewhere() -> None:
    calculated_at = datetime(2026, 9, 1, 1, 0, tzinfo=UTC)
    basis = provider().cooling_system_restore_basis(
        calculated_at=calculated_at,
        context=applicable_context(),
    )
    result = calculate_maintenance_cost_scenarios(
        MaintenanceCostAnalysisInput(
            analysis_id="cost-analysis-cooling-basis",
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
                sop_id="SOP-DEMO-COOLING-SYSTEM-001",
                sop_version="1.1",
            ),
            action_candidate_id="candidate-cooling-restore-demo",
            action_code="COOLING_SYSTEM_RESTORE",
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
        "low_minor": 46830,
        "base_minor": 76620,
        "high_minor": 131730,
    }
    assert result.lowest_calculated_cost_option_id == immediate.option_id
    assert result.missing_inputs == ("expected_failure_loss",)
