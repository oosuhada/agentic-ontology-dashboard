from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256_PATTERN = r"^[a-f0-9]{64}$"
SCHEMA_VERSION = "adaptive-modeling-v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    ACTIVE = "active"
    RETIRED = "retired"
    REJECTED = "rejected"


class CapabilityStatus(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


REVIEW_TRANSITIONS: dict[ReviewStatus, set[ReviewStatus]] = {
    ReviewStatus.DRAFT: {ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.SUPERSEDED},
    ReviewStatus.APPROVED: {ReviewStatus.SUPERSEDED},
    ReviewStatus.REJECTED: {ReviewStatus.SUPERSEDED},
    ReviewStatus.SUPERSEDED: set(),
}
RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.FAILED},
    RunStatus.RUNNING: {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED},
    RunStatus.SUCCEEDED: set(),
    RunStatus.FAILED: {RunStatus.QUEUED},
    RunStatus.CANCELLED: {RunStatus.QUEUED},
}
MODEL_TRANSITIONS: dict[ModelStatus, set[ModelStatus]] = {
    ModelStatus.CANDIDATE: {ModelStatus.APPROVED, ModelStatus.REJECTED},
    ModelStatus.APPROVED: {ModelStatus.ACTIVE, ModelStatus.RETIRED, ModelStatus.REJECTED},
    ModelStatus.ACTIVE: {ModelStatus.RETIRED},
    ModelStatus.RETIRED: {ModelStatus.ACTIVE},
    ModelStatus.REJECTED: set(),
}


def ensure_transition(current: str, target: str, kind: Literal["review", "run", "model"]) -> None:
    maps: dict[str, dict[Any, set[Any]]] = {
        "review": REVIEW_TRANSITIONS,
        "run": RUN_TRANSITIONS,
        "model": MODEL_TRANSITIONS,
    }
    enum_types = {"review": ReviewStatus, "run": RunStatus, "model": ModelStatus}
    enum_type = enum_types[kind]
    current_value = enum_type(current)
    target_value = enum_type(target)
    if target_value not in maps[kind][current_value]:
        raise ValueError(f"invalid {kind} status transition: {current} -> {target}")


def canonical_checksum(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


class ScopedIdentity(StrictModel):
    schema_version: Literal["adaptive-modeling-v1"] = SCHEMA_VERSION
    organization_id: str = Field(min_length=1, max_length=160)
    project_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)


