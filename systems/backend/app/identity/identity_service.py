"""Canonical identity service facade and public identity API."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime
from typing import Any, Literal

from .identity_exception import AuthError
from .identity_schema import (
    CSRF_COOKIE,
    DEMO_ACCOUNTS,
    PERMISSION_DEFINITIONS,
    ROLE_DEFINITIONS,
    ROLE_PERMISSIONS,
    SESSION_COOKIE,
    SESSION_TTL_HOURS,
    PUBLIC_COMPARISON_EMAIL,
    PUBLIC_COMPARISON_PASSWORD,
    ActiveProjectRequest,
    AdminUserUpdateRequest,
    DisplayPreferenceUpdateRequest,
    LoginRequest,
    Principal,
    RegisterRequest,
    UserStatus,
)
from .identity_repository import IdentityRepository


class IdentityService:
    def __init__(
        self,
        repository: IdentityRepository,
        *,
        app_env: str | None = None,
        seed_demo: bool | None = None,
        rate_limit_namespace: str = "identity",
    ) -> None:
        self.app_env = (app_env or os.getenv("APP_ENV", "development")).lower()
        self.secure_cookies = self.app_env == "production"
        self.repository = repository
        self.rate_limit_namespace = rate_limit_namespace
        should_seed = seed_demo
        if should_seed is None:
            configured = os.getenv("SEED_DEMO_ACCOUNTS")
            should_seed = (
                configured.lower() in {"1", "true", "yes"}
                if configured is not None
                else self.app_env in {"development", "demo", "test"}
            )
        if self.app_env == "production" and should_seed:
            raise RuntimeError("demo account seed is forbidden when APP_ENV=production")
        if should_seed:
            self.repository.seed_demo_accounts()

    def register(self, request: RegisterRequest) -> dict[str, Any]:
        return self.repository.create_pending_user(request)

    @staticmethod
    def _client_hash(value: str | None) -> str | None:
        if not value:
            return None
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def login(
        self,
        request: LoginRequest,
        *,
        user_agent: str | None = None,
        client_ip: str | None = None,
    ) -> tuple[Principal, str, datetime, str]:
        user = self.repository.authenticate(request.email, request.password)
        principal = self.repository.principal(user["id"])
        token, expires_at = self.repository.create_session(
            user["id"],
            user_agent_hash=self._client_hash(user_agent),
            ip_hash=self._client_hash(client_ip),
            active_project_id=principal.active_project_id,
        )
        csrf_token = secrets.token_urlsafe(32)
        return principal, token, expires_at, csrf_token

    def open_public_comparison_session(
        self,
        *,
        user_agent: str | None = None,
        client_ip: str | None = None,
    ) -> tuple[Principal, str, datetime, str]:
        enabled = os.getenv("ENABLE_PUBLIC_BLUEPRINT_COMPARISON")
        public_enabled = (
            enabled.lower() in {"1", "true", "yes"}
            if enabled is not None
            else self.app_env in {"development", "demo", "test"}
        )
        if not public_enabled:
            raise AuthError("public_comparison_disabled", "공개 비교 화면을 사용할 수 없습니다.")
        return self.login(
            LoginRequest(
                email=PUBLIC_COMPARISON_EMAIL,
                password=PUBLIC_COMPARISON_PASSWORD,
            ),
            user_agent=user_agent,
            client_ip=client_ip,
        )

    def principal_for_token(
        self,
        token: str,
        *,
        user_agent: str | None = None,
        client_ip: str | None = None,
    ) -> Principal:
        user = self.repository.user_for_session(
            token,
            user_agent_hash=self._client_hash(user_agent),
            ip_hash=self._client_hash(client_ip),
        )
        return self.repository.principal(
            user["id"],
            active_project_id=user.get("active_project_id"),
        )

    def rotate_session(
        self,
        token: str,
        *,
        user_agent: str | None = None,
        client_ip: str | None = None,
    ) -> tuple[Principal, str, datetime, str]:
        new_token, expires_at, user = self.repository.rotate_session(
            token,
            user_agent_hash=self._client_hash(user_agent),
            ip_hash=self._client_hash(client_ip),
        )
        csrf_token = secrets.token_urlsafe(32)
        return (
            self.repository.principal(
                user["id"],
                active_project_id=user.get("active_project_id"),
            ),
            new_token,
            expires_at,
            csrf_token,
        )

    def active_sessions(self, *, principal: Principal, current_token: str) -> list[dict[str, Any]]:
        return self.repository.list_active_sessions(
            user_id=principal.user_id,
            current_token=current_token,
        )

    def revoke_other_sessions(self, *, principal: Principal, current_token: str) -> int:
        return self.repository.revoke_other_sessions(
            user_id=principal.user_id,
            current_token=current_token,
        )

    def logout(self, token: str) -> None:
        self.repository.revoke_session(token)

    @staticmethod
    def verify_csrf(cookie_value: str | None, header_value: str | None) -> None:
        if not cookie_value or not header_value or not hmac.compare_digest(cookie_value, header_value):
            raise AuthError(
                "csrf_validation_failed",
                "요청 검증에 실패했습니다. 페이지를 새로고침한 뒤 다시 시도하세요.",
            )

    @staticmethod
    def require_permission(principal: Principal, permission: str) -> None:
        if permission not in principal.permissions:
            raise AuthError("permission_denied", "이 작업을 수행할 권한이 없습니다.")

    def set_active_project(
        self,
        *,
        token: str,
        principal: Principal,
        request: ActiveProjectRequest,
    ) -> Principal:
        self.require_project(principal, request.project_id)
        self.repository.set_session_active_project(
            token,
            user_id=principal.user_id,
            project_id=request.project_id,
        )
        return self.repository.principal(
            principal.user_id,
            active_project_id=request.project_id,
        )

    @staticmethod
    def require_project(principal: Principal, project_id: str) -> None:
        if project_id not in principal.project_scopes:
            raise AuthError("project_scope_denied", "허용된 Project 범위를 벗어난 요청입니다.")

    def require_workspace(self, principal: Principal, workspace_id: str) -> None:
        if workspace_id not in principal.workspace_scopes:
            raise AuthError("workspace_scope_denied", "허용된 workspace 범위를 벗어난 요청입니다.")
        workspace = next(
            (
                item
                for item in self.repository.list_workspaces(
                    organization_id=principal.organization_id,
                )
                if item["id"] == workspace_id
            ),
            None,
        )
        if workspace is None:
            raise AuthError("workspace_scope_denied", "허용된 workspace 범위를 벗어난 요청입니다.")
        project_id = workspace.get("project_id")
        if not project_id or project_id not in principal.project_scopes:
            raise AuthError("project_scope_denied", "허용된 Project 범위를 벗어난 요청입니다.")
        if principal.active_project_id and project_id != principal.active_project_id:
            raise AuthError("active_project_mismatch", "먼저 해당 Project를 활성화해야 합니다.")

    @staticmethod
    def legacy_dashboard_role(
        principal: Principal,
        requested_role: str | None = None,
    ) -> Literal["manager", "engineer"]:
        if principal.is_admin and requested_role in {"manager", "engineer"}:
            return requested_role
        role = principal.roles[0] if principal.roles else ""
        mapping: dict[str, Literal["manager", "engineer"]] = {
            "executive_viewer": "manager",
            "process_manager": "manager",
            "process_engineer": "engineer",
            "maintenance_technician": "engineer",
            "quality_auditor": "manager",
            "ml_validator": "engineer",
            "fde": "engineer",
            "tenant_admin": "manager",
        }
        resolved = mapping.get(role, "manager")
        if requested_role is not None and requested_role != resolved:
            raise AuthError("role_context_denied", "현재 역할에 허용되지 않은 화면 관점입니다.")
        return resolved

    @staticmethod
    def report_role(
        principal: Principal,
        requested_role: str | None = None,
    ) -> Literal["manager", "engineer", "executive"]:
        if principal.is_admin and requested_role in {"manager", "engineer", "executive"}:
            return requested_role
        role = principal.roles[0] if principal.roles else ""
        mapping: dict[str, Literal["manager", "engineer", "executive"]] = {
            "executive_viewer": "executive",
            "process_manager": "manager",
            "process_engineer": "engineer",
            "maintenance_technician": "engineer",
            "quality_auditor": "manager",
            "ml_validator": "engineer",
            "fde": "engineer",
            "tenant_admin": "manager",
        }
        resolved = mapping.get(role, "manager")
        if requested_role is not None and requested_role != resolved:
            raise AuthError("role_context_denied", "현재 역할에 허용되지 않은 보고 관점입니다.")
        return resolved

    def get_display_preferences(self, *, user_id: str) -> dict[str, Any] | None:
        return self.repository.get_display_preferences(user_id=user_id)

    def save_display_preferences(self, *, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.save_display_preferences(user_id=user_id, payload=payload)


__all__ = [
    "ActiveProjectRequest",
    "AdminUserUpdateRequest",
    "AuthError",
    "CSRF_COOKIE",
    "DEMO_ACCOUNTS",
    "DisplayPreferenceUpdateRequest",
    "IdentityRepository",
    "IdentityService",
    "LoginRequest",
    "PERMISSION_DEFINITIONS",
    "Principal",
    "ROLE_DEFINITIONS",
    "ROLE_PERMISSIONS",
    "RegisterRequest",
    "SESSION_COOKIE",
    "SESSION_TTL_HOURS",
    "UserStatus",
]
