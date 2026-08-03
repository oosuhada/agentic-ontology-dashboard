from __future__ import annotations

import sqlite3

from ontology_dashboard.identity import AuthError, Principal

from .models import Project, ProjectCreateRequest, ProjectUpdateRequest
from .repository import ProjectRepository


class ProjectService:
    def __init__(self, repository: ProjectRepository) -> None:
        self.repository = repository

    @staticmethod
    def _project_scope(principal: Principal) -> list[str] | None:
        return None if principal.is_admin else principal.project_scopes

    def list_for_principal(self, principal: Principal) -> list[Project]:
        return [
            Project.model_validate(item)
            for item in self.repository.list_projects(
                organization_id=principal.organization_id,
                project_ids=self._project_scope(principal),
            )
            if item["status"] != "archived"
        ]

    def get_for_principal(self, principal: Principal, project_id: str) -> Project:
        self.require_project(principal, project_id)
        item = self.repository.get_project(
            organization_id=principal.organization_id,
            project_id=project_id,
        )
        if item is None or item["status"] == "archived":
            raise AuthError(404, "project_not_found", "Project를 찾을 수 없습니다.")
        return Project.model_validate(item)

    def list_workspaces(self, principal: Principal, project_id: str) -> list[dict[str, object]]:
        self.require_project(principal, project_id)
        return self.repository.list_workspaces(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_ids=None if principal.is_admin else principal.workspace_scopes,
        )

    def create(self, principal: Principal, request: ProjectCreateRequest) -> Project:
        if not principal.is_admin:
            raise AuthError(403, "permission_denied", "Project 생성은 조직 관리자만 수행할 수 있습니다.")
        try:
            item = self.repository.create_project(
                organization_id=principal.organization_id,
                request=request,
            )
        except sqlite3.IntegrityError as exc:
            raise AuthError(409, "project_slug_conflict", "같은 slug의 Project가 이미 존재합니다.") from exc
        return Project.model_validate(item)

    def update(
        self,
        principal: Principal,
        project_id: str,
        request: ProjectUpdateRequest,
    ) -> Project:
        if not principal.is_admin:
            raise AuthError(403, "permission_denied", "Project 수정은 조직 관리자만 수행할 수 있습니다.")
        if request.default_workspace_id is not None and not self.repository.workspace_belongs_to_project(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=request.default_workspace_id,
        ):
            raise AuthError(
                422,
                "invalid_default_workspace",
                "기본 Workspace는 같은 Organization과 Project에 속해야 합니다.",
            )
        item = self.repository.update_project(
            organization_id=principal.organization_id,
            project_id=project_id,
            request=request,
        )
        if item is None:
            raise AuthError(404, "project_not_found", "Project를 찾을 수 없습니다.")
        return Project.model_validate(item)

    @staticmethod
    def require_project(principal: Principal, project_id: str) -> None:
        if principal.is_admin:
            return
        if project_id not in principal.project_scopes:
            raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 요청입니다.")