class ArtifactReference(StrictModel):
    uri: str = Field(pattern=r"^(artifact|s3|gs|az|file)://")
    checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    media_type: str = Field(min_length=3, max_length=160)
    size_bytes: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    store_capability: Literal["ready", "blocked"] = "ready"

    @field_validator("uri")
    @classmethod
    def reject_windows_identity(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError("artifact URI must use portable URI separators")
        return value


class FieldProfile(StrictModel):
    name: str
    inferred_datatype: Literal["integer", "number", "boolean", "datetime", "string", "unknown"]
    null_ratio: float = Field(ge=0, le=1)
    distinct_estimate: int = Field(ge=0)
    semantic_candidates: list[
        Literal["identifier", "timestamp", "group_key", "measure", "dimension", "text"]
    ] = Field(default_factory=list)
    potential_sensitive: bool = False
    essential_key_candidate: bool = False
    summary: dict[str, Any] = Field(default_factory=dict)


class DatasetIntakeProfile(ScopedIdentity):
    profile_id: str
    dataset_id: str | None = None
    source_uri: str
    source_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    parser_version: str
    cache_key: str = Field(pattern=SHA256_PATTERN)
    byte_size: int = Field(ge=0)
    media_type: str
    status: Literal["profiling", "ready_for_review", "unsupported", "failed"]
    structure_type: Literal[
        "tabular_column_as_attribute",
        "tabular_row_as_attribute",
        "wide_pivot",
        "key_value",
        "multi_header",
        "unsupported",
    ]
    field_profiles: list[FieldProfile] = Field(default_factory=list)
    preview_rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int | None = Field(default=None, ge=0)
    retryable: bool = False
    failure_reason: str | None = None
    idempotency_key: str
    revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_cache_key(self) -> "DatasetIntakeProfile":
        expected = canonical_checksum(
            {"source_checksum_sha256": self.source_checksum_sha256, "parser_version": self.parser_version}
        )
        if self.cache_key != expected:
            raise ValueError("cache_key must bind full source checksum and parser version")
        return self


class IntakeProfileRequest(StrictModel):
    project_id: str
    workspace_id: str
    source_path: str
    sheet: str | None = None
    use_llm: bool = False
    idempotency_key: str


class ManifestDraftCreateRequest(StrictModel):
    project_id: str
    workspace_id: str
    profile_id: str
    idempotency_key: str


class ManifestDraftUpdateRequest(StrictModel):
    project_id: str
    workspace_id: str
    expected_revision: int = Field(ge=1)
    field_suggestions: list[ManifestFieldSuggestion] | None = None
    quality_rules: list[dict[str, Any]] | None = None
    encoding: str | None = None
    delimiter: str | None = None
    sheet: str | None = None


class ManifestDraftDecisionRequest(StrictModel):
    project_id: str
    workspace_id: str
    expected_revision: int = Field(ge=1)
    decision: Literal["approve", "reject", "supersede"]
    rationale: str = Field(min_length=2, max_length=1000)


class ManifestFieldSuggestion(StrictModel):
    source_field: str
    canonical_field: str | None = None
    selected: bool = True
    required: bool = False
    rationale: str
    confidence: float = Field(ge=0, le=1)
    essential_key: bool = False

    @model_validator(mode="after")
    def protect_essential_key(self) -> "ManifestFieldSuggestion":
        if self.essential_key and not self.selected:
            raise ValueError("essential key cannot be automatically excluded")
        return self


class ManifestDraft(ScopedIdentity):
    draft_id: str
    profile_id: str
    dataset_id: str | None = None
    source_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    revision: int = Field(default=1, ge=1)
    status: ReviewStatus = ReviewStatus.DRAFT
    format: Literal["csv", "xlsx"]
    encoding: str | None = None
    delimiter: str | None = None
    sheet: str | None = None
    field_suggestions: list[ManifestFieldSuggestion]
    quality_rules: list[dict[str, Any]] = Field(default_factory=list)
    missing_prerequisites: list[str] = Field(default_factory=list)
    approved_by: str | None = None
    decision_rationale: str | None = None
    idempotency_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MappingEvidence(StrictModel):
    source: Literal["rule", "manifest_metadata", "unit_metadata", "llm_suggestion", "user_confirmation"]
    detail: str
    score: float = Field(ge=0, le=1)


class OntologyMappingCandidate(StrictModel):
    candidate_id: str
    source_field: str
    target_object_type: str | None = None
    target_property: str | None = None
    datatype: str | None = None
    physical_unit: str | None = None
    grain: str | None = None
    semantic_role: Literal[
        "identifier", "timestamp", "dimension", "measure", "status", "text", "unresolved"
    ]
    group_key: bool = False
    join_key: bool = False
    critical_field: bool = False
    confidence: float = Field(ge=0, le=1)
    evidences: list[MappingEvidence] = Field(default_factory=list)
    status: Literal["proposed", "approved", "rejected", "unresolved"] = "proposed"


class OntologyMappingDecision(StrictModel):
    candidate_id: str
    decision: Literal["approve", "reject", "edit"]
    decided_by: str
    rationale: str
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MappingSet(ScopedIdentity):
    mapping_set_id: str
    dataset_version_id: str
    version: int = Field(ge=1)
    checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    status: ReviewStatus = ReviewStatus.DRAFT
    candidates: list[OntologyMappingCandidate]
    approved_by: str | None = None
    revision: int = Field(default=1, ge=1)
    idempotency_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MappingGenerateRequest(StrictModel):
    project_id: str
    workspace_id: str
    profile_id: str
    dataset_version_id: str
    use_llm: bool = False
    idempotency_key: str


class MappingCandidateDecisionRequest(StrictModel):
    project_id: str
    workspace_id: str
    expected_revision: int = Field(ge=1)
    candidate_id: str
    decision: Literal["approve", "reject", "edit"]
    rationale: str = Field(min_length=2, max_length=1000)
    target_object_type: str | None = None
    target_property: str | None = None
    datatype: str | None = None
    physical_unit: str | None = None
    grain: str | None = None
    semantic_role: Literal[
        "identifier", "timestamp", "dimension", "measure", "status", "text", "unresolved"
    ] | None = None
    group_key: bool | None = None
    join_key: bool | None = None


class MappingSetDecisionRequest(StrictModel):
    project_id: str
    workspace_id: str
    expected_revision: int = Field(ge=1)
    decision: Literal["approve", "reject", "supersede"]
    rationale: str = Field(min_length=2, max_length=1000)


class MappingSetCloneRequest(StrictModel):
    project_id: str
    workspace_id: str
    idempotency_key: str


class CapabilityEvaluation(ScopedIdentity):
    evaluation_id: str
    dataset_version_id: str
    mapping_set_id: str
    capability: Literal[
        "predictive_training",
        "predictive_scoring",
        "maintenance_context",
        "replay_time_series",
        "explanation",
    ]
    status: CapabilityStatus
    satisfied_prerequisites: list[str] = Field(default_factory=list)
    missing_prerequisites: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeatureRecipe(StrictModel):
    recipe_id: str
    version: int = Field(ge=1)
    checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    ontology_property: str
    operation: Literal[
        "identity",
        "rolling_mean",
        "rolling_std",
        "lag",
        "diff",
        "gradient",
        "ema",
        "moving_average",
        "power_w",
        "temperature_gap_k",
        "overstrain_load",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)
    group_by: str
    order_by: str
    minimum_history: int = Field(default=1, ge=1)
    null_policy: Literal["drop", "preserve", "fill_zero"] = "preserve"
    boundary_policy: Literal["reset_per_group"] = "reset_per_group"
    source_grain: str
    output_datatype: Literal["number", "integer", "boolean", "string"]
    output_unit: str | None = None
    leakage_policy: Literal["past_and_present_only"] = "past_and_present_only"
    status: Literal["enabled", "deprecated"] = "enabled"


class LabelPolicy(StrictModel):
    label_policy_id: str
    version: int = Field(ge=1)
    task: Literal["binary_failure_within_horizon"] = "binary_failure_within_horizon"
    horizon_hours: float = Field(gt=0)
    lookback_hours: float = Field(ge=0)
    embargo_hours: float = Field(ge=0)
    event_time_field: str
    observation_time_field: str
    target_source: str
    overlapping_window_policy: Literal["earliest_event", "nearest_event", "allow_overlap"]
    forbidden_sources: list[Literal["evaluation_truth", "hidden_truth"]] = Field(
        default_factory=lambda: ["evaluation_truth", "hidden_truth"]
    )


class FeatureRecipeSet(ScopedIdentity):
    recipe_set_id: str
    dataset_version_id: str
    mapping_set_id: str
    version: int = Field(ge=1)
    checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    status: ReviewStatus = ReviewStatus.DRAFT
    recipes: list[FeatureRecipe]
    label_policy: LabelPolicy
    validation_report: dict[str, Any] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)
    idempotency_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeatureDatasetVersion(ScopedIdentity):
    feature_dataset_version_id: str
    dataset_version_id: str
    mapping_set_id: str
    recipe_set_id: str
    label_policy_id: str
    materialization_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    status: RunStatus
    row_count: int = Field(ge=0)
    feature_count: int = Field(ge=0)
    equipment_count: int = Field(ge=0)
    time_start: datetime | None = None
    time_end: datetime | None = None
    artifact: ArtifactReference | None = None
    schema_metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SplitPolicy(StrictModel):
    mode: Literal["group_chronological", "group_holdout", "benchmark_random"] = "group_chronological"
    group_field: str
    time_field: str
    train_fraction: float = Field(gt=0, lt=1)
    validation_fraction: float = Field(gt=0, lt=1)
    test_fraction: float = Field(gt=0, lt=1)
    embargo_hours: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def fractions_sum(self) -> "SplitPolicy":
        if abs(self.train_fraction + self.validation_fraction + self.test_fraction - 1.0) > 1e-8:
            raise ValueError("split fractions must sum to 1")
        return self


