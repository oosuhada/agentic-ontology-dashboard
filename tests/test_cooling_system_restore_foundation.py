from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.maintenance import (
    ConfidenceLevel,
    CostAnalysisBasis,
    CostInputSource,
    CostInputSourceKind,
    EquipmentIdentity,
    ExecutionTiming,
    InspectionResult,
    MaintenanceActionCode,
    MaintenanceCostAnalysisInput,
    MaintenanceScenarioInput,
    SensitivityDuration,
    SensitivityMoney,
    SensitivityRatePerMinute,
    calculate_maintenance_cost_scenarios,
    create_operations_manual_recommendation,
    derive_cooling_system_restore_action_candidate,
    derive_tool_replacement_action_candidate,
)


def _inspection_result() -> InspectionResult:
    return InspectionResult(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        inspection_result_id="inspection-result-cooling-001",
        work_order_id="inspection-work-order-001",
        event_id="event-001",
        asset_id="CNC-001",
        equipment_id="CNC-001",
        asset_type="cnc",
        outcome="maintenance_recommended",
        checklist=(
            {
                "item_id": "cooling-path",
                "status": "fail",
                "note": "coolant flow is restricted",
            },
        ),
        measurements=(
            {"name": "coolant_temperature_c", "value": 92, "unit": "C"},
        ),
        findings=("cooling path requires maintenance",),
        note="cooling path failure confirmed",
        recorded_by="engineer-1",
        recorded_at=datetime(2026, 8, 31, 5, 0, tzinfo=UTC),
    )


def _money(value: int) -> SensitivityMoney:
    return SensitivityMoney(
        low_minor=value,
        base_minor=value,
        high_minor=value,
    )


def _duration(value: int) -> SensitivityDuration:
    return SensitivityDuration(
        low_minutes=value,
        base_minutes=value,
        high_minutes=value,
    )


def _rate(value: int) -> SensitivityRatePerMinute:
    return SensitivityRatePerMinute(
        low_minor_per_minute=value,
        base_minor_per_minute=value,
        high_minor_per_minute=value,
    )


def _scenario(timing: ExecutionTiming, value: int) -> MaintenanceScenarioInput:
    return MaintenanceScenarioInput(
        execution_timing=timing,
        parts_cost=_money(value),
        labor_duration=_duration(10),
        labor_rate_per_minute=_rate(100),
        external_service_cost=_money(0),
        expected_downtime=_duration(20),
        production_loss_rate_per_minute=_rate(50),
        expected_failure_loss=_money(value),
        confidence=ConfidenceLevel.MEDIUM,
    )


def test_cooling_candidate_requires_typed_inspection_evidence() -> None:
    inspection = _inspection_result()

    candidate = derive_cooling_system_restore_action_candidate(inspection)

    assert candidate.action_code == "COOLING_SYSTEM_RESTORE"
    assert candidate.inspection_result_id == inspection.inspection_result_id
    assert candidate.basis_codes == (
        "inspection.checklist:cooling-path:fail",
        "inspection.measurement:coolant_temperature_c",
    )
    with pytest.raises(ValueError, match="TOOL_REPLACEMENT candidate requires"):
        derive_tool_replacement_action_candidate(inspection)


def test_cooling_manual_recommendation_preserves_action_identity() -> None:
    recommendation = create_operations_manual_recommendation(
        identity=EquipmentIdentity(
            organization_id="org-1",
            project_id="project-1",
            workspace_id="workspace-1",
            asset_id="CNC-001",
            equipment_id="CNC-001",
            asset_type="cnc",
        ),
        event_id="event-001",
        source_product_result_id="result-001",
        source_evidence_id="evidence-001",
        source_schema_version="product-result-artifact-v1",
        source_inspection_work_order_id="inspection-work-order-001",
        source_inspection_reference="inspection-result-cooling-001",
        authored_by="manager-1",
        authored_at=datetime(2026, 8, 31, 5, 5, tzinfo=UTC),
        basis=("inspection cooling-path failure",),
        action_code=MaintenanceActionCode.COOLING_SYSTEM_RESTORE,
    )

    assert recommendation.kind == recommendation.action_code == "COOLING_SYSTEM_RESTORE"
    assert recommendation.label == "냉각 시스템 복구"
    assert recommendation.materialization_key.endswith(":COOLING_SYSTEM_RESTORE")


def test_cooling_cost_scenarios_remain_read_only_and_deterministic() -> None:
    candidate = derive_cooling_system_restore_action_candidate(_inspection_result())
    source = MaintenanceCostAnalysisInput(
        analysis_id="cost-analysis-cooling-001",
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        asset_id="CNC-001",
        equipment_id="CNC-001",
        calculated_at=datetime(2026, 8, 31, 5, 10, tzinfo=UTC),
        based_on=CostAnalysisBasis(
            product_result_id="result-001",
            evidence_id="evidence-001",
            inspection_work_order_id="inspection-work-order-001",
            inspection_result_id="inspection-result-cooling-001",
            sop_id="sop-cooling-inspection",
            sop_version="1.1",
        ),
        action_candidate_id=candidate.action_candidate_id,
        action_code=MaintenanceActionCode.COOLING_SYSTEM_RESTORE,
        currency="KRW",
        currency_minor_unit=0,
        scenarios=(
            _scenario(ExecutionTiming.IMMEDIATE, 50_000),
            _scenario(ExecutionTiming.PLANNED_WINDOW, 30_000),
            _scenario(ExecutionTiming.REINSPECT_AFTER, 80_000),
            _scenario(ExecutionTiming.NO_ACTION_BASELINE, 200_000),
        ),
        assumptions=("cost-only decision support",),
        input_sources=(
            CostInputSource(
                input_name="cooling_restore_price",
                source_kind=CostInputSourceKind.QUOTED,
                source_reference="quote-001",
                confidence=ConfidenceLevel.MEDIUM,
            ),
        ),
        price_version="quote-001",
        calculation_policy_version="cooling-restore-cost-policy-v1",
    )

    first = calculate_maintenance_cost_scenarios(source)
    second = calculate_maintenance_cost_scenarios(source)

    assert first == second
    assert {option.action_code for option in first.options} == {
        MaintenanceActionCode.COOLING_SYSTEM_RESTORE
    }
    selected = next(
        option
        for option in first.options
        if option.option_id == first.lowest_calculated_cost_option_id
    )
    assert selected.execution_timing is ExecutionTiming.PLANNED_WINDOW
    assert "recommendation_id" not in first.model_dump(mode="json")
