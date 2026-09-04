"""Pydantic schemas and dataclasses for the Generator Runtime Prediction Pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SHA256_PATTERN = r"^[a-f0-9]{64}$"


def _normalize_prediction_result_checksum_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        return value.replace("+00:00", "Z") if value.endswith("+00:00") else value
    if isinstance(value, dict):
        return {
            key: _normalize_prediction_result_checksum_value(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [_normalize_prediction_result_checksum_value(item) for item in value]
    return value


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArtifactReference(BaseModel):
    """Reference to an atomically published file asset."""
    model_config = ConfigDict(extra="forbid")

    uri: str = Field(..., description="Logical relative or absolute URI to the artifact")
    sha256: str = Field(..., pattern=SHA256_PATTERN, description="SHA-256 checksum of the artifact payload")
    role: str = Field("generic_artifact", description="Role or purpose of this artifact reference")
    size_bytes: Optional[int] = Field(None, exclude=True, description="Size in bytes")


class PipelineError(BaseModel):
    """Structured error information with stage context and retryability."""
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    stage: str = Field(..., description="Pipeline stage where error occurred")
    details: list[dict[str, Any]] = Field(default_factory=list, description="Diagnostic error details")
    retryable: bool = Field(False, description="Whether this error is retryable")
    attempt: int = Field(1, description="Attempt number when error occurred")
    occurred_at: str = Field(default_factory=now_utc_iso, description="ISO timestamp")


class StageState(BaseModel):
    """Execution state of an individual pipeline stage."""
    model_config = ConfigDict(extra="forbid")

    stage_name: str = Field(..., description="Name of the stage")
    status: Literal["pending", "running", "succeeded", "failed", "skipped"] = Field(
        "pending", description="Stage execution status"
    )
    attempt: int = Field(1, ge=1, description="Attempt count")
    started_at: Optional[str] = Field(None, description="ISO start timestamp")
    finished_at: Optional[str] = Field(None, description="ISO finish timestamp")
    input_refs: list[ArtifactReference] = Field(default_factory=list, description="Input artifact references")
    output_refs: list[ArtifactReference] = Field(default_factory=list, description="Output artifact references")
    error_code: Optional[str] = Field(None, description="Error code if failed")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    retryable: Optional[bool] = Field(None, description="Whether failed stage is retryable")


class RuntimeFeatureRowMetadata(BaseModel):
    """Row metadata mapping each feature matrix row to equipment and timestamp."""
    model_config = ConfigDict(extra="forbid")

    row_index: int = Field(..., ge=0, description="Row index in feature matrix")
    asset_id: str = Field(..., description="Target asset/equipment identifier")
    observed_at: str = Field(..., description="Observation timestamp in UTC ISO format")


class ActiveModelConfig(BaseModel):
    """Configuration for a single base model in active-model-set.json."""
    model_config = ConfigDict(extra="forbid")

    model_version: str = Field(..., min_length=1, description="Target model artifact version string")
    required: bool = Field(..., description="Whether failure of this model fails the entire batch")


class ActiveModelSet(BaseModel):
    """Active model set configuration pointer used during Generator Runtime Prediction."""
    model_config = ConfigDict(extra="forbid")

    model_set_id: str = Field(..., min_length=1, description="Model set identifier")
    model_set_version: str = Field(..., min_length=1, description="Model set version string")
    updated_at: datetime = Field(..., description="ISO timestamp of last update")
    models: dict[str, ActiveModelConfig] = Field(..., min_length=1, description="Map of base model identifiers to active model config")


class ActiveModelSnapshotItem(BaseModel):
    """Snapshot entry for an active model included in an external Prediction Result Batch."""
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(..., min_length=1, description="Model identifier, e.g. pdm-lightgbm")
    model_version: str = Field(..., min_length=1, description="Model version string")
    required: bool = Field(True, description="Whether this model is required")
    model_artifact_manifest_sha256: str = Field(..., pattern=SHA256_PATTERN, description="Model artifact manifest SHA-256")
    selected_threshold: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Model Artifact training_config.selected_threshold used for positive-class decisions",
    )

    @field_validator("model_artifact_manifest_sha256")
    @classmethod
    def validate_non_zero_manifest_sha(cls, v: str) -> str:
        if v == "0" * 64:
            raise ValueError("model_artifact_manifest_sha256 cannot be all zeros.")
        return v


class ActiveModelSetSnapshot(BaseModel):
    """Snapshot of active model set pinned at batch execution time and transmitted in external batch."""
    model_config = ConfigDict(extra="forbid")

    model_set_id: str = Field(..., min_length=1, description="Model set identifier")
    model_set_version: str = Field(..., min_length=1, description="Model set version string")
    models: list[ActiveModelSnapshotItem] = Field(..., min_length=1, description="List of active model snapshots")

    @model_validator(mode="after")
    def validate_unique_models(self) -> ActiveModelSetSnapshot:
        seen = set()
        for m in self.models:
            key = (m.model_id, m.model_version)
            if key in seen:
                raise ValueError(f"Duplicate model in model_set snapshot: {key}")
            seen.add(key)
        return self


class ModelPredictionResult(BaseModel):
    """Inference result payload for a single model in equipment batch."""
    model_config = ConfigDict(extra="forbid")

    model_version: str = Field(..., description="Published model artifact version")
    status: Literal["succeeded", "failed", "unknown"] = Field("succeeded", description="Model evaluation status")
    observed_at: str = Field(..., description="Observation timestamp in UTC ISO format")
    score_type: Optional[str] = Field("positive_class_probability", description="Type of score, e.g. positive_class_probability")
    score_source: Optional[Literal["predict_proba", "decision_function_compat", "predict_compat"]] = Field(
        "predict_proba", description="Inference method source"
    )
    score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Predicted numeric score/probability")
    artifact_ref: Optional[ArtifactReference] = Field(None, description="Reference to Model Artifact")
    feature_ref: Optional[ArtifactReference] = Field(None, description="Reference to Runtime Feature bundle")
    manifest_checksum: Optional[str] = Field(None, description="SHA-256 checksum of Model Artifact manifest")
    feature_schema_version: Optional[str] = Field(None, description="Feature schema version string")
    label_schema_version: Optional[str] = Field(None, description="Label schema version string")
    history_requirement_version: Optional[str] = Field(None, description="History requirement version string")
    model_set_id: Optional[str] = Field(None, exclude=True, description="internal-only: snapshot mismatch validation")
    model_set_version: Optional[str] = Field(None, exclude=True, description="internal-only: snapshot mismatch validation")
    error_code: Optional[str] = Field(None, description="Error code if model inference failed")
    error_message: Optional[str] = Field(None, description="Error message if model inference failed")


class InternalModelPredictionResult(BaseModel):
    """Internal model inference result containing asset_id and model_id for orchestration."""
    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(..., description="Target equipment identifier")
    model_id: str = Field(..., description="Unique model identifier, e.g. pdm-lightgbm")
    model_version: str = Field(..., description="Published model artifact version")
    status: Literal["succeeded", "failed", "unknown"] = Field("succeeded", description="Model evaluation status")
    observed_at: str = Field(..., description="Observation timestamp in UTC ISO format")
    score_type: Optional[str] = Field("positive_class_probability", description="Type of score, e.g. positive_class_probability")
    score_source: Optional[Literal["predict_proba", "decision_function_compat", "predict_compat"]] = Field(
        "predict_proba", description="Inference method source"
    )
    score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Predicted numeric score/probability")
    artifact_ref: Optional[ArtifactReference] = Field(None, description="Reference to Model Artifact")
    feature_ref: Optional[ArtifactReference] = Field(None, description="Reference to Runtime Feature bundle")
    manifest_checksum: Optional[str] = Field(None, description="SHA-256 checksum of Model Artifact manifest")
    feature_schema_version: Optional[str] = Field(None, description="Feature schema version string")
    label_schema_version: Optional[str] = Field(None, description="Label schema version string")
    history_requirement_version: Optional[str] = Field(None, description="History requirement version string")
    model_set_id: Optional[str] = Field(None, description="Model set ID")
    model_set_version: Optional[str] = Field(None, description="Model set version")
    error_code: Optional[str] = Field(None, description="Error code if model inference failed")
    error_message: Optional[str] = Field(None, description="Error message if model inference failed")

    def to_payload_result(self) -> ModelPredictionResult:
        """Convert internal result to contract payload result (without redundant asset_id/model_id)."""
        return ModelPredictionResult(
            model_version=self.model_version,
            status=self.status,
            observed_at=self.observed_at,
            score_type=self.score_type,
            score_source=self.score_source,
            score=self.score,
            artifact_ref=self.artifact_ref,
            feature_ref=self.feature_ref,
            manifest_checksum=self.manifest_checksum,
            feature_schema_version=self.feature_schema_version,
            label_schema_version=self.label_schema_version,
            history_requirement_version=self.history_requirement_version,
            model_set_id=self.model_set_id,
            model_set_version=self.model_set_version,
            error_code=self.error_code,
            error_message=self.error_message,
        )


class PredictionDeliveryEventState(BaseModel):
    """Delivery state tracking for an individual Prediction Result Batch delivery event."""
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="Unique event identifier")
    asset_id: str = Field(..., description="Target equipment identifier")
    status: Literal["pending", "sending", "retry_wait", "sent", "failed"] = Field(
        "pending", description="Event delivery status"
    )
    attempt: int = Field(0, ge=0, description="Attempt count")
    max_attempts: int = Field(5, ge=1, description="Max delivery attempts")
    next_retry_at: Optional[str] = Field(None, description="ISO timestamp for next retry")
    last_error_code: Optional[str] = Field(None, description="Last error code")
    last_error_message: Optional[str] = Field(None, description="Last error message")
    updated_at: str = Field(default_factory=now_utc_iso, description="ISO update timestamp")


class ModelSnapshotEntry(BaseModel):
    """Pinning metadata recorded per active model artifact."""
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(..., description="Unique model identifier, e.g. pdm-lightgbm")
    model_version: str = Field(..., description="Published model artifact version")
    manifest_sha256: str = Field(..., description="SHA-256 checksum of model artifact manifest")
    feature_schema_version: str = Field(..., description="Feature schema version string")
    feature_schema_sha256: str = Field(..., description="SHA-256 checksum of canonical feature schema")
    history_requirement_version: str = Field(..., description="History requirement version string")
    history_requirement_sha256: str = Field(..., description="SHA-256 checksum of canonical history requirement")


class ModelFeatureStageOutput(BaseModel):
    """Structured stage output for a single model's runtime feature extraction."""
    model_config = ConfigDict(extra="forbid")

    artifact_ref: ArtifactReference = Field(..., description="Reference to model feature matrix NPY file")
    model_version: str = Field(..., description="Associated model artifact version")
    feature_schema_version: str = Field(..., description="Feature schema version")
    history_requirement_version: str = Field(..., description="History requirement version")


