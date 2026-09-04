"""Pydantic schemas and contract definitions for Generator Protocol Extraction."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$"
SHA256_PATTERN = r"^[a-f0-9]{64}$"


def _validate_safe_identifier(v: str, field_name: str) -> str:
    cleaned = str(v).strip()
    if not cleaned:
        raise ValueError(f"{field_name}은(는) 빈 문자열일 수 없습니다.")
    if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
        raise ValueError(f"{field_name}에 안전하지 않은 경로 탐색 문자('..', '/', '\\')가 포함되어 있습니다: '{v}'")
    if not re.match(IDENTIFIER_PATTERN, cleaned):
        raise ValueError(f"{field_name}의 형식이 올바르지 않습니다: '{v}' (허용: 영숫자, '.', '_', '-')")
    return cleaned


class ExtractionRequest(BaseModel):
    """Request payload for POST /extraction."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(..., min_length=1, description="Unique API request identifier")
    idempotency_key: str = Field(..., min_length=1, description="Idempotent execution key")
    run_id: str = Field(..., min_length=1, description="Unique extraction run identifier")
    source_uri: str = Field(..., min_length=1, description="Source protocol log file path")
    source_sha256: str = Field(..., pattern=SHA256_PATTERN, description="Expected SHA-256 checksum of source file")
    source_direction: Literal["published", "received"] = Field(
        default="received",
        description="Target transmission direction to extract. Only matching direction records are consumed."
    )
    source_run_manifest_uri: str = Field(
        ...,
        min_length=1,
        description="Upstream gen_data run manifest URI certifying protocol finalization"
    )
    source_run_manifest_sha256: str = Field(
        ...,
        pattern=SHA256_PATTERN,
        description="Upstream gen_data run manifest SHA-256 checksum"
    )
    source_schema_version: str = Field(..., min_length=1, description="Source sensor protocol schema version")
    protocol_version: str = Field(..., min_length=1, description="Protocol version string")
    mapping_id: str = Field(..., min_length=1, description="Approved static mapping table identifier")
    mapping_version: str = Field(..., min_length=1, description="Approved static mapping version string")
    mapping_sha256: str = Field(..., pattern=SHA256_PATTERN, description="SHA-256 checksum of mapping table definition")
    dataset_id: str = Field(..., pattern=IDENTIFIER_PATTERN, description="Target Canonical Observation dataset ID")
    dataset_version: str = Field(..., pattern=IDENTIFIER_PATTERN, description="Target dataset version string")

    @field_validator("request_id", "idempotency_key", "run_id")
    @classmethod
    def validate_keys(cls, v: str) -> str:
        cleaned = str(v).strip()
        if not cleaned:
            raise ValueError("식별자 필드는 빈 문자열일 수 없습니다.")
        if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
            raise ValueError(f"식별자에 안전하지 않은 문자('..', '/', '\\')가 포함되어 있습니다: '{v}'")
        return cleaned

    @field_validator("dataset_id", "dataset_version")
    @classmethod
    def validate_dataset_identifiers(cls, v: str) -> str:
        return _validate_safe_identifier(v, "dataset identifier")

    @field_validator("source_uri", "source_run_manifest_uri")
    @classmethod
    def validate_source_uri(cls, v: str) -> str:
        cleaned = str(v).strip().replace("\\", "/")
        if not cleaned:
            raise ValueError("경로 URI는 빈 문자열일 수 없습니다.")
        if ".." in cleaned.split("/"):
            raise ValueError(f"경로 URI에 상위 디렉터리 탐색(..)이 포함될 수 없습니다: '{v}'")
        return cleaned


class ExtractionTimeRange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_time: str
    max_time: str


class ExtractionResultPayload(BaseModel):
    """Payload body included in ExtractionResponse."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    dataset_version: str
    manifest_uri: str
    manifest_sha256: str = Field(..., pattern=SHA256_PATTERN)
    observations_uri: str
    observations_sha256: str = Field(..., pattern=SHA256_PATTERN)
    provenance_uri: str
    provenance_sha256: str = Field(..., pattern=SHA256_PATTERN)
    rejected_uri: str
    rejected_sha256: str = Field(..., pattern=SHA256_PATTERN)
    total_records_processed: int = Field(..., ge=0)
    observations_count: int = Field(..., ge=0)
    rejected_count: int = Field(..., ge=0)
    asset_ids: list[str] = Field(default_factory=list)
    time_range: Optional[ExtractionTimeRange] = None


class ExtractionResponse(BaseModel):
    """Response returned by POST /extraction."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    idempotency_key: str
    run_id: str
    status: Literal["succeeded"] = "succeeded"
    dataset_id: str
    dataset_version: str
    result: ExtractionResultPayload


