"""Contracts for the synthetic preventive What-if result producer.

This non-deployable experiment package emits structured analysis only.
Role-aware prose, API hosting, and UI rendering remain downstream concerns.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ActionCode(str, Enum):
    TOOL_REPLACEMENT = "TOOL_REPLACEMENT"


class EffectScope(str, Enum):
    SYNTHETIC_COUNTERFACTUAL_SIMULATION = "synthetic_counterfactual_simulation"


class LimitationCode(str, Enum):
    SYNTHETIC_DATA_ONLY = "SYNTHETIC_DATA_ONLY"
    NOT_CAUSAL_PROOF = "NOT_CAUSAL_PROOF"
    NOT_REAL_WORLD_EFFECT_GUARANTEE = "NOT_REAL_WORLD_EFFECT_GUARANTEE"
    CONTRACT_FIXTURE_ONLY = "CONTRACT_FIXTURE_ONLY"


class IndicatorDirection(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"
    RISK_UP = "risk_up"
    RISK_DOWN = "risk_down"


class SourceReference(StrictModel):
    source: str = Field(min_length=1)
    source_field: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    period_from: datetime | None = None
    period_to: datetime | None = None

    @model_validator(mode="after")
    def validate_period(self) -> SourceReference:
        if self.period_from and self.period_to and self.period_to < self.period_from:
            raise ValueError("period_to must not precede period_from")
        return self


class RiseEvent(StrictModel):
    started_at: datetime
    peak_at: datetime
    baseline_probability: float = Field(ge=0, le=1)
    peak_probability: float = Field(ge=0, le=1)
    probability_delta: float = Field(ge=0, le=1)
    time_to_peak_hours: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_rise(self) -> RiseEvent:
        if self.peak_at < self.started_at:
            raise ValueError("peak_at must not precede started_at")
        expected_delta = self.peak_probability - self.baseline_probability
        if abs(expected_delta - self.probability_delta) > 1e-9:
            raise ValueError("probability_delta must equal peak minus baseline")
        expected_hours = (self.peak_at - self.started_at).total_seconds() / 3600.0
        if abs(expected_hours - self.time_to_peak_hours) > 1e-9:
            raise ValueError("time_to_peak_hours must equal started_at to peak_at duration")
        return self


class RiskRiseDetectionPolicy(StrictModel):
    policy_version: str = Field(min_length=1)
    policy_scope: Literal["offline_what_if_candidate_detection"]
    authoritative_for_operational_risk: Literal[False]
    allowed_uses: list[
        Literal[
            "what_if_candidate_selection",
            "offline_experiment_ranking",
            "sensor_evidence_reference",
        ]
    ] = Field(min_length=1)
    prohibited_uses: list[
        Literal[
            "failure_probability_override",
            "status_grade_assignment",
            "top_factors_override",
            "recommended_action_assignment",
            "operational_alert_threshold",
            "failure_cause_confirmation",
            "intervention_effect_confirmation",
        ]
    ] = Field(min_length=1)
    eligible_asset_types: list[str] = Field(min_length=1)
    minimum_step_probability_increase: float = Field(gt=0, le=1)
    minimum_total_probability_increase: float = Field(gt=0, le=1)
    maximum_observation_gap_hours: float = Field(gt=0)
    baseline_window_hours: float = Field(gt=0)
    distribution_basis: dict[str, str | int | float]

    @model_validator(mode="after")
    def validate_usage_boundary(self) -> RiskRiseDetectionPolicy:
        required_prohibitions = {
            "failure_probability_override",
            "status_grade_assignment",
            "top_factors_override",
            "recommended_action_assignment",
            "operational_alert_threshold",
            "failure_cause_confirmation",
            "intervention_effect_confirmation",
        }
        if not required_prohibitions.issubset(self.prohibited_uses):
            raise ValueError("risk-rise policy must retain all operational-use prohibitions")
        return self


class PredictionFactor(StrictModel):
    feature: str = Field(min_length=1)
    signed_contribution: float
    direction: IndicatorDirection


class PredictionTimelinePoint(StrictModel):
    prediction_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    asset_type: str = Field(min_length=1)
    observed_at: datetime
    failure_probability: float = Field(ge=0, le=1)
    model_version: str = Field(min_length=1)
    top_factors: list[PredictionFactor] = Field(default_factory=list)


class DetectedRiskRiseEvent(StrictModel):
    event_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    asset_type: str = Field(min_length=1)
    started_at: datetime
    peak_at: datetime
    ended_at: datetime
    baseline_probability: float = Field(ge=0, le=1)
    peak_probability: float = Field(ge=0, le=1)
    probability_delta: float = Field(gt=0, le=1)
    time_to_peak_hours: float = Field(ge=0)
    duration_hours: float = Field(ge=0)
    terminated_by: Literal["non_increase", "gap", "end_of_timeline"]
    policy_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    source_prediction_ids: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_event_timing(self) -> DetectedRiskRiseEvent:
        if not self.started_at <= self.peak_at <= self.ended_at:
            raise ValueError("risk rise timestamps must satisfy started_at <= peak_at <= ended_at")
        expected_delta = self.peak_probability - self.baseline_probability
        if abs(expected_delta - self.probability_delta) > 1e-9:
            raise ValueError("probability_delta must equal peak minus baseline")
        expected_peak_hours = (self.peak_at - self.started_at).total_seconds() / 3600
        if abs(expected_peak_hours - self.time_to_peak_hours) > 1e-9:
            raise ValueError("time_to_peak_hours must match event timestamps")
        expected_duration = (self.ended_at - self.started_at).total_seconds() / 3600
        if abs(expected_duration - self.duration_hours) > 1e-9:
            raise ValueError("duration_hours must match event timestamps")
        return self


class SensorFeatureStatistic(StrictModel):
    feature: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    baseline_count: int = Field(gt=0)
    risk_count: int = Field(gt=0)
    baseline_mean: float
    baseline_median: float
    baseline_stddev: float = Field(ge=0)
    risk_mean: float
    risk_median: float
    risk_stddev: float = Field(ge=0)
    change_percent: float | None = None
    baseline_sigma_shift: float | None = None
    source_reference: SourceReference


class LeadingIndicator(StrictModel):
    feature: str = Field(min_length=1)
    direction: IndicatorDirection
    baseline_value: float
    risk_window_value: float
    change_percent: float | None = None
    signed_contribution: float | None = None
    source_reference: SourceReference


class ToolReplacementParameters(StrictModel):
    tool_wear_after: float = Field(ge=0)


class ToolReplacementIntervention(StrictModel):
    action_code: Literal[ActionCode.TOOL_REPLACEMENT]
    parameters: ToolReplacementParameters
    estimated_downtime_minutes: int | None = Field(default=None, ge=0)
    policy_version: str = Field(min_length=1)


class ProbabilityEffect(StrictModel):
    baseline_probability: float = Field(ge=0, le=1)
    intervention_probability: float = Field(ge=0, le=1)
    estimated_probability_reduction: float = Field(ge=-1, le=1)

    @model_validator(mode="after")
    def validate_reduction(self) -> ProbabilityEffect:
        expected = self.baseline_probability - self.intervention_probability
        if abs(expected - self.estimated_probability_reduction) > 1e-9:
            raise ValueError("estimated_probability_reduction must equal baseline minus intervention")
        return self


class EconomicEffect(StrictModel):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    intervention_cost: float | None = Field(default=None, ge=0)
    baseline_expected_loss: float | None = Field(default=None, ge=0)
    intervention_expected_loss: float | None = Field(default=None, ge=0)
    estimated_net_benefit: float | None = None
    calculation_scope: Literal["synthetic_scenario_estimate"]
    price_version: str = Field(min_length=1)


class Limitation(StrictModel):
    code: LimitationCode


class WhatIfProvenance(StrictModel):
    dataset_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    simulation_policy_version: str = Field(min_length=1)
    source_type: Literal["contract_fixture", "simulation_output"]
    canonical_source_mutated: Literal[False] = False


class WhatIfResult(StrictModel):
    schema_version: Literal["what-if-result-v1.0"]
    simulation_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    asset_type: Literal["cnc"]
    decision_at: datetime
    rise_event: RiseEvent
    leading_indicators: list[LeadingIndicator] = Field(min_length=1)
    intervention: ToolReplacementIntervention
    effect: ProbabilityEffect
    economic_effect: EconomicEffect | None = None
    effect_scope: EffectScope
    limitations: list[Limitation] = Field(min_length=1)
    provenance: WhatIfProvenance

    @model_validator(mode="after")
    def validate_semantics(self) -> WhatIfResult:
        codes = {item.code for item in self.limitations}
        required = {
            LimitationCode.SYNTHETIC_DATA_ONLY,
            LimitationCode.NOT_CAUSAL_PROOF,
            LimitationCode.NOT_REAL_WORLD_EFFECT_GUARANTEE,
        }
        if not required.issubset(codes):
            raise ValueError("synthetic What-if results must expose all safety limitations")
        if any(
            item.source_reference.asset_id != self.asset_id
            for item in self.leading_indicators
        ):
            raise ValueError("all leading indicator source asset IDs must match result asset_id")
        if self.intervention.policy_version != self.provenance.simulation_policy_version:
            raise ValueError("intervention and provenance policy versions must match")
        if self.decision_at < self.rise_event.started_at:
            raise ValueError("decision_at must not precede rise event started_at")
        return self


class ToolReplacementPolicy(StrictModel):
    policy_version: str = Field(min_length=1)
    action_code: Literal[ActionCode.TOOL_REPLACEMENT]
    asset_type: Literal["cnc"]
    tool_wear_after: float = Field(ge=0)
    default_duration_minutes: int = Field(gt=0)
    requires_shutdown: Literal[True]
    applicable_failure_modes: list[Literal["tool_wear_failure", "overstrain_failure"]]
    cost_source_type: Literal["missing", "synthetic_assumption", "actual_transaction"]
    default_parts_cost: float | None = Field(default=None, ge=0)
    default_labor_cost: float | None = Field(default=None, ge=0)


def preventive_what_if_schema() -> dict[str, object]:
    schema = WhatIfResult.model_json_schema(
        ref_template="#/$defs/{model}",
        mode="validation",
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://ontology-dashboard.local/schemas/preventive-what-if.schema.json",
        **schema,
    }
