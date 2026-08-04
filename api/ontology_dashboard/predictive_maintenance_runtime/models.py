from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..adapters.models import PredictionResult


SHA256_PATTERN = r"^[a-f0-9]{64}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GraphReadiness(StrictModel):
    status: Literal["pending", "indexing", "ready", "failed", "unavailable"]
    record_count: int = Field(default=0, ge=0)
    provider_run_id: str | None = None
    last_error: str | None = None
    attempt_count: int = Field(default=0, ge=0)
    updated_at: datetime | None = None
    required_for_runtime: Literal[False] = False


class GovernanceProvenance(StrictModel):
    release_identity: dict[str, Any] = Field(default_factory=dict)
    tool_wear_continuity: dict[str, Any] = Field(default_factory=dict)
    agent_example_evaluation: dict[str, Any] = Field(default_factory=dict)
    ai4i_physics: dict[str, Any] = Field(default_factory=dict)
    ai4i_contract: dict[str, Any] = Field(default_factory=dict)
    query_time_derived_measures: dict[str, str] = Field(default_factory=dict)
    governance_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    prediction_label_semantics: Literal[
        "generic_binary_risk_not_ai4i_failure_mode"
    ] = "generic_binary_risk_not_ai4i_failure_mode"
    release_evidence_is_prediction_label: Literal[False] = False
    maintenance_evidence_accuracy_is_instance_accuracy: Literal[False] = False


class SemanticQueryCapability(StrictModel):
    dimensions: list[str]
    canonical_measures: list[str]
    derived_measures: dict[str, str]
    latest_result_contract: Literal[
        "result_artifact", "prediction_snapshot_compatibility"
    ]
    replay_prediction_contract: Literal[
        "precomputed_prediction_timeline"
    ] = "precomputed_prediction_timeline"
    supported_grains: list[Literal["raw", "10m", "1h"]]
    nearest_prediction_join: Literal["at_or_before_observation_time"] = (
        "at_or_before_observation_time"
    )
    evaluation_truth_queryable: Literal[False] = False
    model_training_available: Literal[False] = False


class DatasetVersionRuntimeContext(StrictModel):
    organization_id: str
    project_id: str
    workspace_id: str
    dataset_id: str
    dataset_version_id: str
    source_version: str
    bundle_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    version_number: int = Field(ge=1)
    record_count: int = Field(ge=0)
    dataset_status: str
    row_counts: dict[str, int] = Field(default_factory=dict)
    source_contract: dict[str, Any] = Field(default_factory=dict)
    model_version: str | None = None
    result_artifact_schema_version: str | None = None
    prediction_task: Literal["binary_failure_within_horizon"] | None = None
    semantic_catalog_version: str = "predictive-maintenance-semantic-compat-v1"
    governance: GovernanceProvenance
    graph: GraphReadiness
    semantic_query: SemanticQueryCapability


class DatasetVersionOption(StrictModel):
    dataset_id: str
    dataset_name: str
    dataset_version_id: str
    version_number: int = Field(ge=1)
    source_version: str
    bundle_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    dataset_status: str
    record_count: int = Field(ge=0)
    row_counts: dict[str, int] = Field(default_factory=dict)
    result_artifact_count: int = Field(default=0, ge=0)
    prediction_timeline_count: int = Field(default=0, ge=0)
    model_version: str | None = None
    result_artifact_schema_version: str | None = None
    prediction_task: Literal["binary_failure_within_horizon"] | None = None
    graph: GraphReadiness
    release_ready: bool
    is_latest: bool
    is_v3_1: bool


class DatasetVersionOptions(StrictModel):
    organization_id: str
    project_id: str
    workspace_id: str
    items: list[DatasetVersionOption]
    default_dataset_version_id: str | None = None
    immutable_versioning: Literal[True] = True
    rollback_supported: bool


class PredictiveMaintenanceReleaseOverview(StrictModel):
    active: DatasetVersionRuntimeContext
    versions: DatasetVersionOptions
    phase_contract: Literal["predictive-maintenance-canonical-v3.1"] = (
        "predictive-maintenance-canonical-v3.1"
    )
    immutable_upgrade_verified: bool
    result_artifact_coverage: int = Field(ge=0)
    projection_status: GraphReadiness
    safe_release_gates: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    hidden_truth_exposed: Literal[False] = False
    evaluation_truth_exposed: Literal[False] = False


class ProductFactor(StrictModel):
    rank: int = Field(ge=1, le=3)
    feature: str
    feature_value: float
    signed_contribution: float
    direction: Literal["risk_up", "risk_down"]
    explanation_method: str


class PolicyRecommendation(StrictModel):
    action: str
    priority: str
    semantic_type: Literal["policy_recommendation"] = "policy_recommendation"
    approval_state: Literal["not_requested"] = "not_requested"
    execution_state: Literal["not_executed"] = "not_executed"
    creates_work_order_automatically: Literal[False] = False


class ProductResultProvenance(StrictModel):
    dataset_id: str
    dataset_version_id: str
    source_version: str
    bundle_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    result_artifact_source_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    prediction_id: str
    prediction_result_id: str
    model_version: str
    schema_version: str
    prediction_task: Literal["binary_failure_within_horizon"]
    source_type: str
    canonical_source_mutated: Literal[False] = False


