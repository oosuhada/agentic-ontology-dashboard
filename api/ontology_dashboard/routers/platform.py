from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import (
    database_target,
    get_application_runtime_repository,
    get_artifact_governance_service,
    get_branching_lineage_repository,
    get_connector_repository,
    get_connector_service,
    get_durable_job_repository,
    get_ontology_primitive_repository,
    get_project_service,
    require_csrf,
    require_permission,
)
from ..artifact_storage import (
    ArtifactGovernanceService,
    ArtifactGovernanceSnapshot,
    ArtifactObject,
    ArtifactOperatorRequest,
    ArtifactPermissionError,
    ArtifactReconciliationReport,
    SignedArtifactDownload,
    artifact_storage_readiness,
)
from ..application_runtime import (
    ApplicationRuntimeRepository,
    ApplicationRuntimeSnapshot,
    SearchRequest,
)
from ..branching_lineage import (
    BranchChangeRequest,
    BranchDiff,
    BranchingLineageRepository,
    BranchingLineageSnapshot,
    PolicyCheckRequest,
    PolicyDecision,
)
from ..connectors import (
    ConnectorRepository,
    ConnectorRunRequest,
    ConnectorService,
    ConnectorSnapshot,
    connector_readiness,
)
from ..distributed_runtime import (
    DistributedRuntimeSnapshot,
    DurableJobEventPage,
    DurableJobRepository,
    JobOperatorRequest,
    distributed_runtime_readiness,
)
from ..domain_packs import ProjectApplicationDefinition, list_domain_packs, resolve_domain_pack
from ..enterprise_identity import enterprise_identity_readiness
from ..deployment import deployment_readiness
from ..identity import Principal
from ..ontology_primitives import (
    ActionPreview,
    ActionPreviewRequest,
    FunctionExecution,
    FunctionExecutionRequest,
    OntologyPrimitiveRepository,
    PrimitiveSnapshot,
)
from ..pipeline_runtime import PipelinePlan, PipelinePlanRequest, plan_pipeline, sample_pipeline
from ..mlops_runtime import DriftEvaluationRequest, MLOpsSnapshot, evaluate_drift, mlops_snapshot
from ..automation_runtime import (
    AutomationSimulationRequest,
    AutomationSnapshot,
    automation_snapshot,
    simulate_automation,
)
from ..projects import ProjectService
from ..persistence_readiness import persistence_readiness
from ..observability import ObservabilityReadiness, observability_readiness

router = APIRouter(prefix="/api/platform", tags=["platform"])


@router.get("/domain-packs")
def domain_pack_catalog(
    _: Principal = Depends(require_permission("app.access")),
):
    return {"items": [item.model_dump(mode="json") for item in list_domain_packs()]}


@router.get("/projects/{project_id}/applications/v4")
def project_v4_application(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
):
    project = projects.get_for_principal(principal, project_id)
    workspaces = projects.list_workspaces(principal, project_id)
    domain_pack, configuration_source = resolve_domain_pack(project.domain_pack_code)
    return ProjectApplicationDefinition(
        application_id="ontology-commercial-v4",
        project_id=project.id,
        workspace_ids=tuple(item["id"] for item in workspaces),
        domain_pack=domain_pack,
        configuration_source=configuration_source,
    ).model_dump(mode="json")


@router.get("/projects/{project_id}/persistence-readiness")
def project_persistence_readiness(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
):
    projects.get_for_principal(principal, project_id)
    return persistence_readiness(database_target()).model_dump(mode="json")


@router.get("/projects/{project_id}/enterprise-identity")
def project_enterprise_identity(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
):
    projects.get_for_principal(principal, project_id)
    return enterprise_identity_readiness().model_dump(mode="json")


@router.get("/projects/{project_id}/deployment-readiness")
def project_deployment_readiness(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
):
    projects.get_for_principal(principal, project_id)
    return deployment_readiness(Path(__file__).resolve().parents[3]).model_dump(mode="json")


@router.get("/projects/{project_id}/distributed-runtime")
def project_distributed_runtime(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
    jobs: DurableJobRepository = Depends(get_durable_job_repository),
):
    projects.get_for_principal(principal, project_id)
    readiness = distributed_runtime_readiness(
        jobs.database,
        organization_id=principal.organization_id,
        project_id=project_id,
    )
    recent = jobs.list_jobs(
        organization_id=principal.organization_id,
        project_id=project_id,
        limit=30,
    )
    dead_letters = tuple(item for item in recent if item.state == "dead_letter")
    return DistributedRuntimeSnapshot(
        readiness=readiness,
        jobs=recent,
        dead_letters=dead_letters,
    ).model_dump(mode="json")


