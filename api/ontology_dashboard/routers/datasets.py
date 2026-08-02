"""Project-scoped Dataset Catalog, versions, mappings and materializations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..datasets import (
    DatasetCatalogService,
    DatasetCreateRequest,
    DatasetVersionCreateRequest,
    MaterializationCreateRequest,
    OntologyMappingCreateRequest,
)
from ..dependencies import get_dataset_catalog_service, require_csrf, require_permission
from ..identity import Principal

router = APIRouter(prefix="/api", tags=["datasets"])


@router.get("/projects/{project_id}/dataset-catalog")
def list_datasets(
    project_id: str,
    principal: Principal = Depends(require_permission("datasets.read")),
    service: DatasetCatalogService = Depends(get_dataset_catalog_service),
):
    return {
        "items": [
            item.model_dump(mode="json", by_alias=True)
            for item in service.list_datasets(principal=principal, project_id=project_id)
        ]
    }


@router.post("/projects/{project_id}/dataset-catalog", status_code=status.HTTP_201_CREATED)
def create_dataset(
    project_id: str,
    request: DatasetCreateRequest,
    principal: Principal = Depends(require_permission("datasets.ingest")),
    _: None = Depends(require_csrf),
    service: DatasetCatalogService = Depends(get_dataset_catalog_service),
):
    if request.project_id != project_id:
        raise HTTPException(status_code=422, detail="path and payload project_id must match")
    return service.create_dataset(principal=principal, request=request).model_dump(
        mode="json", by_alias=True
    )


@router.get("/projects/{project_id}/dataset-catalog/{dataset_id}")
def dataset_detail(
    project_id: str,
    dataset_id: str,
    principal: Principal = Depends(require_permission("datasets.read")),
    service: DatasetCatalogService = Depends(get_dataset_catalog_service),
):
    try:
        detail = service.detail(
            principal=principal,
            project_id=project_id,
            dataset_id=dataset_id,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"dataset not found: {error.args[0]}") from error
    return detail.model_dump(mode="json", by_alias=True)


@router.post(
    "/projects/{project_id}/dataset-catalog/{dataset_id}/versions",
    status_code=status.HTTP_201_CREATED,
)
def create_dataset_version(
    project_id: str,
    dataset_id: str,
    request: DatasetVersionCreateRequest,
    principal: Principal = Depends(require_permission("datasets.ingest")),
    _: None = Depends(require_csrf),
    service: DatasetCatalogService = Depends(get_dataset_catalog_service),
):
    try:
        version = service.create_version(
            principal=principal,
            project_id=project_id,
            dataset_id=dataset_id,
            request=request,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"dataset not found: {error.args[0]}") from error
    return version.model_dump(mode="json", by_alias=True)


@router.put(
    "/projects/{project_id}/dataset-catalog/{dataset_id}/versions/{version_id}/mapping"
)
def save_ontology_mapping(
    project_id: str,
    dataset_id: str,
    version_id: str,
    request: OntologyMappingCreateRequest,
    principal: Principal = Depends(require_permission("datasets.ingest")),
    _: None = Depends(require_csrf),
    service: DatasetCatalogService = Depends(get_dataset_catalog_service),
):
    try:
        mapping = service.save_mapping(
            principal=principal,
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=version_id,
            request=request,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"dataset version not found: {error.args[0]}") from error
    return mapping.model_dump(mode="json", by_alias=True)


@router.post(
    "/projects/{project_id}/dataset-catalog/{dataset_id}/versions/{version_id}/materializations",
    status_code=status.HTTP_201_CREATED,
)
def create_materialization(
    project_id: str,
    dataset_id: str,
    version_id: str,
    request: MaterializationCreateRequest,
    principal: Principal = Depends(require_permission("datasets.ingest")),
    _: None = Depends(require_csrf),
    service: DatasetCatalogService = Depends(get_dataset_catalog_service),
):
    try:
        materialization = service.create_materialization(
            principal=principal,
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=version_id,
            request=request,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"dataset version not found: {error.args[0]}") from error
    return materialization.model_dump(mode="json", by_alias=True)