class EquipmentDeliveryOutput(BaseModel):
    """Per-equipment delivery output state recorded in Checkpoint 5."""
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="Deterministic event ID for equipment batch")
    payload_sha256: str = Field(..., description="SHA-256 checksum of canonical batch payload")
    status: Literal["published", "pending", "failed"] = Field("published", description="Outbox delivery registration status")
    outbox_ref: Optional[ArtifactReference] = Field(None, description="Artifact reference to stored outbox file")


class PredictionResultSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uri: str = Field(..., min_length=1)
    sha256: str = Field(..., pattern=SHA256_PATTERN)

    @field_validator("sha256")
    @classmethod
    def validate_non_zero_sha256(cls, v: str) -> str:
        if v == "0" * 64:
            raise ValueError("SHA-256 checksum cannot be all zeros.")
        return v


class PredictionResultLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_session_id: Optional[str] = None
    overlay_branch_id: Optional[str] = None
    history_segment_id: Optional[str] = None
    maintenance_event_id: Optional[str] = None
    maintenance_action_id: Optional[str] = None
    state_version: Optional[int] = None


class RuntimeSourceContext(BaseModel):
    """Canonical runtime source context preserved across Enqueue, Queue, RunState, Checkpoint, and Batch."""
    model_config = ConfigDict(extra="forbid")

    source_uri: str = Field(..., min_length=1)
    source_checksum: str = Field(..., pattern=SHA256_PATTERN)
    source_kind: Literal["live_sensor", "simulation_overlay", "maintenance_replay_overlay"]
    source_contract_version: str = Field(..., min_length=1)
    source_schema_version: str = Field(..., min_length=1)
    pipeline_contract_version: str = Field(..., min_length=1)
    lineage: PredictionResultLineage = Field(default_factory=PredictionResultLineage)

    @field_validator("source_checksum")
    @classmethod
    def validate_non_zero_source_checksum(cls, v: str) -> str:
        if v == "0" * 64:
            raise ValueError("source_checksum cannot be all zeros.")
        return v

    @model_validator(mode="after")
    def validate_overlay_lineage(self) -> RuntimeSourceContext:
        if self.source_kind == "maintenance_replay_overlay":
            lin = self.lineage
            if (
                not lin
                or not (lin.simulation_session_id and str(lin.simulation_session_id).strip())
                or not (lin.overlay_branch_id and str(lin.overlay_branch_id).strip())
                or not (lin.history_segment_id and str(lin.history_segment_id).strip())
                or not (lin.maintenance_event_id and str(lin.maintenance_event_id).strip())
                or not (lin.maintenance_action_id and str(lin.maintenance_action_id).strip())
                or lin.state_version is None
                or lin.state_version < 1
            ):
                raise ValueError(
                    "When source_kind is 'maintenance_replay_overlay', all 6 lineage fields "
                    "(simulation_session_id, overlay_branch_id, history_segment_id, maintenance_event_id, "
                    "maintenance_action_id, state_version >= 1) are required."
                )
        return self


