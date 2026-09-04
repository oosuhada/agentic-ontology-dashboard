from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.maintenance import (
    CalculationStatus,
    ConfidenceLevel,
    CostAnalysisBasis,
    CostInputSource,
    CostInputSourceKind,
    ExecutionTiming,
    MaintenanceActionCode,
    SensitivityDuration,
    SensitivityMoney,
    SensitivityRatePerMinute,
    ToolReplacementCostAnalysisInput,
    ToolReplacementScenarioInput,
    calculate_tool_replacement_cost_scenarios,
)


def money(low: int, base: int, high: int) -> SensitivityMoney:
    return SensitivityMoney(low_minor=low, base_minor=base, high_minor=high)


def duration(low: int, base: int, high: int) -> SensitivityDuration:
    return SensitivityDuration(
        low_minutes=low, base_minutes=base, high_minutes=high
    )


def rate(low: int, base: int, high: int) -> SensitivityRatePerMinute:
    return SensitivityRatePerMinute(
        low_minor_per_minute=low,
        base_minor_per_minute=base,
        high_minor_per_minute=high,
    )


def scenario(
    timing: ExecutionTiming,
    *,
    parts: SensitivityMoney,
    labor_minutes: SensitivityDuration,
    labor_rate: SensitivityRatePerMinute,
    external: SensitivityMoney,
    downtime: SensitivityDuration,
    production_rate: SensitivityRatePerMinute,
    failure_loss: SensitivityMoney | None,
    confidence: ConfidenceLevel,
) -> ToolReplacementScenarioInput:
    return ToolReplacementScenarioInput(
        execution_timing=timing,
        parts_cost=parts,
        labor_duration=labor_minutes,
        labor_rate_per_minute=labor_rate,
        external_service_cost=external,
        expected_downtime=downtime,
        production_loss_rate_per_minute=production_rate,
        expected_failure_loss=failure_loss,
        confidence=confidence,
    )


def analysis_input(*, missing_failure_loss: bool = False) -> ToolReplacementCostAnalysisInput:
    zero = money(0, 0, 0)
    return ToolReplacementCostAnalysisInput(
        analysis_id="cost-analysis-cnc-001",
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        asset_id="CNC-S01-L01-04",
        equipment_id="CNC-S01-L01-04",
        calculated_at=datetime(2026, 8, 29, 6, 0, tzinfo=UTC),
        based_on=CostAnalysisBasis(
            product_result_id="product-result-cnc-001",
            evidence_id="evidence-cnc-001",
            inspection_work_order_id="inspection-wo-cnc-001",
            inspection_result_id="inspection-result-cnc-001",
            sop_id="sop-cnc-tool-inspection",
            sop_version="1.1",
        ),
        action_candidate_id="candidate-tool-replacement-001",
        action_code=MaintenanceActionCode.TOOL_REPLACEMENT,
        currency="KRW",
        currency_minor_unit=0,
        scenarios=(
            scenario(
                ExecutionTiming.IMMEDIATE,
                parts=money(45000, 50000, 60000),
                labor_minutes=duration(50, 60, 70),
                labor_rate=rate(500, 500, 600),
                external=zero,
                downtime=duration(40, 50, 70),
                production_rate=rate(1000, 1200, 1500),
                failure_loss=(None if missing_failure_loss else money(10000, 20000, 40000)),
                confidence=ConfidenceLevel.MEDIUM,
            ),
            scenario(
                ExecutionTiming.PLANNED_WINDOW,
                parts=money(45000, 50000, 60000),
                labor_minutes=duration(40, 50, 60),
                labor_rate=rate(500, 500, 600),
                external=zero,
                downtime=duration(20, 30, 45),
                production_rate=rate(800, 1000, 1200),
                failure_loss=(None if missing_failure_loss else money(10000, 20000, 50000)),
                confidence=ConfidenceLevel.MEDIUM,
            ),
            scenario(
                ExecutionTiming.REINSPECT_AFTER,
                parts=money(5000, 10000, 15000),
                labor_minutes=duration(15, 20, 30),
                labor_rate=rate(500, 500, 600),
                external=zero,
                downtime=duration(15, 25, 40),
                production_rate=rate(800, 1000, 1200),
                failure_loss=(None if missing_failure_loss else money(70000, 130000, 220000)),
                confidence=ConfidenceLevel.LOW,
            ),
            scenario(
                ExecutionTiming.NO_ACTION_BASELINE,
                parts=zero,
                labor_minutes=duration(0, 0, 0),
                labor_rate=rate(0, 0, 0),
                external=zero,
                downtime=duration(0, 0, 0),
                production_rate=rate(0, 0, 0),
                failure_loss=(
                    None
                    if missing_failure_loss
                    else money(100000, 250000, 500000)
                ),
                confidence=ConfidenceLevel.LOW,
            ),
        ),
        assumptions=(
            "Failure loss is supplied as sensitivity input, not predicted here.",
        ),
        input_sources=(
            CostInputSource(
                input_name="maintenance_price_policy",
                source_kind=CostInputSourceKind.POLICY,
                source_reference="maintenance-price-2026-08",
                confidence=ConfidenceLevel.MEDIUM,
            ),
        ),
        price_version="maintenance-price-2026-08",
        calculation_policy_version="tool-replacement-cost-policy-v1",
    )


