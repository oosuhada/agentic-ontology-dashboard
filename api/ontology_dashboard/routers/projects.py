from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import (
    get_project_service,
    get_service,
    require_csrf,
    require_permission,
)
from ..identity import AuthError, Principal
from ..projects import ProjectCreateRequest, ProjectService, ProjectUpdateRequest
from ..service import ManufacturingPredictiveMaintenanceService

router = APIRouter(tags=["projects"])


@router.get("/api/projects")
def list_projects(
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
):
    return {"items": [item.model_dump(mode="json") for item in projects.list_for_principal(principal)]}


@router.get("/api/projects/{project_id}")
def get_project(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
):
    return projects.get_for_principal(principal, project_id).model_dump(mode="json")


@router.get("/api/projects/{project_id}/workspaces")
def list_project_workspaces(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
):
    return {"items": projects.list_workspaces(principal, project_id)}


@router.get("/api/projects/{project_id}/events")
def list_project_events(
    project_id: str,
    principal: Principal = Depends(require_permission("events.read")),
    projects: ProjectService = Depends(get_project_service),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    projects.get_for_principal(principal, project_id)
    if principal.active_project_id != project_id:
        raise AuthError(409, "active_project_mismatch", "먼저 해당 Project를 활성화해야 합니다.")
    items = service.list_events() if project_id == "manufacturing-demo-project" else []
    return {"items": items}


@router.post("/api/admin/projects", status_code=201)
def create_project(
    request: ProjectCreateRequest,
    principal: Principal = Depends(require_permission("admin.access")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
):
    return projects.create(principal, request).model_dump(mode="json")


@router.patch("/api/admin/projects/{project_id}")
def update_project(
    project_id: str,
    request: ProjectUpdateRequest,
    principal: Principal = Depends(require_permission("admin.access")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
):
    return projects.update(principal, project_id, request).model_dump(mode="json")
