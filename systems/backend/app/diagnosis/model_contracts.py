from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SHA256_PATTERN = r"^[a-f0-9]{64}$"
SCHEMA_VERSION = "adaptive-modeling-v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    ACTIVE = "active"
    RETIRED = "retired"
    REJECTED = "rejected"


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
    algorithm: Literal["logistic_regression", "random_forest", "lightgbm", "xgboost"]
    prediction_task: Literal["binary_failure_within_horizon"] = "binary_failure_within_horizon"
    dataset_version_id: str
    mapping_set_id: str
    recipe_set_id: str
    feature_dataset_version_id: str
    label_policy_id: str
    status: ModelStatus
    artifact: ArtifactReference
    input_features: list[str]
    input_schema_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    runtime_versions: dict[str, str] = Field(default_factory=dict)
    calibration_method: str | None = None
    calibration_artifact: ArtifactReference | None = None
    confidence_status: Literal["calibrated", "unavailable_uncalibrated"] = "unavailable_uncalibrated"
    threshold_policy: ThresholdPolicy
    explanation_provider: str
    explanation_provider_version: str
    limitations: list[str] = Field(default_factory=list)
    promotion_gate: dict[str, Any] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)
    activated_at: datetime | None = None
    retired_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelScoreResult(StrictModel):
    prediction_result_id: str
    model_version_id: str
    prediction_task: Literal["binary_failure_within_horizon"]
    failure_probability: float = Field(ge=0, le=1)
    decision_threshold: float = Field(ge=0, le=1)
    predicted_label: Literal["failure_risk", "no_significant_risk"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_status: Literal["calibrated", "unavailable_uncalibrated"]
    observation_id: str
    observed_at: datetime
    input_schema_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    explanation_id: str | None = None


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


__all__ = [
    "ArtifactReference",
    "ExplanationArtifact",
    "ExplanationFactor",
    "ModelScoreResult",
    "ModelStatus",
    "ModelVersion",
    "ThresholdPolicy",
    "canonical_checksum",
]
