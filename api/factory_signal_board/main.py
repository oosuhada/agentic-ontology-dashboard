from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .contracts import DecisionRequest, FollowUpRequest, LayoutRequest, NoteRequest, ReportRequest
from .identity import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    AdminUserUpdateRequest,
    AuthError,
    IdentityService,
    LoginRequest,
    Principal,
    RegisterRequest,
)
from .ontology import ACTION_TYPES, LINK_TYPES, MANUFACTURING_PACK, OBJECT_TYPES, registry_payload
from .service import EventNotFound, FactorySignalService

ROOT = Path(__file__).resolve().parents[2]
MANUFACTURING_WORKSPACE = "manufacturing-demo"


def database_path() -> str:
    return os.getenv("FACTORY_SIGNAL_DB", str(ROOT / "data" / "local" / "factory_signal_board.db"))


@lru_cache(maxsize=1)
def get_service() -> FactorySignalService:
    return FactorySignalService(ROOT, database_path=database_path())


@lru_cache(maxsize=1)
def get_identity_service() -> IdentityService:
    return IdentityService(database_path())


app = FastAPI(
    title="Ontology Dashboard API",
    version="0.2.0",
    description=(
        "Domain-neutral ontology dashboard foundation with the Manufacturing Predictive Maintenance Pack, "
        "cookie authentication, workspace-scoped RBAC, and administrator audit."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
)


@app.exception_handler(EventNotFound)
async def not_found_handler(_: Request, exc: EventNotFound) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "not_found", "message": f"resource not found: {exc.args[0]}"}},
    )


@app.exception_handler(AuthError)
async def auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(ValueError)
async def validation_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "contract_validation_failed", "message": str(exc)}},
    )


def current_principal(
    request: Request,
    identity: IdentityService = Depends(get_identity_service),
) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthError(401, "authentication_required", "로그인이 필요합니다.")
    return identity.principal_for_token(token)


def require_permission(permission: str) -> Callable[..., Principal]:
    def dependency(
        principal: Principal = Depends(current_principal),
        identity: IdentityService = Depends(get_identity_service),
    ) -> Principal:
        identity.require_permission(principal, permission)
        return principal

    return dependency


def require_manufacturing_scope(
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
) -> Principal:
    identity.require_workspace(principal, MANUFACTURING_WORKSPACE)
    return principal


def require_csrf(
    request: Request,
    identity: IdentityService = Depends(get_identity_service),
) -> None:
    identity.verify_csrf(request.cookies.get(CSRF_COOKIE), request.headers.get("X-CSRF-Token"))


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ontology-dashboard",
        "mode": "offline-capable",
        "domain_pack": "manufacturing-predictive-maintenance",
    }


@app.post("/api/auth/register", status_code=201)
def register(request: RegisterRequest, identity: IdentityService = Depends(get_identity_service)):
    user = identity.register(request)
    return {
        "user_id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "status": user["status"],
        "requested_organization_name": user["requested_organization_name"],
    }


@app.post("/api/auth/login")
def login(
    request: LoginRequest,
    response: Response,
    identity: IdentityService = Depends(get_identity_service),
):
    principal, token, expires_at, csrf_token = identity.login(request)
    max_age = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        expires=expires_at,
        httponly=True,
        secure=identity.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        expires=expires_at,
        httponly=False,
        secure=identity.secure_cookies,
        samesite="lax",
        path="/",
    )
    return {"user": principal.model_dump(mode="json"), "csrf_token": csrf_token}


@app.post("/api/auth/logout", status_code=204)
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


@app.get("/api/auth/me")
def me(request: Request, principal: Principal = Depends(current_principal)):
    return {
        "user": principal.model_dump(mode="json"),
        "csrf_token": request.cookies.get(CSRF_COOKIE),
    }


@app.get("/api/workspaces")
def list_workspaces(
    principal: Principal = Depends(require_permission("app.access")),
    identity: IdentityService = Depends(get_identity_service),
):
    items = [
        workspace
        for workspace in identity.repository.list_workspaces()
        if workspace["id"] in principal.workspace_scopes
    ]
    return {"items": items}


@app.get("/api/domain-packs")
def list_domain_packs(_: Principal = Depends(require_permission("ontology.registry.read"))):
    return {"items": [MANUFACTURING_PACK.model_dump(mode="json")]}


@app.get("/api/ontology/registry")
def ontology_registry(_: Principal = Depends(require_permission("ontology.registry.read"))):
    return registry_payload()


@app.get("/api/ontology/object-types")
def list_object_types(_: Principal = Depends(require_permission("ontology.registry.read"))):
    return {"items": [item.model_dump(mode="json") for item in OBJECT_TYPES]}


@app.get("/api/ontology/link-types")
def list_link_types(_: Principal = Depends(require_permission("ontology.registry.read"))):
    return {"items": [item.model_dump(mode="json") for item in LINK_TYPES]}


@app.get("/api/ontology/action-types")
def list_action_types(_: Principal = Depends(require_permission("ontology.registry.read"))):
    return {"items": [item.model_dump(mode="json") for item in ACTION_TYPES]}


@app.get("/api/equipment")
def list_equipment(
    _: Principal = Depends(require_manufacturing_scope),
    service: FactorySignalService = Depends(get_service),
):
    return {"items": service.list_equipment()}


