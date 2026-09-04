"""Pydantic schemas for Generator Training domain API."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

from systems.generator.app.training.training_exception import TrainingContractError


class TrainingRequest(BaseModel):
    """Request model for POST /train and POST /train/{base_model}."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(..., min_length=1, description="Observation dataset identifier")
    dataset_version: str = Field(..., min_length=1, description="Observation dataset version")
    feature_dataset_version: str = Field(..., min_length=1, description="Feature dataset version")
    training_config_version: str = Field(
        default="training-config-v1",
        min_length=1,
        description="Training and evaluation configuration version",
    )
    model_version: str | None = Field(
        default=None,
        description="Optional explicit model version. Auto-generated if omitted.",
    )
    activation_policy: Literal["activate_on_success", "publish_only"] | None = Field(
        default=None,
        description="Deprecated: Model Artifact publication always automatically updates latest.json upon success.",
    )

    @field_validator(
        "dataset_id",
        "dataset_version",
        "feature_dataset_version",
        "training_config_version",
        "model_version",
        mode="after",
    )
    @classmethod
    def validate_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise TrainingContractError("식별자는 빈 문자열일 수 없습니다.")
        if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
            raise TrainingContractError(f"식별자 '{value}'에 허용되지 않는 경로 문자('..', '/', '\\')가 포함되어 있습니다.")
        return cleaned


class ModelTrainingResult(BaseModel):
    """Result of training an individual base model."""

    model_config = ConfigDict(extra="forbid")

    base_model: str
    model_id: str
    model_version: str
    status: Literal["succeeded", "failed", "skipped", "partially_succeeded"]
    published: bool = False
    latest_updated: bool = False
    model_artifact_uri: str | None = None
    artifact_uri: str | None = None
    metrics_summary: dict[str, float] | None = None
    latest_error_code: str | None = None
    latest_error_message: str | None = None
    activated: bool = False
    activation_error_code: str | None = None
    error_code: str | None = None


class TrainingResponse(BaseModel):
    """Response model for POST /train and POST /train/{base_model}."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    run_id: str
    status: Literal["succeeded", "partially_succeeded", "failed"]
    dataset_id: str
    dataset_version: str
    feature_dataset_version: str
    training_config_version: str
    results: list[ModelTrainingResult]