class RuntimeInputIdentity(BaseModel):
    """Canonical identity combining Dataset specification and complete RuntimeSourceContext."""
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(..., min_length=1, description="Dataset identifier")
    dataset_version: str = Field(..., min_length=1, description="Dataset version string")
    source: RuntimeSourceContext = Field(..., description="Canonical runtime source context")


class PredictionResultBatchSourceContext(BaseModel):
    """Canonical source and dataset context for external Prediction Result Batch."""
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(..., min_length=1, description="Dataset identifier")
    dataset_version: str = Field(..., min_length=1, description="Dataset version string")
    source_uri: str = Field(..., min_length=1, description="Source file relative or logical URI")
    source_checksum: str = Field(..., pattern=SHA256_PATTERN, description="Source file SHA-256")
    source_kind: Literal["live_sensor", "simulation_overlay", "maintenance_replay_overlay"] = Field(..., description="Source kind")
    source_contract_version: str = Field(..., min_length=1, description="Source contract version")
    source_schema_version: str = Field(..., min_length=1, description="Source schema version")
    pipeline_contract_version: str = Field(..., min_length=1, description="Pipeline contract version")
    lineage: PredictionResultLineage = Field(default_factory=PredictionResultLineage, description="Traceability lineage")

    @field_validator("source_checksum")
    @classmethod
    def validate_non_zero_source_checksum(cls, v: str) -> str:
        if v == "0" * 64:
            raise ValueError("source_checksum cannot be all zeros.")
        return v

    @model_validator(mode="after")
    def validate_overlay_lineage(self) -> PredictionResultBatchSourceContext:
        if self.source_kind == "maintenance_replay_overlay":
            lin = self.lineage
            if (
                not lin
                or not (lin.simulation_session_id and str(lin.simulation_session_id).strip())
                or not (lin.overlay_branch_id and str(lin.overlay_branch_id).strip())
                or not (lin.history_segment_id and str(lin.history_segment_id).strip())
                or not (lin.maintenance_event_id and str(lin.maintenance_event_id).strip())
                or not (lin.maintenance_action_id and str(lin.maintenance_action_id).strip())
                or lin.state_version is None
                or lin.state_version < 1
            ):
                raise ValueError(
                    "When source_kind is 'maintenance_replay_overlay', all 6 lineage fields "
                    "(simulation_session_id, overlay_branch_id, history_segment_id, maintenance_event_id, "
                    "maintenance_action_id, state_version >= 1) are required."
                )
        return self

    @classmethod
    def from_runtime_input(cls, runtime_input: RuntimeInputIdentity) -> PredictionResultBatchSourceContext:
        return cls(
            dataset_id=runtime_input.dataset_id,
            dataset_version=runtime_input.dataset_version,
            source_uri=runtime_input.source.source_uri,
            source_checksum=runtime_input.source.source_checksum,
            source_kind=runtime_input.source.source_kind,
            source_contract_version=runtime_input.source.source_contract_version,
            source_schema_version=runtime_input.source.source_schema_version,
            pipeline_contract_version=runtime_input.source.pipeline_contract_version,
            lineage=runtime_input.source.lineage,
        )


