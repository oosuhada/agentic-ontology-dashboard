from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .diagnosis_schema import PredictionResult


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
    relational_status: Literal["pending", "indexing", "ready", "failed", "unavailable"] = (
        "unavailable"
    )
    relational_record_count: int = Field(default=0, ge=0)
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
    relational_status: Literal["pending", "indexing", "ready", "failed", "unavailable"] = (
        "unavailable"
    )
    relational_record_count: int = Field(default=0, ge=0)
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
    selection_mode: Literal["automatic", "explicit"] = "automatic"
    selection_reason: Literal[
        "wall_clock_live_runtime",
        "canonical_v3_1_release_ready",
        "latest_published_predictive_maintenance",
        "latest_predictive_maintenance",
        "latest_wall_clock_safe_predictive_maintenance",
        "explicit_user_selection",
        "no_runtime_dataset",
    ] = "no_runtime_dataset"
    immutable_versioning: Literal[True] = True
    rollback_supported: bool


class DatasetVersionSelectionRequest(StrictModel):
    dataset_version_id: str | None = Field(default=None, max_length=160)


class PredictionResultBatchProducer(StrictModel):
    system: Literal["systems.generator"]
    runtime_version: str = Field(min_length=1, max_length=128)
    outbox_id: str | None = Field(default=None, max_length=240)


class PredictionResultBatchSourceRef(StrictModel):
    uri: str = Field(min_length=1, max_length=1000)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("sha256")
    @classmethod
    def reject_zero_sha256(cls, value: str) -> str:
        if value == "0" * 64:
            raise ValueError("SHA-256 checksum cannot be all zeros")
        return value


class PredictionResultBatchLineage(StrictModel):
    simulation_session_id: str | None = Field(default=None, max_length=240)
    overlay_branch_id: str | None = Field(default=None, max_length=240)
    history_segment_id: str | None = Field(default=None, max_length=240)
    maintenance_event_id: str | None = Field(default=None, max_length=240)
    maintenance_action_id: str | None = Field(default=None, max_length=240)
    state_version: int | None = Field(default=None, ge=1)


class PredictionResultTopFactorExpression(StrictModel):
    feature: str = Field(min_length=1, max_length=240)
    display_name: str | None = Field(default=None, max_length=240)
    feature_value: float | int | str | bool | None = None
    signed_contribution: float
    direction: Literal["risk_up", "risk_down"]
    explanation_method: str = Field(min_length=1, max_length=240)
    evidence_field_id: str | None = Field(default=None, max_length=240)
    source_ref: PredictionResultBatchSourceRef | None = None


class PredictionResultExplanation(StrictModel):
    top_factors: list[PredictionResultTopFactorExpression] = Field(
        default_factory=list,
        max_length=5,
    )
    confidence_label: str | None = Field(default=None, max_length=80)
    explanation_method: str | None = Field(default=None, max_length=240)
    feature_snapshot_ref: PredictionResultBatchSourceRef | None = None
    sensor_window_ref: PredictionResultBatchSourceRef | None = None
    display_labels: dict[str, str] = Field(default_factory=dict)


class PredictionResultBatchSourceContext(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=240)
    dataset_version: str = Field(min_length=1, max_length=240)
    source_uri: str = Field(min_length=1, max_length=1000)
    source_checksum: str = Field(pattern=SHA256_PATTERN)
    source_kind: Literal[
        "live_sensor",
        "simulation_overlay",
        "maintenance_replay_overlay",
    ]
    source_contract_version: str = Field(min_length=1, max_length=240)
    source_schema_version: str = Field(min_length=1, max_length=240)
    pipeline_contract_version: str = Field(min_length=1, max_length=240)
    lineage: PredictionResultBatchLineage

    @field_validator("source_checksum")
    @classmethod
    def reject_zero_sha256(cls, value: str) -> str:
        if value == "0" * 64:
            raise ValueError("SHA-256 checksum cannot be all zeros")
        return value

    @model_validator(mode="after")
    def enforce_source_context_lineage(self) -> "PredictionResultBatchSourceContext":
        if self.source_kind == "maintenance_replay_overlay":
            missing = _missing_maintenance_replay_lineage(self.lineage)
            if missing:
                raise ValueError(
                    "maintenance_replay_overlay source_context requires lineage fields: "
                    + ", ".join(missing)
                )
        return self


class PredictionResultBatchModelSetItem(StrictModel):
    model_id: str = Field(min_length=1, max_length=240)
    model_version: str = Field(min_length=1, max_length=240)
    required: bool = True
    model_artifact_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    selected_threshold: float | None = Field(default=None, ge=0, le=1)

    @field_validator("model_artifact_manifest_sha256")
    @classmethod
    def reject_zero_sha256(cls, value: str) -> str:
        if value == "0" * 64:
            raise ValueError("SHA-256 checksum cannot be all zeros")
        return value


