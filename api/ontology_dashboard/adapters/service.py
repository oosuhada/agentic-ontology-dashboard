from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ontology_dashboard.identity import AuthError, IdentityService, Principal

from .file_adapter import FileAdapter
from .models import DatasetManifest, IngestionResult, PredictionResult
from .prediction_repository import PredictionResultRepository
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
    ) -> None:
        self.path = Path(database_path)
        self.root = Path(root)
        self.registry = registry or default_adapter_registry()
        configured = os.getenv("ONTOLOGY_DASHBOARD_DATA_ROOTS", "")
        roots = [Path(value) for value in configured.split(os.pathsep) if value.strip()]
        if not roots:
            roots = [self.root / "data" / "raw", self.root / "data" / "fixtures"]
        self.repository = repository or AdapterRepository(self.path)
        self.predictions = prediction_repository or PredictionResultRepository(self.path)
        self.file_adapter = FileAdapter(
            self.path,
            allowed_roots=roots,
            registry=self.registry,
            repository=self.repository,
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
        return self.file_adapter.ingest(manifest)

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


__all__ = ["AdapterService", "DatasetManifest", "IngestionResult", "PredictionResult"]
