from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from .governance_service import GovernanceService


def build_governance_router(
    *,
    get_governance_service: Callable[..., GovernanceService],
    require_permission: Callable[[str], Any],
    require_csrf: Callable[..., None],
) -> APIRouter:
    router = APIRouter(
        prefix="/api/projects/{project_id}/workspaces/{workspace_id}/governance",
        tags=["governance"],
    )

    @router.get("")
    def governance_overview(
        project_id: str,
        workspace_id: str,
        principal: Any = Depends(require_permission("governance.read")),
        service: GovernanceService = Depends(get_governance_service),
    ):
        return service.overview(
            principal=principal,
            project_id=project_id,
            workspace_id=workspace_id,
        ).model_dump(mode="json")

    @router.post("/projections/{projection_id}/retry")
    def retry_projection(
        project_id: str,
        workspace_id: str,
        projection_id: str,
        principal: Any = Depends(require_permission("governance.projection.retry")),
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

    return router


__all__ = ["build_governance_router"]
