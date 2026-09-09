"""Small process/readiness endpoints for local, Docker and hosted runtime probes."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.common.runtime_settings import project_root
from app.infra.db.migrations import migration_status
from app.infra.db.settings import database_location
from app.infra.observability.runtime import (
    METRICS,
    metrics_authorized,
    observability_readiness,
)


router = APIRouter(tags=["system"])


@router.get("/health")
@router.get("/health/live")
def live() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ontology-dashboard",
        "build_sha": os.getenv("ONTOLOGY_DASHBOARD_BUILD_SHA", "unknown"),
    }


@router.get("/health/startup")
@router.get("/health/ready")
def ready():
    try:
        migration_status(database_location(project_root()))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "service": "ontology-dashboard", "dependency": "database"},
        )
    return {
        "status": "ready",
        "service": "ontology-dashboard",
        "build_sha": os.getenv("ONTOLOGY_DASHBOARD_BUILD_SHA", "unknown"),
    }


@router.get("/health/observability")
def observability_status():
    return observability_readiness().model_dump(mode="json")


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(request: Request):
    if not metrics_authorized(request):
        return PlainTextResponse("unauthorized\n", status_code=401)
    return PlainTextResponse(
        METRICS.render_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


__all__ = ["router"]