class PredictionResultBatchModelSet(StrictModel):
    model_set_id: str = Field(min_length=1, max_length=240)
    model_set_version: str = Field(min_length=1, max_length=240)
    models: list[PredictionResultBatchModelSetItem] = Field(min_length=1)


def _missing_maintenance_replay_lineage(
    lineage: PredictionResultBatchLineage,
) -> list[str]:
    return [
        field
        for field in (
            "simulation_session_id",
            "overlay_branch_id",
            "history_segment_id",
            "maintenance_event_id",
            "maintenance_action_id",
            "state_version",
        )
        if getattr(lineage, field) in (None, "")
    ]


class PredictionResultBatchItem(StrictModel):
    """Raw Generator prediction output before Backend Product Result promotion."""

    event_id: str = Field(min_length=1, max_length=240)
    asset_id: str = Field(min_length=1, max_length=240)
    observed_at: datetime
    source_kind: Literal[
        "live_sensor",
        "simulation_overlay",
        "maintenance_replay_overlay",
    ]
    source_ref: PredictionResultBatchSourceRef
    payload_sha256: str = Field(pattern=SHA256_PATTERN)
    output_status: Literal[
        "predicted",
        "warming_up",
        "history_insufficient",
        "failed_source_unavailable",
        "failed_model_artifact",
        "failed_feature_execution",
        "failed_model_inference",
    ]
    score: float | None = Field(default=None, ge=0, le=1)
    model_id: str = Field(min_length=1, max_length=240)
    model_version: str = Field(min_length=1, max_length=240)
    model_artifact_manifest_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    feature_schema_version: str | None = Field(default=None, min_length=1, max_length=240)
    history_requirement_version: str | None = Field(default=None, min_length=1, max_length=240)
    label_schema_version: str | None = Field(default=None, min_length=1, max_length=240)
    feature_schema_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    history_requirement_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    label_schema_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    lineage: PredictionResultBatchLineage
    explanation: PredictionResultExplanation | None = None
    failure_reason: str | None = Field(default=None, max_length=1000)

    @field_validator(
        "payload_sha256",
        "model_artifact_manifest_sha256",
        "feature_schema_sha256",
        "history_requirement_sha256",
        "label_schema_sha256",
    )
    @classmethod
    def reject_zero_sha256(cls, value: str | None) -> str | None:
        if value == "0" * 64:
            raise ValueError("SHA-256 checksum cannot be all zeros")
        return value

    @model_validator(mode="after")
    def enforce_raw_batch_boundary(self) -> "PredictionResultBatchItem":
        if self.output_status == "predicted":
            if self.score is None:
                raise ValueError("predicted batch items require score")
            if self.failure_reason is not None:
                raise ValueError("predicted batch items must not carry failure_reason")
            if not self.model_artifact_manifest_sha256:
                raise ValueError(
                    "predicted batch items require model_artifact_manifest_sha256"
                )
            if not self.feature_schema_version:
                raise ValueError("predicted batch items require feature_schema_version")
            if not self.history_requirement_version:
                raise ValueError(
                    "predicted batch items require history_requirement_version"
                )
            if not self.label_schema_version:
                raise ValueError("predicted batch items require label_schema_version")
            if not self.feature_schema_sha256:
                raise ValueError("predicted batch items require feature_schema_sha256")
            if not self.history_requirement_sha256:
                raise ValueError(
                    "predicted batch items require history_requirement_sha256"
                )
            if not self.label_schema_sha256:
                raise ValueError("predicted batch items require label_schema_sha256")
        else:
            if self.explanation is not None:
                raise ValueError("non-predicted batch items must not carry explanation")
            if self.score is not None:
                raise ValueError("non-predicted batch items must not carry score")
            if not self.failure_reason:
                raise ValueError("non-predicted batch items require failure_reason")
            if self.output_status in {
                "warming_up",
                "history_insufficient",
                "failed_feature_execution",
                "failed_model_inference",
            }:
                if not self.model_artifact_manifest_sha256:
                    raise ValueError(
                        f"{self.output_status} batch items require "
                        "model_artifact_manifest_sha256"
                    )
                if not self.feature_schema_version:
                    raise ValueError(
                        f"{self.output_status} batch items require feature_schema_version"
                    )
                if not self.history_requirement_version:
                    raise ValueError(
                        f"{self.output_status} batch items require history_requirement_version"
                    )
                if not self.label_schema_version:
                    raise ValueError(
                        f"{self.output_status} batch items require label_schema_version"
                    )
                if not self.feature_schema_sha256:
                    raise ValueError(
                        f"{self.output_status} batch items require feature_schema_sha256"
                    )
                if not self.history_requirement_sha256:
                    raise ValueError(
                        f"{self.output_status} batch items require history_requirement_sha256"
                    )
                if not self.label_schema_sha256:
                    raise ValueError(
                        f"{self.output_status} batch items require label_schema_sha256"
                    )
            elif self.output_status in {
                "failed_model_artifact",
                "failed_source_unavailable",
            }:
                if self.model_artifact_manifest_sha256 is not None:
                    raise ValueError(
                        f"{self.output_status} batch items must not carry "
                        "model_artifact_manifest_sha256"
                    )
                if self.feature_schema_version is not None:
                    raise ValueError(
                        f"{self.output_status} batch items must not carry feature_schema_version"
                    )
                if self.history_requirement_version is not None:
                    raise ValueError(
                        f"{self.output_status} batch items must not carry "
                        "history_requirement_version"
                    )
                if self.label_schema_version is not None:
                    raise ValueError(
                        f"{self.output_status} batch items must not carry label_schema_version"
                    )
                if self.feature_schema_sha256 is not None:
                    raise ValueError(
                        f"{self.output_status} batch items must not carry feature_schema_sha256"
                    )
                if self.history_requirement_sha256 is not None:
                    raise ValueError(
                        f"{self.output_status} batch items must not carry "
                        "history_requirement_sha256"
                    )
                if self.label_schema_sha256 is not None:
                    raise ValueError(
                        f"{self.output_status} batch items must not carry label_schema_sha256"
                    )
        if self.source_kind == "maintenance_replay_overlay":
            missing = _missing_maintenance_replay_lineage(self.lineage)
            if missing:
                raise ValueError(
                    "maintenance_replay_overlay batch items require lineage fields: "
                    + ", ".join(missing)
                )
        return self


