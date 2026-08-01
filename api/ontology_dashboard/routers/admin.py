"""Administrator APIs with organization-scoped access."""

from fastapi import APIRouter, Depends

from ..dependencies import get_identity_service, get_role_workflow_service, require_csrf, require_permission
from ..identity import (
    AdminUserUpdateRequest,
    IdentityService,
    Principal,
    ProjectMembershipUpdateRequest,
)
from ..role_workflow_models import ApprovalDecisionRequest
from ..role_workflow_service import RoleWorkflowService

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/overview")
def admin_overview(
    principal: Principal = Depends(require_permission("admin.access")),
    identity: IdentityService = Depends(get_identity_service),
):
    users = identity.repository.list_users(
        organization_id=principal.organization_id,
        include_unassigned_pending=True,
    )
    return {
        "active_users": sum(user["status"] == "active" for user in users),
        "pending_users": sum(user["status"] == "pending_approval" for user in users),
        "disabled_users": sum(user["status"] == "disabled" for user in users),
        "workspace_count": len(
            identity.repository.list_workspaces(organization_id=principal.organization_id)
        ),
        "recent_admin_changes": identity.repository.list_admin_audit(
            limit=5,
            organization_id=principal.organization_id,
        ),
    }


@router.get("/users")
def admin_users(
    principal: Principal = Depends(require_permission("admin.users.read")),
    identity: IdentityService = Depends(get_identity_service),
):
    return {
        "items": identity.repository.list_users(
            organization_id=principal.organization_id,
            include_unassigned_pending=True,
        )
    }


@router.get("/projects/{project_id}/members")
def admin_project_members(
    project_id: str,
    principal: Principal = Depends(require_permission("admin.users.read")),
    identity: IdentityService = Depends(get_identity_service),
):
    return {
        "items": identity.list_project_members(
            principal=principal,
            project_id=project_id,
        )
    }


@router.put("/projects/{project_id}/members/{user_id}")
def admin_update_project_membership(
    project_id: str,
    user_id: str,
    request: ProjectMembershipUpdateRequest,
    principal: Principal = Depends(require_permission("admin.users.manage")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
):
    return identity.update_project_membership(
        principal=principal,
        project_id=project_id,
        target_user_id=user_id,
        request=request,
    )


@router.patch("/users/{user_id}")
def admin_update_user(
    user_id: str,
    request: AdminUserUpdateRequest,
    principal: Principal = Depends(require_permission("admin.users.manage")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
):
    return identity.repository.update_user(
        actor_user_id=principal.user_id,
        target_user_id=user_id,
        request=request,
        organization_id=principal.organization_id,
    )


@router.get("/roles")
def admin_roles(
    _: Principal = Depends(require_permission("admin.users.read")),
    identity: IdentityService = Depends(get_identity_service),
):
    return {"items": identity.repository.list_roles()}


@router.get("/workspaces")
def admin_workspaces(
    principal: Principal = Depends(require_permission("admin.users.read")),
    identity: IdentityService = Depends(get_identity_service),
):
    return {
        "items": identity.repository.list_workspaces(
            organization_id=principal.organization_id,
        )
    }


@router.get("/audit")
def admin_audit(
    principal: Principal = Depends(require_permission("admin.audit.read")),
    identity: IdentityService = Depends(get_identity_service),
):
    return {
        "items": identity.repository.list_admin_audit(
            organization_id=principal.organization_id,
        )
    }


@router.get("/workflow-approvals")
def admin_workflow_approvals(
    principal: Principal = Depends(require_permission("admin.access")),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
):
    return workflows.list_admin_approvals(principal=principal)


@router.post("/template-publish-requests/{request_id}/decision")
def admin_decide_template_publish_request(
    request_id: str,
    request: ApprovalDecisionRequest,
    principal: Principal = Depends(require_permission("dashboards.templates.approve")),
    _: None = Depends(require_csrf),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
):
    return workflows.decide_template_request(
        principal=principal,
        request_id=request_id,
        decision=request,
    )


@router.post("/model-release-requests/{request_id}/decision")
def admin_decide_model_release_request(
    request_id: str,
    request: ApprovalDecisionRequest,
    principal: Principal = Depends(require_permission("ml.release.approve")),
    _: None = Depends(require_csrf),
    workflows: RoleWorkflowService = Depends(get_role_workflow_service),
):
    return workflows.decide_model_release_request(
        principal=principal,
        request_id=request_id,
        decision=request,
    )
