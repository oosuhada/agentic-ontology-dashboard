"""System and contract endpoints."""

from fastapi import APIRouter, Request

from ..polyglot import PolyglotHealthService, PolyglotSettings

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ontology-dashboard",
        "mode": "offline-capable",
        "domain_pack": "manufacturing-predictive-maintenance",
    }


@router.get("/api/system/polyglot-health")
def polyglot_health() -> dict:
    return PolyglotHealthService(PolyglotSettings.from_environment()).snapshot()


@router.get("/api/openapi-contract")
def openapi_contract(request: Request) -> dict:
    return request.app.openapi()
