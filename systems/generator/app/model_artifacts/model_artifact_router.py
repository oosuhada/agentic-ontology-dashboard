"""Read-only Model Artifact operational API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from .model_artifact_service import ModelArtifactCatalogService


router = APIRouter(prefix="/models", tags=["model-artifacts"])
_service: ModelArtifactCatalogService | None = None


def get_model_artifact_service() -> ModelArtifactCatalogService:
    global _service
    if _service is None:
        _service = ModelArtifactCatalogService()
    return _service


def set_model_artifact_service(service: ModelArtifactCatalogService | None) -> None:
    global _service
    _service = service


@router.get("")
def list_models(service: ModelArtifactCatalogService = Depends(get_model_artifact_service)):
    return {"items": service.list_models()}


@router.get("/{model_id}/versions")
def list_model_versions(
    model_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: ModelArtifactCatalogService = Depends(get_model_artifact_service),
):
    items = service.list_versions(model_id)
    return {"items": items[offset : offset + limit], "total": len(items), "offset": offset, "limit": limit}


@router.get("/{model_id}/latest")
def get_latest_model(
    model_id: str,
    service: ModelArtifactCatalogService = Depends(get_model_artifact_service),
):
    try:
        return service.latest(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{model_id}/versions/{model_version}")
def get_model_version(
    model_id: str,
    model_version: str,
    service: ModelArtifactCatalogService = Depends(get_model_artifact_service),
):
    try:
        return service.inspect(model_id, model_version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


__all__ = ["router", "set_model_artifact_service"]
