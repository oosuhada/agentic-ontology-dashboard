"""Typed Dataset, version, mapping, materialization and projection models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

StoreKind = Literal["relational", "graph", "vector"]
ProjectionStatus = Literal["pending", "indexing", "ready", "failed"]
ProjectionHealth = Literal["pending", "indexing", "ready", "failed", "missing"]
DatasetStatus = Literal["draft", "active", "archived"]
VersionStatus = Literal["registered", "profiling", "projecting", "ready", "failed"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DatasetCreateRequest(StrictModel):
    id: str | None = Field(default=None, min_length=3, max_length=160)
    project_id: str = Field(min_length=3, max_length=160)
    workspace_id: str = Field(min_length=3, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,118}[a-z0-9]$")
    display_name: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=4000)
    source_type: str = Field(default="file", min_length=1, max_length=80)


class DatasetFileCreate(StrictModel):
    uri: str = Field(min_length=1, max_length=2048)
    media_type: str = Field(min_length=1, max_length=128)
    checksum_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    size_bytes: int | None = Field(default=None, ge=0)


class DatasetVersionCreateRequest(StrictModel):
    source_version: str = Field(min_length=1, max_length=160)
    version_label: str | None = Field(default=None, max_length=160)
    manifest_id: str | None = Field(default=None, max_length=160)
    checksum_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")
    profile: dict[str, Any] = Field(default_factory=dict)
    record_count: int = Field(default=0, ge=0)
    files: list[DatasetFileCreate] = Field(default_factory=list)


class OntologyMappingCreateRequest(StrictModel):
    object_type: str = Field(min_length=1, max_length=160)
    identity_field: str = Field(min_length=1, max_length=240)
    property_mapping: dict[str, str] = Field(default_factory=dict)
    relationship_mapping: list[dict[str, Any]] = Field(default_factory=list)
    content_fields: list[str] = Field(default_factory=list)
    allowed_roles: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def identity_is_mapped(self) -> "OntologyMappingCreateRequest":
        if self.property_mapping and self.identity_field not in self.property_mapping:
            self.property_mapping[self.identity_field] = self.identity_field
        return self


class MaterializationCreateRequest(StrictModel):
    source_kind: Literal["analysis_result", "query_result", "projection"]
    source_reference: str = Field(min_length=1, max_length=500)
    format: Literal["parquet", "jsonl", "csv"] = "parquet"
    artifact_uri: str = Field(min_length=1, max_length=2048)
    checksum_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    record_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetPage(StrictModel):
    items: list["DatasetRecord"]
    offset: int
    limit: int
    total: int


class DatasetRecord(StrictModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    slug: str
    display_name: str
    description: str
    source_type: str
    status: DatasetStatus
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime
    latest_version_id: str | None = None
    latest_version_label: str | None = None
    latest_source_version: str | None = None
    record_count: int = 0
    projection_health: dict[StoreKind, ProjectionHealth] = Field(default_factory=dict)


class DatasetFileRecord(StrictModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    dataset_id: str
    dataset_version_id: str
    uri: str
    media_type: str
    checksum_sha256: str
    size_bytes: int | None = None
    created_at: datetime


class DatasetVersionRecord(StrictModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    dataset_id: str
    version_number: int
    version_label: str
    source_version: str
    manifest_id: str | None = None
    checksum_sha256: str
    schema_: dict[str, Any] = Field(alias="schema")
    profile: dict[str, Any]
    record_count: int
    status: VersionStatus
    created_by: str | None = None
    created_at: datetime


class ProjectionRecord(StrictModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    dataset_id: str
    dataset_version_id: str
    store_kind: StoreKind
    status: ProjectionStatus
    object_namespace: str
    source_version: str
    record_count: int
    attempt_count: int
    last_error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class OntologyMappingRecord(StrictModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    dataset_id: str
    dataset_version_id: str
    object_type: str
    identity_field: str
    property_mapping: dict[str, str]
    relationship_mapping: list[dict[str, Any]]
    content_fields: list[str]
    allowed_roles: list[str]
    status: str
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class MaterializationRecord(StrictModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    dataset_id: str
    dataset_version_id: str
    source_kind: str
    source_reference: str
    format: str
    artifact_uri: str
    checksum_sha256: str
    record_count: int
    status: str
    metadata: dict[str, Any]
    created_by: str | None = None
    created_at: datetime


class AdapterIngestionRunRecord(StrictModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    manifest_id: str
    adapter_code: str
    status: str
    source_record_count: int
    accepted_record_count: int
    quarantined_record_count: int
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class QuarantineRecord(StrictModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    ingestion_run_id: str
    source_row_number: int | None = None
    error_code: str
    error_message: str
    record: dict[str, Any]
    created_at: datetime


class DocumentIndexReadiness(StrictModel):
    status: Literal["ready", "indexing", "pending", "failed", "missing", "not_configured"]
    projection_id: str | None = None
    dataset_version_id: str | None = None
    content_fields: list[str] = Field(default_factory=list)
    indexed_record_count: int = 0
    last_error: str | None = None


class DatasetDetail(StrictModel):
    dataset: DatasetRecord
    versions: list[DatasetVersionRecord]
    files: list[DatasetFileRecord] = Field(default_factory=list)
    projections: list[ProjectionRecord]
    mappings: list[OntologyMappingRecord]
    materializations: list[MaterializationRecord]
    ingestion_runs: list[AdapterIngestionRunRecord] = Field(default_factory=list)
    quarantine_records: list[QuarantineRecord] = Field(default_factory=list)
    lineage_references: list[str] = Field(default_factory=list)
    document_index_readiness: DocumentIndexReadiness


class CanonicalObjectEnvelope(StrictModel):
    contract_version: Literal["1.0"] = "1.0"
    organization_id: str
    project_id: str
    workspace_id: str
    dataset_id: str
    dataset_version_id: str
    source_version: str
    object_type: str
    object_id: str
    source_identity: str
    properties: dict[str, Any]
    content: str
    allowed_roles: list[str] = Field(default_factory=list)
    source_record: dict[str, Any]

    @field_validator("object_id")
    @classmethod
    def object_id_is_scoped(cls, value: str) -> str:
        if value.count(":") < 4:
            raise ValueError("canonical object_id must include project, dataset, version and object type scope")
        return value


class ProjectionBatch(StrictModel):
    dataset: DatasetRecord
    version: DatasetVersionRecord
    mapping: OntologyMappingRecord
    objects: list[CanonicalObjectEnvelope]
