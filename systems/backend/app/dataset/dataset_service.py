"""Dataset Catalog application service and canonical identity construction."""

from __future__ import annotations

from urllib.parse import quote

from .dataset_domain import DatasetPrincipal
from .dataset_exception import DatasetAccessError
from .dataset_repository import DatasetRepositoryPort
from .dataset_schema import (
    AdapterIngestionRunRecord,
    CanonicalObjectEnvelope,
    DatasetCreateRequest,
    DatasetDetail,
    DatasetFileRecord,
    DatasetPage,
    DatasetRecord,
    DatasetVersionCreateRequest,
    DatasetVersionRecord,
    DocumentIndexReadiness,
    MaterializationCreateRequest,
    MaterializationRecord,
    OntologyMappingCreateRequest,
    OntologyMappingRecord,
    ProjectionBatch,
    ProjectionRecord,
    QuarantineRecord,
)


class DatasetCatalogService:
    def __init__(self, repository: DatasetRepositoryPort) -> None:
        self.repository = repository

    @staticmethod
    def _require_project(principal: DatasetPrincipal, project_id: str) -> None:
        if project_id not in principal.project_scopes:
            raise DatasetAccessError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 요청입니다.")
        if principal.active_project_id and principal.active_project_id != project_id:
            raise DatasetAccessError(409, "active_project_mismatch", "먼저 해당 Project를 활성화해야 합니다.")

    @staticmethod
    def _require_workspace(principal: DatasetPrincipal, workspace_id: str) -> None:
        if workspace_id not in principal.workspace_scopes:
            raise DatasetAccessError(403, "workspace_scope_denied", "허용된 workspace 범위를 벗어난 요청입니다.")

    def create_dataset(
        self,
        *,
        principal: DatasetPrincipal,
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

    def list_datasets(self, *, principal: DatasetPrincipal, project_id: str) -> list[DatasetRecord]:
        return self.list_dataset_page(
            principal=principal,
            project_id=project_id,
            offset=0,
            limit=10_000,
        ).items

    def list_dataset_page(
        self,
        *,
        principal: DatasetPrincipal,
        project_id: str,
        offset: int = 0,
        limit: int = 50,
        search: str | None = None,
        workspace_id: str | None = None,
        status: str | None = None,
        source_type: str | None = None,
    ) -> DatasetPage:
        self._require_project(principal, project_id)
        if workspace_id is not None:
            self._require_workspace(principal, workspace_id)
        payload = self.repository.list_dataset_page(
            organization_id=principal.organization_id,
            project_id=project_id,
            offset=offset,
            limit=limit,
            search=search,
            workspace_id=workspace_id,
            status=status,
            source_type=source_type,
        )
        return DatasetPage(
            items=[DatasetRecord.model_validate(item) for item in payload["items"]],
            offset=payload["offset"],
            limit=payload["limit"],
            total=payload["total"],
        )

    def detail(
        self,
        *,
        principal: DatasetPrincipal,
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
        versions = [
            DatasetVersionRecord.model_validate(item)
            for item in self.repository.list_versions(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset_id,
            )
        ]
        files = [
            DatasetFileRecord.model_validate(item)
            for item in self.repository.list_files(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset_id,
            )
        ]
        projections = [
            ProjectionRecord.model_validate(item)
            for item in self.repository.list_projections(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset_id,
            )
        ]
        mappings = [
            OntologyMappingRecord.model_validate(item)
            for item in self.repository.list_mappings(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset_id,
            )
        ]
        materializations = [
            MaterializationRecord.model_validate(item)
            for item in self.repository.list_materializations(
                organization_id=principal.organization_id,
                project_id=project_id,
                dataset_id=dataset_id,
            )
        ]
        manifest_ids = list(dict.fromkeys(item.manifest_id for item in versions if item.manifest_id))
        ingestion_runs = [
            AdapterIngestionRunRecord.model_validate(item)
            for item in self.repository.list_ingestion_runs(
                organization_id=principal.organization_id,
                project_id=project_id,
                manifest_ids=manifest_ids,
            )
        ]
        quarantine_records = [
            QuarantineRecord.model_validate(item)
            for item in self.repository.list_quarantine_records(
                organization_id=principal.organization_id,
                project_id=project_id,
                ingestion_run_ids=[item.id for item in ingestion_runs],
            )
        ]
        latest_version_id = dataset.latest_version_id
        vector_projection = next(
            (
                item
                for item in projections
                if item.store_kind == "vector" and item.dataset_version_id == latest_version_id
            ),
            None,
        )
        latest_mapping = next(
            (item for item in mappings if item.dataset_version_id == latest_version_id),
            None,
        )
        content_fields = latest_mapping.content_fields if latest_mapping is not None else []
        if vector_projection is None:
            document_readiness = DocumentIndexReadiness(status="missing")
        elif not content_fields:
            document_readiness = DocumentIndexReadiness(
                status="not_configured",
                projection_id=vector_projection.id,
                dataset_version_id=vector_projection.dataset_version_id,
                indexed_record_count=vector_projection.record_count,
                last_error=vector_projection.last_error,
            )
        else:
            document_readiness = DocumentIndexReadiness(
                status=vector_projection.status,
                projection_id=vector_projection.id,
                dataset_version_id=vector_projection.dataset_version_id,
                content_fields=content_fields,
                indexed_record_count=vector_projection.record_count,
                last_error=vector_projection.last_error,
            )
        lineage_references = list(
            dict.fromkeys(
                [item.source_reference for item in materializations]
                + [
                    str(item.metadata.get("downstream_dataset_version_id"))
                    for item in materializations
                    if item.metadata.get("downstream_dataset_version_id")
                ]
            )
        )
        return DatasetDetail(
            dataset=dataset,
            versions=versions,
            files=files,
            projections=projections,
            mappings=mappings,
            materializations=materializations,
            ingestion_runs=ingestion_runs,
            quarantine_records=quarantine_records,
            lineage_references=lineage_references,
            document_index_readiness=document_readiness,
        )

    def create_version(
        self,
        *,
        principal: DatasetPrincipal,
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
        principal: DatasetPrincipal,
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
        principal: DatasetPrincipal,
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
        principal: DatasetPrincipal,
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
