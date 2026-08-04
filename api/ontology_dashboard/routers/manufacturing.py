"""Manufacturing-compatible Event routes shared by Project showcase domain packs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from ..contracts import DecisionRequest, FollowUpRequest, LayoutRequest, NoteRequest, ReportRequest
from ..dependencies import (
    MANUFACTURING_WORKSPACE,
    get_identity_service,
    get_ontology_service,
    get_service,
    require_csrf,
    require_manufacturing_scope,
    require_permission,
)
from ..identity import AuthError, IdentityService, Principal
from ..ontology import ActionInvocation
from ..ontology_adapter import inspection_object_id, risk_event_object_id
from ..ontology_service import OntologyService
from ..service import ManufacturingPredictiveMaintenanceService

router = APIRouter(prefix="/api", tags=["manufacturing-domain-pack"])


def _require_active_event_project(
    principal: Principal,
    service: ManufacturingPredictiveMaintenanceService,
    event_id: str,
) -> str:
    project_id = service.project_id_for_event(event_id)
    if not principal.is_admin and project_id not in principal.project_scopes:
        raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 Event입니다.")
    if principal.active_project_id != project_id:
        raise AuthError(409, "active_project_mismatch", "먼저 Event가 속한 Project를 활성화해야 합니다.")
    return project_id


def _require_configured_action_project(project_id: str) -> None:
    if project_id != "manufacturing-demo-project":
        raise AuthError(
            422,
            "project_action_not_configured",
            "이 showcase Project는 현재 Evidence 조회 전용입니다. Action mapping을 먼저 게시해야 합니다.",
        )


@router.get("/equipment")
def list_equipment(
    _: Principal = Depends(require_manufacturing_scope),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    return {"items": service.list_equipment()}


@router.get("/equipment/{equipment_id}")
def get_equipment(
    equipment_id: str,
    _: Principal = Depends(require_manufacturing_scope),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    return service.equipment(equipment_id)


@router.get("/events")
def list_events(
    _: Principal = Depends(require_manufacturing_scope),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    return {"items": service.list_events()}


@router.get("/events/{event_id}")
def get_event(
    event_id: str,
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    _require_active_event_project(principal, service, event_id)
    return service.event(event_id)


@router.get("/events/{event_id}/evidence")
def get_evidence(
    event_id: str,
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    _require_active_event_project(principal, service, event_id)
    return service.evidence(event_id)


@router.post("/events/{event_id}/report")
def create_report(
    event_id: str,
    request: ReportRequest,
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    identity: IdentityService = Depends(get_identity_service),
):
    _require_active_event_project(principal, service, event_id)
    role = identity.legacy_dashboard_role(principal, request.role)
    report, trace = service.report(
        event_id,
        ReportRequest(role=role, use_llm=request.use_llm),
    )
    return {"report": report.model_dump(mode="json"), "trace": trace}


@router.post("/events/{event_id}/layout")
def create_layout(
    event_id: str,
    request: LayoutRequest,
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    identity: IdentityService = Depends(get_identity_service),
):
    _require_active_event_project(principal, service, event_id)
    role = identity.legacy_dashboard_role(principal, request.role)
    layout, trace = service.layout(
        event_id,
        LayoutRequest(role=role, intent=request.intent, use_llm=request.use_llm),
    )
    return {"layout": layout.model_dump(mode="json"), "trace": trace}


@router.post("/events/{event_id}/decision")
def record_decision(
    event_id: str,
    request: DecisionRequest,
    principal: Principal = Depends(require_permission("events.decision")),
    _: None = Depends(require_csrf),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    project_id = _require_active_event_project(principal, service, event_id)
    _require_configured_action_project(project_id)
    execution = ontology.invoke(
        ActionInvocation(
            action_type="record_operational_decision",
            object_id=risk_event_object_id(event_id),
            workspace_id=MANUFACTURING_WORKSPACE,
            parameters={"decision": request.decision, "note": request.note},
            idempotency_key=f"legacy-decision:{uuid.uuid4()}",
        ),
        principal,
    )
    return execution.result


@router.post("/events/{event_id}/notes")
def add_note(
    event_id: str,
    request: NoteRequest,
    principal: Principal = Depends(require_permission("events.note")),
    _: None = Depends(require_csrf),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    ontology: OntologyService = Depends(get_ontology_service),
):
    project_id = _require_active_event_project(principal, service, event_id)
    _require_configured_action_project(project_id)
    execution = ontology.invoke(
        ActionInvocation(
            action_type="record_inspection_note",
            object_id=inspection_object_id(event_id),
            workspace_id=MANUFACTURING_WORKSPACE,
            parameters={"body": request.body},
            idempotency_key=f"legacy-note:{uuid.uuid4()}",
        ),
        principal,
    )
    return execution.result


@router.post("/events/{event_id}/follow-up")
def follow_up(
    event_id: str,
    request: FollowUpRequest,
    principal: Principal = Depends(require_permission("events.read")),
    _: None = Depends(require_csrf),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
    identity: IdentityService = Depends(get_identity_service),
):
    _require_active_event_project(principal, service, event_id)
    role = identity.legacy_dashboard_role(principal, request.role)
    safe_request = FollowUpRequest(role=role, question=request.question)
    return service.follow_up(event_id, safe_request).model_dump(mode="json")


@router.get("/events/{event_id}/activity")
def event_activity(
    event_id: str,
    principal: Principal = Depends(require_permission("events.read")),
    service: ManufacturingPredictiveMaintenanceService = Depends(get_service),
):
    _require_active_event_project(principal, service, event_id)
    service.event(event_id)
    return service.repository.event_activity(event_id)
