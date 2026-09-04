"""FastAPI adapter for the canonical Planner application capability."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from app.common.rate_limit import PLANNER_RATE, RateLimiter
from app.identity import IdentityService, Principal

from .planner_schema import (
    BoardRecommendationRequest,
    DashboardDraftRequest,
    GroundedNarrativeRequest,
    NaturalLanguageObjectQueryRequest,
    VisualizationRecommendationRequest,
)
from .planner_service import OntologyDashboardPlannerService


def build_planner_router(
    *,
    get_identity_service: Callable[..., IdentityService],
    get_planner_service: Callable[..., OntologyDashboardPlannerService],
    get_runtime_service: Callable[..., Any],
    get_rate_limiter: Callable[..., RateLimiter],
    rate_limit_subject: Callable[..., str],
    require_csrf: Callable[..., Any],
    require_permission: Callable[[str], Callable[..., Principal]],
) -> APIRouter:
    router = APIRouter(prefix="/api/planner", tags=["planner"])

    def enforce_planner_rate(
        limiter: RateLimiter,
        principal: Principal,
        bucket: str,
    ) -> None:
        limiter.check(
            bucket=bucket,
            subject=rate_limit_subject(principal.user_id),
            rule=PLANNER_RATE,
        )

    @router.post("/object-query")
    def plan_object_query(
        request: NaturalLanguageObjectQueryRequest,
        principal: Principal = Depends(require_permission("planner.object_query")),
        _: None = Depends(require_csrf),
        identity: IdentityService = Depends(get_identity_service),
        planner: OntologyDashboardPlannerService = Depends(get_planner_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ) -> dict[str, Any]:
        enforce_planner_rate(limiter, principal, "planner.object_query")
        identity.require_workspace(principal, request.workspace_id)
        return planner.object_query_plan(
            principal=principal,
            request=request,
        ).model_dump(mode="json")

    @router.post("/board-recommendations")
    def recommend_boards(
        request: BoardRecommendationRequest,
        principal: Principal = Depends(require_permission("planner.board_recommend")),
        _: None = Depends(require_csrf),
        identity: IdentityService = Depends(get_identity_service),
        planner: OntologyDashboardPlannerService = Depends(get_planner_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ) -> dict[str, Any]:
        enforce_planner_rate(limiter, principal, "planner.board_recommend")
        identity.require_workspace(principal, request.workspace_id)
        return planner.board_recommendations(
            principal=principal,
            request=request,
        ).model_dump(mode="json")

    @router.post("/dashboard-drafts")
    def generate_dashboard_draft(
        request: DashboardDraftRequest,
        principal: Principal = Depends(require_permission("planner.dashboard_draft")),
        _: None = Depends(require_csrf),
        identity: IdentityService = Depends(get_identity_service),
        planner: OntologyDashboardPlannerService = Depends(get_planner_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ) -> dict[str, Any]:
        enforce_planner_rate(limiter, principal, "planner.dashboard_draft")
        identity.require_workspace(principal, request.workspace_id)
        return planner.dashboard_draft(
            principal=principal,
            request=request,
        ).model_dump(mode="json")

    @router.post("/visualizations/recommend")
    def recommend_visualization(
        request: VisualizationRecommendationRequest,
        principal: Principal = Depends(require_permission("planner.board_recommend")),
        _: None = Depends(require_csrf),
        identity: IdentityService = Depends(get_identity_service),
        planner: OntologyDashboardPlannerService = Depends(get_planner_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ) -> dict[str, Any]:
        enforce_planner_rate(limiter, principal, "planner.visualization_recommend")
        identity.require_workspace(principal, request.workspace_id)
        return planner.visualization_recommendation(
            principal=principal,
            request=request,
        ).model_dump(mode="json")

    @router.post("/visualizations/semantic-plan")
    def plan_semantic_visualization(
        request: dict[str, Any],
        principal: Principal = Depends(require_permission("planner.board_recommend")),
        _: None = Depends(require_csrf),
        identity: IdentityService = Depends(get_identity_service),
        planner: OntologyDashboardPlannerService = Depends(get_planner_service),
        runtime: Any = Depends(get_runtime_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ) -> dict[str, Any]:
        enforce_planner_rate(limiter, principal, "planner.semantic_visualization_plan")
        try:
            parsed = planner.parse_semantic_request(request)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        identity.require_workspace(principal, parsed.source.workspace_id)
        identity.require_project(principal, parsed.source.project_id)
        try:
            context = runtime.context(
                organization_id=principal.organization_id,
                project_id=parsed.source.project_id,
                workspace_id=parsed.source.workspace_id,
                dataset_version_id=parsed.source.dataset_version_id,
            )
        except KeyError as error:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset Version not found: {error.args[0]}",
            ) from error
        response = planner.semantic_visualization_plan(
            principal=principal,
            request=parsed,
            runtime_context=context,
        )
        return response.model_dump(mode="json")

    @router.post("/grounded-narrative")
    def generate_grounded_narrative(
        request: GroundedNarrativeRequest,
        principal: Principal = Depends(require_permission("planner.narrative")),
        _: None = Depends(require_csrf),
        identity: IdentityService = Depends(get_identity_service),
        planner: OntologyDashboardPlannerService = Depends(get_planner_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ) -> dict[str, Any]:
        enforce_planner_rate(limiter, principal, "planner.narrative")
        identity.require_workspace(principal, request.workspace_id)
        return planner.grounded_narrative(
            principal=principal,
            request=request,
        ).model_dump(mode="json")

    return router


__all__ = ["build_planner_router"]
