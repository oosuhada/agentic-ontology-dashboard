"""V3.1 Result Artifact, canonical observation, and replay APIs."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from ..dependencies import (
    get_identity_service,
    get_predictive_maintenance_runtime_service,
    require_csrf,
    require_permission,
)
from ..identity import IdentityService, Principal
from ..predictive_maintenance_runtime import (
    PredictiveMaintenanceRuntimeService,
    ReplayControlRequest,
    ReplayStartRequest,
)
from ..predictive_maintenance_runtime.repository import ALLOWED_DERIVED_MEASURES

router = APIRouter(
    prefix="/api/projects/{project_id}/workspaces/{workspace_id}/predictive-maintenance",
    tags=["predictive-maintenance-runtime"],
)


def require_scope(
    *,
    principal: Principal,
    identity: IdentityService,
    project_id: str,
    workspace_id: str,
) -> None:
    identity.require_project(principal, project_id)
    identity.require_workspace(principal, workspace_id)


@router.get("/context")
def runtime_context(
    project_id: str,
    workspace_id: str,
    dataset_version_id: str | None = Query(default=None, max_length=160),
    principal: Principal = Depends(require_permission("datasets.read")),
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
            dataset_version_id=dataset_version_id,
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
    principal: Principal = Depends(require_permission("datasets.read")),
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
        dataset_version_id=dataset_version_id,
        asset_id=asset_id,
        site_id=site_id,
        cell_id=cell_id,
        asset_type=asset_type,
        status_grade=status_grade,
        offset=offset,
        limit=limit,
    ).model_dump(mode="json")


@router.get("/snapshots/{prediction_id}")
def snapshot_drilldown(
    project_id: str,
    workspace_id: str,
    prediction_id: str,
    dataset_version_id: str | None = Query(default=None, max_length=160),
    principal: Principal = Depends(require_permission("datasets.read")),
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
            dataset_version_id=dataset_version_id,
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
    principal: Principal = Depends(require_permission("datasets.read")),
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
        dataset_version_id=dataset_version_id,
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
    principal: Principal = Depends(require_permission("datasets.read")),
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
        dataset_version_id=dataset_version_id,
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


@router.post("/replay/sessions", status_code=status.HTTP_201_CREATED)
def start_replay(
    project_id: str,
    workspace_id: str,
    payload: ReplayStartRequest,
    principal: Principal = Depends(require_permission("datasets.read")),
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
        dataset_version_id=payload.dataset_version_id,
        start_time=payload.start_time,
        speed=payload.speed_minutes_per_second,
    ).model_dump(mode="json")


@router.get("/replay/sessions/{session_id}")
def replay_snapshot(
    project_id: str,
    workspace_id: str,
    session_id: str,
    principal: Principal = Depends(require_permission("datasets.read")),
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
    principal: Principal = Depends(require_permission("datasets.read")),
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
    principal: Principal = Depends(require_permission("datasets.read")),
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
