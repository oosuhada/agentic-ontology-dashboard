"""Project-scoped Dataset and Prediction Result ingestion routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dataset.ingestion.ingestion_schema import DatasetManifest
from app.diagnosis.diagnosis_schema import PredictionResult
from .api_service import AdapterService
from app.dependencies import current_principal, get_adapter_service, require_csrf
from app.identity import Principal

router = APIRouter(tags=["datasets", "predictions"])


@router.get("/api/adapters")
def list_adapters(
    principal: Principal = Depends(current_principal),
    adapters: AdapterService = Depends(get_adapter_service),
):
    return {"items": adapters.list_adapters(principal)}


@router.get("/api/projects/{project_id}/datasets")
def list_project_datasets(
    project_id: str,
    principal: Principal = Depends(current_principal),
    adapters: AdapterService = Depends(get_adapter_service),
):
    return {"items": adapters.list_manifests(principal, project_id)}


@router.post("/api/projects/{project_id}/datasets/ingest", status_code=201)
def ingest_project_dataset(
    project_id: str,
    manifest: DatasetManifest,
    principal: Principal = Depends(current_principal),
    _: None = Depends(require_csrf),
    adapters: AdapterService = Depends(get_adapter_service),
):
    return adapters.ingest(principal, project_id, manifest).model_dump(mode="json")


@router.get("/api/projects/{project_id}/predictions")
def list_project_predictions(
    project_id: str,
    workspace_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(current_principal),
    adapters: AdapterService = Depends(get_adapter_service),
):
    return {
        "items": adapters.list_predictions(
            principal,
            project_id,
            workspace_id=workspace_id,
            limit=limit,
        )
    }


@router.post("/api/projects/{project_id}/predictions", status_code=201)
def ingest_prediction_result(
    project_id: str,
    result: PredictionResult,
    principal: Principal = Depends(current_principal),
    _: None = Depends(require_csrf),
    adapters: AdapterService = Depends(get_adapter_service),
):
    return adapters.save_prediction(principal, project_id, result)
