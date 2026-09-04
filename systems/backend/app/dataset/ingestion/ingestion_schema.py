from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DatasetSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uri: str = Field(min_length=1, max_length=2048)
    media_type: str = Field(min_length=1, max_length=128)
    checksum_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    size_bytes: int | None = Field(default=None, ge=0)
    encoding: str | None = Field(default="utf-8", max_length=64)


class DatasetSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["csv", "xlsx", "json", "jsonl", "parquet"]
    delimiter: str | None = Field(default=None, max_length=8)
    sheet: str | None = Field(default=None, max_length=256)
    required_fields: list[str] = Field(default_factory=list)
    field_aliases: dict[str, list[str]] = Field(default_factory=dict)
    primary_key: list[str] = Field(default_factory=list)
    timestamp_field: str | None = None
    timezone: str | None = "UTC"


class QualityRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    field: str = Field(min_length=1, max_length=256)
    rule: Literal["required", "number", "integer", "datetime", "enum", "min", "max"]
    value: Any = None


class DatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal["1.0"] = "1.0"
    manifest_id: str = Field(min_length=1, max_length=128)
    organization_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    adapter_code: str = Field(min_length=1, max_length=128)
    dataset_name: str = Field(min_length=1, max_length=256)
    dataset_version: str = Field(min_length=1, max_length=128)
    license: str | None = Field(default=None, max_length=256)
    provenance_url: str | None = None
    source: DatasetSource
    schema_: DatasetSchema = Field(alias="schema")
    quality_rules: list[QualityRule] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QuarantinedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_row_number: int | None = Field(default=None, ge=1)
    error_code: str
    error_message: str
    record: dict[str, Any]


class IngestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ingestion_run_id: str
    manifest_id: str
    organization_id: str
    project_id: str
    workspace_id: str
    adapter_code: str
    status: Literal["completed", "completed_with_quarantine", "failed"]
    source_record_count: int = Field(ge=0)
    accepted_record_count: int = Field(ge=0)
    quarantined_record_count: int = Field(ge=0)
    accepted_records: list[dict[str, Any]] = Field(default_factory=list)
    quarantined_records: list[QuarantinedRecord] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @field_validator("quarantined_record_count")
    @classmethod
    def non_negative_quarantine(cls, value: int) -> int:
        return max(0, value)