# --- Internal Domain Record Models ---

class ProvenanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    observed_at: str
    measurement_key: str
    source_observation_id: str
    source_sequence: int
    source_direction: str
    source_status_code: Optional[str] = None
    source_quality: Optional[str] = None
    mapping_id: str
    mapping_version: str
    mapping_sha256: str
    extraction_run_id: str


class RejectedRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    source_offset: Optional[int] = None
    source_sequence: Optional[int] = None
    source_observation_id: Optional[str] = None
    error_code: str
    error_message: str
    mapping_id: Optional[str] = None
    mapping_version: Optional[str] = None
    run_id: Optional[str] = None
    raw_record_checksum: Optional[str] = None
    rejected_at: str


# --- Task 5: Polling Worker and API Models ---

class ExtractionSourceStatus(BaseModel):
    """Source-level extraction status tracking."""

    model_config = ConfigDict(extra="forbid")

    source_identity: Optional[str] = None
    source_uri: str
    site_id: str
    cell_id: str
    status: Literal[
        "discovered",
        "queued",
        "processing",
        "waiting",
        "blocked",
        "failed",
    ]
    last_started_at: Optional[str] = None
    last_succeeded_at: Optional[str] = None
    last_failed_at: Optional[str] = None
    last_committed_offset: int = 0
    last_observed_at: Optional[str] = None
    last_published_window: Optional[str] = None
    attempt: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: Optional[bool] = None


class RuntimeHandoffStatusSummary(BaseModel):
    """Status summary of runtime prediction handoff queues."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    runtime_prediction_enabled: bool = False
    pending: int = 0
    runtime_disabled: int = 0
    enqueueing: int = 0
    enqueued: int = 0
    retry_wait: int = 0
    blocked: int = 0
    retry_exhausted: int = 0
    last_enqueued_at: Optional[str] = None
    last_error_code: Optional[str] = None


class ExtractionManagerStatus(BaseModel):
    """Manager-level global extraction and worker status."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    running: bool
    poll_interval_seconds: float
    discovered_source_count: int
    queued_source_count: int
    processing_source_count: int
    blocked_source_count: int
    last_poll_started_at: Optional[str] = None
    last_poll_completed_at: Optional[str] = None
    sources: list[ExtractionSourceStatus] = Field(default_factory=list)
    runtime_handoff: Optional[RuntimeHandoffStatusSummary] = None


class PublishedDatasetSummary(BaseModel):
    """Summary of a published dataset within a source processing cycle."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    dataset_version: str
    manifest_uri: str


class SourceProcessingResult(BaseModel):
    """Execution result for a single source extraction."""

    model_config = ConfigDict(extra="forbid")

    source_uri: str
    source_identity: Optional[str] = None
    status: Literal["succeeded", "no_data", "failed", "blocked"]
    start_offset: int
    committed_offset: int
    records_read: int
    observations_staged: int
    rejected_staged: int
    published_datasets: list[PublishedDatasetSummary] = Field(default_factory=list)
    pending_windows: list[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class GenDataExtractionRequest(BaseModel):
    """Request payload for POST /extraction (gen_data sensor stream mode)."""

    model_config = ConfigDict(extra="forbid")

    source_mode: Literal["gen_data_sensor_stream"] = "gen_data_sensor_stream"
    source_uri: Optional[str] = None
    mapping_id: Optional[str] = None
    mapping_version: Optional[str] = None
    mapping_sha256: Optional[str] = None
    flush_before: Optional[datetime] = None
    max_records: Optional[int] = None

    @field_validator("source_uri")
    @classmethod
    def validate_source_uri(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = str(v).strip().replace("\\", "/")
        if not cleaned:
            raise ValueError("source_uri는 빈 문자열일 수 없습니다.")
        if ".." in cleaned.split("/"):
            raise ValueError(f"source_uri에 상위 디렉터리 탐색(..)이 포함될 수 없습니다: '{v}'")
        if cleaned.startswith("/"):
            raise ValueError(f"source_uri는 논리 상대 경로여야 합니다 (절대 경로 불가): '{v}'")
        return cleaned

    @field_validator("max_records")
    @classmethod
    def validate_max_records(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError(f"max_records는 0보다 커야 합니다: {v}")
        return v

    @model_validator(mode="after")
    def validate_mapping_fields(self) -> GenDataExtractionRequest:
        mapping_fields = [self.mapping_id, self.mapping_version, self.mapping_sha256]
        provided = [f for f in mapping_fields if f is not None]
        if provided and len(provided) != 3:
            raise ValueError("mapping_id, mapping_version, mapping_sha256는 모두 지정하거나 모두 생략해야 합니다.")
        if self.mapping_sha256 is not None:
            if not re.match(SHA256_PATTERN, self.mapping_sha256):
                raise ValueError(f"mapping_sha256의 형식이 올바르지 않습니다: '{self.mapping_sha256}'")
        return self


class GenDataExtractionResponse(BaseModel):
    """Response payload for POST /extraction."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    run_id: str
    status: Literal["succeeded", "partially_succeeded", "no_data"]
    processed_sources: int
    succeeded_sources: int
    failed_sources: int
    sources: list[SourceProcessingResult] = Field(default_factory=list)


