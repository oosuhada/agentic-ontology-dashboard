"""System and contract endpoints."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ontology-dashboard",
        "mode": "offline-capable",
        "domain_pack": "manufacturing-predictive-maintenance",
    }


@router.get("/api/openapi-contract")
def openapi_contract(request: Request) -> dict:
    return request.app.openapi()
