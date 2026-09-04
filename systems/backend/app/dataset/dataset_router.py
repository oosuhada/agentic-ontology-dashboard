"""Project-scoped Dataset Catalog, versions, mappings and materializations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dataset import (
    DatasetCatalogService,
    DatasetCreateRequest,
    DatasetVersionCreateRequest,
    MaterializationCreateRequest,
    OntologyMappingCreateRequest,
)
from app.dependencies import get_dataset_catalog_service, require_csrf, require_permission
from app.identity import Principal

router = APIRouter(prefix="/api", tags=["datasets"])


@router.get("/projects/{project_id}/dataset-catalog")
def list_datasets(
    project_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    search: str | None = Query(default=None, max_length=240),
    workspace_id: str | None = Query(default=None, max_length=160),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(draft|active|archived)$"),
    source_type: str | None = Query(default=None, max_length=80),
    principal: Principal = Depends(require_permission("datasets.read")),
    service: DatasetCatalogService = Depends(get_dataset_catalog_service),
):
    page = service.list_dataset_page(
        principal=principal,
        project_id=project_id,
        offset=offset,
        limit=limit,
        search=search,
        workspace_id=workspace_id,
        status=status_filter,
        source_type=source_type,
    )
    return page.model_dump(mode="json", by_alias=True)


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