@app.get("/api/equipment/{equipment_id}")
def get_equipment(
    equipment_id: str,
    _: Principal = Depends(require_manufacturing_scope),
    service: FactorySignalService = Depends(get_service),
):
    return service.equipment(equipment_id)


@app.get("/api/events")
def list_events(
    _: Principal = Depends(require_manufacturing_scope),
    service: FactorySignalService = Depends(get_service),
):
    return {"items": service.list_events()}


@app.get("/api/events/{event_id}")
def get_event(
    event_id: str,
    _: Principal = Depends(require_manufacturing_scope),
    service: FactorySignalService = Depends(get_service),
):
    return service.event(event_id)


@app.get("/api/events/{event_id}/evidence")
def get_evidence(
    event_id: str,
    _: Principal = Depends(require_manufacturing_scope),
    service: FactorySignalService = Depends(get_service),
):
    return service.evidence(event_id)


@app.post("/api/events/{event_id}/report")
def create_report(
    event_id: str,
    request: ReportRequest,
    principal: Principal = Depends(require_manufacturing_scope),
    service: FactorySignalService = Depends(get_service),
    identity: IdentityService = Depends(get_identity_service),
):
    role = identity.legacy_dashboard_role(principal, request.role)
    report, trace = service.report(event_id, ReportRequest(role=role, use_llm=request.use_llm))
    return {"report": report.model_dump(mode="json"), "trace": trace}


@app.post("/api/events/{event_id}/layout")
def create_layout(
    event_id: str,
    request: LayoutRequest,
    principal: Principal = Depends(require_manufacturing_scope),
    service: FactorySignalService = Depends(get_service),
    identity: IdentityService = Depends(get_identity_service),
):
    role = identity.legacy_dashboard_role(principal, request.role)
    layout, trace = service.layout(
        event_id,
        LayoutRequest(role=role, intent=request.intent, use_llm=request.use_llm),
    )
    return {"layout": layout.model_dump(mode="json"), "trace": trace}


@app.post("/api/events/{event_id}/decision")
def record_decision(
    event_id: str,
    request: DecisionRequest,
    principal: Principal = Depends(require_permission("events.decision")),
    _: None = Depends(require_csrf),
    service: FactorySignalService = Depends(get_service),
    identity: IdentityService = Depends(get_identity_service),
):
    identity.require_workspace(principal, MANUFACTURING_WORKSPACE)
    safe_request = DecisionRequest(
        actor=principal.display_name,
        decision=request.decision,
        note=request.note,
    )
    return service.decide(event_id, safe_request)


@app.post("/api/events/{event_id}/notes")
def add_note(
    event_id: str,
    request: NoteRequest,
    principal: Principal = Depends(require_permission("events.note")),
    _: None = Depends(require_csrf),
    service: FactorySignalService = Depends(get_service),
    identity: IdentityService = Depends(get_identity_service),
):
    identity.require_workspace(principal, MANUFACTURING_WORKSPACE)
    safe_request = NoteRequest(actor=principal.display_name, body=request.body)
    return service.note(event_id, safe_request)


@app.post("/api/events/{event_id}/follow-up")
def follow_up(
    event_id: str,
    request: FollowUpRequest,
    principal: Principal = Depends(require_manufacturing_scope),
    _: None = Depends(require_csrf),
    service: FactorySignalService = Depends(get_service),
    identity: IdentityService = Depends(get_identity_service),
):
    role = identity.legacy_dashboard_role(principal, request.role)
    safe_request = FollowUpRequest(role=role, question=request.question)
    return service.follow_up(event_id, safe_request).model_dump(mode="json")


@app.get("/api/events/{event_id}/activity")
def event_activity(
    event_id: str,
    _: Principal = Depends(require_manufacturing_scope),
    service: FactorySignalService = Depends(get_service),
):
    service.event(event_id)
    return service.repository.event_activity(event_id)


@app.get("/api/admin/overview")
def admin_overview(
    _: Principal = Depends(require_permission("admin.access")),
    identity: IdentityService = Depends(get_identity_service),
):
    users = identity.repository.list_users()
    return {
        "active_users": sum(user["status"] == "active" for user in users),
        "pending_users": sum(user["status"] == "pending_approval" for user in users),
        "disabled_users": sum(user["status"] == "disabled" for user in users),
        "workspace_count": len(identity.repository.list_workspaces()),
        "recent_admin_changes": identity.repository.list_admin_audit(limit=5),
    }


@app.get("/api/admin/users")
def admin_users(
    _: Principal = Depends(require_permission("admin.users.read")),
    identity: IdentityService = Depends(get_identity_service),
):
    return {"items": identity.repository.list_users()}


@app.patch("/api/admin/users/{user_id}")
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
    )


@app.get("/api/admin/roles")
def admin_roles(
    _: Principal = Depends(require_permission("admin.users.read")),
    identity: IdentityService = Depends(get_identity_service),
):
    return {"items": identity.repository.list_roles()}


@app.get("/api/admin/workspaces")
def admin_workspaces(
    _: Principal = Depends(require_permission("admin.users.read")),
    identity: IdentityService = Depends(get_identity_service),
):
    return {"items": identity.repository.list_workspaces()}


@app.get("/api/admin/audit")
def admin_audit(
    _: Principal = Depends(require_permission("admin.audit.read")),
    identity: IdentityService = Depends(get_identity_service),
):
    return {"items": identity.repository.list_admin_audit()}


@app.get("/api/openapi-contract")
def openapi_contract() -> dict:
    return app.openapi()
