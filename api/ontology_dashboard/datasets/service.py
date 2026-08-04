"""Dataset Catalog application service and canonical identity construction."""

from __future__ import annotations

from urllib.parse import quote

from ..identity import AuthError, Principal
from .models import (
    CanonicalObjectEnvelope,
    DatasetCreateRequest,
    DatasetDetail,
    DatasetRecord,
    DatasetVersionCreateRequest,
    DatasetVersionRecord,
    MaterializationCreateRequest,
    MaterializationRecord,
    OntologyMappingCreateRequest,
    OntologyMappingRecord,
    ProjectionBatch,
    ProjectionRecord,
)
from .repository import DatasetRepository


class DatasetCatalogService:
    def __init__(self, repository: DatasetRepository) -> None:
        self.repository = repository

    @staticmethod
    def _require_project(principal: Principal, project_id: str) -> None:
        if project_id not in principal.project_scopes:
            raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 요청입니다.")
        if principal.active_project_id and principal.active_project_id != project_id:
            raise AuthError(409, "active_project_mismatch", "먼저 해당 Project를 활성화해야 합니다.")

    @staticmethod
    def _require_workspace(principal: Principal, workspace_id: str) -> None:
        if workspace_id not in principal.workspace_scopes:
            raise AuthError(403, "workspace_scope_denied", "허용된 workspace 범위를 벗어난 요청입니다.")

    def create_dataset(
        self,
        *,
        principal: Principal,
        request: DatasetCreateRequest,
    ) -> DatasetRecord:
        self._require_project(principal, request.project_id)
        self._require_workspace(principal, request.workspace_id)
        return DatasetRecord.model_validate(
            self.repository.create_dataset(
                organization_id=principal.organization_id,
                actor_user_id=principal.user_id,
                request=request,
            )
        )

    def list_datasets(self, *, principal: Principal, project_id: str) -> list[DatasetRecord]:
        self._require_project(principal, project_id)
        return [
            DatasetRecord.model_validate(item)
            for item in self.repository.list_datasets(
                organization_id=principal.organization_id,
                project_id=project_id,
            )
        ]

    def detail(
        self,
        *,
        principal: Principal,
        project_id: str,
        dataset_id: str,
    ) -> DatasetDetail:
        self._require_project(principal, project_id)
        dataset = DatasetRecord.model_validate(
            self.repository.get_dataset(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset_id,
            )
        )
        return DatasetDetail(
            dataset=dataset,
            versions=[
                DatasetVersionRecord.model_validate(item)
                for item in self.repository.list_versions(
                    organization_id=principal.organization_id,
                    project_id=project_id,
                    dataset_id=dataset_id,
                )
            ],
            projections=[
                ProjectionRecord.model_validate(item)
                for item in self.repository.list_projections(
                    organization_id=principal.organization_id,
                    project_id=project_id,
                    dataset_id=dataset_id,
                )
            ],
            mappings=[
                OntologyMappingRecord.model_validate(item)
                for item in self.repository.list_mappings(
                    organization_id=principal.organization_id,
                    project_id=project_id,
                    dataset_id=dataset_id,
                )
            ],
            materializations=[
                MaterializationRecord.model_validate(item)
                for item in self.repository.list_materializations(
                    organization_id=principal.organization_id,
                    project_id=project_id,
                    dataset_id=dataset_id,
                )
            ],
        )

    def create_version(
        self,
        *,
        principal: Principal,
        project_id: str,
        dataset_id: str,
        request: DatasetVersionCreateRequest,
    ) -> DatasetVersionRecord:
        self._require_project(principal, project_id)
        return DatasetVersionRecord.model_validate(
            self.repository.create_version(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset_id,
                actor_user_id=principal.user_id,
                request=request,
            )
        )

    def save_mapping(
        self,
        *,
        principal: Principal,
        project_id: str,
        dataset_id: str,
        version_id: str,
        request: OntologyMappingCreateRequest,
    ) -> OntologyMappingRecord:
        self._require_project(principal, project_id)
        return OntologyMappingRecord.model_validate(
            self.repository.save_mapping(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset_id,
                version_id=version_id,
                actor_user_id=principal.user_id,
                request=request,
            )
        )

    def create_materialization(
        self,
        *,
        principal: Principal,
        project_id: str,
        dataset_id: str,
        version_id: str,
        request: MaterializationCreateRequest,
    ) -> MaterializationRecord:
        self._require_project(principal, project_id)
        return MaterializationRecord.model_validate(
            self.repository.create_materialization(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset_id,
                version_id=version_id,
                actor_user_id=principal.user_id,
                request=request,
            )
        )

    def build_projection_batch(
        self,
        *,
        principal: Principal,
        project_id: str,
        dataset_id: str,
        version_id: str,
        records: list[dict[str, object]],
        object_type: str | None = None,
    ) -> ProjectionBatch:
        self._require_project(principal, project_id)
        dataset = DatasetRecord.model_validate(
            self.repository.get_dataset(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset_id,
            )
        )
        version = DatasetVersionRecord.model_validate(
            self.repository.get_version(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset_id,
                version_id=version_id,
            )
        )
        mapping = OntologyMappingRecord.model_validate(
            self.repository.get_mapping(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset_id,
                version_id=version_id,
                object_type=object_type,
            )
        )
        objects = [
            self._envelope(dataset=dataset, version=version, mapping=mapping, record=record)
            for record in records
        ]
        return ProjectionBatch(dataset=dataset, version=version, mapping=mapping, objects=objects)

    @staticmethod
    def _envelope(
        *,
        dataset: DatasetRecord,
        version: DatasetVersionRecord,
        mapping: OntologyMappingRecord,
        record: dict[str, object],
    ) -> CanonicalObjectEnvelope:
        source_identity = record.get(mapping.identity_field)
        if source_identity is None or not str(source_identity).strip():
            raise ValueError(f"record is missing identity field: {mapping.identity_field}")
        identity = str(source_identity).strip()
        object_id = ":".join(
            (
                dataset.project_id,
                dataset.id,
                version.id,
                mapping.object_type,
                quote(identity, safe=""),
            )
        )
        properties: dict[str, object] = {}
        for source_field, target_property in mapping.property_mapping.items():
            if source_field in record:
                properties[target_property] = record[source_field]
        content_parts = [
            str(record[field])
            for field in mapping.content_fields
            if field in record and record[field] is not None
        ]
        content = "\n".join(content_parts) or " ".join(
            f"{key}: {value}" for key, value in properties.items() if value is not None
        )
        return CanonicalObjectEnvelope(
            organization_id=dataset.organization_id,
            project_id=dataset.project_id,
            workspace_id=dataset.workspace_id,
            dataset_id=dataset.id,
            dataset_version_id=version.id,
            source_version=version.source_version,
            object_type=mapping.object_type,
            object_id=object_id,
            source_identity=identity,
            properties=properties,
            content=content,
            allowed_roles=mapping.allowed_roles,
            source_record=record,
        )
