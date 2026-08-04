"""Scoped multi-store agent orchestration routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import get_multistore_orchestrator, require_csrf, require_permission
from ..identity import Principal
from ..orchestration import AgentQueryRequest, MultiStoreOrchestrator

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/query")
def run_agent_query(
    request: AgentQueryRequest,
    principal: Principal = Depends(require_permission("planner.object_query")),
    _: None = Depends(require_csrf),
    orchestrator: MultiStoreOrchestrator = Depends(get_multistore_orchestrator),
):
    return orchestrator.run(principal=principal, request=request).model_dump(mode="json")


@router.get("/runs")
def list_agent_runs(
    project_id: str = Query(min_length=3, max_length=160),
    workspace_id: str = Query(min_length=3, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    route_filter: str | None = Query(default=None, alias="route"),
    search: str | None = Query(default=None, max_length=240),
    principal: Principal = Depends(require_permission("planner.object_query")),
    orchestrator: MultiStoreOrchestrator = Depends(get_multistore_orchestrator),
):
    return orchestrator.list_runs(
        principal=principal,
        project_id=project_id,
        workspace_id=workspace_id,
        offset=offset,
        limit=limit,
        status=status_filter,
        route=route_filter,
        search=search,
    ).model_dump(mode="json")


@router.get("/runs/{run_id}")
def inspect_agent_run(
    run_id: str,
    project_id: str = Query(min_length=3, max_length=160),
    workspace_id: str | None = Query(default=None, min_length=3, max_length=160),
    principal: Principal = Depends(require_permission("planner.object_query")),
    orchestrator: MultiStoreOrchestrator = Depends(get_multistore_orchestrator),
):
    try:
        run = orchestrator.inspect(
            principal=principal,
            project_id=project_id,
            run_id=run_id,
            workspace_id=workspace_id,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"agent run not found: {error.args[0]}") from error
    return run.model_dump(mode="json")
