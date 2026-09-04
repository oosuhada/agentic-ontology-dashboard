"""Project metadata, scope, and membership lifecycle use cases."""

from __future__ import annotations

from app.identity.contracts import PrincipalContext, ROLE_DEFINITIONS, WorkspaceScope

from .project_domain import ProjectAuditPort, ProjectId
from .project_exception import ProjectError
from .project_repository import ProjectRepository
from .project_schema import (
    Project,
    ProjectCreateRequest,
    ProjectMembershipUpdateRequest,
    ProjectUpdateRequest,
)


class ProjectService:
    def __init__(
        self,
        repository: ProjectRepository,
        *,
        audit_port: ProjectAuditPort | None = None,
    ) -> None:
        self.repository = repository
        self.audit_port = audit_port

    @staticmethod
    def _project_scope(principal: PrincipalContext) -> list[ProjectId] | None:
        return None if principal.is_admin else principal.project_scopes

    @staticmethod
    def _require_permission(principal: PrincipalContext, permission: str) -> None:
        if permission not in principal.permissions:
            raise ProjectError("permission_denied", "이 작업을 수행할 권한이 없습니다.")

    @staticmethod
    def _require_membership_scope(principal: PrincipalContext, project_id: ProjectId) -> None:
        if project_id not in principal.project_scopes:
            raise ProjectError(
                "project_scope_denied",
                "허용된 Project 범위를 벗어난 요청입니다.",
            )

    def list_for_principal(self, principal: PrincipalContext) -> list[Project]:
        return [
            Project.model_validate(item)
            for item in self.repository.list_projects(
                organization_id=principal.organization_id,
                project_ids=self._project_scope(principal),
            )
            if item["status"] != "archived"
        ]

    def get_for_principal(self, principal: PrincipalContext, project_id: ProjectId) -> Project:
        self.require_project(principal, project_id)
        item = self.repository.get_project(
            organization_id=principal.organization_id,
            project_id=project_id,
        )
        if item is None or item["status"] == "archived":
            raise ProjectError("project_not_found", "Project를 찾을 수 없습니다.")
        return Project.model_validate(item)

    def list_workspaces(
        self,
        principal: PrincipalContext,
        project_id: ProjectId,
    ) -> list[dict[str, object]]:
        self.require_project(principal, project_id)
        workspace_ids: list[WorkspaceScope] | None = (
            None if principal.is_admin else principal.workspace_scopes
        )
        return self.repository.list_workspaces(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_ids=workspace_ids,
        )

    def create(self, principal: PrincipalContext, request: ProjectCreateRequest) -> Project:
        if not principal.is_admin:
            raise ProjectError(
                "permission_denied",
                "Project 생성은 조직 관리자만 수행할 수 있습니다.",
            )
        item = self.repository.create_project(
            organization_id=principal.organization_id,
            request=request,
        )
        return Project.model_validate(item)

    def update(
        self,
        principal: PrincipalContext,
        project_id: ProjectId,
        request: ProjectUpdateRequest,
    ) -> Project:
        if not principal.is_admin:
            raise ProjectError(
                "permission_denied",
                "Project 수정은 조직 관리자만 수행할 수 있습니다.",
            )
        if request.default_workspace_id is not None and not self.repository.workspace_belongs_to_project(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=request.default_workspace_id,
        ):
            raise ProjectError(
                "invalid_default_workspace",
                "기본 Workspace는 같은 Organization과 Project에 속해야 합니다.",
            )
        item = self.repository.update_project(
            organization_id=principal.organization_id,
            project_id=project_id,
            request=request,
        )
        if item is None:
            raise ProjectError("project_not_found", "Project를 찾을 수 없습니다.")
        return Project.model_validate(item)

    @staticmethod
    def require_project(principal: PrincipalContext, project_id: ProjectId) -> None:
        if principal.is_admin:
            return
        if project_id not in principal.project_scopes:
            raise ProjectError(
                "project_scope_denied",
                "허용된 Project 범위를 벗어난 요청입니다.",
            )

    def list_project_members(
        self,
        *,
        principal: PrincipalContext,
        project_id: ProjectId,
    ) -> list[dict[str, object]]:
        self._require_permission(principal, "admin.users.read")
        self._require_membership_scope(principal, project_id)
        return self.repository.list_project_members(
            organization_id=principal.organization_id,
            project_id=project_id,
        )

    def update_project_membership(
        self,
        *,
        principal: PrincipalContext,
        project_id: ProjectId,
        target_user_id: str,
        request: ProjectMembershipUpdateRequest,
    ) -> dict[str, object]:
        self._require_permission(principal, "admin.users.manage")
        self._require_membership_scope(principal, project_id)
        invalid_roles = sorted(set(request.roles) - set(ROLE_DEFINITIONS))
        if invalid_roles:
            raise ProjectError(
                "invalid_role",
                f"알 수 없는 역할입니다: {', '.join(invalid_roles)}",
            )
        if not request.roles:
            raise ProjectError(
                "role_required",
                "Project membership에는 역할이 하나 이상 필요합니다.",
            )
        before, after = self.repository.update_project_membership(
            actor_user_id=principal.user_id,
            organization_id=principal.organization_id,
            project_id=project_id,
            target_user_id=target_user_id,
            status=request.status,
            roles=request.roles,
        )
        if self.audit_port is not None:
            self.audit_port.record_admin_audit(
                actor_user_id=principal.user_id,
                target_user_id=target_user_id,
                action="project.membership.updated",
                before=before or {},
                after=after,
            )
        return after


__all__ = ["ProjectService"]