class MetricSet(StrictModel):
    average_precision: float | None = None
    roc_auc: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    brier_score: float | None = None
    positive_prediction_rate: float | None = None
    confusion_matrix: list[list[int]] | None = None
    sample_count: int = Field(ge=0)
    positive_count: int = Field(ge=0)
    positive_rate: float = Field(ge=0, le=1)
    unavailable_reason: str | None = None


class CandidateResult(StrictModel):
    candidate_id: str
    algorithm: Literal[
        "dummy_prior", "logistic_regression", "random_forest", "lightgbm", "xgboost"
    ]
    status: Literal[
        "queued", "running", "succeeded", "failed", "blocked_dependency", "rejected"
    ]
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    dependency_version: str | None = None
    validation_metrics: MetricSet | None = None
    held_out_test_metrics: MetricSet | None = None
    selected: bool = False
    selection_rationale: str | None = None
    artifact: ArtifactReference | None = None
    error_reason: str | None = None


class ExperimentRun(ScopedIdentity):
    experiment_id: str
    dataset_version_id: str
    mapping_set_id: str
    recipe_set_id: str
    feature_dataset_version_id: str
    label_policy_id: str
    status: RunStatus
    split_policy: SplitPolicy
    random_seed: int
    progress: float = Field(default=0, ge=0, le=1)
    candidates: list[CandidateResult] = Field(default_factory=list)
    selected_candidate_id: str | None = None
    threshold_policy_id: str | None = None
    artifact: ArtifactReference | None = None
    idempotency_key: str
    retry_count: int = Field(default=0, ge=0)
    revision: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ThresholdPolicy(StrictModel):
    threshold_policy_id: str
    version: int = Field(ge=1)
    recall_target: float = Field(ge=0, le=1)
    recall_constrained_threshold: float = Field(ge=0, le=1)
    cost_minimizing_threshold: float = Field(ge=0, le=1)
    false_negative_cost: float = Field(gt=0)
    false_positive_cost: float = Field(gt=0)
    selected_operational_threshold: float = Field(ge=0, le=1)
    validation_only_selection: Literal[True] = True
    artifact: ArtifactReference | None = None


