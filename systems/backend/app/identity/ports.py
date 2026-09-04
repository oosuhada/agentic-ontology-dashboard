"""Public Identity contracts consumed by other Backend domains."""

from __future__ import annotations

from typing import Protocol

from .identity_schema import Principal


PrincipalContext = Principal
WorkspaceScope = str


class IdentityAccessPort(Protocol):
    """Narrow authorization/session surface exposed to other domains."""

    def principal_for_token(
        self,
        token: str,
        *,
        user_agent: str | None = None,
        client_ip: str | None = None,
    ) -> PrincipalContext: ...

    @staticmethod
    def require_permission(principal: PrincipalContext, permission: str) -> None: ...

    @staticmethod
    def require_project(principal: PrincipalContext, project_id: str) -> None: ...

    def require_workspace(self, principal: PrincipalContext, workspace_id: WorkspaceScope) -> None: ...


__all__ = ["IdentityAccessPort", "PrincipalContext", "WorkspaceScope"]
