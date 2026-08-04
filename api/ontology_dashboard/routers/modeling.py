from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_identity_service, get_modeling_service, require_permission
from ..identity import IdentityService, Principal
from ..modeling import ModelingService
from ..modeling.models import (
    IntakeProfileRequest,
    ManifestDraftCreateRequest,
    ManifestDraftDecisionRequest,
    ManifestDraftUpdateRequest,
)
from .predictive_maintenance_runtime import require_scope

router = APIRouter(prefix="/api/modeling", tags=["modeling"])


@router.get("/contracts")
def modeling_contracts(
    project_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("ml.console.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return {
        **service.contract_summary().model_dump(mode="json"),
        "artifact_capability": service.artifact_capability(),
        "organization_id": principal.organization_id,
        "project_id": project_id,
        "workspace_id": workspace_id,
    }


@router.post("/intake/profiles")
def create_intake_profile(
    request: IntakeProfileRequest,
    principal: Principal = Depends(require_permission("datasets.ingest")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    try:
        return service.profile_source(
            organization_id=principal.organization_id,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            source_path=request.source_path,
            sheet=request.sheet,
            use_llm=request.use_llm,
            idempotency_key=request.idempotency_key,
            actor_id=principal.user_id,
        ).model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dataset Intake source not found") from exc


@router.get("/intake/profiles/{profile_id}")
def get_intake_profile(
    profile_id: str,
    project_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("datasets.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    try:
        return service.intake_profile(
            profile_id,
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        ).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset Intake Profile not found") from exc


@router.post("/manifest-drafts")
def create_manifest_draft(
    request: ManifestDraftCreateRequest,
    principal: Principal = Depends(require_permission("datasets.ingest")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.create_manifest_draft(
        profile_id=request.profile_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        idempotency_key=request.idempotency_key,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.get("/manifest-drafts/{draft_id}")
def get_manifest_draft(
    draft_id: str,
    project_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("datasets.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    try:
        return service.manifest_draft(
            draft_id,
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        ).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Manifest Draft not found") from exc


@router.patch("/manifest-drafts/{draft_id}")
def update_manifest_draft(
    draft_id: str,
    request: ManifestDraftUpdateRequest,
    principal: Principal = Depends(require_permission("datasets.ingest")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.update_manifest_draft(
        draft_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.post("/manifest-drafts/{draft_id}/decision")
def decide_manifest_draft(
    draft_id: str,
    request: ManifestDraftDecisionRequest,
    principal: Principal = Depends(require_permission("datasets.ingest")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.decide_manifest_draft(
        draft_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.get("/manifest-drafts/{draft_id}/approved-manifest")
def approved_manifest_payload(
    draft_id: str,
    project_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("datasets.ingest")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return service.approved_manifest_payload(
        draft_id,
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
    )