class PredictionResultBatch(StrictModel):
    """Generator -> Backend Inbox handoff; not Product Result/Evidence."""

    contract_version: Literal["prediction-result-batch-v1"]
    batch_id: str = Field(min_length=1, max_length=240)
    producer: PredictionResultBatchProducer
    emitted_at: datetime
    source_context: PredictionResultBatchSourceContext
    model_set: PredictionResultBatchModelSet
    results: list[PredictionResultBatchItem] = Field(min_length=1)


class PredictionInboxItemReceipt(StrictModel):
    event_id: str
    payload_sha256: str
    validation_status: Literal["accepted", "duplicate", "conflict", "rejected"]
    rejection_reason: str | None = None


class PredictionInboxReceipt(StrictModel):
    batch_id: str
    payload_sha256: str
    validation_status: Literal["accepted", "duplicate", "conflict", "rejected"]
    rejection_reason: str | None = None
    received_results: int = Field(ge=0)
    accepted_results: int = Field(ge=0)
    duplicate_results: int = Field(ge=0)
    conflict_results: int = Field(ge=0)
    rejected_results: int = Field(ge=0)
    item_receipts: list[PredictionInboxItemReceipt] = Field(default_factory=list)
    promotion_status: Literal["promoted", "already_promoted", "partially_promoted", "not_promoted"] = "not_promoted"
    product_result_created: bool = False
    promoted_results: int = Field(default=0, ge=0)
    already_promoted_results: int = Field(default=0, ge=0)
    skipped_results: int = Field(default=0, ge=0)
    product_result_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)


class PredictionBatchPromotionItemReceipt(StrictModel):
    event_id: str
    promotion_status: Literal["promoted", "already_promoted", "skipped"]
    product_result_id: str | None = None
    artifact_id: str | None = None
    reason: str | None = None


class PredictionBatchPromotionReceipt(StrictModel):
    batch_id: str
    promotion_status: Literal["promoted", "already_promoted", "partially_promoted", "not_promoted"]
    product_result_created: bool
    received_results: int = Field(ge=0)
    promoted_results: int = Field(ge=0)
    already_promoted_results: int = Field(ge=0)
    skipped_results: int = Field(ge=0)
    product_result_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    item_receipts: list[PredictionBatchPromotionItemReceipt] = Field(default_factory=list)


