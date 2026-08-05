"""System and contract endpoints."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..deployment import process_probe, readiness_probe, startup_probe
from ..polyglot import PolyglotHealthService, PolyglotSettings

router = APIRouter(tags=["system"])
ROOT = Path(__file__).resolve().parents[3]


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ontology-dashboard",
        "mode": "liveness-compatibility",
        "domain_pack": "manufacturing-predictive-maintenance",
    }


@router.get("/health/live")
def health_live():
    return process_probe().model_dump(mode="json")


@router.get("/health/startup")
def health_startup():
    payload = startup_probe(ROOT)
    return JSONResponse(
        payload.model_dump(mode="json"),
        status_code=200 if payload.state == "ready" else 503,
    )


@router.get("/health/ready")
def health_ready():
    payload = readiness_probe(ROOT)
    return JSONResponse(
        payload.model_dump(mode="json"),
        status_code=200 if payload.state in {"ready", "degraded"} else 503,
    )


@router.get("/api/system/polyglot-health")
def polyglot_health() -> dict:
    return PolyglotHealthService(PolyglotSettings.from_environment()).snapshot()


@router.get("/api/openapi-contract")
def openapi_contract(request: Request) -> dict:
    return request.app.openapi()
