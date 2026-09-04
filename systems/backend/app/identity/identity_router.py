"""HTTP adapter for authentication and session use cases.

The router is constructed by the composition root so this domain adapter does
not import legacy dependency wiring or infrastructure implementations.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from app.common.rate_limit import LOGIN_RATE, SESSION_RATE, RateLimiter

from .identity_exception import AuthError
from .identity_schema import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    ActiveProjectRequest,
    DisplayPreferenceUpdateRequest,
    LoginRequest,
    Principal,
    RegisterRequest,
)
from .identity_service import IdentityService


_IDENTITY_HTTP_STATUS_BY_CODE = {
    "authentication_required": 401,
    "invalid_credentials": 401,
    "session_expired": 401,
    "session_idle_timeout": 401,
    "session_client_mismatch": 401,
    "account_disabled": 403,
    "account_inactive": 403,
    "board_role_denied": 403,
    "csrf_validation_failed": 403,
    "organization_required": 403,
    "organization_scope_denied": 403,
    "pending_approval": 403,
    "permission_denied": 403,
    "project_scope_denied": 403,
    "role_context_denied": 403,
    "tenant_scope_denied": 403,
    "workspace_scope_denied": 403,
    "notification_not_found": 404,
    "project_not_found": 404,
    "public_comparison_disabled": 404,
    "user_not_found": 404,
    "action_in_progress": 409,
    "active_project_mismatch": 409,
    "active_project_required": 409,
    "analysis_version_conflict": 409,
    "dashboard_revision_conflict": 409,
    "email_already_registered": 409,
    "idempotency_key_conflict": 409,
    "mandatory_board_required": 409,
    "prior_action_failed": 409,
    "project_slug_conflict": 409,
    "report_revision_conflict": 409,
    "self_lockout_blocked": 409,
    "invalid_default_workspace": 422,
    "invalid_permission": 422,
    "invalid_role": 422,
    "invalid_workspace_scope": 422,
    "project_action_not_configured": 422,
    "project_context_mismatch": 422,
    "role_required": 422,
}


def identity_http_status(error: AuthError) -> int:
    """Map Identity application error codes to HTTP at the presentation edge."""

    return _IDENTITY_HTTP_STATUS_BY_CODE.get(error.code, 400)


def build_identity_router(
    *,
    get_identity_service: Callable[..., IdentityService],
    get_rate_limiter: Callable[..., RateLimiter],
    current_principal: Callable[..., Principal],
    require_csrf: Callable[..., None],
    client_ip: Callable[[Request], str],
    rate_limit_subject: Callable[..., str],
    set_auth_cookies: Callable[..., None],
) -> APIRouter:
    """Build the Identity HTTP adapter from composition-owned dependencies."""

    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.post("/register", status_code=201)
    def register(request: RegisterRequest, identity: IdentityService = Depends(get_identity_service)):
        user = identity.register(request)
        return {
            "user_id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "status": user["status"],
            "requested_organization_name": user["requested_organization_name"],
            "requested_role": user["requested_role_code"],
        }

    @router.post("/login")
    def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
        identity: IdentityService = Depends(get_identity_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ):
        limiter.check(
            bucket="auth.login",
            subject=rate_limit_subject(
                identity.rate_limit_namespace,
                client_ip(request),
                payload.email.lower(),
            ),
            rule=LOGIN_RATE,
        )
        principal, token, expires_at, csrf_token = identity.login(
            payload,
            user_agent=request.headers.get("User-Agent"),
            client_ip=client_ip(request),
        )
        set_auth_cookies(
            response=response,
            identity=identity,
            token=token,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
        return {"user": principal.model_dump(mode="json"), "csrf_token": csrf_token}

    @router.post("/public-blueprint-comparison")
    def public_blueprint_comparison(
        request: Request,
        response: Response,
        identity: IdentityService = Depends(get_identity_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ):
        limiter.check(
            bucket="auth.public_blueprint_comparison",
            subject=rate_limit_subject(identity.rate_limit_namespace, client_ip(request)),
            rule=SESSION_RATE,
        )
        principal, token, expires_at, csrf_token = identity.open_public_comparison_session(
            user_agent=request.headers.get("User-Agent"),
            client_ip=client_ip(request),
        )
        set_auth_cookies(
            response=response,
            identity=identity,
            token=token,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
        return {"user": principal.model_dump(mode="json"), "csrf_token": csrf_token}

    @router.post("/logout", status_code=204)
    def logout(
        request: Request,
        response: Response,
        _: None = Depends(require_csrf),
        identity: IdentityService = Depends(get_identity_service),
    ):
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            identity.logout(token)
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(CSRF_COOKIE, path="/")

    @router.get("/me")
    def me(request: Request, principal: Principal = Depends(current_principal)):
        return {
            "user": principal.model_dump(mode="json"),
            "csrf_token": request.cookies.get(CSRF_COOKIE),
        }

    @router.get("/display-preferences")
    def get_display_preferences(
        principal: Principal = Depends(current_principal),
        identity: IdentityService = Depends(get_identity_service),
    ):
        return {"preferences": identity.get_display_preferences(user_id=principal.user_id)}

    @router.put("/display-preferences")
    def save_display_preferences(
        payload: DisplayPreferenceUpdateRequest,
        principal: Principal = Depends(current_principal),
        _: None = Depends(require_csrf),
        identity: IdentityService = Depends(get_identity_service),
    ):
        return identity.save_display_preferences(
            user_id=principal.user_id,
            payload=payload.model_dump(mode="json"),
        )

    @router.patch("/active-project")
    def set_active_project(
        payload: ActiveProjectRequest,
        request: Request,
        principal: Principal = Depends(current_principal),
        _: None = Depends(require_csrf),
        identity: IdentityService = Depends(get_identity_service),
    ):
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise AuthError("authentication_required", "로그인이 필요합니다.")
        updated = identity.set_active_project(
            token=token,
            principal=principal,
            request=payload,
        )
        return {"user": updated.model_dump(mode="json")}

    @router.post("/refresh")
    def refresh_session(
        request: Request,
        response: Response,
        _: None = Depends(require_csrf),
        identity: IdentityService = Depends(get_identity_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ):
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise AuthError("authentication_required", "로그인이 필요합니다.")
        limiter.check(
            bucket="auth.refresh",
            subject=rate_limit_subject(token),
            rule=SESSION_RATE,
        )
        principal, new_token, expires_at, csrf_token = identity.rotate_session(
            token,
            user_agent=request.headers.get("User-Agent"),
            client_ip=client_ip(request),
        )
        set_auth_cookies(
            response=response,
            identity=identity,
            token=new_token,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
        return {"user": principal.model_dump(mode="json"), "csrf_token": csrf_token}

    @router.get("/sessions")
    def list_sessions(
        request: Request,
        principal: Principal = Depends(current_principal),
        identity: IdentityService = Depends(get_identity_service),
    ):
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise AuthError("authentication_required", "로그인이 필요합니다.")
        return {"items": identity.active_sessions(principal=principal, current_token=token)}

    @router.delete("/sessions/others")
    def revoke_other_sessions(
        request: Request,
        principal: Principal = Depends(current_principal),
        _: None = Depends(require_csrf),
        identity: IdentityService = Depends(get_identity_service),
        limiter: RateLimiter = Depends(get_rate_limiter),
    ):
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise AuthError("authentication_required", "로그인이 필요합니다.")
        limiter.check(
            bucket="auth.sessions.revoke_others",
            subject=rate_limit_subject(principal.user_id),
            rule=SESSION_RATE,
        )
        return {
            "revoked": identity.revoke_other_sessions(
                principal=principal,
                current_token=token,
            )
        }

    return router


__all__ = ["build_identity_router", "identity_http_status"]
