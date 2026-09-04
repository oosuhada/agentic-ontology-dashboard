"""Persistence port for Dataset ingestion manifests and quarantine state."""

from __future__ import annotations

from typing import Any, Protocol

from .ingestion_schema import DatasetManifest, QuarantinedRecord


class IngestionRepositoryPort(Protocol):
    def save_manifest(self, manifest: DatasetManifest) -> None: ...

    def start_run(self, manifest: DatasetManifest) -> str: ...

    def complete_run(
        self,
        *,
        run_id: str,
        manifest: DatasetManifest,
        source_count: int,
        accepted_count: int,
        quarantined: list[QuarantinedRecord],
        error_message: str | None = None,
    ) -> None: ...

    def list_manifests(
        self, *, organization_id: str, project_id: str
    ) -> list[dict[str, Any]]: ...


__all__ = ["IngestionRepositoryPort"]