def compute_model_set_payload_sha256(
    *,
    model_set_id: str,
    model_set_version: str,
    models: list[ActiveModelSnapshotItem] | dict[str, Any],
) -> str:
    """Compute canonical SHA-256 digest for an Active Model Set snapshot.

    Includes model_set_id, model_set_version, ordered model membership,
    individual model versions, required flag, and manifest checksums.
    """
    import hashlib
    import json

    canonical_models = []
    if isinstance(models, list):
        for item in sorted(models, key=lambda m: m.model_id if isinstance(m, ActiveModelSnapshotItem) else m["model_id"]):
            if isinstance(item, ActiveModelSnapshotItem):
                canonical_models.append({
                    "model_id": item.model_id,
                    "model_version": item.model_version,
                    "required": item.required,
                    "manifest_sha256": item.model_artifact_manifest_sha256,
                    "selected_threshold": item.selected_threshold,
                })
            else:
                canonical_models.append({
                    "model_id": item["model_id"],
                    "model_version": item["model_version"],
                    "required": item.get("required", True),
                    "manifest_sha256": item.get("manifest_sha256") or item.get("model_artifact_manifest_sha256", ""),
                    "selected_threshold": item.get("selected_threshold"),
                })
    elif isinstance(models, dict):
        for mid in sorted(models.keys()):
            val = models[mid]
            mver = val.model_version if hasattr(val, "model_version") else val.get("model_version")
            req = val.required if hasattr(val, "required") else val.get("required", True)
            msha = (
                getattr(val, "manifest_sha256", None)
                or (val.get("manifest_sha256") if isinstance(val, dict) else None)
                or (val.get("model_artifact_manifest_sha256") if isinstance(val, dict) else None)
                or ""
            )
            canonical_models.append({
                "model_id": mid,
                "model_version": mver,
                "required": req,
                "manifest_sha256": msha,
                "selected_threshold": (
                    getattr(val, "selected_threshold", None)
                    if hasattr(val, "selected_threshold")
                    else val.get("selected_threshold")
                    if isinstance(val, dict)
                    else None
                ),
            })

    canonical_payload = {
        "model_set_id": model_set_id,
        "model_set_version": model_set_version,
        "models": canonical_models,
    }
    canonical_json = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class PipelineCheckpoint(BaseModel):
    """State checkpoint recorded at end of each stage for resumption."""
    model_config = ConfigDict(extra="forbid")

    checkpoint_version: str = Field("generator-runtime-checkpoint-v1", description="Checkpoint schema version")
    run_id: str = Field(..., description="Run identifier")
    job_id: str = Field(..., description="Job identifier")
    source_identity: str = Field(..., description="Source identity SHA-256")
    source_uri: str = Field(..., description="Source file relative or logical URI")
    source_checksum: str = Field(..., description="Source file SHA-256")
    source_size_bytes: Optional[int] = Field(None, description="Source file size in bytes")
    dataset_id: str = Field(..., description="Dataset ID")
    dataset_version: str = Field(..., description="Dataset version")
    model_set_id: str = Field(..., min_length=1, description="Active Model Set ID pinned at execution time")
    model_set_version: str = Field(..., min_length=1, description="Active Model Set version string")
    model_set_payload_sha256: str = Field(..., pattern=SHA256_PATTERN, description="Canonical SHA-256 digest of Active Model Set")
    pipeline_contract_version: str = Field("generator-prediction-result-v1", description="Pipeline contract version")
    source_kind: str = Field(..., min_length=1, description="Source kind")
    source_contract_version: str = Field(..., min_length=1, description="Source contract version")
    source_schema_version: str = Field(..., min_length=1, description="Source schema version")
    lineage_json: str = Field(..., description="Lineage JSON serialization")
    source_context: RuntimeSourceContext = Field(..., description="Snapshot of RuntimeSourceContext")
    last_completed_stage: Optional[Literal[
        "source_validated",
        "preprocessing",
        "runtime_feature",
        "runtime_prediction",
        "batch_building",
        "prediction_delivery"
    ]] = Field(None, description="Last completed stage name")
    next_stage: Optional[Literal[
        "preprocessing",
        "runtime_feature",
        "runtime_prediction",
        "batch_building",
        "prediction_delivery",
        "completed"
    ]] = Field(None, description="Next stage to execute")
    status: Literal["resumable", "debug_only", "cleanup_pending", "completed", "invalidated"] = Field(
        "resumable", description="Checkpoint lifecycle status"
    )
    created_at: str = Field(default_factory=now_utc_iso, description="Created timestamp")
    updated_at: str = Field(default_factory=now_utc_iso, description="Updated timestamp")
    stage_outputs: dict[str, list[ArtifactReference]] = Field(default_factory=dict, description="Validated output artifact references by stage")
    model_stage_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict, description="Structured model-specific outputs, e.g. runtime_feature by model_id")
    delivery_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict, description="Per-equipment delivery output states by asset_id")
    batch_manifest_ref: Optional[ArtifactReference] = Field(None, description="Reference to staged batch manifest")
    model_snapshot: dict[str, dict[str, Any]] = Field(default_factory=dict, description="Active model versions, manifest checksums and schemas")
    snapshot_validation_status: Optional[Literal["valid", "incompatible", "partially_invalid", "unvalidated"]] = Field(
        "unvalidated", description="Validation status of model snapshot against active model artifacts"
    )
    errors: list[PipelineError] = Field(default_factory=list, description="Historical error list")

    @field_validator("source_identity", "source_checksum", "model_set_payload_sha256")
    @classmethod
    def validate_non_zero_sha256(cls, v: str) -> str:
        if v == "0" * 64:
            raise ValueError("SHA-256 checksum cannot be all zeros.")
        return v


