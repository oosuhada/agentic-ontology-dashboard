"""Single Backend ASGI composition root."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.application import create_app
from app.dashboard import DashboardAccessError, DashboardNotFoundError, build_dashboard_router
from app.dataset import DatasetAccessError
from app.dependencies import (
    client_ip,
    current_principal,
    get_adapter_service,
    get_dashboard_service,
    get_dataset_catalog_service,
    get_export_service,
    get_governance_service,
    get_identity_service,
    get_maintenance_loop_service,
    get_ontology_planner_service,
    get_ontology_service,
    get_predictive_maintenance_runtime_service,
    get_project_service,
    get_rate_limiter,
    get_role_workflow_service,
    get_service,
    rate_limit_subject,
    require_csrf,
    require_permission,
    set_auth_cookies,
)
from app.governance import GovernanceAccessError, build_governance_router
from app.health import router as health_router
from app.identity import AuthError
from app.identity.identity_router import build_identity_router, identity_http_status
from app.maintenance.maintenance_router import create_maintenance_router
from app.ontology.ontology_router import create_ontology_router
from app.ontology.ontology_service import OntologyAccessError, OntologyNotFound
from app.planner import build_planner_router
from app.project import ProjectError
from app.project.project_router import build_project_router
from app.report import ReportConflictError, build_report_router
from app.dataset.ingestion.router import router as adapters_router
from app.dataset.dataset_router import router as datasets_router
from app.operations.router import router as manufacturing_router
from app.diagnosis.runtime_router import (
    internal_router as prediction_result_inbox_router,
    router as predictive_maintenance_runtime_router,
)
from app.operations.service import EventNotFound


app = create_app()


@app.exception_handler(AuthError)
async def auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=identity_http_status(exc),
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(ProjectError)
async def project_error_handler(_: Request, exc: ProjectError) -> JSONResponse:
    status_code = 404 if exc.code == "project_not_found" else 403 if "denied" in exc.code else 400
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(DatasetAccessError)
async def dataset_access_error_handler(_: Request, exc: DatasetAccessError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(OntologyAccessError)
async def ontology_access_error_handler(_: Request, exc: OntologyAccessError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.detail}},
    )


@app.exception_handler(OntologyNotFound)
async def ontology_not_found_handler(_: Request, exc: OntologyNotFound) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "not_found", "message": str(exc.args[0])}},
    )


@app.exception_handler(DashboardNotFoundError)
async def dashboard_not_found_handler(_: Request, exc: DashboardNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "not_found", "message": str(exc)}},
    )


@app.exception_handler(DashboardAccessError)
@app.exception_handler(GovernanceAccessError)
async def access_error_handler(_: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(ReportConflictError)
async def report_conflict_handler(_: Request, exc: ReportConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(EventNotFound)
async def event_not_found_handler(_: Request, exc: EventNotFound) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "not_found", "message": f"resource not found: {exc.args[0]}"}},
    )


identity_router = build_identity_router(
    get_identity_service=get_identity_service,
    get_rate_limiter=get_rate_limiter,
    current_principal=current_principal,
    require_csrf=require_csrf,
    client_ip=client_ip,
    rate_limit_subject=rate_limit_subject,
    set_auth_cookies=set_auth_cookies,
)
project_router = build_project_router(
    get_project_service=get_project_service,
    get_event_query=get_service,
    require_permission=require_permission,
    require_csrf=require_csrf,
)
ontology_router = create_ontology_router(
    get_identity_service=get_identity_service,
    get_ontology_service=get_ontology_service,
    require_csrf=require_csrf,
    require_permission=require_permission,
)
planner_router = build_planner_router(
    get_identity_service=get_identity_service,
    get_planner_service=get_ontology_planner_service,
    get_runtime_service=get_predictive_maintenance_runtime_service,
    get_rate_limiter=get_rate_limiter,
    rate_limit_subject=rate_limit_subject,
    require_csrf=require_csrf,
    require_permission=require_permission,
)
dashboard_router = build_dashboard_router(
    get_dashboard_service=get_dashboard_service,
    get_identity_service=get_identity_service,
    get_ontology_service=get_ontology_service,
    get_role_workflow_service=get_role_workflow_service,
    get_event_query_service=get_service,
    require_csrf=require_csrf,
    require_permission=require_permission,
)
report_router = build_report_router(
    get_report_service=get_export_service,
    get_identity_service=get_identity_service,
    get_rate_limiter=get_rate_limiter,
    rate_limit_subject=rate_limit_subject,
    require_csrf=require_csrf,
    require_permission=require_permission,
)
governance_router = build_governance_router(
    get_governance_service=get_governance_service,
    require_permission=require_permission,
    require_csrf=require_csrf,
)
maintenance_router = create_maintenance_router(
    require_permission=require_permission,
    get_identity_service=get_identity_service,
    get_maintenance_service=get_maintenance_loop_service,
    require_csrf=require_csrf,
)

for router in (
    health_router,
    identity_router,
    project_router,
    ontology_router,
    datasets_router,
    adapters_router,
    predictive_maintenance_runtime_router,
    prediction_result_inbox_router,
    manufacturing_router,
    dashboard_router,
    report_router,
    governance_router,
    planner_router,
    maintenance_router,
):
    app.include_router(router)


__all__ = ["app", "get_identity_service", "get_service"]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
