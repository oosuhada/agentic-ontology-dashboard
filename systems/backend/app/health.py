"""Small process/readiness endpoints for local, Docker and hosted runtime probes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.common.runtime_settings import project_root
from app.infra.db.migrations import migration_status
from app.infra.db.settings import database_location


router = APIRouter(tags=["system"])


@router.get("/health")
@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok", "service": "ontology-dashboard"}


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
    return {"status": "ready", "service": "ontology-dashboard"}


__all__ = ["router"]
