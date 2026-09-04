"""Persistence-neutral repository contract owned by Identity."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from .identity_schema import Principal, RegisterRequest


class IdentityRepository(Protocol):
    def seed_demo_accounts(self) -> None: ...

    def create_pending_user(self, request: RegisterRequest) -> dict[str, Any]: ...

    def authenticate(self, email: str, password: str) -> dict[str, Any]: ...

    def create_session(
        self,
        user_id: str,
        *,
        user_agent_hash: str | None = None,
        ip_hash: str | None = None,
        rotated_from: str | None = None,
        active_project_id: str | None = None,
    ) -> tuple[str, datetime]: ...

    def revoke_session(self, token: str) -> None: ...

    def set_session_active_project(self, token: str, *, user_id: str, project_id: str) -> None: ...

    def user_for_session(
        self,
        token: str,
        *,
        user_agent_hash: str | None = None,
        ip_hash: str | None = None,
        touch: bool = True,
    ) -> dict[str, Any]: ...

    def rotate_session(
        self,
        token: str,
        *,
        user_agent_hash: str | None = None,
        ip_hash: str | None = None,
    ) -> tuple[str, datetime, dict[str, Any]]: ...

    def list_active_sessions(
        self, *, user_id: str, current_token: str | None = None
    ) -> list[dict[str, Any]]: ...

    def revoke_other_sessions(self, *, user_id: str, current_token: str) -> int: ...

    def principal(self, user_id: str, *, active_project_id: str | None = None) -> Principal: ...

    def list_workspaces(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_display_preferences(self, *, user_id: str) -> dict[str, Any] | None: ...

    def save_display_preferences(
        self, *, user_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]: ...


__all__ = ["IdentityRepository"]