class PipelineRunState(BaseModel):
    """Complete execution record for a single pipeline run."""
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., description="Unique run identifier (UUID/timestamp based)")
    job_id: str = Field(..., description="Queue job identifier")
    status: Literal[
        "pending",
        "queued",
        "running",
        "succeeded",
        "succeeded_with_cleanup_warning",
        "partially_succeeded",
        "failed",
    ] = Field("pending", description="Overall pipeline run status")
    current_stage: Optional[str] = Field(None, description="Currently active stage")
    source_ref: ArtifactReference = Field(..., description="Source observation protocol file reference")
    source_context: Optional[RuntimeSourceContext] = Field(
        None,
        description="Snapshot of RuntimeSourceContext at run start; absent only on legacy persisted run records",
    )
    stages: dict[str, StageState] = Field(default_factory=dict, description="Stage execution map")
    prediction_results: list[InternalModelPredictionResult] = Field(
        default_factory=list, description="Array of prediction results for all registered models across equipments"
    )
    prediction_delivery_status: Optional[Literal["not_required", "pending", "sent", "failed"]] = Field(
        None, description="Prediction delivery dispatch status"
    )
    prediction_event_ids: list[str] = Field(
        default_factory=list, description="List of generated prediction batch event IDs"
    )
    prediction_events: list[PredictionDeliveryEventState] = Field(
        default_factory=list, description="List of per-event delivery states"
    )
    started_at: Optional[str] = Field(None, description="ISO start timestamp")
    finished_at: Optional[str] = Field(None, description="ISO finish timestamp")
    errors: list[PipelineError] = Field(default_factory=list, description="List of errors occurred")

    # Resumption, checkpoint, and intermediate cleanup lifecycle fields
    last_completed_stage: Optional[str] = Field(None, description="Last completed stage name")
    next_stage: Optional[str] = Field(None, description="Next stage to execute")
    resume_count: int = Field(0, ge=0, description="Number of times this run was resumed")
    resumed_from_stage: Optional[str] = Field(None, description="Stage from which this execution resumed")
    checkpoint_status: Optional[Literal["resumable", "debug_only", "cleanup_pending", "completed", "invalidated"]] = Field(
        None, description="Checkpoint lifecycle status"
    )
    cleanup_status: Optional[Literal["not_started", "cleanup_pending", "cleaned", "cleanup_failed", "cleanup_skipped"]] = Field(
        "not_started", description="Intermediate output cleanup status"
    )
    intermediate_outputs: list[ArtifactReference] = Field(
        default_factory=list, description="List of run-dedicated intermediate artifacts subject to cleanup"
    )
    checkpoint: Optional[PipelineCheckpoint] = Field(None, description="Current persistent stage checkpoint")
    batch_manifest_ref: Optional[ArtifactReference] = Field(None, description="Reference to staged batch manifest")
    model_stage_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict, description="Structured stage outputs by model_id")
    delivery_outputs: dict[str, dict[str, Any]] = Field(default_factory=dict, description="Per-equipment delivery output states")
    cleanup_deleted_paths: list[str] = Field(default_factory=list, description="List of successfully deleted paths during cleanup")
    cleanup_failed_paths: list[str] = Field(default_factory=list, description="List of paths that failed to delete during cleanup")


