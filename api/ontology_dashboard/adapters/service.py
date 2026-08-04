from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ontology_dashboard.datasets import (
    DatasetCatalogService,
    DatasetCreateRequest,
    DatasetFileCreate,
    DatasetRepository,
    DatasetVersionCreateRequest,
)
from ontology_dashboard.identity import AuthError, IdentityService, Principal

from .file_adapter import FileAdapter
from .bundle_file_adapter import BundleFileAdapter
from .bundle_models import (
    BundleValidationResult,
    DatasetBundleManifestV2,
    PostgreSQLBundleIngestionResult,
)
from .models import DatasetManifest, IngestionResult, PredictionResult
from .prediction_repository import PredictionResultRepository
from .postgresql_bundle_ingestion import PostgreSQLPredictiveMaintenanceBundleIngestor
from .registry import AdapterRegistry, default_adapter_registry
from .repository import AdapterRepository


class AdapterService:
    def __init__(
        self,
        database_path: str | Path,
        *,
        root: str | Path,
        registry: AdapterRegistry | None = None,
        repository: AdapterRepository | None = None,
        prediction_repository: PredictionResultRepository | None = None,
        dataset_catalog: DatasetCatalogService | None = None,
    ) -> None:
        self.database = str(database_path)
        self.path = (
            self.database
            if self.database.startswith(("postgresql://", "postgresql+psycopg://"))
            else Path(self.database)
        )
        self.root = Path(root)
        self.registry = registry or default_adapter_registry()
        configured = os.getenv("ONTOLOGY_DASHBOARD_DATA_ROOTS", "")
        roots = [Path(value) for value in configured.split(os.pathsep) if value.strip()]
        if not roots:
            roots = [self.root / "data" / "raw", self.root / "data" / "fixtures"]
        self.repository = repository or AdapterRepository(self.path)
        self.predictions = prediction_repository or PredictionResultRepository(self.path)
        self.dataset_catalog = dataset_catalog or DatasetCatalogService(
            DatasetRepository(self.database)
        )
        self.file_adapter = FileAdapter(
            self.database,
            allowed_roots=roots,
            registry=self.registry,
            repository=self.repository,
        )
        self.bundle_file_adapter = BundleFileAdapter(
            allowed_roots=roots,
            registry=self.registry,
        )

    @staticmethod
    def _require_permission(principal: Principal, permission: str) -> None:
        if permission not in principal.permissions:
            raise AuthError(403, "permission_denied", "이 작업을 수행할 권한이 없습니다.")

    @staticmethod
    def _require_active_project(principal: Principal, project_id: str) -> None:
        if project_id not in principal.project_scopes:
            raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 요청입니다.")
        if principal.active_project_id != project_id:
            raise AuthError(409, "active_project_mismatch", "먼저 해당 Project를 활성화해야 합니다.")

    @staticmethod
    def _require_workspace(principal: Principal, workspace_id: str) -> None:
        if workspace_id not in principal.workspace_scopes:
            raise AuthError(403, "workspace_scope_denied", "허용된 Workspace 범위를 벗어난 요청입니다.")

    def list_adapters(self, principal: Principal) -> list[dict[str, str]]:
        self._require_permission(principal, "datasets.read")
        return self.registry.list()

    def list_manifests(self, principal: Principal, project_id: str) -> list[dict[str, Any]]:
        self._require_permission(principal, "datasets.read")
        self._require_active_project(principal, project_id)
        return self.repository.list_manifests(
            organization_id=principal.organization_id,
            project_id=project_id,
        )

    def ingest(
        self,
        principal: Principal,
        project_id: str,
        manifest: DatasetManifest,
    ) -> IngestionResult:
        self._require_permission(principal, "datasets.ingest")
        self._require_active_project(principal, project_id)
        self._require_workspace(principal, manifest.workspace_id)
        if manifest.organization_id != principal.organization_id:
            raise AuthError(403, "tenant_scope_denied", "다른 조직의 Dataset은 수집할 수 없습니다.")
        if manifest.project_id != project_id:
            raise AuthError(422, "project_context_mismatch", "Manifest의 Project가 요청 경로와 일치하지 않습니다.")
        result = self.file_adapter.ingest(manifest)
        self._sync_dataset_catalog(principal, manifest, result)
        return result

    def validate_bundle(
        self,
        principal: Principal,
        project_id: str,
        manifest: DatasetBundleManifestV2,
    ) -> BundleValidationResult:
        """Validate a bundle before the Phase 2 PostgreSQL ingestion transaction."""

        self._require_permission(principal, "datasets.ingest")
        self._require_active_project(principal, project_id)
        self._require_workspace(principal, manifest.workspace_id)
        if manifest.organization_id != principal.organization_id:
            raise AuthError(403, "tenant_scope_denied", "다른 조직의 Dataset은 수집할 수 없습니다.")
        if manifest.project_id != project_id:
            raise AuthError(
                422,
                "project_context_mismatch",
                "Bundle Manifest의 Project가 요청 경로와 일치하지 않습니다.",
            )
        return self.bundle_file_adapter.validate(manifest)

    def ingest_bundle_postgresql(
        self,
        principal: Principal,
        project_id: str,
        manifest: DatasetBundleManifestV2,
        *,
        database_url: str,
        validation: BundleValidationResult | None = None,
    ) -> PostgreSQLBundleIngestionResult:
        """Validate and atomically COPY a bundle through the PostgreSQL production port."""

        checked = validation or self.validate_bundle(principal, project_id, manifest)
        if validation is not None:
            self._require_permission(principal, "datasets.ingest")
            self._require_active_project(principal, project_id)
            self._require_workspace(principal, manifest.workspace_id)
            if manifest.organization_id != principal.organization_id:
                raise AuthError(
                    403,
                    "tenant_scope_denied",
                    "다른 조직의 Dataset은 수집할 수 없습니다.",
                )
            if manifest.project_id != project_id:
                raise AuthError(
                    422,
                    "project_context_mismatch",
                    "Bundle Manifest의 Project가 요청 경로와 일치하지 않습니다.",
                )
        return PostgreSQLPredictiveMaintenanceBundleIngestor(
            database_url
        ).ingest_validated_bundle(
            manifest=manifest,
            validation=checked,
        )

    def _sync_dataset_catalog(
        self,
        principal: Principal,
        manifest: DatasetManifest,
        result: IngestionResult,
    ) -> None:
        """Promote a validated legacy manifest into the canonical Dataset Version model."""
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

    def save_prediction(
        self,
        principal: Principal,
        project_id: str,
        result: PredictionResult,
    ) -> dict[str, Any]:
        self._require_permission(principal, "predictions.ingest")
        self._require_active_project(principal, project_id)
        self._require_workspace(principal, result.workspace_id)
        if result.organization_id != principal.organization_id:
            raise AuthError(403, "tenant_scope_denied", "다른 조직의 Prediction Result는 수집할 수 없습니다.")
        if result.project_id != project_id:
            raise AuthError(422, "project_context_mismatch", "Prediction Result의 Project가 요청 경로와 일치하지 않습니다.")
        return self.predictions.save(result)

    def list_predictions(
        self,
        principal: Principal,
        project_id: str,
        *,
        workspace_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_permission(principal, "datasets.read")
        self._require_active_project(principal, project_id)
        if workspace_id is not None:
            self._require_workspace(principal, workspace_id)
        return self.predictions.list(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=max(1, min(limit, 500)),
        )


__all__ = [
    "AdapterService",
    "BundleValidationResult",
    "DatasetBundleManifestV2",
    "DatasetManifest",
    "IngestionResult",
    "PostgreSQLBundleIngestionResult",
    "PredictionResult",
]