# --- Task 6: Runtime Handoff Models ---

class ExtractionRuntimeHandoffDataset(BaseModel):
    """Dataset file reference within handoff payload."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(..., min_length=1)
    dataset_version: str = Field(..., min_length=1)
    manifest_uri: str = Field(..., min_length=1)
    observations_uri: str = Field(..., min_length=1)
    observations_sha256: str = Field(..., pattern=SHA256_PATTERN)
    observations_size_bytes: int = Field(..., ge=0)


class ExtractionRuntimeHandoffLineage(BaseModel):
    """Lineage context for runtime input."""

    model_config = ConfigDict(extra="forbid")

    simulation_session_id: Optional[str] = None
    overlay_branch_id: Optional[str] = None
    history_segment_id: Optional[str] = None
    maintenance_event_id: Optional[str] = None
    maintenance_action_id: Optional[str] = None
    state_version: Optional[int] = None


class ExtractionRuntimeHandoffSource(BaseModel):
    """Source context within runtime input identity."""

    model_config = ConfigDict(extra="forbid")

    source_uri: str = Field(..., min_length=1)
    source_checksum: str = Field(..., pattern=SHA256_PATTERN)
    source_kind: Literal["live_sensor"] = "live_sensor"
    source_contract_version: str = Field(..., min_length=1)
    source_schema_version: str = Field(..., min_length=1)
    pipeline_contract_version: Literal["generator-prediction-result-v1"] = "generator-prediction-result-v1"
    lineage: ExtractionRuntimeHandoffLineage = Field(default_factory=ExtractionRuntimeHandoffLineage)


class ExtractionRuntimeHandoffRuntimeInput(BaseModel):
    """Input identity to enqueue into runtime prediction queue."""

    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(..., min_length=1)
    dataset_version: str = Field(..., min_length=1)
    source: ExtractionRuntimeHandoffSource


class ExtractionRuntimeHandoffDelivery(BaseModel):
    """Delivery and retry state of handoff item."""

    model_config = ConfigDict(extra="forbid")

    attempt_count: int = Field(0, ge=0)
    runtime_job_id: Optional[str] = None
    queue_item_id: Optional[str] = None
    last_error_code: Optional[str] = None
    last_error_message: Optional[str] = None
    next_retry_at: Optional[str] = None


class ExtractionRuntimeHandoff(BaseModel):
    """Canonical Extraction -> Runtime Prediction Handoff Record."""

    model_config = ConfigDict(extra="forbid")

    handoff_schema_version: Literal["generator-extraction-runtime-handoff-v1"] = "generator-extraction-runtime-handoff-v1"
    handoff_id: str = Field(..., pattern=SHA256_PATTERN)
    status: Literal[
        "pending",
        "runtime_disabled",
        "enqueueing",
        "enqueued",
        "retry_wait",
        "blocked",
        "retry_exhausted",
    ]
    created_at: str
    updated_at: str
    dataset: ExtractionRuntimeHandoffDataset
    runtime_input: ExtractionRuntimeHandoffRuntimeInput
    delivery: ExtractionRuntimeHandoffDelivery
