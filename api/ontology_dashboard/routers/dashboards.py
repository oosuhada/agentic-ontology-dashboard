"""Dashboard template, preference, board, saved-view and share routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from ..dashboard_models import (
    DashboardBoardQueryRequest,
    DashboardPreferenceRestoreRequest,
    DashboardPreferenceSaveRequest,
    DashboardShareCreateRequest,
    DashboardTemplatePublishRequest,
    SavedViewCreateRequest,
)
from ..dashboard_service import DashboardService
from ..dependencies import (
    get_dashboard_service,
    get_identity_service,
    get_ontology_service,
    get_role_workflow_service,
    require_csrf,
    require_permission,
)
from ..identity import AuthError, IdentityService, Principal
from ..ontology_adapter import risk_event_object_id
from ..ontology_service import OntologyService
from ..role_workflow_models import TemplatePublishRequestCreate
from ..role_workflow_service import RoleWorkflowService

router = APIRouter(tags=["dashboards"])


def require_template_role_context(principal: Principal, role_code: str) -> None:
    if role_code in principal.roles or "dashboards.templates.manage" in principal.permissions:
        return
    raise AuthError(
        403,
        "role_context_denied",
        "다른 역할의 Dashboard template을 조회할 수 없습니다.",
    )


@router.get("/api/dashboards/resolved")
def resolved_dashboard(
    workspace_id: str,
    principal: Principal = Depends(require_permission("dashboards.read")),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
):
    identity.require_workspace(principal, workspace_id)
    return dashboards.resolve(principal=principal, workspace_id=workspace_id).model_dump(mode="json")


# Static suffixes must be registered before the base dynamic role route.
@router.get("/api/dashboard-templates/{role_code}/versions")
def dashboard_template_versions(
    role_code: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("dashboards.read")),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
):
    identity.require_workspace(principal, workspace_id)
    require_template_role_context(principal, role_code)
    return {
        "items": dashboards.repository.list_template_versions(
            workspace_id=workspace_id,
            role_code=role_code,
        )
    }


@router.get("/api/dashboard-templates/{role_code}/preview")
def preview_dashboard_template(
    role_code: str,
    workspace_id: str,
    version: int | None = Query(default=None, ge=1),
    principal: Principal = Depends(require_permission("dashboards.read")),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
):
    identity.require_workspace(principal, workspace_id)
    require_template_role_context(principal, role_code)
    return dashboards.preview(
        workspace_id=workspace_id,
        role_code=role_code,
        version=version,
    ).model_dump(mode="json")


@router.post("/api/dashboard-templates/{role_code}/publish")
def publish_dashboard_template(
    role_code: str,
    request: DashboardTemplatePublishRequest,
    principal: Principal = Depends(require_permission("dashboards.templates.approve")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
):
    identity.require_workspace(principal, request.workspace_id)
    return dashboards.publish_template(
        principal=principal,
        target_role=role_code,
        request=request,
    ).model_dump(mode="json")


@router.post(
    "/api/dashboard-templates/{role_code}/publish-requests",
    status_code=201,
)
def request_dashboard_template_publish(
    role_code: str,
    request: TemplatePublishRequestCreate,
    principal: Principal = Depends(require_permission("dashboards.templates.request")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
):
    if request.target_role != role_code:
        raise ValueError("target_role must match the URL role_code")
    identity.require_workspace(principal, request.workspace_id)
    return workflows.create_template_publish_request(principal=principal, request=request)


@router.get("/api/dashboard-templates/{role_code}")
def current_dashboard_template(
    role_code: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("dashboards.read")),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
):
    identity.require_workspace(principal, workspace_id)
    require_template_role_context(principal, role_code)
    return dashboards.current_template(
        workspace_id=workspace_id,
        role_code=role_code,
    ).model_dump(mode="json")


@router.get("/api/boards/catalog")
def board_catalog(
    workspace_id: str,
    q: str | None = None,
    category: str | None = None,
    role_code: str | None = None,
    principal: Principal = Depends(require_permission("dashboards.read")),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
):
    identity.require_workspace(principal, workspace_id)
    return dashboards.catalog(
        principal=principal,
        query=q,
        category=category,
        role_code=role_code,
    ).model_dump(mode="json")


@router.post("/api/dashboards/{dashboard_id}/boards/{board_id}/query")
def query_dashboard_board(
    dashboard_id: str,
    board_id: str,
    request: DashboardBoardQueryRequest,
    principal: Principal = Depends(require_permission("dashboards.read")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    identity.require_workspace(principal, request.workspace_id)
    return dashboards.query_board(
        principal=principal,
        dashboard_id=dashboard_id,
        board_id=board_id,
        request=request,
        ontology=ontology,
    )


@router.put("/api/dashboards/preferences")
def save_dashboard_preferences(
    request: DashboardPreferenceSaveRequest,
    principal: Principal = Depends(require_permission("dashboards.personalize")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
):
    identity.require_workspace(principal, request.workspace_id)
    return dashboards.save_preferences(principal=principal, request=request).model_dump(mode="json")


@router.post("/api/dashboards/preferences/restore")
def restore_dashboard_preferences(
    request: DashboardPreferenceRestoreRequest,
    principal: Principal = Depends(require_permission("dashboards.personalize")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
):
    identity.require_workspace(principal, request.workspace_id)
    return dashboards.restore_defaults(
        principal=principal,
        workspace_id=request.workspace_id,
    ).model_dump(mode="json")


@router.get("/api/dashboards/saved-views")
def list_dashboard_saved_views(
    workspace_id: str,
    principal: Principal = Depends(require_permission("dashboards.personalize")),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
):
    identity.require_workspace(principal, workspace_id)
    return {
        "items": [
            item.model_dump(mode="json")
            for item in dashboards.list_saved_views(
                principal=principal,
                workspace_id=workspace_id,
            )
        ]
    }


@router.post("/api/dashboards/saved-views", status_code=201)
def create_dashboard_saved_view(
    request: SavedViewCreateRequest,
    principal: Principal = Depends(require_permission("dashboards.personalize")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
):
    identity.require_workspace(principal, request.workspace_id)
    return dashboards.create_saved_view(principal=principal, request=request).model_dump(mode="json")


@router.get("/api/dashboards/saved-views/{view_id}")
def get_dashboard_saved_view(
    view_id: str,
    principal: Principal = Depends(require_permission("dashboards.personalize")),
    dashboards: DashboardService = Depends(get_dashboard_service),
):
    return dashboards.get_saved_view(principal=principal, view_id=view_id).model_dump(mode="json")


@router.delete("/api/dashboards/saved-views/{view_id}", status_code=204)
def delete_dashboard_saved_view(
    view_id: str,
    principal: Principal = Depends(require_permission("dashboards.personalize")),
    _: None = Depends(require_csrf),
    dashboards: DashboardService = Depends(get_dashboard_service),
) -> Response:
    dashboards.delete_saved_view(principal=principal, view_id=view_id)
    return Response(status_code=204)


@router.post("/api/dashboards/shares", status_code=201)
def create_dashboard_share(
    request: DashboardShareCreateRequest,
    principal: Principal = Depends(require_permission("dashboards.share")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    identity.require_workspace(principal, request.workspace_id)
    return dashboards.create_share(
        principal=principal,
        request=request,
        validate_event=lambda event_id: ontology.get_object(
            workspace_id=request.workspace_id,
            object_id=risk_event_object_id(event_id),
        ),
    ).model_dump(mode="json")


@router.get("/api/dashboards/shares/{token}")
def resolve_dashboard_share(
    token: str,
    principal: Principal = Depends(require_permission("dashboards.read")),
    identity: IdentityService = Depends(get_identity_service),
    dashboards: DashboardService = Depends(get_dashboard_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    payload = dashboards.resolve_share(token=token)
    identity.require_workspace(principal, payload.workspace_id)
    event_id = payload.parameter_state.get("selected_event_id")
    if isinstance(event_id, str) and event_id:
        ontology.get_object(
            workspace_id=payload.workspace_id,
            object_id=risk_event_object_id(event_id),
        )
    return payload.model_dump(mode="json")