def test_calculator_is_deterministic_and_sums_derived_components() -> None:
    source = analysis_input()

    first = calculate_tool_replacement_cost_scenarios(source)
    second = calculate_tool_replacement_cost_scenarios(source)

    assert first == second
    immediate = next(
        option
        for option in first.options
        if option.execution_timing is ExecutionTiming.IMMEDIATE
    )
    assert immediate.labor_cost == money(25000, 30000, 42000)
    assert immediate.production_loss == money(40000, 60000, 105000)
    assert immediate.total_expected_cost == money(120000, 160000, 247000)


def test_calculator_input_rejects_mismatched_operations_identity() -> None:
    payload = analysis_input().model_dump()
    payload["equipment_id"] = "CNC-OTHER"

    with pytest.raises(ValidationError, match="equipment_id = asset_id"):
        ToolReplacementCostAnalysisInput.model_validate(payload)


def test_calculator_selects_lowest_base_cost_without_creating_decision_fields() -> None:
    result = calculate_tool_replacement_cost_scenarios(analysis_input())
    selected = next(
        option
        for option in result.options
        if option.option_id == result.lowest_calculated_cost_option_id
    )

    assert selected.execution_timing is ExecutionTiming.PLANNED_WINDOW
    payload = result.model_dump(mode="json")
    forbidden = {
        "recommendation_id",
        "recommendation_decision_id",
        "work_order_id",
        "maintenance_action_id",
        "baseline_probability",
        "intervention_probability",
    }
    assert forbidden.isdisjoint(payload)


def test_missing_failure_loss_returns_insufficient_without_inventing_probability() -> None:
    result = calculate_tool_replacement_cost_scenarios(
        analysis_input(missing_failure_loss=True)
    )

    assert result.lowest_calculated_cost_option_id is None
    assert result.missing_inputs == ("expected_failure_loss",)
    assert all(
        option.calculation_status is CalculationStatus.INSUFFICIENT
        and option.total_expected_cost is None
        and option.confidence is ConfidenceLevel.INSUFFICIENT
        for option in result.options
    )


def test_zero_costs_are_explicit_inputs_not_missing_defaults() -> None:
    result = calculate_tool_replacement_cost_scenarios(analysis_input())
    baseline = next(
        option
        for option in result.options
        if option.execution_timing is ExecutionTiming.NO_ACTION_BASELINE
    )

    assert baseline.parts_cost == money(0, 0, 0)
    assert baseline.missing_inputs == ()
    assert baseline.total_expected_cost == money(100000, 250000, 500000)
