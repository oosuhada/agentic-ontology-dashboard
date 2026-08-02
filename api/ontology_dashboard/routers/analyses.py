"""Versioned Analysis definitions, server execution and node-result APIs."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from ..analysis_models import AnalysisCreateRequest, AnalysisRunRequest, AnalysisUpdateRequest
from ..datasets import AnalysisDatasetMaterializer, AnalysisMaterializationRequest
from ..analysis_repository import AnalysisVersionConflict
from ..analysis_service import AnalysisNotFound, AnalysisService
from ..dependencies import (
    get_analysis_materializer,
    get_analysis_service,
    get_identity_service,
    get_ontology_service,
    require_csrf,
    require_permission,
)
from ..identity import IdentityService, Principal
from ..ontology_service import OntologyService

router = APIRouter(tags=["analyses"])


@router.post("/api/analyses")
def create_analysis(
    request: AnalysisCreateRequest,
    principal: Principal = Depends(require_permission("dashboards.personalize")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    analyses: AnalysisService = Depends(get_analysis_service),
):
    identity.require_workspace(principal, request.workspace_id)
    return analyses.create(request, principal).model_dump(mode="json")


@router.get("/api/analyses/{analysis_id}")
def get_analysis(
    analysis_id: str,
    workspace_id: str,
    version: int | None = Query(default=None, ge=1),
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    identity: IdentityService = Depends(get_identity_service),
    analyses: AnalysisService = Depends(get_analysis_service),
):
    identity.require_workspace(principal, workspace_id)
    try:
        return analyses.get(
            analysis_id=analysis_id,
            workspace_id=workspace_id,
            principal=principal,
            version=version,
        ).model_dump(mode="json")
    except AnalysisNotFound as exc:
        from ..service import EventNotFound

        raise EventNotFound(str(exc.args[0])) from exc


@router.put("/api/analyses/{analysis_id}")
def update_analysis(
    analysis_id: str,
    request: AnalysisUpdateRequest,
    principal: Principal = Depends(require_permission("dashboards.personalize")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    analyses: AnalysisService = Depends(get_analysis_service),
):
    identity.require_workspace(principal, request.workspace_id)
    try:
        return analyses.update(
            analysis_id=analysis_id,
            request=request,
            principal=principal,
        ).model_dump(mode="json")
    except AnalysisNotFound as exc:
        from ..service import EventNotFound

        raise EventNotFound(str(exc.args[0])) from exc
    except AnalysisVersionConflict as exc:
        from ..identity import AuthError

        raise AuthError(409, "analysis_version_conflict", str(exc)) from exc


@router.post("/api/analyses/{analysis_id}/run")
def run_analysis(
    analysis_id: str,
    request: AnalysisRunRequest,
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    analyses: AnalysisService = Depends(get_analysis_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    identity.require_workspace(principal, request.workspace_id)
    try:
        return analyses.run(
            analysis_id=analysis_id,
            request=request,
            principal=principal,
            ontology=ontology,
        ).model_dump(mode="json")
    except AnalysisNotFound as exc:
        from ..service import EventNotFound

        raise EventNotFound(str(exc.args[0])) from exc


@router.post(
    "/api/analyses/{analysis_id}/materializations",
    status_code=status.HTTP_201_CREATED,
)
def materialize_analysis_result(
    analysis_id: str,
    request: AnalysisMaterializationRequest,
    principal: Principal = Depends(require_permission("datasets.ingest")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    materializer: AnalysisDatasetMaterializer = Depends(get_analysis_materializer),
):
    identity.require_workspace(principal, request.workspace_id)
    if principal.active_project_id != request.project_id:
        raise HTTPException(status_code=409, detail="request project must be the active Project")
    try:
        return materializer.materialize(
            principal=principal,
            analysis_id=analysis_id,
            request=request,
        ).model_dump(mode="json")
    except AnalysisNotFound as error:
        raise HTTPException(status_code=404, detail=f"analysis not found: {error.args[0]}") from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error.args[0])) from error


@router.post(
    "/api/analyses/{analysis_id}/jobs",
    status_code=status.HTTP_202_ACCEPTED,
)
def queue_analysis_run(
    analysis_id: str,
    request: AnalysisRunRequest,
    background_tasks: BackgroundTasks,
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    analyses: AnalysisService = Depends(get_analysis_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    identity.require_workspace(principal, request.workspace_id)
    queued = analyses.queue_run(
        analysis_id=analysis_id,
        request=request,
        principal=principal,
    )
    background_tasks.add_task(
        analyses.execute_queued_run,
        run_id=queued.id,
        request=request,
        principal=principal,
        ontology=ontology,
    )
    return queued.model_dump(mode="json")


@router.post("/api/analysis-runs/{run_id}/cancel")
def cancel_analysis_run(
    run_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    analyses: AnalysisService = Depends(get_analysis_service),
):
    identity.require_workspace(principal, workspace_id)
    try:
        return analyses.cancel_run(
            run_id=run_id,
            workspace_id=workspace_id,
            principal=principal,
        ).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"analysis run not found: {error.args[0]}") from error


@router.get("/api/analysis-runs/{run_id}/nodes/{node_id}/rows")
def get_analysis_node_rows(
    run_id: str,
    node_id: str,
    workspace_id: str,
    cursor: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    identity: IdentityService = Depends(get_identity_service),
    analyses: AnalysisService = Depends(get_analysis_service),
):
    identity.require_workspace(principal, workspace_id)
    try:
        return analyses.node_rows_page(
            run_id=run_id,
            node_id=node_id,
            workspace_id=workspace_id,
            principal=principal,
            cursor=cursor,
            limit=limit,
        ).model_dump(mode="json")
    except AnalysisNotFound as error:
        raise HTTPException(status_code=404, detail=f"analysis result not found: {error.args[0]}") from error


@router.get("/api/analysis-runs/{run_id}")
def get_analysis_run(
    run_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    identity: IdentityService = Depends(get_identity_service),
    analyses: AnalysisService = Depends(get_analysis_service),
):
    identity.require_workspace(principal, workspace_id)
    try:
        return analyses.get_run(
            run_id=run_id,
            workspace_id=workspace_id,
            principal=principal,
        ).model_dump(mode="json")
    except AnalysisNotFound as exc:
        from ..service import EventNotFound

        raise EventNotFound(str(exc.args[0])) from exc


@router.get("/api/analyses/{analysis_id}/nodes/{node_id}/result")
def get_analysis_node_result(
    analysis_id: str,
    node_id: str,
    workspace_id: str,
    version_policy: str = Query(default="pinned", pattern="^(pinned|latest_published)$"),
    version: int | None = Query(default=None, ge=1),
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    identity: IdentityService = Depends(get_identity_service),
    analyses: AnalysisService = Depends(get_analysis_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    identity.require_workspace(principal, workspace_id)
    try:
        return analyses.node_result(
            analysis_id=analysis_id,
            node_id=node_id,
            workspace_id=workspace_id,
            version_policy=version_policy,
            version=version,
            principal=principal,
            ontology=ontology,
        ).model_dump(mode="json")
    except AnalysisNotFound as exc:
        from ..service import EventNotFound

        raise EventNotFound(str(exc.args[0])) from exc