class DashboardDataSource(StrictModel):
    dataset_id: str
    dataset_name: str
    dataset_version_id: str
    source_version: str
    model_version: str | None = None
    result_artifact_schema_version: str | None = None
    prediction_task: Literal["binary_failure_within_horizon"] | None = None
    bundle_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    record_count: int = Field(ge=0)
    row_counts: dict[str, int] = Field(default_factory=dict)
    result_artifact_count: int = Field(default=0, ge=0)
    prediction_timeline_count: int = Field(default=0, ge=0)
    relational_status: Literal["pending", "indexing", "ready", "failed", "unavailable"]
    relational_record_count: int = Field(default=0, ge=0)
    dataset_status: str
    release_ready: bool
    selection_mode: Literal["automatic", "explicit"]
    selection_reason: str
    source_kind: Literal["postgresql_result_artifact"] = "postgresql_result_artifact"
    graph: GraphReadiness


class DashboardEquipment(StrictModel):
    equipment_id: str
    display_name: str
    line: str
    criticality: Literal["low", "medium", "high"]
    assigned_engineer: str
    last_maintenance_date: str
    estimated_downtime_minutes: int = Field(ge=0)
    spare_part_available: bool | None = None


class DashboardEventSummary(StrictModel):
    event_id: str
    scenario_id: str
    ontology_object_id: str | None = None
    equipment: DashboardEquipment
    status: str
    failure_probability: float | None = Field(default=None, ge=0, le=1)
    confidence: str
    predicted_failure_type: str
    recommended_decision: str
    observed_at: datetime
    dataset_version_id: str


class DashboardEventDetail(StrictModel):
    event_id: str
    evidence: dict[str, Any]
    report: dict[str, Any]
    layout: dict[str, Any]
    maintenance_events: list[dict[str, Any]] = Field(default_factory=list)


class PredictiveMaintenanceDashboardResponse(StrictModel):
    data_source: DashboardDataSource
    context: DatasetVersionRuntimeContext
    versions: DatasetVersionOptions
    events: list[DashboardEventSummary]
    selected_event_id: str | None = None
    selected_event_detail: DashboardEventDetail | None = None
    fallback_available: Literal[True] = True
    fallback_name: Literal["Hanbit Tech Operations Reference"] = (
        "Hanbit Tech Operations Reference"
    )
    replay_source: Literal["postgresql_prediction_timeline"] = (
        "postgresql_prediction_timeline"
    )


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


class ProductEvidenceGapSummary(StrictModel):
    gap_id: str
    field: str
    owner_domain: str
    display_policy: str
    reason: str | None = None
    required_source: str | None = None


class ProductEvidenceSourceFieldSummary(StrictModel):
    field_id: str
    label: str
    source_path: str
    description: str | None = None


class ProductEvidenceActionSummary(StrictModel):
    action_id: str
    label: str
    kind: str
    requires_human_approval: bool = True
    basis: list[str] = Field(default_factory=list)


class ProductResultBatchLineageSummary(StrictModel):
    batch_id: str | None = None
    event_id: str | None = None
    emitted_at: datetime | None = None
    generated_at: datetime | None = None
    source_kind: str | None = None
    producer_id: str | None = None
    model_id: str | None = None
    source_reference: str | None = None
    simulation_session_id: str | None = None
    overlay_branch_id: str | None = None
    history_segment_id: str | None = None
    maintenance_action_id: str | None = None
    maintenance_event_id: str | None = None
    state_version: int | None = Field(default=None, ge=1)


class ProductResultEvidenceSummary(StrictModel):
    available: bool
    batch_lineage: ProductResultBatchLineageSummary | None = None
    evidence_payload_reference: dict[str, Any] | None = None
    sensor_window_rows: int = Field(default=0, ge=0)
    sensor_window: dict[str, Any] = Field(default_factory=dict)
    component_hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions: list[ProductEvidenceActionSummary] = Field(default_factory=list)
    source_fields: list[ProductEvidenceSourceFieldSummary] = Field(default_factory=list)
    evidence_gaps: list[ProductEvidenceGapSummary] = Field(default_factory=list)


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
    simulation_session_id: str | None = None
    overlay_branch_id: str | None = None
    history_segment_id: str | None = None
    maintenance_action_id: str | None = None
    maintenance_event_id: str | None = None
    state_version: int | None = Field(default=None, ge=1)


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
    evidence_summary: ProductResultEvidenceSummary | None = None
    provenance: ProductResultProvenance
    governance: GovernanceProvenance
    graph: GraphReadiness
    prediction_result: PredictionResult
    producer_artifact: dict[str, Any] | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def enforce_result_semantics(self) -> "GovernedProductResult":
        if self.source_contract == "result_artifact":
            if not self.artifact_id or len(self.top_factors) != 3:
                raise ValueError("Result Artifact product results require artifact_id and Top-3 factors")
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
