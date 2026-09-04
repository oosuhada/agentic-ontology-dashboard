"""Versioned reference inputs consumed by Maintenance cost analysis."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .cost_analysis_schema import CostInputSource, ExecutionTiming, FrozenModel
from .cost_calculator import ToolReplacementScenarioInput


class CostBasisResolutionContext(FrozenModel):
    """Typed operational facts used to resolve an Action-specific cost basis.

    ``None`` means the inspection did not establish the fact.  Callers must
    not treat an unknown fact as satisfying a demo basis applicability rule.
    """

    execution_mode: Literal["in_house", "external"] | None = None
    spare_part_available: bool | None = None
    vendor_dispatch_required: bool | None = None
    component_replacement_required: bool | None = None

    def require_complete_for(self, action_code: str) -> None:
        required = {
            "TOOL_REPLACEMENT": (
                "execution_mode",
                "spare_part_available",
                "vendor_dispatch_required",
            ),
            "COOLING_SYSTEM_RESTORE": (
                "execution_mode",
                "vendor_dispatch_required",
                "component_replacement_required",
            ),
        }.get(action_code)
        if required is None:
            raise ValueError(f"unsupported cost-basis Action: {action_code}")
        missing = [name for name in required if getattr(self, name) is None]
        if missing:
            raise ValueError(
                f"{action_code} cost basis requires explicit applicability facts: "
                + ", ".join(missing)
            )


class MaintenanceActionCostBasis(FrozenModel):
    """Server-owned economic inputs for one Maintenance Action analysis."""

    currency: str = Field(pattern=r"^[A-Z]{3}$")
    currency_minor_unit: Literal[0, 2, 3]
    scenarios: tuple[ToolReplacementScenarioInput, ...] = Field(
        min_length=4, max_length=4
    )
    assumptions: tuple[str, ...]
    input_sources: tuple[CostInputSource, ...] = Field(min_length=1)
    price_version: str = Field(min_length=1, max_length=160)
    calculation_policy_version: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def require_complete_timing_set(self) -> MaintenanceActionCostBasis:
        timings = [scenario.execution_timing for scenario in self.scenarios]
        if len(set(timings)) != len(timings) or set(timings) != set(ExecutionTiming):
            raise ValueError(
                "TOOL_REPLACEMENT cost basis requires all four timing scenarios"
            )
        return self


class ToolReplacementCostBasis(MaintenanceActionCostBasis):
    """Server-owned economic inputs for one TOOL_REPLACEMENT analysis."""


class CoolingSystemRestoreCostBasis(MaintenanceActionCostBasis):
    """Server-owned economic inputs for one COOLING_SYSTEM_RESTORE analysis."""


__all__ = [
    "CostBasisResolutionContext",
    "CoolingSystemRestoreCostBasis",
    "MaintenanceActionCostBasis",
    "ToolReplacementCostBasis",
]
