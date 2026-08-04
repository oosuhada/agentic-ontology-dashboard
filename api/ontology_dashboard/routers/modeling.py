from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..adapters.service import AdapterService
from ..dependencies import (
    get_adapter_service,
    get_identity_service,
    get_modeling_service,
    require_permission,
)
from ..identity import IdentityService, Principal
from ..modeling import ModelingService
from ..modeling.models import (
    IntakeProfileRequest,
    ManifestDraftCreateRequest,
    ManifestDraftDecisionRequest,
    ManifestDraftUpdateRequest,
    ManifestIngestRequest,
    MappingCandidateDecisionRequest,
    MappingGenerateRequest,
    MappingSetCloneRequest,
    MappingSetDecisionRequest,
    FeatureMaterializationRequest,
    FeatureRecipeSetCreateRequest,
    FeatureRecipeSetDecisionRequest,
    ExperimentCreateRequest,
    ExperimentCancelRequest,
    ExperimentRecoverRequest,
    ExperimentRetryRequest,
    ModelActivateRequest,
    ModelReleaseDecisionRequest,
    ModelReleaseRequestCreate,
    ModelRollbackRequest,
    ModelScoreRequest,
    ModelVersionCreateRequest,
)
from ..modeling.experiments import dependency_capabilities
from .predictive_maintenance_runtime import require_scope

router = APIRouter(prefix="/api/modeling", tags=["modeling"])


def require_roles(principal: Principal, *roles: str) -> None:
    if not set(principal.roles).intersection(roles):
        raise HTTPException(status_code=403, detail=f"one of roles {roles} is required")


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


