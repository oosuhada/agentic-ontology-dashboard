from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_identity_service, get_modeling_service, require_permission
from ..identity import IdentityService, Principal
from ..modeling import ModelingService
from .predictive_maintenance_runtime import require_scope

router = APIRouter(prefix="/api/modeling", tags=["modeling"])


@router.get("/contracts")
def modeling_contracts(
    project_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("ml.console.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return {
        **service.contract_summary().model_dump(mode="json"),
        "artifact_capability": service.artifact_capability(),
        "organization_id": principal.organization_id,
        "project_id": project_id,
        "workspace_id": workspace_id,
    }
