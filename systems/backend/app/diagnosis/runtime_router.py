"""V3.1 Result Artifact, canonical observation, and replay APIs."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import uuid
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
DEMO_LIVE_MODEL_HASH = "d" * 64
DEMO_LIVE_FEATURE_SCHEMA_HASH = "e" * 64
DEMO_LIVE_HISTORY_SCHEMA_HASH = "f" * 64
DEMO_LIVE_LABEL_SCHEMA_HASH = "a" * 64
DEMO_LIVE_TARGET_ASSET_ID = "CNC-S04-L04-01"


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


def _demo_live_status(score: float) -> str:
    if score >= 0.78:
        return "critical"
    if score >= 0.62:
        return "warning"
    if score >= 0.42:
        return "attention"
    return "normal"


def _demo_live_sha(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _demo_live_batch(
    *,
    service: PredictiveMaintenanceRuntimeService,
    principal: Principal,
    project_id: str,
    workspace_id: str,
    dataset_version_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    versions = service.versions(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        user_id=principal.user_id,
    )
    selected_version_id = dataset_version_id or versions.default_dataset_version_id
    version = next(
        (item for item in versions.items if item.dataset_version_id == selected_version_id),
        versions.items[0] if versions.items else None,
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Dataset Version not found for realtime demo tick")
    latest = service.latest_results(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        dataset_version_id=version.dataset_version_id,
        offset=0,
        limit=500,
    )
    candidates = sorted(
        latest.items,
        key=lambda item: (
            0 if item.asset_type == "compressor" else 1,
            item.site_id,
            item.cell_id,
            item.asset_id,
        ),
    )
    if not candidates:
        raise HTTPException(status_code=404, detail="No assets available for realtime demo tick")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    sequence = int(now.timestamp() // 5)
    target = next(
        (item for item in candidates if item.asset_id == DEMO_LIVE_TARGET_ASSET_ID),
        candidates[0],
    )
    score_pattern = [0.84, 0.88, 0.91, 0.87, 0.89]
    pattern_index = sequence % len(score_pattern)
    score = score_pattern[pattern_index]
    tool_wear_min = round(86.4 + pattern_index * 1.25, 2)
    torque_nm = round(34.8 + pattern_index * 2.15, 2)
    temperature_gap_k = round(6.9 + pattern_index * 0.45, 2)
    air_temperature_k = round(298.15 + ((sequence % 3) - 1) * 0.35, 2)
    process_temperature_k = round(air_temperature_k + temperature_gap_k, 2)
    rotational_speed_rpm = round(1880 - pattern_index * 58, 2)
    status_grade = _demo_live_status(score)
    batch_id = f"demo-live-{now.strftime('%Y%m%dT%H%M%SZ')}-{target.asset_id}"
    event_id = f"demo-live-event-{target.asset_id}-{uuid.uuid5(uuid.NAMESPACE_URL, batch_id).hex[:12]}"
    source_ref = {
        "uri": f"demo/realtime-role-wireframe/{target.asset_id}/{now.isoformat().replace('+00:00', 'Z')}",
        "sha256": _demo_live_sha(
            {
                "asset_id": target.asset_id,
                "observed_at": now.isoformat().replace("+00:00", "Z"),
                "score": score,
                "source": "realtime-role-wireframe-demo",
            }
        ),
    }
    lineage = {
        "simulation_session_id": "presentation-live-demo",
        "overlay_branch_id": "realtime-role-wireframe",
        "history_segment_id": None,
        "maintenance_event_id": None,
        "maintenance_action_id": None,
        "state_version": max(1, sequence),
    }
    item = {
        "event_id": event_id,
        "asset_id": target.asset_id,
        "observed_at": now.isoformat().replace("+00:00", "Z"),
        "source_kind": "simulation_overlay",
        "source_ref": source_ref,
        "payload_sha256": "1" * 64,
        "output_status": "predicted",
        "score": score,
        "model_id": "hanbit-live-demo-risk",
        "model_version": "presentation-live-v1",
        "model_artifact_manifest_sha256": DEMO_LIVE_MODEL_HASH,
        "feature_schema_version": "presentation-live-v1",
        "history_requirement_version": "presentation-live-v1",
        "label_schema_version": "presentation-live-v1",
        "feature_schema_sha256": DEMO_LIVE_FEATURE_SCHEMA_HASH,
        "history_requirement_sha256": DEMO_LIVE_HISTORY_SCHEMA_HASH,
        "label_schema_sha256": DEMO_LIVE_LABEL_SCHEMA_HASH,
        "lineage": lineage,
        "explanation": {
            "top_factors": [
                {
                    "feature": "tool_wear_min",
                    "display_name": "공구 마모",
                    "feature_value": tool_wear_min,
                    "signed_contribution": 0.37,
                    "direction": "risk_up",
                    "explanation_method": "presentation_live_signal",
                    "evidence_field_id": "demo.signal.tool_wear_min",
                    "source_ref": source_ref,
                },
                {
                    "feature": "torque_nm",
                    "display_name": "토크 부하",
                    "feature_value": torque_nm,
                    "signed_contribution": 0.29,
                    "direction": "risk_up",
                    "explanation_method": "presentation_live_signal",
                    "evidence_field_id": "demo.signal.torque_nm",
                    "source_ref": source_ref,
                },
                {
                    "feature": "temperature_gap_k",
                    "display_name": "공정 온도 편차",
                    "feature_value": temperature_gap_k,
                    "signed_contribution": 0.21,
                    "direction": "risk_up",
                    "explanation_method": "presentation_live_signal",
                    "evidence_field_id": "demo.signal.temperature_gap_k",
                    "source_ref": source_ref,
                },
            ],
            "confidence_label": "high",
            "explanation_method": "presentation_live_demo_generator",
            "feature_snapshot_ref": source_ref,
            "sensor_window_ref": source_ref,
            "display_labels": {
                "tool_wear_min": "공구 마모",
                "torque_nm": "토크 부하",
                "temperature_gap_k": "공정 온도 편차",
            },
        },
        "failure_reason": None,
    }
    item["payload_sha256"] = service._prediction_item_sha256(item)
    batch = {
        "contract_version": "prediction-result-batch-v1",
        "batch_id": batch_id,
        "producer": {
            "system": "systems.generator",
            "runtime_version": "presentation-live-v1",
            "outbox_id": f"presentation-live-{uuid.uuid5(uuid.NAMESPACE_URL, event_id).hex[:10]}",
        },
        "emitted_at": now.isoformat().replace("+00:00", "Z"),
        "source_context": {
            "dataset_id": version.dataset_id,
            "dataset_version": version.dataset_version_id,
            "source_uri": source_ref["uri"],
            "source_checksum": source_ref["sha256"],
            "source_kind": "simulation_overlay",
            "source_contract_version": "presentation-live-demo-v1",
            "source_schema_version": "presentation-live-demo-v1",
            "pipeline_contract_version": "generator-prediction-result-v1",
            "lineage": lineage,
        },
        "model_set": {
            "model_set_id": "hanbit-live-demo-risk-set",
            "model_set_version": "presentation-live-v1",
            "models": [
                {
                    "model_id": "hanbit-live-demo-risk",
                    "model_version": "presentation-live-v1",
                    "required": True,
                    "model_artifact_manifest_sha256": DEMO_LIVE_MODEL_HASH,
                    "selected_threshold": 0.62,
                }
            ],
        },
        "results": [item],
    }
    return batch, {
        "asset_id": target.asset_id,
        "asset_type": target.asset_type,
        "site_id": target.site_id,
        "cell_id": target.cell_id,
        "event_id": event_id,
        "score": score,
        "status_grade": status_grade,
        "observed_at": now.isoformat().replace("+00:00", "Z"),
        "sensor_observation": {
            "product_type": "demo-part-a",
            "air_temperature_k": air_temperature_k,
            "process_temperature_k": process_temperature_k,
            "rotational_speed_rpm": rotational_speed_rpm,
            "torque_nm": torque_nm,
            "tool_wear_min": tool_wear_min,
        },
    }


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