class ModelVersion(ScopedIdentity):
    model_version_id: str
    experiment_id: str
    candidate_id: str
    dataset_version_id: str
    mapping_set_id: str
    recipe_set_id: str
    feature_dataset_version_id: str
    label_policy_id: str
    status: ModelStatus
    artifact: ArtifactReference
    input_schema_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    runtime_versions: dict[str, str] = Field(default_factory=dict)
    calibration_method: str | None = None
    calibration_artifact: ArtifactReference | None = None
    threshold_policy: ThresholdPolicy
    explanation_provider: str
    explanation_provider_version: str
    limitations: list[str] = Field(default_factory=list)
    revision: int = Field(default=1, ge=1)
    activated_at: datetime | None = None
    retired_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExplanationFactor(StrictModel):
    rank: int = Field(ge=1)
    feature: str
    observed_value: float | int | str | None = None
    unit: str | None = None
    reference_range: str | None = None
    direction: Literal["risk_up", "risk_down", "neutral"]
    contribution: float
    contribution_kind: Literal["local_contribution"] = "local_contribution"


class ExplanationArtifact(ScopedIdentity):
    explanation_id: str
    prediction_result_id: str
    observation_id: str
    observed_at: datetime
    model_version_id: str
    recipe_set_id: str
    provider: str
    provider_version: str
    status: Literal["available", "unavailable", "failed"]
    top_factors: list[ExplanationFactor] = Field(default_factory=list)
    input_schema_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    unavailable_reason: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    causal_proof: Literal[False] = False


class ModelingContractSummary(StrictModel):
    schema_version: Literal["adaptive-modeling-v1"] = SCHEMA_VERSION
    bounded_context: Literal["modeling"] = "modeling"
    contracts: list[str]
    artifact_store: CapabilityStatus
    synchronous_training_endpoint: Literal[False] = False
    project3_logic_duplicated: Literal[False] = False
    mcp_protocol_implemented: Literal[False] = False


__all__ = [name for name in globals() if not name.startswith("_")]
