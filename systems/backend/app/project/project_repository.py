"""Persistence-neutral Project repository contract and stable demo identifiers."""

from __future__ import annotations

from typing import Any, Protocol

from .project_domain import (
    DEFAULT_ORGANIZATION_ID,
    DEFAULT_PROJECT_ID,
    DEFAULT_WORKSPACE_ID,
    DEMO_ORGANIZATION_ID,
    DEMO_PROJECT_ID,
    DEMO_WORKSPACE_ID,
    ProjectId,
)
from .project_schema import ProjectCreateRequest, ProjectUpdateRequest


class ProjectRepository(Protocol):
    def list_projects(
        self,
        *,
        organization_id: str,
        project_ids: list[ProjectId] | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_project(
        self, *, organization_id: str, project_id: ProjectId
    ) -> dict[str, Any] | None: ...

    def list_workspaces(
        self,
        *,
        organization_id: str,
        project_id: ProjectId,
        workspace_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...

    def create_project(
        self, *, organization_id: str, request: ProjectCreateRequest
    ) -> dict[str, Any]: ...

    def update_project(
        self,
        *,
        organization_id: str,
        project_id: ProjectId,
        request: ProjectUpdateRequest,
    ) -> dict[str, Any] | None: ...

    def workspace_belongs_to_project(
        self,
        *,
        organization_id: str,
        project_id: ProjectId,
        workspace_id: str,
    ) -> bool: ...

    def list_project_members(
        self, *, organization_id: str, project_id: ProjectId
    ) -> list[dict[str, Any]]: ...

    def update_project_membership(
        self,
        *,
        actor_user_id: str,
        organization_id: str,
        project_id: ProjectId,
        target_user_id: str,
        status: str,
        roles: list[str],
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]: ...


__all__ = [
    "DEFAULT_ORGANIZATION_ID",
    "DEFAULT_PROJECT_ID",
    "DEFAULT_WORKSPACE_ID",
    "DEMO_ORGANIZATION_ID",
    "DEMO_PROJECT_ID",
    "DEMO_WORKSPACE_ID",
    "ProjectRepository",
]
