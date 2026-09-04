"""Typed contract for read-only maintenance cost scenario results."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MaintenanceActionCode(StrEnum):
    TOOL_REPLACEMENT = "TOOL_REPLACEMENT"
    COOLING_SYSTEM_RESTORE = "COOLING_SYSTEM_RESTORE"


class ExecutionTiming(StrEnum):
    """Comparison timing; reinspect/no-action values are not MaintenanceActions."""

    IMMEDIATE = "immediate"
    PLANNED_WINDOW = "planned_window"
    REINSPECT_AFTER = "reinspect_after"
    NO_ACTION_BASELINE = "no_action_baseline"


class CalculationStatus(StrEnum):
    CALCULATED = "calculated"
    INSUFFICIENT = "insufficient"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class CostInputSourceKind(StrEnum):
    OBSERVED = "observed"
    QUOTED = "quoted"
    PUBLIC_REFERENCE = "public_reference"
    POLICY = "policy"
    ASSUMPTION = "assumption"


class LimitationCode(StrEnum):
    DECISION_SUPPORT_ONLY = "DECISION_SUPPORT_ONLY"
    NOT_RECOMMENDATION = "NOT_RECOMMENDATION"
    NOT_APPROVAL = "NOT_APPROVAL"
    NOT_EXECUTION_COMMAND = "NOT_EXECUTION_COMMAND"
    COST_ESTIMATE_NOT_GUARANTEE = "COST_ESTIMATE_NOT_GUARANTEE"


class SensitivityMoney(FrozenModel):
    """Money in ISO-4217 minor units, avoiding binary floating-point ambiguity."""

    low_minor: int = Field(ge=0)
    base_minor: int = Field(ge=0)
    high_minor: int = Field(ge=0)

    @model_validator(mode="after")
    def require_ordered_range(self) -> SensitivityMoney:
        if not self.low_minor <= self.base_minor <= self.high_minor:
            raise ValueError("money range must satisfy low <= base <= high")
        return self


class SensitivityDuration(FrozenModel):
    low_minutes: int = Field(ge=0)
    base_minutes: int = Field(ge=0)
    high_minutes: int = Field(ge=0)

    @model_validator(mode="after")
    def require_ordered_range(self) -> SensitivityDuration:
        if not self.low_minutes <= self.base_minutes <= self.high_minutes:
            raise ValueError("duration range must satisfy low <= base <= high")
        return self


class CostAnalysisBasis(FrozenModel):
    product_result_id: str = Field(min_length=1, max_length=240)
    evidence_id: str = Field(min_length=1, max_length=240)
    inspection_work_order_id: str = Field(min_length=1, max_length=240)
    inspection_result_id: str = Field(min_length=1, max_length=240)
    sop_id: str = Field(min_length=1, max_length=240)
    sop_version: str = Field(min_length=1, max_length=160)


class CostInputSource(FrozenModel):
    input_name: str = Field(min_length=1, max_length=160)
    source_kind: CostInputSourceKind
    source_reference: str = Field(min_length=1, max_length=500)
    confidence: Literal[
        ConfidenceLevel.HIGH,
        ConfidenceLevel.MEDIUM,
        ConfidenceLevel.LOW,
    ]


class MaintenanceCostOption(FrozenModel):
    """A timing comparison for an authoritative, externally owned Action candidate."""

    option_id: str = Field(min_length=1, max_length=240)
    action_candidate_id: str = Field(min_length=1, max_length=240)
    action_code: MaintenanceActionCode
    execution_timing: ExecutionTiming
    assumed_execution_at: datetime | None = None
    labor_rate_type: Literal["normal", "night", "not_applicable"] | None = None
    labor_rate_base_minor_per_minute: int | None = Field(default=None, ge=0)
    calculation_status: CalculationStatus
    parts_cost: SensitivityMoney | None
    labor_cost: SensitivityMoney | None
    external_service_cost: SensitivityMoney | None
    production_loss: SensitivityMoney | None
    expected_failure_loss: SensitivityMoney | None
    total_expected_cost: SensitivityMoney | None
    expected_downtime: SensitivityDuration | None
    confidence: ConfidenceLevel
    missing_inputs: tuple[str, ...]

    @model_validator(mode="after")
    def require_status_consistency(self) -> MaintenanceCostOption:
        components = (
            self.parts_cost,
            self.labor_cost,
            self.external_service_cost,
            self.production_loss,
            self.expected_failure_loss,
            self.expected_downtime,
        )
        if self.calculation_status is CalculationStatus.INSUFFICIENT:
            if self.total_expected_cost is not None:
                raise ValueError("insufficient option cannot publish total_expected_cost")
            if not self.missing_inputs:
                raise ValueError("insufficient option must identify missing_inputs")
            if self.confidence is not ConfidenceLevel.INSUFFICIENT:
                raise ValueError("insufficient option requires insufficient confidence")
            return self

        if any(value is None for value in components) or self.total_expected_cost is None:
            raise ValueError("calculated option requires every cost and downtime field")
        if self.missing_inputs:
            raise ValueError("calculated option cannot contain missing_inputs")
        if self.confidence is ConfidenceLevel.INSUFFICIENT:
            raise ValueError("calculated option cannot use insufficient confidence")

        assert self.parts_cost is not None
        assert self.labor_cost is not None
        assert self.external_service_cost is not None
        assert self.production_loss is not None
        assert self.expected_failure_loss is not None
        assert self.total_expected_cost is not None
        for band in ("low_minor", "base_minor", "high_minor"):
            expected = sum(
                getattr(component, band)
                for component in (
                    self.parts_cost,
                    self.labor_cost,
                    self.external_service_cost,
                    self.production_loss,
                    self.expected_failure_loss,
                )
            )
            if getattr(self.total_expected_cost, band) != expected:
                raise ValueError("total_expected_cost must equal its cost components")
        return self


class MaintenanceCostScenarioResult(FrozenModel):
    schema_version: Literal["maintenance-cost-scenario-v1.0"]
    analysis_id: str = Field(min_length=1, max_length=240)
    organization_id: str = Field(min_length=1, max_length=160)
    project_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)
    asset_id: str = Field(min_length=1, max_length=240)
    equipment_id: str = Field(min_length=1, max_length=240)
    calculated_at: datetime
    based_on: CostAnalysisBasis
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    currency_minor_unit: Literal[0, 2, 3]
    options: tuple[MaintenanceCostOption, ...] = Field(min_length=1)
    lowest_calculated_cost_option_id: str | None = Field(
        min_length=1, max_length=240
    )
    assumptions: tuple[str, ...]
    input_sources: tuple[CostInputSource, ...] = Field(min_length=1)
    missing_inputs: tuple[str, ...]
    price_version: str = Field(min_length=1, max_length=160)
    calculation_policy_version: str = Field(min_length=1, max_length=160)
    limitations: tuple[LimitationCode, ...]

    @model_validator(mode="after")
    def require_result_invariants(self) -> MaintenanceCostScenarioResult:
        if self.asset_id != self.equipment_id:
            raise ValueError("Operations cost analysis requires equipment_id = asset_id")

        option_ids = [option.option_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("option_id values must be unique")

        input_names = [source.input_name for source in self.input_sources]
        if len(input_names) != len(set(input_names)):
            raise ValueError("input source names must be unique")

        expected_timings = set(ExecutionTiming)
        groups: dict[tuple[str, MaintenanceActionCode], set[ExecutionTiming]] = {}
        for option in self.options:
            key = (option.action_candidate_id, option.action_code)
            groups.setdefault(key, set()).add(option.execution_timing)
        if any(timings != expected_timings for timings in groups.values()):
            raise ValueError("each action candidate requires all four timing scenarios")
        if len(groups) * len(expected_timings) != len(self.options):
            raise ValueError("each action candidate may have only one option per timing")

        calculated = [
            option
            for option in self.options
            if option.calculation_status is CalculationStatus.CALCULATED
        ]
        option_missing_inputs = {
            missing_input
            for option in self.options
            for missing_input in option.missing_inputs
        }
        if set(self.missing_inputs) != option_missing_inputs:
            raise ValueError("result missing_inputs must aggregate option missing_inputs")

        if not calculated:
            if self.lowest_calculated_cost_option_id is not None:
                raise ValueError("no calculated option can be selected as lowest")
        else:
            expected_lowest = min(
                calculated,
                key=lambda option: (
                    option.total_expected_cost.base_minor,  # type: ignore[union-attr]
                    option.option_id,
                ),
            )
            if self.lowest_calculated_cost_option_id != expected_lowest.option_id:
                raise ValueError(
                    "lowest_calculated_cost_option_id must identify the lowest base cost"
                )

        required_limitations = set(LimitationCode)
        if (
            set(self.limitations) != required_limitations
            or len(self.limitations) != len(required_limitations)
        ):
            raise ValueError("all decision-boundary limitations are required")
        return self
