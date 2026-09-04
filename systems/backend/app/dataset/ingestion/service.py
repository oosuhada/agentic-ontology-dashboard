"""Dataset-owned ingestion use cases separated from Prediction persistence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from app.dataset.dataset_domain import DatasetPrincipal
from app.dataset.dataset_exception import DatasetAccessError
from app.dataset.dataset_schema import (
    DatasetCreateRequest,
    DatasetFileCreate,
    DatasetVersionCreateRequest,
)
from app.dataset.dataset_service import DatasetCatalogService

from .bundle_file_adapter import BundleFileAdapter
from ..bundle_contract import BundleValidationResult, DatasetBundleManifestV2
from .file_adapter import FileAdapter
from .ingestion_schema import DatasetManifest, IngestionResult
from .registry import AdapterRegistry, default_adapter_registry
from .repository import IngestionRepositoryPort


class DatasetIngestionService:
    def __init__(
        self,
        *,
        repository: IngestionRepositoryPort,
        dataset_catalog: DatasetCatalogService,
        allowed_roots: Iterable[str | Path],
        registry: AdapterRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.dataset_catalog = dataset_catalog
        self.registry = registry or default_adapter_registry()
        self.file_adapter = FileAdapter(
            allowed_roots=allowed_roots,
            registry=self.registry,
            repository=repository,
        )
        self.bundle_file_adapter = BundleFileAdapter(
            allowed_roots=allowed_roots,
            registry=self.registry,
        )

    @staticmethod
    def _require_permission(principal: DatasetPrincipal, permission: str) -> None:
        if permission not in principal.permissions:
            raise DatasetAccessError(403, "permission_denied", "이 작업을 수행할 권한이 없습니다.")

    @staticmethod
    def _require_active_project(principal: DatasetPrincipal, project_id: str) -> None:
        if project_id not in principal.project_scopes:
            raise DatasetAccessError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 요청입니다.")
        if principal.active_project_id != project_id:
            raise DatasetAccessError(409, "active_project_mismatch", "먼저 해당 Project를 활성화해야 합니다.")

    @staticmethod
    def _require_workspace(principal: DatasetPrincipal, workspace_id: str) -> None:
        if workspace_id not in principal.workspace_scopes:
            raise DatasetAccessError(403, "workspace_scope_denied", "허용된 Workspace 범위를 벗어난 요청입니다.")

    def list_adapters(self, principal: DatasetPrincipal) -> list[dict[str, str]]:
        self._require_permission(principal, "datasets.read")
        return self.registry.list()

    def list_manifests(
        self, principal: DatasetPrincipal, project_id: str
    ) -> list[dict[str, Any]]:
        self._require_permission(principal, "datasets.read")
        self._require_active_project(principal, project_id)
        return self.repository.list_manifests(
            organization_id=principal.organization_id,
            project_id=project_id,
        )

    def ingest(
        self,
        principal: DatasetPrincipal,
        project_id: str,
        manifest: DatasetManifest,
    ) -> IngestionResult:
        self._require_permission(principal, "datasets.ingest")
        self._require_active_project(principal, project_id)
        self._require_workspace(principal, manifest.workspace_id)
        if manifest.organization_id != principal.organization_id:
            raise DatasetAccessError(403, "tenant_scope_denied", "다른 조직의 Dataset은 수집할 수 없습니다.")
        if manifest.project_id != project_id:
            raise DatasetAccessError(
                422,
                "project_context_mismatch",
                "Manifest의 Project가 요청 경로와 일치하지 않습니다.",
            )
        result = self.file_adapter.ingest(manifest)
        self._sync_dataset_catalog(principal, manifest, result)
        return result

    def validate_bundle(
        self,
        principal: DatasetPrincipal,
        project_id: str,
        manifest: DatasetBundleManifestV2,
    ) -> BundleValidationResult:
        self._require_permission(principal, "datasets.ingest")
        self._require_active_project(principal, project_id)
        self._require_workspace(principal, manifest.workspace_id)
        if manifest.organization_id != principal.organization_id:
            raise DatasetAccessError(403, "tenant_scope_denied", "다른 조직의 Dataset은 수집할 수 없습니다.")
        if manifest.project_id != project_id:
            raise DatasetAccessError(
                422,
                "project_context_mismatch",
                "Bundle Manifest의 Project가 요청 경로와 일치하지 않습니다.",
            )
        return self.bundle_file_adapter.validate(manifest)

    def _sync_dataset_catalog(
        self,
        principal: DatasetPrincipal,
        manifest: DatasetManifest,
        result: IngestionResult,
    ) -> None:
        datasets = self.dataset_catalog.list_datasets(
            principal=principal,
            project_id=manifest.project_id,
        )
        dataset = next((item for item in datasets if item.id == manifest.manifest_id), None)
        if dataset is None:
            raw_slug = f"{manifest.adapter_code}-{manifest.manifest_id}".lower()
            slug = re.sub(r"[^a-z0-9-]+", "-", raw_slug).strip("-")[:120].rstrip("-")
            if len(slug) < 3:
                slug = f"dataset-{manifest.manifest_id.lower()}"
            dataset = self.dataset_catalog.create_dataset(
                principal=principal,
                request=DatasetCreateRequest(
                    id=manifest.manifest_id,
                    project_id=manifest.project_id,
                    workspace_id=manifest.workspace_id,
                    slug=slug,
                    display_name=manifest.dataset_name,
                    description=f"Validated {manifest.adapter_code} adapter dataset",
                    source_type=manifest.adapter_code,
                ),
            )
        detail = self.dataset_catalog.detail(
            principal=principal,
            project_id=manifest.project_id,
            dataset_id=dataset.id,
        )
        if any(item.source_version == manifest.dataset_version for item in detail.versions):
            return
        self.dataset_catalog.create_version(
            principal=principal,
            project_id=manifest.project_id,
            dataset_id=dataset.id,
            request=DatasetVersionCreateRequest(
                source_version=manifest.dataset_version,
                version_label=manifest.dataset_version,
                manifest_id=manifest.manifest_id,
                checksum_sha256=manifest.source.checksum_sha256,
                schema=manifest.schema_.model_dump(mode="json"),
                profile={
                    "ingestion_status": result.status,
                    "source_record_count": result.source_record_count,
                    "accepted_record_count": result.accepted_record_count,
                    "quarantined_record_count": result.quarantined_record_count,
                    "metrics": result.metrics,
                },
                record_count=result.accepted_record_count,
                files=[
                    DatasetFileCreate(
                        uri=manifest.source.uri,
                        media_type=manifest.source.media_type,
                        checksum_sha256=manifest.source.checksum_sha256,
                        size_bytes=manifest.source.size_bytes,
                    )
                ],
            ),
        )


__all__ = ["DatasetIngestionService"]
