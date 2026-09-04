"""Project HTTP adapter built from composition-owned dependency callbacks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from app.identity import PrincipalContext

from .project_domain import ProjectEventQueryPort, ProjectId
from .project_exception import ProjectError
from .project_schema import ProjectCreateRequest, ProjectUpdateRequest
from .project_service import ProjectService


_PROJECT_HTTP_STATUS_BY_CODE = {
    "permission_denied": 403,
    "project_scope_denied": 403,
    "project_not_found": 404,
    "user_not_found": 404,
    "active_project_mismatch": 409,
    "project_slug_conflict": 409,
    "self_lockout_blocked": 409,
    "invalid_default_workspace": 422,
    "invalid_role": 422,
    "role_required": 422,
}


def project_http_status(error: ProjectError) -> int:
    """Translate Project application error codes at the HTTP boundary."""

    return _PROJECT_HTTP_STATUS_BY_CODE.get(error.code, 400)


def build_project_router(
    *,
    get_project_service: Callable[..., ProjectService],
    get_event_query: Callable[..., ProjectEventQueryPort],
    require_permission: Callable[[str], Any],
    require_csrf: Callable[..., None],
) -> APIRouter:
    """Build the Project router without importing legacy composition or peer implementations."""

    router = APIRouter(tags=["projects"])

    @router.get("/api/projects")
    def list_projects(
        principal: PrincipalContext = Depends(require_permission("app.access")),
        projects: ProjectService = Depends(get_project_service),
    ):
        return {
            "items": [
                item.model_dump(mode="json")
                for item in projects.list_for_principal(principal)
            ]
        }

    @router.get("/api/projects/{project_id}")
    def get_project(
        project_id: ProjectId,
        principal: PrincipalContext = Depends(require_permission("app.access")),
        projects: ProjectService = Depends(get_project_service),
    ):
        return projects.get_for_principal(principal, project_id).model_dump(mode="json")

    @router.get("/api/projects/{project_id}/workspaces")
    def list_project_workspaces(
        project_id: ProjectId,
        principal: PrincipalContext = Depends(require_permission("app.access")),
        projects: ProjectService = Depends(get_project_service),
    ):
        return {"items": projects.list_workspaces(principal, project_id)}

    @router.get("/api/projects/{project_id}/events")
    def list_project_events(
        project_id: ProjectId,
        principal: PrincipalContext = Depends(require_permission("events.read")),
        projects: ProjectService = Depends(get_project_service),
        events: ProjectEventQueryPort = Depends(get_event_query),
    ):
        projects.get_for_principal(principal, project_id)
        if principal.active_project_id != project_id:
            raise ProjectError(
                "active_project_mismatch",
                "먼저 해당 Project를 활성화해야 합니다.",
            )
        return {"items": events.list_events(project_id)}

    @router.post("/api/admin/projects", status_code=201)
    def create_project(
        request: ProjectCreateRequest,
        principal: PrincipalContext = Depends(require_permission("admin.access")),
        _: None = Depends(require_csrf),
        projects: ProjectService = Depends(get_project_service),
    ):
        return projects.create(principal, request).model_dump(mode="json")

    @router.patch("/api/admin/projects/{project_id}")
    def update_project(
        project_id: ProjectId,
        request: ProjectUpdateRequest,
        principal: PrincipalContext = Depends(require_permission("admin.access")),
        _: None = Depends(require_csrf),
        projects: ProjectService = Depends(get_project_service),
    ):
        return projects.update(principal, project_id, request).model_dump(mode="json")

    return router


__all__ = ["build_project_router", "project_http_status"]