def compute_source_identity(
    *,
    source_checksum: str,
    dataset_id: str,
    dataset_version: str,
    pipeline_contract_version: str,
    source_contract_version: str,
    source_schema_version: str,
    source_kind: str,
    lineage: PredictionResultLineage | dict[str, Any] | None = None,
) -> str:
    """Compute stable, version-aware deduplication identity for source input including full source context."""
    import hashlib
    import json

    if isinstance(lineage, PredictionResultLineage):
        lineage_dict = lineage.model_dump(mode="json")
    elif isinstance(lineage, dict):
        lineage_dict = dict(lineage)
    else:
        lineage_dict = {}

    identity_payload = {
        "dataset_id": dataset_id.strip(),
        "dataset_version": dataset_version.strip(),
        "lineage": lineage_dict,
        "pipeline_contract_version": pipeline_contract_version.strip(),
        "source_checksum": source_checksum.strip().lower(),
        "source_contract_version": source_contract_version.strip(),
        "source_kind": source_kind.strip(),
        "source_schema_version": source_schema_version.strip(),
    }
    canonical_json = json.dumps(
        identity_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compute_source_context_digest(
    source_context: PredictionResultBatchSourceContext | RuntimeInputIdentity | RuntimeSourceContext | dict[str, Any],
    *,
    dataset_id: Optional[str] = None,
    dataset_version: Optional[str] = None,
) -> str:
    """Compute canonical 64-character SHA-256 digest of source context."""
    if isinstance(source_context, PredictionResultBatchSourceContext):
        return compute_source_identity(
            source_checksum=source_context.source_checksum,
            dataset_id=source_context.dataset_id,
            dataset_version=source_context.dataset_version,
            pipeline_contract_version=source_context.pipeline_contract_version,
            source_contract_version=source_context.source_contract_version,
            source_schema_version=source_context.source_schema_version,
            source_kind=source_context.source_kind,
            lineage=source_context.lineage,
        )
    elif isinstance(source_context, RuntimeInputIdentity):
        return compute_source_identity(
            source_checksum=source_context.source.source_checksum,
            dataset_id=source_context.dataset_id,
            dataset_version=source_context.dataset_version,
            pipeline_contract_version=source_context.source.pipeline_contract_version,
            source_contract_version=source_context.source.source_contract_version,
            source_schema_version=source_context.source.source_schema_version,
            source_kind=source_context.source.source_kind,
            lineage=source_context.source.lineage,
        )
    elif isinstance(source_context, RuntimeSourceContext):
        if not dataset_id or not dataset_version:
            raise ValueError("dataset_id and dataset_version are required when source_context is RuntimeSourceContext.")
        return compute_source_identity(
            source_checksum=source_context.source_checksum,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            pipeline_contract_version=source_context.pipeline_contract_version,
            source_contract_version=source_context.source_contract_version,
            source_schema_version=source_context.source_schema_version,
            source_kind=source_context.source_kind,
            lineage=source_context.lineage,
        )
    elif isinstance(source_context, dict):
        d_ctx = dict(source_context)
        d_id = dataset_id or d_ctx.get("dataset_id")
        d_ver = dataset_version or d_ctx.get("dataset_version")
        if not d_id or not d_ver:
            raise ValueError("dataset_id and dataset_version are required in dictionary source_context.")
        return compute_source_identity(
            source_checksum=d_ctx.get("source_checksum") or (d_ctx.get("source_ref", {}).get("sha256") if isinstance(d_ctx.get("source_ref"), dict) else ""),
            dataset_id=str(d_id),
            dataset_version=str(d_ver),
            pipeline_contract_version=str(d_ctx.get("pipeline_contract_version", "")),
            source_contract_version=str(d_ctx.get("source_contract_version", "")),
            source_schema_version=str(d_ctx.get("source_schema_version", "")),
            source_kind=str(d_ctx.get("source_kind", "")),
            lineage=d_ctx.get("lineage"),
        )
    else:
        raise TypeError(f"Unsupported source_context type: {type(source_context)}")


def compute_prediction_result_item_event_id(
    *,
    source_context_digest: str,
    asset_id: str,
    observed_at: datetime | str,
    model_id: str,
    model_version: str,
    model_artifact_manifest_sha256: Optional[str] = None,
) -> str:
    """Compute deterministic item event_id incorporating canonical source context digest."""
    import hashlib
    if isinstance(observed_at, datetime):
        obs_dt = observed_at
        if obs_dt.tzinfo is None:
            obs_dt = obs_dt.replace(tzinfo=timezone.utc)
        obs_str = obs_dt.isoformat().replace("+00:00", "Z")
    else:
        obs_str = str(observed_at).strip()

    item_key = (
        f"prediction-result-batch-v1:{source_context_digest}:{asset_id}:{obs_str}:"
        f"{model_id}:{model_version}:{model_artifact_manifest_sha256 or ''}"
    )
    return f"evt-{hashlib.sha256(item_key.encode('utf-8')).hexdigest()[:32]}"


def compute_prediction_result_batch_id(
    *,
    source_context_digest: str,
    model_set_id: str,
    model_set_version: str,
    model_set_payload_sha256: str,
    sorted_event_ids: list[str],
) -> str:
    """Compute deterministic external batch_id incorporating canonical source context digest and model set digest."""
    import hashlib
    batch_key = (
        f"prediction-result-batch-v1:{source_context_digest}:"
        f"{model_set_id}:{model_set_version}:{model_set_payload_sha256}:"
        f"{','.join(sorted_event_ids)}"
    )
    return f"batch-{hashlib.sha256(batch_key.encode('utf-8')).hexdigest()[:24]}"


class PipelineQueueItem(BaseModel):
    """Item managed in persistent FIFO queue."""
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., min_length=1, description="Unique job identifier")
    source_uri: str = Field(..., min_length=1, description="Source file relative or absolute URI")
    source_checksum: str = Field(..., pattern=SHA256_PATTERN, description="Source file SHA-256 checksum")
    source_identity: Optional[str] = Field(None, description="SHA-256 deduplication identity of input and contract versions")
    size_bytes: Optional[int] = Field(None, ge=0, description="File size in bytes at detection time")
    dataset_id: str = Field(..., min_length=1, description="Dataset identifier")
    dataset_version: str = Field(..., min_length=1, description="Dataset version")
    pipeline_contract_version: str = Field(..., min_length=1, description="Pipeline contract version")
    source_kind: Literal["live_sensor", "simulation_overlay", "maintenance_replay_overlay"]
    source_contract_version: str = Field(..., min_length=1, description="Source contract version")
    source_schema_version: str = Field(..., min_length=1, description="Source schema version")
    lineage: PredictionResultLineage = Field(default_factory=PredictionResultLineage, description="Overlay lineage metadata")
    detected_at: str = Field(default_factory=now_utc_iso, description="ISO detection timestamp")
    sequence: int = Field(1, ge=1, description="FIFO sequence number")
    attempt: int = Field(1, ge=1, description="Execution attempt number")
    retry_of_job_id: Optional[str] = Field(None, description="Previous failed job ID if re-enqueued")
    status: Literal[
        "detected",
        "queued",
        "running",
        "succeeded",
        "retry_wait",
        "failed",
        "dead_letter",
    ] = Field("queued", description="Queue item state")
    error_code: Optional[str] = Field(None, description="Error code if item failed")

    @field_validator("source_checksum")
    @classmethod
    def validate_non_zero_source_checksum(cls, v: str) -> str:
        if v == "0" * 64:
            raise ValueError("source_checksum cannot be all zeros.")
        return v


class SourceLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_uri: str
    source_checksum: str
    pipeline_contract_version: str = "generator-prediction-result-v1"


class PredictionResultProducer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: Literal["systems.generator"] = "systems.generator"
    runtime_version: str = Field(..., min_length=1)
    outbox_id: Optional[str] = None


