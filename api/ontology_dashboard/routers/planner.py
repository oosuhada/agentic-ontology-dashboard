"""Project-scoped Ontology planner routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import (
    get_identity_service,
    get_ontology_planner_service,
    get_predictive_maintenance_runtime_service,
    get_rate_limiter,
    rate_limit_subject,
    require_csrf,
    require_permission,
)
from ..identity import IdentityService, Principal
from ..planner import (
    BoardRecommendationRequest,
    DashboardDraftRequest,
    GroundedNarrativeRequest,
    NaturalLanguageObjectQueryRequest,
    OntologyDashboardPlannerService,
    VisualizationRecommendationRequest,
)
from ..predictive_maintenance_runtime import PredictiveMaintenanceRuntimeService
from ..security import PLANNER_RATE, RateLimiter
from ..visualizations import SemanticVisualizationPlanRequest

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
    planner: OntologyDashboardPlannerService = Depends(get_ontology_planner_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    enforce_planner_rate(limiter, principal, "planner.object_query")
    identity.require_workspace(principal, request.workspace_id)
    return planner.object_query_plan(principal=principal, request=request).model_dump(mode="json")


@router.post("/board-recommendations")
def recommend_boards(
    request: BoardRecommendationRequest,
    principal: Principal = Depends(require_permission("planner.board_recommend")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    planner: OntologyDashboardPlannerService = Depends(get_ontology_planner_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    enforce_planner_rate(limiter, principal, "planner.board_recommend")
    identity.require_workspace(principal, request.workspace_id)
    return planner.board_recommendations(principal=principal, request=request).model_dump(mode="json")


@router.post("/dashboard-drafts")
def generate_dashboard_draft(
    request: DashboardDraftRequest,
    principal: Principal = Depends(require_permission("planner.dashboard_draft")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    planner: OntologyDashboardPlannerService = Depends(get_ontology_planner_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    enforce_planner_rate(limiter, principal, "planner.dashboard_draft")
    identity.require_workspace(principal, request.workspace_id)
    return planner.dashboard_draft(principal=principal, request=request).model_dump(mode="json")


@router.post("/visualizations/recommend")
def recommend_visualization(
    request: VisualizationRecommendationRequest,
    principal: Principal = Depends(require_permission("planner.board_recommend")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    planner: OntologyDashboardPlannerService = Depends(get_ontology_planner_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    enforce_planner_rate(limiter, principal, "planner.visualization_recommend")
    identity.require_workspace(principal, request.workspace_id)
    return planner.visualization_recommendation(principal=principal, request=request).model_dump(mode="json")


@router.post("/visualizations/semantic-plan")
def plan_semantic_visualization(
    request: SemanticVisualizationPlanRequest,
    principal: Principal = Depends(require_permission("planner.board_recommend")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    planner: OntologyDashboardPlannerService = Depends(get_ontology_planner_service),
    runtime: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    enforce_planner_rate(limiter, principal, "planner.semantic_visualization_plan")
    identity.require_workspace(principal, request.source.workspace_id)
    identity.require_project(principal, request.source.project_id)
    try:
        context = runtime.context(
            organization_id=principal.organization_id,
            project_id=request.source.project_id,
            workspace_id=request.source.workspace_id,
            dataset_version_id=request.source.dataset_version_id,
        )
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset Version not found: {error.args[0]}",
        ) from error
    return planner.semantic_visualization_plan(
        principal=principal,
        request=request,
        runtime_context=context,
    ).model_dump(mode="json")


@router.post("/grounded-narrative")
def generate_grounded_narrative(
    request: GroundedNarrativeRequest,
    principal: Principal = Depends(require_permission("planner.narrative")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    planner: OntologyDashboardPlannerService = Depends(get_ontology_planner_service),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    enforce_planner_rate(limiter, principal, "planner.narrative")
    identity.require_workspace(principal, request.workspace_id)
    return planner.grounded_narrative(principal=principal, request=request).model_dump(mode="json")
