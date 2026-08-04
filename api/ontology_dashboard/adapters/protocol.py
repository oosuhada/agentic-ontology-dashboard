from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .bundle_models import (
    BundleRoleValidationSummary,
    BundleValidationIssue,
    BundleValidationResult,
    DatasetBundleFile,
    DatasetBundleManifestV2,
)
from .models import DatasetManifest, QuarantinedRecord


@runtime_checkable
class DatasetAdapter(Protocol):
    code: str
    display_name: str

    def required_fields(self, manifest: DatasetManifest) -> set[str]: ...

    def normalize_record(
        self,
        record: dict[str, str],
        *,
        manifest: DatasetManifest,
        row_number: int,
    ) -> dict[str, Any] | QuarantinedRecord: ...

    def derive_metrics(
        self,
        records: list[dict[str, Any]],
        *,
        manifest: DatasetManifest,
    ) -> dict[str, Any]: ...


class SourceFilePolicy(Protocol):
    def validate(self, path: Path) -> Path: ...


@dataclass(frozen=True)
class ResolvedBundleFile:
    descriptor: DatasetBundleFile
    path: Path
    actual_checksum_sha256: str


@dataclass(frozen=True)
class BundleContentValidation:
    roles: tuple[BundleRoleValidationSummary, ...]
    issues: tuple[BundleValidationIssue, ...]
    issue_sample_truncated: bool = False


@runtime_checkable
class BundleDatasetAdapter(Protocol):
    code: str
    display_name: str
    required_roles: frozenset[str]
    allowed_roles: frozenset[str]

    def validate_files(
        self,
        manifest: DatasetBundleManifestV2,
        files: dict[str, ResolvedBundleFile],
        *,
        issue_sample_limit: int,
    ) -> BundleContentValidation: ...


@runtime_checkable
class ValidatedBundleIngestionPort(Protocol):
    """Phase 2 boundary for transactionally ingesting a validated bundle."""

    def ingest_validated_bundle(
        self,
        *,
        manifest: DatasetBundleManifestV2,
        validation: BundleValidationResult,
    ) -> dict[str, Any]: ...