@router.get("/projects/{project_id}/artifact-governance")
def project_artifact_governance(
    project_id: str,
    principal: Principal = Depends(require_permission("governance.read")),
    projects: ProjectService = Depends(get_project_service),
    service: ArtifactGovernanceService = Depends(get_artifact_governance_service),
) -> ArtifactGovernanceSnapshot:
    project = projects.get_for_principal(principal, project_id)
    return ArtifactGovernanceSnapshot(
        readiness=artifact_storage_readiness(),
        artifacts=service.repository.list(
            organization_id=principal.organization_id,
            project_id=project_id,
            limit=100,
        ),
        retention_preview=service.retention_preview(
            organization_id=principal.organization_id,
            project_id=project_id,
        ),
        last_reconciliation=None,
    )


def _project_artifact(
    *,
    service: ArtifactGovernanceService,
    principal: Principal,
    project_id: str,
    artifact_id: str,
) -> ArtifactObject:
    artifact = service.repository.get(
        organization_id=principal.organization_id,
        project_id=project_id,
        artifact_id=artifact_id,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return artifact


@router.post("/projects/{project_id}/artifacts/{artifact_id}/verify")
def verify_project_artifact(
    project_id: str,
    artifact_id: str,
    request: ArtifactOperatorRequest,
    principal: Principal = Depends(require_permission("governance.projection.retry")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    service: ArtifactGovernanceService = Depends(get_artifact_governance_service),
) -> ArtifactObject:
    projects.get_for_principal(principal, project_id)
    artifact = _project_artifact(
        service=service,
        principal=principal,
        project_id=project_id,
        artifact_id=artifact_id,
    )
    return service.verify(artifact, actor_user_id=principal.user_id)


@router.post("/projects/{project_id}/artifacts/{artifact_id}/sign-download")
def sign_project_artifact_download(
    project_id: str,
    artifact_id: str,
    request: ArtifactOperatorRequest,
    principal: Principal = Depends(require_permission("governance.read")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    service: ArtifactGovernanceService = Depends(get_artifact_governance_service),
) -> SignedArtifactDownload:
    projects.get_for_principal(principal, project_id)
    artifact = _project_artifact(
        service=service,
        principal=principal,
        project_id=project_id,
        artifact_id=artifact_id,
    )
    try:
        return service.sign_download(
            artifact,
            actor_user_id=principal.user_id,
            purpose=request.purpose,
        )
    except ArtifactPermissionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/projects/{project_id}/artifact-reconciliation")
def reconcile_project_artifacts(
    project_id: str,
    request: ArtifactOperatorRequest,
    apply: bool = Query(default=False),
    principal: Principal = Depends(require_permission("governance.projection.retry")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    service: ArtifactGovernanceService = Depends(get_artifact_governance_service),
) -> ArtifactReconciliationReport:
    project = projects.get_for_principal(principal, project_id)
    return service.reconcile(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=project.default_workspace_id,
        actor_user_id=principal.user_id,
        apply=apply,
    )


@router.get("/projects/{project_id}/observability")
def project_observability(
    project_id: str,
    principal: Principal = Depends(require_permission("governance.read")),
    projects: ProjectService = Depends(get_project_service),
) -> ObservabilityReadiness:
    projects.get_for_principal(principal, project_id)
    return observability_readiness()


@router.get("/projects/{project_id}/connectors")
def project_connectors(
    project_id: str,
    principal: Principal = Depends(require_permission("governance.read")),
    projects: ProjectService = Depends(get_project_service),
    repository: ConnectorRepository = Depends(get_connector_repository),
):
    project = projects.get_for_principal(principal, project_id)
    repository.ensure_fixture(
        organization_id=principal.organization_id,
        project_id=project_id,
        workspace_id=project.default_workspace_id or "manufacturing-demo",
        actor=principal.user_id,
    )
    runs = repository.list_runs(principal.organization_id, project_id)
    return ConnectorSnapshot(
        readiness=connector_readiness(),
        connectors=repository.list_definitions(principal.organization_id, project_id),
        runs=runs,
        quarantine_count=getattr(repository, "last_quarantine_count", 0),
    ).model_dump(mode="json")


@router.post("/projects/{project_id}/connectors/{connector_id}/run")
def run_project_connector(
    project_id: str,
    connector_id: str,
    request: ConnectorRunRequest,
    principal: Principal = Depends(require_permission("governance.projection.retry")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    service: ConnectorService = Depends(get_connector_service),
):
    projects.get_for_principal(principal, project_id)
    definition = service.repository.get(principal.organization_id, project_id, connector_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="connector not found")
    job_id = service.enqueue(definition, actor=principal.user_id)
    return {"job_id": job_id, "state": "queued", "reason": request.reason}


@router.get("/projects/{project_id}/ontology-primitives")
def project_ontology_primitives(
    project_id: str,
    principal: Principal = Depends(require_permission("ontology.registry.read")),
    projects: ProjectService = Depends(get_project_service),
    repository: OntologyPrimitiveRepository = Depends(get_ontology_primitive_repository),
) -> PrimitiveSnapshot:
    projects.get_for_principal(principal, project_id)
    repository.ensure_samples(principal.organization_id, project_id, principal.user_id)
    return repository.snapshot(principal.organization_id, project_id)


@router.post("/projects/{project_id}/actions/preview")
def preview_project_action(
    project_id: str,
    request: ActionPreviewRequest,
    principal: Principal = Depends(require_permission("ontology.actions.execute")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    repository: OntologyPrimitiveRepository = Depends(get_ontology_primitive_repository),
) -> ActionPreview:
    projects.get_for_principal(principal, project_id)
    repository.ensure_samples(principal.organization_id, project_id, principal.user_id)
    try:
        return repository.preview_action(
            principal.organization_id, project_id, request, principal.user_id
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/projects/{project_id}/functions/execute")
def execute_project_function(
    project_id: str,
    request: FunctionExecutionRequest,
    principal: Principal = Depends(require_permission("ontology.objects.read")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    repository: OntologyPrimitiveRepository = Depends(get_ontology_primitive_repository),
) -> FunctionExecution:
    projects.get_for_principal(principal, project_id)
    repository.ensure_samples(principal.organization_id, project_id, principal.user_id)
    try:
        return repository.execute_function(
            principal.organization_id, project_id, request, principal.user_id
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/projects/{project_id}/branching-lineage")
def project_branching_lineage(
    project_id: str,
    principal: Principal = Depends(require_permission("governance.read")),
    projects: ProjectService = Depends(get_project_service),
    repository: BranchingLineageRepository = Depends(get_branching_lineage_repository),
) -> BranchingLineageSnapshot:
    projects.get_for_principal(principal, project_id)
    repository.ensure_samples(principal.organization_id, project_id, principal.user_id)
    return repository.snapshot(principal.organization_id, project_id)


@router.post("/projects/{project_id}/branches/change")
def create_project_branch_change(
    project_id: str,
    request: BranchChangeRequest,
    principal: Principal = Depends(require_permission("governance.projection.retry")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    repository: BranchingLineageRepository = Depends(get_branching_lineage_repository),
) -> BranchDiff:
    projects.get_for_principal(principal, project_id)
    repository.ensure_samples(principal.organization_id, project_id, principal.user_id)
    try:
        return repository.create_change(
            principal.organization_id, project_id, request, principal.user_id
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/projects/{project_id}/branches/{branch_id}/merge")
def merge_project_branch(
    project_id: str,
    branch_id: str,
    principal: Principal = Depends(require_permission("governance.projection.retry")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    repository: BranchingLineageRepository = Depends(get_branching_lineage_repository),
) -> BranchDiff:
    projects.get_for_principal(principal, project_id)
    try:
        return repository.merge(principal.organization_id, project_id, branch_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/projects/{project_id}/policy/check")
def check_project_policy(
    project_id: str,
    request: PolicyCheckRequest,
    principal: Principal = Depends(require_permission("app.access")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    repository: BranchingLineageRepository = Depends(get_branching_lineage_repository),
) -> PolicyDecision:
    projects.get_for_principal(principal, project_id)
    repository.ensure_samples(principal.organization_id, project_id, principal.user_id)
    return repository.policy_check(
        principal.organization_id, project_id, principal.user_id, request
    )


@router.get("/projects/{project_id}/application-runtime")
def project_application_runtime(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
    repository: ApplicationRuntimeRepository = Depends(get_application_runtime_repository),
) -> ApplicationRuntimeSnapshot:
    projects.get_for_principal(principal, project_id)
    repository.ensure_samples(principal.organization_id, project_id)
    return repository.snapshot(principal.organization_id, project_id)


@router.post("/projects/{project_id}/global-search")
def project_global_search(
    project_id: str,
    request: SearchRequest,
    principal: Principal = Depends(require_permission("app.access")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    repository: ApplicationRuntimeRepository = Depends(get_application_runtime_repository),
) -> dict[str, object]:
    projects.get_for_principal(principal, project_id)
    repository.ensure_samples(principal.organization_id, project_id)
    return {
        "items": repository.search(
            principal.organization_id,
            project_id,
            request,
        )
    }


@router.get("/projects/{project_id}/pipeline/sample-plan")
def project_sample_pipeline_plan(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
) -> PipelinePlan:
    projects.get_for_principal(principal, project_id)
    return plan_pipeline(sample_pipeline())


@router.post("/projects/{project_id}/pipeline/plan")
def project_pipeline_plan(
    project_id: str,
    request: PipelinePlanRequest,
    principal: Principal = Depends(require_permission("app.access")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
) -> PipelinePlan:
    projects.get_for_principal(principal, project_id)
    try:
        return plan_pipeline(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/projects/{project_id}/mlops")
def project_mlops(
    project_id: str,
    principal: Principal = Depends(require_permission("ml.console.read")),
    projects: ProjectService = Depends(get_project_service),
) -> MLOpsSnapshot:
    projects.get_for_principal(principal, project_id)
    return mlops_snapshot()


@router.post("/projects/{project_id}/mlops/drift/evaluate")
def project_mlops_drift_evaluate(
    project_id: str,
    request: DriftEvaluationRequest,
    principal: Principal = Depends(require_permission("ml.console.read")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
) -> dict[str, object]:
    projects.get_for_principal(principal, project_id)
    return evaluate_drift(request)


@router.get("/projects/{project_id}/automation")
def project_automation(
    project_id: str,
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
) -> AutomationSnapshot:
    projects.get_for_principal(principal, project_id)
    return automation_snapshot()


@router.post("/projects/{project_id}/automation/simulate")
def project_automation_simulate(
    project_id: str,
    request: AutomationSimulationRequest,
    principal: Principal = Depends(require_permission("ontology.actions.execute")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
) -> dict[str, object]:
    projects.get_for_principal(principal, project_id)
    return simulate_automation(request)


@router.get("/projects/{project_id}/distributed-job-events")
def project_distributed_job_events(
    project_id: str,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_permission("app.access")),
    projects: ProjectService = Depends(get_project_service),
    jobs: DurableJobRepository = Depends(get_durable_job_repository),
):
    projects.get_for_principal(principal, project_id)
    items = jobs.events_after(
        organization_id=principal.organization_id,
        project_id=project_id,
        cursor=cursor,
        limit=limit,
    )
    return DurableJobEventPage(
        items=items,
        next_cursor=items[-1].cursor if items else cursor,
    ).model_dump(mode="json")


@router.post("/projects/{project_id}/distributed-jobs/{job_id}/cancel")
def cancel_distributed_job(
    project_id: str,
    job_id: str,
    request: JobOperatorRequest,
    principal: Principal = Depends(require_permission("governance.projection.retry")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    jobs: DurableJobRepository = Depends(get_durable_job_repository),
):
    projects.get_for_principal(principal, project_id)
    try:
        return jobs.cancel(
            organization_id=principal.organization_id,
            project_id=project_id,
            job_id=job_id,
            reason=request.reason,
        ).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail="distributed job not found") from error


@router.post("/projects/{project_id}/distributed-jobs/{job_id}/replay")
def replay_distributed_job(
    project_id: str,
    job_id: str,
    request: JobOperatorRequest,
    principal: Principal = Depends(require_permission("governance.projection.retry")),
    _: None = Depends(require_csrf),
    projects: ProjectService = Depends(get_project_service),
    jobs: DurableJobRepository = Depends(get_durable_job_repository),
):
    projects.get_for_principal(principal, project_id)
    try:
        return jobs.replay(
            organization_id=principal.organization_id,
            project_id=project_id,
            job_id=job_id,
            actor_user_id=principal.user_id,
        ).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail="distributed job not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
