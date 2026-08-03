"""Project-scoped role workspace and approval-request routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import (
    get_identity_service,
    get_role_workflow_service,
    require_csrf,
    require_permission,
)
from ..identity import IdentityService, Principal
from ..role_workflow_models import AuditExportCheckpointRequest, ModelReleaseRequestCreate
from ..role_workflow_service import RoleWorkflowService

router = APIRouter(prefix="/api/role-workspaces", tags=["role-workspaces"])


@router.get("/executive")
def executive_role_workspace(
    workspace_id: str,
    principal: Principal = Depends(require_permission("executive.overview.read")),
    identity: IdentityService = Depends(get_identity_service),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
):
    identity.require_workspace(principal, workspace_id)
    return workflows.executive_overview(
        principal=principal,
        workspace_id=workspace_id,
    ).model_dump(mode="json")


@router.get("/audit")
def audit_role_workspace(
    workspace_id: str,
    event_id: str,
    principal: Principal = Depends(require_permission("audit.reconstruction.read")),
    identity: IdentityService = Depends(get_identity_service),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
):
    identity.require_workspace(principal, workspace_id)
    return workflows.audit_reconstruction(
        principal=principal,
        workspace_id=workspace_id,
        event_id=event_id,
    ).model_dump(mode="json")


@router.post("/audit/export-checkpoints", status_code=201)
def create_audit_export_checkpoint(
    request: AuditExportCheckpointRequest,
    principal: Principal = Depends(require_permission("audit.export.checkpoint")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
):
    identity.require_workspace(principal, request.workspace_id)
    return workflows.create_audit_export_checkpoint(principal=principal, request=request)


@router.get("/field")
def field_role_workspace(
    workspace_id: str,
    principal: Principal = Depends(require_permission("field.tasks.read")),
    identity: IdentityService = Depends(get_identity_service),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
):
    identity.require_workspace(principal, workspace_id)
    return workflows.field_workspace(
        principal=principal,
        workspace_id=workspace_id,
    ).model_dump(mode="json")


@router.get("/fde")
def fde_role_workspace(
    workspace_id: str,
    principal: Principal = Depends(require_permission("fde.workbench.read")),
    identity: IdentityService = Depends(get_identity_service),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
):
    identity.require_workspace(principal, workspace_id)
    return workflows.fde_workbench(
        principal=principal,
        workspace_id=workspace_id,
    ).model_dump(mode="json")


@router.get("/ml")
def ml_role_workspace(
    workspace_id: str,
    principal: Principal = Depends(require_permission("ml.console.read")),
    identity: IdentityService = Depends(get_identity_service),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
):
    identity.require_workspace(principal, workspace_id)
    return workflows.model_console(
        principal=principal,
        workspace_id=workspace_id,
    ).model_dump(mode="json")


@router.post("/ml/release-requests", status_code=201)
def create_model_release_request(
    request: ModelReleaseRequestCreate,
    principal: Principal = Depends(require_permission("ml.release.request")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
):
    identity.require_workspace(principal, request.workspace_id)
    return workflows.create_model_release_request(principal=principal, request=request)
