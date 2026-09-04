"""Dashboard HTTP adapter built from composition-injected dependencies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response

from .dashboard_exception import DashboardAccessError
from .dashboard_schema import (
    DashboardBoardQueryRequest,
    DashboardPreferenceRestoreRequest,
    DashboardPreferenceSaveRequest,
    DashboardShareCreateRequest,
    DashboardTemplatePublishRequest,
    DashboardTemplatePublishRequestCreate,
    SavedViewCreateRequest,
)
from .dashboard_service import DashboardService

Role = Literal["manager", "engineer"]
AppLocale = Literal["ko-KR", "en-US"]


def _risk_event_object_id(event_id: str) -> str:
    return f"risk_event:{event_id}"


def build_dashboard_router(
    *,
    get_dashboard_service: Callable[..., DashboardService],
    get_identity_service: Callable[..., Any],
    get_ontology_service: Callable[..., Any],
    get_role_workflow_service: Callable[..., Any],
    get_event_query_service: Callable[..., Any],
    require_csrf: Callable[..., None],
    require_permission: Callable[[str], Any],
) -> APIRouter:
    router = APIRouter(tags=["dashboards"])

    def require_template_role_context(principal: Any, role_code: str) -> None:
        if role_code in principal.roles or "dashboards.templates.manage" in principal.permissions:
            return
        raise DashboardAccessError(
            403,
            "role_context_denied",
            "다른 역할의 Dashboard template을 조회할 수 없습니다.",
        )

    @router.get("/api/dashboards/resolved")
    def resolved_dashboard(
        workspace_id: str,
        principal: Any = Depends(require_permission("dashboards.read")),
        identity: Any = Depends(get_identity_service),
        dashboards: DashboardService = Depends(get_dashboard_service),
    ):
        identity.require_workspace(principal, workspace_id)
        return dashboards.resolve(principal=principal, workspace_id=workspace_id).model_dump(mode="json")

    @router.get("/api/dashboard-templates/{role_code}/versions")
    def dashboard_template_versions(
        role_code: str,
        workspace_id: str,
        principal: Any = Depends(require_permission("dashboards.read")),
        identity: Any = Depends(get_identity_service),
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
        principal: Any = Depends(require_permission("dashboards.read")),
        identity: Any = Depends(get_identity_service),
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
        principal: Any = Depends(require_permission("dashboards.templates.approve")),
        _: None = Depends(require_csrf),
        identity: Any = Depends(get_identity_service),
        dashboards: DashboardService = Depends(get_dashboard_service),
    ):
        identity.require_workspace(principal, request.workspace_id)
        return dashboards.publish_template(
            principal=principal,
            target_role=role_code,
            request=request,
        ).model_dump(mode="json")

    @router.post("/api/dashboard-templates/{role_code}/publish-requests", status_code=201)
    def request_dashboard_template_publish(
        role_code: str,
        request: DashboardTemplatePublishRequestCreate,
        principal: Any = Depends(require_permission("dashboards.templates.request")),
        _: None = Depends(require_csrf),
        identity: Any = Depends(get_identity_service),
        workflows: Any = Depends(get_role_workflow_service),
    ):
        if request.target_role != role_code:
            raise ValueError("target_role must match the URL role_code")
        identity.require_workspace(principal, request.workspace_id)
        return workflows.create_template_publish_request(principal=principal, request=request)

    @router.get("/api/dashboard-templates/{role_code}")
    def current_dashboard_template(
        role_code: str,
        workspace_id: str,
        principal: Any = Depends(require_permission("dashboards.read")),
        identity: Any = Depends(get_identity_service),
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
        principal: Any = Depends(require_permission("dashboards.read")),
        identity: Any = Depends(get_identity_service),
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
        principal: Any = Depends(require_permission("dashboards.read")),
        _: None = Depends(require_csrf),
        identity: Any = Depends(get_identity_service),
        dashboards: DashboardService = Depends(get_dashboard_service),
        ontology: Any = Depends(get_ontology_service),
        event_query: Any = Depends(get_event_query_service),
    ):
        identity.require_workspace(principal, request.workspace_id)
        return dashboards.query_board(
            principal=principal,
            dashboard_id=dashboard_id,
            board_id=board_id,
            request=request,
            ontology=ontology,
            event_rows=event_query.list_events(
                principal.active_project_id or "manufacturing-demo-project"
            ),
        )

    @router.put("/api/dashboards/preferences")
    def save_dashboard_preferences(
        request: DashboardPreferenceSaveRequest,
        principal: Any = Depends(require_permission("dashboards.personalize")),
        _: None = Depends(require_csrf),
        identity: Any = Depends(get_identity_service),
        dashboards: DashboardService = Depends(get_dashboard_service),
    ):
        identity.require_workspace(principal, request.workspace_id)
        return dashboards.save_preferences(principal=principal, request=request).model_dump(mode="json")

    @router.post("/api/dashboards/preferences/restore")
    def restore_dashboard_preferences(
        request: DashboardPreferenceRestoreRequest,
        principal: Any = Depends(require_permission("dashboards.personalize")),
        _: None = Depends(require_csrf),
        identity: Any = Depends(get_identity_service),
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
        principal: Any = Depends(require_permission("dashboards.personalize")),
        identity: Any = Depends(get_identity_service),
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
        principal: Any = Depends(require_permission("dashboards.personalize")),
        _: None = Depends(require_csrf),
        identity: Any = Depends(get_identity_service),
        dashboards: DashboardService = Depends(get_dashboard_service),
    ):
        identity.require_workspace(principal, request.workspace_id)
        return dashboards.create_saved_view(principal=principal, request=request).model_dump(mode="json")

    @router.get("/api/dashboards/saved-views/{view_id}")
    def get_dashboard_saved_view(
        view_id: str,
        principal: Any = Depends(require_permission("dashboards.personalize")),
        dashboards: DashboardService = Depends(get_dashboard_service),
    ):
        return dashboards.get_saved_view(principal=principal, view_id=view_id).model_dump(mode="json")

    @router.delete("/api/dashboards/saved-views/{view_id}", status_code=204)
    def delete_dashboard_saved_view(
        view_id: str,
        principal: Any = Depends(require_permission("dashboards.personalize")),
        _: None = Depends(require_csrf),
        dashboards: DashboardService = Depends(get_dashboard_service),
    ) -> Response:
        dashboards.delete_saved_view(principal=principal, view_id=view_id)
        return Response(status_code=204)

    @router.post("/api/dashboards/shares", status_code=201)
    def create_dashboard_share(
        request: DashboardShareCreateRequest,
        principal: Any = Depends(require_permission("dashboards.share")),
        _: None = Depends(require_csrf),
        identity: Any = Depends(get_identity_service),
        dashboards: DashboardService = Depends(get_dashboard_service),
        ontology: Any = Depends(get_ontology_service),
    ):
        identity.require_workspace(principal, request.workspace_id)
        return dashboards.create_share(
            principal=principal,
            request=request,
            validate_event=lambda event_id: ontology.get_object(
                workspace_id=request.workspace_id,
                object_id=_risk_event_object_id(event_id),
            ),
        ).model_dump(mode="json")

    @router.get("/api/dashboards/shares/{token}")
    def resolve_dashboard_share(
        token: str,
        principal: Any = Depends(require_permission("dashboards.read")),
        identity: Any = Depends(get_identity_service),
        dashboards: DashboardService = Depends(get_dashboard_service),
        ontology: Any = Depends(get_ontology_service),
    ):
        payload = dashboards.resolve_share(token=token)
        identity.require_workspace(principal, payload.workspace_id)
        event_id = payload.parameter_state.get("selected_event_id")
        if isinstance(event_id, str) and event_id:
            ontology.get_object(
                workspace_id=payload.workspace_id,
                object_id=_risk_event_object_id(event_id),
            )
        return payload.model_dump(mode="json")

    return router


__all__ = ["build_dashboard_router"]