class PredictionResultTopFactorExpression(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: str = Field(..., min_length=1)
    display_name: Optional[str] = None
    feature_value: Optional[float | int | str | bool] = None
    signed_contribution: float
    direction: Literal["risk_up", "risk_down"]
    explanation_method: str = Field(..., min_length=1)
    evidence_field_id: Optional[str] = None
    source_ref: Optional[PredictionResultSourceRef] = None


class PredictionResultExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_factors: list[PredictionResultTopFactorExpression] = Field(default_factory=list, max_length=5)
    confidence_label: Optional[str] = None
    explanation_method: Optional[str] = None
    feature_snapshot_ref: Optional[PredictionResultSourceRef] = None
    sensor_window_ref: Optional[PredictionResultSourceRef] = None
    display_labels: dict[str, str] = Field(default_factory=dict)


class PredictionResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., min_length=1)
    asset_id: str = Field(..., min_length=1)
    observed_at: datetime
    source_kind: Literal["live_sensor", "simulation_overlay", "maintenance_replay_overlay"]
    source_ref: PredictionResultSourceRef
    payload_sha256: str = Field(..., pattern=SHA256_PATTERN)
    output_status: Literal[
        "predicted",
        "warming_up",
        "history_insufficient",
        "failed_source_unavailable",
        "failed_model_artifact",
        "failed_feature_execution",
        "failed_model_inference",
    ]
    score: Optional[float] = None
    model_id: str = Field(..., min_length=1)
    model_version: str = Field(..., min_length=1)
    model_artifact_manifest_sha256: Optional[str] = Field(None, pattern=SHA256_PATTERN)
    feature_schema_version: Optional[str] = Field(None, min_length=1)
    history_requirement_version: Optional[str] = Field(None, min_length=1)
    label_schema_version: Optional[str] = Field(None, min_length=1)
    feature_schema_sha256: Optional[str] = Field(None, pattern=SHA256_PATTERN)
    history_requirement_sha256: Optional[str] = Field(None, pattern=SHA256_PATTERN)
    label_schema_sha256: Optional[str] = Field(None, pattern=SHA256_PATTERN)
    lineage: PredictionResultLineage
    explanation: Optional[PredictionResultExplanation] = None
    failure_reason: Optional[str] = None

    @field_validator(
        "payload_sha256",
        "model_artifact_manifest_sha256",
        "feature_schema_sha256",
        "history_requirement_sha256",
        "label_schema_sha256",
    )
    @classmethod
    def validate_non_zero_sha256(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v == "0" * 64:
            raise ValueError("SHA-256 checksum cannot be all zeros.")
        return v

    @model_validator(mode="after")
    def validate_semantics(self) -> PredictionResultItem:
        import math
        if self.score is not None:
            if not math.isfinite(self.score):
                raise ValueError(f"Score must be a finite number, got {self.score}")

        if self.output_status == "predicted":
            if self.score is None:
                raise ValueError("Score is required when output_status is 'predicted'")
            if not (0.0 <= self.score <= 1.0):
                raise ValueError(f"Score must be between 0.0 and 1.0, got {self.score}")
            if self.failure_reason is not None:
                raise ValueError("failure_reason must be None when output_status is 'predicted'")
            if not self.model_artifact_manifest_sha256:
                raise ValueError("model_artifact_manifest_sha256 is required when output_status is 'predicted'")
            if not self.feature_schema_sha256:
                raise ValueError("feature_schema_sha256 is required when output_status is 'predicted'")
            if not self.history_requirement_sha256:
                raise ValueError("history_requirement_sha256 is required when output_status is 'predicted'")
            if not self.label_schema_sha256:
                raise ValueError("label_schema_sha256 is required when output_status is 'predicted'")
            if not self.feature_schema_version or not self.history_requirement_version or not self.label_schema_version:
                raise ValueError("Feature, history, and label schema versions are required when output_status is 'predicted'")
        elif self.output_status in ("warming_up", "history_insufficient", "failed_feature_execution", "failed_model_inference"):
            if self.explanation is not None:
                raise ValueError(f"explanation must be None when output_status is '{self.output_status}'")
            if self.score is not None:
                raise ValueError(f"Score must be None when output_status is '{self.output_status}', got {self.score}")
            if not self.failure_reason or not str(self.failure_reason).strip():
                raise ValueError(f"Non-empty failure_reason is required when output_status is '{self.output_status}'")
            if not self.model_artifact_manifest_sha256:
                raise ValueError(f"model_artifact_manifest_sha256 is required when output_status is '{self.output_status}'")
            if not self.feature_schema_sha256:
                raise ValueError(f"feature_schema_sha256 is required when output_status is '{self.output_status}'")
            if not self.history_requirement_sha256:
                raise ValueError(f"history_requirement_sha256 is required when output_status is '{self.output_status}'")
            if not self.label_schema_sha256:
                raise ValueError(f"label_schema_sha256 is required when output_status is '{self.output_status}'")
            if not self.feature_schema_version or not self.history_requirement_version or not self.label_schema_version:
                raise ValueError(
                    f"Feature, history, and label schema versions are required when output_status is '{self.output_status}'"
                )

        elif self.output_status in ("failed_model_artifact", "failed_source_unavailable"):
            if self.explanation is not None:
                raise ValueError(f"explanation must be None when output_status is '{self.output_status}'")
            if self.score is not None:
                raise ValueError(f"Score must be None when output_status is '{self.output_status}', got {self.score}")
            if not self.failure_reason or not str(self.failure_reason).strip():
                raise ValueError(f"Non-empty failure_reason is required when output_status is '{self.output_status}'")
            if self.model_artifact_manifest_sha256 is not None:
                raise ValueError(f"model_artifact_manifest_sha256 must be None when output_status is '{self.output_status}'")
            if self.feature_schema_sha256 is not None:
                raise ValueError(f"feature_schema_sha256 must be None when output_status is '{self.output_status}'")
            if self.history_requirement_sha256 is not None:
                raise ValueError(f"history_requirement_sha256 must be None when output_status is '{self.output_status}'")
            if self.label_schema_sha256 is not None:
                raise ValueError(f"label_schema_sha256 must be None when output_status is '{self.output_status}'")
            if self.feature_schema_version is not None:
                raise ValueError(f"feature_schema_version must be None when output_status is '{self.output_status}'")
            if self.history_requirement_version is not None:
                raise ValueError(f"history_requirement_version must be None when output_status is '{self.output_status}'")
            if self.label_schema_version is not None:
                raise ValueError(f"label_schema_version must be None when output_status is '{self.output_status}'")

        if self.source_kind == "maintenance_replay_overlay":
            lin = self.lineage
            if (
                not lin
                or not (lin.simulation_session_id and str(lin.simulation_session_id).strip())
                or not (lin.overlay_branch_id and str(lin.overlay_branch_id).strip())
                or not (lin.history_segment_id and str(lin.history_segment_id).strip())
                or not (lin.maintenance_event_id and str(lin.maintenance_event_id).strip())
                or not (lin.maintenance_action_id and str(lin.maintenance_action_id).strip())
                or lin.state_version is None
                or lin.state_version < 1
            ):
                raise ValueError(
                    "When source_kind is 'maintenance_replay_overlay', all 6 lineage fields "
                    "(simulation_session_id, overlay_branch_id, history_segment_id, maintenance_event_id, "
                    "maintenance_action_id, state_version >= 1) are required."
                )

        return self


def compute_prediction_result_item_sha256(item_dict: dict[str, Any]) -> str:
    """Compute canonical SHA-256 for a PredictionResultItem excluding payload_sha256."""
    import hashlib
    import json
    d = dict(item_dict)
    d.pop("payload_sha256", None)
    if d.get("explanation") is None:
        d.pop("explanation", None)
    d = _normalize_prediction_result_checksum_value(d)
    canonical_json = json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def validate_prediction_result_item_checksum(item: PredictionResultItem) -> None:
    """Recompute canonical SHA-256 for item and verify payload_sha256 integrity."""
    from systems.generator.app.runtime_pipeline.pipeline_exception import ModelSetContractInvalidError
    item_dict = item.model_dump(mode="json")
    item_dict.pop("payload_sha256", None)
    computed = compute_prediction_result_item_sha256(item_dict)
    if computed != item.payload_sha256:
        raise ModelSetContractInvalidError(
            f"PredictionResultItem '{item.event_id}' payload_sha256 mismatch: expected '{computed}', got '{item.payload_sha256}'.",
            details=[{"event_id": item.event_id, "expected": computed, "actual": item.payload_sha256}],
            retryable=False,
        )


class PredictionResultBatchPayload(BaseModel):
    """Official external Prediction Result Batch payload (prediction-result-batch-v1)."""
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["prediction-result-batch-v1"] = "prediction-result-batch-v1"
    batch_id: str = Field(..., min_length=1)
    producer: PredictionResultProducer
    emitted_at: datetime
    source_context: PredictionResultBatchSourceContext
    model_set: ActiveModelSetSnapshot
    results: list[PredictionResultItem] = Field(..., min_length=1)


class InternalPredictionResultBatchStage(BaseModel):
    """Generator internal staging payload per equipment (contracts/schemas/generator-runtime-prediction-stage.schema.json).
    Note: This is an internal staging/checkpoint contract and is NOT transmitted to Backend Inbox.
    The official external wire payload is PredictionResultBatchPayload (prediction-result-batch-v1).
    """
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="Unique event identifier")
    run_id: str = Field(..., description="Associated pipeline run ID")
    job_id: str = Field(..., description="Associated queue job ID")
    asset_id: str = Field(..., description="Target equipment identifier")
    observed_at: str = Field(..., description="Observation timestamp in UTC ISO format")
    generated_at: str = Field(default_factory=now_utc_iso, description="Generation timestamp")
    dataset_id: str = Field(..., description="Dataset identifier")
    dataset_version: str = Field(..., description="Dataset version")
    model_set_id: str = Field(..., description="Model set identifier")
    model_set_version: str = Field(..., description="Model set version")
    model_results: dict[str, ModelPredictionResult] = Field(
        ..., description="Map of model_id to model prediction results for this equipment"
    )
    source_lineage: SourceLineage = Field(..., description="Input lineage traceability")
    sensor_data_ref: Optional[dict[str, Any]] = Field(None, description="Sensor data reference")


class PredictionOutboxItem(BaseModel):
    """Item managed in prediction delivery outbox."""
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="Unique event identifier")
    run_id: str = Field(..., description="Associated pipeline run ID")
    job_id: str = Field(..., description="Associated queue job ID")
    asset_id: str = Field(..., description="Target equipment identifier")
    status: Literal["pending", "sending", "sent", "retry_wait", "failed"] = Field(
        "pending", description="Outbox delivery status"
    )
    attempt: int = Field(0, ge=0, description="Attempt count")
    max_attempts: int = Field(5, ge=1, description="Max delivery attempts")
    next_retry_at: Optional[str] = Field(None, description="ISO timestamp for next retry")
    last_error_code: Optional[str] = Field(None, description="Last error code if failed")
    last_error_message: Optional[str] = Field(None, description="Last error message if failed")
    created_at: str = Field(default_factory=now_utc_iso, description="Created timestamp")
    updated_at: str = Field(default_factory=now_utc_iso, description="Updated timestamp")
    payload: PredictionResultBatchPayload = Field(..., description="Batch payload to deliver")
