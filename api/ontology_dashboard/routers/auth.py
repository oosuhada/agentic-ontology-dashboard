"""Authentication and session routes."""

from fastapi import APIRouter, Depends, Request, Response

from ..dependencies import (
    client_ip,
    current_principal,
    get_identity_service,
    get_rate_limiter,
    rate_limit_subject,
    require_csrf,
    set_auth_cookies,
)
from ..identity import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    ActiveProjectRequest,
    AuthError,
    IdentityService,
    LoginRequest,
    Principal,
    RegisterRequest,
)
from ..security import LOGIN_RATE, SESSION_RATE, InMemoryRateLimiter

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
    }


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    identity: IdentityService = Depends(get_identity_service),
    limiter: InMemoryRateLimiter = Depends(get_rate_limiter),
):
    limiter.check(
        bucket="auth.login",
        subject=rate_limit_subject(str(identity.repository.path), client_ip(request), payload.email.lower()),
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
        raise AuthError(401, "authentication_required", "로그인이 필요합니다.")
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
    limiter: InMemoryRateLimiter = Depends(get_rate_limiter),
):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthError(401, "authentication_required", "로그인이 필요합니다.")
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
        raise AuthError(401, "authentication_required", "로그인이 필요합니다.")
    return {"items": identity.active_sessions(principal=principal, current_token=token)}


@router.delete("/sessions/others")
def revoke_other_sessions(
    request: Request,
    principal: Principal = Depends(current_principal),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    limiter: InMemoryRateLimiter = Depends(get_rate_limiter),
):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthError(401, "authentication_required", "로그인이 필요합니다.")
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