@router.post("/manifest-drafts/{draft_id}/ingest", status_code=201)
def ingest_approved_manifest_draft(
    draft_id: str,
    request: ManifestIngestRequest,
    principal: Principal = Depends(require_permission("datasets.ingest")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
    adapters: AdapterService = Depends(get_adapter_service),
):
    require_roles(principal, "fde", "ml_validator", "tenant_admin")
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    manifest = service.adapter_manifest(
        draft_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
    )
    result = adapters.ingest(principal, request.project_id, manifest)
    detail = adapters.dataset_catalog.detail(
        principal=principal,
        project_id=request.project_id,
        dataset_id=manifest.manifest_id,
    )
    dataset_version = next(
        (
            item
            for item in detail.versions
            if item.source_version == manifest.dataset_version
        ),
        None,
    )
    if dataset_version is None:
        raise HTTPException(
            status_code=500,
            detail="Adapter ingestion completed without a Dataset Version",
        )
    return {
        "ingestion": result.model_dump(mode="json"),
        "dataset_id": detail.id,
        "dataset_version": dataset_version.model_dump(mode="json"),
        "manifest_draft_id": draft_id,
    }


@router.post("/mapping-sets")
def create_mapping_set(
    request: MappingGenerateRequest,
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
    return service.create_mapping_set(
        profile_id=request.profile_id,
        dataset_version_id=request.dataset_version_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        use_llm=request.use_llm,
        idempotency_key=request.idempotency_key,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.get("/mapping-sets/{mapping_set_id}")
def get_mapping_set(
    mapping_set_id: str,
    project_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("ontology.registry.read")),
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
        return service.mapping_set(
            mapping_set_id,
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        ).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Mapping Set not found") from exc


@router.post("/mapping-sets/{mapping_set_id}/candidate-decision")
def decide_mapping_candidate(
    mapping_set_id: str,
    request: MappingCandidateDecisionRequest,
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
    return service.decide_mapping_candidate(
        mapping_set_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.post("/mapping-sets/{mapping_set_id}/decision")
def decide_mapping_set(
    mapping_set_id: str,
    request: MappingSetDecisionRequest,
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
    return service.decide_mapping_set(
        mapping_set_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.post("/mapping-sets/{mapping_set_id}/versions")
def clone_mapping_set(
    mapping_set_id: str,
    request: MappingSetCloneRequest,
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
    return service.clone_mapping_set(
        mapping_set_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        idempotency_key=request.idempotency_key,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.get("/mapping-sets/{mapping_set_id}/capabilities")
def mapping_capabilities(
    mapping_set_id: str,
    project_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("ontology.registry.read")),
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
        "items": [
            item.model_dump(mode="json")
            for item in service.mapping_capabilities(
                mapping_set_id,
                organization_id=principal.organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        ]
    }


@router.post("/feature-recipe-sets")
def create_feature_recipe_set(
    request: FeatureRecipeSetCreateRequest,
    principal: Principal = Depends(require_permission("ml.console.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.create_feature_recipe_set(
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.get("/feature-recipe-sets/{recipe_set_id}")
def get_feature_recipe_set(
    recipe_set_id: str,
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
    try:
        return service.feature_recipe_set(
            recipe_set_id,
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        ).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Feature Recipe Set not found") from exc


@router.post("/feature-recipe-sets/{recipe_set_id}/decision")
def decide_feature_recipe_set(
    recipe_set_id: str,
    request: FeatureRecipeSetDecisionRequest,
    principal: Principal = Depends(require_permission("ml.console.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.decide_feature_recipe_set(
        recipe_set_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.post("/feature-datasets/materialize")
def materialize_feature_dataset(
    request: FeatureMaterializationRequest,
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
    return service.materialize_features(
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.get("/feature-datasets/{feature_dataset_version_id}")
def get_feature_dataset_version(
    feature_dataset_version_id: str,
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
    try:
        return service.feature_dataset_version(
            feature_dataset_version_id,
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        ).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Feature Dataset Version not found") from exc


@router.get("/experiment-capabilities")
def experiment_capabilities(
    project_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("ml.console.read")),
    identity: IdentityService = Depends(get_identity_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return {
        "synchronous_training_endpoint": False,
        "execution_mode": "queued_worker_or_cli",
        "algorithms": dependency_capabilities(),
    }


@router.post("/experiments", status_code=202)
def queue_experiment(
    request: ExperimentCreateRequest,
    principal: Principal = Depends(require_permission("ml.console.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.queue_experiment(
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.get("/experiments")
def list_experiments(
    project_id: str,
    workspace_id: str,
    limit: int = 100,
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
        "items": [
            item.model_dump(mode="json")
            for item in service.list_experiments(
                organization_id=principal.organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                limit=limit,
            )
        ]
    }


@router.get("/experiments/{experiment_id}")
def get_experiment(
    experiment_id: str,
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
    try:
        return service.experiment(
            experiment_id,
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        ).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Experiment Run not found") from exc


@router.post("/experiments/{experiment_id}/retry", status_code=202)
def retry_experiment(
    experiment_id: str,
    request: ExperimentRetryRequest,
    principal: Principal = Depends(require_permission("ml.console.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.retry_experiment(
        experiment_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.post("/experiments/{experiment_id}/cancel")
def cancel_experiment(
    experiment_id: str,
    request: ExperimentCancelRequest,
    principal: Principal = Depends(require_permission("ml.console.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_roles(principal, "ml_validator", "tenant_admin")
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.cancel_experiment(
        experiment_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.post("/experiments/{experiment_id}/recover-stale", status_code=202)
def recover_stale_experiment(
    experiment_id: str,
    request: ExperimentRecoverRequest,
    principal: Principal = Depends(require_permission("ml.console.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_roles(principal, "ml_validator", "tenant_admin")
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.recover_stale_experiment(
        experiment_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.post("/model-versions")
def create_model_version(
    request: ModelVersionCreateRequest,
    principal: Principal = Depends(require_permission("ml.console.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_roles(principal, "ml_validator", "tenant_admin")
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.create_model_version(
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.get("/model-versions")
def list_model_versions(
    project_id: str,
    workspace_id: str,
    limit: int = 100,
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
        "items": [
            item.model_dump(mode="json")
            for item in service.list_model_versions(
                organization_id=principal.organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                limit=limit,
            )
        ]
    }


@router.get("/model-versions/{model_version_id}")
def get_model_version(
    model_version_id: str,
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
    try:
        return service.model_version(
            model_version_id,
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        ).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Model Version not found") from exc


@router.post("/model-versions/{model_version_id}/release-requests", status_code=202)
def request_model_release(
    model_version_id: str,
    request: ModelReleaseRequestCreate,
    principal: Principal = Depends(require_permission("ml.release.request")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_roles(principal, "ml_validator", "tenant_admin")
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.request_model_release(
        model_version_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.get("/model-release-requests")
def list_model_release_requests(
    project_id: str,
    workspace_id: str,
    limit: int = 100,
    principal: Principal = Depends(require_permission("governance.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_roles(principal, "ml_validator", "tenant_admin")
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return {
        "items": [
            item.model_dump(mode="json")
            for item in service.list_model_release_requests(
                organization_id=principal.organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                limit=limit,
            )
        ]
    }


@router.post("/model-release-requests/{release_request_id}/decision")
def decide_model_release(
    release_request_id: str,
    request: ModelReleaseDecisionRequest,
    principal: Principal = Depends(require_permission("ml.release.approve")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_roles(principal, "tenant_admin")
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    release, model = service.decide_model_release(
        release_request_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    )
    return {
        "release_request": release.model_dump(mode="json"),
        "model_version": model.model_dump(mode="json"),
    }


@router.post("/model-versions/{model_version_id}/activate")
def activate_model(
    model_version_id: str,
    request: ModelActivateRequest,
    principal: Principal = Depends(require_permission("ml.release.approve")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_roles(principal, "tenant_admin")
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.activate_model(
        model_version_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.post("/model-versions/rollback")
def rollback_model(
    request: ModelRollbackRequest,
    principal: Principal = Depends(require_permission("ml.release.approve")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_roles(principal, "tenant_admin")
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    return service.rollback_model(
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    ).model_dump(mode="json")


@router.post("/model-versions/{model_version_id}/score")
def score_model_version(
    model_version_id: str,
    request: ModelScoreRequest,
    principal: Principal = Depends(require_permission("events.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_scope(
        principal=principal,
        identity=identity,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
    )
    result, explanation = service.score_active_model(
        model_version_id,
        organization_id=principal.organization_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        request=request,
        actor_id=principal.user_id,
    )
    return {
        "prediction": result.model_dump(mode="json"),
        "explanation": explanation.model_dump(mode="json"),
    }


@router.get("/explanations/{explanation_id}")
def get_explanation(
    explanation_id: str,
    project_id: str,
    workspace_id: str,
    principal: Principal = Depends(require_permission("events.read")),
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
        return service.explanation(
            explanation_id,
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        ).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Explanation Artifact not found") from exc


@router.get("/workbench")
def modeling_workbench(
    project_id: str,
    workspace_id: str,
    selected_experiment_id: str | None = None,
    principal: Principal = Depends(require_permission("ml.console.read")),
    identity: IdentityService = Depends(get_identity_service),
    service: ModelingService = Depends(get_modeling_service),
):
    require_roles(principal, "ml_validator", "tenant_admin", "fde")
    require_scope(
        principal=principal,
        identity=identity,
        project_id=project_id,
        workspace_id=workspace_id,
    )
    return service.workbench_payload(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        selected_experiment_id=selected_experiment_id,
    )