class GovernedProductResult(StrictModel):
    contract_version: Literal["1.0"] = "1.0"
    source_contract: Literal[
        "result_artifact", "prediction_snapshot_compatibility"
    ]
    artifact_id: str | None = None
    asset_id: str
    asset_type: Literal["compressor", "cnc"]
    site_id: str
    cell_id: str
    observed_at: datetime
    prediction_horizon_hours: int = Field(gt=0)
    prediction_task: Literal["binary_failure_within_horizon"]
    failure_probability: float = Field(ge=0, le=1)
    predicted_failure_type: Literal["failure_risk", "no_significant_risk"]
    status_grade: Literal["normal", "attention", "warning", "critical"]
    confidence: float = Field(ge=0, le=1)
    top_factors: list[ProductFactor] = Field(default_factory=list, max_length=3)
    recommended_action: PolicyRecommendation | None = None
    provenance: ProductResultProvenance
    governance: GovernanceProvenance
    graph: GraphReadiness
    prediction_result: PredictionResult

    @model_validator(mode="after")
    def enforce_result_semantics(self) -> "GovernedProductResult":
        if self.source_contract == "result_artifact":
            if not self.artifact_id or len(self.top_factors) != 3:
                raise ValueError("Result Artifact product results require artifact_id and Top-3 factors")
            if self.recommended_action is None:
                raise ValueError("Result Artifact product results require a policy recommendation")
        if self.predicted_failure_type not in {
            "failure_risk",
            "no_significant_risk",
        }:
            raise ValueError("predicted_failure_type must remain a generic binary risk class")
        return self


class ProductResultPage(StrictModel):
    context: DatasetVersionRuntimeContext
    items: list[GovernedProductResult]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    latest_product_contract: Literal[
        "result_artifact", "prediction_snapshot_compatibility"
    ]


class SnapshotFactor(StrictModel):
    rank: int
    feature: str
    feature_value: float
    signed_contribution: float
    absolute_contribution: float
    direction: str
    explanation_method: str
    source_type: str


class SnapshotDrilldown(StrictModel):
    dataset_version_id: str
    prediction_id: str
    prediction_result_id: str
    asset_id: str
    asset_type: str
    observed_at: datetime
    prediction_horizon_hours: int
    failure_probability: float
    predicted_failure_type: str | None
    confidence: float
    status: str
    model_version: str
    feature_scope: Any
    factors: list[SnapshotFactor] = Field(default_factory=list)


class TimelinePrediction(StrictModel):
    prediction_id: str
    asset_id: str
    asset_type: str
    observed_at: datetime
    prediction_horizon_hours: int
    failure_probability: float
    status: str
    top_factors: list[dict[str, Any]] = Field(default_factory=list)
    model_version: str
    feature_scope: Any
    source_type: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    semantics: Literal["precomputed_replay_prediction"] = "precomputed_replay_prediction"
    model_retrained_for_query: Literal[False] = False


class SensorObservation(StrictModel):
    observed_at: datetime
    asset_id: str
    asset_type: Literal["compressor", "cnc"]
    site_id: str
    cell_id: str
    is_operating: bool
    operating_state: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    measurements: dict[str, float | str | bool]
    derived_measures: dict[str, float] = Field(default_factory=dict)
    source_kind: Literal["canonical_observation"] = "canonical_observation"


class ObservationQueryResponse(StrictModel):
    context: DatasetVersionRuntimeContext
    window_start: datetime
    window_end: datetime
    grain: Literal["raw", "10m", "1h"]
    source_rows_mutated: Literal[False] = False
    observations: list[SensorObservation]
    nearest_predictions: list[TimelinePrediction] = Field(default_factory=list)
    returned_observation_count: int = Field(ge=0)
    limit: int = Field(ge=1)
    truncated: bool


ReplayState = Literal["stopped", "running", "paused", "completed"]


class ReplayStartRequest(StrictModel):
    dataset_version_id: str | None = Field(default=None, max_length=160)
    start_time: datetime | None = None
    speed_minutes_per_second: float = Field(default=60.0, ge=0.1, le=10080)


class ReplayControlRequest(StrictModel):
    time: datetime | None = None
    speed_minutes_per_second: float | None = Field(default=None, ge=0.1, le=10080)


class ReplayCursor(StrictModel):
    session_id: str
    state: ReplayState
    sequence: int = Field(ge=0)
    simulation_time: datetime
    wall_clock_observed_at: datetime
    source_freshness_at: datetime
    speed_minutes_per_second: float = Field(ge=0.1, le=10080)
    dataset_start: datetime
    dataset_end: datetime
    progress: float = Field(ge=0, le=1)
    simulation_time_is_wall_clock: Literal[False] = False
    model_retrained: Literal[False] = False


class ReplaySessionSnapshot(StrictModel):
    context: DatasetVersionRuntimeContext
    cursor: ReplayCursor
    canonical_sensor_time: datetime
    compressor_observations: list[SensorObservation]
    cnc_observations: list[SensorObservation]
    nearest_prediction_time: datetime | None = None
    predictions: list[TimelinePrediction] = Field(default_factory=list)
    latest_result_artifact_references: list[dict[str, Any]] = Field(default_factory=list)
    graph: GraphReadiness
    replay_source: Literal["postgresql_prediction_timeline"] = (
        "postgresql_prediction_timeline"
    )
    truth_exposed: Literal[False] = False
    sensor_values_generated: Literal[False] = False


class ReplaySessionRecord(StrictModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    dataset_id: str
    dataset_version_id: str
    created_by: str
    state: ReplayState
    simulation_time: datetime
    dataset_start: datetime
    dataset_end: datetime
    source_freshness_at: datetime
    speed_minutes_per_second: float
    sequence: int
    last_advanced_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("simulation_time")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("simulation time must include timezone")
        return value
