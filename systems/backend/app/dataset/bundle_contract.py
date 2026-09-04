"""Public versioned multi-file Dataset Bundle contracts.

The bundle checksum intentionally excludes local URIs, file ordering, manifest
identity, and tenant scope. It identifies immutable dataset content and the
generation/schema contract that produced that content.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SHA256_PATTERN = r"^[a-f0-9]{64}$"
IDENTITY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$"
SOURCE_IDENTITY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$"
FORBIDDEN_RUNTIME_ROLES = {
    "evaluation_truth",
    "failure_schedule",
    "compressor_failure_truth",
    "cnc_failure_truth",
}


class StrictBundleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BundleFileSchemaMetadata(StrictBundleModel):
    schema_version: str = Field(min_length=1, max_length=128)
    required_fields: list[str] = Field(default_factory=list)
    primary_key: list[str] = Field(default_factory=list)
    timestamp_field: str | None = Field(default=None, max_length=256)
    timezone: str | None = Field(default="UTC", max_length=128)

    @field_validator("required_fields", "primary_key")
    @classmethod
    def fields_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("schema field lists must not contain duplicates")
        return value


class DatasetBundleFile(StrictBundleModel):
    role: str = Field(pattern=r"^[a-z][a-z0-9_]{1,127}$")
    uri: str = Field(min_length=1, max_length=2048)
    format: Literal["csv", "json", "jsonl", "parquet"]
    media_type: str = Field(min_length=1, max_length=128)
    checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=0)
    schema_: BundleFileSchemaMetadata = Field(alias="schema")

    @field_validator("checksum_sha256")
    @classmethod
    def normalize_checksum(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def runtime_file_must_not_be_evaluation_truth(self) -> "DatasetBundleFile":
        normalized_uri = self.uri.replace("\\", "/").lower()
        if self.role in FORBIDDEN_RUNTIME_ROLES:
            raise ValueError(f"evaluation truth role is forbidden in runtime bundle files: {self.role}")
        if "/evaluation_truth/" in f"/{normalized_uri.strip('/')}/":
            raise ValueError("canonical/evaluation_truth artifacts cannot be runtime bundle files")
        return self


class PredictiveMaintenanceSourceContract(StrictBundleModel):
    compressor_and_cnc_independent: bool
    topology_relation_is_not_causal_truth: bool
    upstream_features_in_source: bool
    synthetic_effect_columns_in_source: bool
    prediction_outputs_in_source: bool
    evaluation_truth_separate: Literal[True]
    cnc_ai4i_physical_relations: Literal[True] | None = None
    failure_modes_satisfy_sensor_conditions: Literal[True] | None = None
    asset_variability_policy: Literal[
        "small_offsets_plus_time_varying_physical_process"
    ] | None = None

    @model_validator(mode="after")
    def v3_fields_are_declared_as_one_contract(self) -> "PredictiveMaintenanceSourceContract":
        values = (
            self.cnc_ai4i_physical_relations,
            self.failure_modes_satisfy_sensor_conditions,
            self.asset_variability_policy,
        )
        if any(value is not None for value in values) and not all(
            value is not None for value in values
        ):
            raise ValueError("predictive maintenance v3 source-contract fields must be declared together")
        return self

    @property
    def is_v3(self) -> bool:
        return self.cnc_ai4i_physical_relations is True


class BundleGovernanceArtifact(StrictBundleModel):
    role: Literal[
        "package_validation",
        "agent_example_evaluation",
    ]
    uri: str = Field(min_length=1, max_length=2048)
    checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    media_type: Literal["application/json"] = "application/json"
    summary: dict[str, Any] = Field(default_factory=dict)

    @field_validator("checksum_sha256")
    @classmethod
    def normalize_governance_checksum(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def governance_artifact_must_not_be_runtime_truth(self) -> "BundleGovernanceArtifact":
        normalized_uri = self.uri.replace("\\", "/").lower()
        if "/evaluation_truth/" in f"/{normalized_uri.strip('/')}/" or "/hidden_truth/" in f"/{normalized_uri.strip('/')}/":
            raise ValueError("truth and hidden-truth files cannot be governance artifacts")
        forbidden_summary_keys = {
            "event_condition_details",
            "condition_variant",
            "failure_occurred_at",
            "failure_schedule",
            "hidden_truth",
            "source_event_id",
        }

        def contains_forbidden_key(value: Any) -> bool:
            if isinstance(value, dict):
                for key, item in value.items():
                    if str(key).lower() in forbidden_summary_keys:
                        return True
                    if contains_forbidden_key(item):
                        return True
            elif isinstance(value, list):
                return any(contains_forbidden_key(item) for item in value)
            return False

        if contains_forbidden_key(self.summary):
            raise ValueError("governance summaries cannot expose evaluation or hidden-truth details")
        return self


class BundleGenerationMetadata(StrictBundleModel):
    generator_version: str = Field(min_length=1, max_length=128)
    seed: int
    period_start: datetime
    period_end: datetime
    observation_interval_minutes: int = Field(gt=0)
    rate_profile: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def period_is_forward(self) -> "BundleGenerationMetadata":
        if self.period_end <= self.period_start:
            raise ValueError("generation period_end must be after period_start")
        return self


def _canonical_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("bundle generation datetimes must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bundle_checksum_payload(
    *,
    dataset_version: str,
    schema_version: str,
    generation: BundleGenerationMetadata,
    source_contract: PredictiveMaintenanceSourceContract,
    files: list[DatasetBundleFile],
) -> dict[str, Any]:
    """Return the path- and order-independent checksum payload."""

    canonical_files = [
        {
            "role": item.role,
            "checksum_sha256": item.checksum_sha256.lower(),
            "format": item.format,
            "media_type": item.media_type,
            "schema": item.schema_.model_dump(mode="json", exclude_none=True),
        }
        for item in sorted(files, key=lambda item: item.role)
    ]
    return {
        "dataset_version": dataset_version,
        "schema_version": schema_version,
        "generation": {
            "generator_version": generation.generator_version,
            "seed": generation.seed,
            "period_start": _canonical_datetime(generation.period_start),
            "period_end": _canonical_datetime(generation.period_end),
            "observation_interval_minutes": generation.observation_interval_minutes,
            "rate_profile": generation.rate_profile,
        },
        "source_contract": source_contract.model_dump(mode="json", exclude_none=True),
        "files": canonical_files,
    }


def compute_bundle_checksum(
    *,
    dataset_version: str,
    schema_version: str,
    generation: BundleGenerationMetadata,
    source_contract: PredictiveMaintenanceSourceContract,
    files: list[DatasetBundleFile],
) -> str:
    payload = canonical_bundle_checksum_payload(
        dataset_version=dataset_version,
        schema_version=schema_version,
        generation=generation,
        source_contract=source_contract,
        files=files,
    )
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class DatasetBundleManifestV2(StrictBundleModel):
    manifest_version: Literal["2.0"] = "2.0"
    manifest_id: str = Field(pattern=IDENTITY_PATTERN)
    organization_id: str = Field(pattern=IDENTITY_PATTERN)
    project_id: str = Field(pattern=IDENTITY_PATTERN)
    workspace_id: str = Field(pattern=IDENTITY_PATTERN)
    adapter_code: str = Field(pattern=IDENTITY_PATTERN)
    dataset_name: str = Field(min_length=1, max_length=256)
    dataset_version: str = Field(min_length=1, max_length=160)
    schema_version: str = Field(min_length=1, max_length=128)
    bundle_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    generation: BundleGenerationMetadata
    source_contract: PredictiveMaintenanceSourceContract
    files: list[DatasetBundleFile] = Field(min_length=1)
    governance_artifacts: list[BundleGovernanceArtifact] = Field(default_factory=list)
    created_at: datetime

    @field_validator("bundle_checksum_sha256")
    @classmethod
    def normalize_bundle_checksum(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def validate_roles_and_checksum(self) -> "DatasetBundleManifestV2":
        roles = [item.role for item in self.files]
        if len(roles) != len(set(roles)):
            raise ValueError("bundle file roles must be unique")
        governance_roles = [item.role for item in self.governance_artifacts]
        if len(governance_roles) != len(set(governance_roles)):
            raise ValueError("bundle governance artifact roles must be unique")
        expected = compute_bundle_checksum(
            dataset_version=self.dataset_version,
            schema_version=self.schema_version,
            generation=self.generation,
            source_contract=self.source_contract,
            files=self.files,
        )
        if self.bundle_checksum_sha256 != expected:
            raise ValueError("bundle_checksum_sha256 does not match canonical bundle content")
        return self


class BundleValidationIssue(StrictBundleModel):
    """A bounded, serializable sample of a bundle validation failure."""

    role: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2000)
    row_number: int | None = Field(default=None, ge=1)
    record_identity: str | None = Field(default=None, max_length=512)


class BundleRoleValidationSummary(StrictBundleModel):
    role: str = Field(min_length=1, max_length=128)
    uri: str = Field(min_length=1, max_length=2048)
    format: Literal["csv", "json", "jsonl", "parquet"]
    media_type: str = Field(min_length=1, max_length=128)
    status: Literal["pending", "passed", "failed"] = "pending"
    expected_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    actual_checksum_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    checksum_valid: bool = False
    schema_valid: bool = False
    required_fields: list[str] = Field(default_factory=list)
    observed_fields: list[str] = Field(default_factory=list)
    source_record_count: int = Field(default=0, ge=0)
    accepted_record_count: int = Field(default=0, ge=0)
    quarantined_record_count: int = Field(default=0, ge=0)
    issue_counts: dict[str, int] = Field(default_factory=dict)
    earliest_timestamp: datetime | None = None
    latest_timestamp: datetime | None = None

    @model_validator(mode="after")
    def counts_are_consistent(self) -> "BundleRoleValidationSummary":
        if self.accepted_record_count + self.quarantined_record_count != self.source_record_count:
            raise ValueError("role accepted and quarantined counts must equal source count")
        return self


class BundleValidationResult(StrictBundleModel):
    """Streaming validation artifact for one immutable Dataset Bundle.

    The result intentionally carries summaries rather than accepted source rows.
    It can be stored as an ingestion artifact and handed to the Phase 2
    PostgreSQL ingestion port without retaining large CSV/JSONL payloads in
    application memory.
    """

    contract_version: Literal["1.0"] = "1.0"
    artifact_kind: Literal["dataset_bundle_validation"] = "dataset_bundle_validation"
    ingestion_run_id: str = Field(min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=1, max_length=512)
    validation_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    manifest_id: str = Field(pattern=IDENTITY_PATTERN)
    organization_id: str = Field(pattern=IDENTITY_PATTERN)
    project_id: str = Field(pattern=IDENTITY_PATTERN)
    workspace_id: str = Field(pattern=IDENTITY_PATTERN)
    adapter_code: str = Field(pattern=IDENTITY_PATTERN)
    dataset_version: str = Field(min_length=1, max_length=160)
    bundle_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    status: Literal["completed", "failed"]
    source_record_count: int = Field(ge=0)
    validated_record_count: int = Field(ge=0)
    accepted_record_count: int = Field(ge=0)
    quarantined_record_count: int = Field(ge=0)
    materialized_record_count: Literal[0] = 0
    roles: list[BundleRoleValidationSummary]
    issues: list[BundleValidationIssue] = Field(default_factory=list)
    issue_sample_truncated: bool = False
    metrics: dict[str, Any] = Field(default_factory=dict)
    validated_at: datetime

    @model_validator(mode="after")
    def bundle_counts_are_consistent(self) -> "BundleValidationResult":
        if self.validated_record_count + self.quarantined_record_count != self.source_record_count:
            raise ValueError("bundle validated and quarantined counts must equal source count")
        if self.status == "completed":
            if self.issues or self.quarantined_record_count:
                raise ValueError("completed bundle validation cannot contain failures")
            if self.accepted_record_count != self.source_record_count:
                raise ValueError("completed bundle validation must accept every source row")
        elif self.accepted_record_count != 0:
            raise ValueError("failed bundle validation cannot atomically accept source rows")
        return self


class PostgreSQLBundleIngestionResult(StrictBundleModel):
    """Committed PostgreSQL identity and row-count artifact for one bundle."""

    contract_version: Literal["1.0"] = "1.0"
    artifact_kind: Literal["postgresql_bundle_ingestion"] = "postgresql_bundle_ingestion"
    ingestion_run_id: str = Field(min_length=1, max_length=160)
    manifest_record_id: str = Field(min_length=1, max_length=160)
    organization_id: str = Field(pattern=IDENTITY_PATTERN)
    project_id: str = Field(pattern=IDENTITY_PATTERN)
    workspace_id: str = Field(pattern=IDENTITY_PATTERN)
    dataset_id: str = Field(pattern=IDENTITY_PATTERN)
    dataset_version_id: str = Field(pattern=IDENTITY_PATTERN)
    version_number: int = Field(ge=1)
    source_version: str = Field(min_length=1, max_length=160)
    bundle_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    validation_checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    status: Literal["completed"] = "completed"
    reused_dataset_version: bool = False
    row_counts: dict[str, int]
    source_record_count: int = Field(ge=0)
    outbox_event_id: str | None = Field(default=None, max_length=160)
    completed_at: datetime

    @field_validator("row_counts")
    @classmethod
    def row_counts_are_non_negative(cls, value: dict[str, int]) -> dict[str, int]:
        if any(count < 0 for count in value.values()):
            raise ValueError("PostgreSQL ingestion row counts must be non-negative")
        return value

    @model_validator(mode="after")
    def source_count_matches_roles(self) -> "PostgreSQLBundleIngestionResult":
        if sum(self.row_counts.values()) != self.source_record_count:
            raise ValueError("PostgreSQL role row counts must equal source_record_count")
        return self


class DatasetVersionIdentity(StrictBundleModel):
    organization_id: str = Field(pattern=IDENTITY_PATTERN)
    project_id: str = Field(pattern=IDENTITY_PATTERN)
    workspace_id: str = Field(pattern=IDENTITY_PATTERN)
    dataset_id: str = Field(pattern=IDENTITY_PATTERN)
    dataset_version_id: str = Field(pattern=IDENTITY_PATTERN)

    def canonical_key(self) -> str:
        return (
            f"org:{self.organization_id}:project:{self.project_id}:workspace:{self.workspace_id}:"
            f"dataset:{self.dataset_id}:version:{self.dataset_version_id}"
        )


class PostgreSQLObjectIdentity(DatasetVersionIdentity):
    object_type: str = Field(pattern=IDENTITY_PATTERN)
    source_identity: str = Field(pattern=SOURCE_IDENTITY_PATTERN)

    def canonical_key(self) -> str:
        return f"{super().canonical_key()}:object:{self.object_type}:{self.source_identity}"


class Neo4jProjectionIdentity(StrictBundleModel):
    organization_id: str = Field(pattern=IDENTITY_PATTERN)
    project_id: str = Field(pattern=IDENTITY_PATTERN)
    dataset_id: str = Field(pattern=IDENTITY_PATTERN)
    dataset_version_id: str = Field(pattern=IDENTITY_PATTERN)
    object_type: str = Field(pattern=IDENTITY_PATTERN)
    source_identity: str = Field(pattern=SOURCE_IDENTITY_PATTERN)

    def canonical_key(self) -> str:
        return (
            f"org:{self.organization_id}:project:{self.project_id}:dataset:{self.dataset_id}:"
            f"version:{self.dataset_version_id}:object:{self.object_type}:{self.source_identity}"
        )


class DatasetSourceReference(StrictBundleModel):
    dataset_id: str = Field(pattern=IDENTITY_PATTERN)
    dataset_version_id: str = Field(pattern=IDENTITY_PATTERN)
    role: str = Field(pattern=r"^[a-z][a-z0-9_]{1,127}$")
    checksum_sha256: str = Field(pattern=SHA256_PATTERN)
    object_type: str | None = Field(default=None, pattern=IDENTITY_PATTERN)
    source_identity: str | None = Field(default=None, pattern=SOURCE_IDENTITY_PATTERN)
    window_start: datetime | None = None
    window_end: datetime | None = None

    @model_validator(mode="after")
    def optional_parts_are_complete(self) -> "DatasetSourceReference":
        if (self.object_type is None) != (self.source_identity is None):
            raise ValueError("object_type and source_identity must be provided together")
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("window_start and window_end must be provided together")
        if self.window_start is not None and self.window_end is not None:
            if self.window_end <= self.window_start:
                raise ValueError("source reference window_end must be after window_start")
        return self

    def render(self) -> str:
        reference = (
            f"dataset:{self.dataset_id}:version:{self.dataset_version_id}:role:{self.role}:"
            f"sha256:{self.checksum_sha256.lower()}"
        )
        if self.object_type is not None and self.source_identity is not None:
            reference += f":object:{self.object_type}:{self.source_identity}"
        if self.window_start is not None and self.window_end is not None:
            reference += (
                f":window:{_canonical_datetime(self.window_start)}/"
                f"{_canonical_datetime(self.window_end)}"
            )
        return reference
