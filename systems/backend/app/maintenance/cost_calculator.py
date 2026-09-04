"""Deterministic cost scenario calculation for typed Maintenance Actions."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import Field, model_validator

from .cost_analysis_schema import (
    CalculationStatus,
    ConfidenceLevel,
    CostAnalysisBasis,
    CostInputSource,
    ExecutionTiming,
    FrozenModel,
    LimitationCode,
    MaintenanceActionCode,
    MaintenanceCostOption,
    MaintenanceCostScenarioResult,
    SensitivityDuration,
    SensitivityMoney,
)


class SensitivityRatePerMinute(FrozenModel):
    """Money minor units per minute for low/base/high sensitivity bands."""

    low_minor_per_minute: int = Field(ge=0)
    base_minor_per_minute: int = Field(ge=0)
    high_minor_per_minute: int = Field(ge=0)

    @model_validator(mode="after")
    def require_ordered_range(self) -> SensitivityRatePerMinute:
        if not (
            self.low_minor_per_minute
            <= self.base_minor_per_minute
            <= self.high_minor_per_minute
        ):
            raise ValueError("rate range must satisfy low <= base <= high")
        return self


class MaintenanceScenarioInput(FrozenModel):
    execution_timing: ExecutionTiming
    assumed_execution_at: datetime | None = None
    labor_rate_type: Literal["normal", "night", "not_applicable"] | None = None
    parts_cost: SensitivityMoney | None
    labor_duration: SensitivityDuration | None
    labor_rate_per_minute: SensitivityRatePerMinute | None
    external_service_cost: SensitivityMoney | None
    expected_downtime: SensitivityDuration | None
    production_loss_rate_per_minute: SensitivityRatePerMinute | None
    expected_failure_loss: SensitivityMoney | None
    confidence: Literal[
        ConfidenceLevel.HIGH,
        ConfidenceLevel.MEDIUM,
        ConfidenceLevel.LOW,
    ]


class MaintenanceCostAnalysisInput(FrozenModel):
    analysis_id: str = Field(min_length=1, max_length=240)
    organization_id: str = Field(min_length=1, max_length=160)
    project_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)
    asset_id: str = Field(min_length=1, max_length=240)
    equipment_id: str = Field(min_length=1, max_length=240)
    calculated_at: datetime
    based_on: CostAnalysisBasis
    action_candidate_id: str = Field(min_length=1, max_length=240)
    action_code: MaintenanceActionCode
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    currency_minor_unit: Literal[0, 2, 3]
    scenarios: tuple[MaintenanceScenarioInput, ...] = Field(min_length=4, max_length=4)
    assumptions: tuple[str, ...]
    input_sources: tuple[CostInputSource, ...] = Field(min_length=1)
    price_version: str = Field(min_length=1, max_length=160)
    calculation_policy_version: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_complete_scenario_set(self) -> MaintenanceCostAnalysisInput:
        if self.asset_id != self.equipment_id:
            raise ValueError("Operations cost analysis requires equipment_id = asset_id")
        timings = [scenario.execution_timing for scenario in self.scenarios]
        if len(set(timings)) != len(timings) or set(timings) != set(ExecutionTiming):
            raise ValueError("Maintenance cost analysis requires four unique timing scenarios")
        return self


def _multiply_duration_by_rate(
    duration: SensitivityDuration,
    rate: SensitivityRatePerMinute,
) -> SensitivityMoney:
    return SensitivityMoney(
        low_minor=duration.low_minutes * rate.low_minor_per_minute,
        base_minor=duration.base_minutes * rate.base_minor_per_minute,
        high_minor=duration.high_minutes * rate.high_minor_per_minute,
    )


def _sum_money(*components: SensitivityMoney) -> SensitivityMoney:
    return SensitivityMoney(
        low_minor=sum(component.low_minor for component in components),
        base_minor=sum(component.base_minor for component in components),
        high_minor=sum(component.high_minor for component in components),
    )


def _option_id(
    *, analysis_id: str, action_candidate_id: str, timing: ExecutionTiming
) -> str:
    digest = sha256(
        f"{analysis_id}:{action_candidate_id}:{timing.value}".encode("utf-8")
    ).hexdigest()[:24]
    return f"cost-option-{digest}"


def _calculate_option(
    source: MaintenanceCostAnalysisInput,
    scenario: MaintenanceScenarioInput,
) -> MaintenanceCostOption:
    missing_inputs: list[str] = []
    if scenario.parts_cost is None:
        missing_inputs.append("parts_cost")
    if scenario.labor_duration is None:
        missing_inputs.append("labor_duration")
    if scenario.labor_rate_per_minute is None:
        missing_inputs.append("labor_rate_per_minute")
    if scenario.external_service_cost is None:
        missing_inputs.append("external_service_cost")
    if scenario.expected_downtime is None:
        missing_inputs.append("expected_downtime")
    if scenario.production_loss_rate_per_minute is None:
        missing_inputs.append("production_loss_rate_per_minute")
    if scenario.expected_failure_loss is None:
        missing_inputs.append("expected_failure_loss")

    labor_cost = None
    if scenario.labor_duration is not None and scenario.labor_rate_per_minute is not None:
        labor_cost = _multiply_duration_by_rate(
            scenario.labor_duration, scenario.labor_rate_per_minute
        )

    production_loss = None
    if (
        scenario.expected_downtime is not None
        and scenario.production_loss_rate_per_minute is not None
    ):
        production_loss = _multiply_duration_by_rate(
            scenario.expected_downtime,
            scenario.production_loss_rate_per_minute,
        )

    total_expected_cost = None
    if not missing_inputs:
        assert scenario.parts_cost is not None
        assert labor_cost is not None
        assert scenario.external_service_cost is not None
        assert production_loss is not None
        assert scenario.expected_failure_loss is not None
        total_expected_cost = _sum_money(
            scenario.parts_cost,
            labor_cost,
            scenario.external_service_cost,
            production_loss,
            scenario.expected_failure_loss,
        )

    return MaintenanceCostOption(
        option_id=_option_id(
            analysis_id=source.analysis_id,
            action_candidate_id=source.action_candidate_id,
            timing=scenario.execution_timing,
        ),
        action_candidate_id=source.action_candidate_id,
        action_code=source.action_code,
        execution_timing=scenario.execution_timing,
        assumed_execution_at=scenario.assumed_execution_at,
        labor_rate_type=scenario.labor_rate_type,
        labor_rate_base_minor_per_minute=(
            scenario.labor_rate_per_minute.base_minor_per_minute
            if scenario.labor_rate_per_minute is not None
            else None
        ),
        calculation_status=(
            CalculationStatus.INSUFFICIENT
            if missing_inputs
            else CalculationStatus.CALCULATED
        ),
        parts_cost=scenario.parts_cost,
        labor_cost=labor_cost,
        external_service_cost=scenario.external_service_cost,
        production_loss=production_loss,
        expected_failure_loss=scenario.expected_failure_loss,
        total_expected_cost=total_expected_cost,
        expected_downtime=scenario.expected_downtime,
        confidence=(
            ConfidenceLevel.INSUFFICIENT if missing_inputs else scenario.confidence
        ),
        missing_inputs=tuple(missing_inputs),
    )


def calculate_maintenance_cost_scenarios(
    source: MaintenanceCostAnalysisInput,
) -> MaintenanceCostScenarioResult:
    """Calculate cost-only scenarios without creating a recommendation or command."""

    options = tuple(_calculate_option(source, scenario) for scenario in source.scenarios)
    calculated = [
        option
        for option in options
        if option.calculation_status is CalculationStatus.CALCULATED
    ]
    lowest_option_id = None
    if calculated:
        lowest_option_id = min(
            calculated,
            key=lambda option: (
                option.total_expected_cost.base_minor,  # type: ignore[union-attr]
                option.option_id,
            ),
        ).option_id

    missing_inputs = tuple(
        sorted(
            {
                missing_input
                for option in options
                for missing_input in option.missing_inputs
            }
        )
    )
    return MaintenanceCostScenarioResult(
        schema_version="maintenance-cost-scenario-v1.0",
        analysis_id=source.analysis_id,
        organization_id=source.organization_id,
        project_id=source.project_id,
        workspace_id=source.workspace_id,
        asset_id=source.asset_id,
        equipment_id=source.equipment_id,
        calculated_at=source.calculated_at,
        based_on=source.based_on,
        currency=source.currency,
        currency_minor_unit=source.currency_minor_unit,
        options=options,
        lowest_calculated_cost_option_id=lowest_option_id,
        assumptions=source.assumptions,
        input_sources=source.input_sources,
        missing_inputs=missing_inputs,
        price_version=source.price_version,
        calculation_policy_version=source.calculation_policy_version,
        limitations=tuple(LimitationCode),
    )


class ToolReplacementScenarioInput(MaintenanceScenarioInput):
    """Backward-compatible request type for the first Action slice."""


class ToolReplacementCostAnalysisInput(MaintenanceCostAnalysisInput):
    """Keep the existing TOOL_REPLACEMENT input contract strict and named."""

    action_code: Literal[MaintenanceActionCode.TOOL_REPLACEMENT]
    scenarios: tuple[ToolReplacementScenarioInput, ...] = Field(
        min_length=4,
        max_length=4,
    )


def calculate_tool_replacement_cost_scenarios(
    source: ToolReplacementCostAnalysisInput,
) -> MaintenanceCostScenarioResult:
    if source.action_code is not MaintenanceActionCode.TOOL_REPLACEMENT:
        raise ValueError("tool replacement calculator requires TOOL_REPLACEMENT")
    return calculate_maintenance_cost_scenarios(source)
