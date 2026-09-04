"""Project-owned domain contracts shared with other Backend domains."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias

ProjectId: TypeAlias = str
ProjectScope: TypeAlias = str

DEFAULT_ORGANIZATION_ID = "org-ontology-demo"
DEFAULT_PROJECT_ID = "manufacturing-demo-project"
DEFAULT_WORKSPACE_ID = "manufacturing-demo"

DEMO_ORGANIZATION_ID = DEFAULT_ORGANIZATION_ID
DEMO_PROJECT_ID = DEFAULT_PROJECT_ID
DEMO_WORKSPACE_ID = DEFAULT_WORKSPACE_ID


@dataclass(frozen=True, slots=True)
class ProjectContext:
    organization_id: str
    project_id: ProjectId
    workspace_id: str


class ProjectContextResolverPort(Protocol):
    """Project-owned public contract for resolving and preparing workspace scope."""

    def resolve(
        self,
        workspace_id: str,
        *,
        expected_organization_id: str | None = None,
        expected_project_id: ProjectId | None = None,
        connection: Any | None = None,
    ) -> ProjectContext: ...

    def ensure_scope_columns(
        self,
        connection: Any,
        *,
        table: str,
        workspace_column: str = "workspace_id",
    ) -> None: ...


class ProjectAuditPort(Protocol):
    """Narrow audit capability supplied by application composition."""

    def record_admin_audit(
        self,
        *,
        actor_user_id: str,
        target_user_id: str | None,
        action: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> Any: ...


class ProjectEventQueryPort(Protocol):
    """Compatibility query boundary for Project-scoped event reads."""

    def list_events(self, project_id: ProjectId) -> list[dict[str, Any]]: ...


__all__ = [
    "DEFAULT_ORGANIZATION_ID",
    "DEFAULT_PROJECT_ID",
    "DEFAULT_WORKSPACE_ID",
    "DEMO_ORGANIZATION_ID",
    "DEMO_PROJECT_ID",
    "DEMO_WORKSPACE_ID",
    "ProjectAuditPort",
    "ProjectContext",
    "ProjectContextResolverPort",
    "ProjectEventQueryPort",
    "ProjectId",
    "ProjectScope",
]
