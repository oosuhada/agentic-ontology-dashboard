"""V3.1 Result Artifact, canonical observation, and replay APIs."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.operations.contracts import AppLocale
from app.dependencies import (
    client_ip,
    get_identity_service,
    get_predictive_maintenance_runtime_service,
    require_csrf,
    require_permission,
)
from app.identity import CSRF_COOKIE, SESSION_COOKIE, AuthError, IdentityService, Principal
from app.diagnosis.runtime_schema import (
    DatasetVersionSelectionRequest,
    ReplayControlRequest,
    ReplayStartRequest,
)
from app.diagnosis.runtime_service import PredictiveMaintenanceRuntimeService
from app.diagnosis.ports import ALLOWED_DERIVED_MEASURES

router = APIRouter(
    prefix="/api/projects/{project_id}/workspaces/{workspace_id}/predictive-maintenance",
    tags=["predictive-maintenance-runtime"],
)
internal_router = APIRouter(prefix="/internal", tags=["prediction-result-inbox"])
PREDICTION_RESULT_INGEST_TOKEN_ENV = "PREDICTION_RESULT_INGEST_TOKEN"
PREDICTION_RESULT_INGEST_ORG_ENV = "PREDICTION_RESULT_INGEST_ORGANIZATION_ID"


def require_scope(
    *,
    principal: Principal,
    identity: IdentityService,
    project_id: str,
    workspace_id: str,
) -> None:
    identity.require_project(principal, project_id)
    identity.require_workspace(principal, workspace_id)


def selected_dataset_version(
    *,
    service: PredictiveMaintenanceRuntimeService,
    principal: Principal,
    project_id: str,
    workspace_id: str,
    requested: str | None,
) -> str | None:
    if requested:
        return requested
    return service.versions(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        user_id=principal.user_id,
    ).default_dataset_version_id


def _prediction_inbox_response(receipt):
    body = receipt.model_dump(mode="json")
    if receipt.validation_status == "conflict":
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=body)
    if receipt.validation_status == "rejected":
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=body,
        )
    if receipt.validation_status == "duplicate":
        return JSONResponse(status_code=status.HTTP_200_OK, content=body)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body)


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def _prediction_result_service_principal(*, project_id: str, workspace_id: str) -> Principal:
    return Principal(
        user_id="service:generator-runtime",
        organization_id=os.getenv(PREDICTION_RESULT_INGEST_ORG_ENV, "org-ontology-demo"),
        email="generator-runtime@service.local",
        display_name="Generator Runtime",
        status="active",
        roles=["service"],
        permissions=["predictions.ingest"],
        workspace_scopes=[workspace_id],
        project_scopes=[project_id],
        active_project_id=project_id,
        active_project_roles=["service"],
        is_admin=False,
        default_path="/internal/prediction-results",
        landing_key="internal",
    )


def internal_prediction_ingest_principal(
    request: Request,
    project_id: str = Query(max_length=160),
    workspace_id: str = Query(max_length=160),
    identity: IdentityService = Depends(get_identity_service),
) -> Principal:
    configured_token = os.getenv(PREDICTION_RESULT_INGEST_TOKEN_ENV, "").strip()
    supplied_token = _bearer_token(request.headers.get("Authorization"))
    if configured_token:
        if supplied_token and hmac.compare_digest(supplied_token, configured_token):
            return _prediction_result_service_principal(
                project_id=project_id,
                workspace_id=workspace_id,
            )
        if supplied_token:
            raise AuthError("authentication_required", "Prediction Result service token is invalid.")

    session_token = request.cookies.get(SESSION_COOKIE)
    if not session_token:
        raise AuthError("authentication_required", "로그인이 필요합니다.")
    principal = identity.principal_for_token(
        session_token,
        user_agent=request.headers.get("User-Agent"),
        client_ip=client_ip(request),
    )
    identity.require_permission(principal, "predictions.ingest")
    identity.verify_csrf(request.cookies.get(CSRF_COOKIE), request.headers.get("X-CSRF-Token"))
    return principal


@router.get("/context")
def runtime_context(
    project_id: str,
    workspace_id: str,
    dataset_version_id: str | None = Query(default=None, max_length=160),
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    try:
        return service.context(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=selected_dataset_version(
                service=service,
                principal=principal,
                project_id=project_id,
                workspace_id=workspace_id,
                requested=dataset_version_id,
            ),
            user_id=principal.user_id,
        ).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"Dataset Version not found: {error.args[0]}") from error


@router.get("/versions")
def runtime_versions(
    project_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return service.versions(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        user_id=principal.user_id,
    ).model_dump(mode="json")


@router.put("/selection")
def select_runtime_version(
    project_id: str,
    workspace_id: str,
    payload: DatasetVersionSelectionRequest,
    principal: Principal = Depends(require_permission("events.read")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    try:
        return service.select_version(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            user_id=principal.user_id,
            dataset_version_id=payload.dataset_version_id,
        ).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail=f"Dataset Version not found in this Project and Workspace: {error.args[0]}",
        ) from error


@router.get("/dashboard")
def dashboard_source(
    project_id: str,
    workspace_id: str,
    dataset_version_id: str | None = Query(default=None, max_length=160),
    selected_event_id: str | None = Query(default=None, max_length=320),
    role: str = Query(default="manager", pattern="^(manager|engineer|executive)$"),
    report_type: str | None = Query(
        default=None,
        pattern="^(inspection-summary|operations-decision|executive-brief|maintenance-effect|weekly-risk)$",
    ),
    intent: str = Query(
        default="overview",
        pattern="^(overview|explain-risk|compare|summarize-manager|detail-engineer|recommend-check|show-model-details)$",
    ),
    locale: AppLocale = Query(default="ko-KR"),
    view: Literal["legacy", "canonical"] = Query(default="legacy"),
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    try:
        response = service.dashboard(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            user_id=principal.user_id,
            dataset_version_id=dataset_version_id,
            selected_event_id=selected_event_id,
            role=role,
            report_type=report_type,
            intent=intent,
            locale=locale,
            view=view,
        )
        if selected_event_id and response.selected_event_id != selected_event_id:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "selected_snapshot_not_found",
                    "message": "The explicitly selected Decision Case snapshot could not be restored.",
                    "selected_event_id": selected_event_id,
                },
            )
        return response.model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"Dataset Version not found: {error.args[0]}") from error


@router.get("/release")
def release_overview(
    project_id: str,
    workspace_id: str,
    dataset_version_id: str | None = Query(default=None, max_length=160),
    principal: Principal = Depends(require_permission("governance.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    try:
        return service.release_overview(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=selected_dataset_version(
                service=service,
                principal=principal,
                project_id=project_id,
                workspace_id=workspace_id,
                requested=dataset_version_id,
            ),
            user_id=principal.user_id,
        ).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"Dataset Version not found: {error.args[0]}") from error


@router.get("/results/latest")
def latest_product_results(
    project_id: str,
    workspace_id: str,
    dataset_version_id: str | None = Query(default=None, max_length=160),
    asset_id: str | None = Query(default=None, max_length=160),
    site_id: str | None = Query(default=None, max_length=160),
    cell_id: str | None = Query(default=None, max_length=160),
    asset_type: str | None = Query(default=None, pattern="^(compressor|cnc)$"),
    status_grade: str | None = Query(
        default=None, pattern="^(normal|attention|warning|critical)$"
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return service.latest_results(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        dataset_version_id=selected_dataset_version(
            service=service,
            principal=principal,
            project_id=project_id,
            workspace_id=workspace_id,
            requested=dataset_version_id,
        ),
        asset_id=asset_id,
        site_id=site_id,
        cell_id=cell_id,
        asset_type=asset_type,
        status_grade=status_grade,
        offset=offset,
        limit=limit,
    ).model_dump(mode="json")


@router.get("/results/post-maintenance")
def post_maintenance_product_result(
    project_id: str,
    workspace_id: str,
    asset_id: str = Query(min_length=1, max_length=160),
    maintenance_event_id: str = Query(min_length=1, max_length=240),
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    result = service.post_maintenance_result(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        asset_id=asset_id,
        maintenance_event_id=maintenance_event_id,
    )
    return None if result is None else result.model_dump(mode="json")


@router.get("/snapshots/{prediction_id}")
def snapshot_drilldown(
    project_id: str,
    workspace_id: str,
    prediction_id: str,
    dataset_version_id: str | None = Query(default=None, max_length=160),
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    try:
        return service.snapshot_drilldown(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=selected_dataset_version(
                service=service,
                principal=principal,
                project_id=project_id,
                workspace_id=workspace_id,
                requested=dataset_version_id,
            ),
            prediction_id=prediction_id,
        ).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"prediction not found: {error.args[0]}") from error


@router.get("/timeline")
def prediction_timeline(
    project_id: str,
    workspace_id: str,
    dataset_version_id: str | None = Query(default=None, max_length=160),
    asset_id: str | None = Query(default=None, max_length=160),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return service.timeline(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        dataset_version_id=selected_dataset_version(
            service=service,
            principal=principal,
            project_id=project_id,
            workspace_id=workspace_id,
            requested=dataset_version_id,
        ),
        asset_id=asset_id,
        start=start,
        end=end,
        offset=offset,
        limit=limit,
    )


@router.get("/observations")
def observation_window(
    project_id: str,
    workspace_id: str,
    start: datetime,
    end: datetime,
    dataset_version_id: str | None = Query(default=None, max_length=160),
    asset_id: str | None = Query(default=None, max_length=160),
    site_id: str | None = Query(default=None, max_length=160),
    cell_id: str | None = Query(default=None, max_length=160),
    asset_type: str | None = Query(default=None, pattern="^(compressor|cnc)$"),
    grain: str = Query(default="raw", pattern="^(raw|10m|1h)$"),
    derived_measure: list[str] = Query(default=[]),
    limit: int = Query(default=1000, ge=1, le=5000),
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    selected = set(derived_measure)
    invalid = selected - ALLOWED_DERIVED_MEASURES
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported derived measures: {sorted(invalid)}",
        )
    return service.observations(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        dataset_version_id=selected_dataset_version(
            service=service,
            principal=principal,
            project_id=project_id,
            workspace_id=workspace_id,
            requested=dataset_version_id,
        ),
        start=start,
        end=end,
        asset_id=asset_id,
        site_id=site_id,
        cell_id=cell_id,
        asset_type=asset_type,
        grain=grain,
        derived_measures=selected,
        limit=limit,
    ).model_dump(mode="json")


@router.post("/prediction-result-batches")
def receive_prediction_result_batch(
    project_id: str,
    workspace_id: str,
    payload: dict[str, Any] = Body(...),
    principal: Principal = Depends(require_permission("predictions.ingest")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    receipt = service.receive_prediction_result_batch(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        payload=payload,
    )
    return _prediction_inbox_response(receipt)


@router.post("/prediction-result-batches/validate")
def validate_prediction_result_batch(
    project_id: str,
    workspace_id: str,
    payload: dict[str, Any] = Body(...),
    principal: Principal = Depends(require_permission("predictions.ingest")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    return receive_prediction_result_batch(
        project_id=project_id,
        workspace_id=workspace_id,
        payload=payload,
        principal=principal,
        _=_,
        identity=identity,
        service=service,
    )


@router.post("/prediction-result-batches/{batch_id}/promote")
def promote_prediction_result_batch(
    project_id: str,
    workspace_id: str,
    batch_id: str,
    principal: Principal = Depends(require_permission("predictions.ingest")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    try:
        return service.promote_prediction_result_batch(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            batch_id=batch_id,
        ).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prediction Result Batch is not accepted or does not exist.",
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error


@router.post("/replay/sessions", status_code=status.HTTP_201_CREATED)
def start_replay(
    project_id: str,
    workspace_id: str,
    payload: ReplayStartRequest,
    principal: Principal = Depends(require_permission("events.read")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return service.create_replay(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        user_id=principal.user_id,
        dataset_version_id=selected_dataset_version(
            service=service,
            principal=principal,
            project_id=project_id,
            workspace_id=workspace_id,
            requested=payload.dataset_version_id,
        ),
        start_time=payload.start_time,
        speed=payload.speed_minutes_per_second,
    ).model_dump(mode="json")


@router.get("/replay/sessions/{session_id}")
def replay_snapshot(
    project_id: str,
    workspace_id: str,
    session_id: str,
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    try:
        return service.replay_snapshot(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            session_id=session_id,
        ).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"replay session not found: {error.args[0]}") from error


@router.post("/replay/sessions/{session_id}/{action}")
def control_replay(
    project_id: str,
    workspace_id: str,
    session_id: str,
    action: str,
    payload: ReplayControlRequest,
    principal: Principal = Depends(require_permission("events.read")),
    _: None = Depends(require_csrf),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    if action not in {"pause", "resume", "reset", "seek", "speed"}:
        raise HTTPException(status_code=404, detail="unsupported replay action")
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return service.control_replay(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        session_id=session_id,
        action=action,
        time_value=payload.time,
        speed=payload.speed_minutes_per_second,
    ).model_dump(mode="json")


@router.get("/replay/sessions/{session_id}/events")
async def replay_events(
    request: Request,
    project_id: str,
    workspace_id: str,
    session_id: str,
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )

    async def stream():
        last_sequence = -1
        heartbeat = 0
        while not await request.is_disconnected():
            try:
                snapshot = service.replay_snapshot(
                    organization_id=principal.organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    session_id=session_id,
                )
            except KeyError:
                yield "event: error\ndata: {\"code\":\"replay_session_not_found\"}\n\n"
                return
            if snapshot.cursor.sequence != last_sequence:
                last_sequence = snapshot.cursor.sequence
                payload = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False)
                yield f"id: {last_sequence}\nevent: replay\ndata: {payload}\n\n"
                heartbeat = 0
            else:
                heartbeat += 1
                if heartbeat >= 15:
                    yield ": keep-alive\n\n"
                    heartbeat = 0
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@internal_router.post("/prediction-results")
def receive_internal_prediction_results(
    payload: dict[str, Any] = Body(...),
    project_id: str = Query(max_length=160),
    workspace_id: str = Query(max_length=160),
    principal: Principal = Depends(internal_prediction_ingest_principal),
    identity: IdentityService = Depends(get_identity_service),
    service: PredictiveMaintenanceRuntimeService = Depends(
        get_predictive_maintenance_runtime_service
    ),
):
    identity.require_permission(principal, "predictions.ingest")
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    receipt = service.receive_prediction_result_batch(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        payload=payload,
    )
    if receipt.validation_status in {"accepted", "duplicate"}:
        try:
            promotion = service.promote_prediction_result_batch(
                organization_id=principal.organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                batch_id=receipt.batch_id,
            )
        except KeyError:
            if receipt.validation_status == "duplicate":
                return _prediction_inbox_response(receipt)
            raise
        receipt = receipt.model_copy(
            update={
                "promotion_status": promotion.promotion_status,
                "product_result_created": promotion.product_result_created,
                "promoted_results": promotion.promoted_results,
                "already_promoted_results": promotion.already_promoted_results,
                "skipped_results": promotion.skipped_results,
                "product_result_ids": promotion.product_result_ids,
                "artifact_ids": promotion.artifact_ids,
            }
        )
    return _prediction_inbox_response(receipt)
