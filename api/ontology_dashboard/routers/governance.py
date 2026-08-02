"""Project/workspace-scoped Governance Workbench routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_governance_service, require_csrf, require_permission
from ..governance import GovernanceService
from ..identity import Principal

router = APIRouter(prefix="/api/projects/{project_id}/workspaces/{workspace_id}/governance", tags=["governance"])


@router.get("")
def governance_overview(
    project_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("governance.read")),
    service: GovernanceService = Depends(get_governance_service),
):
    return service.overview(
        principal=principal,
        project_id=project_id,
        workspace_id=workspace_id,
    ).model_dump(mode="json")


@router.get("/agent-runs/{run_id}")
def governance_agent_run(
    project_id: str,
    workspace_id: str,
    run_id: str,
    principal: Principal = Depends(require_permission("governance.read")),
    service: GovernanceService = Depends(get_governance_service),
):
    try:
        detail = service.agent_run(
            principal=principal,
            project_id=project_id,
            workspace_id=workspace_id,
            run_id=run_id,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"agent run not found: {error.args[0]}") from error
    return detail.model_dump(mode="json")


@router.post("/projections/{projection_id}/retry")
def retry_projection(
    project_id: str,
    workspace_id: str,
    projection_id: str,
    principal: Principal = Depends(require_permission("governance.projection.retry")),
    _: None = Depends(require_csrf),
    service: GovernanceService = Depends(get_governance_service),
):
    try:
        result = service.retry_projection(
            principal=principal,
            project_id=project_id,
            workspace_id=workspace_id,
            projection_id=projection_id,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"projection not found: {error.args[0]}") from error
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return result.model_dump(mode="json")
