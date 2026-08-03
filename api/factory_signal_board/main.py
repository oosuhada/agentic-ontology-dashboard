"""Ontology Dashboard application composition root.

Feature handlers live in ``ontology_dashboard.routers``.  This module intentionally
keeps only application construction, shared exception mapping and router
registration so feature modules never import back from the composition root.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from ontology_dashboard.application import create_app
from ontology_dashboard.dependencies import (
    get_identity_service,
    get_ontology_planner_service,
    get_rate_limiter,
    get_service,
)
from ontology_dashboard.identity import AuthError
from ontology_dashboard.routers.adapters import router as adapters_router
from ontology_dashboard.routers.admin import router as admin_router
from ontology_dashboard.routers.analyses import router as analyses_router
from ontology_dashboard.routers.auth import router as auth_router
from ontology_dashboard.routers.dashboards import router as dashboards_router
from ontology_dashboard.routers.exports import router as exports_router
from ontology_dashboard.routers.manufacturing import router as manufacturing_router
from ontology_dashboard.routers.ontology import router as ontology_router
from ontology_dashboard.routers.planner import router as planner_router
from ontology_dashboard.routers.projects import router as projects_router
from ontology_dashboard.routers.role_workspaces import router as role_workspaces_router
from ontology_dashboard.routers.system import router as system_router
from ontology_dashboard.security import RateLimitExceeded
from ontology_dashboard.service import EventNotFound

app = create_app()


@app.exception_handler(EventNotFound)
async def not_found_handler(_: Request, exc: EventNotFound) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "not_found",
                "message": f"resource not found: {exc.args[0]}",
            }
        },
    )


@app.exception_handler(AuthError)
async def auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(ValueError)
async def validation_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "contract_validation_failed",
                "message": str(exc),
            }
        },
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(exc.retry_after)},
        content={
            "error": {
                "code": "rate_limit_exceeded",
                "message": "요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
                "bucket": exc.bucket,
                "retry_after": exc.retry_after,
            }
        },
    )


for feature_router in (
    system_router,
    auth_router,
    adapters_router,
    ontology_router,
    analyses_router,
    projects_router,
    dashboards_router,
    exports_router,
    planner_router,
    role_workspaces_router,
    manufacturing_router,
    admin_router,
):
    app.include_router(feature_router)


__all__ = [
    "app",
    "get_identity_service",
    "get_ontology_planner_service",
    "get_rate_limiter",
    "get_service",
]
